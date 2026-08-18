from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from . import models, pay_policy


@dataclass(frozen=True)
class PaySegment:
    minutes: int
    category: models.TimesheetCategory
    classification: pay_policy.DutyPayClassification
    minimum_multiplier: Decimal


def _normal_weekly_limit(contract: models.EmploymentContract | None) -> int:
    statutory = 52 * 60
    if contract is None:
        return statutory
    configured = int(getattr(contract, "standard_weekly_minutes", statutory) or statutory)
    return min(max(configured, 0), statutory)


def _contractual_floor(
    contract: models.EmploymentContract | None,
    classification: pay_policy.DutyPayClassification,
) -> Decimal | None:
    """Resolve a higher contract floor when the contract model exposes one.

    Current deployments do not yet require dedicated multiplier columns on
    EmploymentContract. Keep this resolver server-owned and forward-compatible:
    if such fields or a contract metadata pay_multipliers map are present, they
    immediately become non-lowerable floors without trusting a supervisor's
    request payload.
    """

    if contract is None:
        return None
    field_by_classification = {
        pay_policy.DutyPayClassification.NORMAL_DUTY: "normal_duty_multiplier",
        pay_policy.DutyPayClassification.ORDINARY_OT: "ordinary_ot_multiplier",
        pay_policy.DutyPayClassification.REST_DAY_WORK: "rest_day_multiplier",
        pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK: "public_holiday_multiplier",
    }
    field = field_by_classification[classification]
    direct = getattr(contract, field, None)
    if direct is not None:
        return Decimal(str(direct))
    metadata = getattr(contract, "metadata_json", None) or {}
    pay_multipliers = metadata.get("pay_multipliers") if isinstance(metadata, dict) else None
    if isinstance(pay_multipliers, dict) and pay_multipliers.get(classification.value) is not None:
        return Decimal(str(pay_multipliers[classification.value]))
    return None


def split_pay_segments(
    *,
    minutes: int,
    base_category: models.TimesheetCategory,
    is_public_holiday: bool,
    is_protected_rest_day: bool,
    ordinary_minutes_before: int,
    normal_weekly_limit: int,
    contractual_floor: Decimal | None = None,
) -> list[PaySegment]:
    """Split one attendance-backed line at the normal-hours boundary.

    Rest-day/public-holiday classifications take precedence over ordinary OT;
    Sunday by itself has no special meaning here. The rolling total-hours
    legality ceiling remains in the rostering validator rather than payroll.
    """

    worked = max(int(minutes or 0), 0)
    if worked <= 0:
        return []

    if is_public_holiday:
        classification = pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK
        minimum = pay_policy.minimum_multiplier(classification, contractual_minimum=contractual_floor)
        return [PaySegment(worked, models.TimesheetCategory.PUBLIC_HOLIDAY, classification, minimum)]

    if is_protected_rest_day:
        classification = pay_policy.DutyPayClassification.REST_DAY_WORK
        minimum = pay_policy.minimum_multiplier(classification, contractual_minimum=contractual_floor)
        # WEEKEND is the existing payroll bucket for protected-rest work; the
        # exact reason remains explicit in metadata and is not inferred from day name.
        return [PaySegment(worked, models.TimesheetCategory.WEEKEND, classification, minimum)]

    remaining_normal = max(int(normal_weekly_limit) - max(int(ordinary_minutes_before), 0), 0)
    normal_minutes = min(worked, remaining_normal)
    overtime_minutes = worked - normal_minutes
    output: list[PaySegment] = []
    if normal_minutes:
        classification = pay_policy.DutyPayClassification.NORMAL_DUTY
        minimum = pay_policy.minimum_multiplier(classification, contractual_minimum=contractual_floor)
        output.append(PaySegment(normal_minutes, base_category, classification, minimum))
    if overtime_minutes:
        classification = pay_policy.DutyPayClassification.ORDINARY_OT
        minimum = pay_policy.minimum_multiplier(classification, contractual_minimum=contractual_floor)
        output.append(PaySegment(overtime_minutes, models.TimesheetCategory.OVERTIME, classification, minimum))
    return output


def _contracts_by_user(
    db: Session,
    *,
    amo_id: str,
    user_ids: Sequence[str],
    period_start: date,
    period_end: date,
) -> dict[str, list[models.EmploymentContract]]:
    rows = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id.in_(list(user_ids) or ["__none__"]),
        models.EmploymentContract.employment_status == models.EmploymentStatus.ACTIVE,
        models.EmploymentContract.effective_from <= period_end,
        or_(
            models.EmploymentContract.effective_to.is_(None),
            models.EmploymentContract.effective_to >= period_start,
        ),
    ).order_by(models.EmploymentContract.user_id.asc(), models.EmploymentContract.effective_from.desc()).all()
    result: dict[str, list[models.EmploymentContract]] = defaultdict(list)
    for row in rows:
        result[str(row.user_id)].append(row)
    return result


def _contract_on(
    rows: Sequence[models.EmploymentContract],
    work_date: date,
) -> models.EmploymentContract | None:
    return next(
        (
            row
            for row in rows
            if row.effective_from <= work_date
            and (row.effective_to is None or row.effective_to >= work_date)
        ),
        None,
    )


def _holiday_dates(
    db: Session,
    *,
    amo_id: str,
    period_start: date,
    period_end: date,
) -> set[date]:
    return {
        row[0]
        for row in db.query(models.PublicHoliday.holiday_date)
        .join(
            models.PublicHolidayCalendar,
            models.PublicHoliday.calendar_id == models.PublicHolidayCalendar.id,
        )
        .filter(
            models.PublicHoliday.amo_id == amo_id,
            models.PublicHoliday.holiday_date >= period_start,
            models.PublicHoliday.holiday_date <= period_end,
            models.PublicHoliday.paid.is_(True),
            models.PublicHolidayCalendar.is_active.is_(True),
        )
        .all()
    }


def _assignment_semantics(
    db: Session,
    *,
    amo_id: str,
    user_ids: Sequence[str],
    period_start: date,
    period_end: date,
    timezone_name: str,
) -> tuple[set[tuple[str, date]], set[tuple[str, date]]]:
    from ..rostering import compliance_policy
    from ..rostering import models as roster_models
    from ..rostering.code_registry_models import RosterShiftTemplatePolicy

    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(timezone_name or "UTC")
    except Exception:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo("UTC")

    start_dt = datetime.combine(period_start, time.min, tzinfo=zone).astimezone(timezone.utc)
    end_dt = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    assignments = db.query(roster_models.RosterAssignment).join(
        roster_models.RosterVersion,
        roster_models.RosterAssignment.version_id == roster_models.RosterVersion.id,
    ).options(selectinload(roster_models.RosterAssignment.shift_template)).filter(
        roster_models.RosterAssignment.amo_id == amo_id,
        roster_models.RosterAssignment.user_id.in_(list(user_ids) or ["__none__"]),
        roster_models.RosterAssignment.deleted_at.is_(None),
        roster_models.RosterVersion.status == roster_models.RosterVersionStatus.PUBLISHED,
        roster_models.RosterAssignment.starts_at < end_dt,
        roster_models.RosterAssignment.ends_at > start_dt,
    ).all()

    template_ids = {
        str(row.shift_template_id)
        for row in assignments
        if getattr(row, "shift_template_id", None)
    }
    policies = {
        str(row.shift_template_id): row
        for row in db.query(RosterShiftTemplatePolicy)
        .filter(
            RosterShiftTemplatePolicy.amo_id == amo_id,
            RosterShiftTemplatePolicy.shift_template_id.in_(list(template_ids) or ["__none__"]),
        )
        .all()
    }

    duty_dates: set[tuple[str, date]] = set()
    rest_dates: set[tuple[str, date]] = set()
    for row in assignments:
        local_date = row.starts_at.astimezone(zone).date()
        key = (str(row.user_id), local_date)
        if compliance_policy.assignment_counts_as_duty(row):
            duty_dates.add(key)
        elif compliance_policy.assignment_is_protected_rest(row, policies=policies):
            rest_dates.add(key)
    return duty_dates, rest_dates


def _metadata(
    *,
    classification: pay_policy.DutyPayClassification,
    minimum_multiplier: Decimal,
    base_category: models.TimesheetCategory,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(existing or {})
    payload.update(
        {
            "pay_classification": classification.value,
            "minimum_multiplier": float(minimum_multiplier),
            "base_category": str(getattr(base_category, "value", base_category)),
            "manual_reduction_allowed": False,
        }
    )
    return payload


def apply_pay_classification(
    db: Session,
    *,
    amo_id: str,
    sheets: Sequence[models.Timesheet],
    period_start: date,
    period_end: date,
    timezone_name: str,
) -> None:
    sheet_ids = [str(row.id) for row in sheets]
    user_ids = [str(row.user_id) for row in sheets]
    if not sheet_ids:
        return

    lines = db.query(models.TimesheetLine).filter(
        models.TimesheetLine.amo_id == amo_id,
        models.TimesheetLine.timesheet_id.in_(sheet_ids),
    ).order_by(
        models.TimesheetLine.timesheet_id.asc(),
        models.TimesheetLine.work_date.asc(),
        models.TimesheetLine.created_at.asc(),
        models.TimesheetLine.id.asc(),
    ).all()

    # The legacy variance row calls every minute above the published plan OT.
    # Replace it with the actual normal-hours/pay-reason classification below.
    for line in list(lines):
        if line.source == "CALCULATED_VARIANCE":
            db.delete(line)
    db.flush()
    lines = [line for line in lines if line.source != "CALCULATED_VARIANCE"]

    contracts = _contracts_by_user(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
        period_start=period_start,
        period_end=period_end,
    )
    holidays = _holiday_dates(
        db,
        amo_id=amo_id,
        period_start=period_start,
        period_end=period_end,
    )
    duty_dates, rest_dates = _assignment_semantics(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
        period_start=period_start,
        period_end=period_end,
        timezone_name=timezone_name,
    )

    sheet_by_id = {str(row.id): row for row in sheets}
    week_minutes: dict[tuple[str, date], int] = defaultdict(int)
    overtime_minutes_by_sheet: dict[str, int] = defaultdict(int)

    for line in lines:
        sheet = sheet_by_id.get(str(line.timesheet_id))
        if sheet is None or int(line.minutes or 0) <= 0:
            continue
        if line.category in {models.TimesheetCategory.LEAVE, models.TimesheetCategory.UNPAID_ABSENCE}:
            continue

        user_id = str(sheet.user_id)
        contract = _contract_on(contracts.get(user_id, []), line.work_date)
        week_start = line.work_date - timedelta(days=line.work_date.weekday())
        week_key = (user_id, week_start)
        normal_limit = _normal_weekly_limit(contract)
        is_public_holiday = line.work_date in holidays
        is_protected_rest_day = (user_id, line.work_date) in rest_dates and (
            (user_id, line.work_date) in duty_dates or int(line.minutes or 0) > 0
        )
        base_category = line.category

        preliminary_classification = (
            pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK
            if is_public_holiday
            else pay_policy.DutyPayClassification.REST_DAY_WORK
            if is_protected_rest_day
            else pay_policy.DutyPayClassification.ORDINARY_OT
            if week_minutes[week_key] >= normal_limit
            else pay_policy.DutyPayClassification.NORMAL_DUTY
        )
        contract_floor = _contractual_floor(contract, preliminary_classification)
        segments = split_pay_segments(
            minutes=int(line.minutes or 0),
            base_category=base_category,
            is_public_holiday=is_public_holiday,
            is_protected_rest_day=is_protected_rest_day,
            ordinary_minutes_before=week_minutes[week_key],
            normal_weekly_limit=normal_limit,
            contractual_floor=contract_floor,
        )
        if not segments:
            continue

        first, *additional = segments
        line.minutes = first.minutes
        line.category = first.category
        line.metadata_json = _metadata(
            classification=first.classification,
            minimum_multiplier=first.minimum_multiplier,
            base_category=base_category,
            existing=line.metadata_json,
        )
        line.description = f"{first.classification.value}; attendance reconciled against published roster"
        db.add(line)
        if first.classification == pay_policy.DutyPayClassification.ORDINARY_OT:
            overtime_minutes_by_sheet[str(sheet.id)] += first.minutes

        for segment in additional:
            db.add(
                models.TimesheetLine(
                    amo_id=amo_id,
                    timesheet_id=sheet.id,
                    work_date=line.work_date,
                    category=segment.category,
                    minutes=segment.minutes,
                    roster_assignment_id=line.roster_assignment_id,
                    work_log_entry_id=line.work_log_entry_id,
                    source="PAY_POLICY_SPLIT",
                    description=f"{segment.classification.value}; split at normal-hours threshold",
                    metadata_json=_metadata(
                        classification=segment.classification,
                        minimum_multiplier=segment.minimum_multiplier,
                        base_category=base_category,
                        existing=line.metadata_json,
                    ),
                )
            )
            if segment.classification == pay_policy.DutyPayClassification.ORDINARY_OT:
                overtime_minutes_by_sheet[str(sheet.id)] += segment.minutes

        # Every worked minute contributes to the weekly normal-hours threshold,
        # including rest-day/public-holiday work. The pay reason determines the
        # applicable multiplier; it does not erase the duty hours.
        week_minutes[week_key] += sum(segment.minutes for segment in segments)

    for sheet in sheets:
        sheet.overtime_minutes = overtime_minutes_by_sheet.get(str(sheet.id), 0)
        db.add(sheet)
    db.flush()


def install_service_policy(service_module) -> None:
    if getattr(service_module, "_timesheet_pay_policy_installed", False):
        return
    original_generate = service_module.generate_timesheets

    def governed_generate_timesheets(db: Session, *, amo_id: str, actor_user_id: str, payload):
        rows = original_generate(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        amo = db.query(service_module.account_models.AMO).filter(
            service_module.account_models.AMO.id == amo_id,
        ).first()
        apply_pay_classification(
            db,
            amo_id=amo_id,
            sheets=rows,
            period_start=payload.period_start,
            period_end=payload.period_end,
            timezone_name=getattr(amo, "time_zone", None) or "UTC",
        )
        return rows

    service_module.generate_timesheets = governed_generate_timesheets
    service_module._timesheet_pay_policy_installed = True


__all__ = [
    "PaySegment",
    "apply_pay_classification",
    "install_service_policy",
    "split_pay_segments",
]
