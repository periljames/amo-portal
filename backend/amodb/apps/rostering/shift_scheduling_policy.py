from __future__ import annotations

from . import assignments, consent_service
from .code_registry_models import RosterShiftTemplatePolicy

_INSTALLED = False


def _disabled_template_ids(db, *, amo_id: str, template_ids: set[str]) -> set[str]:
    if not template_ids:
        return set()
    return {
        row.shift_template_id
        for row in db.query(RosterShiftTemplatePolicy).filter(
            RosterShiftTemplatePolicy.amo_id == amo_id,
            RosterShiftTemplatePolicy.shift_template_id.in_(sorted(template_ids)),
            RosterShiftTemplatePolicy.scheduling_eligible.is_(False),
        ).all()
    }


def _require_eligible(db, *, amo_id: str, template_id: str | None) -> None:
    if not template_id:
        return
    if template_id in _disabled_template_ids(db, amo_id=amo_id, template_ids={template_id}):
        raise consent_service.RosterWorkflowError(
            "ROSTER_SHIFT_NOT_SCHEDULABLE",
            "The selected shift is retained for history but is not eligible for new scheduling.",
            {"shift_template_id": template_id},
        )


def _require_bulk_eligible(db, *, amo_id: str, items) -> None:
    template_ids = {
        str(item.shift_template_id)
        for item in items
        if getattr(item, "shift_template_id", None)
    }
    disabled = _disabled_template_ids(db, amo_id=amo_id, template_ids=template_ids)
    if not disabled:
        return
    affected = [
        {
            "index": index,
            "shift_template_id": str(item.shift_template_id),
            "client_id": getattr(item, "client_id", None),
        }
        for index, item in enumerate(items)
        if getattr(item, "shift_template_id", None) in disabled
    ]
    raise consent_service.RosterWorkflowError(
        "ROSTER_SHIFT_NOT_SCHEDULABLE",
        "One or more assignments use a shift that is not eligible for new scheduling.",
        {"disabled_shift_template_ids": sorted(disabled), "affected_items": affected},
    )


def install_service_policy(service_module) -> None:
    """Enforce configured scheduling eligibility at the canonical service seam.

    UI visibility is intentionally not trusted. Direct REST callers, bulk
    planners and generated work patterns are checked on the server. Existing
    historical assignments remain readable because disabling scheduling does
    not rewrite or delete prior roster evidence.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    original_create = service_module.create_assignment
    original_update = service_module.update_assignment
    original_bulk = service_module.bulk_create_assignments
    original_list = service_module.list_shift_templates
    original_assignments_bulk = assignments.bulk_create_assignments

    def create_assignment(db, *, version, actor_user_id: str, payload):
        _require_eligible(
            db,
            amo_id=version.amo_id,
            template_id=getattr(payload, "shift_template_id", None),
        )
        return original_create(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    def update_assignment(db, *, row, actor_user_id: str, payload):
        fields = set(getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set())))
        template_id = payload.shift_template_id if "shift_template_id" in fields else row.shift_template_id
        _require_eligible(db, amo_id=row.amo_id, template_id=template_id)
        return original_update(
            db,
            row=row,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    def bulk_create_assignments(db, *, version, actor_user_id: str, payload):
        _require_bulk_eligible(db, amo_id=version.amo_id, items=payload.assignments)
        return original_bulk(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    def generated_bulk_create_assignments(db, *, version, actor_user_id: str, payload):
        _require_bulk_eligible(db, amo_id=version.amo_id, items=payload.assignments)
        return original_assignments_bulk(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    def list_shift_templates(db, *, amo_id: str, include_inactive: bool = False):
        rows = original_list(db, amo_id=amo_id, include_inactive=include_inactive)
        if include_inactive or not rows:
            return rows
        disabled = _disabled_template_ids(
            db,
            amo_id=amo_id,
            template_ids={row.id for row in rows},
        )
        return [row for row in rows if row.id not in disabled]

    service_module.create_assignment = create_assignment
    service_module.update_assignment = update_assignment
    service_module.bulk_create_assignments = bulk_create_assignments
    service_module.list_shift_templates = list_shift_templates
    # Pattern generation resolves this module-global function at call time.
    assignments.bulk_create_assignments = generated_bulk_create_assignments
    _INSTALLED = True


__all__ = ["install_service_policy"]
