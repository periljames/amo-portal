from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import WriteSessionLocal

from . import domain_models
from . import knowledge_models as km
from .workspace_service import can_read_manual, get_profile


INDEX_VERSION = 1
RECORD_ROOT = Path(os.getenv("DOCUMENT_RECORD_DIR", "uploads/documentation-records")).resolve()
CODE_CANDIDATE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,10}(?:[\s./_-]*\d{1,6})(?:[\s./_-]+[A-Z0-9]{1,10})?)(?![A-Za-z0-9])")

NODE_TYPES = {
    "ROOT",
    "MANAGEMENT_SYSTEM",
    "MANUAL",
    "POLICY",
    "PROCEDURE",
    "WORK_INSTRUCTION",
    "FORM",
    "CHECKLIST",
    "REGISTER",
    "EXTERNAL_DOCUMENT",
    "RECORD_SERIES",
}
CONTENT_NODE_TYPES = {
    "MANUAL",
    "POLICY",
    "PROCEDURE",
    "WORK_INSTRUCTION",
    "FORM",
    "CHECKLIST",
    "REGISTER",
    "EXTERNAL_DOCUMENT",
}
EXECUTABLE_NODE_TYPES = {"FORM", "CHECKLIST", "REGISTER"}
ALLOWED_CHILDREN: dict[str, set[str]] = {
    "ROOT": {"MANAGEMENT_SYSTEM", "MANUAL", "POLICY", "PROCEDURE", "WORK_INSTRUCTION", "FORM", "CHECKLIST", "REGISTER", "EXTERNAL_DOCUMENT", "RECORD_SERIES"},
    "MANAGEMENT_SYSTEM": {"MANAGEMENT_SYSTEM", "MANUAL", "POLICY", "PROCEDURE", "WORK_INSTRUCTION", "FORM", "CHECKLIST", "REGISTER", "EXTERNAL_DOCUMENT", "RECORD_SERIES"},
    "MANUAL": {"POLICY", "PROCEDURE", "WORK_INSTRUCTION", "FORM", "CHECKLIST", "REGISTER", "RECORD_SERIES"},
    "POLICY": {"PROCEDURE", "WORK_INSTRUCTION", "FORM", "CHECKLIST", "REGISTER", "RECORD_SERIES"},
    "PROCEDURE": {"WORK_INSTRUCTION", "FORM", "CHECKLIST", "REGISTER", "RECORD_SERIES"},
    "WORK_INSTRUCTION": {"FORM", "CHECKLIST", "REGISTER", "RECORD_SERIES"},
    "FORM": {"RECORD_SERIES"},
    "CHECKLIST": {"RECORD_SERIES"},
    "REGISTER": {"RECORD_SERIES"},
    "EXTERNAL_DOCUMENT": set(),
    "RECORD_SERIES": set(),
}

SYSTEM_GROUPS = (
    ("SYS-MANAGEMENT", "MANAGEMENT_SYSTEM", "Management systems", 10),
    ("SYS-OPERATIONS", "MANAGEMENT_SYSTEM", "Operations and maintenance", 20),
    ("SYS-SUPPORT", "MANAGEMENT_SYSTEM", "Support processes", 30),
    ("SYS-FORMS", "MANAGEMENT_SYSTEM", "Forms, checklists and registers", 40),
    ("SYS-EXTERNAL", "MANAGEMENT_SYSTEM", "External controlled information", 50),
    ("SYS-RECORDS", "MANAGEMENT_SYSTEM", "Records and retained evidence", 60),
)


def utcnow() -> datetime:
    return datetime.utcnow()


def normalize_code(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())[:128]


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return segment[:120] or "node"


def _node_path(parent: km.DocumentationNode | None, node_id: str, code: str) -> tuple[str, int]:
    segment = f"{_safe_segment(code)}~{node_id[:8]}"
    if not parent:
        return f"/{segment}", 0
    return f"{parent.path.rstrip('/')}/{segment}", int(parent.depth or 0) + 1


def _manual_node_type(manual: manual_models.Manual, profile: domain_models.DocumentControlProfile | None) -> str:
    source = " ".join(filter(None, [manual.manual_type, manual.code, manual.title])).upper()
    if profile and profile.document_class == "EXTERNAL":
        return "EXTERNAL_DOCUMENT"
    if "CHECKLIST" in source or re.search(r"\bCHK(?:LIST)?\b", source):
        return "CHECKLIST"
    if "FORM" in source or re.search(r"\bFRM\b", source):
        return "FORM"
    if "REGISTER" in source or re.search(r"\bREG\b", source):
        return "REGISTER"
    if "WORK INSTRUCTION" in source or re.search(r"\bWI\b", source):
        return "WORK_INSTRUCTION"
    if "PROCEDURE" in source or re.search(r"\bPROC\b", source):
        return "PROCEDURE"
    if "POLICY" in source:
        return "POLICY"
    return "MANUAL"


def _default_group_code(node_type: str, manual: manual_models.Manual, profile: domain_models.DocumentControlProfile | None) -> str:
    if node_type in EXECUTABLE_NODE_TYPES:
        return "SYS-FORMS"
    if node_type == "EXTERNAL_DOCUMENT":
        return "SYS-EXTERNAL"
    source = " ".join(filter(None, [manual.manual_type, manual.title, profile.owner_department if profile else None])).upper()
    if any(token in source for token in ("QUALITY", "SAFETY", "QMS", "SMS", "COMPLIANCE")):
        return "SYS-MANAGEMENT"
    if any(token in source for token in ("MAINTENANCE", "ENGINEERING", "OPERATIONS", "AIRWORTHINESS", "TECHNICAL")):
        return "SYS-OPERATIONS"
    return "SYS-SUPPORT"


def _query_manuals(db: Session, manual_tenant: manual_models.Tenant) -> list[manual_models.Manual]:
    return (
        db.query(manual_models.Manual)
        .filter(manual_models.Manual.tenant_id == manual_tenant.id)
        .order_by(manual_models.Manual.code.asc())
        .all()
    )


def _ensure_node(
    db: Session,
    *,
    tenant_id: str,
    code: str,
    title: str,
    node_type: str,
    parent: km.DocumentationNode | None,
    manual_id: str | None = None,
    order_index: int = 0,
    metadata: dict | None = None,
    actor_id: str | None = None,
) -> km.DocumentationNode:
    normalized = normalize_code(code)
    row = (
        db.query(km.DocumentationNode)
        .filter(km.DocumentationNode.tenant_id == tenant_id, km.DocumentationNode.normalized_code == normalized)
        .first()
    )
    if not row and manual_id:
        row = (
            db.query(km.DocumentationNode)
            .filter(km.DocumentationNode.tenant_id == tenant_id, km.DocumentationNode.manual_id == manual_id)
            .first()
        )
    if not row:
        node_id = str(uuid.uuid4())
        node_path, node_depth = _node_path(parent, node_id, code.strip())
        row = km.DocumentationNode(
            id=node_id,
            tenant_id=tenant_id,
            code=code.strip(),
            normalized_code=normalized,
            title=title.strip(),
            node_type=node_type,
            parent_id=parent.id if parent else None,
            manual_id=manual_id,
            path=node_path,
            depth=node_depth,
            order_index=order_index,
            metadata_json=dict(metadata or {}),
            created_by_user_id=actor_id,
        )
        db.add(row)
        db.flush()
    else:
        row.title = title.strip() or row.title
        if manual_id:
            row.manual_id = manual_id
        row.node_type = node_type
        if row.parent_id != (parent.id if parent else None):
            row.parent_id = parent.id if parent else None
            row.path, row.depth = _node_path(parent, row.id, row.code)
        if metadata:
            row.metadata_json = {**dict(row.metadata_json or {}), **metadata}
    return row


def _latest_revision(db: Session, manual_id: str) -> manual_models.ManualRevision | None:
    return (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual_id)
        .order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc())
        .first()
    )


def _has_acroform(revision: manual_models.ManualRevision | None) -> bool:
    path_value = str(getattr(revision, "source_storage_path", "") or "") if revision else ""
    if not path_value or str(getattr(revision, "source_type_enum", "")).upper().endswith("DOCX"):
        return False
    path = Path(path_value).resolve()
    if not path.exists() or path.suffix.lower() != ".pdf":
        return False
    try:
        import fitz  # type: ignore
        with fitz.open(path) as document:
            return any(page.first_widget is not None for page in document)
    except Exception:
        return False


def _ensure_execution_profile(
    db: Session,
    *,
    tenant_id: str,
    manual: manual_models.Manual,
    node_type: str,
    record_series: km.DocumentationNode,
    actor_id: str | None,
) -> km.DocumentationExecutionProfile:
    row = (
        db.query(km.DocumentationExecutionProfile)
        .filter(km.DocumentationExecutionProfile.tenant_id == tenant_id, km.DocumentationExecutionProfile.manual_id == manual.id)
        .first()
    )
    latest = _latest_revision(db, manual.id)
    acroform = _has_acroform(latest)
    if not row:
        row = km.DocumentationExecutionProfile(
            tenant_id=tenant_id,
            manual_id=manual.id,
            execution_type="PDF_ACROFORM" if acroform else ("CHECKLIST" if node_type == "CHECKLIST" else "DOWNLOADABLE_TEMPLATE"),
            submission_mode="FILL_AND_SUBMIT" if acroform else "DOWNLOAD_AND_UPLOAD",
            record_series_node_id=record_series.id,
            retention_years=7,
            allow_download=True,
            allow_save_draft=acroform,
            requires_signature=False,
            requires_review=False,
            metadata_json={"auto_detected_acroform": acroform},
            created_by_user_id=actor_id,
        )
        db.add(row)
    elif not row.record_series_node_id:
        row.record_series_node_id = record_series.id
    return row


def reconcile_documentation_hierarchy(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    actor_id: str | None = None,
) -> list[km.DocumentationNode]:
    tenant_id = str(manual_tenant.amo_id)
    root = _ensure_node(
        db,
        tenant_id=tenant_id,
        code="DOC-ROOT",
        title=f"{manual_tenant.name} documented information",
        node_type="ROOT",
        parent=None,
        order_index=0,
        metadata={"system": True, "iso_guidance": ["ISO 10013", "ISO 15489"]},
        actor_id=actor_id,
    )
    groups: dict[str, km.DocumentationNode] = {}
    for code, node_type, title, order_index in SYSTEM_GROUPS:
        groups[code] = _ensure_node(
            db,
            tenant_id=tenant_id,
            code=code,
            title=title,
            node_type=node_type,
            parent=root,
            order_index=order_index,
            metadata={"system": True},
            actor_id=actor_id,
        )

    profiles = {
        row.manual_id: row
        for row in db.query(domain_models.DocumentControlProfile).filter(domain_models.DocumentControlProfile.tenant_id == tenant_id).all()
    }
    for index, manual in enumerate(_query_manuals(db, manual_tenant), start=1):
        profile = profiles.get(manual.id)
        node_type = _manual_node_type(manual, profile)
        group = groups[_default_group_code(node_type, manual, profile)]
        node = _ensure_node(
            db,
            tenant_id=tenant_id,
            code=manual.code,
            title=manual.title,
            node_type=node_type,
            parent=group,
            manual_id=manual.id,
            order_index=index,
            metadata={
                "manual_type": manual.manual_type,
                "owner_role": manual.owner_role,
                "aliases": list(dict.fromkeys([manual.code, *list((profile.metadata_json or {}).get("aliases", []))])) if profile else [manual.code],
            },
            actor_id=actor_id,
        )
        if node_type in EXECUTABLE_NODE_TYPES:
            series_code = f"REC-{manual.code}"
            series = _ensure_node(
                db,
                tenant_id=tenant_id,
                code=series_code,
                title=f"{manual.title} completed records",
                node_type="RECORD_SERIES",
                parent=groups["SYS-RECORDS"],
                order_index=index,
                metadata={"template_manual_id": manual.id, "source_node_id": node.id},
                actor_id=actor_id,
            )
            _ensure_execution_profile(
                db,
                tenant_id=tenant_id,
                manual=manual,
                node_type=node_type,
                record_series=series,
                actor_id=actor_id,
            )
    db.flush()
    return (
        db.query(km.DocumentationNode)
        .filter(km.DocumentationNode.tenant_id == tenant_id, km.DocumentationNode.status == "ACTIVE")
        .order_by(km.DocumentationNode.depth.asc(), km.DocumentationNode.order_index.asc(), km.DocumentationNode.title.asc())
        .all()
    )


def validate_hierarchy_move(
    db: Session,
    *,
    tenant_id: str,
    node: km.DocumentationNode,
    parent: km.DocumentationNode | None,
    node_type: str,
) -> None:
    if node_type not in NODE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported documented-information type: {node_type}")
    if parent:
        if parent.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Hierarchy parent is outside the active AMO")
        if node.id == parent.id or parent.path.startswith(f"{node.path.rstrip('/')}/"):
            raise HTTPException(status_code=409, detail="A hierarchy node cannot be moved into itself or its descendant")
        if node_type not in ALLOWED_CHILDREN.get(parent.node_type, set()):
            raise HTTPException(status_code=409, detail=f"{node_type.replace('_', ' ').title()} cannot be placed under {parent.node_type.replace('_', ' ').title()}")
    elif node_type != "ROOT":
        raise HTTPException(status_code=409, detail="Only a hierarchy root may have no parent")
    if node_type in CONTENT_NODE_TYPES and not node.manual_id:
        raise HTTPException(status_code=409, detail="Controlled content nodes must be linked to a document register record")


def update_subtree_paths(db: Session, node: km.DocumentationNode, parent: km.DocumentationNode | None) -> None:
    old_path = node.path
    new_path, depth = _node_path(parent, node.id, node.code)
    depth_delta = depth - int(node.depth or 0)
    node.path = new_path
    node.depth = depth
    descendants = (
        db.query(km.DocumentationNode)
        .filter(km.DocumentationNode.tenant_id == node.tenant_id, km.DocumentationNode.path.like(f"{old_path.rstrip('/')}%"), km.DocumentationNode.id != node.id)
        .all()
    )
    for child in descendants:
        child.path = f"{new_path}{child.path[len(old_path):]}"
        child.depth = max(0, int(child.depth or 0) + depth_delta)


def hierarchy_payload(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    actor_id: str | None = None,
) -> dict:
    nodes = reconcile_documentation_hierarchy(db, manual_tenant=manual_tenant, actor_id=actor_id)
    manual_ids = [node.manual_id for node in nodes if node.manual_id]
    manuals = {
        row.id: row
        for row in db.query(manual_models.Manual).filter(manual_models.Manual.id.in_(manual_ids or ["-"])).all()
    }
    profiles = {
        row.manual_id: row
        for row in db.query(km.DocumentationExecutionProfile).filter(km.DocumentationExecutionProfile.tenant_id == manual_tenant.amo_id).all()
    }
    counts = defaultdict(int)
    for row in db.query(km.DocumentationReference.status).filter(km.DocumentationReference.tenant_id == manual_tenant.amo_id).all():
        counts[str(row[0])] += 1
    items: list[dict] = []
    for node in nodes:
        manual = manuals.get(node.manual_id)
        execution = profiles.get(node.manual_id)
        latest = _latest_revision(db, manual.id) if manual else None
        items.append({
            "id": node.id,
            "parent_id": node.parent_id,
            "node_type": node.node_type,
            "code": node.code,
            "title": node.title,
            "path": node.path,
            "depth": node.depth,
            "order_index": node.order_index,
            "manual_id": node.manual_id,
            "status": node.status,
            "metadata": dict(node.metadata_json or {}),
            "document": {
                "manual_type": manual.manual_type,
                "status": manual.status,
                "current_published_revision_id": manual.current_published_rev_id,
                "latest_revision_id": latest.id if latest else None,
                "latest_revision": latest.rev_number if latest else None,
                "source_type": str(getattr(getattr(latest, "source_type_enum", None), "value", getattr(latest, "source_type_enum", ""))) if latest else None,
            } if manual else None,
            "execution": serialize_execution_profile(execution) if execution else None,
        })
    return {
        "tenant_id": manual_tenant.amo_id,
        "root_id": next((node.id for node in nodes if node.node_type == "ROOT"), None),
        "items": items,
        "reference_health": dict(counts),
    }


def serialize_execution_profile(row: km.DocumentationExecutionProfile | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "execution_type": row.execution_type,
        "submission_mode": row.submission_mode,
        "record_series_node_id": row.record_series_node_id,
        "retention_years": row.retention_years,
        "naming_pattern": row.naming_pattern,
        "allow_download": row.allow_download,
        "allow_save_draft": row.allow_save_draft,
        "requires_signature": row.requires_signature,
        "requires_review": row.requires_review,
        "schema": dict(row.schema_json or {}),
        "access_scope": dict(row.access_scope_json or {}),
        "metadata": dict(row.metadata_json or {}),
        "version": row.version,
    }


def _aliases_by_manual(db: Session, manual_tenant: manual_models.Tenant) -> tuple[dict[str, list[manual_models.Manual]], list[tuple[re.Pattern[str], str, str]]]:
    manuals = _query_manuals(db, manual_tenant)
    nodes = {
        row.manual_id: row
        for row in db.query(km.DocumentationNode).filter(km.DocumentationNode.tenant_id == manual_tenant.amo_id, km.DocumentationNode.manual_id.isnot(None)).all()
    }
    normalized_map: dict[str, list[manual_models.Manual]] = defaultdict(list)
    patterns: list[tuple[re.Pattern[str], str, str]] = []
    seen_patterns: set[tuple[str, str]] = set()
    for manual in manuals:
        node = nodes.get(manual.id)
        aliases = [manual.code, *list((node.metadata_json or {}).get("aliases", []))] if node else [manual.code]
        for alias_value in aliases:
            alias = str(alias_value or "").strip()
            normalized = normalize_code(alias)
            if len(normalized) < 3:
                continue
            if manual not in normalized_map[normalized]:
                normalized_map[normalized].append(manual)
            pattern_key = (manual.id, alias.upper())
            if pattern_key in seen_patterns:
                continue
            seen_patterns.add(pattern_key)
            parts = re.split(r"([\s./_-]+)", alias)
            expression = "".join(r"[\s./_-]+" if re.fullmatch(r"[\s./_-]+", part or "") else re.escape(part) for part in parts if part)
            patterns.append((re.compile(rf"(?<![A-Za-z0-9])({expression})(?![A-Za-z0-9])", re.IGNORECASE), alias, normalized))
    patterns.sort(key=lambda item: len(item[1]), reverse=True)
    return normalized_map, patterns


def _target_revision(db: Session, manual: manual_models.Manual) -> manual_models.ManualRevision | None:
    if not manual.current_published_rev_id:
        return None
    return (
        db.query(manual_models.ManualRevision)
        .filter(
            manual_models.ManualRevision.id == manual.current_published_rev_id,
            manual_models.ManualRevision.manual_id == manual.id,
            manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
        )
        .first()
    )


def _target_relationship(db: Session, tenant_id: str, manual_id: str | None) -> str:
    if not manual_id:
        return "REFERENCES"
    node = (
        db.query(km.DocumentationNode)
        .filter(km.DocumentationNode.tenant_id == tenant_id, km.DocumentationNode.manual_id == manual_id)
        .first()
    )
    if not node:
        return "REFERENCES"
    return {"FORM": "USES_FORM", "CHECKLIST": "USES_CHECKLIST", "REGISTER": "UPDATES_REGISTER"}.get(node.node_type, "REFERENCES")


def _context(text: str, start: int, end: int) -> str:
    return text[max(0, start - 110):min(len(text), end + 160)].strip()


def _bbox_for_occurrence(document, page_number: int | None, raw_token: str) -> dict:
    if not document or not page_number or page_number < 1 or page_number > document.page_count:
        return {}
    try:
        page = document.load_page(page_number - 1)
        rects = page.search_for(raw_token, quads=False)
        if not rects:
            return {}
        rect = rects[0]
        page_rect = page.rect
        if not page_rect.width or not page_rect.height:
            return {}
        return {
            "x": round(rect.x0 / page_rect.width, 6),
            "y": round(rect.y0 / page_rect.height, 6),
            "width": round(rect.width / page_rect.width, 6),
            "height": round(rect.height / page_rect.height, 6),
        }
    except Exception:
        return {}


def _source_pdf(revision: manual_models.ManualRevision):
    path_value = str(revision.source_storage_path or "")
    if not path_value or str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper() != "PDF":
        return None
    path = Path(path_value).resolve()
    if not path.exists():
        return None
    try:
        import fitz  # type: ignore
        return fitz.open(path)
    except Exception:
        return None


def index_revision_references(db: Session, *, revision_id: str) -> dict:
    revision = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.id == revision_id).first()
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found for reference indexing")
    manual = db.query(manual_models.Manual).filter(manual_models.Manual.id == revision.manual_id).first()
    manual_tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.id == manual.tenant_id).first() if manual else None
    if not manual or not manual_tenant:
        raise HTTPException(status_code=404, detail="Document tenant could not be resolved")
    tenant_id = str(manual_tenant.amo_id)
    reconcile_documentation_hierarchy(db, manual_tenant=manual_tenant, actor_id=revision.created_by)
    job = (
        db.query(km.DocumentationIndexJob)
        .filter(km.DocumentationIndexJob.tenant_id == tenant_id, km.DocumentationIndexJob.revision_id == revision.id)
        .first()
    )
    if not job:
        job = km.DocumentationIndexJob(tenant_id=tenant_id, manual_id=manual.id, revision_id=revision.id)
        db.add(job)
    job.status = "RUNNING"
    job.started_at = utcnow()
    job.completed_at = None
    job.error_summary = None
    job.source_sha256 = revision.source_sha256
    job.index_version = INDEX_VERSION
    db.flush()

    try:
        normalized_map, alias_patterns = _aliases_by_manual(db, manual_tenant)
        execution_profiles = {
            row.manual_id: row
            for row in db.query(km.DocumentationExecutionProfile).filter(km.DocumentationExecutionProfile.tenant_id == tenant_id).all()
        }
        existing = {
            row.occurrence_key: row
            for row in db.query(km.DocumentationReference).filter(km.DocumentationReference.source_revision_id == revision.id).all()
        }
        for row in existing.values():
            if row.status == "VERIFIED":
                row.status = "OUTDATED"
            else:
                db.delete(row)
        db.flush()

        sections = (
            db.query(manual_models.ManualSection)
            .filter(manual_models.ManualSection.revision_id == revision.id)
            .order_by(manual_models.ManualSection.order_index.asc())
            .all()
        )
        section_map = {section.id: section for section in sections}
        blocks = (
            db.query(manual_models.ManualBlock)
            .filter(manual_models.ManualBlock.section_id.in_(list(section_map) or ["-"]))
            .order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc())
            .all()
        )
        pdf_document = _source_pdf(revision)
        seen_occurrences: set[str] = set()
        detected = resolved = unresolved = broken = 0

        for block in blocks:
            text = str(block.text_plain or "")
            if not text:
                continue
            section = section_map.get(block.section_id)
            page_number = int((section.metadata_json or {}).get("page_start") or 0) or None if section else None
            matched_spans: list[tuple[int, int]] = []
            occurrences: list[tuple[int, int, str, str, list[manual_models.Manual], str]] = []
            for pattern, _alias, normalized in alias_patterns:
                targets = normalized_map.get(normalized, [])
                for match in pattern.finditer(text):
                    if any(match.start() < end and match.end() > start for start, end in matched_spans):
                        continue
                    if len(targets) == 1 and targets[0].id == manual.id:
                        continue
                    matched_spans.append((match.start(), match.end()))
                    occurrences.append((match.start(), match.end(), match.group(1), normalized, targets, "TEXT_ALIAS"))
            for match in CODE_CANDIDATE.finditer(text):
                if any(match.start() < end and match.end() > start for start, end in matched_spans):
                    continue
                normalized = normalize_code(match.group(1))
                targets = normalized_map.get(normalized, [])
                if len(targets) == 1 and targets[0].id == manual.id:
                    continue
                occurrences.append((match.start(), match.end(), match.group(1), normalized, targets, "CODE_CANDIDATE"))

            for start, end, raw_token, normalized, targets, detection_method in occurrences:
                occurrence_key = hashlib.sha256(f"{revision.id}:{block.id}:{page_number}:{start}:{end}:{normalized}".encode()).hexdigest()
                if occurrence_key in seen_occurrences:
                    continue
                seen_occurrences.add(occurrence_key)
                target_manual = targets[0] if len(targets) == 1 else None
                target_revision = _target_revision(db, target_manual) if target_manual else None
                if len(targets) > 1:
                    status, confidence = "AMBIGUOUS", 55
                elif target_manual and target_revision:
                    status, confidence = "AUTO_RESOLVED", 100 if detection_method == "TEXT_ALIAS" else 90
                elif target_manual:
                    status, confidence = "BROKEN", 80
                else:
                    status, confidence = "UNRESOLVED", 35
                row = existing.get(occurrence_key)
                if row and row.status == "OUTDATED" and row.verified_by_user_id:
                    status = "VERIFIED"
                if not row:
                    row = km.DocumentationReference(
                        tenant_id=tenant_id,
                        source_manual_id=manual.id,
                        source_revision_id=revision.id,
                        occurrence_key=occurrence_key,
                        source_quote=raw_token,
                        raw_token=raw_token,
                        normalized_token=normalized,
                    )
                    db.add(row)
                row.source_section_id = block.section_id
                row.source_block_id = block.id
                row.source_page_number = page_number
                row.source_char_start = start
                row.source_char_end = end
                row.source_bbox_json = _bbox_for_occurrence(pdf_document, page_number, raw_token)
                row.source_quote = raw_token
                row.source_context = _context(text, start, end)
                row.source_change_hash = block.change_hash
                row.raw_token = raw_token
                row.normalized_token = normalized
                row.relationship_type = _target_relationship(db, tenant_id, target_manual.id if target_manual else None)
                row.resolution_policy = "CURRENT_EFFECTIVE"
                row.target_manual_id = target_manual.id if target_manual else None
                row.target_revision_id = target_revision.id if target_revision else None
                row.status = status
                row.confidence_percent = confidence
                row.detection_method = detection_method
                row.candidates_json = [{"manual_id": candidate.id, "code": candidate.code, "title": candidate.title} for candidate in targets[:10]]
                row.last_checked_at = utcnow()
                detected += 1
                if status in {"AUTO_RESOLVED", "VERIFIED"}:
                    resolved += 1
                elif status == "BROKEN":
                    broken += 1
                else:
                    unresolved += 1
        if pdf_document:
            pdf_document.close()
        job.status = "COMPLETED"
        job.detected_count = detected
        job.resolved_count = resolved
        job.unresolved_count = unresolved
        job.broken_count = broken
        job.completed_at = utcnow()
        db.flush()
        return serialize_index_job(job)
    except Exception as exc:
        job.status = "FAILED"
        job.error_summary = str(exc)[:2000]
        job.completed_at = utcnow()
        db.flush()
        raise


def index_revision_background(revision_id: str) -> None:
    db = WriteSessionLocal()
    try:
        index_revision_references(db, revision_id=revision_id)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def serialize_index_job(row: km.DocumentationIndexJob | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "source_sha256": row.source_sha256,
        "index_version": row.index_version,
        "status": row.status,
        "detected_count": row.detected_count,
        "resolved_count": row.resolved_count,
        "unresolved_count": row.unresolved_count,
        "broken_count": row.broken_count,
        "error_summary": row.error_summary,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def readable_reference_payload(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    source_revision_id: str,
    user: account_models.User,
    page: int | None = None,
    section_id: str | None = None,
) -> dict:
    query = db.query(km.DocumentationReference).filter(
        km.DocumentationReference.tenant_id == manual_tenant.amo_id,
        km.DocumentationReference.source_revision_id == source_revision_id,
    )
    if page:
        query = query.filter(km.DocumentationReference.source_page_number == page)
    if section_id:
        query = query.filter(km.DocumentationReference.source_section_id == section_id)
    rows = query.order_by(km.DocumentationReference.source_page_number.asc(), km.DocumentationReference.source_char_start.asc()).all()
    target_ids = {row.target_manual_id for row in rows if row.target_manual_id}
    manuals = {row.id: row for row in db.query(manual_models.Manual).filter(manual_models.Manual.id.in_(target_ids or ["-"])).all()}
    profiles = {
        row.manual_id: row
        for row in db.query(km.DocumentationExecutionProfile).filter(km.DocumentationExecutionProfile.manual_id.in_(target_ids or ["-"])).all()
    }
    nodes = {
        row.manual_id: row
        for row in db.query(km.DocumentationNode).filter(km.DocumentationNode.manual_id.in_(target_ids or ["-"])).all()
    }
    items: list[dict] = []
    for row in rows:
        target = manuals.get(row.target_manual_id)
        control_profile = get_profile(db, manual_tenant, target.id) if target else None
        readable = bool(target and row.target_revision_id and can_read_manual(user, control_profile))
        execution = profiles.get(target.id) if readable and target else None
        node = nodes.get(target.id) if target else None
        items.append({
            "id": row.id,
            "raw_token": row.raw_token,
            "normalized_token": row.normalized_token,
            "relationship_type": row.relationship_type,
            "resolution_policy": row.resolution_policy,
            "status": row.status if readable or not target else "RESTRICTED",
            "confidence_percent": row.confidence_percent,
            "source": {
                "manual_id": row.source_manual_id,
                "revision_id": row.source_revision_id,
                "section_id": row.source_section_id,
                "block_id": row.source_block_id,
                "page_number": row.source_page_number,
                "char_start": row.source_char_start,
                "char_end": row.source_char_end,
                "bbox": dict(row.source_bbox_json or {}),
                "quote": row.source_quote,
                "context": row.source_context,
            },
            "target": {
                "manual_id": target.id,
                "revision_id": row.target_revision_id,
                "code": target.code,
                "title": target.title,
                "manual_type": target.manual_type,
                "node_type": node.node_type if node else None,
                "hierarchy_path": node.path if node else None,
                "reader_url": f"/maintenance/{manual_tenant.slug.upper()}/publications/{target.id}/rev/{row.target_revision_id}/read",
                "pdf_url": f"/manuals/t/{manual_tenant.slug}/{target.id}/rev/{row.target_revision_id}/stream.pdf",
                "execution": serialize_execution_profile(execution),
            } if readable and target else None,
            "candidates": list(row.candidates_json or []) if row.status in {"AMBIGUOUS", "UNRESOLVED", "BROKEN"} and getattr(user, "is_superuser", False) else [],
        })
    job = db.query(km.DocumentationIndexJob).filter(km.DocumentationIndexJob.revision_id == source_revision_id).first()
    return {"items": items, "index": serialize_index_job(job)}


def create_documentation_record(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    template: manual_models.Manual,
    revision: manual_models.ManualRevision,
    profile: km.DocumentationExecutionProfile,
    actor_id: str,
    filename: str,
    content: bytes,
    source_reference_id: str | None,
    payload: dict,
) -> km.DocumentationRecord:
    if not content or not content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="A completed PDF artifact is required")
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Completed record exceeds the 100 MB limit")
    if revision.status_enum != manual_models.ManualRevisionStatus.PUBLISHED or not revision.immutable_locked:
        raise HTTPException(status_code=409, detail="Records may only be created from an effective immutable template revision")
    reference = None
    if source_reference_id:
        reference = db.query(km.DocumentationReference).filter(
            km.DocumentationReference.id == source_reference_id,
            km.DocumentationReference.tenant_id == manual_tenant.amo_id,
            km.DocumentationReference.target_manual_id == template.id,
        ).first()
        if not reference:
            raise HTTPException(status_code=404, detail="The originating document reference is invalid")
    sequence = db.query(km.DocumentationRecord).filter(km.DocumentationRecord.tenant_id == manual_tenant.amo_id).count() + 1
    date_token = utcnow().strftime("%Y%m%d")
    record_number = f"{normalize_code(template.code) or 'REC'}-{date_token}-{sequence:06d}"
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or f"{record_number}.pdf")
    if not safe_filename.lower().endswith(".pdf"):
        safe_filename += ".pdf"
    target_dir = RECORD_ROOT / manual_tenant.slug / normalize_code(template.code).lower() / date_token
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{record_number}_{safe_filename}"
    path.write_bytes(content)
    row = km.DocumentationRecord(
        tenant_id=manual_tenant.amo_id,
        record_number=record_number,
        template_manual_id=template.id,
        template_revision_id=revision.id,
        source_reference_id=reference.id if reference else None,
        record_series_node_id=profile.record_series_node_id,
        source_context_json={
            "source_manual_id": reference.source_manual_id if reference else None,
            "source_revision_id": reference.source_revision_id if reference else None,
            "source_page_number": reference.source_page_number if reference else None,
            "source_quote": reference.source_quote if reference else None,
        },
        payload_json=dict(payload or {}),
        artifact_storage_path=str(path),
        artifact_filename=safe_filename,
        artifact_mime_type="application/pdf",
        artifact_sha256=hashlib.sha256(content).hexdigest(),
        status="PENDING_REVIEW" if profile.requires_review else "SUBMITTED",
        retention_years=profile.retention_years,
        submitted_by_user_id=actor_id,
        metadata_json={
            "template_code": template.code,
            "template_revision": revision.rev_number,
            "execution_type": profile.execution_type,
        },
    )
    db.add(row)
    db.flush()
    return row


def serialize_record(row: km.DocumentationRecord) -> dict:
    return {
        "id": row.id,
        "record_number": row.record_number,
        "template_manual_id": row.template_manual_id,
        "template_revision_id": row.template_revision_id,
        "source_reference_id": row.source_reference_id,
        "record_series_node_id": row.record_series_node_id,
        "artifact_filename": row.artifact_filename,
        "artifact_sha256": row.artifact_sha256,
        "status": row.status,
        "retention_years": row.retention_years,
        "submitted_by_user_id": row.submitted_by_user_id,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "download_url": f"/manuals/t/records/{row.id}/artifact.pdf",
    }
