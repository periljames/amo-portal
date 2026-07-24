"""Focused public CAR invitation extensions.

This module is imported after the main Quality compatibility router has finished
loading. It replaces the original token-read route so existing public invite
URLs gain an audit-report link while retaining the same CAR payload and state
machine.
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
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_db

from . import models
from .router import _car_invite_payload, public_router
from .schemas import CARInviteOut


class CARInviteWithAuditReportOut(CARInviteOut):
    """Public invite response with a token-scoped report download route."""

    audit_report_download_url: Optional[str] = Field(default=None, max_length=1024)


_extension_router = APIRouter(prefix="/quality", tags=["Quality / Public CAR"])


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


@_extension_router.get("/cars/invite/{invite_token}", response_model=CARInviteWithAuditReportOut)
def get_car_invite_with_report(
    invite_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    car = _car_for_token(db, invite_token)
    payload = _car_invite_payload(car, request=request, db=db)
    audit = _audit_for_car(car)
    report_ref = getattr(audit, "report_file_ref", None) if audit is not None else None
    if report_ref and Path(report_ref).is_file():
        payload["audit_report_download_url"] = f"/quality/cars/invite/{car.invite_token}/audit-report"
    else:
        payload["audit_report_download_url"] = None
    return payload


@_extension_router.get("/cars/invite/{invite_token}/audit-report", response_class=FileResponse)
def download_invited_audit_report(
    invite_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    car = _car_for_token(db, invite_token)
    audit = _audit_for_car(car)
    if audit is None or not getattr(audit, "report_file_ref", None):
        raise HTTPException(status_code=404, detail="The issued audit report is not available for this CAR invitation.")

    report_path = Path(str(audit.report_file_ref)).resolve()
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail="The issued audit report file is unavailable.")

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


# Remove only the original token-read operation. The extension preserves its
# behaviour and adds report metadata, while all update/upload/history routes stay
# on their established handlers. Avoiding duplicate path+method registrations is
# important for deterministic routing and OpenAPI generation.
_original_token_path = "/quality/cars/invite/{invite_token}"
public_router.routes[:] = [
    route
    for route in public_router.routes
    if not (
        str(getattr(route, "path", "")) == _original_token_path
        and "GET" in (getattr(route, "methods", None) or set())
    )
]
public_router.routes[0:0] = list(_extension_router.routes)
