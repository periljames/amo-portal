from __future__ import annotations

from datetime import datetime
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.apps.audit import services as audit_services
from amodb.apps.quality import models as quality_models
from amodb.entitlements import _has_module_subscription
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models

router = APIRouter(prefix="/aerodoc", tags=["AeroDoc"])

_VERIFY_RATE_LIMIT_WINDOW_SEC = int(os.getenv("AERODOC_VERIFY_RATE_LIMIT_WINDOW_SEC", "60") or "60")
_VERIFY_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("AERODOC_VERIFY_RATE_LIMIT_MAX_ATTEMPTS", "20") or "20")
_VERIFY_RATE_LIMIT_STATE: dict[tuple[str, str], list[float]] = {}
_VERIFY_RATE_LIMIT_LOCK = threading.Lock()


def _client_ip(request: Request) -> str:
    try:
        return request.client.host if request.client else "unknown"
    except Exception:
        return "unknown"


def _enforce_verify_rate_limit(request: Request, amo_id: str) -> None:
    ip = _client_ip(request)
    now = time.monotonic()
    key = (ip, amo_id)
    with _VERIFY_RATE_LIMIT_LOCK:
        attempts = _VERIFY_RATE_LIMIT_STATE.get(key, [])
        cutoff = now - _VERIFY_RATE_LIMIT_WINDOW_SEC
        attempts = [ts for ts in attempts if ts >= cutoff]
        if len(attempts) >= _VERIFY_RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verify attempts. Please retry later.",
            )
        attempts.append(now)
        _VERIFY_RATE_LIMIT_STATE[key] = attempts


def _module_enabled(db: Session, amo_id: str) -> bool:
    try:
        enabled = _has_module_subscription(db, amo_id, "aerodoc_hybrid_dms")
    except Exception:
        return False
    return enabled is True


@router.get("/public/verify/{serial}")
def public_verify_copy(serial: str, amo_id: str = Query(...), request: Request = None, db: Session = Depends(get_db)):
    if request is not None:
        try:
            _enforce_verify_rate_limit(request, amo_id)
        except HTTPException:
            audit_services.log_event(
                db,
                amo_id=amo_id,
                actor_user_id=None,
                entity_type="qms.physical_copy.verify_public",
                entity_id=serial,
                action="rate_limited",
                after={"amo_id": amo_id},
                metadata={"module": "aerodoc_hybrid_dms"},
            )
            db.commit()
            raise

    if not _module_enabled(db, amo_id):
        raise HTTPException(status_code=403, detail="Module not enabled")

    copy = (
        db.query(quality_models.QMSPhysicalControlledCopy)
        .filter(
            quality_models.QMSPhysicalControlledCopy.amo_id == amo_id,
            quality_models.QMSPhysicalControlledCopy.copy_serial_number == serial,
        )
        .first()
    )
    if not copy:
        return {"serial": serial, "status": "RED", "current": False}

    rev = db.query(quality_models.QMSDocumentRevision).filter(quality_models.QMSDocumentRevision.id == copy.digital_revision_id).first()
    is_current = bool(
        rev
        and rev.lifecycle_status == quality_models.QMSRevisionLifecycleStatus.APPROVED
        and copy.status == quality_models.QMSPhysicalCopyStatus.ACTIVE
        and copy.voided_at is None
    )
    return {
        "serial": serial,
        "status": "GREEN" if is_current else "RED",
        "current": is_current,
        "approved_version": rev.version_semver if rev else None,
        "verified_at": datetime.utcnow().isoformat(),
    }


@router.get("/public/verify/rate-limit/stats")
def public_verify_rate_limit_stats(current_user: account_models.User = Depends(get_current_active_user)):
    role_value = getattr(current_user.role, "value", current_user.role)
    if not (
        current_user.is_superuser
        or role_value in {
            account_models.AccountRole.AMO_ADMIN,
            account_models.AccountRole.QUALITY_MANAGER,
            account_models.AccountRole.QUALITY_INSPECTOR,
            "AMO_ADMIN",
            "QUALITY_MANAGER",
            "QUALITY_INSPECTOR",
            "DOCUMENT_CONTROL_OFFICER",
        }
    ):
        raise HTTPException(status_code=403, detail="Document Control Officer or AMO Admin rights required")
    now = time.monotonic()
    active_keys = 0
    attempts_total = 0
    with _VERIFY_RATE_LIMIT_LOCK:
        for _, attempts in _VERIFY_RATE_LIMIT_STATE.items():
            filtered = [ts for ts in attempts if ts >= now - _VERIFY_RATE_LIMIT_WINDOW_SEC]
            if filtered:
                active_keys += 1
                attempts_total += len(filtered)
    return {
        "window_seconds": _VERIFY_RATE_LIMIT_WINDOW_SEC,
        "max_attempts": _VERIFY_RATE_LIMIT_MAX_ATTEMPTS,
        "active_keys": active_keys,
        "attempts_total": attempts_total,
    }
