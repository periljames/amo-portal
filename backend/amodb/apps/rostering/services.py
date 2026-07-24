# backend/amodb/apps/rostering/services.py
"""Public service facade for the complete duty-rostering domain.

The implementation is split by responsibility to keep lifecycle, assignment,
planning and reporting logic independently testable. Import service functions
from this module when compatibility with the original Phase 1 import path is
required.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..quality import models as quality_models
from ..training import models as training_models
from ..workforce import models as workforce_models
from ..workforce import services as workforce_services
from . import assignments, catalog, common, governance, lifecycle, planning, reports
from .assignments import (
    allocate_to_task,
    bulk_create_assignments as _bulk_create_assignments,
    create_assignment as _create_assignment,
    delete_assignment,
    generate_from_patterns as _generate_from_patterns,
    link_task_assignment,
    list_assignments,
    list_task_links,
    serialize_task_link,
    update_assignment as _update_assignment,
)
from .catalog import (
    create_demand_requirement,
    create_period,
    create_rule,
    create_shift_template,
    create_version,
    list_demand_requirements,
    list_periods,
    list_rules,
    list_shift_templates as _list_shift_templates,
    list_versions,
    roster_contracts,
    seed_default_shift_templates,
    update_period,
    update_rule,
    update_shift_template,
)
from .common import (
    assignment_hours,
    can_approve_roster,
    can_manage_roster,
    can_view_roster,
    effective_amo_id,
    get_assignment,
    get_period,
    get_version,
    serialize_assignment,
    serialize_finding,
    serialize_period,
    serialize_version,
    task_link_hours,
)
from .lifecycle import (
    acknowledge_version,
    approve_version,
    list_exceptions,
    override_finding,
    publish_version,
    revoke_exception,
    submit_version,
    validate_version,
)
from .planning import dashboard, my_roster, planning_board, published_assignments
from .reports import assignment_export_rows, report_summary


def get_effective_amo_id(user: account_models.User) -> str:
    return effective_amo_id(user)


def list_shift_templates(db: Session, *, amo_id: str, include_inactive: bool = False):
    """Return tenant templates while repairing the historical TRAIN semantic.

    Training occupies an employee's working time and must participate in duty,
    overlap, rest and timesheet calculations. Earlier seeds marked the default
    TRAIN template as non-duty; reconcile it whenever templates are loaded so
    both upgraded and newly provisioned tenants receive the canonical meaning.
    """
    rows = _list_shift_templates(db, amo_id=amo_id, include_inactive=include_inactive)
    for row in rows:
        if row.code == "TRAIN" and not row.counts_as_duty:
            row.counts_as_duty = True
            db.add(row)
    db.flush()
    return rows


def _value(value) -> str:
    return str(getattr(value, "value", value))


def _ensure_source_owned_state(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    starts_at,
    ends_at,
    assignment_status,
    assignment_source,
    source_reference_id: Optional[str],
) -> None:
    """Protect canonical Workforce, Training and Quality state at mutation time."""
    status_value = _value(assignment_status)
    source_value = _value(assignment_source)
    external_state = status_value in {"LEAVE", "TRAINING", "UNAVAILABLE"}
    trusted_external_source = source_value in {"LEAVE", "TRAINING", "SYSTEM"} and bool(source_reference_id)
    if external_state and not trusted_external_source:
        owner = "Training" if status_value == "TRAINING" else "Workforce"
        raise ValueError(
            f"{status_value.replace('_', ' ').title()} is owned by the {owner} module. "
            "Create or approve it there; Rostering will display it automatically."
        )

    if trusted_external_source or status_value in {"OFF", "LEAVE", "TRAINING", "UNAVAILABLE"}:
        return

    final_date = (ends_at - timedelta(microseconds=1)).date()
    start_contract = workforce_services.active_contract_for_user(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=starts_at.date(),
    )
    end_contract = workforce_services.active_contract_for_user(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=final_date,
    )
    if not start_contract or not end_contract:
        raise ValueError(
            "This person has no active employment contract for the selected duty period. "
            "Inactive, suspended, terminated and out-of-contract personnel cannot be rostered."
        )

    availability = db.query(workforce_models.EmployeeAvailabilityEvent.id).filter(
        workforce_models.EmployeeAvailabilityEvent.amo_id == amo_id,
        workforce_models.EmployeeAvailabilityEvent.user_id == user_id,
        workforce_models.EmployeeAvailabilityEvent.blocking.is_(True),
        workforce_models.EmployeeAvailabilityEvent.starts_at < ends_at,
        workforce_models.EmployeeAvailabilityEvent.ends_at > starts_at,
    ).first()
    if availability:
        raise ValueError(
            "This person has blocking leave or unavailability in the selected period. "
            "Resolve the Workforce source record before assigning duty."
        )

    training = db.query(training_models.TrainingEventParticipant.id).join(
        training_models.TrainingEvent,
        training_models.TrainingEventParticipant.event_id == training_models.TrainingEvent.id,
    ).filter(
        training_models.TrainingEventParticipant.amo_id == amo_id,
        training_models.TrainingEventParticipant.user_id == user_id,
        training_models.TrainingEventParticipant.status.notin_([
            training_models.TrainingParticipantStatus.CANCELLED,
            training_models.TrainingParticipantStatus.NO_SHOW,
            training_models.TrainingParticipantStatus.DEFERRED,
        ]),
        training_models.TrainingEvent.status != training_models.TrainingEventStatus.CANCELLED,
        training_models.TrainingEvent.starts_on <= final_date,
        or_(
            training_models.TrainingEvent.ends_on.is_(None),
            training_models.TrainingEvent.ends_on >= starts_at.date(),
        ),
    ).first()
    if training:
        raise ValueError(
            "This person is already scheduled for Training in the selected period. "
            "The Training commitment is shown automatically and cannot be overwritten by duty."
        )

    quality_audit = db.query(quality_models.QMSAudit.id).filter(
        quality_models.QMSAudit.amo_id == amo_id,
        quality_models.QMSAudit.deleted_at.is_(None),
        quality_models.QMSAudit.status != quality_models.QMSAuditStatus.CLOSED,
        quality_models.QMSAudit.planned_start.isnot(None),
        quality_models.QMSAudit.planned_start <= final_date,
        or_(
            quality_models.QMSAudit.planned_end.is_(None),
            quality_models.QMSAudit.planned_end >= starts_at.date(),
        ),
        or_(
            quality_models.QMSAudit.lead_auditor_user_id == user_id,
            quality_models.QMSAudit.observer_auditor_user_id == user_id,
            quality_models.QMSAudit.assistant_auditor_user_id == user_id,
            quality_models.QMSAudit.auditee_user_id == user_id,
        ),
    ).first()
    if quality_audit:
        raise ValueError(
            "This person is assigned to a Quality audit in the selected period. "
            "The QMS commitment is shown automatically and cannot be overwritten by duty."
        )


def create_assignment(db: Session, *, version, actor_user_id: str, payload):
    _ensure_source_owned_state(
        db,
        amo_id=version.amo_id,
        user_id=payload.user_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        assignment_status=payload.status,
        assignment_source=payload.source,
        source_reference_id=payload.source_reference_id,
    )
    return _create_assignment(db, version=version, actor_user_id=actor_user_id, payload=payload)


def update_assignment(db: Session, *, row, actor_user_id: str, payload):
    fields = common.model_fields_set(payload)
    _ensure_source_owned_state(
        db,
        amo_id=row.amo_id,
        user_id=row.user_id,
        starts_at=payload.starts_at if "starts_at" in fields else row.starts_at,
        ends_at=payload.ends_at if "ends_at" in fields else row.ends_at,
        assignment_status=payload.status if "status" in fields else row.status,
        assignment_source=row.source,
        source_reference_id=row.source_reference_id,
    )
    return _update_assignment(db, row=row, actor_user_id=actor_user_id, payload=payload)


def _remap_bulk_indexes(entries: list[dict], index_map: list[int]) -> list[dict]:
    remapped: list[dict] = []
    for entry in entries:
        item = dict(entry)
        filtered_index = item.get("index")
        if isinstance(filtered_index, int) and 0 <= filtered_index < len(index_map):
            item["index"] = index_map[filtered_index]
        remapped.append(item)
    return remapped


def bulk_create_assignments(db: Session, *, version, actor_user_id: str, payload):
    """Apply the same source-of-truth guard to bulk and pattern assignments."""
    valid_items = []
    index_map: list[int] = []
    preflight_conflicts: list[dict] = []

    for index, item in enumerate(payload.assignments):
        try:
            _ensure_source_owned_state(
                db,
                amo_id=version.amo_id,
                user_id=item.user_id,
                starts_at=item.starts_at,
                ends_at=item.ends_at,
                assignment_status=item.status,
                assignment_source=item.source,
                source_reference_id=item.source_reference_id,
            )
        except ValueError as exc:
            conflict = {
                "index": index,
                "client_id": getattr(item, "client_id", None),
                "reason": str(exc),
            }
            if payload.atomic:
                raise ValueError(f"Bulk assignment failed at item {index}: {exc}") from exc
            preflight_conflicts.append(conflict)
            continue
        valid_items.append(item)
        index_map.append(index)

    guarded_payload = payload.model_copy(update={"assignments": valid_items})
    result = _bulk_create_assignments(
        db,
        version=version,
        actor_user_id=actor_user_id,
        payload=guarded_payload,
    )
    result.skipped = _remap_bulk_indexes(result.skipped, index_map)
    result.conflicts = preflight_conflicts + _remap_bulk_indexes(result.conflicts, index_map)
    return result


# Pattern generation resolves this module-global function at call time. Rebind
# it once so generated rows cannot bypass the same Workforce/Training/QMS guard.
assignments.bulk_create_assignments = bulk_create_assignments


def generate_from_patterns(db: Session, *, version, actor_user_id: str, payload):
    return _generate_from_patterns(
        db,
        version=version,
        actor_user_id=actor_user_id,
        payload=payload,
    )


def get_shift_template(db: Session, *, amo_id: str, template_id: str):
    from . import models

    return db.query(models.ShiftTemplate).filter(
        models.ShiftTemplate.amo_id == amo_id,
        models.ShiftTemplate.id == template_id,
    ).first()


def get_rule(db: Session, *, amo_id: str, rule_id: str):
    from . import models

    return db.query(models.RosterRule).filter(models.RosterRule.amo_id == amo_id, models.RosterRule.id == rule_id).first()


def get_demand_requirement(db: Session, *, amo_id: str, demand_id: str):
    from . import models

    return db.query(models.RosterDemandRequirement).filter(
        models.RosterDemandRequirement.amo_id == amo_id,
        models.RosterDemandRequirement.id == demand_id,
    ).first()


def get_finding(db: Session, *, amo_id: str, finding_id: str):
    from . import models

    return db.query(models.RosterValidationFinding).filter(
        models.RosterValidationFinding.amo_id == amo_id,
        models.RosterValidationFinding.id == finding_id,
    ).first()


def get_exception(db: Session, *, amo_id: str, exception_id: str):
    from . import models

    return db.query(models.RosterRuleException).filter(
        models.RosterRuleException.amo_id == amo_id,
        models.RosterRuleException.id == exception_id,
    ).first()


def published_version_for_date(db: Session, *, amo_id: str, on_date: date):
    from . import models

    return db.query(models.RosterVersion).join(
        models.RosterPeriod,
        models.RosterVersion.period_id == models.RosterPeriod.id,
    ).filter(
        models.RosterVersion.amo_id == amo_id,
        models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
        models.RosterPeriod.starts_on <= on_date,
        models.RosterPeriod.ends_on >= on_date,
    ).order_by(models.RosterVersion.published_at.desc(), models.RosterVersion.version_no.desc()).first()


list_rule_sets = governance.list_rule_sets
create_rule_set = governance.create_rule_set
update_rule_set = governance.update_rule_set
list_approval_authorities = governance.list_authorities
create_approval_authority = governance.create_authority
update_approval_authority = governance.update_authority
approval_matrix = governance.approval_matrix
request_roster_changes = governance.request_changes


__all__ = [name for name in globals() if not name.startswith("_")]
