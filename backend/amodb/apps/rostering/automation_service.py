"""Controlled roster setup readiness, preview and draft-generation automation."""
from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import distinct, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..workforce import models as workforce_models
from ..workforce import schemas as workforce_schemas
from ..workforce import services as workforce_services
from . import models as roster_models
from . import schemas as roster_schemas
from . import services as roster_services
from .automation_models import (
    RosterAutomationFrequency,
    RosterAutomationRunStatus,
    RosterAutomationTrigger,
    RosterGenerationPolicy,
    RosterGenerationRun,
)
from .automation_schemas import (
    RosterAutomationPreviewItem,
    RosterAutomationPreviewRequest,
    RosterAutomationPreviewResponse,
    RosterAutomationRunRequest,
    RosterGenerationPolicyUpdate,
    RosterSetupReadinessItem,
    RosterSetupReadinessResponse,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value) -> str:
    return str(getattr(value, "value", value))


def _request_fingerprint(
    payload: RosterAutomationRunRequest,
    trigger: RosterAutomationTrigger,
) -> str:
    values = payload.model_dump(mode="json", exclude={"idempotency_key"})
    values["user_ids"] = sorted(set(values.get("user_ids") or []))
    canonical = {"trigger": _enum_value(trigger), "payload": values}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unsupported IANA timezone: {name}") from exc
    return name


def _validate_run_day(frequency, run_day: int) -> int:
    normalized = _enum_value(frequency)
    if normalized in {
        RosterAutomationFrequency.WEEKLY.value,
        RosterAutomationFrequency.FORTNIGHTLY.value,
    }:
        if not 1 <= int(run_day) <= 7:
            raise ValueError("Weekly and fortnightly automation run_day must be an ISO weekday from 1 to 7")
    elif not 1 <= int(run_day) <= 28:
        raise ValueError("Monthly automation run_day must be from 1 to 28")
    return int(run_day)


_SCHEDULE_FIELDS = frozenset({
    "enabled",
    "frequency",
    "run_day",
    "run_hour_local",
    "timezone_name",
})


def _schedule_fields_changed(policy: RosterGenerationPolicy, values: dict) -> bool:
    for key in _SCHEDULE_FIELDS:
        if key not in values:
            continue
        current = getattr(policy, key)
        proposed = values[key]
        if key == "frequency":
            if _enum_value(current) != _enum_value(proposed):
                return True
        elif current != proposed:
            return True
    return False


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(month_index, 12)
    month = zero_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_window(anchor: date, lead_periods: int) -> tuple[date, date]:
    first = _add_months(date(anchor.year, anchor.month, 1), lead_periods)
    last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    return first, last


def _weekly_window(anchor: date, lead_periods: int) -> tuple[date, date]:
    next_monday = anchor + timedelta(days=(7 - anchor.weekday()) % 7 or 7)
    first = next_monday + timedelta(weeks=max(0, lead_periods - 1))
    return first, first + timedelta(days=6)


def _fortnight_window(anchor: date, lead_periods: int) -> tuple[date, date]:
    first, _ = _weekly_window(anchor, lead_periods)
    return first, first + timedelta(days=13)


def _target_window(policy: RosterGenerationPolicy, *, today: Optional[date] = None) -> tuple[date, date]:
    today = today or datetime.now(ZoneInfo(policy.timezone_name)).date()
    frequency = _enum_value(policy.frequency)
    if frequency == RosterAutomationFrequency.WEEKLY.value:
        return _weekly_window(today, policy.lead_periods)
    if frequency == RosterAutomationFrequency.FORTNIGHTLY.value:
        return _fortnight_window(today, policy.lead_periods)
    return _month_window(today, policy.lead_periods)


def _target_window_for_occurrence(
    policy: RosterGenerationPolicy,
    scheduled_at: datetime,
) -> tuple[date, date]:
    """Derive a target window from the scheduled occurrence, not worker delay."""
    local_date = scheduled_at.astimezone(ZoneInfo(policy.timezone_name)).date()
    return _target_window(policy, today=local_date)


def _render_pattern(pattern: str, target_from: date, target_to: date) -> str:
    tokens = {
        "{YYYY}": f"{target_from.year:04d}",
        "{YY}": f"{target_from.year % 100:02d}",
        "{MM}": f"{target_from.month:02d}",
        "{M}": str(target_from.month),
        "{MMMM}": calendar.month_name[target_from.month],
        "{MMM}": calendar.month_abbr[target_from.month],
        "{DD}": f"{target_from.day:02d}",
        "{END_DD}": f"{target_to.day:02d}",
    }
    rendered = pattern
    for token, value in tokens.items():
        rendered = rendered.replace(token, value)
    return rendered.strip()


def _render_period_code(pattern: str, target_from: date, target_to: date) -> str:
    """Render a collision-safe code while preserving a stable date suffix."""
    rendered = _render_pattern(pattern, target_from, target_to) or "ROSTER"
    full_month = (
        target_from.day == 1
        and target_from.year == target_to.year
        and target_from.month == target_to.month
        and target_to.day == calendar.monthrange(target_from.year, target_from.month)[1]
    )
    boundary = (
        f"{target_from:%Y%m}"
        if full_month
        else f"{target_from:%Y%m%d}-{target_to:%Y%m%d}"
    )
    if rendered.endswith(boundary) and len(rendered) <= 32:
        return rendered
    prefix_length = max(0, 32 - len(boundary) - 1)
    prefix = rendered[:prefix_length].rstrip("- _")
    return f"{prefix}-{boundary}" if prefix else boundary


def _next_run(
    policy: RosterGenerationPolicy,
    *,
    now: Optional[datetime] = None,
    previous_scheduled_at: Optional[datetime] = None,
) -> Optional[datetime]:
    if not policy.enabled or _enum_value(policy.frequency) == RosterAutomationFrequency.MANUAL.value:
        return None
    run_day = _validate_run_day(policy.frequency, policy.run_day)
    zone = ZoneInfo(policy.timezone_name)
    current = (now or _utcnow()).astimezone(zone)
    frequency = _enum_value(policy.frequency)

    if previous_scheduled_at is not None:
        previous = previous_scheduled_at.astimezone(zone)
        if frequency == RosterAutomationFrequency.MONTHLY.value:
            next_month = _add_months(previous.date().replace(day=1), 1)
            candidate = datetime.combine(
                date(next_month.year, next_month.month, run_day),
                time(policy.run_hour_local, 0),
                tzinfo=zone,
            )
        else:
            cadence_days = 7 if frequency == RosterAutomationFrequency.WEEKLY.value else 14
            candidate = datetime.combine(
                previous.date() + timedelta(days=cadence_days),
                time(policy.run_hour_local, 0),
                tzinfo=zone,
            )
        # Advance exactly one recorded occurrence. If the resulting
        # timestamp is still overdue, the next scheduler pass must
        # process it and retain its own target period and run evidence.
        return candidate.astimezone(timezone.utc)

    if frequency == RosterAutomationFrequency.MONTHLY.value:
        candidate = datetime.combine(
            date(current.year, current.month, run_day),
            time(policy.run_hour_local, 0),
            tzinfo=zone,
        )
        if candidate <= current:
            next_month = _add_months(candidate.date().replace(day=1), 1)
            candidate = datetime.combine(
                date(next_month.year, next_month.month, run_day),
                time(policy.run_hour_local, 0),
                tzinfo=zone,
            )
    else:
        cadence_days = 7 if frequency == RosterAutomationFrequency.WEEKLY.value else 14
        days_ahead = (run_day - current.isoweekday()) % 7
        candidate = datetime.combine(
            current.date() + timedelta(days=days_ahead),
            time(policy.run_hour_local, 0),
            tzinfo=zone,
        )
        if candidate <= current:
            candidate += timedelta(days=cadence_days)
    return candidate.astimezone(timezone.utc)


def get_or_create_policy(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str] = None,
) -> RosterGenerationPolicy:
    row = db.query(RosterGenerationPolicy).filter(RosterGenerationPolicy.amo_id == amo_id).first()
    if row:
        return row
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    timezone_name = getattr(amo, "time_zone", None) or "UTC"
    _validate_timezone(timezone_name)
    candidate = RosterGenerationPolicy(
        amo_id=amo_id,
        timezone_name=timezone_name,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    candidate.next_run_at = _next_run(candidate)
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
        return candidate
    except IntegrityError:
        winner = db.query(RosterGenerationPolicy).filter(
            RosterGenerationPolicy.amo_id == amo_id,
        ).first()
        if winner is not None:
            return winner
        raise


def update_policy(
    db: Session,
    *,
    row: RosterGenerationPolicy,
    actor_user_id: str,
    payload: RosterGenerationPolicyUpdate,
) -> RosterGenerationPolicy:
    row = db.query(RosterGenerationPolicy).filter(
        RosterGenerationPolicy.id == row.id,
        RosterGenerationPolicy.amo_id == row.amo_id,
    ).populate_existing().with_for_update().one()
    if payload.expected_state_revision != row.state_revision:
        raise RuntimeError(f"ROSTER_AUTOMATION_REVISION_CONFLICT:{row.state_revision}")
    values = payload.model_dump(exclude_unset=True)
    values.pop("expected_state_revision", None)
    reason = str(values.pop("reason", "")).strip()
    if not reason:
        raise ValueError("A reason is required when changing roster automation")
    if values.get("timezone_name"):
        values["timezone_name"] = _validate_timezone(str(values["timezone_name"]))
    schedule_changed = _schedule_fields_changed(row, values)
    previous_next_run = row.next_run_at
    for key, value in values.items():
        setattr(row, key, value)
    _validate_run_day(row.frequency, row.run_day)
    row.updated_by_user_id = actor_user_id
    row.updated_reason = reason
    row.state_revision += 1
    frequency = _enum_value(row.frequency)
    if not row.enabled or frequency == RosterAutomationFrequency.MANUAL.value:
        row.next_run_at = None
    elif schedule_changed or previous_next_run is None:
        row.next_run_at = _next_run(row)
    else:
        row.next_run_at = previous_next_run
    db.add(row)
    db.flush()
    return row


def _period_for_window(
    db: Session,
    *,
    amo_id: str,
    target_from: date,
    target_to: date,
) -> Optional[roster_models.RosterPeriod]:
    return db.query(roster_models.RosterPeriod).options(
        selectinload(roster_models.RosterPeriod.versions),
    ).filter(
        roster_models.RosterPeriod.amo_id == amo_id,
        roster_models.RosterPeriod.starts_on == target_from,
        roster_models.RosterPeriod.ends_on == target_to,
    ).first()


def _eligible_user_ids(
    db: Session,
    *,
    amo_id: str,
    target_from: date,
    target_to: date,
    requested_user_ids: Iterable[str] = (),
) -> list[str]:
    query = db.query(distinct(workforce_models.EmploymentContract.user_id)).filter(
        workforce_models.EmploymentContract.amo_id == amo_id,
        workforce_models.EmploymentContract.employment_status == workforce_models.EmploymentStatus.ACTIVE,
        workforce_models.EmploymentContract.effective_from <= target_to,
        or_(
            workforce_models.EmploymentContract.effective_to.is_(None),
            workforce_models.EmploymentContract.effective_to >= target_from,
        ),
    )
    requested = sorted({str(user_id) for user_id in requested_user_ids if user_id})
    if requested:
        query = query.filter(workforce_models.EmploymentContract.user_id.in_(requested))
    return sorted(str(row[0]) for row in query.all())


def preview(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    payload: RosterAutomationPreviewRequest,
) -> RosterAutomationPreviewResponse:
    policy = get_or_create_policy(db, amo_id=amo_id, actor_user_id=actor_user_id)
    target_from, target_to = (
        (payload.target_from, payload.target_to)
        if payload.target_from and payload.target_to
        else _target_window(policy)
    )
    period_code = _render_period_code(policy.period_code_pattern, target_from, target_to)
    period_name = _render_pattern(policy.period_name_pattern, target_from, target_to)
    period = _period_for_window(db, amo_id=amo_id, target_from=target_from, target_to=target_to)
    drafts = [
        version for version in (period.versions if period else [])
        if _enum_value(version.status) == roster_models.RosterVersionStatus.DRAFT.value
    ]
    draft = sorted(drafts, key=lambda row: row.version_no, reverse=True)[0] if drafts else None

    eligible_ids = _eligible_user_ids(
        db,
        amo_id=amo_id,
        target_from=target_from,
        target_to=target_to,
        requested_user_ids=payload.user_ids,
    )
    pattern_preview = workforce_services.preview_patterns(
        db,
        amo_id=amo_id,
        payload=workforce_schemas.PatternPreviewRequest(
            from_date=target_from,
            to_date=target_to,
            user_ids=eligible_ids,
            roster_version_id=draft.id if draft else None,
        ),
    )
    patterned_users = {row.user_id for row in pattern_preview.items}
    missing_pattern_count = len(set(eligible_ids) - patterned_users)
    estimated_count = sum(
        1 for row in pattern_preview.items
        if row.shift_template_id and _enum_value(row.status) not in {"OFF", "LEAVE", "UNAVAILABLE"} and not row.conflicts
    )

    items: list[RosterAutomationPreviewItem] = []
    if not period and not payload.create_missing_period:
        items.append(RosterAutomationPreviewItem(
            code="PERIOD_MISSING",
            severity="BLOCKER",
            message="No roster period exists for the selected dates and automatic period creation is disabled.",
        ))
    if not eligible_ids:
        items.append(RosterAutomationPreviewItem(
            code="NO_ELIGIBLE_EMPLOYEES",
            severity="WARNING",
            message="No active employment contracts cover the selected period.",
        ))
    if missing_pattern_count:
        items.append(RosterAutomationPreviewItem(
            code="EMPLOYEES_WITHOUT_PATTERN",
            severity="WARNING",
            message=f"{missing_pattern_count} eligible employee(s) have no effective work pattern and will remain unassigned.",
        ))
    if not pattern_preview.items and (payload.generate_from_patterns if payload.generate_from_patterns is not None else policy.generate_from_patterns):
        items.append(RosterAutomationPreviewItem(
            code="NO_ACTIVE_PATTERN_ASSIGNMENTS",
            severity="WARNING",
            message="No explicit assignments or matching automatic rotation rules were found.",
        ))

    blocker_count = sum(1 for item in items if item.severity == "BLOCKER")
    warning_count = sum(1 for item in items if item.severity == "WARNING")
    return RosterAutomationPreviewResponse(
        target_from=target_from,
        target_to=target_to,
        period_code=period_code,
        period_name=period_name,
        period_exists=bool(period),
        period_id=period.id if period else None,
        draft_exists=bool(draft),
        draft_version_id=draft.id if draft else None,
        active_pattern_assignment_count=len({(row.user_id, row.pattern_id) for row in pattern_preview.items}),
        eligible_employee_count=len(eligible_ids),
        employees_without_pattern_count=missing_pattern_count,
        estimated_assignment_count=estimated_count,
        blocking_issue_count=blocker_count,
        warning_count=warning_count,
        items=items,
        requires_confirmation=policy.require_preview_confirmation,
    )


def _existing_run(db: Session, *, amo_id: str, idempotency_key: str) -> Optional[RosterGenerationRun]:
    return db.query(RosterGenerationRun).filter(
        RosterGenerationRun.amo_id == amo_id,
        RosterGenerationRun.idempotency_key == idempotency_key,
    ).first()


def run(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: RosterAutomationRunRequest,
    trigger: RosterAutomationTrigger = RosterAutomationTrigger.MANUAL,
) -> RosterGenerationRun:
    request_fingerprint = _request_fingerprint(payload, trigger)
    replay = _existing_run(db, amo_id=amo_id, idempotency_key=payload.idempotency_key)
    if replay:
        stored_fingerprint = (replay.summary_json or {}).get("request_fingerprint")
        if stored_fingerprint and stored_fingerprint != request_fingerprint:
            raise RuntimeError(f"ROSTER_AUTOMATION_IDEMPOTENCY_PAYLOAD_MISMATCH:{replay.id}")
        replay_status = _enum_value(replay.status)
        if replay_status == RosterAutomationRunStatus.FAILED.value:
            raise RuntimeError(f"ROSTER_AUTOMATION_PREVIOUS_FAILURE:{replay.id}")
        if replay_status == RosterAutomationRunStatus.RUNNING.value:
            raise RuntimeError(f"ROSTER_AUTOMATION_ALREADY_RUNNING:{replay.id}")
        return replay

    policy = get_or_create_policy(db, amo_id=amo_id, actor_user_id=actor_user_id)
    scheduled_occurrence = policy.next_run_at if trigger == RosterAutomationTrigger.SCHEDULED else None
    preview_result = preview(db, amo_id=amo_id, actor_user_id=actor_user_id, payload=payload)
    if preview_result.blocking_issue_count:
        raise ValueError("Roster automation preview contains blocking issues")
    if policy.require_preview_confirmation and not payload.confirm_preview:
        raise ValueError("Confirm the automation preview before generating the draft")

    run_row = RosterGenerationRun(
        amo_id=amo_id,
        policy_id=policy.id,
        trigger=trigger,
        status=RosterAutomationRunStatus.RUNNING,
        idempotency_key=payload.idempotency_key,
        target_from=preview_result.target_from.isoformat(),
        target_to=preview_result.target_to.isoformat(),
        requested_by_user_id=actor_user_id,
        summary_json={"preview": preview_result.model_dump(mode="json"), "request_fingerprint": request_fingerprint},
    )
    db.add(run_row)
    db.flush()

    period = _period_for_window(
        db,
        amo_id=amo_id,
        target_from=preview_result.target_from,
        target_to=preview_result.target_to,
    )
    if not period:
        if not payload.create_missing_period:
            raise ValueError("The selected roster period does not exist")
        period = roster_services.create_period(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            payload=roster_schemas.RosterPeriodCreate(
                period_code=preview_result.period_code,
                name=preview_result.period_name,
                starts_on=preview_result.target_from,
                ends_on=preview_result.target_to,
                notes="Created by controlled roster automation",
                timezone_name=policy.timezone_name,
            ),
        )
    run_row.period_id = period.id

    drafts = [
        row for row in (period.versions or [])
        if _enum_value(row.status) == roster_models.RosterVersionStatus.DRAFT.value
    ]
    draft = sorted(drafts, key=lambda row: row.version_no, reverse=True)[0] if drafts else None
    should_create_draft = (
        payload.create_initial_draft
        if payload.create_initial_draft is not None
        else policy.create_initial_draft
    )
    should_generate = (
        payload.generate_from_patterns
        if payload.generate_from_patterns is not None
        else policy.generate_from_patterns
    )
    if not draft and (should_create_draft or should_generate):
        draft = roster_services.create_version(
            db,
            period=period,
            actor_user_id=actor_user_id,
            payload=roster_schemas.RosterVersionCreate(
                title=f"Automated draft for {period.period_code}",
                change_summary="Generated from effective Workforce work patterns; requires planner review.",
                idempotency_key=f"{payload.idempotency_key}:version",
            ),
        )
    if not draft and (should_create_draft or should_generate):
        raise ValueError("No draft roster version is available for generation")
    if draft:
        draft = db.query(roster_models.RosterVersion).filter(
            roster_models.RosterVersion.id == draft.id,
            roster_models.RosterVersion.amo_id == amo_id,
        ).populate_existing().with_for_update().first()
        if not draft or _enum_value(draft.status) != roster_models.RosterVersionStatus.DRAFT.value:
            raise RuntimeError("ROSTER_AUTOMATION_DRAFT_NOT_EDITABLE")
    run_row.version_id = draft.id if draft else None

    generated_count = 0
    skipped_count = 0
    conflicts: list[dict] = []
    if should_generate and draft:
        generation = roster_services.generate_from_patterns(
            db,
            version=draft,
            actor_user_id=actor_user_id,
            payload=roster_schemas.PatternGenerationRequest(
                from_date=preview_result.target_from,
                to_date=preview_result.target_to,
                user_ids=payload.user_ids,
                idempotency_key=f"{payload.idempotency_key}:pattern",
                skip_duplicates=True,
                expected_version_revision=draft.state_revision,
            ),
        )
        generated_count = len(generation.created)
        skipped_count = len(generation.skipped)
        conflicts = list(generation.conflicts)

    blocker_count = 0
    warning_count = 0
    if policy.validate_after_generation and draft:
        validation = roster_services.validate_version(
            db,
            version=draft,
            actor_user_id=actor_user_id,
        )
        blocker_count = int(validation.blocker_count)
        warning_count = int(validation.warning_count)

    run_row.generated_count = generated_count
    run_row.skipped_count = skipped_count
    run_row.conflict_count = len(conflicts)
    run_row.validation_blocker_count = blocker_count
    run_row.validation_warning_count = warning_count
    run_row.summary_json = {
        "preview": preview_result.model_dump(mode="json"),
        "request_fingerprint": request_fingerprint,
        "conflicts": conflicts,
        "period_created_or_reused": True,
        "draft_created_or_reused": draft is not None,
        "generation_performed": bool(should_generate and draft),
        "validation_performed": bool(policy.validate_after_generation and draft),
        "review_required": True,
        "publication_performed": False,
    }
    run_row.status = (
        RosterAutomationRunStatus.COMPLETED_WITH_CONFLICTS
        if conflicts or blocker_count
        else RosterAutomationRunStatus.COMPLETED
    )
    run_row.completed_at = _utcnow()
    if trigger == RosterAutomationTrigger.SCHEDULED:
        policy.last_run_at = run_row.completed_at
        policy.next_run_at = _next_run(
            policy,
            now=run_row.completed_at,
            previous_scheduled_at=scheduled_occurrence,
        )
        db.add(policy)
    db.add(run_row)
    db.flush()
    return run_row


def list_runs(db: Session, *, amo_id: str, limit: int = 20) -> list[RosterGenerationRun]:
    return db.query(RosterGenerationRun).filter(
        RosterGenerationRun.amo_id == amo_id,
    ).order_by(RosterGenerationRun.created_at.desc(), RosterGenerationRun.id.desc()).limit(limit).all()


def readiness(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
) -> RosterSetupReadinessResponse:
    policy = get_or_create_policy(db, amo_id=amo_id, actor_user_id=actor_user_id)
    today = datetime.now(ZoneInfo(policy.timezone_name)).date()
    next_target_from, next_target_to = _target_window(policy, today=today)
    next_period = _period_for_window(
        db,
        amo_id=amo_id,
        target_from=next_target_from,
        target_to=next_target_to,
    )

    active_shift_count = db.query(func.count(roster_models.ShiftTemplate.id)).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.is_active.is_(True),
    ).scalar() or 0
    active_pattern_count = db.query(func.count(workforce_models.WorkPattern.id)).filter(
        workforce_models.WorkPattern.amo_id == amo_id,
        workforce_models.WorkPattern.is_active.is_(True),
    ).scalar() or 0
    active_rule_count = db.query(func.count(roster_models.RosterRule.id)).filter(
        roster_models.RosterRule.amo_id == amo_id,
        roster_models.RosterRule.is_active.is_(True),
    ).scalar() or 0
    active_authority_count = db.query(func.count(roster_models.RosterApprovalAuthority.id)).filter(
        roster_models.RosterApprovalAuthority.amo_id == amo_id,
        roster_models.RosterApprovalAuthority.is_active.is_(True),
    ).scalar() or 0
    active_contract_ids = _eligible_user_ids(
        db,
        amo_id=amo_id,
        target_from=today,
        target_to=next_target_to,
    )
    readiness_preview = workforce_services.preview_patterns(
        db,
        amo_id=amo_id,
        payload=workforce_schemas.PatternPreviewRequest(
            # Readiness only needs to resolve each person's effective pattern,
            # not materialise every duty and commitment through the end of the
            # next period. The full multi-day preview remains an explicit,
            # bounded planner action.
            from_date=next_target_from,
            to_date=next_target_from,
            user_ids=active_contract_ids,
        ),
    )
    patterned_users = {row.user_id for row in readiness_preview.items}
    missing_pattern_count = len(set(active_contract_ids) - patterned_users)
    upcoming_period_count = db.query(func.count(roster_models.RosterPeriod.id)).filter(
        roster_models.RosterPeriod.amo_id == amo_id,
        roster_models.RosterPeriod.ends_on >= today,
        roster_models.RosterPeriod.status != roster_models.RosterPeriodStatus.ARCHIVED,
    ).scalar() or 0

    items = [
        RosterSetupReadinessItem(
            key="calendar",
            label="Planning calendar",
            state="READY" if upcoming_period_count else "NEEDS_ATTENTION",
            detail=(
                f"{upcoming_period_count} current or future period(s) available."
                if upcoming_period_count
                else "No current or future roster period is available."
            ),
            action_label="Manage calendar",
            action_path="calendar",
        ),
        RosterSetupReadinessItem(
            key="automation",
            label="Automatic period setup",
            state="READY" if policy.enabled else "OPTIONAL",
            detail=(
                f"Enabled; next run {policy.next_run_at.isoformat() if policy.next_run_at else 'not scheduled'}."
                if policy.enabled
                else "Disabled. Periods can still be created manually."
            ),
            action_label="Configure automation",
            action_path="automation",
        ),
        RosterSetupReadinessItem(
            key="shifts",
            label="Shift library",
            state="READY" if active_shift_count else "BLOCKED",
            detail=f"{active_shift_count} active shift template(s).",
            action_label="Manage shifts",
            action_path="shifts",
        ),
        RosterSetupReadinessItem(
            key="patterns",
            label="Work patterns",
            state="READY" if active_pattern_count and not missing_pattern_count else "NEEDS_ATTENTION",
            detail=f"{active_pattern_count} active rotation(s); {missing_pattern_count} employee(s) need an override or matching rule.",
            action_label="Manage patterns",
            action_path="patterns",
        ),
        RosterSetupReadinessItem(
            key="policy",
            label="Compliance and approval",
            state="READY" if active_rule_count and active_authority_count else "NEEDS_ATTENTION",
            detail=f"{active_rule_count} active rule(s); {active_authority_count} approval authority record(s).",
            action_label="Manage policy",
            action_path="policy",
        ),
    ]
    ready_count = sum(1 for item in items if item.state in {"READY", "OPTIONAL"})
    can_plan = bool(active_shift_count and active_contract_ids and upcoming_period_count)
    return RosterSetupReadinessResponse(
        ready_count=ready_count,
        total_count=len(items),
        can_plan=can_plan,
        active_shift_count=int(active_shift_count),
        active_pattern_count=int(active_pattern_count),
        active_rule_count=int(active_rule_count),
        active_approval_authority_count=int(active_authority_count),
        active_contract_count=len(active_contract_ids),
        employees_without_pattern_count=missing_pattern_count,
        upcoming_period_count=int(upcoming_period_count),
        next_period_id=next_period.id if next_period else None,
        next_period_code=next_period.period_code if next_period else None,
        policy=policy,
        items=items,
    )
