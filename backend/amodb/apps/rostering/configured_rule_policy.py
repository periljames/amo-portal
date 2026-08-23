from __future__ import annotations

"""Keep roster compliance rules tenant-configured instead of implicitly seeded.

Older catalogue/validation code still calls ``validation.seed_default_rules`` and
expects ``governance.seed_default_rule_set``. Governance intentionally removed
that implicit bootstrap because a multi-tenant AMO portal must not silently
install an operator/manual/regulatory profile. This compatibility policy closes
that stale seam without reintroducing hard-coded duty/rest values.
"""

from . import governance, validation

_INSTALLED = False


def _configured_rules_only(_db, *, amo_id: str, actor_user_id: str | None = None) -> None:
    """Legacy compatibility hook: configured tenant rules are queried as-is."""

    del amo_id, actor_user_id
    return None


def install_service_policy(service_module) -> None:
    """Disable implicit defaults and make legacy rule creation choose explicitly.

    Existing callers may omit ``rule_set_id``. For compatibility, an omitted ID
    is accepted only when the tenant has exactly one active governed rule set;
    otherwise the caller receives an actionable domain error rather than an
    AttributeError or an invented platform rule set.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    validation.seed_default_rules = _configured_rules_only

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
