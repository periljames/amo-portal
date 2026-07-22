# backend/amodb/apps/rostering/catalog.py
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..workforce import calculations as workforce_calculations
from . import common, models, schemas, validation


def seed_default_shift_templates(db: Session, *, amo_id: str, actor_user_id: Optional[str] = None) -> None:
    defaults = [
        ("DAY", "Day duty", models.ShiftTemplateKind.DAY, "08:00", "17:00", 540, True, "shift-day", "Sun"),
        ("NIGHT", "Night duty", models.ShiftTemplateKind.NIGHT, "18:00", "06:00", 720, True, "shift-night", "Moon"),
        ("STBY", "Standby", models.ShiftTemplateKind.STANDBY, "06:00", "18:00", 720, True, "shift-standby", "Radio"),
        ("TRAIN", "Training", models.ShiftTemplateKind.TRAINING, "08:00", "17:00", 540, False, "shift-training", "GraduationCap"),
        ("OFF", "Off duty", models.ShiftTemplateKind.OFF, None, None, 0, False, "shift-off", "CircleOff"),
        ("LEAVE", "Leave", models.ShiftTemplateKind.LEAVE, None, None, 0, False, "shift-leave", "Palmtree"),
    ]
    existing = {row[0] for row in db.query(models.ShiftTemplate.code).filter(models.ShiftTemplate.amo_id == amo_id).all()}
    for order, (code, label, kind, start, end, minutes, counts, color_token, icon_name) in enumerate(defaults, start=1):
        if code in existing:
            continue
        db.add(models.ShiftTemplate(
            amo_id=amo_id,
            code=code,
            label=label,
            kind=kind,
            default_start_time=start,
            default_end_time=end,
            duration_minutes=minutes,
            counts_as_duty=counts,
            display_order=order * 10,
            color_token=color_token,
            icon_name=icon_name,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        ))
    db.flush()


def list_shift_templates(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.ShiftTemplate]:
    seed_default_shift_templates(db, amo_id=amo_id)
    query = db.query(models.ShiftTemplate).filter(models.ShiftTemplate.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.ShiftTemplate.is_active.is_(True))
    return query.order_by(models.ShiftTemplate.display_order.asc(), models.ShiftTemplate.code.asc(), models.ShiftTemplate.id.asc()).all()


def create_shift_template(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.ShiftTemplateCreate) -> models.ShiftTemplate:
    row = models.ShiftTemplate(
        amo_id=amo_id,
        **common.dump(payload),
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    row.code = row.code.strip().upper()
    row.label = row.label.strip()
    db.add(row)
    db.flush()
    common.audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="ShiftTemplate", entity_id=row.id, action="create", after={"code": row.code, "label": row.label, "kind": common.enum_value(row.kind)})
    return row


def update_shift_template(db: Session, *, row: models.ShiftTemplate, actor_user_id: str, payload: schemas.ShiftTemplateUpdate) -> models.ShiftTemplate:
    before = {"code": row.code, "label": row.label, "kind": common.enum_value(row.kind), "is_active": row.is_active}
    for key, value in common.dump(payload, exclude_unset=True).items():
        if key == "code" and value:
            value = value.strip().upper()
        if key == "label" and value:
            value = value.strip()
        setattr(row, key, value)
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    common.audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="ShiftTemplate", entity_id=row.id, action="update", before=before, after={"code": row.code, "label": row.label, "kind": common.enum_value(row.kind), "is_active": row.is_active})
    return row


def list_periods(
    db: Session,
    *,
    amo_id: str,
    period_status: Optional[models.RosterPeriodStatus] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[models.RosterPeriod]:
    query = db.query(models.RosterPeriod).options(
        selectinload(models.RosterPeriod.versions).selectinload(models.RosterVersion.assignments),
        selectinload(models.RosterPeriod.versions).selectinload(models.RosterVersion.validation_findings),
    ).filter(models.RosterPeriod.amo_id == amo_id)
    if period_status:
        query = query.filter(models.RosterPeriod.status == period_status)
    if from_date:
        query = query.filter(models.RosterPeriod.ends_on >= from_date)
    if to_date:
        query = query.filter(models.RosterPeriod.starts_on <= to_date)
    return query.order_by(models.RosterPeriod.starts_on.desc(), models.RosterPeriod.period_code.desc(), models.RosterPeriod.id.asc()).all()


def create_period(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.RosterPeriodCreate) -> models.RosterPeriod:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    timezone_name = payload.timezone_name or getattr(amo, "time_zone", None) or "UTC"
    workforce_calculations.get_zone(timezone_name)
    row = models.RosterPeriod(
        amo_id=amo_id,
        period_code=payload.period_code.strip().upper(),
        name=payload.name.strip(),
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        notes=payload.notes,
        timezone_name=timezone_name,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="RosterPeriod", entity_id=row.id, action="create", after={"period_code": row.period_code, "starts_on": row.starts_on.isoformat(), "ends_on": row.ends_on.isoformat(), "timezone_name": timezone_name})
    return row


def update_period(db: Session, *, row: models.RosterPeriod, actor_user_id: str, payload: schemas.RosterPeriodUpdate) -> models.RosterPeriod:
    before = {"name": row.name, "status": common.enum_value(row.status), "notes": row.notes, "timezone_name": row.timezone_name}
    for key, value in common.dump(payload, exclude_unset=True).items():
        if key == "timezone_name" and value:
            workforce_calculations.get_zone(value)
        setattr(row, key, value)
    db.add(row)
    db.flush()
    common.audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="RosterPeriod", entity_id=row.id, action="update", before=before, after={"name": row.name, "status": common.enum_value(row.status), "notes": row.notes, "timezone_name": row.timezone_name})
    return row


def _next_version_number(db: Session, *, period_id: str) -> int:
    current = db.query(func.max(models.RosterVersion.version_no)).filter(models.RosterVersion.period_id == period_id).scalar()
    return int(current or 0) + 1


def _copy_assignments(db: Session, *, source: models.RosterVersion, target: models.RosterVersion, actor_user_id: str) -> None:
    for item in sorted([row for row in source.assignments or [] if row.deleted_at is None], key=lambda row: (row.starts_at, row.user_id, row.id)):
        db.add(models.RosterAssignment(
            amo_id=target.amo_id,
            version_id=target.id,
            user_id=item.user_id,
            department_id=item.department_id,
            base_station_id=item.base_station_id,
            shift_template_id=item.shift_template_id,
            status=item.status,
            source=item.source,
            source_reference_id=item.source_reference_id,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            planned_minutes=item.planned_minutes,
            role_label=item.role_label,
            team_code=item.team_code,
            location_label=item.location_label,
            task_note=item.task_note,
            change_reason=item.change_reason,
            locked_after_publish=False,
            state_revision=1,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        ))
    db.flush()


def create_version(
    db: Session,
    *,
    period: models.RosterPeriod,
    actor_user_id: str,
    payload: schemas.RosterVersionCreate,
) -> models.RosterVersion:
    if period.status in {models.RosterPeriodStatus.LOCKED, models.RosterPeriodStatus.ARCHIVED}:
        raise ValueError("Locked or archived roster periods cannot receive a new version")
    if payload.idempotency_key:
        existing = db.query(models.RosterVersion).filter(models.RosterVersion.amo_id == period.amo_id, models.RosterVersion.idempotency_key == payload.idempotency_key).first()
        if existing:
            return existing
    source_id = payload.source_version_id or payload.copy_from_version_id
    source = None
    if source_id:
        source = common.get_version(db, amo_id=period.amo_id, version_id=source_id)
        if not source or source.period_id != period.id:
            raise ValueError("Source roster version was not found in this period")
    if source and source.status == models.RosterVersionStatus.PUBLISHED and not payload.amendment_reason:
        raise ValueError("Published roster amendments require an amendment reason")
    row = models.RosterVersion(
        amo_id=period.amo_id,
        period_id=period.id,
        source_version_id=source.id if source else None,
        version_no=_next_version_number(db, period_id=period.id),
        title=payload.title or (f"Amendment of v{source.version_no}" if source and source.status == models.RosterVersionStatus.PUBLISHED else None),
        change_summary=payload.change_summary,
        amendment_type=payload.amendment_type,
        amendment_reason=payload.amendment_reason,
        effective_from=payload.effective_from,
        idempotency_key=payload.idempotency_key,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    if source:
        _copy_assignments(db, source=source, target=row, actor_user_id=actor_user_id)
    common.audit(db, amo_id=period.amo_id, actor_user_id=actor_user_id, entity_type="RosterVersion", entity_id=row.id, action="create", after={"period_id": period.id, "version_no": row.version_no, "source_version_id": row.source_version_id, "amendment_type": common.enum_value(row.amendment_type) if row.amendment_type else None, "amendment_reason": row.amendment_reason})
    return row


def list_versions(db: Session, *, amo_id: str, period_id: str) -> list[models.RosterVersion]:
    return db.query(models.RosterVersion).options(
        selectinload(models.RosterVersion.assignments),
        selectinload(models.RosterVersion.validation_findings),
    ).filter(models.RosterVersion.amo_id == amo_id, models.RosterVersion.period_id == period_id).order_by(models.RosterVersion.version_no.desc(), models.RosterVersion.id.asc()).all()


def list_rules(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.RosterRule]:
    validation.seed_default_rules(db, amo_id=amo_id)
    query = db.query(models.RosterRule).filter(models.RosterRule.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.RosterRule.is_active.is_(True))
    return query.order_by(models.RosterRule.display_order.asc(), models.RosterRule.code.asc(), models.RosterRule.id.asc()).all()


def create_rule(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.RosterRuleCreate) -> models.RosterRule:
    common.require_department(db, amo_id=amo_id, department_id=payload.department_id)
    common.require_base(db, amo_id=amo_id, base_station_id=payload.base_station_id)
    common.require_shift_template(db, amo_id=amo_id, shift_template_id=payload.shift_template_id)
    if payload.user_id:
        common.require_user(db, amo_id=amo_id, user_id=payload.user_id, active_only=False)
    row = models.RosterRule(amo_id=amo_id, **common.dump(payload), created_by_user_id=actor_user_id, updated_by_user_id=actor_user_id)
    row.code = row.code.strip().upper()
    row.name = row.name.strip()
    db.add(row)
    db.flush()
    common.audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="RosterRule", entity_id=row.id, action="create", after={"code": row.code, "rule_type": common.enum_value(row.rule_type), "scope": common.enum_value(row.scope), "severity": common.enum_value(row.severity), "parameters_json": row.parameters_json})
    return row


def update_rule(db: Session, *, row: models.RosterRule, actor_user_id: str, payload: schemas.RosterRuleUpdate) -> models.RosterRule:
    before = {"name": row.name, "severity": common.enum_value(row.severity), "parameters_json": row.parameters_json, "is_active": row.is_active, "allow_override": row.allow_override}
    for key, value in common.dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    if row.effective_from and row.effective_to and row.effective_to < row.effective_from:
        raise ValueError("effective_to must be on or after effective_from")
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    common.audit(db, amo_id=row.amo_id, actor_user_id=actor_user_id, entity_type="RosterRule", entity_id=row.id, action="update", before=before, after={"name": row.name, "severity": common.enum_value(row.severity), "parameters_json": row.parameters_json, "is_active": row.is_active, "allow_override": row.allow_override}, critical=True)
    return row


def list_demand_requirements(
    db: Session,
    *,
    amo_id: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    base_station_id: Optional[str] = None,
    department_id: Optional[str] = None,
    include_inactive: bool = False,
) -> list[models.RosterDemandRequirement]:
    query = db.query(models.RosterDemandRequirement).filter(models.RosterDemandRequirement.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.RosterDemandRequirement.is_active.is_(True))
    if from_date:
        query = query.filter(models.RosterDemandRequirement.ends_at >= from_date)
    if to_date:
        query = query.filter(models.RosterDemandRequirement.starts_at <= to_date)
    if base_station_id:
        query = query.filter(models.RosterDemandRequirement.base_station_id == base_station_id)
    if department_id:
        query = query.filter(models.RosterDemandRequirement.department_id == department_id)
    return query.order_by(models.RosterDemandRequirement.starts_at.asc(), models.RosterDemandRequirement.requirement_code.asc(), models.RosterDemandRequirement.id.asc()).all()


def create_demand_requirement(db: Session, *, amo_id: str, actor_user_id: str, payload: schemas.RosterDemandRequirementCreate) -> models.RosterDemandRequirement:
    common.require_base(db, amo_id=amo_id, base_station_id=payload.base_station_id)
    common.require_department(db, amo_id=amo_id, department_id=payload.department_id)
    if payload.authorisation_type_id:
        exists = db.query(account_models.AuthorisationType.id).filter(account_models.AuthorisationType.amo_id == amo_id, account_models.AuthorisationType.id == payload.authorisation_type_id).first()
        if not exists:
            raise ValueError("Authorisation type not found in AMO scope")
    row = models.RosterDemandRequirement(amo_id=amo_id, **common.dump(payload), created_by_user_id=actor_user_id, updated_by_user_id=actor_user_id)
    row.requirement_code = row.requirement_code.strip().upper()
    row.label = row.label.strip()
    db.add(row)
    db.flush()
    common.audit(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type="RosterDemandRequirement", entity_id=row.id, action="create", after={"requirement_code": row.requirement_code, "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "required_headcount": row.required_headcount, "required_minutes": row.required_minutes})
    return row


def roster_contracts(db: Session, *, current_user: account_models.User) -> schemas.RosterContractResponse:
    permission_list = list(sorted(__import__("amodb.apps.workforce.permissions", fromlist=["permissions_for_user"]).permissions_for_user(db, user=current_user)))
    capabilities = {
        "view_all": "roster.view_all" in permission_list,
        "edit": "roster.edit" in permission_list,
        "approve": "roster.approve" in permission_list,
        "publish": "roster.publish" in permission_list,
        "manage_rules": "roster.manage_rules" in permission_list,
        "manage_patterns": "roster.manage_patterns" in permission_list,
        "manage_workforce": "workforce.manage_contracts" in permission_list,
        "payroll_export": "payroll.export" in permission_list,
    }
    return schemas.RosterContractResponse(
        canonical_personnel_key="accounts.users.id",
        route_contracts={
            "workforce": "/workforce",
            "rostering": "/rostering",
            "training": "/training",
            "planning": "/planning",
            "work": "/work",
            "foundations": "/foundations",
            "notifications": "/notifications",
        },
        source_modules={
            "identity": "accounts.users",
            "personnel_profile": "accounts.personnel_profiles",
            "employment": "workforce.employment_contracts",
            "patterns": "workforce.work_patterns",
            "leave": "workforce.leave_requests + employee_availability_events",
            "base": "foundations.base_stations",
            "training": "training compliance + event time windows",
            "authorisation": "accounts.user_authorisations",
            "workload": "work.work_orders + task_cards",
            "actual_hours": "work.work_log_entries + workforce.attendance_events",
        },
        phase="complete-workforce-integrated",
        permissions=permission_list,
        capabilities=capabilities,
    )
