# backend/amodb/apps/training/record_lifecycle.py
"""
Training record lifecycle helpers.

Purpose:
- Prevent exact duplicate training records for the same user/course/date.
- Treat a newer record for the same user/course as a renewal.
- Mark previous active records as RENEWED instead of deleting them.
- Keep historical records queryable for audit, but hide them from normal display.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ...user_id import generate_user_id
from . import models as training_models

RECORD_STATUS_ACTIVE = "ACTIVE"
RECORD_STATUS_RENEWED = "RENEWED"
RECORD_STATUS_SUPERSEDED = "SUPERSEDED"
HISTORICAL_STATUSES = {RECORD_STATUS_RENEWED, RECORD_STATUS_SUPERSEDED}


def normalise_record_status(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().upper().replace(" ", "_")
    if not raw:
        return None
    aliases = {
        "CURRENT": RECORD_STATUS_ACTIVE,
        "OK": RECORD_STATUS_ACTIVE,
        "COMPLIANT": RECORD_STATUS_ACTIVE,
        "ACTIVE": RECORD_STATUS_ACTIVE,
        "RENEWED": RECORD_STATUS_RENEWED,
        "SUPERSEDED": RECORD_STATUS_RENEWED,
        "INACTIVE": RECORD_STATUS_RENEWED,
    }
    return aliases.get(raw, raw)


def extract_remark_token(remarks: Optional[str], key: str) -> Optional[str]:
    if not remarks:
        return None
    match = re.search(rf"(?:^|\|)\s*{re.escape(key)}\s*=\s*([^|]+?)\s*(?:\||$)", remarks, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() or None


def get_record_lifecycle_status(record: training_models.TrainingRecord) -> str:
    """Return ACTIVE unless the DB column or legacy remarks mark the record as historical."""
    db_status = normalise_record_status(getattr(record, "record_status", None))
    if db_status:
        return db_status

    remark_status = normalise_record_status(extract_remark_token(getattr(record, "remarks", None), "LifecycleStatus"))
    if remark_status:
        return remark_status

    source_status = normalise_record_status(getattr(record, "source_status", None))
    if source_status:
        return source_status

    legacy_source_status = normalise_record_status(extract_remark_token(getattr(record, "remarks", None), "Status"))
    if legacy_source_status in HISTORICAL_STATUSES:
        return legacy_source_status

    return RECORD_STATUS_ACTIVE


def is_active_record(record: training_models.TrainingRecord) -> bool:
    return get_record_lifecycle_status(record) not in HISTORICAL_STATUSES


def active_records_filter(model=training_models.TrainingRecord):
    """SQLAlchemy filter for current display records only.

    Both record_status and source_status are checked so legacy imported rows
    marked as RENEWED/SUPERSEDED are hidden even before the lifecycle column is
    fully normalised.
    """
    historical = tuple(HISTORICAL_STATUSES)
    return and_(
        or_(model.record_status.is_(None), func.upper(model.record_status).notin_(historical)),
        or_(model.source_status.is_(None), func.upper(model.source_status).notin_(historical)),
    )


def list_active_records_for_user_course(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    course_id: str,
) -> list[training_models.TrainingRecord]:
    return (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user_id,
            training_models.TrainingRecord.course_id == course_id,
            active_records_filter(training_models.TrainingRecord),
        )
        .order_by(
            training_models.TrainingRecord.completion_date.desc(),
            training_models.TrainingRecord.created_at.desc(),
            training_models.TrainingRecord.id.desc(),
        )
        .all()
    )


def find_exact_duplicate(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    course_id: str,
    completion_date: date,
) -> Optional[training_models.TrainingRecord]:
    return (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user_id,
            training_models.TrainingRecord.course_id == course_id,
            training_models.TrainingRecord.completion_date == completion_date,
        )
        .order_by(training_models.TrainingRecord.created_at.desc(), training_models.TrainingRecord.id.desc())
        .first()
    )


def append_lifecycle_remark(remarks: Optional[str], status: str) -> str:
    token = f"LifecycleStatus={status}"
    raw = (remarks or "").strip()
    if not raw:
        return token
    if re.search(r"(?:^|\|)\s*LifecycleStatus\s*=", raw, flags=re.IGNORECASE):
        return raw
    return f"{raw} | {token}"


def mark_records_as_renewed(
    db: Session,
    *,
    previous_records: Iterable[training_models.TrainingRecord],
    renewed_by_record_id: str,
    actor_user_id: Optional[str] = None,
) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    for record in previous_records:
        if not is_active_record(record):
            continue
        record.record_status = RECORD_STATUS_RENEWED
        record.source_status = record.source_status or RECORD_STATUS_RENEWED
        record.superseded_by_record_id = renewed_by_record_id
        record.superseded_at = now
        record.remarks = append_lifecycle_remark(getattr(record, "remarks", None), RECORD_STATUS_RENEWED)
        if hasattr(record, "updated_by_user_id") and actor_user_id:
            record.updated_by_user_id = actor_user_id
        db.add(record)
        count += 1
    return count


def prepare_training_record_insert(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    course_id: str,
    completion_date: date,
    confirm_renewal: bool,
    actor_user_id: Optional[str] = None,
) -> tuple[str, list[training_models.TrainingRecord]]:
    """
    Returns a new record id and any prior active records that must be renewed.

    Behaviour:
    - Same user + same course + same completion date is an exact duplicate and should be blocked.
    - Same user + same course + later/different completion date is a renewal and requires confirmation.
    - Prior active records are marked renewed before the new insert to satisfy the partial unique index.
    """
    exact = find_exact_duplicate(
        db,
        amo_id=amo_id,
        user_id=user_id,
        course_id=course_id,
        completion_date=completion_date,
    )
    if exact is not None:
        raise ValueError("DUPLICATE_TRAINING_RECORD")

    previous_records = list_active_records_for_user_course(
        db,
        amo_id=amo_id,
        user_id=user_id,
        course_id=course_id,
    )
    if previous_records and not confirm_renewal:
        raise ValueError("TRAINING_RECORD_RENEWAL_CONFIRMATION_REQUIRED")

    new_record_id = generate_user_id()
    if previous_records:
        mark_records_as_renewed(
            db,
            previous_records=previous_records,
            renewed_by_record_id=new_record_id,
            actor_user_id=actor_user_id,
        )
        db.flush()

    return new_record_id, previous_records
