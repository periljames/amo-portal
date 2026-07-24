# backend/amodb/apps/rostering/validation.py
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..training import compliance as training_compliance
from ..training import models as training_models
from ..workforce import calculations as workforce_calculations
from ..workforce import models as workforce_models
from ..workforce import services as workforce_services
from . import models, schemas

UTC = timezone.utc


@dataclass(frozen=True)
class FindingSpec:
    source: models.RosterValidationSource
    severity: models.RosterValidationSeverity
    code: str
    message: str
    assignment_id: Optional[str] = None
    user_id: Optional[str] = None
    rule_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    overridable: bool = False
    sort_order: int = 100


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _rule_parameters(row: models.RosterRule) -> dict[str, Any]:
    return dict(row.parameters_json or {})


def _severity(row: Optional[models.RosterRule], fallback: models.RosterValidationSeverity) -> models.RosterValidationSeverity:
    return row.severity if row is not None else fallback


def _overridable(row: Optional[models.RosterRule]) -> bool:
    return bool(row and row.allow_override)


def seed_default_rules(db: Session, *, amo_id: str, actor_user_id: Optional[str] = None) -> None:
    from . import governance

    rule_set = governance.seed_default_rule_set(db, amo_id=amo_id, actor_user_id=actor_user_id)
    defaults: list[dict[str, Any]] = [
        {"code": "OVERLAPPING_ASSIGNMENTS", "name": "No overlapping assignments", "rule_type": models.RosterRuleType.OVERLAP, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {}, "allow_override": False, "display_order": 10, "is_active": True},
        {"code": "MINIMUM_REST_8H", "name": "Minimum rest between duties", "rule_type": models.RosterRuleType.MIN_REST_HOURS, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"minimum_minutes": 480}, "allow_override": True, "display_order": 20, "is_active": True},
        {"code": "MAX_SHIFT_LENGTH_12H", "name": "Maximum single shift length", "rule_type": models.RosterRuleType.MAX_ASSIGNMENT_DURATION, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"maximum_minutes": 720}, "allow_override": True, "display_order": 25, "is_active": True},
        {"code": "MAX_DUTY_DAY_12H", "name": "Maximum duty in a local day", "rule_type": models.RosterRuleType.MAX_DUTY_HOURS_DAY, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"maximum_minutes": 720}, "allow_override": True, "display_order": 30, "is_active": True},
        {"code": "MAX_NORMAL_DUTY_7D_52H", "name": "Normal duty limit in seven rolling days", "rule_type": models.RosterRuleType.MAX_DUTY_HOURS_ROLLING, "severity": models.RosterValidationSeverity.WARNING, "parameters_json": {"window_days": 7, "maximum_minutes": 3120}, "allow_override": True, "display_order": 40, "is_active": True},
        {"code": "MAX_DUTY_14D_116H", "name": "Normal and overtime cap in fourteen rolling days", "rule_type": models.RosterRuleType.MAX_DUTY_HOURS_ROLLING, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"window_days": 14, "maximum_minutes": 6960}, "allow_override": True, "display_order": 42, "is_active": True},
        {"code": "MAX_CONSECUTIVE_DUTY_DAYS_6", "name": "Maximum consecutive duty days", "rule_type": models.RosterRuleType.MAX_CONSECUTIVE_DAYS, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"maximum_days": 6}, "allow_override": True, "display_order": 50, "is_active": True},
        {"code": "REST_DAY_24H_IN_7D", "name": "Twenty-four consecutive hours free from duty in seven days", "rule_type": models.RosterRuleType.REQUIRED_DAYS_OFF, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"window_days": 7, "minimum_continuous_minutes": 1440}, "allow_override": True, "display_order": 55, "is_active": True},
        {"code": "MAX_CONSECUTIVE_NIGHTS_MOPM", "name": "Maximum consecutive night shifts", "rule_type": models.RosterRuleType.MAX_CONSECUTIVE_NIGHTS, "severity": models.RosterValidationSeverity.WARNING, "parameters_json": {"maximum_nights": 0}, "allow_override": True, "display_order": 58, "is_active": False},
        {"code": "CONTRACT_ELIGIBILITY", "name": "Active employment contract and shift eligibility", "rule_type": models.RosterRuleType.CONTRACT_ELIGIBILITY, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {}, "allow_override": False, "display_order": 60, "is_active": True},
        {"code": "AVAILABILITY_CONFLICT", "name": "Approved leave and unavailability block duty", "rule_type": models.RosterRuleType.AVAILABILITY_CONFLICT, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {}, "allow_override": False, "display_order": 70, "is_active": True},
        {"code": "TRAINING_VALIDITY", "name": "Mandatory training must remain valid", "rule_type": models.RosterRuleType.TRAINING_VALIDITY, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"warning_days": 30}, "allow_override": False, "display_order": 80, "is_active": True},
        {"code": "LICENCE_VALIDITY", "name": "Maintenance licence must remain valid", "rule_type": models.RosterRuleType.LICENCE_VALIDITY, "severity": models.RosterValidationSeverity.BLOCKER, "parameters_json": {"warning_days": 30}, "allow_override": False, "display_order": 90, "is_active": True},
        {"code": "REQUIRED_CERTIFYING_COVERAGE", "name": "Certifying coverage for productive duty", "rule_type": models.RosterRuleType.REQUIRED_CERTIFYING_COVERAGE, "severity": models.RosterValidationSeverity.WARNING, "parameters_json": {"minimum_headcount": 1, "bucket_minutes": 720}, "allow_override": True, "display_order": 100, "is_active": True},
    ]
    existing = {row.code: row for row in db.query(models.RosterRule).filter(models.RosterRule.amo_id == amo_id).all()}
    for definition in defaults:
        row = existing.get(definition["code"])
        if row:
            if not row.rule_set_id:
                row.rule_set_id = rule_set.id
                db.add(row)
            continue
        db.add(models.RosterRule(
            amo_id=amo_id,
            rule_set_id=rule_set.id,
            scope=models.RosterRuleScope.AMO,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            **definition,
        ))
    db.flush()


def active_rules(db: Session, *, amo_id: str, on_date: date) -> list[models.RosterRule]:
    seed_default_rules(db, amo_id=amo_id)
    return db.query(models.RosterRule).filter(
        models.RosterRule.amo_id == amo_id,
        models.RosterRule.is_active.is_(True),
        or_(models.RosterRule.effective_from.is_(None), models.RosterRule.effective_from <= on_date),
        or_(models.RosterRule.effective_to.is_(None), models.RosterRule.effective_to >= on_date),
    ).order_by(models.RosterRule.display_order.asc(), models.RosterRule.code.asc(), models.RosterRule.id.asc()).all()


def rule_applies(rule: models.RosterRule, assignment: Optional[models.RosterAssignment]) -> bool:
    if rule.scope == models.RosterRuleScope.AMO:
        return True
    if assignment is None:
        return False
    if rule.scope == models.RosterRuleScope.DEPARTMENT:
        return assignment.department_id == rule.department_id
    if rule.scope == models.RosterRuleScope.BASE:
        return assignment.base_station_id == rule.base_station_id
    if rule.scope == models.RosterRuleScope.SHIFT_TEMPLATE:
        return assignment.shift_template_id == rule.shift_template_id
    if rule.scope == models.RosterRuleScope.USER:
        return assignment.user_id == rule.user_id
    return False


def find_rule(rules: Sequence[models.RosterRule], rule_type: models.RosterRuleType, assignment: Optional[models.RosterAssignment] = None) -> Optional[models.RosterRule]:
    applicable = [row for row in rules if row.rule_type == rule_type and rule_applies(row, assignment)]
    if not applicable:
        return None
    # The most specific active rule wins; ties follow display order and stable id.
    rank = {
        models.RosterRuleScope.AMO: 0,
        models.RosterRuleScope.DEPARTMENT: 1,
        models.RosterRuleScope.BASE: 2,
        models.RosterRuleScope.SHIFT_TEMPLATE: 3,
        models.RosterRuleScope.USER: 4,
    }
    applicable.sort(key=lambda row: (rank.get(row.scope, 0), -row.display_order, row.id), reverse=True)
    return applicable[0]


def find_rules(
    rules: Sequence[models.RosterRule],
    rule_type: models.RosterRuleType,
    assignment: Optional[models.RosterAssignment] = None,
) -> list[models.RosterRule]:
    matching = [
        row
        for row in rules
        if row.rule_type == rule_type and rule_applies(row, assignment)
    ]
    if not matching:
        return []
    rank = {
        models.RosterRuleScope.AMO: 0,
        models.RosterRuleScope.DEPARTMENT: 1,
        models.RosterRuleScope.BASE: 2,
        models.RosterRuleScope.SHIFT_TEMPLATE: 3,
        models.RosterRuleScope.USER: 4,
    }
    by_code: dict[str, models.RosterRule] = {}
    for row in matching:
        current = by_code.get(row.code)
        if current is None or rank.get(row.scope, 0) > rank.get(current.scope, 0):
            by_code[row.code] = row
    return sorted(
        by_code.values(),
        key=lambda row: (row.display_order, row.code, row.id),
    )


def _assignment_minutes(row: models.RosterAssignment) -> int:
    return int(row.planned_minutes) if row.planned_minutes is not None else workforce_calculations.duration_minutes(row.starts_at, row.ends_at)


def _is_productive(row: models.RosterAssignment) -> bool:
    return row.status in {models.RosterAssignmentStatus.DUTY, models.RosterAssignmentStatus.STANDBY}


def _is_certifying(user: Optional[account_models.User]) -> bool:
    if not user or getattr(user, "is_system_account", False):
        return False
    return user.role in {account_models.AccountRole.CERTIFYING_ENGINEER, account_models.AccountRole.CERTIFYING_TECHNICIAN}


def _fingerprint(version: models.RosterVersion, assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule]) -> str:
    payload = {
        "version_id": version.id,
        "state_revision": version.state_revision,
        "assignments": [
            {
                "id": row.id,
                "state_revision": row.state_revision,
                "user_id": row.user_id,
                "department_id": row.department_id,
                "base_station_id": row.base_station_id,
                "shift_template_id": row.shift_template_id,
                "status": _enum_value(row.status),
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat(),
                "planned_minutes": row.planned_minutes,
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            }
            for row in sorted(assignments, key=lambda item: item.id)
        ],
        "rules": [
            {
                "id": row.id,
                "updated_at": row.updated_at.isoformat(),
                "severity": _enum_value(row.severity),
                "parameters": row.parameters_json,
            }
            for row in sorted(rules, key=lambda item: item.id)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _base_integrity_findings(version: models.RosterVersion, assignments: Sequence[models.RosterAssignment]) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    start = datetime.combine(version.period.starts_on, time.min, tzinfo=UTC)
    end = datetime.combine(version.period.ends_on + timedelta(days=1), time.min, tzinfo=UTC)
    for row in assignments:
        if row.starts_at < start or row.ends_at > end:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.ROSTER,
                severity=models.RosterValidationSeverity.BLOCKER,
                code="ASSIGNMENT_OUTSIDE_PERIOD",
                message="Assignment falls outside the roster period.",
                assignment_id=row.id,
                user_id=row.user_id,
                details={"period_start": start.isoformat(), "period_end": end.isoformat(), "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat()},
                sort_order=5,
            ))
        if not row.base_station_id and _is_productive(row):
            findings.append(FindingSpec(
                source=models.RosterValidationSource.BASE,
                severity=models.RosterValidationSeverity.BLOCKER,
                code="MISSING_BASE",
                message="Productive duty requires a canonical base station.",
                assignment_id=row.id,
                user_id=row.user_id,
                sort_order=10,
            ))
        if not row.department_id:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.IDENTITY,
                severity=models.RosterValidationSeverity.WARNING,
                code="MISSING_DEPARTMENT",
                message="Assignment is not linked to a department and cannot be grouped reliably.",
                assignment_id=row.id,
                user_id=row.user_id,
                sort_order=12,
            ))
        if row.user is None or not row.user.is_active:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.IDENTITY,
                severity=models.RosterValidationSeverity.BLOCKER,
                code="INACTIVE_OR_MISSING_USER",
                message="The assigned user is missing or inactive.",
                assignment_id=row.id,
                user_id=row.user_id,
                sort_order=15,
            ))
        elif getattr(row.user, "is_system_account", False):
            findings.append(FindingSpec(
                source=models.RosterValidationSource.IDENTITY,
                severity=models.RosterValidationSeverity.BLOCKER,
                code="SYSTEM_ACCOUNT_ROSTERED",
                message="System and service accounts cannot be rostered.",
                assignment_id=row.id,
                user_id=row.user_id,
                sort_order=16,
            ))
    return findings


def _overlap_and_rest_findings(assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule]) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        if _is_productive(row):
            by_user[row.user_id].append(row)
    for user_id, rows in by_user.items():
        rows.sort(key=lambda item: (item.starts_at, item.ends_at, item.id))
        for previous, current in zip(rows, rows[1:]):
            if current.starts_at < previous.ends_at:
                rule = find_rule(rules, models.RosterRuleType.OVERLAP, current)
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.ROSTER,
                    severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                    code="OVERLAPPING_ASSIGNMENTS",
                    message="This duty overlaps another assignment for the same person.",
                    assignment_id=current.id,
                    user_id=user_id,
                    rule_id=getattr(rule, "id", None),
                    details={"conflicting_assignment_id": previous.id, "overlap_minutes": workforce_calculations.overlap_minutes(previous.starts_at, previous.ends_at, current.starts_at, current.ends_at)},
                    overridable=_overridable(rule),
                    sort_order=20,
                ))
                continue
            rule = find_rule(rules, models.RosterRuleType.MIN_REST_HOURS, current)
            if not rule:
                continue
            minimum = int(_rule_parameters(rule).get("minimum_minutes", 0))
            rest = workforce_calculations.duration_minutes(previous.ends_at, current.starts_at)
            if rest < minimum:
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=rule.severity,
                    code=rule.code,
                    message=f"Rest between duties is {rest} minutes; the configured minimum is {minimum} minutes.",
                    assignment_id=current.id,
                    user_id=user_id,
                    rule_id=rule.id,
                    details={"previous_assignment_id": previous.id, "rest_minutes": rest, "minimum_minutes": minimum},
                    overridable=rule.allow_override,
                    sort_order=30,
                ))
    return findings


def _duty_limit_findings(
    assignments: Sequence[models.RosterAssignment],
    rules: Sequence[models.RosterRule],
    timezone_name: str,
) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        if _is_productive(row):
            by_user[row.user_id].append(row)
    zone = workforce_calculations.get_zone(timezone_name)

    for user_id, rows in by_user.items():
        rows.sort(key=lambda item: (item.starts_at, item.ends_at, item.id))
        daily: dict[date, list[models.RosterAssignment]] = defaultdict(list)

        for row in rows:
            work_day = workforce_calculations.ensure_aware(row.starts_at).astimezone(zone).date()
            daily[work_day].append(row)
            duration_rule = find_rule(
                rules,
                models.RosterRuleType.MAX_ASSIGNMENT_DURATION,
                row,
            )
            if duration_rule:
                maximum = int(_rule_parameters(duration_rule).get('maximum_minutes', 0))
                actual = workforce_calculations.duration_minutes(row.starts_at, row.ends_at)
                if maximum and actual > maximum:
                    findings.append(FindingSpec(
                        source=models.RosterValidationSource.RULE,
                        severity=duration_rule.severity,
                        code=duration_rule.code,
                        message=(
                            f'This shift is {actual} minutes; the configured maximum '
                            f'shift length is {maximum} minutes.'
                        ),
                        assignment_id=row.id,
                        user_id=user_id,
                        rule_id=duration_rule.id,
                        details={
                            'shift_minutes': actual,
                            'maximum_minutes': maximum,
                        },
                        overridable=duration_rule.allow_override,
                        sort_order=35,
                    ))

        for work_day, day_rows in sorted(daily.items()):
            rule = find_rule(
                rules,
                models.RosterRuleType.MAX_DUTY_HOURS_DAY,
                day_rows[0],
            )
            if not rule:
                continue
            maximum = int(_rule_parameters(rule).get('maximum_minutes', 0))
            total = sum(_assignment_minutes(item) for item in day_rows)
            if maximum and total > maximum:
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=rule.severity,
                    code=rule.code,
                    message=(
                        f'Planned duty on {work_day.isoformat()} is {total} minutes; '
                        f'maximum is {maximum} minutes.'
                    ),
                    assignment_id=day_rows[-1].id,
                    user_id=user_id,
                    rule_id=rule.id,
                    details={
                        'work_date': work_day.isoformat(),
                        'planned_minutes': total,
                        'maximum_minutes': maximum,
                        'assignment_ids': [item.id for item in day_rows],
                    },
                    overridable=rule.allow_override,
                    sort_order=40,
                ))

        rolling_rules = find_rules(
            rules,
            models.RosterRuleType.MAX_DUTY_HOURS_ROLLING,
            rows[0] if rows else None,
        )
        for rolling_rule in rolling_rules:
            parameters = _rule_parameters(rolling_rule)
            window_days = max(int(parameters.get('window_days', 7)), 1)
            maximum = int(parameters.get('maximum_minutes', 0))
            if not maximum:
                continue
            for anchor in sorted(daily):
                window_end = anchor + timedelta(days=window_days - 1)
                window_rows = [
                    item
                    for day_value, items in daily.items()
                    if anchor <= day_value <= window_end
                    for item in items
                ]
                total = sum(_assignment_minutes(item) for item in window_rows)
                if total <= maximum:
                    continue
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=rolling_rule.severity,
                    code=rolling_rule.code,
                    message=(
                        f'Rolling {window_days}-day duty is {total} minutes; '
                        f'maximum is {maximum} minutes.'
                    ),
                    assignment_id=window_rows[-1].id if window_rows else None,
                    user_id=user_id,
                    rule_id=rolling_rule.id,
                    details={
                        'window_start': anchor.isoformat(),
                        'window_end': window_end.isoformat(),
                        'planned_minutes': total,
                        'maximum_minutes': maximum,
                    },
                    overridable=rolling_rule.allow_override,
                    sort_order=45,
                ))
                break

        consecutive_rule = find_rule(
            rules,
            models.RosterRuleType.MAX_CONSECUTIVE_DAYS,
            rows[0] if rows else None,
        )
        if consecutive_rule and daily:
            maximum_days = max(
                int(_rule_parameters(consecutive_rule).get('maximum_days', 0)),
                0,
            )
            streak_start: Optional[date] = None
            previous_day: Optional[date] = None
            streak = 0
            for work_day in sorted(daily):
                if previous_day is not None and work_day == previous_day + timedelta(days=1):
                    streak += 1
                else:
                    streak_start = work_day
                    streak = 1
                previous_day = work_day
                if not maximum_days or streak <= maximum_days:
                    continue
                last_assignment = sorted(
                    daily[work_day],
                    key=lambda item: (item.starts_at, item.id),
                )[-1]
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=consecutive_rule.severity,
                    code=consecutive_rule.code,
                    message=(
                        f'Duty is planned for {streak} consecutive days; '
                        f'maximum is {maximum_days} days.'
                    ),
                    assignment_id=last_assignment.id,
                    user_id=user_id,
                    rule_id=consecutive_rule.id,
                    details={
                        'streak_start': streak_start.isoformat() if streak_start else None,
                        'streak_end': work_day.isoformat(),
                        'consecutive_days': streak,
                        'maximum_days': maximum_days,
                    },
                    overridable=consecutive_rule.allow_override,
                    sort_order=50,
                ))
                break

        night_rule = find_rule(
            rules,
            models.RosterRuleType.MAX_CONSECUTIVE_NIGHTS,
            rows[0] if rows else None,
        )
        maximum_nights = (
            int(_rule_parameters(night_rule).get('maximum_nights', 0))
            if night_rule
            else 0
        )
        if night_rule and maximum_nights > 0:
            night_dates = sorted({
                workforce_calculations.ensure_aware(row.starts_at).astimezone(zone).date()
                for row in rows
                if getattr(getattr(row, 'shift_template', None), 'kind', None)
                == models.ShiftTemplateKind.NIGHT
            })
            streak = 0
            previous_day = None
            for work_day in night_dates:
                if previous_day and work_day == previous_day + timedelta(days=1):
                    streak += 1
                else:
                    streak = 1
                previous_day = work_day
                if streak <= maximum_nights:
                    continue
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=night_rule.severity,
                    code=night_rule.code,
                    message=(
                        f'Night duty is planned for {streak} consecutive nights; '
                        f'maximum is {maximum_nights}.'
                    ),
                    user_id=user_id,
                    rule_id=night_rule.id,
                    details={
                        'streak_end': work_day.isoformat(),
                        'consecutive_nights': streak,
                        'maximum_nights': maximum_nights,
                    },
                    overridable=night_rule.allow_override,
                    sort_order=52,
                ))
                break

        day_off_rule = find_rule(
            rules,
            models.RosterRuleType.REQUIRED_DAYS_OFF,
            rows[0] if rows else None,
        )
        if day_off_rule and rows:
            parameters = _rule_parameters(day_off_rule)
            window_days = max(int(parameters.get('window_days', 7)), 1)
            required_gap = max(
                int(parameters.get('minimum_continuous_minutes', 1440)),
                1,
            )
            first_day = workforce_calculations.ensure_aware(rows[0].starts_at).astimezone(zone).date()
            last_day = workforce_calculations.ensure_aware(rows[-1].ends_at).astimezone(zone).date()
            anchor = first_day
            while anchor + timedelta(days=window_days - 1) <= last_day:
                window_start = datetime.combine(anchor, time.min, tzinfo=zone).astimezone(UTC)
                window_end = datetime.combine(
                    anchor + timedelta(days=window_days),
                    time.min,
                    tzinfo=zone,
                ).astimezone(UTC)
                intervals = sorted(
                    [
                        (max(row.starts_at, window_start), min(row.ends_at, window_end))
                        for row in rows
                        if row.starts_at < window_end and row.ends_at > window_start
                    ],
                    key=lambda value: value[0],
                )
                cursor = window_start
                longest_gap = 0
                for starts_at, ends_at in intervals:
                    if starts_at > cursor:
                        longest_gap = max(
                            longest_gap,
                            workforce_calculations.duration_minutes(cursor, starts_at),
                        )
                    cursor = max(cursor, ends_at)
                if cursor < window_end:
                    longest_gap = max(
                        longest_gap,
                        workforce_calculations.duration_minutes(cursor, window_end),
                    )
                if longest_gap < required_gap:
                    findings.append(FindingSpec(
                        source=models.RosterValidationSource.RULE,
                        severity=day_off_rule.severity,
                        code=day_off_rule.code,
                        message=(
                            f'No continuous {required_gap / 60:g}-hour duty-free '
                            f'period exists in the {window_days}-day window '
                            f'starting {anchor.isoformat()}.'
                        ),
                        assignment_id=rows[-1].id,
                        user_id=user_id,
                        rule_id=day_off_rule.id,
                        details={
                            'window_start': anchor.isoformat(),
                            'window_days': window_days,
                            'longest_rest_minutes': longest_gap,
                            'required_rest_minutes': required_gap,
                        },
                        overridable=day_off_rule.allow_override,
                        sort_order=54,
                    ))
                    break
                anchor += timedelta(days=1)
    return findings


def _contract_findings(db: Session, assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule]) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    cache: dict[tuple[str, date], Optional[workforce_models.EmploymentContract]] = {}
    for row in assignments:
        if not _is_productive(row):
            continue
        key = (row.user_id, row.starts_at.date())
        if key not in cache:
            cache[key] = workforce_services.active_contract_for_user(db, amo_id=row.amo_id, user_id=row.user_id, on_date=row.starts_at.date())
        contract = cache[key]
        rule = find_rule(rules, models.RosterRuleType.CONTRACT_ELIGIBILITY, row)
        if contract is None:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.CONTRACT,
                severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                code="MISSING_ACTIVE_CONTRACT",
                message="No active employment contract covers this duty.",
                assignment_id=row.id,
                user_id=row.user_id,
                rule_id=getattr(rule, "id", None),
                details={"duty_date": row.starts_at.date().isoformat()},
                overridable=_overridable(rule),
                sort_order=60,
            ))
            continue
        shift_kind = getattr(getattr(row, "shift_template", None), "kind", None)
        if shift_kind == models.ShiftTemplateKind.NIGHT and not contract.night_shift_eligible:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.CONTRACT,
                severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                code="NIGHT_SHIFT_NOT_ELIGIBLE",
                message="The active employment contract does not permit night duty.",
                assignment_id=row.id,
                user_id=row.user_id,
                rule_id=getattr(rule, "id", None),
                overridable=_overridable(rule),
                sort_order=62,
            ))
        if row.status == models.RosterAssignmentStatus.STANDBY and not contract.standby_eligible:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.CONTRACT,
                severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                code="STANDBY_NOT_ELIGIBLE",
                message="The active employment contract does not permit standby duty.",
                assignment_id=row.id,
                user_id=row.user_id,
                rule_id=getattr(rule, "id", None),
                overridable=_overridable(rule),
                sort_order=63,
            ))
    return findings


def _availability_findings(db: Session, assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule]) -> list[FindingSpec]:
    if not assignments:
        return []
    start = min(row.starts_at for row in assignments)
    end = max(row.ends_at for row in assignments)
    user_ids = sorted({row.user_id for row in assignments})
    events = db.query(workforce_models.EmployeeAvailabilityEvent).filter(
        workforce_models.EmployeeAvailabilityEvent.amo_id == assignments[0].amo_id,
        workforce_models.EmployeeAvailabilityEvent.user_id.in_(user_ids),
        workforce_models.EmployeeAvailabilityEvent.blocking.is_(True),
        workforce_models.EmployeeAvailabilityEvent.starts_at < end,
        workforce_models.EmployeeAvailabilityEvent.ends_at > start,
    ).order_by(workforce_models.EmployeeAvailabilityEvent.user_id.asc(), workforce_models.EmployeeAvailabilityEvent.starts_at.asc(), workforce_models.EmployeeAvailabilityEvent.id.asc()).all()
    by_user: dict[str, list[workforce_models.EmployeeAvailabilityEvent]] = defaultdict(list)
    for event in events:
        by_user[event.user_id].append(event)
    findings: list[FindingSpec] = []
    for row in assignments:
        if not _is_productive(row):
            continue
        for event in by_user.get(row.user_id, []):
            if workforce_calculations.interval_overlaps(row.starts_at, row.ends_at, event.starts_at, event.ends_at):
                rule = find_rule(rules, models.RosterRuleType.AVAILABILITY_CONFLICT, row)
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.AVAILABILITY,
                    severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                    code="BLOCKING_AVAILABILITY_CONFLICT",
                    message=f"Duty conflicts with {_enum_value(event.availability_type).replace('_', ' ').lower()}.",
                    assignment_id=row.id,
                    user_id=row.user_id,
                    rule_id=getattr(rule, "id", None),
                    details={"availability_event_id": event.id, "availability_type": _enum_value(event.availability_type), "starts_at": event.starts_at.isoformat(), "ends_at": event.ends_at.isoformat(), "source_type": event.source_type, "source_id": event.source_id},
                    overridable=_overridable(rule),
                    sort_order=70,
                ))
    return findings


def _training_event_findings(db: Session, assignments: Sequence[models.RosterAssignment]) -> list[FindingSpec]:
    if not assignments:
        return []
    user_ids = sorted({row.user_id for row in assignments})
    start_date = min(row.starts_at.date() for row in assignments)
    end_date = max(row.ends_at.date() for row in assignments)
    participants = db.query(training_models.TrainingEventParticipant).join(
        training_models.TrainingEvent,
        training_models.TrainingEventParticipant.event_id == training_models.TrainingEvent.id,
    ).options(
        selectinload(training_models.TrainingEventParticipant.event),
    ).filter(
        training_models.TrainingEventParticipant.amo_id == assignments[0].amo_id,
        training_models.TrainingEventParticipant.user_id.in_(user_ids),
        training_models.TrainingEventParticipant.status.notin_([
            training_models.TrainingParticipantStatus.CANCELLED,
            training_models.TrainingParticipantStatus.NO_SHOW,
            training_models.TrainingParticipantStatus.DEFERRED,
        ]),
        training_models.TrainingEvent.status != training_models.TrainingEventStatus.CANCELLED,
        training_models.TrainingEvent.starts_on <= end_date,
        or_(training_models.TrainingEvent.ends_on.is_(None), training_models.TrainingEvent.ends_on >= start_date),
    ).order_by(training_models.TrainingEventParticipant.user_id.asc(), training_models.TrainingEvent.starts_on.asc()).all()
    windows = {
        row.training_event_id: row
        for row in db.query(workforce_models.TrainingEventTimeWindow).filter(
            workforce_models.TrainingEventTimeWindow.amo_id == assignments[0].amo_id,
            workforce_models.TrainingEventTimeWindow.training_event_id.in_([participant.event_id for participant in participants] or ["__none__"]),
        ).all()
    }
    by_user: dict[str, list[tuple[training_models.TrainingEventParticipant, datetime, datetime, bool]]] = defaultdict(list)
    for participant in participants:
        event = participant.event
        precise = windows.get(event.id)
        if precise:
            event_start, event_end, date_only = precise.starts_at, precise.ends_at, False
        else:
            event_start = datetime.combine(event.starts_on, time.min, tzinfo=UTC)
            event_end = datetime.combine((event.ends_on or event.starts_on) + timedelta(days=1), time.min, tzinfo=UTC)
            date_only = True
        by_user[participant.user_id].append((participant, event_start, event_end, date_only))
    findings: list[FindingSpec] = []
    for assignment in assignments:
        if not _is_productive(assignment):
            continue
        for participant, event_start, event_end, date_only in by_user.get(assignment.user_id, []):
            if workforce_calculations.interval_overlaps(assignment.starts_at, assignment.ends_at, event_start, event_end):
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.TRAINING,
                    severity=models.RosterValidationSeverity.BLOCKER,
                    code="TRAINING_EVENT_CONFLICT",
                    message=f"Duty conflicts with training event '{participant.event.title}'.",
                    assignment_id=assignment.id,
                    user_id=assignment.user_id,
                    details={"training_event_id": participant.event_id, "event_start": event_start.isoformat(), "event_end": event_end.isoformat(), "date_only_fallback": date_only},
                    overridable=False,
                    sort_order=75,
                ))
    return findings


def _training_validity_findings(db: Session, assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule]) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    assignments_by_user: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for row in assignments:
        if _is_productive(row):
            assignments_by_user[row.user_id].append(row)
    for user_id, rows in assignments_by_user.items():
        user = rows[0].user
        if not user:
            continue
        try:
            courses = training_compliance.get_courses_for_user(db, user, required_only=True)
            latest = training_compliance._latest_records_for_user(db, user, [course.id for course in courses])
        except Exception:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.TRAINING,
                severity=models.RosterValidationSeverity.WARNING,
                code="TRAINING_COMPLIANCE_UNAVAILABLE",
                message="Training compliance could not be calculated for this person.",
                user_id=user_id,
                details={"user_id": user_id},
                sort_order=78,
            ))
            continue
        for row in rows:
            rule = find_rule(rules, models.RosterRuleType.TRAINING_VALIDITY, row)
            warning_days = int(_rule_parameters(rule).get("warning_days", 30)) if rule else 30
            duty_date = row.ends_at.date()
            for course in courses:
                record = latest.get(course.id)
                valid_until = getattr(record, "valid_until", None) if record else None
                if record is None or (valid_until is not None and valid_until < duty_date):
                    findings.append(FindingSpec(
                        source=models.RosterValidationSource.TRAINING,
                        severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                        code="MANDATORY_TRAINING_INVALID",
                        message=f"Mandatory training '{course.course_name}' is missing or expired for this duty.",
                        assignment_id=row.id,
                        user_id=user_id,
                        rule_id=getattr(rule, "id", None),
                        details={"course_id": course.id, "course_code": course.course_id, "valid_until": valid_until.isoformat() if valid_until else None, "duty_date": duty_date.isoformat()},
                        overridable=_overridable(rule),
                        sort_order=80,
                    ))
                elif valid_until is not None and valid_until <= duty_date + timedelta(days=warning_days):
                    findings.append(FindingSpec(
                        source=models.RosterValidationSource.TRAINING,
                        severity=models.RosterValidationSeverity.WARNING,
                        code="MANDATORY_TRAINING_DUE_SOON",
                        message=f"Mandatory training '{course.course_name}' expires within {warning_days} days of this duty.",
                        assignment_id=row.id,
                        user_id=user_id,
                        rule_id=getattr(rule, "id", None),
                        details={"course_id": course.id, "course_code": course.course_id, "valid_until": valid_until.isoformat(), "warning_days": warning_days},
                        overridable=True,
                        sort_order=82,
                    ))
    return findings


def _licence_and_authorisation_findings(db: Session, assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule]) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    auth_cache: dict[str, list[account_models.UserAuthorisation]] = {}
    for row in assignments:
        if not _is_productive(row) or not row.user:
            continue
        rule = find_rule(rules, models.RosterRuleType.LICENCE_VALIDITY, row)
        duty_date = row.ends_at.date()
        expiry = row.user.licence_expires_on
        role_requires_licence = _is_certifying(row.user) or bool(row.role_label and any(token in row.role_label.lower() for token in ("cert", "inspect", "release", "crs")))
        if role_requires_licence and (not row.user.licence_number or not expiry or expiry < duty_date):
            findings.append(FindingSpec(
                source=models.RosterValidationSource.AUTHORISATION,
                severity=_severity(rule, models.RosterValidationSeverity.BLOCKER),
                code="LICENCE_INVALID",
                message="A valid maintenance licence is required for the assigned role.",
                assignment_id=row.id,
                user_id=row.user_id,
                rule_id=getattr(rule, "id", None),
                details={"licence_number": row.user.licence_number, "licence_expires_on": expiry.isoformat() if expiry else None, "duty_date": duty_date.isoformat()},
                overridable=_overridable(rule),
                sort_order=85,
            ))
        elif expiry and expiry <= duty_date + timedelta(days=int(_rule_parameters(rule).get("warning_days", 30)) if rule else 30):
            findings.append(FindingSpec(
                source=models.RosterValidationSource.AUTHORISATION,
                severity=models.RosterValidationSeverity.WARNING,
                code="LICENCE_DUE_SOON",
                message="The maintenance licence expires close to this duty.",
                assignment_id=row.id,
                user_id=row.user_id,
                details={"licence_expires_on": expiry.isoformat(), "duty_date": duty_date.isoformat()},
                overridable=True,
                sort_order=86,
            ))
        if role_requires_licence:
            if row.user_id not in auth_cache:
                auth_cache[row.user_id] = db.query(account_models.UserAuthorisation).options(selectinload(account_models.UserAuthorisation.authorisation_type)).filter(account_models.UserAuthorisation.user_id == row.user_id).all()
            valid = [auth for auth in auth_cache[row.user_id] if auth.is_currently_valid(duty_date)]
            if not valid:
                findings.append(FindingSpec(
                    source=models.RosterValidationSource.AUTHORISATION,
                    severity=models.RosterValidationSeverity.BLOCKER,
                    code="AUTHORISATION_INVALID",
                    message="No current AMO authorisation covers the assigned certifying or inspection role.",
                    assignment_id=row.id,
                    user_id=row.user_id,
                    details={"duty_date": duty_date.isoformat(), "role_label": row.role_label},
                    overridable=False,
                    sort_order=88,
                ))
    return findings


def _coverage_findings(db: Session, assignments: Sequence[models.RosterAssignment], rules: Sequence[models.RosterRule], version: models.RosterVersion) -> list[FindingSpec]:
    findings: list[FindingSpec] = []
    period_start = datetime.combine(version.period.starts_on, time.min, tzinfo=UTC)
    period_end = datetime.combine(version.period.ends_on + timedelta(days=1), time.min, tzinfo=UTC)
    demands = db.query(models.RosterDemandRequirement).filter(
        models.RosterDemandRequirement.amo_id == version.amo_id,
        models.RosterDemandRequirement.is_active.is_(True),
        models.RosterDemandRequirement.starts_at < period_end,
        models.RosterDemandRequirement.ends_at > period_start,
    ).order_by(models.RosterDemandRequirement.starts_at.asc(), models.RosterDemandRequirement.requirement_code.asc(), models.RosterDemandRequirement.id.asc()).all()
    auth_cache: dict[str, list[account_models.UserAuthorisation]] = {}
    for demand in demands:
        matching = [row for row in assignments if _is_productive(row) and row.starts_at < demand.ends_at and row.ends_at > demand.starts_at]
        if demand.base_station_id:
            matching = [row for row in matching if row.base_station_id == demand.base_station_id]
        if demand.department_id:
            matching = [row for row in matching if row.department_id == demand.department_id]
        if demand.role_label:
            token = demand.role_label.strip().lower()
            matching = [row for row in matching if token in (row.role_label or "").lower()]
        if demand.authorisation_type_id:
            authorised: list[models.RosterAssignment] = []
            for row in matching:
                if row.user_id not in auth_cache:
                    auth_cache[row.user_id] = db.query(account_models.UserAuthorisation).filter(account_models.UserAuthorisation.user_id == row.user_id).all()
                if any(auth.authorisation_type_id == demand.authorisation_type_id and auth.is_currently_valid(demand.starts_at.date()) for auth in auth_cache[row.user_id]):
                    authorised.append(row)
            matching = authorised
        headcount = len({row.user_id for row in matching})
        minutes = sum(workforce_calculations.overlap_minutes(row.starts_at, row.ends_at, demand.starts_at, demand.ends_at) for row in matching)
        if headcount < demand.required_headcount or minutes < demand.required_minutes:
            findings.append(FindingSpec(
                source=models.RosterValidationSource.WORKLOAD,
                severity=models.RosterValidationSeverity.BLOCKER,
                code="DEMAND_COVERAGE_GAP",
                message=f"Coverage requirement '{demand.label}' is not met.",
                details={"demand_requirement_id": demand.id, "required_headcount": demand.required_headcount, "actual_headcount": headcount, "required_minutes": demand.required_minutes, "actual_minutes": minutes, "starts_at": demand.starts_at.isoformat(), "ends_at": demand.ends_at.isoformat()},
                overridable=True,
                sort_order=90,
            ))

    coverage_rule = find_rule(rules, models.RosterRuleType.REQUIRED_CERTIFYING_COVERAGE)
    if coverage_rule:
        parameters = _rule_parameters(coverage_rule)
        minimum = max(int(parameters.get("minimum_headcount", 1)), 0)
        bucket_minutes = max(int(parameters.get("bucket_minutes", 720)), 60)
        cursor = period_start
        while cursor < period_end:
            bucket_end = min(cursor + timedelta(minutes=bucket_minutes), period_end)
            productive = [row for row in assignments if _is_productive(row) and row.starts_at < bucket_end and row.ends_at > cursor]
            if productive:
                certifying = {row.user_id for row in productive if _is_certifying(row.user)}
                if len(certifying) < minimum:
                    findings.append(FindingSpec(
                        source=models.RosterValidationSource.AUTHORISATION,
                        severity=coverage_rule.severity,
                        code=coverage_rule.code,
                        message=f"Only {len(certifying)} certifying staff cover this active duty window; minimum is {minimum}.",
                        rule_id=coverage_rule.id,
                        details={"starts_at": cursor.isoformat(), "ends_at": bucket_end.isoformat(), "actual_headcount": len(certifying), "minimum_headcount": minimum},
                        overridable=coverage_rule.allow_override,
                        sort_order=92,
                    ))
            cursor = bucket_end
    return findings


def build_findings(db: Session, *, version: models.RosterVersion, rules: Sequence[models.RosterRule]) -> list[FindingSpec]:
    assignments = [row for row in version.assignments or [] if row.deleted_at is None]
    assignments.sort(key=lambda item: (item.user_id, item.starts_at, item.ends_at, item.id))
    timezone_name = version.period.timezone_name or "UTC"
    findings: list[FindingSpec] = []
    findings.extend(_base_integrity_findings(version, assignments))
    findings.extend(_overlap_and_rest_findings(assignments, rules))
    findings.extend(_duty_limit_findings(assignments, rules, timezone_name))
    findings.extend(_contract_findings(db, assignments, rules))
    findings.extend(_availability_findings(db, assignments, rules))
    findings.extend(_training_event_findings(db, assignments))
    findings.extend(_training_validity_findings(db, assignments, rules))
    findings.extend(_licence_and_authorisation_findings(db, assignments, rules))
    findings.extend(_coverage_findings(db, assignments, rules, version))
    findings.sort(key=lambda item: (item.sort_order, _enum_value(item.severity), item.code, item.user_id or "", item.assignment_id or "", item.message))
    return findings


def _active_exceptions(db: Session, *, version: models.RosterVersion) -> list[models.RosterRuleException]:
    now = _utcnow()
    return db.query(models.RosterRuleException).filter(
        models.RosterRuleException.amo_id == version.amo_id,
        models.RosterRuleException.version_id == version.id,
        models.RosterRuleException.decision != models.RosterExceptionDecision.REVOKE,
        or_(models.RosterRuleException.expires_at.is_(None), models.RosterRuleException.expires_at >= now),
    ).order_by(models.RosterRuleException.created_at.desc(), models.RosterRuleException.id.desc()).all()


def _matching_exception(spec: FindingSpec, exceptions: Sequence[models.RosterRuleException]) -> Optional[models.RosterRuleException]:
    for row in exceptions:
        if row.rule_id and row.rule_id != spec.rule_id:
            continue
        if row.assignment_id and row.assignment_id != spec.assignment_id:
            continue
        if row.user_id and row.user_id != spec.user_id:
            continue
        if row.finding and row.finding.code != spec.code:
            continue
        if spec.severity == models.RosterValidationSeverity.BLOCKER and row.decision != models.RosterExceptionDecision.OVERRIDE_BLOCKER:
            continue
        if spec.severity != models.RosterValidationSeverity.BLOCKER and row.decision not in {models.RosterExceptionDecision.ACCEPT_WARNING, models.RosterExceptionDecision.OVERRIDE_BLOCKER}:
            continue
        return row
    return None


def run_validation(db: Session, *, version: models.RosterVersion, actor_user_id: Optional[str] = None) -> schemas.RosterValidationResult:
    rules = active_rules(db, amo_id=version.amo_id, on_date=version.period.starts_on)
    specs = build_findings(db, version=version, rules=rules)
    exceptions = _active_exceptions(db, version=version)
    db.query(models.RosterValidationFinding).filter(models.RosterValidationFinding.version_id == version.id).delete(synchronize_session=False)
    db.flush()
    persisted: list[models.RosterValidationFinding] = []
    for spec in specs:
        exception = _matching_exception(spec, exceptions) if spec.overridable else None
        row = models.RosterValidationFinding(
            amo_id=version.amo_id,
            version_id=version.id,
            assignment_id=spec.assignment_id,
            user_id=spec.user_id,
            rule_id=spec.rule_id,
            source=spec.source,
            severity=spec.severity,
            code=spec.code,
            message=spec.message,
            details_json=spec.details or None,
            overridable=spec.overridable,
            resolved=exception is not None,
            overridden_at=exception.created_at if exception else None,
            overridden_by_user_id=exception.approved_by_user_id if exception else None,
            override_reason=exception.reason if exception else None,
            sort_order=spec.sort_order,
        )
        db.add(row)
        db.flush()
        if exception and exception.finding_id != row.id:
            exception.finding_id = row.id
            db.add(exception)
        persisted.append(row)
    version.last_validated_at = _utcnow()
    version.validation_fingerprint = _fingerprint(version, [row for row in version.assignments or [] if row.deleted_at is None], rules)
    db.add(version)
    db.flush()
    blocker_count = sum(1 for row in persisted if row.severity == models.RosterValidationSeverity.BLOCKER and not row.resolved)
    warning_count = sum(1 for row in persisted if row.severity == models.RosterValidationSeverity.WARNING and not row.resolved)
    info_count = sum(1 for row in persisted if row.severity == models.RosterValidationSeverity.INFO and not row.resolved)
    overridden_count = sum(1 for row in persisted if row.resolved and row.overridden_at is not None)
    return schemas.RosterValidationResult(
        version_id=version.id,
        validation_fingerprint=version.validation_fingerprint,
        blocker_count=blocker_count,
        warning_count=warning_count,
        info_count=info_count,
        overridden_count=overridden_count,
        can_submit=blocker_count == 0,
        can_publish=blocker_count == 0 and version.status in {models.RosterVersionStatus.APPROVED, models.RosterVersionStatus.PUBLISHED},
        findings=[schemas.RosterValidationFindingRead.model_validate(row) for row in persisted],
    )


def override_finding(
    db: Session,
    *,
    finding: models.RosterValidationFinding,
    actor_user_id: str,
    payload: schemas.RosterRuleOverrideRequest,
) -> models.RosterRuleException:
    if not finding.overridable:
        raise ValueError("This validation finding cannot be overridden")
    if finding.severity == models.RosterValidationSeverity.BLOCKER and payload.decision != models.RosterExceptionDecision.OVERRIDE_BLOCKER:
        raise ValueError("Blocker findings require OVERRIDE_BLOCKER decision")
    if finding.severity != models.RosterValidationSeverity.BLOCKER and payload.decision == models.RosterExceptionDecision.REVOKE:
        raise ValueError("Use the exception revoke endpoint to revoke an override")
    exception = models.RosterRuleException(
        amo_id=finding.amo_id,
        version_id=finding.version_id,
        finding_id=finding.id,
        rule_id=finding.rule_id,
        assignment_id=finding.assignment_id,
        user_id=finding.user_id,
        decision=payload.decision,
        reason=payload.reason,
        approved_by_user_id=actor_user_id,
        expires_at=payload.expires_at,
    )
    db.add(exception)
    finding.resolved = True
    finding.overridden_at = _utcnow()
    finding.overridden_by_user_id = actor_user_id
    finding.override_reason = payload.reason
    db.add(finding)
    db.flush()
    return exception
