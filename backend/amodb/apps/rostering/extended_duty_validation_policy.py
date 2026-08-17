from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_

from . import compliance_policy, models, validation
from .extended_duty_models import RosterDutyExtension, RosterDutyExtensionStatus

_INSTALLED = False
RECOVERY_REST_CODE = "ROSTER_RECOVERY_REST_REQUIRED"
CONTROLLED_EXTENSION_CODE = "ROSTER_EXTENDED_DUTY_CONTROLLED"


def _controlled_limit(extension: RosterDutyExtension, rule_type: models.RosterRuleType) -> int:
    fatigue = dict(extension.fatigue_risk_json or {})
    if rule_type == models.RosterRuleType.MAX_ASSIGNMENT_DURATION:
        return int(fatigue.get("extended_maximum_minutes") or 0)
    if rule_type == models.RosterRuleType.MAX_DUTY_HOURS_DAY:
        return int(fatigue.get("extended_daily_maximum_minutes") or 0)
    return 0


def _finding_minutes(spec: validation.FindingSpec, rule_type: models.RosterRuleType) -> int:
    details = dict(spec.details or {})
    if rule_type == models.RosterRuleType.MAX_ASSIGNMENT_DURATION:
        return int(details.get("shift_minutes") or 0)
    if rule_type == models.RosterRuleType.MAX_DUTY_HOURS_DAY:
        return int(details.get("planned_minutes") or 0)
    return 0


def recovery_rest_minutes(*, extended_duty_end: datetime, next_duty_start: datetime) -> int:
    """Return complete recovery-rest minutes between two effective duty timestamps."""
    return max(int((next_duty_start - extended_duty_end).total_seconds() // 60), 0)


def install() -> None:
    """Recognize only the governed extension path while preserving all hard rules."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_build = validation.build_findings
    original_override = validation.override_finding

    def build_findings(db, *, version, rules):
        specs = original_build(db, version=version, rules=rules)
        extensions = db.query(RosterDutyExtension).filter(
            RosterDutyExtension.amo_id == version.amo_id,
            RosterDutyExtension.version_id == version.id,
            RosterDutyExtension.status != RosterDutyExtensionStatus.CANCELLED,
        ).all()
        if not extensions:
            return specs

        extension_by_assignment = {row.assignment_id: row for row in extensions}
        rule_ids = {spec.rule_id for spec in specs if spec.rule_id}
        rule_by_id = {
            row.id: row
            for row in db.query(models.RosterRule).filter(
                models.RosterRule.amo_id == version.amo_id,
                models.RosterRule.id.in_(rule_ids),
            ).all()
        } if rule_ids else {}

        governed: list[validation.FindingSpec] = []
        for spec in specs:
            extension = extension_by_assignment.get(str(spec.assignment_id or ""))
            rule = rule_by_id.get(spec.rule_id) if spec.rule_id else None
            controlled_types = {
                models.RosterRuleType.MAX_ASSIGNMENT_DURATION,
                models.RosterRuleType.MAX_DUTY_HOURS_DAY,
            }
            controlled_limit = _controlled_limit(extension, rule.rule_type) if extension is not None and rule is not None else 0
            finding_minutes = _finding_minutes(spec, rule.rule_type) if rule is not None else 0
            if (
                extension is not None
                and rule is not None
                and rule.rule_type in controlled_types
                and extension.proposed_extended_end == extension.assignment.ends_at
                and controlled_limit > 0
                and finding_minutes <= controlled_limit
            ):
                governed.append(validation.FindingSpec(
                    source=models.RosterValidationSource.RULE,
                    severity=models.RosterValidationSeverity.INFO,
                    code=CONTROLLED_EXTENSION_CODE,
                    message=(
                        "Ordinary maintenance duty duration exceeded under the controlled unscheduled-aircraft "
                        "extension path. Personnel acknowledgement, supervisor approval, recovery rest and all "
                        "other hard statutory checks remain mandatory."
                    ),
                    assignment_id=spec.assignment_id,
                    user_id=spec.user_id,
                    rule_id=spec.rule_id,
                    details={
                        "underlying_finding": {
                            "code": spec.code,
                            "message": spec.message,
                            "details": spec.details,
                        },
                        "extension_id": extension.id,
                        "operational_reference": extension.operational_reference,
                        "aircraft_registration": extension.aircraft_registration,
                        "continuous_duty_minutes": extension.continuous_duty_minutes,
                        "controlled_maximum_minutes": controlled_limit,
                        "finding_minutes": finding_minutes,
                        "required_recovery_rest_minutes": extension.required_recovery_rest_minutes,
                    },
                    overridable=False,
                    sort_order=spec.sort_order,
                ))
                continue
            governed.append(spec)

        for extension in extensions:
            required = int(extension.required_recovery_rest_minutes or 0)
            if required <= 0 or extension.assignment is None:
                continue
            assignment = extension.assignment
            threshold = assignment.ends_at + timedelta(minutes=required)
            next_rows = db.query(models.RosterAssignment).join(
                models.RosterVersion,
                models.RosterVersion.id == models.RosterAssignment.version_id,
            ).filter(
                models.RosterAssignment.amo_id == version.amo_id,
                models.RosterAssignment.user_id == assignment.user_id,
                models.RosterAssignment.deleted_at.is_(None),
                models.RosterAssignment.starts_at >= assignment.ends_at,
                models.RosterAssignment.starts_at < threshold,
                or_(
                    models.RosterAssignment.version_id == version.id,
                    models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
                ),
            ).order_by(models.RosterAssignment.starts_at.asc()).all()
            next_duty = next((row for row in next_rows if compliance_policy.assignment_counts_as_duty(row)), None)
            if next_duty is None:
                continue
            actual_rest = recovery_rest_minutes(
                extended_duty_end=assignment.ends_at,
                next_duty_start=next_duty.starts_at,
            )
            governed.append(validation.FindingSpec(
                source=models.RosterValidationSource.RULE,
                severity=models.RosterValidationSeverity.BLOCKER,
                code=RECOVERY_REST_CODE,
                message=(
                    f"Mandatory recovery rest after controlled extended duty is {actual_rest} minutes; "
                    f"the configured requirement is {required} minutes."
                ),
                assignment_id=next_duty.id,
                user_id=assignment.user_id,
                rule_id=None,
                details={
                    "extension_id": extension.id,
                    "extended_assignment_id": assignment.id,
                    "next_assignment_id": next_duty.id,
                    "actual_rest_minutes": actual_rest,
                    "required_rest_minutes": required,
                    "recovery_rest_basis": extension.recovery_rest_basis,
                },
                overridable=False,
                sort_order=36,
            ))
        governed.sort(key=lambda item: (item.sort_order, str(getattr(item.severity, "value", item.severity)), item.code, item.user_id or "", item.assignment_id or ""))
        return governed

    def override_finding(db, *, finding, actor_user_id: str, payload):
        if finding.code in {RECOVERY_REST_CODE, CONTROLLED_EXTENSION_CODE}:
            raise ValueError("Controlled extended-duty statutory controls cannot be overridden internally")
        return original_override(
            db,
            finding=finding,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    validation.build_findings = build_findings
    validation.override_finding = override_finding
    _INSTALLED = True


__all__ = [
    "CONTROLLED_EXTENSION_CODE",
    "RECOVERY_REST_CODE",
    "install",
    "recovery_rest_minutes",
]
