"""Focused public CAR invitation extensions.

This module is imported after the main Quality compatibility router has finished
loading. It replaces the original token-read route so existing public invite
URLs gain an audit-report link while retaining the same CAR payload and state
machine. It also replaces the token PATCH adapter so the expanded CAR narrative
contract is preserved without changing the established submission workflow.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_db

from . import models
from .audit_report_governance_models import QualityAuditReportRevision
from .router import (
    AUDIT_REPORT_DIR,
    _car_invite_payload,
    _limit_car_invite_text,
    _require_public_car_invite_editable,
    public_router,
    submit_car_from_invite as _submit_car_from_invite_base,
)
from .schemas import CARInviteOut, CARInviteUpdate, CAROut


class CARInviteWithAuditReportOut(CARInviteOut):
    """Public invite response with a token-scoped report download route."""

    audit_report_download_url: Optional[str] = Field(default=None, max_length=1024)


_extension_router = APIRouter(prefix="/quality", tags=["Quality / Public CAR"])
_DETAILED_RESPONSE_FIELDS = (
    "containment_action",
    "root_cause",
    "corrective_action",
    "preventive_action",
)
_DETAILED_RESPONSE_MAX_LENGTH = 8000


def _car_for_token(db: Session, invite_token: str) -> models.CorrectiveActionRequest:
    clean_token = (invite_token or "").strip()
    if not clean_token or len(clean_token) > 255:
        raise HTTPException(status_code=404, detail="CAR invitation not found")
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == clean_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="CAR invitation not found")
    return car


def _audit_for_car(car: models.CorrectiveActionRequest) -> Optional[models.QMSAudit]:
    finding = getattr(car, "finding", None)
    return getattr(finding, "audit", None) if finding is not None else None


def _safe_report_filename(audit: models.QMSAudit, file_path: Path) -> str:
    audit_ref = re.sub(r"[^A-Za-z0-9._-]+", "-", str(audit.audit_ref or "audit")).strip("-._") or "audit"
    suffix = file_path.suffix.lower() or ".pdf"
    return f"{audit_ref}_issued-audit-report{suffix}"


def _controlled_report_path(value: object) -> Optional[Path]:
    if not value:
        return None
    report_root = AUDIT_REPORT_DIR.resolve()
    candidate = Path(str(value)).resolve()
    try:
        candidate.relative_to(report_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _issued_revision_matches_path(revision: object, file_path: Path) -> bool:
    if str(getattr(revision, "status", "") or "").upper() != "ISSUED":
        return False
    file_ref = getattr(revision, "file_ref", None)
    if not file_ref:
        return False
    try:
        return Path(str(file_ref)).resolve() == file_path.resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _set_public_tenant_context(db: Session, *, amo_id: str) -> None:
    """Set the token-resolved tenant for forced-RLS public Quality reads."""

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT set_config('app.tenant_id', :amo_id, true)"),
        {"amo_id": str(amo_id)},
    )


def _issued_report_path(db: Session, audit: models.QMSAudit | None) -> Optional[Path]:
    """Return the compatibility report only when it is a governed ISSUED revision.

    ``QMSAudit.report_file_ref`` can point at a newly uploaded first revision before
    that revision has passed internal review, approval and issue. Public CAR invite
    holders must never see that draft projection. A prior issued report remains
    eligible while a later revision is being governed because the audit compatibility
    pointer is deliberately restored to that prior issued file.
    """

    if audit is None:
        return None
    candidate = _controlled_report_path(getattr(audit, "report_file_ref", None))
    if candidate is None:
        return None

    _set_public_tenant_context(db, amo_id=str(audit.amo_id))
    revisions = (
        db.query(QualityAuditReportRevision)
        .filter(
            QualityAuditReportRevision.amo_id == audit.amo_id,
            QualityAuditReportRevision.audit_id == audit.id,
            QualityAuditReportRevision.status == "ISSUED",
        )
        .order_by(QualityAuditReportRevision.revision_no.desc())
        .limit(20)
        .all()
    )
    return candidate if any(_issued_revision_matches_path(row, candidate) for row in revisions) else None


def _persist_detailed_response_fields(car: models.CorrectiveActionRequest, payload: CARInviteUpdate) -> None:
    """Apply the schema-supported 8k narrative fields before base submission.

    The compatibility submit handler historically defaults text trimming to 500
    characters because legacy evidence/reference fields remain capped there.
    These four governed response narratives now have an 8,000-character schema
    contract, so the active public PATCH adapter persists them explicitly at that
    limit and delegates every other validation, response, audit and notification
    side effect to the established handler.
    """

    for field in _DETAILED_RESPONSE_FIELDS:
        value = getattr(payload, field)
        if value is not None:
            setattr(
                car,
                field,
                _limit_car_invite_text(value, max_length=_DETAILED_RESPONSE_MAX_LENGTH),
            )


@_extension_router.get("/cars/invite/{invite_token}", response_model=CARInviteWithAuditReportOut)
def get_car_invite_with_report(
    invite_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    car = _car_for_token(db, invite_token)
    payload = _car_invite_payload(car, request=request, db=db)
    audit = _audit_for_car(car)
    report_path = _issued_report_path(db, audit)
    payload["audit_report_download_url"] = (
        f"/quality/cars/invite/{car.invite_token}/audit-report" if report_path is not None else None
    )
    return payload


@_extension_router.patch("/cars/invite/{invite_token}", response_model=CAROut)
def submit_car_invite_with_detailed_response(
    invite_token: str,
    payload: CARInviteUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    car = _car_for_token(db, invite_token)
    _require_public_car_invite_editable(db, car)
    _persist_detailed_response_fields(car, payload)

    # Prevent the compatibility handler from re-applying its historical 500
    # character default to the four narrative fields. The same SQLAlchemy session
    # retains the values above while the base function executes all established
    # submission validation, evidence, review-state, audit and notification work.
    delegated_payload = payload.model_copy(
        update={field: None for field in _DETAILED_RESPONSE_FIELDS}
    )
    return _submit_car_from_invite_base(invite_token, delegated_payload, request, db)


@_extension_router.get("/cars/invite/{invite_token}/audit-report", response_class=FileResponse)
def download_invited_audit_report(
    invite_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    car = _car_for_token(db, invite_token)
    audit = _audit_for_car(car)
    report_path = _issued_report_path(db, audit)
    if report_path is None:
        raise HTTPException(status_code=404, detail="The issued audit report is not available for this CAR invitation.")

    audit_services.log_event(
        db,
        amo_id=audit.amo_id,
        actor_user_id=None,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="public_car_invite_report_download",
        after={"car_id": str(car.id), "car_number": car.car_number},
        correlation_id=str(uuid4()),
        metadata={
            "module": "quality",
            "route": str(request.url.path),
            "source": "car_invite",
        },
    )
    db.commit()

    media_type = mimetypes.guess_type(report_path.name)[0] or "application/octet-stream"
    return FileResponse(
        path=report_path,
        filename=_safe_report_filename(audit, report_path),
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


# Replace the original token read and update operations with the focused
# extension handlers. Upload/history/recall routes remain on their established
# implementations. Avoiding duplicate path+method registrations is important for
# deterministic routing and OpenAPI generation.
_original_token_path = "/quality/cars/invite/{invite_token}"
public_router.routes[:] = [
    route
    for route in public_router.routes
    if not (
        str(getattr(route, "path", "")) == _original_token_path
        and ({"GET", "PATCH"} & (getattr(route, "methods", None) or set()))
    )
]
public_router.routes[0:0] = list(_extension_router.routes)
