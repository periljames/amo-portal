from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..workforce import models as workforce_models
from . import common, models


def template_usage_count(db: Session, *, amo_id: str, template_id: str) -> int:
    """Count operational references that make a roster code unsafe to delete."""

    assignment_count = int(
        db.query(func.count(models.RosterAssignment.id))
        .filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterAssignment.shift_template_id == template_id,
        )
        .scalar()
        or 0
    )
    rule_count = int(
        db.query(func.count(models.RosterRule.id))
        .filter(
            models.RosterRule.amo_id == amo_id,
            models.RosterRule.shift_template_id == template_id,
        )
        .scalar()
        or 0
    )
    pattern_day_count = int(
        db.query(func.count(workforce_models.WorkPatternDay.id))
        .filter(
            workforce_models.WorkPatternDay.amo_id == amo_id,
            workforce_models.WorkPatternDay.shift_template_id == template_id,
        )
        .scalar()
        or 0
    )
    return assignment_count + rule_count + pattern_day_count


def delete_unused_template(
    db: Session,
    *,
    amo_id: str,
    template_id: str,
    actor_user_id: str,
) -> None:
    row = (
        db.query(models.ShiftTemplate)
        .filter(
            models.ShiftTemplate.amo_id == amo_id,
            models.ShiftTemplate.id == template_id,
        )
        .first()
    )
    if not row:
        raise LookupError("Shift template not found")

    usage = template_usage_count(db, amo_id=amo_id, template_id=template_id)
    if usage:
        raise ValueError(
            "This code is referenced by roster history, validation rules, or workforce patterns and cannot be deleted. "
            "Retire it by setting Active off so operational configuration and historical rosters retain their meaning."
        )

    before = {"code": row.code, "label": row.label, "is_active": row.is_active}
    db.delete(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="ShiftTemplate",
        entity_id=template_id,
        action="delete_unused",
        before=before,
        critical=True,
    )


def install_code_registry_policy(code_registry_module) -> None:
    code_registry_module.template_usage_count = template_usage_count
    code_registry_module.delete_unused_template = delete_unused_template
