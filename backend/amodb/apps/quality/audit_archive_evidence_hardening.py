from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import audit_archive_governance_router as governance
from . import audit_archive_package_router as package
from .audit_evidence_models import QualityAuditEvidenceArtifact
from .audit_evidence_storage import resolve_audit_evidence


_original_build_inventory = governance._build_inventory
_original_render_package = package._render_package


def build_inventory_with_evidence(db: Session, *, amo_id: str, audit) -> list[dict[str, Any]]:
    """Extend the authoritative archive inventory with governed evidence files."""

    items = list(_original_build_inventory(db, amo_id=amo_id, audit=audit))
    evidence_rows = db.query(QualityAuditEvidenceArtifact).filter(
        QualityAuditEvidenceArtifact.amo_id == amo_id,
        QualityAuditEvidenceArtifact.audit_id == audit.id,
    ).order_by(QualityAuditEvidenceArtifact.created_at.asc(), QualityAuditEvidenceArtifact.id.asc()).all()

    for artifact in evidence_rows:
        items.append(governance._record_item(
            item_type="EVIDENCE_ARTIFACT",
            record_id=artifact.id,
            source_system="QUALITY_AUDIT_EVIDENCE",
            retention_role="OBJECTIVE_AUDIT_EVIDENCE",
            content_hash=artifact.sha256,
            metadata={
                "filename": artifact.filename,
                "content_type": artifact.content_type,
                "size_bytes": int(artifact.size_bytes),
                "checklist_item_id": str(artifact.checklist_item_id) if artifact.checklist_item_id else None,
                "finding_id": str(artifact.finding_id) if artifact.finding_id else None,
                "source_type": artifact.source_type,
                "description": artifact.description,
                "created_at": artifact.created_at,
                # Private controlled-storage reference retained inside the archive
                # manifest so the inventory remains independently traceable even
                # before package extraction. The archive also contains the bytes.
                "storage_ref": artifact.file_ref,
            },
        ))
    return items


def _evidence_member(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    filename = package._safe_name(str(metadata.get("filename") or "evidence"))
    record_id = package._safe_name(str(item.get("authoritative_record_id") or "artifact"))
    return f"evidence/files/{record_id}/{filename}"


def render_package_with_evidence(
    path: Path,
    *,
    manifest_payload: dict[str, Any],
    manifest_sha256: str,
    inventory: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> tuple[int, str]:
    """Write the normal package, then append verified governed evidence bytes.

    Every evidence member is checked against the database-governed size/SHA before
    it is copied. A missing or altered file fails archive generation closed; the
    caller's existing transaction cleanup removes the incomplete ZIP.
    """

    _original_render_package(
        path,
        manifest_payload=manifest_payload,
        manifest_sha256=manifest_sha256,
        inventory=inventory,
        timeline=timeline,
    )

    evidence_items = sorted(
        [item for item in inventory if item.get("item_type") == "EVIDENCE_ARTIFACT"],
        key=lambda item: str(item.get("authoritative_record_id") or ""),
    )
    if not evidence_items:
        return path.stat().st_size, package._sha256(path)

    prepared: list[tuple[dict[str, Any], Path, str]] = []
    index_items: list[dict[str, Any]] = []
    for item in evidence_items:
        metadata = dict(item.get("metadata") or {})
        storage_ref = str(metadata.get("storage_ref") or "").strip()
        if not storage_ref:
            raise HTTPException(status_code=409, detail="Governed audit evidence is missing its controlled storage reference.")
        evidence_path = resolve_audit_evidence(storage_ref)
        expected_size = int(metadata.get("size_bytes") or 0)
        actual_size = evidence_path.stat().st_size
        if actual_size != expected_size:
            raise HTTPException(
                status_code=409,
                detail=f"Governed audit evidence {item.get('authoritative_record_id')} no longer matches its recorded size.",
            )
        expected_sha = str(item.get("content_hash") or "").lower()
        actual_sha = package._sha256(evidence_path).lower()
        if not expected_sha or actual_sha != expected_sha:
            raise HTTPException(
                status_code=409,
                detail=f"Governed audit evidence {item.get('authoritative_record_id')} failed SHA-256 verification.",
            )
        member = _evidence_member(item)
        prepared.append((item, evidence_path, member))
        index_item = dict(item)
        index_metadata = dict(metadata)
        index_metadata["archive_member"] = member
        index_item["metadata"] = index_metadata
        index_items.append(index_item)

    with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        package._zip_json(
            archive,
            "evidence/index.json",
            {"items": index_items, "item_count": len(index_items)},
        )
        for _item, evidence_path, member in prepared:
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            with evidence_path.open("rb") as source, archive.open(info, "w", force_zip64=True) as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)

    return path.stat().st_size, package._sha256(path)


# Package generation imported _build_inventory by value, so patch both modules.
# Endpoint functions resolve _render_package from their module globals at call
# time, allowing this additive hardening without another archive state machine.
governance._build_inventory = build_inventory_with_evidence
package._build_inventory = build_inventory_with_evidence
package._render_package = render_package_with_evidence
