# backend/amodb/apps/workforce/services.py
from __future__ import annotations

import csv
import io
import math
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..audit import services as audit_services
from ..foundations import models as foundation_models
from ..foundations import schemas as foundation_schemas
from ..foundations import services as foundation_services
from ..notifications import service as notification_service
from ..work import models as work_models
from . import calculations, governance_models, hierarchy_roles, models, permissions, schemas

UTC = timezone.utc
ATTENDANCE_MAX_OPEN_SESSION = timedelta(hours=18)
ATTENDANCE_SELF_SERVICE_BACKDATE_LIMIT = timedelta(minutes=15)
ATTENDANCE_SELF_SERVICE_FUTURE_LIMIT = timedelta(minutes=5)
ATTENDANCE_RESILIENT_CAPTURE_LIMIT = timedelta(minutes=max(
    120,
    min(int(os.getenv("ATTENDANCE_RESILIENT_CAPTURE_LIMIT_MINUTES", "180") or "180"), 1_440),
))


def _utcnow() -> datetime:
    return datetime.now(UTC)


def effective_amo_id(user: account_models.User) -> str:
    return getattr(user, "effective_amo_id", None) or user.amo_id


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _model_fields_set(payload: Any) -> set[str]:
    return set(getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set())))


def _dump(payload: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    critical: bool = False,
) -> None:
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        metadata={"module": "workforce", **(metadata or {})},
        critical=critical,
    )


def _send_email(
    db: Session,
    *,
    amo_id: str,
    recipient: Optional[str],
    template_key: str,
    subject: str,
    context: dict[str, Any],
    correlation_id: str,
) -> None:
    try:
        notification_service.send_email(
            template_key=template_key,
            recipient=recipient,
            subject=subject,
            context=context,
            correlation_id=correlation_id,
            amo_id=amo_id,
            db=db,
        )
    except Exception:
        # Email delivery must not roll back the authoritative workforce workflow.
        # EmailLog preserves provider/configuration failures for admin review.
        return


def _require_user(db: Session, *, amo_id: str, user_id: str, active_only: bool = False) -> account_models.User:
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
    )
    if active_only:
        query = query.filter(account_models.User.is_active.is_(True))
    user = query.first()
    if not user:
        raise ValueError("User not found in AMO scope")
    if getattr(user, "is_system_account", False):
        raise ValueError("System accounts cannot own workforce records")
    return user


def personnel_profile_for_user(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    for_update: bool = False,
) -> Optional[account_models.PersonnelProfile]:
    query = db.query(account_models.PersonnelProfile).filter(
        account_models.PersonnelProfile.amo_id == amo_id,
        account_models.PersonnelProfile.user_id == user_id,
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def hire_dates_by_user(
    db: Session,
    *,
    amo_id: str,
    user_ids: Sequence[str],
) -> dict[str, date]:
    if not user_ids:
        return {}
    rows = db.query(
        account_models.PersonnelProfile.user_id,
        account_models.PersonnelProfile.hire_date,
    ).filter(
        account_models.PersonnelProfile.amo_id == amo_id,
        account_models.PersonnelProfile.user_id.in_(list(user_ids)),
        account_models.PersonnelProfile.hire_date.isnot(None),
    ).all()
    return {str(user_id): hire_date for user_id, hire_date in rows if user_id and hire_date}


def authoritative_contract_start(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    requested_start: date,
) -> tuple[date, bool]:
    """Return the imported hire date when present; otherwise retain the supplied start."""
    profile = personnel_profile_for_user(db, amo_id=amo_id, user_id=user_id)
    if profile and profile.hire_date:
        return profile.hire_date, True
    return requested_start, False


def _require_base(db: Session, *, amo_id: str, base_station_id: Optional[str]) -> Optional[foundation_models.BaseStation]:
    if not base_station_id:
        return None
    row = db.query(foundation_models.BaseStation).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        foundation_models.BaseStation.id == base_station_id,
    ).first()
    if not row:
        raise ValueError("Base station not found in AMO scope")
    return row


def _paginate(query, *, page: int, page_size: int) -> tuple[list[Any], int]:
    total = int(query.order_by(None).count())
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def page(items: list[Any], *, page_number: int, page_size: int, total: int) -> schemas.Page[Any]:
    return schemas.Page(
        items=items,
        page=page_number,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


# ---------------------------------------------------------------------------
# Employment contracts
# ---------------------------------------------------------------------------


def _contract_snapshot(row: models.EmploymentContract) -> dict[str, Any]:
    return {
        "user_id": row.user_id,
        "contract_type": _enum_value(row.contract_type),
        "employment_status": _enum_value(row.employment_status),
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "standard_weekly_minutes": row.standard_weekly_minutes,
        "standard_daily_minutes": row.standard_daily_minutes,
        "fte_percentage": row.fte_percentage,
        "primary_base_station_id": row.primary_base_station_id,
        "secondary_base_station_id": row.secondary_base_station_id,
        "supervisor_user_id": row.supervisor_user_id,
        "cost_centre": row.cost_centre,
        "payroll_number": row.payroll_number,
        "overtime_eligible": row.overtime_eligible,
        "night_shift_eligible": row.night_shift_eligible,
        "standby_eligible": row.standby_eligible,
    }


def _validate_contract_overlap(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    effective_from: date,
    effective_to: Optional[date],
    exclude_id: Optional[str] = None,
) -> None:
    end = effective_to or date.max
    query = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        models.EmploymentContract.effective_from <= end,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= effective_from),
    )
    if exclude_id:
        query = query.filter(models.EmploymentContract.id != exclude_id)
    conflict = query.order_by(models.EmploymentContract.effective_from.asc()).first()
    if conflict:
        raise ValueError(f"Employment contract overlaps existing contract {conflict.id}")


def serialize_contract(row: models.EmploymentContract) -> schemas.EmploymentContractRead:
    return schemas.EmploymentContractRead(
        **_contract_snapshot(row),
        id=row.id,
        amo_id=row.amo_id,
        user_full_name=getattr(row.user, "full_name", None),
        user_staff_code=getattr(row.user, "staff_code", None),
        primary_base_code=getattr(row.primary_base, "code", None),
        secondary_base_code=getattr(row.secondary_base, "code", None),
        supervisor_name=getattr(row.supervisor, "full_name", None),
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_contracts(
    db: Session,
    *,
    amo_id: str,
    page_number: int = 1,
    page_size: int = 50,
    user_id: Optional[str] = None,
    employment_status: Optional[models.EmploymentStatus] = None,
    base_station_id: Optional[str] = None,
    search: Optional[str] = None,
) -> schemas.Page[schemas.EmploymentContractRead]:
    query = db.query(models.EmploymentContract).options(
        selectinload(models.EmploymentContract.user),
        selectinload(models.EmploymentContract.primary_base),
        selectinload(models.EmploymentContract.secondary_base),
        selectinload(models.EmploymentContract.supervisor),
    ).filter(models.EmploymentContract.amo_id == amo_id)
    if user_id:
        query = query.filter(models.EmploymentContract.user_id == user_id)
    if employment_status:
        query = query.filter(models.EmploymentContract.employment_status == employment_status)
    if base_station_id:
        query = query.filter(or_(
            models.EmploymentContract.primary_base_station_id == base_station_id,
            models.EmploymentContract.secondary_base_station_id == base_station_id,
        ))
    if search:
        term = f"%{search.strip()}%"
        query = query.join(account_models.User, models.EmploymentContract.user_id == account_models.User.id).filter(or_(
            account_models.User.full_name.ilike(term),
            account_models.User.staff_code.ilike(term),
            models.EmploymentContract.payroll_number.ilike(term),
        ))
    query = query.order_by(models.EmploymentContract.effective_from.desc(), models.EmploymentContract.user_id.asc(), models.EmploymentContract.id.asc())
    rows, total = _paginate(query, page=page_number, page_size=page_size)
    return page([serialize_contract(row) for row in rows], page_number=page_number, page_size=page_size, total=total)


def get_contract(db: Session, *, amo_id: str, contract_id: str) -> Optional[models.EmploymentContract]:
    return db.query(models.EmploymentContract).options(
        selectinload(models.EmploymentContract.user),
        selectinload(models.EmploymentContract.primary_base),
        selectinload(models.EmploymentContract.secondary_base),
        selectinload(models.EmploymentContract.supervisor),
    ).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.id == contract_id,
    ).first()


def active_contract_for_user(db: Session, *, amo_id: str, user_id: str, on_date: date) -> Optional[models.EmploymentContract]:
    return db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.effective_from <= on_date,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= on_date),
    ).order_by(models.EmploymentContract.effective_from.desc()).first()


def _supervisor_validation_date(*, effective_from: date, effective_to: date | None) -> date:
    today = date.today()
    if effective_from <= today and (effective_to is None or effective_to >= today):
        return today
    return effective_from


def create_contract(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.EmploymentContractCreate,
) -> models.EmploymentContract:
    _require_user(db, amo_id=amo_id, user_id=payload.user_id)
    effective_from, start_locked = authoritative_contract_start(
        db,
        amo_id=amo_id,
        user_id=payload.user_id,
        requested_start=payload.effective_from,
    )
    if effective_from != payload.effective_from:
        payload = payload.model_copy(update={"effective_from": effective_from})
    _require_base(db, amo_id=amo_id, base_station_id=payload.primary_base_station_id)
    _require_base(db, amo_id=amo_id, base_station_id=payload.secondary_base_station_id)
    if payload.supervisor_user_id:
        _require_user(db, amo_id=amo_id, user_id=payload.supervisor_user_id)
        validation_date = _supervisor_validation_date(
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
        )
        hierarchy_roles.require_person_can_have_supervisor(
            db,
            amo_id=amo_id,
            user_id=payload.user_id,
            on_date=validation_date,
        )
        hierarchy_roles.require_no_reporting_cycle(
            db,
            amo_id=amo_id,
            user_id=payload.user_id,
            supervisor_user_id=payload.supervisor_user_id,
            on_date=validation_date,
        )
    _validate_contract_overlap(
        db,
        amo_id=amo_id,
        user_id=payload.user_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    row = models.EmploymentContract(
        amo_id=amo_id,
        **_dump(payload),
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="EmploymentContract",
        entity_id=row.id,
        action="create",
        after=_contract_snapshot(row),
        metadata={
            "effective_from_source": "PERSONNEL_HIRE_DATE" if start_locked else "CONTRACT_INPUT",
            "effective_from_locked": start_locked,
        },
    )
    return row


def update_contract(
    db: Session,
    *,
    row: models.EmploymentContract,
    actor_user_id: str,
    payload: schemas.EmploymentContractUpdate,
) -> models.EmploymentContract:
    before = _contract_snapshot(row)
    fields = _model_fields_set(payload)
    profile = personnel_profile_for_user(
        db,
        amo_id=row.amo_id,
        user_id=row.user_id,
    )
    hire_date = profile.hire_date if profile else None
    later_period_exists = db.query(models.EmploymentContract.id).filter(
        models.EmploymentContract.amo_id == row.amo_id,
        models.EmploymentContract.user_id == row.user_id,
        models.EmploymentContract.id != row.id,
        models.EmploymentContract.effective_from > row.effective_from,
    ).first() is not None
    start_locked = bool(hire_date and not later_period_exists)
    if start_locked and "effective_from" in fields and payload.effective_from != hire_date:
        raise ValueError(
            "Workforce start is controlled by the authoritative imported hire date. Update the personnel source record and re-import it to correct this date."
        )
    for base_field in ("primary_base_station_id", "secondary_base_station_id"):
        if base_field in fields:
            _require_base(db, amo_id=row.amo_id, base_station_id=getattr(payload, base_field))
    if "supervisor_user_id" in fields and payload.supervisor_user_id:
        _require_user(db, amo_id=row.amo_id, user_id=payload.supervisor_user_id)
    for key, value in _dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    if start_locked:
        row.effective_from = hire_date
    if row.effective_to and row.effective_to < row.effective_from:
        raise ValueError("effective_to must be on or after effective_from")
    if row.supervisor_user_id:
        validation_date = _supervisor_validation_date(
            effective_from=row.effective_from,
            effective_to=row.effective_to,
        )
        hierarchy_roles.require_person_can_have_supervisor(
            db,
            amo_id=row.amo_id,
            user_id=row.user_id,
            on_date=validation_date,
        )
        hierarchy_roles.require_no_reporting_cycle(
            db,
            amo_id=row.amo_id,
            user_id=row.user_id,
            supervisor_user_id=row.supervisor_user_id,
            on_date=validation_date,
        )
    _validate_contract_overlap(
        db,
        amo_id=row.amo_id,
        user_id=row.user_id,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        exclude_id=row.id,
    )
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    _audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="EmploymentContract",
        entity_id=row.id,
        action="update",
        before=before,
        after=_contract_snapshot(row),
        metadata={
            "effective_from_source": "PERSONNEL_HIRE_DATE" if start_locked else "CONTRACT_INPUT",
            "effective_from_locked": start_locked,
        },
    )
    return row


def sync_contract_start_from_hire_date(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    hire_date: Optional[date],
    actor_user_id: Optional[str],
    source: str,
) -> Optional[models.EmploymentContract]:
    """Align the initial employment period to the authoritative Workforce start date."""
    if not hire_date:
        return None
    row = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
    ).order_by(
        models.EmploymentContract.effective_from.asc(),
        models.EmploymentContract.id.asc(),
    ).with_for_update().first()
    if row is None or row.effective_from == hire_date:
        return row

    before = _contract_snapshot(row)
    blocked_reason: Optional[str] = None
    if row.effective_to and hire_date > row.effective_to:
        blocked_reason = "Hire date falls after the first contract's end date"
    else:
        try:
            _validate_contract_overlap(
                db,
                amo_id=amo_id,
                user_id=user_id,
                effective_from=hire_date,
                effective_to=row.effective_to,
                exclude_id=row.id,
            )
        except ValueError as exc:
            blocked_reason = str(exc)

    if blocked_reason:
        _audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            entity_type="EmploymentContract",
            entity_id=row.id,
            action="hire_date_sync_blocked",
            before=before,
            after=before,
            metadata={
                "source": source,
                "hire_date": hire_date.isoformat(),
                "reason": blocked_reason,
            },
            critical=True,
        )
        return row

    row.effective_from = hire_date
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="EmploymentContract",
        entity_id=row.id,
        action="sync_hire_date",
        before=before,
        after=_contract_snapshot(row),
        metadata={"source": source, "effective_from_locked": True},
        critical=True,
    )
    return row


def create_reemployment_contract(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    effective_from: date,
    actor_user_id: str,
    reason: str,
) -> Optional[models.EmploymentContract]:
    """Start a new controlled employment period by carrying forward the last contract terms."""
    latest = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
    ).order_by(
        models.EmploymentContract.effective_from.desc(),
        models.EmploymentContract.id.desc(),
    ).with_for_update().first()
    if latest is None:
        return None
    if latest.effective_from == effective_from:
        before = _contract_snapshot(latest)
        latest.employment_status = models.EmploymentStatus.ACTIVE
        latest.effective_to = None
        latest.updated_by_user_id = actor_user_id
        db.add(latest)
        db.flush()
        _audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            entity_type="EmploymentContract",
            entity_id=latest.id,
            action="reactivate_employment_period",
            before=before,
            after=_contract_snapshot(latest),
            metadata={"reason": reason, "effective_from_locked": True},
            critical=True,
        )
        return latest
    if latest.effective_from > effective_from:
        raise ValueError("Re-employment date must be after the latest contract start")

    previous_before = _contract_snapshot(latest)
    prior_end = effective_from - timedelta(days=1)
    if latest.effective_to is None or latest.effective_to >= effective_from:
        latest.effective_to = prior_end
        if latest.employment_status != models.EmploymentStatus.TERMINATED:
            latest.employment_status = models.EmploymentStatus.TERMINATED
        latest.updated_by_user_id = actor_user_id
        db.add(latest)
        db.flush()
        _audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            entity_type="EmploymentContract",
            entity_id=latest.id,
            action="close_for_reemployment",
            before=previous_before,
            after=_contract_snapshot(latest),
            metadata={"reason": reason},
            critical=True,
        )

    replacement = models.EmploymentContract(
        amo_id=amo_id,
        user_id=user_id,
        contract_type=latest.contract_type,
        employment_status=models.EmploymentStatus.ACTIVE,
        effective_from=effective_from,
        effective_to=None,
        standard_weekly_minutes=latest.standard_weekly_minutes,
        standard_daily_minutes=latest.standard_daily_minutes,
        fte_percentage=latest.fte_percentage,
        primary_base_station_id=latest.primary_base_station_id,
        secondary_base_station_id=latest.secondary_base_station_id,
        supervisor_user_id=latest.supervisor_user_id,
        cost_centre=latest.cost_centre,
        payroll_number=latest.payroll_number,
        overtime_eligible=latest.overtime_eligible,
        night_shift_eligible=latest.night_shift_eligible,
        standby_eligible=latest.standby_eligible,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(replacement)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="EmploymentContract",
        entity_id=replacement.id,
        action="create_reemployment_period",
        after=_contract_snapshot(replacement),
        metadata={"reason": reason, "effective_from_locked": True},
        critical=True,
    )
    return replacement


# ---------------------------------------------------------------------------
# Work patterns
# ---------------------------------------------------------------------------


def _pattern_day_read(row: models.WorkPatternDay) -> schemas.WorkPatternDayRead:
    return schemas.WorkPatternDayRead(
        id=row.id,
        amo_id=row.amo_id,
        work_pattern_id=row.work_pattern_id,
        cycle_day_index=row.cycle_day_index,
        shift_template_id=row.shift_template_id,
        status=row.status,
        start_time_local=row.start_time_local,
        end_time_local=row.end_time_local,
        spans_next_day=row.spans_next_day,
        planned_minutes=row.planned_minutes,
        shift_code=getattr(row.shift_template, "code", None),
        shift_label=getattr(row.shift_template, "label", None),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pattern_applicability(row: models.WorkPattern) -> schemas.WorkPatternApplicability:
    """Treat malformed legacy rule JSON as disabled instead of breaking setup."""
    try:
        return schemas.WorkPatternApplicability.model_validate(row.applicability_json or {})
    except (TypeError, ValueError):
        return schemas.WorkPatternApplicability()


def serialize_pattern(row: models.WorkPattern) -> schemas.WorkPatternRead:
    applicability = _pattern_applicability(row)
    return schemas.WorkPatternRead(
        id=row.id,
        amo_id=row.amo_id,
        code=row.code,
        name=row.name,
        description=row.description,
        cycle_length_days=row.cycle_length_days,
        is_active=row.is_active,
        timezone_name=row.timezone_name,
        applicability=applicability,
        days=[_pattern_day_read(day) for day in sorted(row.days or [], key=lambda item: item.cycle_day_index)],
        assigned_employee_count=len(row.employee_assignments or []),
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_patterns(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[schemas.WorkPatternRead]:
    query = db.query(models.WorkPattern).options(
        selectinload(models.WorkPattern.days).selectinload(models.WorkPatternDay.shift_template),
        selectinload(models.WorkPattern.employee_assignments),
    ).filter(models.WorkPattern.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.WorkPattern.is_active.is_(True))
    rows = query.order_by(models.WorkPattern.code.asc(), models.WorkPattern.id.asc()).all()
    return [serialize_pattern(row) for row in rows]


def get_pattern(db: Session, *, amo_id: str, pattern_id: str) -> Optional[models.WorkPattern]:
    return db.query(models.WorkPattern).options(
        selectinload(models.WorkPattern.days).selectinload(models.WorkPatternDay.shift_template),
        selectinload(models.WorkPattern.employee_assignments),
    ).filter(models.WorkPattern.amo_id == amo_id, models.WorkPattern.id == pattern_id).first()


def _replace_pattern_days(
    db: Session,
    *,
    pattern: models.WorkPattern,
    days: Sequence[schemas.WorkPatternDayInput],
) -> None:
    # Validate the complete replacement before mutating the managed collection.
    # Explicitly deleting children while leaving them attached to ``pattern.days``
    # makes a later ``Session.add(pattern)`` cascade into those deleted instances.
    shift_ids = {item.shift_template_id for item in days if item.shift_template_id}
    if shift_ids:
        from ..rostering import models as roster_models

        found_shift_ids = {
            shift_id
            for (shift_id,) in db.query(roster_models.ShiftTemplate.id).filter(
                roster_models.ShiftTemplate.amo_id == pattern.amo_id,
                roster_models.ShiftTemplate.id.in_(shift_ids),
            ).all()
        }
        if found_shift_ids != shift_ids:
            raise ValueError("Shift template not found in AMO scope")

    replacements = [
        models.WorkPatternDay(
            amo_id=pattern.amo_id,
            work_pattern_id=pattern.id,
            **_dump(item),
        )
        for item in sorted(days, key=lambda row: row.cycle_day_index)
    ]

    # WorkPattern.days owns its children via delete-orphan. Clear the relationship
    # before flushing so deleted instances are detached from the parent and the
    # unique (pattern, cycle-day) keys are released before replacements are added.
    pattern.days.clear()
    db.flush()
    pattern.days.extend(replacements)
    db.flush()


def _validate_automatic_pattern_shift_scope(
    db: Session,
    *,
    amo_id: str,
    shift_template_ids: Sequence[str],
    applicability: schemas.WorkPatternApplicability,
) -> None:
    if not applicability.auto_assign or not shift_template_ids:
        return
    from ..rostering import models as roster_models

    shifts = db.query(roster_models.ShiftTemplate).options(
        selectinload(roster_models.ShiftTemplate.departments),
    ).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.id.in_(set(shift_template_ids)),
    ).all()
    rule_departments = set(applicability.department_ids)
    for shift in shifts:
        allowed = set(shift.department_ids)
        if not allowed:
            continue
        if not rule_departments:
            raise ValueError(
                f"Shift {shift.code} is department-specific; choose departments for this automatic rotation"
            )
        if not rule_departments.issubset(allowed):
            raise ValueError(
                f"Shift {shift.code} is not available to every department selected for this rotation"
            )


def _validate_pattern_user_shift_scope(
    pattern: models.WorkPattern,
    *,
    user: account_models.User,
) -> None:
    department_id = str(user.department_id or "")
    for day in pattern.days or []:
        shift = day.shift_template
        allowed = set(getattr(shift, "department_ids", []) or []) if shift is not None else set()
        if allowed and department_id not in allowed:
            raise ValueError(
                f"Rotation {pattern.code} contains shift {shift.code}, which is not available to this employee's department"
            )


def create_pattern(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.WorkPatternCreate,
) -> models.WorkPattern:
    calculations.get_zone(payload.timezone_name)
    _validate_automatic_pattern_shift_scope(
        db,
        amo_id=amo_id,
        shift_template_ids=[str(day.shift_template_id) for day in payload.days if day.shift_template_id],
        applicability=payload.applicability,
    )
    row = models.WorkPattern(
        amo_id=amo_id,
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        description=payload.description,
        cycle_length_days=payload.cycle_length_days,
        is_active=payload.is_active,
        timezone_name=payload.timezone_name,
        applicability_json=payload.applicability.model_dump(mode="json"),
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    _replace_pattern_days(db, pattern=row, days=payload.days)
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="WorkPattern", entity_id=row.id, action="create", after={"code": row.code, "cycle_length_days": row.cycle_length_days})
    return row


def update_pattern(
    db: Session,
    *,
    row: models.WorkPattern,
    actor_user_id: str,
    payload: schemas.WorkPatternUpdate,
) -> models.WorkPattern:
    before = {
        "code": row.code,
        "name": row.name,
        "cycle_length_days": row.cycle_length_days,
        "is_active": row.is_active,
        "applicability": row.applicability_json or {},
    }
    fields = _model_fields_set(payload)
    if "timezone_name" in fields and payload.timezone_name:
        calculations.get_zone(payload.timezone_name)
    for key, value in _dump(payload, exclude_unset=True).items():
        if key == "days":
            continue
        if key == "applicability":
            row.applicability_json = payload.applicability.model_dump(mode="json") if payload.applicability else {}
            continue
        if key == "code" and value:
            value = value.strip().upper()
        if key == "name" and value:
            value = value.strip()
        setattr(row, key, value)
    final_applicability = payload.applicability or _pattern_applicability(row)
    final_shift_ids = (
        [str(day.shift_template_id) for day in payload.days if day.shift_template_id]
        if payload.days is not None
        else [str(day.shift_template_id) for day in row.days if day.shift_template_id]
    )
    _validate_automatic_pattern_shift_scope(
        db,
        amo_id=row.amo_id,
        shift_template_ids=final_shift_ids,
        applicability=final_applicability,
    )
    if payload.days is not None:
        cycle_length = payload.cycle_length_days or row.cycle_length_days
        if any(day.cycle_day_index >= cycle_length for day in payload.days):
            raise ValueError("cycle_day_index must be below cycle_length_days")
        _replace_pattern_days(db, pattern=row, days=payload.days)
    row.updated_by_user_id = actor_user_id
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="WorkPattern", entity_id=row.id, action="update", before=before, after={"code": row.code, "name": row.name, "cycle_length_days": row.cycle_length_days, "is_active": row.is_active, "applicability": row.applicability_json or {}})
    return row


def delete_pattern(
    db: Session,
    *,
    row: models.WorkPattern,
    actor_user_id: str,
    reason: str,
) -> None:
    """Delete setup mistakes while preserving assigned or generated history."""
    assignment_count = int(
        db.query(func.count(models.EmployeeWorkPatternAssignment.id)).filter(
            models.EmployeeWorkPatternAssignment.amo_id == row.amo_id,
            models.EmployeeWorkPatternAssignment.work_pattern_id == row.id,
        ).scalar()
        or 0
    )
    from ..rostering import models as roster_models

    rule_history_count = int(
        db.query(func.count(roster_models.RosterAssignment.id)).filter(
            roster_models.RosterAssignment.amo_id == row.amo_id,
            roster_models.RosterAssignment.source_reference_id.like(f"rule:{row.id}:%"),
        ).scalar()
        or 0
    )
    if assignment_count or rule_history_count:
        raise ValueError(
            "This rotation is assigned or has roster history and cannot be deleted. "
            "Retire it instead so published rosters keep their meaning."
        )
    before = {
        "code": row.code,
        "name": row.name,
        "cycle_length_days": row.cycle_length_days,
        "is_active": row.is_active,
        "reason": reason.strip(),
    }
    pattern_id = row.id
    amo_id = row.amo_id
    db.delete(row)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="WorkPattern",
        entity_id=pattern_id,
        action="delete_unused",
        before=before,
    )


def assign_pattern(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.EmployeeWorkPatternAssignmentCreate,
) -> models.EmployeeWorkPatternAssignment:
    user = _require_user(db, amo_id=amo_id, user_id=payload.user_id, active_only=True)
    pattern = get_pattern(db, amo_id=amo_id, pattern_id=payload.work_pattern_id)
    if not pattern or not pattern.is_active:
        raise ValueError("Active work pattern not found")
    _validate_pattern_user_shift_scope(pattern, user=user)
    end = payload.effective_to or date.max
    overlap = db.query(models.EmployeeWorkPatternAssignment).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id == payload.user_id,
        models.EmployeeWorkPatternAssignment.effective_from <= end,
        or_(models.EmployeeWorkPatternAssignment.effective_to.is_(None), models.EmployeeWorkPatternAssignment.effective_to >= payload.effective_from),
    ).first()
    if overlap:
        raise ValueError("Employee already has an overlapping work-pattern assignment")
    row = models.EmployeeWorkPatternAssignment(
        amo_id=amo_id,
        **_dump(payload),
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="EmployeeWorkPatternAssignment", entity_id=row.id, action="create", after=_dump(payload))
    return row


def list_pattern_assignments(
    db: Session,
    *,
    amo_id: str,
    user_id: Optional[str] = None,
    pattern_id: Optional[str] = None,
) -> list[schemas.EmployeeWorkPatternAssignmentRead]:
    query = db.query(models.EmployeeWorkPatternAssignment).options(
        selectinload(models.EmployeeWorkPatternAssignment.user),
        selectinload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(models.EmployeeWorkPatternAssignment.amo_id == amo_id)
    if user_id:
        query = query.filter(models.EmployeeWorkPatternAssignment.user_id == user_id)
    if pattern_id:
        query = query.filter(models.EmployeeWorkPatternAssignment.work_pattern_id == pattern_id)
    rows = query.order_by(models.EmployeeWorkPatternAssignment.user_id.asc(), models.EmployeeWorkPatternAssignment.effective_from.desc()).all()
    return [schemas.EmployeeWorkPatternAssignmentRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        work_pattern_id=row.work_pattern_id,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        cycle_anchor_date=row.cycle_anchor_date,
        user_full_name=getattr(row.user, "full_name", None),
        pattern_code=getattr(row.work_pattern, "code", None),
        pattern_name=getattr(row.work_pattern, "name", None),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ) for row in rows]


def update_pattern_assignment(
    db: Session,
    *,
    row: models.EmployeeWorkPatternAssignment,
    actor_user_id: str,
    payload: schemas.EmployeeWorkPatternAssignmentUpdate,
) -> models.EmployeeWorkPatternAssignment:
    values = _dump(payload, exclude_unset=True)
    reason = str(values.pop("reason", "")).strip()
    next_pattern_id = values.get("work_pattern_id", row.work_pattern_id)
    next_from = values.get("effective_from", row.effective_from)
    next_to = values.get("effective_to", row.effective_to)
    next_anchor = values.get("cycle_anchor_date", row.cycle_anchor_date)
    if next_to and next_to < next_from:
        raise ValueError("effective_to must be on or after effective_from")
    pattern = get_pattern(db, amo_id=row.amo_id, pattern_id=next_pattern_id)
    if not pattern or not pattern.is_active:
        raise ValueError("Active work pattern not found")
    user = _require_user(db, amo_id=row.amo_id, user_id=row.user_id, active_only=True)
    _validate_pattern_user_shift_scope(pattern, user=user)
    end = next_to or date.max
    overlap = db.query(models.EmployeeWorkPatternAssignment).filter(
        models.EmployeeWorkPatternAssignment.amo_id == row.amo_id,
        models.EmployeeWorkPatternAssignment.user_id == row.user_id,
        models.EmployeeWorkPatternAssignment.id != row.id,
        models.EmployeeWorkPatternAssignment.effective_from <= end,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= next_from,
        ),
    ).first()
    if overlap:
        raise ValueError("Employee already has an overlapping work-pattern assignment")
    before = {
        "work_pattern_id": row.work_pattern_id,
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
    }
    row.work_pattern_id = next_pattern_id
    row.effective_from = next_from
    row.effective_to = next_to
    row.cycle_anchor_date = next_anchor
    db.add(row)
    db.flush()
    _audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="EmployeeWorkPatternAssignment",
        entity_id=row.id,
        action="update",
        before=before,
        after={
            "work_pattern_id": row.work_pattern_id,
            "effective_from": row.effective_from.isoformat(),
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
            "reason": reason,
        },
    )
    return row


def delete_pattern_assignment(
    db: Session,
    *,
    row: models.EmployeeWorkPatternAssignment,
    actor_user_id: str,
    reason: str,
) -> None:
    snapshot = {
        "user_id": row.user_id,
        "work_pattern_id": row.work_pattern_id,
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
        "reason": reason.strip(),
    }
    _audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="EmployeeWorkPatternAssignment",
        entity_id=row.id,
        action="delete",
        before=snapshot,
    )
    db.delete(row)
    db.flush()


def preview_patterns(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.PatternPreviewRequest,
    pattern_id: Optional[str] = None,
) -> schemas.PatternPreviewResponse:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    timezone_name = getattr(amo, "time_zone", None) or "UTC"
    zone = calculations.get_zone(timezone_name)
    query = db.query(models.EmployeeWorkPatternAssignment).join(
        models.WorkPattern,
        models.EmployeeWorkPatternAssignment.work_pattern_id == models.WorkPattern.id,
    ).options(
        selectinload(models.EmployeeWorkPatternAssignment.user),
        selectinload(models.EmployeeWorkPatternAssignment.work_pattern)
        .selectinload(models.WorkPattern.days)
        .selectinload(models.WorkPatternDay.shift_template),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.is_active.is_(True),
        models.EmployeeWorkPatternAssignment.effective_from <= payload.to_date,
        or_(models.EmployeeWorkPatternAssignment.effective_to.is_(None), models.EmployeeWorkPatternAssignment.effective_to >= payload.from_date),
    )
    if payload.user_ids:
        query = query.filter(models.EmployeeWorkPatternAssignment.user_id.in_(payload.user_ids))
    if pattern_id:
        query = query.filter(models.EmployeeWorkPatternAssignment.work_pattern_id == pattern_id)
    assignments = query.order_by(models.EmployeeWorkPatternAssignment.user_id.asc(), models.EmployeeWorkPatternAssignment.effective_from.asc()).all()

    existing_keys: set[str] = set()
    existing_roster_rows: list[Any] = []
    if payload.roster_version_id:
        from ..rostering import models as roster_models
        existing_roster_rows = db.query(roster_models.RosterAssignment).filter(
            roster_models.RosterAssignment.amo_id == amo_id,
            roster_models.RosterAssignment.version_id == payload.roster_version_id,
            roster_models.RosterAssignment.deleted_at.is_(None),
        ).all()
        existing_keys = {str(row.source_reference_id) for row in existing_roster_rows if row.source_reference_id}

    requested_user_ids = sorted({str(value) for value in payload.user_ids if value})
    people_query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if requested_user_ids:
        people_query = people_query.filter(account_models.User.id.in_(requested_user_ids))
    people = people_query.order_by(account_models.User.full_name.asc(), account_models.User.id.asc()).all()
    people_by_id = {str(row.id): row for row in people}

    contracts = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id.in_(list(people_by_id) or ["__none__"]),
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.effective_from <= payload.to_date,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= payload.from_date),
    ).order_by(models.EmploymentContract.effective_from.desc(), models.EmploymentContract.id.asc()).all()
    contracts_by_user: dict[str, list[models.EmploymentContract]] = defaultdict(list)
    for contract in contracts:
        contracts_by_user[str(contract.user_id)].append(contract)

    # Generation used to call ``active_contract_for_user`` once for every
    # employee/day occurrence and scan every existing roster row for every
    # collision check. A 69-person monthly roster therefore issued more than
    # 2,000 avoidable contract queries and could exceed the portal's write
    # timeout. Keep the already range-scoped data in user indexes instead.
    existing_roster_by_user: dict[str, list[Any]] = defaultdict(list)
    for roster_row in existing_roster_rows:
        existing_roster_by_user[str(roster_row.user_id)].append(roster_row)

    placements = db.query(governance_models.WorkforcePersonPlacement).options(
        selectinload(governance_models.WorkforcePersonPlacement.org_unit),
    ).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.user_id.in_(list(people_by_id) or ["__none__"]),
        governance_models.WorkforcePersonPlacement.effective_from <= payload.to_date,
        or_(
            governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= payload.from_date,
        ),
    ).order_by(
        governance_models.WorkforcePersonPlacement.effective_from.desc(),
        governance_models.WorkforcePersonPlacement.id.asc(),
    ).all()
    placements_by_user: dict[str, list[governance_models.WorkforcePersonPlacement]] = defaultdict(list)
    for placement in placements:
        placements_by_user[str(placement.user_id)].append(placement)

    automatic_query = db.query(models.WorkPattern).options(
        selectinload(models.WorkPattern.days).selectinload(models.WorkPatternDay.shift_template),
    ).filter(models.WorkPattern.amo_id == amo_id, models.WorkPattern.is_active.is_(True))
    if pattern_id:
        automatic_query = automatic_query.filter(models.WorkPattern.id == pattern_id)
    automatic_patterns = [row for row in automatic_query.all() if _pattern_applicability(row).auto_assign]

    def on_date(rows: Sequence[Any], work_date: date) -> Optional[Any]:
        return next((row for row in rows if row.effective_from <= work_date and (row.effective_to is None or row.effective_to >= work_date)), None)

    def pattern_match(
        pattern: models.WorkPattern,
        *,
        person: account_models.User,
        contract: models.EmploymentContract,
        placement: Optional[governance_models.WorkforcePersonPlacement],
    ) -> Optional[tuple[int, int, schemas.WorkPatternApplicability]]:
        rule = _pattern_applicability(pattern)
        if not rule.auto_assign or rule.anchor_date is None:
            return None
        department_candidates = {str(person.department_id)} if person.department_id else set()
        legacy_department_id = getattr(getattr(placement, "org_unit", None), "legacy_department_id", None)
        if legacy_department_id:
            department_candidates.add(str(legacy_department_id))
        if rule.department_ids and not department_candidates.intersection(rule.department_ids):
            return None
        if rule.position_ids and (not placement or str(placement.position_id or "") not in rule.position_ids):
            return None
        contract_type = _enum_value(contract.contract_type)
        if rule.contract_types and contract_type not in {_enum_value(value) for value in rule.contract_types}:
            return None
        specificity = sum(bool(group) for group in (rule.position_ids, rule.department_ids, rule.contract_types))
        return specificity, rule.priority, rule

    def row_conflicts(
        *,
        user_id: str,
        department_id: Optional[str],
        work_date: date,
        starts_at: Optional[datetime],
        ends_at: Optional[datetime],
        shift: Optional[Any],
        contract: Optional[models.EmploymentContract],
        source_reference_id: str,
        commitments_by_user: dict[str, list[Any]],
    ) -> list[str]:
        conflicts: list[str] = []
        allowed_departments = set(getattr(shift, "department_ids", []) or []) if shift is not None else set()
        if allowed_departments and str(department_id or "") not in allowed_departments:
            conflicts.append("SHIFT_NOT_AVAILABLE_FOR_DEPARTMENT")
        if contract is None:
            conflicts.append("MISSING_ACTIVE_CONTRACT")
        elif shift is not None:
            shift_kind = _enum_value(getattr(shift, "kind", ""))
            if shift_kind == "NIGHT" and not contract.night_shift_eligible:
                conflicts.append("NIGHT_SHIFT_NOT_ELIGIBLE")
            if shift_kind == "STANDBY" and not contract.standby_eligible:
                conflicts.append("STANDBY_NOT_ELIGIBLE")
        if starts_at is None or ends_at is None:
            aware_start = datetime.combine(work_date, time.min, tzinfo=zone).astimezone(UTC)
            aware_end = datetime.combine(work_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        else:
            aware_start = calculations.ensure_aware(starts_at)
            aware_end = calculations.ensure_aware(ends_at)
        for commitment in commitments_by_user.get(user_id, []):
            protects_cell = commitment.blocking or (
                commitment.provisional and commitment.source_module == "WORKFORCE"
            )
            if protects_cell and aware_start < calculations.ensure_aware(commitment.ends_at) and aware_end > calculations.ensure_aware(commitment.starts_at):
                conflicts.append(f"PROTECTED_{_enum_value(commitment.kind).upper()}")
        for roster_row in existing_roster_by_user.get(user_id, []):
            if str(roster_row.source_reference_id or "") == source_reference_id:
                continue
            if aware_start < calculations.ensure_aware(roster_row.ends_at) and aware_end > calculations.ensure_aware(roster_row.starts_at):
                conflicts.append("ROSTER_CELL_OCCUPIED")
                break
        return sorted(set(conflicts))

    from ..rostering import commitments as roster_commitments
    protected = roster_commitments.list_commitments(
        db,
        amo_id=amo_id,
        from_date=payload.from_date,
        to_date=payload.to_date,
        user_ids=list(people_by_id),
    ).items
    commitments_by_user: dict[str, list[Any]] = defaultdict(list)
    for commitment in protected:
        commitments_by_user[str(commitment.user_id)].append(commitment)

    rows: list[schemas.PatternPreviewRow] = []
    explicit_dates: set[tuple[str, date]] = set()
    for assignment in assignments:
        days = {day.cycle_day_index: day for day in assignment.work_pattern.days or []}
        occurrences = calculations.preview_work_pattern(
            assignment=assignment,
            pattern_days=days,
            from_date=payload.from_date,
            to_date=payload.to_date,
            timezone_name=timezone_name,
        )
        for occurrence in occurrences:
            explicit_dates.add((str(occurrence.user_id), occurrence.work_date))
            contract = on_date(contracts_by_user.get(str(occurrence.user_id), []), occurrence.work_date)
            shift = days[occurrence.cycle_day_index].shift_template
            conflicts = row_conflicts(
                user_id=str(occurrence.user_id),
                department_id=getattr(assignment.user, "department_id", None),
                work_date=occurrence.work_date,
                starts_at=occurrence.starts_at,
                ends_at=occurrence.ends_at,
                shift=shift,
                contract=contract,
                source_reference_id=occurrence.source_reference_id,
                commitments_by_user=commitments_by_user,
            )
            rows.append(schemas.PatternPreviewRow(
                user_id=occurrence.user_id,
                user_full_name=getattr(assignment.user, "full_name", None),
                work_date=occurrence.work_date,
                cycle_day_index=occurrence.cycle_day_index,
                status=occurrence.status,
                starts_at=occurrence.starts_at,
                ends_at=occurrence.ends_at,
                planned_minutes=occurrence.planned_minutes,
                shift_template_id=occurrence.shift_template_id,
                shift_code=getattr(shift, "code", None),
                pattern_id=assignment.work_pattern_id,
                pattern_code=getattr(assignment.work_pattern, "code", None),
                resolution_source="EXPLICIT",
                base_station_id=getattr(contract, "primary_base_station_id", None),
                source_reference_id=occurrence.source_reference_id,
                duplicate=occurrence.source_reference_id in existing_keys,
                conflicts=conflicts,
            ))

    cursor = payload.from_date
    while cursor <= payload.to_date:
        for user_id, person in people_by_id.items():
            if (user_id, cursor) in explicit_dates:
                continue
            contract = on_date(contracts_by_user.get(user_id, []), cursor)
            if contract is None or _enum_value(contract.employment_status) not in {"ACTIVE", "ONBOARDING"}:
                continue
            placement = on_date(placements_by_user.get(user_id, []), cursor)
            matches: list[tuple[int, int, models.WorkPattern, schemas.WorkPatternApplicability]] = []
            for pattern in automatic_patterns:
                matched = pattern_match(pattern, person=person, contract=contract, placement=placement)
                if matched:
                    matches.append((matched[0], matched[1], pattern, matched[2]))
            if not matches:
                continue
            matches.sort(key=lambda item: (-item[0], item[1], item[2].code, item[2].id))
            specificity, priority, pattern, rule = matches[0]
            ambiguous = len(matches) > 1 and matches[1][0] == specificity and matches[1][1] == priority
            cycle_index = calculations.resolve_cycle_day(
                work_date=cursor,
                cycle_anchor_date=rule.anchor_date,
                cycle_length_days=pattern.cycle_length_days,
            )
            pattern_day = next((day for day in pattern.days or [] if day.cycle_day_index == cycle_index), None)
            if pattern_day is None:
                continue
            starts_at, ends_at, minutes = calculations.local_shift_window_to_utc(
                work_date=cursor,
                start_time_local=pattern_day.start_time_local,
                end_time_local=pattern_day.end_time_local,
                timezone_name=timezone_name or pattern.timezone_name,
                spans_next_day=pattern_day.spans_next_day,
                fallback_minutes=pattern_day.planned_minutes,
            )
            source_reference_id = f"rule:{pattern.id}:{user_id}:{cursor.isoformat()}"
            conflicts = row_conflicts(
                user_id=user_id,
                department_id=getattr(person, "department_id", None),
                work_date=cursor,
                starts_at=starts_at,
                ends_at=ends_at,
                shift=pattern_day.shift_template,
                contract=contract,
                source_reference_id=source_reference_id,
                commitments_by_user=commitments_by_user,
            )
            if ambiguous:
                conflicts.append("AMBIGUOUS_PATTERN_RULE")
            rows.append(schemas.PatternPreviewRow(
                user_id=user_id,
                user_full_name=person.full_name,
                work_date=cursor,
                cycle_day_index=cycle_index,
                status=pattern_day.status,
                starts_at=starts_at,
                ends_at=ends_at,
                planned_minutes=minutes,
                shift_template_id=pattern_day.shift_template_id,
                shift_code=getattr(pattern_day.shift_template, "code", None),
                pattern_id=pattern.id,
                pattern_code=pattern.code,
                resolution_source="RULE",
                base_station_id=getattr(contract, "primary_base_station_id", None),
                source_reference_id=source_reference_id,
                duplicate=source_reference_id in existing_keys,
                conflicts=sorted(set(conflicts)),
            ))
        cursor += timedelta(days=1)
    rows.sort(key=lambda item: (item.work_date, item.user_full_name or item.user_id, item.starts_at or datetime.min.replace(tzinfo=UTC)))
    return schemas.PatternPreviewResponse(
        from_date=payload.from_date,
        to_date=payload.to_date,
        item_count=len(rows),
        duplicate_count=sum(1 for row in rows if row.duplicate),
        conflict_count=sum(1 for row in rows if row.conflicts),
        items=rows,
    )


# ---------------------------------------------------------------------------
# Leave, balances and availability
# ---------------------------------------------------------------------------


def seed_default_leave_types(db: Session, *, amo_id: str, actor_user_id: Optional[str] = None) -> None:
    defaults = [
        ("ANNUAL", "Annual leave", models.AvailabilityType.ANNUAL_LEAVE, True, True),
        ("SICK", "Sick leave", models.AvailabilityType.SICK_LEAVE, True, False),
        ("COMPASSIONATE", "Compassionate leave", models.AvailabilityType.COMPASSIONATE_LEAVE, True, False),
        ("MATERNITY", "Maternity leave", models.AvailabilityType.MATERNITY_LEAVE, True, False),
        ("PATERNITY", "Paternity leave", models.AvailabilityType.PATERNITY_LEAVE, True, False),
        ("STUDY", "Study leave", models.AvailabilityType.STUDY_LEAVE, True, True),
        ("UNPAID", "Unpaid leave", models.AvailabilityType.UNPAID_LEAVE, False, False),
    ]
    existing = {row[0] for row in db.query(models.LeaveType.code).filter(models.LeaveType.amo_id == amo_id).all()}
    for order, (code, name, availability_type, paid, deducts) in enumerate(defaults, start=1):
        if code in existing:
            continue
        db.add(models.LeaveType(
            amo_id=amo_id,
            code=code,
            name=name,
            availability_type=availability_type,
            paid=paid,
            deducts_balance=deducts,
            supervisor_approval_required=True,
            hr_approval_required=True,
            display_order=order * 10,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        ))
    db.flush()


def list_leave_types(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.LeaveType]:
    seed_default_leave_types(db, amo_id=amo_id)
    query = db.query(models.LeaveType).filter(models.LeaveType.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.LeaveType.is_active.is_(True))
    return query.order_by(models.LeaveType.display_order.asc(), models.LeaveType.code.asc()).all()


def create_leave_type(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.LeaveTypeCreate) -> models.LeaveType:
    row = models.LeaveType(
        amo_id=amo_id,
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        **{key: value for key, value in _dump(payload).items() if key not in {"code", "name"}},
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="LeaveType", entity_id=row.id, action="create", after={"code": row.code, "name": row.name})
    return row


def update_leave_type(db: Session, *, row: models.LeaveType, actor_user_id: str, payload: schemas.LeaveTypeUpdate) -> models.LeaveType:
    before = {"name": row.name, "availability_type": _enum_value(row.availability_type), "is_active": row.is_active}
    for key, value in _dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="LeaveType", entity_id=row.id, action="update", before=before, after={"name": row.name, "availability_type": _enum_value(row.availability_type), "is_active": row.is_active})
    return row


def _balance_available(row: models.EmployeeLeaveBalance) -> int:
    return row.allocated_minutes + row.carried_minutes + row.adjustment_minutes - row.used_minutes - row.pending_minutes


def serialize_balance(row: models.EmployeeLeaveBalance) -> schemas.LeaveBalanceRead:
    return schemas.LeaveBalanceRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        user_full_name=getattr(row.user, "full_name", None),
        leave_type_id=row.leave_type_id,
        leave_type_code=getattr(row.leave_type, "code", None),
        leave_type_name=getattr(row.leave_type, "name", None),
        leave_year=row.leave_year,
        allocated_minutes=row.allocated_minutes,
        carried_minutes=row.carried_minutes,
        used_minutes=row.used_minutes,
        pending_minutes=row.pending_minutes,
        adjustment_minutes=row.adjustment_minutes,
        available_minutes=_balance_available(row),
        updated_by_user_id=row.updated_by_user_id,
        updated_at=row.updated_at,
    )


def list_balances(db: Session, *, amo_id: str, user_id: Optional[str] = None, leave_year: Optional[int] = None) -> list[schemas.LeaveBalanceRead]:
    query = db.query(models.EmployeeLeaveBalance).options(
        selectinload(models.EmployeeLeaveBalance.user),
        selectinload(models.EmployeeLeaveBalance.leave_type),
    ).filter(models.EmployeeLeaveBalance.amo_id == amo_id)
    if user_id:
        query = query.filter(models.EmployeeLeaveBalance.user_id == user_id)
    if leave_year:
        query = query.filter(models.EmployeeLeaveBalance.leave_year == leave_year)
    rows = query.order_by(models.EmployeeLeaveBalance.leave_year.desc(), models.EmployeeLeaveBalance.user_id.asc(), models.EmployeeLeaveBalance.leave_type_id.asc()).all()
    return [serialize_balance(row) for row in rows]


def update_balance(db: Session, *, row: models.EmployeeLeaveBalance, actor_user_id: str, payload: schemas.LeaveBalanceUpdate) -> models.EmployeeLeaveBalance:
    before = {"allocated_minutes": row.allocated_minutes, "carried_minutes": row.carried_minutes, "adjustment_minutes": row.adjustment_minutes}
    for key, value in _dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="EmployeeLeaveBalance", entity_id=row.id, action="update", before=before, after={"allocated_minutes": row.allocated_minutes, "carried_minutes": row.carried_minutes, "adjustment_minutes": row.adjustment_minutes})
    return row


def _requested_minutes(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    starts_at: datetime,
    ends_at: datetime,
    explicit: Optional[int],
) -> int:
    """Calculate leave against planned working time, never 24-hour days."""

    if explicit is not None:
        return int(explicit)
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    zone = calculations.get_zone(getattr(amo, "time_zone", None) or "UTC")
    local_start = calculations.ensure_aware(starts_at).astimezone(zone).date()
    local_end = (calculations.ensure_aware(ends_at).astimezone(zone) - timedelta(microseconds=1)).date()
    preview = preview_patterns(
        db,
        amo_id=amo_id,
        payload=schemas.PatternPreviewRequest(
            from_date=local_start,
            to_date=local_end,
            user_ids=[user_id],
        ),
    )
    if preview.items:
        planned = sum(max(int(item.planned_minutes or 0), 0) for item in preview.items)
        if planned <= 0:
            raise ValueError("The selected dates contain no scheduled working time")
        return planned

    requested = 0
    cursor = local_start
    while cursor <= local_end:
        if cursor.weekday() < 5:
            contract = active_contract_for_user(db, amo_id=amo_id, user_id=user_id, on_date=cursor)
            requested += int(getattr(contract, "standard_daily_minutes", 480) or 480)
        cursor += timedelta(days=1)
    if requested <= 0:
        raise ValueError("The selected dates contain no contracted working time")
    return requested


def _leave_balance(db: Session, *, request: models.LeaveRequest, create: bool = False) -> Optional[models.EmployeeLeaveBalance]:
    leave_year = request.starts_at.year
    query = db.query(models.EmployeeLeaveBalance).filter(
        models.EmployeeLeaveBalance.amo_id == request.amo_id,
        models.EmployeeLeaveBalance.user_id == request.user_id,
        models.EmployeeLeaveBalance.leave_type_id == request.leave_type_id,
        models.EmployeeLeaveBalance.leave_year == leave_year,
    )
    row = query.with_for_update().first()
    if row is None and create:
        row = models.EmployeeLeaveBalance(
            amo_id=request.amo_id,
            user_id=request.user_id,
            leave_type_id=request.leave_type_id,
            leave_year=leave_year,
        )
        db.add(row)
        db.flush()
    return row


def _published_roster_conflicts(db: Session, *, request: models.LeaveRequest) -> list[dict[str, Any]]:
    from ..rostering import models as roster_models
    rows = db.query(roster_models.RosterAssignment).join(
        roster_models.RosterVersion,
        roster_models.RosterAssignment.version_id == roster_models.RosterVersion.id,
    ).filter(
        roster_models.RosterAssignment.amo_id == request.amo_id,
        roster_models.RosterAssignment.user_id == request.user_id,
        roster_models.RosterVersion.status == roster_models.RosterVersionStatus.PUBLISHED,
        roster_models.RosterAssignment.starts_at < request.ends_at,
        roster_models.RosterAssignment.ends_at > request.starts_at,
    ).order_by(roster_models.RosterAssignment.starts_at.asc(), roster_models.RosterAssignment.id.asc()).all()
    return [{
        "assignment_id": row.id,
        "version_id": row.version_id,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "status": _enum_value(row.status),
    } for row in rows]


def serialize_leave_request(db: Session, row: models.LeaveRequest) -> schemas.LeaveRequestRead:
    approvals = [schemas.LeaveApprovalRead(
        id=approval.id,
        stage=approval.stage,
        decision=approval.decision,
        actor_user_id=approval.actor_user_id,
        actor_name=getattr(approval.actor, "full_name", None),
        comment=approval.comment,
        decided_at=approval.decided_at,
    ) for approval in sorted(row.approvals or [], key=lambda item: item.decided_at)]
    return schemas.LeaveRequestRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        user_full_name=getattr(row.user, "full_name", None),
        user_staff_code=getattr(row.user, "staff_code", None),
        department_id=getattr(row.user, "department_id", None),
        leave_type_id=row.leave_type_id,
        leave_type_code=getattr(row.leave_type, "code", None),
        leave_type_name=getattr(row.leave_type, "name", None),
        availability_type=getattr(row.leave_type, "availability_type", None),
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        requested_minutes=row.requested_minutes,
        status=row.status,
        reason=row.reason,
        attachment_reference=row.attachment_reference,
        published_roster_conflicts=_published_roster_conflicts(db, request=row),
        approvals=approvals,
        submitted_at=row.submitted_at,
        supervisor_approved_at=row.supervisor_approved_at,
        hr_approved_at=row.hr_approved_at,
        rejected_at=row.rejected_at,
        cancelled_at=row.cancelled_at,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _leave_query(db: Session, *, amo_id: str):
    return db.query(models.LeaveRequest).options(
        selectinload(models.LeaveRequest.user),
        selectinload(models.LeaveRequest.leave_type),
        selectinload(models.LeaveRequest.approvals).selectinload(models.LeaveRequestApproval.actor),
    ).filter(models.LeaveRequest.amo_id == amo_id)


def get_leave_request(db: Session, *, amo_id: str, request_id: str) -> Optional[models.LeaveRequest]:
    return _leave_query(db, amo_id=amo_id).filter(models.LeaveRequest.id == request_id).first()


def list_leave_requests(
    db: Session,
    *,
    amo_id: str,
    page_number: int,
    page_size: int,
    user_id: Optional[str] = None,
    department_id: Optional[str] = None,
    request_status: Optional[models.LeaveRequestStatus] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> schemas.Page[schemas.LeaveRequestRead]:
    query = _leave_query(db, amo_id=amo_id)
    if user_id:
        query = query.filter(models.LeaveRequest.user_id == user_id)
    if department_id:
        query = query.join(account_models.User, models.LeaveRequest.user_id == account_models.User.id).filter(account_models.User.department_id == department_id)
    if request_status:
        query = query.filter(models.LeaveRequest.status == request_status)
    if from_date:
        query = query.filter(models.LeaveRequest.ends_at >= datetime.combine(from_date, time.min, tzinfo=UTC))
    if to_date:
        query = query.filter(models.LeaveRequest.starts_at < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC))
    query = query.order_by(models.LeaveRequest.starts_at.desc(), models.LeaveRequest.id.asc())
    rows, total = _paginate(query, page=page_number, page_size=page_size)
    return page([serialize_leave_request(db, row) for row in rows], page_number=page_number, page_size=page_size, total=total)


def create_leave_request(
    db: Session,
    *,
    amo_id: str,
    actor: account_models.User,
    payload: schemas.LeaveRequestCreate,
) -> models.LeaveRequest:
    target_user_id = payload.user_id or actor.id
    if target_user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.LEAVE_REVIEW):
        raise ValueError("You may only create your own leave request")
    _require_user(db, amo_id=amo_id, user_id=target_user_id, active_only=True)
    leave_type = db.query(models.LeaveType).filter(models.LeaveType.amo_id == amo_id, models.LeaveType.id == payload.leave_type_id, models.LeaveType.is_active.is_(True)).first()
    if not leave_type:
        raise ValueError("Active leave type not found")
    if leave_type.requires_attachment and not payload.attachment_reference:
        raise ValueError("This leave type requires an attachment")
    requested = _requested_minutes(
        db,
        amo_id=amo_id,
        user_id=target_user_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        explicit=payload.requested_minutes,
    )
    overlap = _leave_query(db, amo_id=amo_id).filter(
        models.LeaveRequest.user_id == target_user_id,
        models.LeaveRequest.status.notin_([models.LeaveRequestStatus.REJECTED, models.LeaveRequestStatus.CANCELLED, models.LeaveRequestStatus.RECALLED]),
        models.LeaveRequest.starts_at < payload.ends_at,
        models.LeaveRequest.ends_at > payload.starts_at,
    ).first()
    if overlap:
        raise ValueError(f"Leave request overlaps existing request {overlap.id}")
    row = models.LeaveRequest(
        amo_id=amo_id,
        user_id=target_user_id,
        leave_type_id=payload.leave_type_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        requested_minutes=requested,
        reason=payload.reason,
        attachment_reference=payload.attachment_reference,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="create", after={"user_id": target_user_id, "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "requested_minutes": requested})
    return row


def update_leave_request(db: Session, *, row: models.LeaveRequest, actor: account_models.User, payload: schemas.LeaveRequestUpdate) -> models.LeaveRequest:
    if row.status != models.LeaveRequestStatus.DRAFT:
        raise ValueError("Only draft leave requests can be edited")
    if row.user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.LEAVE_REVIEW):
        raise ValueError("Leave request edit denied")
    before = {"starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "requested_minutes": row.requested_minutes}
    for key, value in _dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    if row.ends_at <= row.starts_at:
        raise ValueError("ends_at must be after starts_at")
    if "requested_minutes" not in _model_fields_set(payload):
        row.requested_minutes = _requested_minutes(
            db,
            amo_id=row.amo_id,
            user_id=row.user_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            explicit=None,
        )
    if row.leave_type.requires_attachment and not row.attachment_reference:
        raise ValueError("This leave type requires an attachment")
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="update", before=before, after={"starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "requested_minutes": row.requested_minutes})
    return row


def submit_leave_request(db: Session, *, row: models.LeaveRequest, actor: account_models.User) -> models.LeaveRequest:
    if row.status != models.LeaveRequestStatus.DRAFT:
        raise ValueError("Only draft leave requests can be submitted")
    if row.user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.LEAVE_REVIEW):
        raise ValueError("Leave request submit denied")
    balance = _leave_balance(db, request=row, create=True)
    if row.leave_type.deducts_balance:
        available = _balance_available(balance)
        if available < row.requested_minutes and not row.leave_type.allow_negative_balance:
            raise ValueError(f"Insufficient leave balance: {available} minutes available")
        balance.pending_minutes += row.requested_minutes
        balance.updated_by_user_id = actor.id
        db.add(balance)
    row.status = models.LeaveRequestStatus.SUBMITTED
    row.submitted_at = _utcnow()
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="submit", after={"status": _enum_value(row.status), "pending_minutes": row.requested_minutes})
    supervisor = active_contract_for_user(db, amo_id=row.amo_id, user_id=row.user_id, on_date=row.starts_at.date())
    supervisor_user = getattr(supervisor, "supervisor", None)
    _send_email(
        db,
        amo_id=row.amo_id,
        recipient=getattr(supervisor_user, "email", None),
        template_key="workforce.leave.submitted",
        subject=f"Leave request submitted by {row.user.full_name}",
        context={"request_id": row.id, "employee": row.user.full_name, "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat()},
        correlation_id=f"leave:{row.id}:submitted",
    )
    return row


def _record_leave_decision(
    db: Session,
    *,
    row: models.LeaveRequest,
    actor: account_models.User,
    stage: models.LeaveApprovalStage,
    decision: models.ApprovalDecision,
    comment: Optional[str],
) -> None:
    existing = db.query(models.LeaveRequestApproval).filter(
        models.LeaveRequestApproval.leave_request_id == row.id,
        models.LeaveRequestApproval.stage == stage,
    ).first()
    if existing:
        existing.decision = decision
        existing.actor_user_id = actor.id
        existing.comment = comment
        existing.decided_at = _utcnow()
        db.add(existing)
    else:
        db.add(models.LeaveRequestApproval(
            amo_id=row.amo_id,
            leave_request_id=row.id,
            stage=stage,
            decision=decision,
            actor_user_id=actor.id,
            comment=comment,
        ))


def supervisor_approve_leave(db: Session, *, row: models.LeaveRequest, actor: account_models.User, comment: Optional[str]) -> models.LeaveRequest:
    if row.status != models.LeaveRequestStatus.SUBMITTED:
        raise ValueError("Only submitted leave can receive supervisor approval")
    if row.user_id == actor.id:
        raise ValueError("Employees cannot approve their own leave")
    contract = active_contract_for_user(db, amo_id=row.amo_id, user_id=row.user_id, on_date=row.starts_at.date())
    if contract and contract.supervisor_user_id and contract.supervisor_user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.LEAVE_APPROVE):
        raise ValueError("Only the assigned supervisor or HR may approve this request")
    _record_leave_decision(db, row=row, actor=actor, stage=models.LeaveApprovalStage.SUPERVISOR, decision=models.ApprovalDecision.APPROVED, comment=comment)
    row.status = models.LeaveRequestStatus.SUPERVISOR_APPROVED
    row.supervisor_approved_at = _utcnow()
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="supervisor_approve", after={"status": _enum_value(row.status)})
    return row


def hr_approve_leave(db: Session, *, row: models.LeaveRequest, actor: account_models.User, comment: Optional[str]) -> models.LeaveRequest:
    allowed = {models.LeaveRequestStatus.SUBMITTED, models.LeaveRequestStatus.SUPERVISOR_APPROVED}
    if row.status not in allowed:
        raise ValueError("Leave is not ready for HR approval")
    if row.leave_type.supervisor_approval_required and row.status != models.LeaveRequestStatus.SUPERVISOR_APPROVED:
        raise ValueError("Supervisor approval is required before HR approval")
    if row.user_id == actor.id:
        raise ValueError("Employees cannot approve their own leave")
    _record_leave_decision(db, row=row, actor=actor, stage=models.LeaveApprovalStage.HR, decision=models.ApprovalDecision.APPROVED, comment=comment)
    balance = _leave_balance(db, request=row, create=True)
    if row.leave_type.deducts_balance:
        balance.pending_minutes = max(balance.pending_minutes - row.requested_minutes, 0)
        balance.used_minutes += row.requested_minutes
        balance.updated_by_user_id = actor.id
        db.add(balance)
    event = db.query(models.EmployeeAvailabilityEvent).filter(
        models.EmployeeAvailabilityEvent.amo_id == row.amo_id,
        models.EmployeeAvailabilityEvent.source_type == "LEAVE_REQUEST",
        models.EmployeeAvailabilityEvent.source_id == row.id,
    ).first()
    if not event:
        event = models.EmployeeAvailabilityEvent(
            amo_id=row.amo_id,
            user_id=row.user_id,
            availability_type=row.leave_type.availability_type,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            blocking=True,
            provisional=False,
            source_type="LEAVE_REQUEST",
            source_id=row.id,
            reason=row.reason,
            metadata_json={"leave_type_id": row.leave_type_id, "leave_request_id": row.id},
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        db.add(event)
    row.status = models.LeaveRequestStatus.HR_APPROVED
    row.hr_approved_at = _utcnow()
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    conflicts = _published_roster_conflicts(db, request=row)
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="hr_approve", after={"status": _enum_value(row.status), "published_roster_conflicts": conflicts}, critical=True)
    _send_email(
        db,
        amo_id=row.amo_id,
        recipient=getattr(row.user, "email", None),
        template_key="workforce.leave.approved",
        subject="Your leave request was approved",
        context={"request_id": row.id, "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "roster_amendment_required": bool(conflicts)},
        correlation_id=f"leave:{row.id}:approved",
    )
    return row


def reject_leave(db: Session, *, row: models.LeaveRequest, actor: account_models.User, reason: Optional[str]) -> models.LeaveRequest:
    if row.status in {models.LeaveRequestStatus.HR_APPROVED, models.LeaveRequestStatus.REJECTED, models.LeaveRequestStatus.CANCELLED, models.LeaveRequestStatus.RECALLED}:
        raise ValueError("Leave request cannot be rejected in its current state")
    stage = models.LeaveApprovalStage.HR if permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.LEAVE_APPROVE) else models.LeaveApprovalStage.SUPERVISOR
    _record_leave_decision(db, row=row, actor=actor, stage=stage, decision=models.ApprovalDecision.REJECTED, comment=reason)
    if row.status != models.LeaveRequestStatus.DRAFT and row.leave_type.deducts_balance:
        balance = _leave_balance(db, request=row)
        if balance:
            balance.pending_minutes = max(balance.pending_minutes - row.requested_minutes, 0)
            balance.updated_by_user_id = actor.id
            db.add(balance)
    row.status = models.LeaveRequestStatus.REJECTED
    row.rejected_at = _utcnow()
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="reject", after={"status": _enum_value(row.status), "reason": reason})
    _send_email(db, amo_id=row.amo_id, recipient=getattr(row.user, "email", None), template_key="workforce.leave.rejected", subject="Your leave request was rejected", context={"request_id": row.id, "reason": reason}, correlation_id=f"leave:{row.id}:rejected")
    return row


def cancel_leave(db: Session, *, row: models.LeaveRequest, actor: account_models.User, reason: Optional[str]) -> models.LeaveRequest:
    if row.user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.LEAVE_APPROVE):
        raise ValueError("Leave cancellation denied")
    if row.status in {models.LeaveRequestStatus.REJECTED, models.LeaveRequestStatus.CANCELLED, models.LeaveRequestStatus.RECALLED}:
        return row
    balance = _leave_balance(db, request=row)
    if balance and row.leave_type.deducts_balance:
        if row.status == models.LeaveRequestStatus.HR_APPROVED:
            balance.used_minutes = max(balance.used_minutes - row.requested_minutes, 0)
        elif row.status != models.LeaveRequestStatus.DRAFT:
            balance.pending_minutes = max(balance.pending_minutes - row.requested_minutes, 0)
        balance.updated_by_user_id = actor.id
        db.add(balance)
    event = db.query(models.EmployeeAvailabilityEvent).filter(
        models.EmployeeAvailabilityEvent.amo_id == row.amo_id,
        models.EmployeeAvailabilityEvent.source_type == "LEAVE_REQUEST",
        models.EmployeeAvailabilityEvent.source_id == row.id,
    ).first()
    if event:
        db.delete(event)
    row.status = models.LeaveRequestStatus.CANCELLED
    row.cancelled_at = _utcnow()
    row.updated_by_user_id = actor.id
    if reason:
        row.reason = f"{row.reason or ''}\nCancellation: {reason}".strip()
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="LeaveRequest", entity_id=row.id, action="cancel", after={"status": _enum_value(row.status), "reason": reason})
    return row


def serialize_availability(row: models.EmployeeAvailabilityEvent) -> schemas.AvailabilityEventRead:
    return schemas.AvailabilityEventRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        user_full_name=getattr(row.user, "full_name", None),
        availability_type=row.availability_type,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        blocking=row.blocking,
        provisional=row.provisional,
        source_type=row.source_type,
        source_id=row.source_id,
        reason=row.reason,
        metadata_json=row.metadata_json,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_availability(
    db: Session,
    *,
    amo_id: str,
    from_dt: datetime,
    to_dt: datetime,
    user_id: Optional[str] = None,
    blocking: Optional[bool] = None,
) -> list[schemas.AvailabilityEventRead]:
    query = db.query(models.EmployeeAvailabilityEvent).options(selectinload(models.EmployeeAvailabilityEvent.user)).filter(
        models.EmployeeAvailabilityEvent.amo_id == amo_id,
        models.EmployeeAvailabilityEvent.starts_at < to_dt,
        models.EmployeeAvailabilityEvent.ends_at > from_dt,
    )
    if user_id:
        query = query.filter(models.EmployeeAvailabilityEvent.user_id == user_id)
    if blocking is not None:
        query = query.filter(models.EmployeeAvailabilityEvent.blocking.is_(blocking))
    rows = query.order_by(models.EmployeeAvailabilityEvent.starts_at.asc(), models.EmployeeAvailabilityEvent.user_id.asc(), models.EmployeeAvailabilityEvent.id.asc()).all()
    return [serialize_availability(row) for row in rows]


def create_availability(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.AvailabilityEventCreate) -> models.EmployeeAvailabilityEvent:
    _require_user(db, amo_id=amo_id, user_id=payload.user_id)
    source_id = payload.source_id or generate_source_id("availability", payload.user_id, payload.starts_at)
    row = models.EmployeeAvailabilityEvent(
        amo_id=amo_id,
        **{**_dump(payload), "source_id": source_id},
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="EmployeeAvailabilityEvent", entity_id=row.id, action="create", after={"user_id": row.user_id, "type": _enum_value(row.availability_type), "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat()})
    return row


def generate_source_id(prefix: str, user_id: str, at: datetime) -> str:
    return f"{prefix}:{user_id}:{int(calculations.ensure_aware(at).timestamp())}"


def update_availability(db: Session, *, row: models.EmployeeAvailabilityEvent, actor_user_id: str, payload: schemas.AvailabilityEventUpdate) -> models.EmployeeAvailabilityEvent:
    if row.source_type == "LEAVE_REQUEST":
        raise ValueError("Leave-projected availability must be changed through the leave workflow")
    before = {"type": _enum_value(row.availability_type), "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "blocking": row.blocking}
    for key, value in _dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    if row.ends_at <= row.starts_at:
        raise ValueError("ends_at must be after starts_at")
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="EmployeeAvailabilityEvent", entity_id=row.id, action="update", before=before, after={"type": _enum_value(row.availability_type), "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "blocking": row.blocking})
    return row


def delete_availability(db: Session, *, row: models.EmployeeAvailabilityEvent, actor_user_id: str) -> None:
    if row.source_type == "LEAVE_REQUEST":
        raise ValueError("Leave-projected availability must be removed through leave cancellation")
    snapshot = {"user_id": row.user_id, "type": _enum_value(row.availability_type), "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat()}
    db.delete(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="EmployeeAvailabilityEvent", entity_id=row.id, action="delete", before=snapshot)


# ---------------------------------------------------------------------------
# Public holidays
# ---------------------------------------------------------------------------


def list_public_holidays(db: Session, *, amo_id: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[schemas.PublicHolidayRead]:
    query = db.query(models.PublicHoliday).options(selectinload(models.PublicHoliday.calendar)).filter(models.PublicHoliday.amo_id == amo_id)
    if from_date:
        query = query.filter(models.PublicHoliday.holiday_date >= from_date)
    if to_date:
        query = query.filter(models.PublicHoliday.holiday_date <= to_date)
    rows = query.order_by(models.PublicHoliday.holiday_date.asc(), models.PublicHoliday.name.asc()).all()
    return [schemas.PublicHolidayRead(
        id=row.id,
        amo_id=row.amo_id,
        calendar_id=row.calendar_id,
        holiday_date=row.holiday_date,
        name=row.name,
        paid=row.paid,
        metadata_json=row.metadata_json,
        calendar_code=getattr(row.calendar, "code", None),
        calendar_name=getattr(row.calendar, "name", None),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    ) for row in rows]


def create_holiday_calendar(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.PublicHolidayCalendarCreate) -> models.PublicHolidayCalendar:
    calculations.get_zone(payload.timezone_name)
    row = models.PublicHolidayCalendar(amo_id=amo_id, **_dump(payload), created_by_user_id=actor_user_id)
    row.code = row.code.strip().upper()
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="PublicHolidayCalendar", entity_id=row.id, action="create", after={"code": row.code, "name": row.name})
    return row


def create_public_holiday(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.PublicHolidayCreate) -> models.PublicHoliday:
    calendar = db.query(models.PublicHolidayCalendar).filter(models.PublicHolidayCalendar.amo_id == amo_id, models.PublicHolidayCalendar.id == payload.calendar_id).first()
    if not calendar:
        raise ValueError("Public holiday calendar not found")
    row = models.PublicHoliday(amo_id=amo_id, **_dump(payload), created_by_user_id=actor_user_id)
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="PublicHoliday", entity_id=row.id, action="create", after={"date": row.holiday_date.isoformat(), "name": row.name})
    return row


# ---------------------------------------------------------------------------
# Attendance, timesheets and payroll
# ---------------------------------------------------------------------------


def serialize_attendance(row: models.AttendanceEvent) -> schemas.AttendanceEventRead:
    return schemas.AttendanceEventRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        user_full_name=getattr(row.user, "full_name", None),
        event_type=row.event_type,
        occurred_at=row.occurred_at,
        source=row.source,
        base_station_id=row.base_station_id,
        roster_assignment_id=row.roster_assignment_id,
        idempotency_key=row.idempotency_key,
        note=row.note,
        metadata_json=row.metadata_json,
        recorded_by_user_id=row.recorded_by_user_id,
        created_at=row.created_at,
    )


def _attendance_state(event_type: Optional[models.AttendanceEventType]) -> str:
    if event_type is None or event_type == models.AttendanceEventType.CLOCK_OUT:
        return "CLOCKED_OUT"
    if event_type == models.AttendanceEventType.BREAK_START:
        return "ON_BREAK"
    return "WORKING"


def _validate_attendance_transition(*, state: str, event_type: models.AttendanceEventType) -> None:
    allowed = {
        "CLOCKED_OUT": {models.AttendanceEventType.CLOCK_IN},
        "WORKING": {models.AttendanceEventType.BREAK_START, models.AttendanceEventType.CLOCK_OUT},
        "ON_BREAK": {models.AttendanceEventType.BREAK_END, models.AttendanceEventType.CLOCK_OUT},
    }
    if event_type not in allowed.get(state, set()):
        expected = ", ".join(sorted(item.value for item in allowed.get(state, set()))) or "a manager correction"
        raise ValueError(
            f"{event_type.value.replace('_', ' ').title()} is not valid while attendance is "
            f"{state.replace('_', ' ').lower()}. Expected: {expected}."
        )


def _open_attendance_started_at(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    latest: Optional[models.AttendanceEvent],
) -> Optional[datetime]:
    if latest is None or _attendance_state(latest.event_type) == "CLOCKED_OUT":
        return None
    clock_in = db.query(models.AttendanceEvent).filter(
        models.AttendanceEvent.amo_id == amo_id,
        models.AttendanceEvent.user_id == user_id,
        models.AttendanceEvent.event_type == models.AttendanceEventType.CLOCK_IN,
        models.AttendanceEvent.occurred_at <= latest.occurred_at,
    ).order_by(models.AttendanceEvent.occurred_at.desc(), models.AttendanceEvent.id.desc()).first()
    return calculations.ensure_aware(clock_in.occurred_at) if clock_in else None


def create_attendance_event(db: Session, *, amo_id: str, actor: account_models.User, payload: schemas.AttendanceEventCreate) -> models.AttendanceEvent:
    user_id = payload.user_id or actor.id
    if user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.ATTENDANCE_MANAGE):
        raise ValueError("Attendance capture for another user is denied")
    # Serialize live attendance changes per employee. This prevents two browser
    # tabs from both accepting an action against the same previous state.
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
    ).with_for_update().first()
    if not user or getattr(user, "is_system_account", False):
        raise ValueError("Active user not found in AMO scope")
    existing = db.query(models.AttendanceEvent).filter(models.AttendanceEvent.amo_id == amo_id, models.AttendanceEvent.idempotency_key == payload.idempotency_key).first()
    if existing:
        return existing

    occurred_at = calculations.ensure_aware(payload.occurred_at).astimezone(UTC)
    metadata_json = dict(payload.metadata_json or {})
    note = payload.note
    source = (payload.source or "MANUAL").strip().upper()
    self_service = source == "SELF_SERVICE"
    can_manage_attendance = permissions.has_permission(
        db,
        user=actor,
        permission=permissions.PermissionCode.ATTENDANCE_MANAGE,
    )
    if not self_service and not can_manage_attendance:
        raise ValueError("Manual attendance capture requires a supervisor")
    if self_service and user_id != actor.id:
        raise ValueError("Self-service attendance can only be recorded for the signed-in user")

    roster_assignment = None
    if payload.roster_assignment_id:
        from ..rostering import models as roster_models
        roster_assignment = db.query(roster_models.RosterAssignment).filter(
            roster_models.RosterAssignment.amo_id == amo_id,
            roster_models.RosterAssignment.id == payload.roster_assignment_id,
            roster_models.RosterAssignment.user_id == user_id,
        ).first()
        if not roster_assignment:
            raise ValueError("Roster assignment does not belong to this employee")

    resolved_base_station_id = payload.base_station_id or getattr(roster_assignment, "base_station_id", None)
    if not resolved_base_station_id:
        contract = active_contract_for_user(
            db,
            amo_id=amo_id,
            user_id=user_id,
            on_date=occurred_at.date(),
        )
        resolved_base_station_id = getattr(contract, "primary_base_station_id", None)
    base_station = _require_base(db, amo_id=amo_id, base_station_id=resolved_base_station_id)

    if self_service and payload.event_type in {
        models.AttendanceEventType.CLOCK_IN,
        models.AttendanceEventType.CLOCK_OUT,
    }:
        if base_station is None:
            metadata_json.update({
                "location_state": "NO_ASSIGNED_BASE",
                "requires_review": True,
                "review_reason": "No effective duty or contract base was available for location verification",
            })
        elif payload.location_latitude is not None:
            evaluation = foundation_services.evaluate_location(
                db,
                amo_id=amo_id,
                payload=foundation_schemas.LocationEvaluationRequest(
                    latitude=payload.location_latitude,
                    longitude=payload.location_longitude,
                    accuracy_m=payload.location_accuracy_m,
                    base_station_id=base_station.id,
                ),
            )
            location_state = (
                "INSIDE"
                if evaluation.inside_geofence
                else "LOW_CONFIDENCE"
                if evaluation.location_confidence == "LOW"
                else "OUTSIDE"
            )
            metadata_json.update({
                "location_state": location_state,
                "location_checked_at": occurred_at.isoformat(),
                "location_confidence": evaluation.location_confidence,
                "location_distance_m": evaluation.distance_m,
                "location_geofence_radius_m": evaluation.geofence_radius_m,
                "location_base_code": evaluation.base_code,
            })
            if not evaluation.inside_geofence or evaluation.location_confidence == "LOW":
                metadata_json.update({
                    "requires_review": True,
                    "review_reason": evaluation.review_reason
                    or "Attendance was recorded outside the approved base geofence or with low-confidence location evidence",
                    "location_exception_reason": payload.location_exception_reason,
                })
        elif (
            base_station.checkin_prompt_enabled
            or base_station.checkout_reminder_enabled
            or base_station.suspicious_location_review_enabled
        ):
            metadata_json.update({
                "location_state": "UNVERIFIED",
                "requires_review": True,
                "review_reason": "Device location was unavailable while attendance location policy was enabled",
                "location_exception_reason": payload.location_exception_reason,
            })

    if payload.event_type == models.AttendanceEventType.MANUAL_ADJUSTMENT and roster_assignment is not None:
        # Attribute the correction to the affected duty day while preserving
        # the actual audit timestamp in AttendanceEvent.created_at.
        occurred_at = calculations.ensure_aware(roster_assignment.ends_at).astimezone(UTC) - timedelta(seconds=1)

    if self_service:
        now = _utcnow()
        if occurred_at > now + ATTENDANCE_SELF_SERVICE_FUTURE_LIMIT:
            raise ValueError("Attendance time cannot be more than 5 minutes in the future")
        if occurred_at < now - ATTENDANCE_SELF_SERVICE_BACKDATE_LIMIT:
            resilient_capture = metadata_json.get("client_capture_mode") == "RESILIENT_DEVICE"
            if not resilient_capture or occurred_at < now - ATTENDANCE_RESILIENT_CAPTURE_LIMIT:
                raise ValueError("Self-service attendance is too old to replay safely; ask a supervisor for a correction")
            metadata_json.update({
                "requires_review": True,
                "review_reason": "Attendance was captured during an outage and replayed outside the normal 15-minute window",
                "offline_replayed_at": now.isoformat(),
                "offline_delay_minutes": int((now - occurred_at).total_seconds() // 60),
            })
        if payload.event_type == models.AttendanceEventType.MANUAL_ADJUSTMENT:
            raise ValueError("Manual attendance adjustments require a supervisor")

        latest = db.query(models.AttendanceEvent).filter(
            models.AttendanceEvent.amo_id == amo_id,
            models.AttendanceEvent.user_id == user_id,
            models.AttendanceEvent.event_type != models.AttendanceEventType.MANUAL_ADJUSTMENT,
        ).order_by(models.AttendanceEvent.occurred_at.desc(), models.AttendanceEvent.id.desc()).first()
        state = _attendance_state(latest.event_type if latest else None)
        _validate_attendance_transition(state=state, event_type=payload.event_type)
        open_since = _open_attendance_started_at(
            db,
            amo_id=amo_id,
            user_id=user_id,
            latest=latest,
        )
        if open_since and occurred_at - open_since > ATTENDANCE_MAX_OPEN_SESSION:
            if payload.event_type != models.AttendanceEventType.CLOCK_OUT:
                raise ValueError("This attendance session is over 18 hours old. Clock out to close it for supervisor review")
            attempted_at = occurred_at
            occurred_at = open_since + ATTENDANCE_MAX_OPEN_SESSION
            metadata_json.update({
                "requires_review": True,
                "review_reason": "Stale attendance session was capped at 18 hours and requires supervisor review",
                "actual_clock_out_attempted_at": attempted_at.isoformat(),
                "session_cap_minutes": int(ATTENDANCE_MAX_OPEN_SESSION.total_seconds() // 60),
            })
            note = note or "System-capped stale self-service session; supervisor correction required"

    row = models.AttendanceEvent(
        amo_id=amo_id,
        user_id=user_id,
        event_type=payload.event_type,
        occurred_at=occurred_at,
        source=source,
        base_station_id=resolved_base_station_id,
        roster_assignment_id=payload.roster_assignment_id,
        idempotency_key=payload.idempotency_key,
        note=note,
        metadata_json=metadata_json or None,
        recorded_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    if payload.event_type == models.AttendanceEventType.MANUAL_ADJUSTMENT:
        if not note or len(note.strip()) < 8:
            raise ValueError("Manual attendance adjustment requires an audited reason of at least 8 characters")
        try:
            adjustment_minutes = int(metadata_json.get("minutes", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Manual attendance adjustment requires a whole-minute value") from exc
        if adjustment_minutes == 0 or abs(adjustment_minutes) > 1_440:
            raise ValueError("Manual attendance adjustment must be between -1440 and 1440 minutes and cannot be zero")
        variance_id = metadata_json.get("variance_id")
        if variance_id:
            variance = db.query(models.RosterActualVariance).filter(
                models.RosterActualVariance.amo_id == amo_id,
                models.RosterActualVariance.id == str(variance_id),
                models.RosterActualVariance.user_id == user_id,
            ).with_for_update().first()
            if not variance:
                raise ValueError("Attendance variance is no longer available for correction")
            variance.attendance_minutes = max(variance.attendance_minutes + adjustment_minutes, 0)
            variance.variance_minutes = variance.attendance_minutes - variance.planned_minutes
            variance.classification = "MATCHED" if abs(variance.variance_minutes) < 30 else "VARIANCE"
            variance.calculated_at = _utcnow()
            variance.metadata_json = {
                **(variance.metadata_json or {}),
                "last_correction_event_id": row.id,
                "last_correction_minutes": adjustment_minutes,
                "last_correction_reason": note.strip(),
                "last_corrected_by_user_id": actor.id,
            }
            db.add(variance)
    _audit(db, amo_id=amo_id, actor_user_id=actor.id, entity_type="AttendanceEvent", entity_id=row.id, action="create", after={"user_id": user_id, "event_type": _enum_value(row.event_type), "occurred_at": row.occurred_at.isoformat()})
    return row


def attendance_summary(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    from_date: date,
    to_date: date,
    timezone_name: str,
) -> schemas.AttendanceSummaryRead:
    start_dt, end_dt = calculations.period_bounds_utc(from_date, to_date, timezone_name)
    user = _require_user(db, amo_id=amo_id, user_id=user_id)
    events = db.query(models.AttendanceEvent).options(selectinload(models.AttendanceEvent.user)).filter(
        models.AttendanceEvent.amo_id == amo_id,
        models.AttendanceEvent.user_id == user_id,
        models.AttendanceEvent.occurred_at >= start_dt,
        models.AttendanceEvent.occurred_at < end_dt,
    ).order_by(models.AttendanceEvent.occurred_at.asc(), models.AttendanceEvent.id.asc()).all()
    totals = calculations.calculate_attendance_totals(events, window_start=start_dt, window_end=end_dt)
    latest = db.query(models.AttendanceEvent).filter(
        models.AttendanceEvent.amo_id == amo_id,
        models.AttendanceEvent.user_id == user_id,
        models.AttendanceEvent.event_type != models.AttendanceEventType.MANUAL_ADJUSTMENT,
    ).order_by(models.AttendanceEvent.occurred_at.desc(), models.AttendanceEvent.id.desc()).first()
    current_state = _attendance_state(latest.event_type if latest else None)
    current_since = _open_attendance_started_at(
        db,
        amo_id=amo_id,
        user_id=user_id,
        latest=latest,
    )
    current_minutes = calculations.duration_minutes(current_since, _utcnow()) if current_since else 0
    if current_since and _utcnow() - current_since > ATTENDANCE_MAX_OPEN_SESSION:
        current_state = "STALE_OPEN"
    review_count = sum(1 for event in events if (event.metadata_json or {}).get("requires_review"))
    warnings = list(totals.warnings)
    review_reasons = {
        str((event.metadata_json or {}).get("review_reason") or "").strip()
        for event in events
        if (event.metadata_json or {}).get("requires_review")
    }
    warnings.extend(sorted(reason for reason in review_reasons if reason))
    if current_state == "STALE_OPEN":
        warnings.insert(0, "Open attendance session is over 18 hours old; clock out to cap it and request supervisor correction")
    return schemas.AttendanceSummaryRead(
        user_id=user_id,
        user_full_name=user.full_name,
        from_date=from_date,
        to_date=to_date,
        presence_minutes=totals.presence_minutes,
        break_minutes=totals.break_minutes,
        paid_minutes=totals.paid_minutes,
        incomplete=totals.incomplete,
        current_state=current_state,
        current_since=current_since,
        current_session_minutes=current_minutes,
        requires_review_count=review_count,
        warnings=warnings,
        events=[serialize_attendance(row) for row in events],
    )


def reconcile_open_attendance_sessions(
    db: Session,
    *,
    now: Optional[datetime] = None,
    limit: int = 200,
) -> dict[str, int]:
    """Remind for overdue rostered sessions and safely close abandoned sessions.

    A browser session or logout is never treated as payroll evidence. Automatic
    closure is a bounded safety fallback and always creates a review-required
    attendance event for a supervisor to confirm or correct.
    """
    current = calculations.ensure_aware(now or _utcnow()).astimezone(UTC)
    latest_times = db.query(
        models.AttendanceEvent.amo_id.label("amo_id"),
        models.AttendanceEvent.user_id.label("user_id"),
        func.max(models.AttendanceEvent.occurred_at).label("occurred_at"),
    ).filter(
        models.AttendanceEvent.event_type != models.AttendanceEventType.MANUAL_ADJUSTMENT,
    ).group_by(
        models.AttendanceEvent.amo_id,
        models.AttendanceEvent.user_id,
    ).subquery()
    latest_rows = db.query(models.AttendanceEvent).options(
        selectinload(models.AttendanceEvent.user),
    ).join(
        latest_times,
        and_(
            latest_times.c.amo_id == models.AttendanceEvent.amo_id,
            latest_times.c.user_id == models.AttendanceEvent.user_id,
            latest_times.c.occurred_at == models.AttendanceEvent.occurred_at,
        ),
    ).filter(
        models.AttendanceEvent.event_type.in_([
            models.AttendanceEventType.CLOCK_IN,
            models.AttendanceEventType.BREAK_START,
            models.AttendanceEventType.BREAK_END,
        ]),
    ).order_by(models.AttendanceEvent.occurred_at.asc()).limit(max(1, min(limit, 1000))).all()

    from ..rostering import models as roster_models

    amo_zones: dict[str, ZoneInfo] = {}
    reminded = 0
    closed = 0
    seen_users: set[tuple[str, str]] = set()
    for latest in latest_rows:
        user_key = (str(latest.amo_id), str(latest.user_id))
        if user_key in seen_users:
            continue
        seen_users.add(user_key)
        # Dedicated workforce workers run concurrently. Claim the same user
        # row used by live clock events so only one worker may remind or close
        # an attendance session, while peers skip it without waiting.
        user_claim = db.query(account_models.User.id).filter(
            account_models.User.amo_id == latest.amo_id,
            account_models.User.id == latest.user_id,
        )
        if db.get_bind().dialect.name == "postgresql":
            user_claim = user_claim.with_for_update(skip_locked=True)
        else:
            user_claim = user_claim.with_for_update()
        if user_claim.first() is None:
            continue
        open_since = _open_attendance_started_at(
            db,
            amo_id=latest.amo_id,
            user_id=latest.user_id,
            latest=latest,
        )
        if not open_since:
            continue
        clock_in = db.query(models.AttendanceEvent).filter(
            models.AttendanceEvent.amo_id == latest.amo_id,
            models.AttendanceEvent.user_id == latest.user_id,
            models.AttendanceEvent.event_type == models.AttendanceEventType.CLOCK_IN,
            models.AttendanceEvent.occurred_at == open_since,
        ).order_by(models.AttendanceEvent.id.desc()).first()
        if not clock_in:
            continue
        assignment_id = latest.roster_assignment_id or clock_in.roster_assignment_id
        assignment = None
        if assignment_id:
            assignment = db.query(roster_models.RosterAssignment).filter(
                roster_models.RosterAssignment.amo_id == latest.amo_id,
                roster_models.RosterAssignment.id == assignment_id,
                roster_models.RosterAssignment.user_id == latest.user_id,
                roster_models.RosterAssignment.deleted_at.is_(None),
            ).first()

        base_id = latest.base_station_id or clock_in.base_station_id or getattr(assignment, "base_station_id", None)
        base = _require_base(db, amo_id=latest.amo_id, base_station_id=base_id)
        clock_metadata = dict(clock_in.metadata_json or {})
        if (
            assignment is not None
            and calculations.ensure_aware(assignment.ends_at).astimezone(UTC) <= current
            and base is not None
            and base.checkout_reminder_enabled
            and not clock_metadata.get("checkout_reminder_sent_at")
        ):
            _send_email(
                db,
                amo_id=latest.amo_id,
                recipient=getattr(latest.user, "email", None),
                template_key="workforce.attendance.checkout_reminder",
                subject="Clock-out reminder",
                context={
                    "employee": getattr(latest.user, "full_name", None),
                    "assignment_id": assignment.id,
                    "shift_ended_at": assignment.ends_at.isoformat(),
                },
                correlation_id=f"attendance:{clock_in.id}:checkout-reminder",
            )
            clock_metadata["checkout_reminder_sent_at"] = current.isoformat()
            clock_in.metadata_json = clock_metadata
            db.add(clock_in)
            reminded += 1

        if latest.amo_id not in amo_zones:
            timezone_name = db.query(account_models.AMO.time_zone).filter(
                account_models.AMO.id == latest.amo_id,
            ).scalar() or "UTC"
            try:
                amo_zones[latest.amo_id] = ZoneInfo(str(timezone_name))
            except ZoneInfoNotFoundError:
                amo_zones[latest.amo_id] = ZoneInfo("UTC")
        zone = amo_zones[latest.amo_id]
        closing_reference = calculations.ensure_aware(
            assignment.ends_at if assignment is not None else open_since,
        ).astimezone(zone)
        local_midnight = datetime.combine(
            closing_reference.date() + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(UTC)
        safety_deadline = min(local_midnight, open_since + ATTENDANCE_MAX_OPEN_SESSION)
        if current < safety_deadline:
            continue

        idempotency_key = f"attendance:auto-close:{clock_in.id}"
        if db.query(models.AttendanceEvent.id).filter(
            models.AttendanceEvent.amo_id == latest.amo_id,
            models.AttendanceEvent.idempotency_key == idempotency_key,
        ).first():
            continue
        close_row = models.AttendanceEvent(
            amo_id=latest.amo_id,
            user_id=latest.user_id,
            event_type=models.AttendanceEventType.CLOCK_OUT,
            occurred_at=safety_deadline,
            source="SYSTEM_AUTO_CLOSE",
            base_station_id=base_id,
            roster_assignment_id=assignment_id,
            idempotency_key=idempotency_key,
            note="Automatically closed after the safe attendance deadline; supervisor confirmation required",
            metadata_json={
                "requires_review": True,
                "review_reason": "Open attendance session reached local midnight or the 18-hour safety limit",
                "open_event_id": clock_in.id,
                "auto_close_deadline": safety_deadline.isoformat(),
                "session_evidence": "Roster, attendance and configured base policy only; portal logout was not used as payroll evidence",
            },
            recorded_by_user_id=None,
        )
        db.add(close_row)
        db.flush()
        contract = active_contract_for_user(
            db,
            amo_id=latest.amo_id,
            user_id=latest.user_id,
            on_date=open_since.astimezone(zone).date(),
        )
        supervisor = getattr(contract, "supervisor", None)
        _send_email(
            db,
            amo_id=latest.amo_id,
            recipient=getattr(supervisor, "email", None),
            template_key="workforce.attendance.auto_closed",
            subject="Attendance session needs review",
            context={
                "employee": getattr(latest.user, "full_name", None),
                "attendance_event_id": close_row.id,
                "closed_at": safety_deadline.isoformat(),
            },
            correlation_id=f"attendance:{clock_in.id}:auto-close-review",
        )
        _audit(
            db,
            amo_id=latest.amo_id,
            actor_user_id=None,
            entity_type="AttendanceEvent",
            entity_id=close_row.id,
            action="system_auto_close",
            after={"user_id": latest.user_id, "occurred_at": safety_deadline.isoformat()},
            critical=True,
        )
        closed += 1
    return {"reminded": reminded, "closed": closed}


def attendance_export_csv(summary: schemas.AttendanceSummaryRead) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["employee", "event", "occurred_at", "source", "base_station_id", "roster_assignment_id", "requires_review", "note"])
    for event in summary.events:
        writer.writerow([
            event.user_full_name or event.user_id,
            _enum_value(event.event_type),
            event.occurred_at.isoformat(),
            event.source,
            event.base_station_id or "",
            event.roster_assignment_id or "",
            "yes" if (event.metadata_json or {}).get("requires_review") else "no",
            event.note or "",
        ])
    return output.getvalue()


def leave_requests_export_csv(rows: Sequence[schemas.LeaveRequestRead]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["employee", "staff_code", "leave_type", "starts_at", "ends_at", "requested_minutes", "status", "roster_conflicts", "reason"])
    for row in rows:
        writer.writerow([
            row.user_full_name or row.user_id,
            row.user_staff_code or "",
            row.leave_type_name or row.leave_type_code or row.leave_type_id,
            row.starts_at.isoformat(),
            row.ends_at.isoformat(),
            row.requested_minutes,
            _enum_value(row.status),
            len(row.published_roster_conflicts),
            row.reason or "",
        ])
    return output.getvalue()


def _timesheet_line_category(assignment: Any) -> models.TimesheetCategory:
    status = _enum_value(getattr(assignment, "status", "DUTY"))
    shift_kind = _enum_value(getattr(getattr(assignment, "shift_template", None), "kind", ""))
    if status == "STANDBY":
        return models.TimesheetCategory.STANDBY
    if status == "TRAINING":
        return models.TimesheetCategory.TRAINING
    if status == "TRAVEL":
        return models.TimesheetCategory.TRAVEL
    if status == "LEAVE":
        return models.TimesheetCategory.LEAVE
    if shift_kind == "NIGHT":
        return models.TimesheetCategory.NIGHT
    return models.TimesheetCategory.ORDINARY


def _published_assignments(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    start_dt: datetime,
    end_dt: datetime,
) -> list[Any]:
    from ..rostering import models as roster_models
    return db.query(roster_models.RosterAssignment).join(
        roster_models.RosterVersion,
        roster_models.RosterAssignment.version_id == roster_models.RosterVersion.id,
    ).options(selectinload(roster_models.RosterAssignment.shift_template)).filter(
        roster_models.RosterAssignment.amo_id == amo_id,
        roster_models.RosterAssignment.user_id == user_id,
        roster_models.RosterVersion.status == roster_models.RosterVersionStatus.PUBLISHED,
        roster_models.RosterAssignment.starts_at < end_dt,
        roster_models.RosterAssignment.ends_at > start_dt,
    ).order_by(roster_models.RosterAssignment.starts_at.asc(), roster_models.RosterAssignment.id.asc()).all()


def _daily_attendance_minutes(events: Sequence[models.AttendanceEvent], *, timezone_name: str) -> dict[date, int]:
    zone = calculations.get_zone(timezone_name)
    by_day: dict[date, list[models.AttendanceEvent]] = defaultdict(list)
    for event in events:
        by_day[calculations.ensure_aware(event.occurred_at).astimezone(zone).date()].append(event)
    return {day: calculations.calculate_attendance_totals(rows).paid_minutes for day, rows in by_day.items()}


def generate_timesheets(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.TimesheetGenerateRequest,
) -> list[models.Timesheet]:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    timezone_name = getattr(amo, "time_zone", None) or "UTC"
    start_dt, end_dt = calculations.period_bounds_utc(payload.period_start, payload.period_end, timezone_name)
    user_query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if payload.user_ids:
        user_query = user_query.filter(account_models.User.id.in_(payload.user_ids))
    users = user_query.order_by(account_models.User.full_name.asc(), account_models.User.id.asc()).all()
    output: list[models.Timesheet] = []

    for user in users:
        sheet = db.query(models.Timesheet).options(selectinload(models.Timesheet.lines)).filter(
            models.Timesheet.amo_id == amo_id,
            models.Timesheet.user_id == user.id,
            models.Timesheet.period_start == payload.period_start,
            models.Timesheet.period_end == payload.period_end,
        ).first()
        if sheet and sheet.status != models.TimesheetStatus.DRAFT:
            output.append(sheet)
            continue
        if sheet and payload.replace_draft:
            for line in list(sheet.lines or []):
                db.delete(line)
        elif not sheet:
            sheet = models.Timesheet(
                amo_id=amo_id,
                user_id=user.id,
                period_start=payload.period_start,
                period_end=payload.period_end,
                created_by_user_id=actor_user_id,
                updated_by_user_id=actor_user_id,
            )
            db.add(sheet)
            db.flush()

        assignments = _published_assignments(db, amo_id=amo_id, user_id=user.id, start_dt=start_dt, end_dt=end_dt)
        attendance_events = db.query(models.AttendanceEvent).filter(
            models.AttendanceEvent.amo_id == amo_id,
            models.AttendanceEvent.user_id == user.id,
            models.AttendanceEvent.occurred_at >= start_dt,
            models.AttendanceEvent.occurred_at < end_dt,
        ).order_by(models.AttendanceEvent.occurred_at.asc()).all()
        attendance_by_day = _daily_attendance_minutes(attendance_events, timezone_name=timezone_name)
        work_logs = db.query(work_models.WorkLogEntry).filter(
            work_models.WorkLogEntry.amo_id == amo_id,
            work_models.WorkLogEntry.user_id == user.id,
            work_models.WorkLogEntry.start_time < end_dt,
            work_models.WorkLogEntry.end_time > start_dt,
        ).order_by(work_models.WorkLogEntry.start_time.asc(), work_models.WorkLogEntry.id.asc()).all()

        assignment_by_day: dict[date, list[Any]] = defaultdict(list)
        zone = calculations.get_zone(timezone_name)
        for assignment in assignments:
            assignment_by_day[calculations.ensure_aware(assignment.starts_at).astimezone(zone).date()].append(assignment)
        planned_minutes = sum(int(getattr(row, "planned_minutes", None) or calculations.duration_minutes(row.starts_at, row.ends_at)) for row in assignments)
        attendance_minutes = sum(attendance_by_day.values())
        productive_minutes = sum(max(int(round(float(row.actual_hours or 0) * 60)), 0) for row in work_logs)

        all_days = sorted(set(attendance_by_day) | set(assignment_by_day))
        classified_total = 0
        for work_day in all_days:
            actual = attendance_by_day.get(work_day, 0)
            day_assignments = assignment_by_day.get(work_day, [])
            if day_assignments:
                primary = sorted(day_assignments, key=lambda row: (row.starts_at, row.id))[0]
                category = _timesheet_line_category(primary)
                roster_assignment_id = primary.id
            else:
                category = models.TimesheetCategory.OVERTIME if actual > 0 else models.TimesheetCategory.UNPAID_ABSENCE
                roster_assignment_id = None
            if actual == 0 and day_assignments:
                expected = sum(int(getattr(row, "planned_minutes", None) or calculations.duration_minutes(row.starts_at, row.ends_at)) for row in day_assignments)
                category = models.TimesheetCategory.UNPAID_ABSENCE
                actual = expected
            if actual <= 0:
                continue
            db.add(models.TimesheetLine(
                amo_id=amo_id,
                timesheet_id=sheet.id,
                work_date=work_day,
                category=category,
                minutes=actual,
                roster_assignment_id=roster_assignment_id,
                source="ATTENDANCE_ROSTER_RECONCILIATION",
                description="Attendance classified against the published duty roster",
            ))
            classified_total += actual

        overtime_minutes = max(attendance_minutes - planned_minutes, 0)
        if overtime_minutes > 0:
            db.add(models.TimesheetLine(
                amo_id=amo_id,
                timesheet_id=sheet.id,
                work_date=payload.period_end,
                category=models.TimesheetCategory.OVERTIME,
                minutes=overtime_minutes,
                source="CALCULATED_VARIANCE",
                description="Attendance above published planned duty minutes",
                metadata_json={"planned_minutes": planned_minutes, "attendance_minutes": attendance_minutes},
            ))
        sheet.planned_minutes = planned_minutes
        sheet.attendance_minutes = attendance_minutes
        sheet.productive_minutes = productive_minutes
        sheet.overtime_minutes = overtime_minutes
        sheet.variance_minutes = attendance_minutes - planned_minutes
        sheet.updated_by_user_id = actor_user_id
        db.add(sheet)
        db.flush()
        _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="Timesheet", entity_id=sheet.id, action="generate", after={"user_id": user.id, "planned_minutes": planned_minutes, "attendance_minutes": attendance_minutes, "productive_minutes": productive_minutes, "overtime_minutes": overtime_minutes})
        output.append(sheet)
    return output


def serialize_timesheet(row: models.Timesheet) -> schemas.TimesheetRead:
    contract = getattr(row, "_active_contract", None)
    return schemas.TimesheetRead(
        id=row.id,
        amo_id=row.amo_id,
        user_id=row.user_id,
        user_full_name=getattr(row.user, "full_name", None),
        payroll_number=getattr(contract, "payroll_number", None),
        period_start=row.period_start,
        period_end=row.period_end,
        status=row.status,
        planned_minutes=row.planned_minutes,
        attendance_minutes=row.attendance_minutes,
        productive_minutes=row.productive_minutes,
        overtime_minutes=row.overtime_minutes,
        variance_minutes=row.variance_minutes,
        lines=[schemas.TimesheetLineRead.model_validate(line) for line in sorted(row.lines or [], key=lambda item: (item.work_date, _enum_value(item.category), item.id))],
        submitted_at=row.submitted_at,
        supervisor_approved_at=row.supervisor_approved_at,
        hr_approved_at=row.hr_approved_at,
        exported_at=row.exported_at,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_timesheets(
    db: Session,
    *,
    amo_id: str,
    page_number: int,
    page_size: int,
    user_id: Optional[str] = None,
    sheet_status: Optional[models.TimesheetStatus] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> schemas.Page[schemas.TimesheetRead]:
    query = db.query(models.Timesheet).options(selectinload(models.Timesheet.user), selectinload(models.Timesheet.lines)).filter(models.Timesheet.amo_id == amo_id)
    if user_id:
        query = query.filter(models.Timesheet.user_id == user_id)
    if sheet_status:
        query = query.filter(models.Timesheet.status == sheet_status)
    if period_start:
        query = query.filter(models.Timesheet.period_end >= period_start)
    if period_end:
        query = query.filter(models.Timesheet.period_start <= period_end)
    query = query.order_by(models.Timesheet.period_start.desc(), models.Timesheet.user_id.asc(), models.Timesheet.id.asc())
    rows, total = _paginate(query, page=page_number, page_size=page_size)
    for row in rows:
        row._active_contract = active_contract_for_user(db, amo_id=amo_id, user_id=row.user_id, on_date=row.period_end)
    return page([serialize_timesheet(row) for row in rows], page_number=page_number, page_size=page_size, total=total)


def submit_timesheet(db: Session, *, row: models.Timesheet, actor: account_models.User) -> models.Timesheet:
    if row.status != models.TimesheetStatus.DRAFT:
        raise ValueError("Only draft timesheets can be submitted")
    if row.user_id != actor.id and not permissions.has_permission(db, user=actor, permission=permissions.PermissionCode.ATTENDANCE_MANAGE):
        raise ValueError("Timesheet submit denied")
    row.status = models.TimesheetStatus.SUBMITTED
    row.submitted_at = _utcnow()
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="Timesheet", entity_id=row.id, action="submit", after={"status": _enum_value(row.status)})
    return row


def approve_timesheet(db: Session, *, row: models.Timesheet, actor: account_models.User, payload: schemas.TimesheetApprovalRequest) -> models.Timesheet:
    if row.user_id == actor.id:
        raise ValueError("Users cannot approve their own timesheets")
    if payload.stage == models.LeaveApprovalStage.SUPERVISOR:
        if row.status != models.TimesheetStatus.SUBMITTED:
            raise ValueError("Timesheet must be submitted before supervisor approval")
        row.status = models.TimesheetStatus.SUPERVISOR_APPROVED
        row.supervisor_approved_at = _utcnow()
        action = "supervisor_approve"
    else:
        if row.status != models.TimesheetStatus.SUPERVISOR_APPROVED:
            raise ValueError("Supervisor approval is required before HR approval")
        row.status = models.TimesheetStatus.HR_APPROVED
        row.hr_approved_at = _utcnow()
        action = "hr_approve"
    row.updated_by_user_id = actor.id
    db.add(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor.id, entity_type="Timesheet", entity_id=row.id, action=action, after={"status": _enum_value(row.status), "comment": payload.comment}, critical=payload.stage == models.LeaveApprovalStage.HR)
    return row


def payroll_export_rows(db: Session, *, amo_id: str, period_start: Optional[date] = None, period_end: Optional[date] = None) -> list[schemas.PayrollExportRow]:
    query = db.query(models.Timesheet).options(selectinload(models.Timesheet.user), selectinload(models.Timesheet.lines)).filter(
        models.Timesheet.amo_id == amo_id,
        models.Timesheet.status == models.TimesheetStatus.HR_APPROVED,
    )
    if period_start:
        query = query.filter(models.Timesheet.period_end >= period_start)
    if period_end:
        query = query.filter(models.Timesheet.period_start <= period_end)
    rows = query.order_by(models.Timesheet.period_start.asc(), models.Timesheet.user_id.asc()).all()
    output: list[schemas.PayrollExportRow] = []
    for row in rows:
        totals: dict[str, int] = defaultdict(int)
        for line in row.lines or []:
            totals[_enum_value(line.category)] += int(line.minutes or 0)
        contract = active_contract_for_user(db, amo_id=amo_id, user_id=row.user_id, on_date=row.period_end)
        output.append(schemas.PayrollExportRow(
            timesheet_id=row.id,
            payroll_number=getattr(contract, "payroll_number", None),
            user_id=row.user_id,
            staff_code=getattr(row.user, "staff_code", None),
            full_name=getattr(row.user, "full_name", row.user_id),
            period_start=row.period_start,
            period_end=row.period_end,
            ordinary_minutes=totals[models.TimesheetCategory.ORDINARY.value],
            overtime_minutes=totals[models.TimesheetCategory.OVERTIME.value],
            night_minutes=totals[models.TimesheetCategory.NIGHT.value],
            weekend_minutes=totals[models.TimesheetCategory.WEEKEND.value],
            public_holiday_minutes=totals[models.TimesheetCategory.PUBLIC_HOLIDAY.value],
            standby_minutes=totals[models.TimesheetCategory.STANDBY.value],
            callout_minutes=totals[models.TimesheetCategory.CALLOUT.value],
            training_minutes=totals[models.TimesheetCategory.TRAINING.value],
            travel_minutes=totals[models.TimesheetCategory.TRAVEL.value],
            leave_minutes=totals[models.TimesheetCategory.LEAVE.value],
            unpaid_absence_minutes=totals[models.TimesheetCategory.UNPAID_ABSENCE.value],
            approved_at=row.hr_approved_at,
        ))
    return output


def payroll_export_csv(rows: Sequence[schemas.PayrollExportRow]) -> str:
    output = io.StringIO()
    fieldnames = list(schemas.PayrollExportRow.model_fields.keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        payload = row.model_dump(mode="json")
        writer.writerow(payload)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Explicit permissions and user preferences
# ---------------------------------------------------------------------------


def create_permission_grant(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.PermissionGrantCreate) -> models.WorkforcePermissionGrant:
    _require_user(db, amo_id=amo_id, user_id=payload.user_id)
    if payload.permission_code not in permissions.ALL_PERMISSIONS:
        raise ValueError("Unknown workforce permission code")
    if payload.department_id:
        exists = db.query(account_models.Department.id).filter(account_models.Department.amo_id == amo_id, account_models.Department.id == payload.department_id).first()
        if not exists:
            raise ValueError("Department not found in AMO scope")
    _require_base(db, amo_id=amo_id, base_station_id=payload.base_station_id)
    row = models.WorkforcePermissionGrant(amo_id=amo_id, **_dump(payload), granted_by_user_id=actor_user_id)
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="WorkforcePermissionGrant", entity_id=row.id, action="create", after={"user_id": row.user_id, "permission_code": row.permission_code, "effect": _enum_value(row.effect)}, critical=True)
    return row


def list_permission_grants(db: Session, *, amo_id: str, user_id: Optional[str] = None) -> list[models.WorkforcePermissionGrant]:
    query = db.query(models.WorkforcePermissionGrant).filter(models.WorkforcePermissionGrant.amo_id == amo_id)
    if user_id:
        query = query.filter(models.WorkforcePermissionGrant.user_id == user_id)
    return query.order_by(models.WorkforcePermissionGrant.user_id.asc(), models.WorkforcePermissionGrant.permission_code.asc(), models.WorkforcePermissionGrant.created_at.asc()).all()


def delete_permission_grant(db: Session, *, row: models.WorkforcePermissionGrant, actor_user_id: str) -> None:
    snapshot = {"user_id": row.user_id, "permission_code": row.permission_code, "effect": _enum_value(row.effect)}
    db.delete(row)
    db.flush()
    _audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="WorkforcePermissionGrant", entity_id=row.id, action="delete", before=snapshot, critical=True)


def get_or_create_planner_preference(db: Session, *, amo_id: str, user_id: str) -> models.PlannerPreference:
    row = db.query(models.PlannerPreference).filter(models.PlannerPreference.amo_id == amo_id, models.PlannerPreference.user_id == user_id).first()
    if not row:
        row = models.PlannerPreference(amo_id=amo_id, user_id=user_id)
        db.add(row)
        db.flush()
    return row


def update_planner_preference(db: Session, *, row: models.PlannerPreference, payload: schemas.PlannerPreferenceUpdate) -> models.PlannerPreference:
    for key, value in _dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


def serialize_planner_preference(row: models.PlannerPreference) -> schemas.PlannerPreferenceRead:
    return schemas.PlannerPreferenceRead.model_validate(row)
