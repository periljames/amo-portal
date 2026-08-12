from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from amodb.apps.manuals import models as manual_models

from . import domain_models as dm
from . import retention_models as retention_models
from . import workspace_evidence_pack_router as pack


_installed = False
_original_datasets = pack._datasets
EVIDENCE_ROOT = Path(os.getenv("DOCUMENT_EVIDENCE_DIR", "uploads/document-control-evidence")).resolve()
MANUAL_ROOT = Path(os.getenv("MANUAL_UPLOAD_DIR", "uploads/manuals")).resolve()


def _known_lifecycle_entity_ids(db: Session, *, amo_id: str, manual_id: str) -> set[str]:
    ids: set[str] = {manual_id}
    models = (
        dm.DocumentChangeRequest,
        dm.DocumentWorkflowInstance,
        dm.DocumentAuthoritySubmission,
        dm.DocumentTemporaryRevision,
        dm.DocumentDistributionCampaign,
        dm.DocumentControlledCopy,
        dm.DocumentReviewPlan,
        dm.ExternalDocumentSource,
        dm.DocumentApplicabilityRule,
        dm.DocumentIntegrationLink,
        retention_models.DocumentRetentionDisposition,
    )
    for model in models:
        if not hasattr(model, "manual_id"):
            continue
        rows = (
            db.query(model.id)
            .filter(model.tenant_id == amo_id, model.manual_id == manual_id)
            .limit(pack.MAX_PACK_ROWS_PER_DATASET + 1)
            .all()
        )
        if len(rows) > pack.MAX_PACK_ROWS_PER_DATASET:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "EVIDENCE_PACK_DATASET_TOO_LARGE",
                    "message": f"Evidence pack lifecycle index for {model.__tablename__} exceeds the synchronous row ceiling.",
                    "dataset": model.__tablename__,
                    "rows": len(rows),
                    "limit": pack.MAX_PACK_ROWS_PER_DATASET,
                },
            )
        ids.update(str(row[0]) for row in rows if row[0])
    return ids


def _manual_audit_rows(db: Session, *, tenant_id: str, manual_id: str) -> list[manual_models.ManualAuditLog]:
    tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.id == tenant_id).first()
    if not tenant:
        return []
    entity_ids = _known_lifecycle_entity_ids(db, amo_id=tenant.amo_id, manual_id=manual_id)
    rows = (
        db.query(manual_models.ManualAuditLog)
        .filter(
            manual_models.ManualAuditLog.tenant_id == tenant_id,
            or_(
                manual_models.ManualAuditLog.entity_id.in_(entity_ids),
                cast(manual_models.ManualAuditLog.diff_json, String).like(f"%{manual_id}%"),
            ),
        )
        .order_by(manual_models.ManualAuditLog.at.asc(), manual_models.ManualAuditLog.id.asc())
        .limit(pack.MAX_PACK_ROWS_PER_DATASET + 1)
        .all()
    )
    return pack._bounded(rows, dataset="audit_history")


def _inside_controlled_root(path: Path) -> bool:
    return any(path == root or root in path.parents for root in (EVIDENCE_ROOT, MANUAL_ROOT))


def _read_verified_file(path_value: str, expected_sha256: str, *, label: str) -> bytes:
    path = Path(path_value).resolve()
    if not _inside_controlled_root(path):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVIDENCE_PACK_STORAGE_BOUNDARY_VIOLATION",
                "message": f"Retained file is outside configured Document Control storage: {label}",
            },
        )
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=409,
            detail={"code": "EVIDENCE_PACK_FILE_MISSING", "message": f"Retained file is unavailable: {label}"},
        )
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if not expected_sha256 or actual.lower() != expected_sha256.lower():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVIDENCE_PACK_CHECKSUM_MISMATCH",
                "message": f"Retained file checksum does not match the controlled record: {label}",
                "expected_sha256": expected_sha256,
                "actual_sha256": actual,
            },
        )
    return content


def _datasets(db: Session, *, tenant_id: str, manual_id: str, revision_id: str | None):
    result = _original_datasets(
        db,
        tenant_id=tenant_id,
        manual_id=manual_id,
        revision_id=revision_id,
    )
    tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.id == tenant_id).first()
    if not tenant:
        result["retention_dispositions"] = []
        return result
    query = db.query(retention_models.DocumentRetentionDisposition).filter(
        retention_models.DocumentRetentionDisposition.tenant_id == tenant.amo_id,
        retention_models.DocumentRetentionDisposition.manual_id == manual_id,
    )
    if revision_id:
        query = query.filter(
            (retention_models.DocumentRetentionDisposition.revision_id == revision_id)
            | (retention_models.DocumentRetentionDisposition.revision_id.is_(None))
        )
    result["retention_dispositions"] = pack._bounded(
        query.order_by(
            retention_models.DocumentRetentionDisposition.created_at.asc(),
            retention_models.DocumentRetentionDisposition.id.asc(),
        ).all(),
        dataset="retention_dispositions",
    )
    return result


def install() -> None:
    global _installed
    if _installed:
        return
    pack._manual_audit_rows = _manual_audit_rows
    pack._read_verified_file = _read_verified_file
    pack._datasets = _datasets
    _installed = True
