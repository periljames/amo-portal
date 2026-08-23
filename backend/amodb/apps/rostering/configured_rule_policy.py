from __future__ import annotations

"""Keep roster compliance rules tenant-configured instead of implicitly seeded.

Older catalogue/validation code still calls ``validation.seed_default_rules`` and
expects ``governance.seed_default_rule_set``. Governance intentionally removed
that implicit bootstrap because a multi-tenant AMO portal must not silently
install an operator/manual/regulatory profile. This compatibility policy closes
that stale seam without reintroducing hard-coded duty/rest values.
"""

from datetime import date

from sqlalchemy import or_

from . import governance, models, validation

_INSTALLED = False


def _configured_rules_only(_db, *, amo_id: str, actor_user_id: str | None = None) -> None:
    """Legacy compatibility hook: never create platform-owned default rules."""

    del amo_id, actor_user_id
    return None


def _configured_active_rules(db, *, amo_id: str, on_date: date) -> list[models.RosterRule]:
    """Return only rules belonging to an active/effective governed rule set.

    A rule with a missing parent set, an inactive parent set or a parent set that
    is not effective on the validation date cannot govern a roster. Rule-level
    active/effective dates are enforced as well. This prevents retired or legacy
    ungoverned records from blocking planner mutations after default seeding was
    removed.
    """

    return (
        db.query(models.RosterRule)
        .join(models.RosterRuleSet, models.RosterRule.rule_set_id == models.RosterRuleSet.id)
        .filter(
            models.RosterRule.amo_id == amo_id,
            models.RosterRuleSet.amo_id == amo_id,
            models.RosterRule.is_active.is_(True),
            models.RosterRuleSet.is_active.is_(True),
            or_(models.RosterRule.effective_from.is_(None), models.RosterRule.effective_from <= on_date),
            or_(models.RosterRule.effective_to.is_(None), models.RosterRule.effective_to >= on_date),
            or_(models.RosterRuleSet.effective_from.is_(None), models.RosterRuleSet.effective_from <= on_date),
            or_(models.RosterRuleSet.effective_to.is_(None), models.RosterRuleSet.effective_to >= on_date),
        )
        .order_by(
            models.RosterRuleSet.priority.asc(),
            models.RosterRule.display_order.asc(),
            models.RosterRule.code.asc(),
            models.RosterRule.id.asc(),
        )
        .all()
    )


def install_service_policy(service_module) -> None:
    """Disable implicit defaults and make governed rule use explicit.

    Validation is constrained to active/effective tenant rule sets. Existing
    callers may omit ``rule_set_id`` when creating a rule only when exactly one
    active governed set exists; otherwise the caller receives an actionable
    domain error rather than an AttributeError or an invented platform rule set.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    validation.seed_default_rules = _configured_rules_only
    validation.active_rules = _configured_active_rules

    original_create_rule = service_module.create_rule

    def create_rule(db, *, amo_id: str, actor_user_id: str, payload):
        if getattr(payload, "rule_set_id", None):
            return original_create_rule(
                db,
                amo_id=amo_id,
                actor_user_id=actor_user_id,
                payload=payload,
            )

        rule_sets = governance.list_rule_sets(db, amo_id=amo_id, include_inactive=False)
        if not rule_sets:
            raise ValueError(
                "Create an active governed roster rule set in Setup before adding compliance rules."
            )
        if len(rule_sets) > 1:
            raise ValueError(
                "Select the governed roster rule set for this compliance rule."
            )

        resolved_payload = payload.model_copy(update={"rule_set_id": rule_sets[0].id})
        return original_create_rule(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            payload=resolved_payload,
        )

    service_module.create_rule = create_rule
    _INSTALLED = True


__all__ = ["install_service_policy"]
