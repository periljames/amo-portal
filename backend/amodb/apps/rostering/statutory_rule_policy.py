from __future__ import annotations

from . import models, validation

_INSTALLED = False

HARD_AVIATION_RULE_TYPES = {
    models.RosterRuleType.MAX_ASSIGNMENT_DURATION,
    models.RosterRuleType.MAX_DUTY_HOURS_DAY,
    models.RosterRuleType.MIN_REST_HOURS,
}


def is_hard_aviation_rule(row: models.RosterRule | None) -> bool:
    return bool(row and row.rule_type in HARD_AVIATION_RULE_TYPES)


def install() -> None:
    """Make maintenance duty-duration and prior-rest rules server-side hard limits."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_active = validation.active_rules
    original_override = validation.override_finding

    def active_rules(db, *, amo_id: str, on_date):
        rows = original_active(db, amo_id=amo_id, on_date=on_date)
        for row in rows:
            if is_hard_aviation_rule(row):
                row.severity = models.RosterValidationSeverity.BLOCKER
                row.allow_override = False
        return rows

    def override_finding(db, *, finding, actor_user_id: str, payload):
        rule = getattr(finding, "rule", None)
        if rule is None and getattr(finding, "rule_id", None):
            rule = db.query(models.RosterRule).filter(
                models.RosterRule.amo_id == finding.amo_id,
                models.RosterRule.id == finding.rule_id,
            ).first()
        if is_hard_aviation_rule(rule):
            raise ValueError(
                "This aviation duty/rest rule cannot be overridden by personnel consent, "
                "managerial approval or administrator action."
            )
        return original_override(
            db,
            finding=finding,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    validation.active_rules = active_rules
    validation.override_finding = override_finding
    _INSTALLED = True


__all__ = ["HARD_AVIATION_RULE_TYPES", "install", "is_hard_aviation_rule"]
