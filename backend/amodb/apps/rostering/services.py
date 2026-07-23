# backend/amodb/apps/rostering/services.py
"""Public service facade for the complete duty-rostering domain.

The implementation is split by responsibility to keep lifecycle, assignment,
planning and reporting logic independently testable.  Import service functions
from this module when compatibility with the original Phase 1 import path is
required.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from ..accounts import models as account_models
from . import assignments, catalog, common, lifecycle, planning, reports
from .assignments import (
    allocate_to_task,
    bulk_create_assignments,
    create_assignment,
    delete_assignment,
    generate_from_patterns,
    link_task_assignment,
    list_assignments,
    list_task_links,
    serialize_task_link,
    update_assignment,
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
