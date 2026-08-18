from __future__ import annotations

from .code_registry_models import RosterDutySemantic, RosterShiftTemplatePolicy

_INSTALLED = False


def install(code_registry_module) -> None:
    """Initialize only newly created starter policies from controlled semantics.

    No display code is inspected. Existing tenant-owned policies are left
    untouched; this wrapper only fills the new fields for rows created by the
    starter-pack command in the same transaction.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    original = code_registry_module.install_starter_pack

    def install_starter_pack(db, *, amo_id: str, actor_user_id: str):
        created, skipped = original(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
        )
        created_ids = [row.id for row in created]
        if created_ids:
            policies = db.query(RosterShiftTemplatePolicy).filter(
                RosterShiftTemplatePolicy.amo_id == amo_id,
                RosterShiftTemplatePolicy.shift_template_id.in_(created_ids),
            ).all()
            template_by_id = {row.id: row for row in created}
            for policy in policies:
                template = template_by_id.get(policy.shift_template_id)
                semantic = policy.duty_semantic
                policy.counts_as_rest = bool(
                    template
                    and not template.counts_as_duty
                    and semantic in {RosterDutySemantic.REST, RosterDutySemantic.OFF}
                )
                policy.on_site_availability = bool(
                    template
                    and template.counts_as_duty
                    and semantic == RosterDutySemantic.STANDBY
                )
                policy.scheduling_eligible = True
                db.add(policy)
            db.flush()
        return created, skipped

    code_registry_module.install_starter_pack = install_starter_pack
    _INSTALLED = True


__all__ = ["install"]
