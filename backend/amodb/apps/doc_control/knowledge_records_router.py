from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import knowledge_models as km
from .knowledge_service import serialize_record
from .workspace_decision_policy import is_decision_approver, require_decision_approver
from .workspace_service import require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Generated Records"])


class RecordReviewDecision(BaseModel):
    decision: Literal["ACCEPT", "RETURN"]
    comments: str = Field(min_length=3, max_length=4000)
    evidence_references: list[str] = Field(default_factory=list, max_length=50)


def _audit(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
    request: Request,
    action: str,
    record: km.DocumentationRecord,
    diff: dict,
) -> None:
    db.add(
        manual_models.ManualAuditLog(
            tenant_id=tenant.id,
            actor_id=user.id,
            action=action,
            entity_type="documentation_record",
            entity_id=record.id,
            ip_device=(
                f"{request.client.host if request.client else 'unknown'}::"
                f"{request.headers.get('user-agent', 'n/a')}"
            ),
            diff_json=diff,
        )
    )


def _integrity(row: km.DocumentationRecord) -> dict:
    path = Path(row.artifact_storage_path).resolve()
    if not path.exists() or not path.is_file():
        return {"status": "MISSING", "expected_sha256": row.artifact_sha256, "actual_sha256": None}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "status": "VERIFIED" if digest == row.artifact_sha256 else "MISMATCH",
        "expected_sha256": row.artifact_sha256,
        "actual_sha256": digest,
        "size_bytes": path.stat().st_size,
    }


def _record_payload(
    row: km.DocumentationRecord,
    *,
    tenant_slug: str,
    templates: dict[str, manual_models.Manual],
    revisions: dict[str, manual_models.ManualRevision],
    series: dict[str, km.DocumentationNode],
    include_integrity: bool = False,
) -> dict:
    payload = serialize_record(row)
    payload["download_url"] = f"/manuals/t/{tenant_slug}/records/{row.id}/artifact.pdf"
    template = templates.get(row.template_manual_id)
    revision = revisions.get(row.template_revision_id)
    record_series = series.get(row.record_series_node_id)
    payload.update(
        {
            "template": {
                "code": template.code,
                "title": template.title,
                "manual_type": template.manual_type,
            }
            if template
            else None,
            "template_revision": {
                "issue_number": revision.issue_number,
                "revision_number": revision.rev_number,
                "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
            }
            if revision
            else None,
            "record_series": {
                "id": record_series.id,
                "code": record_series.code,
                "title": record_series.title,
                "path": record_series.path,
            }
            if record_series
            else None,
            "source_context": dict(row.source_context_json or {}),
            "metadata": dict(row.metadata_json or {}),
            "reviewed_by_user_id": row.reviewed_by_user_id,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        }
    )
    if include_integrity:
        payload["integrity"] = _integrity(row)
    return payload


@router.get("/t/{tenant_slug}/knowledge/records")
def list_generated_records(
    tenant_slug: str,
    series_id: str | None = None,
    template_manual_id: str | None = None,
    status: str | None = None,
    submitted_by_user_id: str | None = None,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(km.DocumentationRecord).filter(km.DocumentationRecord.tenant_id == tenant.amo_id)
    if series_id:
        query = query.filter(km.DocumentationRecord.record_series_node_id == series_id)
    if template_manual_id:
        query = query.filter(km.DocumentationRecord.template_manual_id == template_manual_id)
    if status:
        query = query.filter(km.DocumentationRecord.status == status.upper())
    if submitted_by_user_id:
        query = query.filter(km.DocumentationRecord.submitted_by_user_id == submitted_by_user_id)
    total = query.count()
    size = max(1, min(250, per_page))
    current_page = max(1, page)
    rows = (
        query.order_by(km.DocumentationRecord.submitted_at.desc(), km.DocumentationRecord.id.desc())
        .offset((current_page - 1) * size)
        .limit(size)
        .all()
    )
    template_ids = {row.template_manual_id for row in rows}
    revision_ids = {row.template_revision_id for row in rows}
    series_ids = {row.record_series_node_id for row in rows if row.record_series_node_id}
    templates = {
        row.id: row
        for row in db.query(manual_models.Manual)
        .filter(manual_models.Manual.id.in_(template_ids or ["-"]), manual_models.Manual.tenant_id == tenant.id)
        .all()
    }
    revisions = {
        row.id: row
        for row in db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.id.in_(revision_ids or ["-"]))
        .all()
    }
    series = {
        row.id: row
        for row in db.query(km.DocumentationNode)
        .filter(km.DocumentationNode.id.in_(series_ids or ["-"]), km.DocumentationNode.tenant_id == tenant.amo_id)
        .all()
    }
    return {
        "items": [
            _record_payload(
                row,
                tenant_slug=tenant.slug,
                templates=templates,
                revisions=revisions,
                series=series,
            )
            for row in rows
        ],
        "pagination": {
            "page": current_page,
            "per_page": size,
            "total": total,
            "returned": len(rows),
        },
        "capabilities": {
            "review": is_decision_approver(current_user),
            "control": True,
        },
    }


@router.get("/t/{tenant_slug}/knowledge/records/{record_id}")
def generated_record_detail(
    tenant_slug: str,
    record_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(km.DocumentationRecord)
        .filter(km.DocumentationRecord.id == record_id, km.DocumentationRecord.tenant_id == tenant.amo_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Generated record not found")
    template = db.query(manual_models.Manual).filter(manual_models.Manual.id == row.template_manual_id).first()
    revision = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.id == row.template_revision_id).first()
    record_series = (
        db.query(km.DocumentationNode).filter(km.DocumentationNode.id == row.record_series_node_id).first()
        if row.record_series_node_id
        else None
    )
    return {
        **_record_payload(
            row,
            tenant_slug=tenant.slug,
            templates={template.id: template} if template else {},
            revisions={revision.id: revision} if revision else {},
            series={record_series.id: record_series} if record_series else {},
            include_integrity=True,
        ),
        "capabilities": {
            "review": is_decision_approver(current_user),
            "control": True,
        },
    }


@router.post("/t/{tenant_slug}/knowledge/records/{record_id}/review")
def review_generated_record(
    tenant_slug: str,
    record_id: str,
    payload: RecordReviewDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(km.DocumentationRecord)
        .filter(km.DocumentationRecord.id == record_id, km.DocumentationRecord.tenant_id == tenant.amo_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Generated record not found")
    if row.status not in {"PENDING_REVIEW", "SUBMITTED", "RETURNED"}:
        raise HTTPException(status_code=409, detail="This generated record has already reached a terminal review state")
    integrity = _integrity(row)
    if integrity["status"] != "VERIFIED":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GENERATED_RECORD_INTEGRITY_FAILED",
                "message": "The retained PDF does not match its recorded checksum and cannot be reviewed.",
                "integrity": integrity,
            },
        )
    before = row.status
    row.status = "ACCEPTED" if payload.decision == "ACCEPT" else "RETURNED"
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = datetime.utcnow()
    history = list((row.metadata_json or {}).get("review_history", []))
    history.append(
        {
            "decision": payload.decision,
            "comments": payload.comments.strip(),
            "evidence_references": [value.strip() for value in payload.evidence_references if value.strip()],
            "reviewed_by_user_id": current_user.id,
            "reviewed_at": row.reviewed_at.isoformat(),
            "from_status": before,
            "to_status": row.status,
        }
    )
    row.metadata_json = {**dict(row.metadata_json or {}), "review_history": history}
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        action="documentation.record.reviewed",
        record=row,
        diff={
            "from_status": before,
            "to_status": row.status,
            "decision": payload.decision,
            "comments": payload.comments.strip(),
            "evidence_references": payload.evidence_references,
            "artifact_sha256": row.artifact_sha256,
        },
    )
    db.commit()
    return {
        "id": row.id,
        "record_number": row.record_number,
        "status": row.status,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "integrity": integrity,
    }
