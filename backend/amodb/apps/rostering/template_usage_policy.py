from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session, noload, selectinload

from ..workforce import models as workforce_models
from . import common, models
from .code_registry_models import (
    RosterCalendarMode,
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)
from .roster_control_models import RosterShiftAlias

_COMPACT_CODE_RE = re.compile(r"^[A-Z0-9]{1,2}$")


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
    alias_count = int(
        db.query(func.count(RosterShiftAlias.id))
        .filter(
            RosterShiftAlias.amo_id == amo_id,
            RosterShiftAlias.shift_template_id == template_id,
        )
        .scalar()
        or 0
    )
    return assignment_count + rule_count + pattern_day_count + alias_count


def _template_signature(row: models.ShiftTemplate) -> tuple[str, str, str, bool]:
    return (
        str(getattr(row.kind, "value", row.kind)),
        str(row.default_start_time or ""),
        str(row.default_end_time or ""),
        bool(row.counts_as_duty),
    )


def _policy_signature(row: RosterShiftTemplatePolicy) -> tuple[str, str, int]:
    return (
        str(getattr(row.calendar_mode, "value", row.calendar_mode)),
        str(getattr(row.duty_semantic, "value", row.duty_semantic)),
        int(row.unpaid_break_minutes or 0),
    )


def _default_policy_signature(template: models.ShiftTemplate) -> tuple[str, str, int]:
    calendar_mode = (
        RosterCalendarMode.ALL_DAY
        if template.kind in {models.ShiftTemplateKind.OFF, models.ShiftTemplateKind.LEAVE}
        else RosterCalendarMode.TIMED
    )
    semantic = {
        models.ShiftTemplateKind.STANDBY: RosterDutySemantic.STANDBY,
        models.ShiftTemplateKind.TRAINING: RosterDutySemantic.TRAINING,
        models.ShiftTemplateKind.OFF: RosterDutySemantic.OFF,
        models.ShiftTemplateKind.LEAVE: RosterDutySemantic.LEAVE,
    }.get(template.kind, RosterDutySemantic.DUTY)
    return calendar_mode.value, semantic.value, 0


def _effective_policy_signature(
    policy: RosterShiftTemplatePolicy | None,
    template: models.ShiftTemplate,
) -> tuple[str, str, int]:
    return _policy_signature(policy) if policy is not None else _default_policy_signature(template)


def _policy_snapshot(
    policy: RosterShiftTemplatePolicy | None,
    template: models.ShiftTemplate,
) -> dict[str, object]:
    calendar_mode, duty_semantic, unpaid_break_minutes = _effective_policy_signature(policy, template)
    return {
        "calendar_mode": calendar_mode,
        "duty_semantic": duty_semantic,
        "unpaid_break_minutes": unpaid_break_minutes,
        "verification_status": str(getattr(policy.verification_status, "value", policy.verification_status)) if policy else RosterCodeVerificationStatus.UNRESOLVED.value,
        "effective_from": policy.effective_from.isoformat() if policy and policy.effective_from else None,
        "effective_to": policy.effective_to.isoformat() if policy and policy.effective_to else None,
        "source_reference": policy.source_reference if policy else None,
        "stored": policy is not None,
    }


def _persist_default_policy(
    db: Session,
    *,
    amo_id: str,
    template: models.ShiftTemplate,
    actor_user_id: str,
) -> RosterShiftTemplatePolicy:
    calendar_mode, duty_semantic, unpaid_break_minutes = _default_policy_signature(template)
    row = RosterShiftTemplatePolicy(
        amo_id=amo_id,
        shift_template_id=template.id,
        calendar_mode=RosterCalendarMode(calendar_mode),
        duty_semantic=RosterDutySemantic(duty_semantic),
        unpaid_break_minutes=unpaid_break_minutes,
        verification_status=RosterCodeVerificationStatus.UNRESOLVED,
        source_reference="Canonical shift defaults confirmed during duplicate-code merge.",
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def _copy_policy(
    db: Session,
    *,
    source_policy: RosterShiftTemplatePolicy | None,
    source_template: models.ShiftTemplate,
    target_policy: RosterShiftTemplatePolicy | None,
    target_template: models.ShiftTemplate,
    amo_id: str,
    actor_user_id: str,
) -> RosterShiftTemplatePolicy:
    """Apply the complete source policy to the canonical target policy row."""
    if target_policy is None:
        target_policy = _persist_default_policy(
            db,
            amo_id=amo_id,
            template=target_template,
            actor_user_id=actor_user_id,
        )
    if source_policy is None:
        calendar_mode, duty_semantic, unpaid_break_minutes = _default_policy_signature(source_template)
        target_policy.calendar_mode = RosterCalendarMode(calendar_mode)
        target_policy.duty_semantic = RosterDutySemantic(duty_semantic)
        target_policy.unpaid_break_minutes = unpaid_break_minutes
        target_policy.verification_status = RosterCodeVerificationStatus.UNRESOLVED
        target_policy.effective_from = None
        target_policy.effective_to = None
        target_policy.source_reference = "Inherited default policy during duplicate-code merge."
    else:
        for field in (
            "unpaid_break_minutes",
            "calendar_mode",
            "duty_semantic",
            "verification_status",
            "effective_from",
            "effective_to",
            "source_reference",
        ):
            setattr(target_policy, field, getattr(source_policy, field))
    target_policy.updated_by_user_id = actor_user_id
    db.add(target_policy)
    return target_policy


def merge_duplicate_template(
    db: Session,
    *,
    amo_id: str,
    source_template_id: str,
    target_template_id: str,
    actor_user_id: str,
    reason: str,
    target_code: str | None = None,
    policy_resolution: str = "REQUIRE_MATCH",
) -> tuple[models.ShiftTemplate, dict[str, int]]:
    """Move all live references to a compatible canonical shift, then delete the duplicate."""
    if source_template_id == target_template_id:
        raise ValueError("Choose a different canonical shift code")
    rows = (
        db.query(models.ShiftTemplate)
        .options(
            noload(models.ShiftTemplate.assignments),
            selectinload(models.ShiftTemplate.departments),
        )
        .filter(
            models.ShiftTemplate.amo_id == amo_id,
            models.ShiftTemplate.id.in_([source_template_id, target_template_id]),
        )
        .with_for_update()
        .all()
    )
    by_id = {str(row.id): row for row in rows}
    source = by_id.get(source_template_id)
    target = by_id.get(target_template_id)
    if source is None or target is None:
        raise LookupError("Source or canonical shift template was not found")
    if not target.is_active:
        raise ValueError("The canonical shift code must be active")
    if _template_signature(source) != _template_signature(target):
        raise ValueError(
            "Only shifts with the same type, hours and duty meaning can be merged"
        )
    canonical_code = str(target_code or target.code or "").strip().upper()
    if not _COMPACT_CODE_RE.fullmatch(canonical_code):
        raise ValueError("The canonical shift must use a one or two character code")
    code_owner = db.query(models.ShiftTemplate.id).filter(
        models.ShiftTemplate.amo_id == amo_id,
        func.upper(models.ShiftTemplate.code) == canonical_code,
        models.ShiftTemplate.id != target.id,
    ).first()
    if code_owner:
        raise ValueError(f"Roster code {canonical_code} already exists for this tenant")

    before = {
        "source": {
            "id": source.id,
            "code": source.code,
            "label": source.label,
            "department_ids": source.department_ids,
        },
        "target": {
            "id": target.id,
            "code": target.code,
            "label": target.label,
            "department_ids": target.department_ids,
        },
    }
    source_policy = db.query(RosterShiftTemplatePolicy).filter(
        RosterShiftTemplatePolicy.amo_id == amo_id,
        RosterShiftTemplatePolicy.shift_template_id == source.id,
    ).first()
    target_policy = db.query(RosterShiftTemplatePolicy).filter(
        RosterShiftTemplatePolicy.amo_id == amo_id,
        RosterShiftTemplatePolicy.shift_template_id == target.id,
    ).first()
    source_policy_before = _policy_snapshot(source_policy, source)
    target_policy_before = _policy_snapshot(target_policy, target)
    policy_fields = (
        "calendar_mode",
        "duty_semantic",
        "unpaid_break_minutes",
        "verification_status",
        "effective_from",
        "effective_to",
        "source_reference",
    )
    differences = [
        field
        for field in policy_fields
        if source_policy_before[field] != target_policy_before[field]
    ]
    policies_differ = bool(differences)
    if policies_differ and policy_resolution not in {"KEEP_TARGET", "KEEP_SOURCE"}:
        raise ValueError(
            "These codes differ in " + ", ".join(differences) + ". Choose which shift policy to keep before merging"
        )

    moved_counts = {
        "roster_assignments": db.query(models.RosterAssignment).filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterAssignment.shift_template_id == source.id,
        ).update({models.RosterAssignment.shift_template_id: target.id}, synchronize_session=False),
        "validation_rules": db.query(models.RosterRule).filter(
            models.RosterRule.amo_id == amo_id,
            models.RosterRule.shift_template_id == source.id,
        ).update({models.RosterRule.shift_template_id: target.id}, synchronize_session=False),
        "work_pattern_days": db.query(workforce_models.WorkPatternDay).filter(
            workforce_models.WorkPatternDay.amo_id == amo_id,
            workforce_models.WorkPatternDay.shift_template_id == source.id,
        ).update({workforce_models.WorkPatternDay.shift_template_id: target.id}, synchronize_session=False),
        "aliases": db.query(RosterShiftAlias).filter(
            RosterShiftAlias.amo_id == amo_id,
            RosterShiftAlias.shift_template_id == source.id,
        ).update({RosterShiftAlias.shift_template_id: target.id}, synchronize_session=False),
    }

    moved_counts["policies"] = 0
    if policy_resolution == "KEEP_SOURCE":
        target_policy = _copy_policy(
            db,
            source_policy=source_policy,
            source_template=source,
            target_policy=target_policy,
            target_template=target,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
        )
        if source_policy is not None:
            db.delete(source_policy)
        moved_counts["policies"] = 1
    elif policies_differ and policy_resolution == "KEEP_TARGET":
        if target_policy is None:
            target_policy = _persist_default_policy(
                db,
                amo_id=amo_id,
                template=target,
                actor_user_id=actor_user_id,
            )
        if source_policy is not None:
            db.delete(source_policy)
            moved_counts["policies"] = 1
    elif source_policy is not None:
        if target_policy is None:
            source_policy.shift_template_id = target.id
            source_policy.updated_by_user_id = actor_user_id
            db.add(source_policy)
        else:
            db.delete(source_policy)
        moved_counts["policies"] = 1

    # Empty scope means tenant-wide. Preserve that broader meaning when either
    # duplicate is global; otherwise retain the union of both scoped audiences.
    if not target.departments or not source.departments:
        target.departments = []
    else:
        departments = {str(row.id): row for row in target.departments}
        departments.update({str(row.id): row for row in source.departments})
        target.departments = list(departments.values())
    target.code = canonical_code
    target.updated_by_user_id = actor_user_id
    db.add(target)

    db.delete(source)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="ShiftTemplate",
        entity_id=target.id,
        action="merge_duplicate",
        before=before,
        after={
            "canonical_template_id": target.id,
            "canonical_code": target.code,
            "moved_counts": moved_counts,
            "department_ids": target.department_ids,
            "reason": reason.strip(),
            "policy_resolution": policy_resolution,
            "source_policy_before": source_policy_before,
            "target_policy_before": target_policy_before,
        },
        critical=True,
    )
    return target, {key: int(value or 0) for key, value in moved_counts.items()}


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
