# backend/amodb/apps/rostering/services.py
"""Public service facade for the complete duty-rostering domain.

The implementation is split by responsibility to keep lifecycle, assignment,
planning and reporting logic independently testable.  Import service functions
from this module when compatibility with the original Phase 1 import path is
required.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..training import models as training_models
from ..workforce import models as workforce_models
from . import assignments, catalog, common, lifecycle, planning, reports
from .assignments import (
    allocate_to_task,
    bulk_create_assignments,
    create_assignment as _create_assignment,
    delete_assignment,
    generate_from_patterns,
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
    overlap, rest and timesheet calculations.  Earlier seeds marked the default
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
    """Prevent roster-only copies of state owned by Workforce or Training."""
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

    final_date = (ends_at - timedelta(microseconds=1)).date()
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


__all__ = [name for name in globals() if not name.startswith("_")]
