from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.manuals import models as manual_models
from amodb.database import WriteSessionLocal

from . import knowledge_models as km
from .knowledge_service import (
    CODE_CANDIDATE,
    INDEX_VERSION,
    _aliases_by_manual,
    _context,
    _target_relationship,
    _target_revision,
    normalize_code,
    reconcile_documentation_hierarchy,
    serialize_index_job,
    utcnow,
)


def _source_type(revision: manual_models.ManualRevision) -> str:
    return str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()


def _reference_occurrences(
    text: str,
    *,
    alias_patterns,
    normalized_map,
    source_manual_id: str,
) -> list[tuple[int, int, str, str, list[manual_models.Manual], str]]:
    matched_spans: list[tuple[int, int]] = []
    occurrences: list[tuple[int, int, str, str, list[manual_models.Manual], str]] = []
    for pattern, _alias, normalized in alias_patterns:
        targets = normalized_map.get(normalized, [])
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in matched_spans):
                continue
            if len(targets) == 1 and targets[0].id == source_manual_id:
                continue
            matched_spans.append((match.start(), match.end()))
            occurrences.append((match.start(), match.end(), match.group(1), normalized, targets, "TEXT_ALIAS"))
    for match in CODE_CANDIDATE.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in matched_spans):
            continue
        normalized = normalize_code(match.group(1))
        targets = normalized_map.get(normalized, [])
        if len(targets) == 1 and targets[0].id == source_manual_id:
            continue
        matched_spans.append((match.start(), match.end()))
        occurrences.append((match.start(), match.end(), match.group(1), normalized, targets, "CODE_CANDIDATE"))
    return occurrences


def _page_sections(sections: Iterable[manual_models.ManualSection]) -> dict[int, manual_models.ManualSection]:
    result: dict[int, manual_models.ManualSection] = {}
    for section in sections:
        metadata = dict(section.metadata_json or {})
        start = int(metadata.get("page_start") or 0)
        end = int(metadata.get("page_end") or start or 0)
        if start <= 0:
            continue
        for page_number in range(start, max(start, end) + 1):
            result.setdefault(page_number, section)
    return result


def _page_bbox(page, raw_token: str) -> dict:
    try:
        rects = page.search_for(raw_token, quads=False)
        if not rects:
            compact = " ".join(raw_token.split())
            rects = page.search_for(compact, quads=False) if compact != raw_token else []
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


def _status_for(targets: list[manual_models.Manual], target_revision) -> tuple[str, int]:
    if len(targets) > 1:
        return "AMBIGUOUS", 55
    if targets and target_revision:
        return "AUTO_RESOLVED", 100
    if targets:
        return "BROKEN", 80
    return "UNRESOLVED", 35


def _write_occurrence(
    db: Session,
    *,
    existing: dict[str, km.DocumentationReference],
    seen: set[str],
    tenant_id: str,
    source_manual: manual_models.Manual,
    source_revision: manual_models.ManualRevision,
    source_section_id: str | None,
    source_block_id: str | None,
    source_page_number: int | None,
    source_change_hash: str | None,
    source_text: str,
    start: int,
    end: int,
    raw_token: str,
    normalized: str,
    targets: list[manual_models.Manual],
    detection_method: str,
    bbox: dict,
) -> str | None:
    occurrence_key = hashlib.sha256(
        f"{source_revision.id}:{source_page_number or 0}:{source_block_id or '-'}:{start}:{end}:{normalized}".encode()
    ).hexdigest()
    if occurrence_key in seen:
        return None
    seen.add(occurrence_key)
    target_manual = targets[0] if len(targets) == 1 else None
    target_revision = _target_revision(db, target_manual) if target_manual else None
    status, confidence = _status_for(targets, target_revision)
    if detection_method == "CODE_CANDIDATE" and status == "AUTO_RESOLVED":
        confidence = 90
    row = existing.get(occurrence_key)
    if row and row.status == "OUTDATED" and row.verified_by_user_id:
        status = "VERIFIED"
        confidence = 100
    if not row:
        row = km.DocumentationReference(
            tenant_id=tenant_id,
            source_manual_id=source_manual.id,
            source_revision_id=source_revision.id,
            occurrence_key=occurrence_key,
            source_quote=raw_token,
            raw_token=raw_token,
            normalized_token=normalized,
        )
        db.add(row)
    row.source_section_id = source_section_id
    row.source_block_id = source_block_id
    row.source_page_number = source_page_number
    row.source_char_start = start
    row.source_char_end = end
    row.source_bbox_json = bbox
    row.source_quote = raw_token
    row.source_context = _context(source_text, start, end)
    row.source_change_hash = source_change_hash
    row.raw_token = raw_token
    row.normalized_token = normalized
    row.relationship_type = _target_relationship(db, tenant_id, target_manual.id if target_manual else None)
    row.resolution_policy = row.resolution_policy if row.status == "OUTDATED" and row.verified_by_user_id else "CURRENT_EFFECTIVE"
    row.target_manual_id = target_manual.id if target_manual else row.target_manual_id if row.verified_by_user_id else None
    row.target_revision_id = target_revision.id if target_revision else row.target_revision_id if row.verified_by_user_id else None
    row.status = status
    row.confidence_percent = confidence
    row.detection_method = detection_method
    row.candidates_json = [
        {"manual_id": candidate.id, "code": candidate.code, "title": candidate.title}
        for candidate in targets[:10]
    ]
    row.last_checked_at = utcnow()
    return status


def _index_pdf(
    db: Session,
    *,
    source_manual: manual_models.Manual,
    source_revision: manual_models.ManualRevision,
    tenant_id: str,
    sections: list[manual_models.ManualSection],
    alias_patterns,
    normalized_map,
    existing: dict[str, km.DocumentationReference],
    seen: set[str],
) -> tuple[dict[str, int], bool]:
    path_value = str(source_revision.source_storage_path or "")
    path = Path(path_value).resolve() if path_value else None
    if not path or not path.exists() or path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=409, detail="The PDF source is unavailable for reference indexing")
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for exact PDF reference indexing") from exc
    counts = {"detected": 0, "resolved": 0, "unresolved": 0, "broken": 0}
    searchable_text = False
    page_section = _page_sections(sections)
    with fitz.open(path) as document:
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            text = str(page.get_text("text") or "")
            if not text.strip():
                continue
            searchable_text = True
            section = page_section.get(page_number)
            for start, end, raw_token, normalized, targets, method in _reference_occurrences(
                text,
                alias_patterns=alias_patterns,
                normalized_map=normalized_map,
                source_manual_id=source_manual.id,
            ):
                status = _write_occurrence(
                    db,
                    existing=existing,
                    seen=seen,
                    tenant_id=tenant_id,
                    source_manual=source_manual,
                    source_revision=source_revision,
                    source_section_id=section.id if section else None,
                    source_block_id=None,
                    source_page_number=page_number,
                    source_change_hash=source_revision.source_sha256,
                    source_text=text,
                    start=start,
                    end=end,
                    raw_token=raw_token,
                    normalized=normalized,
                    targets=targets,
                    detection_method=method,
                    bbox=_page_bbox(page, raw_token),
                )
                if not status:
                    continue
                counts["detected"] += 1
                if status in {"AUTO_RESOLVED", "VERIFIED"}:
                    counts["resolved"] += 1
                elif status == "BROKEN":
                    counts["broken"] += 1
                else:
                    counts["unresolved"] += 1
    return counts, searchable_text


def _index_structured_blocks(
    db: Session,
    *,
    source_manual: manual_models.Manual,
    source_revision: manual_models.ManualRevision,
    tenant_id: str,
    sections: list[manual_models.ManualSection],
    alias_patterns,
    normalized_map,
    existing: dict[str, km.DocumentationReference],
    seen: set[str],
) -> dict[str, int]:
    section_map = {section.id: section for section in sections}
    blocks = (
        db.query(manual_models.ManualBlock)
        .filter(manual_models.ManualBlock.section_id.in_(list(section_map) or ["-"]))
        .order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc())
        .all()
    )
    counts = {"detected": 0, "resolved": 0, "unresolved": 0, "broken": 0}
    for block in blocks:
        text = str(block.text_plain or "")
        if not text:
            continue
        section = section_map.get(block.section_id)
        page_number = int((section.metadata_json or {}).get("page_start") or 0) or None if section else None
        for start, end, raw_token, normalized, targets, method in _reference_occurrences(
            text,
            alias_patterns=alias_patterns,
            normalized_map=normalized_map,
            source_manual_id=source_manual.id,
        ):
            status = _write_occurrence(
                db,
                existing=existing,
                seen=seen,
                tenant_id=tenant_id,
                source_manual=source_manual,
                source_revision=source_revision,
                source_section_id=block.section_id,
                source_block_id=block.id,
                source_page_number=page_number,
                source_change_hash=block.change_hash,
                source_text=text,
                start=start,
                end=end,
                raw_token=raw_token,
                normalized=normalized,
                targets=targets,
                detection_method=method,
                bbox={},
            )
            if not status:
                continue
            counts["detected"] += 1
            if status in {"AUTO_RESOLVED", "VERIFIED"}:
                counts["resolved"] += 1
            elif status == "BROKEN":
                counts["broken"] += 1
            else:
                counts["unresolved"] += 1
    return counts


def index_revision_references(db: Session, *, revision_id: str) -> dict:
    revision = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.id == revision_id).first()
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found for reference indexing")
    manual = db.query(manual_models.Manual).filter(manual_models.Manual.id == revision.manual_id).first()
    manual_tenant = (
        db.query(manual_models.Tenant).filter(manual_models.Tenant.id == manual.tenant_id).first()
        if manual
        else None
    )
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
        existing = {
            row.occurrence_key: row
            for row in db.query(km.DocumentationReference)
            .filter(km.DocumentationReference.source_revision_id == revision.id)
            .all()
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
        seen: set[str] = set()
        warning = None
        if _source_type(revision) == "PDF":
            counts, searchable_text = _index_pdf(
                db,
                source_manual=manual,
                source_revision=revision,
                tenant_id=tenant_id,
                sections=sections,
                alias_patterns=alias_patterns,
                normalized_map=normalized_map,
                existing=existing,
                seen=seen,
            )
            if not searchable_text:
                warning = "The PDF contains no searchable text. Controlled OCR indexing is required before textual references can be detected."
        else:
            counts = _index_structured_blocks(
                db,
                source_manual=manual,
                source_revision=revision,
                tenant_id=tenant_id,
                sections=sections,
                alias_patterns=alias_patterns,
                normalized_map=normalized_map,
                existing=existing,
                seen=seen,
            )
        for row in existing.values():
            if row.status == "OUTDATED" and row.occurrence_key not in seen:
                counts["unresolved"] += 1
        job.status = "COMPLETED_WITH_WARNINGS" if warning else "COMPLETED"
        job.detected_count = counts["detected"]
        job.resolved_count = counts["resolved"]
        job.unresolved_count = counts["unresolved"]
        job.broken_count = counts["broken"]
        job.error_summary = warning
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
        claim = (
            db.query(km.DocumentationIndexJob)
            .filter(
                km.DocumentationIndexJob.revision_id == revision_id,
                km.DocumentationIndexJob.status == "PENDING",
            )
            .with_for_update(skip_locked=True)
            .first()
        )
        if claim is None:
            return
        claim.status = "RUNNING"
        claim.started_at = utcnow()
        claim.completed_at = None
        claim.error_summary = None
        # Keep the claim lock and all index mutations in one transaction. If the
        # process exits, PostgreSQL restores PENDING automatically; another
        # worker can then claim the revision without overlapping a live indexer.
        db.flush()
        index_revision_references(db, revision_id=revision_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            job = db.query(km.DocumentationIndexJob).filter(km.DocumentationIndexJob.revision_id == revision_id).first()
            if job:
                job.status = "FAILED"
                job.error_summary = str(exc)[:2000]
                job.completed_at = utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
