"""Harden governed references, hierarchy, records, and reader tree access."""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from . import knowledge_indexer, knowledge_models, knowledge_service


knowledge_service.index_revision_references = knowledge_indexer.index_revision_references
knowledge_service.index_revision_background = knowledge_indexer.index_revision_background


# Preserve controller-verified reference resolutions during reindexing.
_original_write_occurrence = knowledge_indexer._write_occurrence


def _occurrence_key(*, source_revision, source_page_number, source_block_id, start, end, normalized) -> str:
    return hashlib.sha256(
        f"{source_revision.id}:{source_page_number or 0}:{source_block_id or '-'}:{start}:{end}:{normalized}".encode()
    ).hexdigest()


def _verified_resolution_snapshot(row) -> dict[str, Any] | None:
    if not row or not row.verified_by_user_id or row.status not in {"VERIFIED", "OUTDATED"}:
        return None
    return {
        "relationship_type": row.relationship_type,
        "resolution_policy": row.resolution_policy,
        "target_manual_id": row.target_manual_id,
        "target_revision_id": row.target_revision_id,
        "target_section_id": row.target_section_id,
        "verified_by_user_id": row.verified_by_user_id,
        "verified_at": row.verified_at,
    }


def _restore_verified_resolution(row, snapshot: dict[str, Any]) -> None:
    for field, value in snapshot.items():
        setattr(row, field, value)
    row.status = "VERIFIED"
    row.confidence_percent = 100


def _write_occurrence_preserving_verified(*args, **kwargs):
    existing = kwargs.get("existing") or {}
    key = _occurrence_key(
        source_revision=kwargs["source_revision"],
        source_page_number=kwargs.get("source_page_number"),
        source_block_id=kwargs.get("source_block_id"),
        start=kwargs["start"],
        end=kwargs["end"],
        normalized=kwargs["normalized"],
    )
    row = existing.get(key)
    snapshot = _verified_resolution_snapshot(row)
    status = _original_write_occurrence(*args, **kwargs)
    if snapshot and row:
        _restore_verified_resolution(row, snapshot)
        return "VERIFIED"
    return status


knowledge_indexer._write_occurrence = _write_occurrence_preserving_verified


# Preserve governed hierarchy placement and classification during reconciliation.
_original_ensure_node = knowledge_service._ensure_node


def _hierarchy_override_detected(row, *, code: str, title: str, node_type: str, parent, order_index: int) -> bool:
    expected_parent_id = parent.id if parent else None
    return any(
        (
            row.code != code.strip(),
            row.title != title.strip(),
            row.node_type != node_type,
            row.parent_id != expected_parent_id,
            int(row.order_index or 0) != int(order_index or 0),
        )
    )


def _ensure_node_preserving_governance(
    db,
    *,
    tenant_id: str,
    code: str,
    title: str,
    node_type: str,
    parent,
    manual_id: str | None = None,
    order_index: int = 0,
    metadata: dict | None = None,
    actor_id: str | None = None,
):
    normalized = knowledge_service.normalize_code(code)
    row = (
        db.query(knowledge_models.DocumentationNode)
        .filter(
            knowledge_models.DocumentationNode.tenant_id == tenant_id,
            knowledge_models.DocumentationNode.normalized_code == normalized,
        )
        .first()
    )
    if not row and manual_id:
        row = (
            db.query(knowledge_models.DocumentationNode)
            .filter(
                knowledge_models.DocumentationNode.tenant_id == tenant_id,
                knowledge_models.DocumentationNode.manual_id == manual_id,
            )
            .first()
        )

    if not row:
        created = _original_ensure_node(
            db,
            tenant_id=tenant_id,
            code=code,
            title=title,
            node_type=node_type,
            parent=parent,
            manual_id=manual_id,
            order_index=order_index,
            metadata=metadata,
            actor_id=actor_id,
        )
        created.metadata_json = {
            **dict(created.metadata_json or {}),
            "hierarchy_management": "SYSTEM" if (metadata or {}).get("system") else "AUTO",
        }
        return created

    current_metadata = dict(row.metadata_json or {})
    management = str(current_metadata.get("hierarchy_management") or "").upper()
    is_system = bool(current_metadata.get("system") or (metadata or {}).get("system"))
    if not is_system and management != "GOVERNED" and _hierarchy_override_detected(
        row,
        code=code,
        title=title,
        node_type=node_type,
        parent=parent,
        order_index=order_index,
    ):
        management = "GOVERNED"

    if management == "GOVERNED":
        if manual_id:
            row.manual_id = manual_id
        row.metadata_json = {
            **current_metadata,
            **dict(metadata or {}),
            "hierarchy_management": "GOVERNED",
        }
        return row

    reconciled = _original_ensure_node(
        db,
        tenant_id=tenant_id,
        code=code,
        title=title,
        node_type=node_type,
        parent=parent,
        manual_id=manual_id,
        order_index=order_index,
        metadata=metadata,
        actor_id=actor_id,
    )
    reconciled.metadata_json = {
        **dict(reconciled.metadata_json or {}),
        "hierarchy_management": "SYSTEM" if is_system else "AUTO",
    }
    return reconciled


knowledge_service._ensure_node = _ensure_node_preserving_governance


# Preserve one-time execution-profile discovery from the original runtime layer.
_original_ensure_execution_profile = knowledge_service._ensure_execution_profile


def _ensure_execution_profile_once(
    db,
    *,
    tenant_id: str,
    manual,
    node_type: str,
    record_series,
    actor_id: str | None,
):
    row = (
        db.query(knowledge_models.DocumentationExecutionProfile)
        .filter(
            knowledge_models.DocumentationExecutionProfile.tenant_id == tenant_id,
            knowledge_models.DocumentationExecutionProfile.manual_id == manual.id,
        )
        .first()
    )
    if row:
        if not row.record_series_node_id:
            row.record_series_node_id = record_series.id
        return row
    return _original_ensure_execution_profile(
        db,
        tenant_id=tenant_id,
        manual=manual,
        node_type=node_type,
        record_series=record_series,
        actor_id=actor_id,
    )


knowledge_service._ensure_execution_profile = _ensure_execution_profile_once


# Collision-resistant retained-record allocation and failure-safe artifact writes.
def _new_record_number(template_code: str, *, date_token: str | None = None) -> str:
    date_token = date_token or knowledge_service.utcnow().strftime("%Y%m%d")
    code = (knowledge_service.normalize_code(template_code) or "REC")[:96]
    return f"{code}-{date_token}-{uuid.uuid4().hex[:20].upper()}"


def _create_documentation_record_hardened(
    db,
    *,
    manual_tenant,
    template,
    revision,
    profile,
    actor_id: str,
    filename: str,
    content: bytes,
    source_reference_id: str | None,
    payload: dict,
):
    manual_models = knowledge_service.manual_models
    km = knowledge_models
    if not content or not content.startswith(b"%PDF"):
        raise knowledge_service.HTTPException(status_code=422, detail="A completed PDF artifact is required")
    if len(content) > 100 * 1024 * 1024:
        raise knowledge_service.HTTPException(status_code=413, detail="Completed record exceeds the 100 MB limit")
    if revision.status_enum != manual_models.ManualRevisionStatus.PUBLISHED or not revision.immutable_locked:
        raise knowledge_service.HTTPException(
            status_code=409,
            detail="Records may only be created from an effective immutable template revision",
        )

    reference = None
    if source_reference_id:
        reference = (
            db.query(km.DocumentationReference)
            .filter(
                km.DocumentationReference.id == source_reference_id,
                km.DocumentationReference.tenant_id == manual_tenant.amo_id,
                km.DocumentationReference.target_manual_id == template.id,
            )
            .first()
        )
        if not reference:
            raise knowledge_service.HTTPException(
                status_code=404,
                detail="The originating document reference is invalid",
            )

    date_token = knowledge_service.utcnow().strftime("%Y%m%d")
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "completed.pdf")
    if not safe_filename.lower().endswith(".pdf"):
        safe_filename += ".pdf"
    target_dir = (
        knowledge_service.RECORD_ROOT
        / manual_tenant.slug
        / knowledge_service.normalize_code(template.code).lower()
        / date_token
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    path: Path | None = None
    record_number = ""
    for _ in range(10):
        record_number = _new_record_number(template.code, date_token=date_token)
        candidate = target_dir / f"{record_number}_{safe_filename}"
        try:
            with candidate.open("xb") as artifact:
                artifact.write(content)
            path = candidate
            break
        except FileExistsError:
            continue
    if path is None:
        raise knowledge_service.HTTPException(
            status_code=409,
            detail="A unique retained-record artifact path could not be allocated",
        )

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
            "allocation": "UUID_V4_EXCLUSIVE_CREATE",
        },
    )
    db.add(row)
    try:
        db.flush()
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    return row


knowledge_service.create_documentation_record = _create_documentation_record_hardened


# Permission-filtered hierarchy serialization for ordinary publication readers.
_original_hierarchy_payload = knowledge_service.hierarchy_payload


def _filter_hierarchy_items(items: list[dict], readable_manual_ids: set[str]) -> list[dict]:
    hidden_ids: set[str] = set()
    for item in items:
        manual_id = item.get("manual_id")
        metadata = dict(item.get("metadata") or {})
        template_manual_id = metadata.get("template_manual_id")
        if manual_id and str(manual_id) not in readable_manual_ids:
            hidden_ids.add(str(item.get("id")))
        elif template_manual_id and str(template_manual_id) not in readable_manual_ids:
            hidden_ids.add(str(item.get("id")))

    changed = True
    while changed:
        changed = False
        for item in items:
            item_id = str(item.get("id"))
            parent_id = item.get("parent_id")
            if item_id not in hidden_ids and parent_id and str(parent_id) in hidden_ids:
                hidden_ids.add(item_id)
                changed = True

    return [item for item in items if str(item.get("id")) not in hidden_ids]


def _hierarchy_payload_access_filtered(
    db,
    *,
    manual_tenant,
    actor_id: str | None = None,
    user=None,
) -> dict:
    payload = _original_hierarchy_payload(
        db,
        manual_tenant=manual_tenant,
        actor_id=actor_id,
    )
    if user is None or knowledge_service.workspace_service.is_control_user(user):
        return payload

    manuals = (
        db.query(knowledge_service.manual_models.Manual)
        .filter(knowledge_service.manual_models.Manual.tenant_id == manual_tenant.id)
        .all()
    )
    profiles = {
        row.manual_id: row
        for row in db.query(knowledge_service.domain_models.DocumentControlProfile)
        .filter(knowledge_service.domain_models.DocumentControlProfile.tenant_id == manual_tenant.amo_id)
        .all()
    }
    readable_manual_ids = {
        str(manual.id)
        for manual in manuals
        if knowledge_service.can_read_manual(user, profiles.get(manual.id))
    }
    payload["items"] = _filter_hierarchy_items(
        list(payload.get("items") or []),
        readable_manual_ids,
    )
    visible_ids = {str(item.get("id")) for item in payload["items"]}
    if str(payload.get("root_id")) not in visible_ids:
        payload["root_id"] = next(
            (item.get("id") for item in payload["items"] if item.get("node_type") == "ROOT"),
            None,
        )
    payload["reference_health"] = {}
    return payload


from . import workspace_service as _workspace_service

knowledge_service.workspace_service = _workspace_service
knowledge_service.hierarchy_payload = _hierarchy_payload_access_filtered


__all__ = [
    "_create_documentation_record_hardened",
    "_filter_hierarchy_items",
    "_hierarchy_override_detected",
    "_new_record_number",
    "_restore_verified_resolution",
    "_verified_resolution_snapshot",
]
