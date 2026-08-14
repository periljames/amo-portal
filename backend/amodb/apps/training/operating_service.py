from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, inspect, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, noload, selectinload

from ..accounts import models as account_models
from ..audit import services as audit_services
from ..quality import models as quality_models
from ..doc_control import models as doc_control_models
from ..realtime import models as realtime_models
from ..tasks import services as task_services
from . import compliance
from . import models as legacy_models
from . import operating_models as models
from . import operating_schemas as schemas
from . import operating_rules as rules
from . import record_lifecycle as training_record_lifecycle
from . import workbook_models
from .permissions import require_not_self_approval


UTC = timezone.utc
APPROVED_STATES = {"APPROVED", "EFFECTIVE"}
MUTABLE_STATES = {"DRAFT", "RETURNED"}
COMPLETED_AUDIT_STATES = {"COMPLETED", "CLOSED", "APPROVED"}
DEFAULT_COMMITTEE_POSITIONS = ["HEAD_OF_QUALITY", "HEAD_OF_BASE_MAINTENANCE", "HEAD_OF_LINE_MAINTENANCE"]


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _money(value: Decimal | int | str | None, places: int = 6) -> Decimal:
    return rules.decimal_value(value, places)


def _amo_id(user: account_models.User) -> str:
    amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not amo_id:
        raise HTTPException(status_code=403, detail="Select an AMO tenant before using Training & Competence.")
    return str(amo_id)


def _get_scoped(db: Session, model: type, record_id: str, amo_id: str, label: str):
    row = db.query(model).filter(model.id == record_id, model.amo_id == amo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} was not found in this AMO.")
    return row


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    critical: bool = False,
) -> None:
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        metadata={"module": "training", "operating_system": True},
        critical=critical,
    )


def get_or_create_settings(db: Session, *, amo_id: str) -> models.TrainingOperatingSettings:
    row = db.query(models.TrainingOperatingSettings).filter(models.TrainingOperatingSettings.amo_id == amo_id).first()
    if row:
        return row
    row = models.TrainingOperatingSettings(amo_id=amo_id)
    db.add(row)
    db.flush()
    return row


def read_settings(db: Session, *, amo_id: str) -> schemas.TrainingOperatingSettingsRead:
    """Read tenant configuration without creating rows during a GET request."""
    row = db.query(models.TrainingOperatingSettings).filter(models.TrainingOperatingSettings.amo_id == amo_id).first()
    if row is None:
        return schemas.TrainingOperatingSettingsRead(amo_id=amo_id, configured=False)
    payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    payload["configured"] = True
    return schemas.TrainingOperatingSettingsRead.model_validate(payload)


def update_settings(
    db: Session,
    *,
    actor: account_models.User,
    payload: schemas.TrainingOperatingSettingsUpdate,
) -> models.TrainingOperatingSettings:
    amo_id = _amo_id(actor)
    row = get_or_create_settings(db, amo_id=amo_id)
    before = {key: getattr(row, key) for key in payload.__class__.model_fields}
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by_user_id = str(actor.id)
    row.configuration_revision_no = int(row.configuration_revision_no or 0) + 1
    db.flush()
    snapshot = payload.model_dump(mode="json")
    snapshot["configuration_revision_no"] = row.configuration_revision_no
    db.add(models.TrainingConfigurationRevision(
        amo_id=amo_id,
        revision_no=row.configuration_revision_no,
        snapshot=snapshot,
        change_summary="Training operating settings updated from the tenant setup workspace.",
        created_by_user_id=str(actor.id),
    ))
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.settings", entity_id=str(row.id), action="UPDATED", before=before, after=payload.model_dump(mode="json"))
    return row


def setup_readiness(db: Session, *, actor: account_models.User) -> schemas.SetupReadinessRead:
    amo_id = _amo_id(actor)
    settings = db.query(models.TrainingOperatingSettings).filter(models.TrainingOperatingSettings.amo_id == amo_id).first()
    counts = {
        "people": db.query(func.count(account_models.User.id)).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True), account_models.User.is_system_account.is_(False)).scalar() or 0,
        "courses": db.query(func.count(legacy_models.TrainingCourse.id)).filter(legacy_models.TrainingCourse.amo_id == amo_id, legacy_models.TrainingCourse.is_active.is_(True)).scalar() or 0,
        "requirements": db.query(func.count(workbook_models.TrainingCourseRoleRule.id)).filter(workbook_models.TrainingCourseRoleRule.amo_id == amo_id, workbook_models.TrainingCourseRoleRule.is_active.is_(True)).scalar() or 0,
        "forms": db.query(func.count(models.TrainingControlledFormTemplate.id)).filter(models.TrainingControlledFormTemplate.amo_id == amo_id, models.TrainingControlledFormTemplate.status == "ACTIVE").scalar() or 0,
        "templates": db.query(func.count(models.TrainingAssessmentTemplate.id)).filter(models.TrainingAssessmentTemplate.amo_id == amo_id, models.TrainingAssessmentTemplate.active.is_(True)).scalar() or 0,
        "assessment_courses": db.query(func.count(legacy_models.TrainingCourse.id)).filter(legacy_models.TrainingCourse.amo_id == amo_id, legacy_models.TrainingCourse.is_active.is_(True), legacy_models.TrainingCourse.assessment_required.is_(True)).scalar() or 0,
        "resources": db.query(func.count(models.TrainingReferenceResource.id)).filter(models.TrainingReferenceResource.amo_id == amo_id, models.TrainingReferenceResource.active.is_(True)).scalar() or 0,
    }
    items = [
        schemas.SetupReadinessItem(key="settings", label="Operating policy", status="READY" if settings else "BLOCKED", blocking=True, reason="Tenant policy has been saved." if settings else "Save tenant timing, approval and certificate policy.", action_path="settings#operating-policy"),
        schemas.SetupReadinessItem(key="people", label="Personnel register", status="READY" if counts["people"] else "BLOCKED", blocking=True, reason=f'{counts["people"]} active personnel available.' if counts["people"] else "Import or create active personnel.", action_path="people"),
        schemas.SetupReadinessItem(key="courses", label="Course catalogue", status="READY" if counts["courses"] else "BLOCKED", blocking=True, reason=f'{counts["courses"]} active courses available.' if counts["courses"] else "Import or create the governed course catalogue.", action_path="requirements"),
        schemas.SetupReadinessItem(key="requirements", label="Requirement rules", status="READY" if counts["requirements"] else "BLOCKED", blocking=True, reason=f'{counts["requirements"]} active requirement rules.' if counts["requirements"] else "Map courses to role groups and personnel.", action_path="requirements"),
        schemas.SetupReadinessItem(key="forms", label="Controlled forms", status="READY" if counts["forms"] else "BLOCKED", blocking=True, reason=f'{counts["forms"]} active controlled forms.' if counts["forms"] else "Register and activate plan, budget, attendance and assessment forms or DMS revisions.", action_path="settings#controlled-forms"),
        schemas.SetupReadinessItem(key="assessments", label="Assessment criteria", status="READY" if counts["templates"] or not counts["assessment_courses"] else "BLOCKED", blocking=bool(counts["assessment_courses"]), reason=f'{counts["templates"]} active templates for {counts["assessment_courses"]} assessed courses.' if counts["templates"] else ("No assessed courses currently require criteria." if not counts["assessment_courses"] else f'{counts["assessment_courses"]} courses require assessment but no template is active.'), action_path="settings#assessment-templates"),
        schemas.SetupReadinessItem(key="resources", label="Scheduling catalogues", status="READY" if counts["resources"] else "WARNING", blocking=False, reason=f'{counts["resources"]} providers, locations or instructors available.' if counts["resources"] else "Add reusable providers, locations and instructors to avoid free-text scheduling.", action_path="settings#resource-catalogues"),
    ]
    ready = sum(item.status == "READY" for item in items)
    return schemas.SetupReadinessRead(
        generated_at=utcnow(),
        go_live_ready=all(not item.blocking or item.status == "READY" for item in items),
        completion_percent=round((ready / len(items)) * 100),
        items=items,
    )


def create_reference_resource(db: Session, *, actor: account_models.User, payload: schemas.TrainingReferenceResourceCreate) -> models.TrainingReferenceResource:
    amo_id = _amo_id(actor)
    row = models.TrainingReferenceResource(
        amo_id=amo_id,
        created_by_user_id=str(actor.id),
        **payload.model_dump(),
    )
    row.code = row.code.strip().upper()
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail={"code": "RESOURCE_CODE_EXISTS", "message": "That resource code already exists for this type."}) from exc
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.reference_resource", entity_id=str(row.id), action="CREATED", after={"type": row.resource_type, "code": row.code})
    return row


def update_reference_resource(db: Session, *, actor: account_models.User, resource_id: str, payload: schemas.TrainingReferenceResourceCreate) -> models.TrainingReferenceResource:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingReferenceResource, resource_id, amo_id, "Training resource")
    before = {key: getattr(row, key) for key in payload.__class__.model_fields}
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.code = row.code.strip().upper()
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.reference_resource", entity_id=str(row.id), action="UPDATED", before=before, after=payload.model_dump(mode="json"))
    return row


def create_controlled_form(db: Session, *, actor: account_models.User, payload: schemas.ControlledFormTemplateCreate) -> models.TrainingControlledFormTemplate:
    amo_id = _amo_id(actor)
    maximum = db.query(func.max(models.TrainingControlledFormTemplate.revision_no)).filter(
        models.TrainingControlledFormTemplate.amo_id == amo_id,
        func.upper(models.TrainingControlledFormTemplate.code) == payload.code.upper(),
    ).scalar() or 0
    row = models.TrainingControlledFormTemplate(
        amo_id=amo_id,
        revision_no=int(maximum) + 1,
        created_by_user_id=str(actor.id),
        **payload.model_dump(by_alias=True),
    )
    row.code = row.code.strip().upper()
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.controlled_form", entity_id=str(row.id), action="CREATED", after={"code": row.code, "revision": row.revision_no})
    return row


def transition_controlled_form(db: Session, *, actor: account_models.User, form_id: str, target: str) -> models.TrainingControlledFormTemplate:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingControlledFormTemplate, form_id, amo_id, "Controlled form")
    target = target.upper()
    if target == "ACTIVE" and not (row.dms_revision_id or row.schema_json):
        raise HTTPException(status_code=409, detail={"code": "FORM_DEFINITION_REQUIRED", "message": "Link an effective DMS revision or define frontend form fields before activation."})
    if target == "ACTIVE":
        if row.dms_revision_id:
            try:
                revision_uuid = uuid.UUID(str(row.dms_revision_id))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail={"code": "DMS_REVISION_ID_INVALID", "message": "The linked DMS revision ID is not a valid identifier."}) from exc
            qms_revision = db.query(quality_models.QMSDocumentRevision).filter(
                quality_models.QMSDocumentRevision.id == revision_uuid,
                quality_models.QMSDocumentRevision.amo_id == amo_id,
            ).first()
            package = db.query(doc_control_models.RevisionPackage).filter(
                doc_control_models.RevisionPackage.package_id == str(row.dms_revision_id),
                doc_control_models.RevisionPackage.tenant_id == amo_id,
            ).first()
            qms_status = _enum(getattr(qms_revision, "lifecycle_status", None)).upper()
            if not ((qms_revision and qms_status == "APPROVED") or (package and package.published_at)):
                raise HTTPException(status_code=409, detail={"code": "DMS_REVISION_NOT_EFFECTIVE", "message": "Only an approved QMS revision or published DMS revision package may control an active training form."})
        db.query(models.TrainingControlledFormTemplate).filter(
            models.TrainingControlledFormTemplate.amo_id == amo_id,
            models.TrainingControlledFormTemplate.code == row.code,
            models.TrainingControlledFormTemplate.id != row.id,
            models.TrainingControlledFormTemplate.status == "ACTIVE",
        ).update({"status": "SUPERSEDED"}, synchronize_session=False)
        row.approved_by_user_id = str(actor.id)
        settings = get_or_create_settings(db, amo_id=amo_id)
        if row.workflow == "PLAN":
            settings.plan_form_reference = row.code
        elif row.workflow == "BUDGET":
            settings.budget_form_reference = row.code
        elif row.workflow == "ATTENDANCE":
            settings.attendance_form_reference = row.code
        elif row.workflow == "ASSESSMENT":
            mappings = dict(settings.assessment_form_mappings or {})
            mappings[row.code] = str(row.id)
            settings.assessment_form_mappings = mappings
        elif row.workflow == "AUTHORIZATION":
            mappings = dict(settings.authorization_form_mappings or {})
            mappings[row.code] = str(row.id)
            settings.authorization_form_mappings = mappings
    row.status = target
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.controlled_form", entity_id=str(row.id), action=target, critical=target == "ACTIVE")
    return row


def _add_plan_item(
    db: Session,
    *,
    amo_id: str,
    plan: models.TrainingPlan,
    actor_user_id: str,
    item: schemas.TrainingPlanItemCreate,
) -> models.TrainingPlanItem:
    course = None
    if item.course_id:
        course = _get_scoped(db, legacy_models.TrainingCourse, item.course_id, amo_id, "Course")
    obligations = {value.user_id: value for value in item.participant_obligations}
    participant_ids = list(dict.fromkeys(item.participant_ids or obligations.keys()))
    if participant_ids:
        valid_users = db.query(account_models.User).filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id.in_(participant_ids),
                account_models.User.is_system_account.is_(False),
            ).all()
        users_by_id = {str(value.id): value for value in valid_users}
        valid_ids = set(users_by_id)
        missing = sorted(set(participant_ids) - valid_ids)
        if missing:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PARTICIPANTS", "user_ids": missing})
    count = len(participant_ids) if participant_ids else item.participant_count
    total = _money(item.estimated_unit_cost) * count
    row = models.TrainingPlanItem(
        amo_id=amo_id,
        plan_id=plan.id,
        course_id=course.id if course else None,
        course_code_snapshot=course.course_id if course else None,
        course_name_snapshot=(course.course_name if course else item.course_name or "Uncatalogued training"),
        training_kind=item.training_kind,
        provider_mode=item.provider_mode,
        provider=item.provider,
        participant_count=count,
        planned_month=item.planned_month,
        quarter=item.quarter or (((item.planned_month - 1) // 3) + 1 if item.planned_month else None),
        planned_start=item.planned_start,
        planned_end=item.planned_end,
        location=item.location,
        instructor_ids=item.instructor_ids,
        duration_days=item.duration_days,
        justification=item.justification,
        source_type=item.source_type,
        manual_reference=item.manual_reference,
        authorization_impact=item.authorization_impact,
        priority=item.priority,
        original_currency=item.original_currency,
        estimated_unit_cost=_money(item.estimated_unit_cost),
        estimated_total_cost=_money(total),
        owner_user_id=item.owner_user_id,
        notes=item.notes,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    for user_id in participant_ids:
        obligation = obligations.get(user_id)
        user = users_by_id[user_id]
        db.add(models.TrainingPlanParticipant(
            amo_id=amo_id,
            plan_item_id=row.id,
            user_id=user_id,
            person_name_snapshot=(obligation.person_name if obligation else None) or user.full_name,
            staff_code_snapshot=(obligation.staff_code if obligation else None) or user.staff_code,
            last_completion_date=obligation.last_completion_date if obligation else None,
            expiry_date=obligation.expiry_date if obligation else None,
            planned_due_date=obligation.planned_due_date if obligation else None,
            obligation_status=obligation.obligation_status if obligation else "PLANNED",
            source_type=obligation.source_type if obligation else "REQUIREMENT",
            source_record_id=obligation.source_record_id if obligation else None,
            source_reference=obligation.source_reference if obligation else None,
        ))
    return row


def _demand_items(db: Session, *, amo_id: str, year: int) -> list[schemas.TrainingPlanItemCreate]:
    generated_on = date.today()
    evaluation_date = generated_on if year == generated_on.year else date(year, 1, 1) if year > generated_on.year else date(year, 12, 31)
    year_end = date(year, 12, 31)
    users = db.query(account_models.User).outerjoin(
        account_models.PersonnelProfile,
        account_models.PersonnelProfile.user_id == account_models.User.id,
    ).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_system_account.is_(False),
        or_(
            account_models.User.is_active.is_(True),
            func.lower(account_models.PersonnelProfile.status) == "active",
        ),
    ).all()
    courses = db.query(legacy_models.TrainingCourse).options(noload("*")).filter(
        legacy_models.TrainingCourse.amo_id == amo_id,
        legacy_models.TrainingCourse.is_active.is_(True),
    ).all()
    course_by_code = {str(course.course_id): course for course in courses}
    record_rows = db.query(legacy_models.TrainingRecord).filter(
        legacy_models.TrainingRecord.amo_id == amo_id,
        legacy_models.TrainingRecord.user_id.in_([str(user.id) for user in users] or [""]),
        training_record_lifecycle.active_records_filter(legacy_models.TrainingRecord),
    ).order_by(
        legacy_models.TrainingRecord.user_id.asc(),
        legacy_models.TrainingRecord.course_id.asc(),
        legacy_models.TrainingRecord.valid_until.desc().nullslast(),
        legacy_models.TrainingRecord.completion_date.desc().nullslast(),
        legacy_models.TrainingRecord.created_at.desc().nullslast(),
    ).all()
    latest_records: dict[tuple[str, str], legacy_models.TrainingRecord] = {}
    for record in record_rows:
        latest_records.setdefault((str(record.user_id), str(record.course_id)), record)

    buckets: dict[tuple[str, int], dict[str, Any]] = {}
    for user in users:
        required_course_ids = set(compliance.get_required_course_ids_for_user(db, user))
        evaluation = compliance.evaluate_user_training_policy(db, user, required_only=False, today=evaluation_date)
        for item in evaluation.items:
            course = course_by_code.get(str(item.course_id))
            if not course:
                continue
            record = latest_records.get((str(user.id), str(course.id)))
            is_required = str(course.id) in required_course_ids
            if record is None and not is_required:
                continue
            expiry_date = item.valid_until
            planned_due_date = item.extended_due_date or expiry_date
            # A completed one-off course has no renewal to place in the plan.
            if record is not None and planned_due_date is None:
                continue
            if planned_due_date and planned_due_date > year_end:
                continue
            month = rules.plan_month_for_due_date(due_date=planned_due_date, plan_year=year, generated_on=generated_on)
            if record:
                reference_parts = []
                if record.legacy_record_id:
                    reference_parts.append(f"Workbook RecordID {record.legacy_record_id}")
                if record.certificate_reference:
                    reference_parts.append(f"Certificate {record.certificate_reference}")
                if not reference_parts:
                    reference_parts.append(f"Training record {record.id}")
                source_type = "WORKBOOK_RECORD" if record.legacy_record_id else "TRAINING_RECORD"
                source_reference = " · ".join(reference_parts)
            else:
                source_type = "REQUIREMENT"
                source_reference = "No completion record · requirements matrix"
            obligation_status = (
                "NOT_DONE" if record is None
                else "OVERDUE" if planned_due_date and planned_due_date < evaluation_date
                else "DUE_SOON" if planned_due_date and (planned_due_date - evaluation_date).days <= 45
                else "EXPIRING"
            )
            bucket = buckets.setdefault((str(course.id), month), {"course": course, "month": month, "obligations": []})
            bucket["obligations"].append(schemas.TrainingPlanParticipantCreate(
                user_id=str(user.id),
                person_name=user.full_name,
                staff_code=user.staff_code,
                last_completion_date=record.completion_date if record else None,
                expiry_date=expiry_date,
                planned_due_date=planned_due_date,
                obligation_status=obligation_status,
                source_type=source_type,
                source_record_id=str(record.id) if record else None,
                source_reference=source_reference,
            ))
    result: list[schemas.TrainingPlanItemCreate] = []
    for bucket in sorted(buckets.values(), key=lambda value: (value["month"], value["course"].course_id)):
        course = bucket["course"]
        month = bucket["month"]
        obligations = sorted(
            bucket["obligations"],
            key=lambda value: (value.planned_due_date or date.min, value.person_name or ""),
        )
        urgent = any(value.obligation_status in {"OVERDUE", "NOT_DONE"} for value in obligations)
        result.append(schemas.TrainingPlanItemCreate(
            course_id=str(course.id),
            training_kind=_enum(course.kind) or "OTHER",
            provider=course.default_provider,
            location=course.default_facility,
            instructor_ids=list(course.default_instructor_ids or []),
            participant_obligations=obligations,
            planned_month=month,
            duration_days=course.default_duration_days,
            justification="Generated from each person's latest controlling completion record, expiry date, recurrence rule and requirement scope.",
            source_type="EXPIRY_SCHEDULE",
            manual_reference=course.regulatory_reference,
            priority="HIGH" if urgent else "NORMAL",
            original_currency=course.cost_currency or "USD",
            estimated_unit_cost=course.estimated_unit_cost or 0,
            notes="Participant-level expiry and source references are frozen with this plan revision.",
        ))
    return result


def refresh_plan_from_obligations(db: Session, *, actor: account_models.User, plan_id: str) -> models.TrainingPlan:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingPlan, plan_id, amo_id, "Training plan")
    if row.status not in MUTABLE_STATES:
        raise HTTPException(status_code=409, detail="Only a draft or returned plan may be recalculated from current records.")
    removed = 0
    for item in list(row.items):
        if item.source_type == "EXPIRY_SCHEDULE":
            db.delete(item)
            removed += 1
    db.flush()
    generated = _demand_items(db, amo_id=amo_id, year=row.plan_year)
    for item in generated:
        _add_plan_item(db, amo_id=amo_id, plan=row, actor_user_id=str(actor.id), item=item)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="training.plan",
        entity_id=str(row.id),
        action="RECALCULATED",
        before={"generated_items": removed},
        after={"generated_items": len(generated), "source": "current training records and expiry dates"},
    )
    return row


def create_plan(db: Session, *, actor: account_models.User, payload: schemas.TrainingPlanCreate) -> models.TrainingPlan:
    amo_id = _amo_id(actor)
    max_revision = db.query(func.max(models.TrainingPlan.revision_no)).filter(
        models.TrainingPlan.amo_id == amo_id,
        models.TrainingPlan.plan_year == payload.plan_year,
    ).scalar() or 0
    settings = get_or_create_settings(db, amo_id=amo_id)
    row = models.TrainingPlan(
        amo_id=amo_id,
        plan_year=payload.plan_year,
        revision_no=int(max_revision) + 1,
        title=payload.title,
        status="DRAFT",
        form_reference=settings.plan_form_reference,
        notes=payload.notes,
        prepared_by_user_id=str(actor.id),
    )
    db.add(row)
    db.flush()
    items = list(payload.items)
    if payload.generate_from_obligations:
        items.extend(_demand_items(db, amo_id=amo_id, year=payload.plan_year))
    for item in items:
        _add_plan_item(db, amo_id=amo_id, plan=row, actor_user_id=str(actor.id), item=item)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.plan", entity_id=str(row.id), action="CREATED", after={"year": row.plan_year, "revision": row.revision_no, "items": len(items)})
    return row


def sync_current_plan_from_records(
    db: Session,
    *,
    actor: account_models.User,
    plan_year: int | None = None,
) -> dict[str, Any]:
    """Synchronise uploaded records into a governed current-year plan revision.

    Workbook commits may update hundreds of controlling expiry dates at once.
    A mutable draft is recalculated in place; an approved plan is first revised
    so the approved evidence remains immutable. Plans already submitted for
    review are deliberately not changed behind the reviewers' backs.
    """
    amo_id = _amo_id(actor)
    year = plan_year or date.today().year
    latest = (
        db.query(models.TrainingPlan)
        .filter(models.TrainingPlan.amo_id == amo_id, models.TrainingPlan.plan_year == year)
        .order_by(models.TrainingPlan.revision_no.desc())
        .first()
    )
    if latest is None:
        created = create_plan(
            db,
            actor=actor,
            payload=schemas.TrainingPlanCreate(
                plan_year=year,
                title=f"{year} Expiry-driven Training Plan",
                notes="Automatically created from the latest governed training workbook import.",
                generate_from_obligations=True,
            ),
        )
        return {"action": "CREATED", "plan_id": str(created.id), "revision_no": created.revision_no, "status": created.status}
    if latest.status in MUTABLE_STATES:
        refreshed = refresh_plan_from_obligations(db, actor=actor, plan_id=str(latest.id))
        return {"action": "RECALCULATED", "plan_id": str(refreshed.id), "revision_no": refreshed.revision_no, "status": refreshed.status}
    if latest.status in APPROVED_STATES:
        revision = revise_plan(db, actor=actor, plan_id=str(latest.id))
        refreshed = refresh_plan_from_obligations(db, actor=actor, plan_id=str(revision.id))
        return {
            "action": "REVISED_AND_RECALCULATED",
            "plan_id": str(refreshed.id),
            "revision_no": refreshed.revision_no,
            "status": refreshed.status,
            "supersedes_plan_id": str(latest.id),
        }
    return {
        "action": "REVIEW_LOCKED",
        "plan_id": str(latest.id),
        "revision_no": latest.revision_no,
        "status": latest.status,
        "message": "The latest plan is in review and was not silently rewritten. Return or complete it before recalculation.",
    }


def run_monthly_plan_automation(
    db: Session,
    *,
    actor: account_models.User,
    period: date | None = None,
    trigger: str = "MANUAL",
    force: bool = False,
) -> models.TrainingAutomationRun:
    """Idempotently materialise each person's expiry obligations into the annual plan."""
    amo_id = _amo_id(actor)
    period = period or date.today()
    key = f"monthly-plan:{period.year:04d}-{period.month:02d}"
    existing = db.query(models.TrainingAutomationRun).filter(
        models.TrainingAutomationRun.amo_id == amo_id,
        models.TrainingAutomationRun.idempotency_key == key,
    ).first()
    if existing and not force:
        return existing
    if existing and force:
        key = f"{key}:manual:{secrets.token_hex(6)}"
    run = models.TrainingAutomationRun(
        amo_id=amo_id,
        idempotency_key=key,
        period_year=period.year,
        period_month=period.month,
        trigger=trigger.upper(),
        status="RUNNING",
        actor_user_id=str(actor.id),
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()
    try:
        settings = read_settings(db, amo_id=amo_id)
        plan_years = [period.year]
        if (period + timedelta(days=settings.default_planning_lead_days)).year > period.year:
            plan_years.append(period.year + 1)
        results = [sync_current_plan_from_records(db, actor=actor, plan_year=year) for year in plan_years]
        change_set_ids: list[str] = []
        for result in results:
            plan_id = result.get("plan_id")
            participant_count = 0
            if plan_id:
                participant_count = int(
                    db.query(func.count(models.TrainingPlanParticipant.id))
                    .join(models.TrainingPlanItem, models.TrainingPlanItem.id == models.TrainingPlanParticipant.plan_item_id)
                    .filter(models.TrainingPlanItem.plan_id == plan_id, models.TrainingPlanParticipant.amo_id == amo_id)
                    .scalar() or 0
                )
            change_set = models.TrainingChangeRequest(
                amo_id=amo_id,
                object_type="PLAN",
                object_id=plan_id,
                operation="MONTHLY_EXPIRY_RECALCULATION",
                status="PREVIEW",
                requested_payload={"automation_run_id": str(run.id), "period": f"{period.year:04d}-{period.month:02d}", "result": result},
                impact_summary={
                    "affected_count": participant_count,
                    "plan_year": result.get("plan_year") or next((year for year in plan_years if str(year) in str(result)), None),
                    "action": result.get("action"),
                    "requires_planner_acceptance": True,
                    "review_locked": result.get("action") == "REVIEW_LOCKED",
                },
                validation_result={"status": "BLOCKED" if result.get("action") == "REVIEW_LOCKED" else "VALID", "errors": [result.get("message")] if result.get("message") else []},
                requested_by_user_id=str(actor.id),
            )
            db.add(change_set)
            db.flush()
            change_set_ids.append(str(change_set.id))
        run.status = "ACTION_REQUIRED" if any(result.get("action") == "REVIEW_LOCKED" for result in results) else "COMPLETED"
        run.plan_id = results[0].get("plan_id")
        run.summary = {"period": f"{period.year:04d}-{period.month:02d}", "plan_years": plan_years, "runs": results, "change_set_ids": change_set_ids, "source_cutoff_at": utcnow().isoformat()}
        run.completed_at = utcnow()
        _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.automation_run", entity_id=str(run.id), action=run.status, after=run.summary)
        return run
    except Exception as exc:
        run.status = "FAILED"
        run.error_text = str(exc)[:4000]
        run.completed_at = utcnow()
        _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.automation_run", entity_id=str(run.id), action="FAILED", after={"error": run.error_text}, critical=True)
        return run


def automation_status(db: Session, *, actor: account_models.User) -> schemas.AutomationStatusRead:
    amo_id = _amo_id(actor)
    settings = read_settings(db, amo_id=amo_id)
    last = db.query(models.TrainingAutomationRun).filter(
        models.TrainingAutomationRun.amo_id == amo_id,
    ).order_by(models.TrainingAutomationRun.started_at.desc()).first()
    now = utcnow()
    next_month = now.month + (1 if now.day > settings.plan_run_day or (now.day == settings.plan_run_day and now.hour >= settings.plan_run_hour) else 0)
    year = now.year + (1 if next_month > 12 else 0)
    month = 1 if next_month > 12 else next_month
    next_run = datetime(year, month, settings.plan_run_day, settings.plan_run_hour, tzinfo=UTC) if settings.plan_automation_enabled else None
    return schemas.AutomationStatusRead(
        enabled=settings.plan_automation_enabled,
        timezone=settings.timezone,
        run_day=settings.plan_run_day,
        run_hour=settings.plan_run_hour,
        next_run_at=next_run,
        last_run=schemas.AutomationRunRead.model_validate(last) if last else None,
    )


def revise_plan(db: Session, *, actor: account_models.User, plan_id: str) -> models.TrainingPlan:
    amo_id = _amo_id(actor)
    source = _get_scoped(db, models.TrainingPlan, plan_id, amo_id, "Training plan")
    if source.status not in APPROVED_STATES:
        raise HTTPException(status_code=409, detail="Only an approved plan may be revised; edit the current draft instead.")
    max_revision = db.query(func.max(models.TrainingPlan.revision_no)).filter(
        models.TrainingPlan.amo_id == amo_id,
        models.TrainingPlan.plan_year == source.plan_year,
    ).scalar() or source.revision_no
    revision = models.TrainingPlan(
        amo_id=amo_id, plan_year=source.plan_year, revision_no=int(max_revision) + 1,
        title=source.title, status="DRAFT", form_reference=source.form_reference,
        notes=source.notes, supersedes_plan_id=source.id, prepared_by_user_id=str(actor.id),
    )
    db.add(revision)
    db.flush()
    for source_item in source.items:
        clone = models.TrainingPlanItem(
            **{column.name: getattr(source_item, column.name) for column in models.TrainingPlanItem.__table__.columns if column.name not in {"id", "plan_id", "created_at", "updated_at"}},
            plan_id=revision.id,
        )
        db.add(clone)
        db.flush()
        for participant in source_item.participants:
            db.add(models.TrainingPlanParticipant(
                **{
                    column.name: getattr(participant, column.name)
                    for column in models.TrainingPlanParticipant.__table__.columns
                    if column.name not in {"id", "plan_item_id", "created_at"}
                },
                plan_item_id=clone.id,
            ))
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.plan", entity_id=str(revision.id), action="REVISED", after={"supersedes": source.id, "revision": revision.revision_no})
    return revision


def transition_plan(db: Session, *, actor: account_models.User, plan_id: str, target: str, comment: str | None) -> models.TrainingPlan:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingPlan, plan_id, amo_id, "Training plan")
    target = target.upper()
    if not rules.plan_transition_allowed(row.status, target):
        raise HTTPException(status_code=409, detail=f"Training plan cannot move from {row.status} to {target}.")
    now = utcnow()
    if target == "SUBMITTED":
        row.submitted_by_user_id, row.submitted_at = str(actor.id), now
    elif target == "REVIEWED":
        require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=row.prepared_by_user_id, action="review")
        row.reviewed_by_user_id, row.reviewed_at = str(actor.id), now
    elif target == "APPROVED":
        require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=row.prepared_by_user_id, action="approve")
        row.approved_by_user_id, row.approved_at, row.issue_date = str(actor.id), now, date.today()
        older = db.query(models.TrainingPlan).filter(
            models.TrainingPlan.amo_id == amo_id,
            models.TrainingPlan.plan_year == row.plan_year,
            models.TrainingPlan.id != row.id,
            models.TrainingPlan.status == "APPROVED",
        ).all()
        for previous in older:
            previous.status = "SUPERSEDED"
    row.status = target
    if comment:
        row.notes = ((row.notes or "") + f"\n[{target}] {comment}").strip()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.plan", entity_id=str(row.id), action=target, critical=target == "APPROVED")
    return row


def build_budget(db: Session, *, actor: account_models.User, payload: schemas.BudgetBuildCreate) -> models.TrainingBudget:
    amo_id = _amo_id(actor)
    plan = _get_scoped(db, models.TrainingPlan, payload.plan_id, amo_id, "Training plan")
    max_revision = db.query(func.max(models.TrainingBudget.revision_no)).filter(models.TrainingBudget.amo_id == amo_id, models.TrainingBudget.plan_id == plan.id).scalar() or 0
    settings = get_or_create_settings(db, amo_id=amo_id)
    reporting = payload.reporting_currency.upper()
    rates = {key.upper(): Decimal(str(value)) for key, value in payload.exchange_rates.items()}
    rates[reporting] = Decimal("1")
    budget = models.TrainingBudget(
        amo_id=amo_id, plan_id=plan.id, revision_no=int(max_revision) + 1,
        status="DRAFT", reporting_currency=reporting,
        form_reference=settings.budget_form_reference, prepared_by_user_id=str(actor.id),
    )
    db.add(budget)
    db.flush()
    for item in plan.items:
        currency = item.original_currency.upper()
        rate = rates.get(currency)
        if rate is None or rate <= 0:
            raise HTTPException(status_code=422, detail={"code": "MISSING_EXCHANGE_RATE", "currency": currency})
        planned = _money(item.estimated_unit_cost) * item.participant_count
        converted = _money(planned * rate)
        db.add(models.TrainingBudgetLine(
            amo_id=amo_id, budget_id=budget.id, plan_item_id=item.id, course_id=item.course_id,
            course_code_snapshot=item.course_code_snapshot, course_name_snapshot=item.course_name_snapshot,
            training_kind=item.training_kind, provider=item.provider, original_currency=currency,
            reporting_currency=reporting, unit_cost=_money(item.estimated_unit_cost), trainee_count=item.participant_count,
            planned_amount=_money(planned), approved_amount=Decimal("0"), committed_amount=Decimal("0"), actual_amount=Decimal("0"),
            exchange_rate=rate, rate_date=payload.rate_date, rate_source=payload.rate_source,
            converted_planned_amount=converted, converted_approved_amount=Decimal("0"),
            converted_committed_amount=Decimal("0"), converted_actual_amount=Decimal("0"),
            quarter=item.quarter or 1,
        ))
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.budget", entity_id=str(budget.id), action="BUILT", after={"plan_id": plan.id, "rate_date": str(payload.rate_date), "rate_source": payload.rate_source})
    return budget


def revise_budget(db: Session, *, actor: account_models.User, budget_id: str) -> models.TrainingBudget:
    amo_id = _amo_id(actor)
    source = _get_scoped(db, models.TrainingBudget, budget_id, amo_id, "Training budget")
    if source.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only an approved budget may be revised; edit the current draft instead.")
    max_revision = db.query(func.max(models.TrainingBudget.revision_no)).filter(
        models.TrainingBudget.amo_id == amo_id,
        models.TrainingBudget.plan_id == source.plan_id,
    ).scalar() or source.revision_no
    revision = models.TrainingBudget(
        amo_id=amo_id,
        plan_id=source.plan_id,
        revision_no=int(max_revision) + 1,
        status="DRAFT",
        reporting_currency=source.reporting_currency,
        form_reference=source.form_reference,
        notes=source.notes,
        supersedes_budget_id=source.id,
        prepared_by_user_id=str(actor.id),
    )
    db.add(revision)
    db.flush()
    for source_line in source.lines:
        clone = models.TrainingBudgetLine(
            **{
                column.name: getattr(source_line, column.name)
                for column in models.TrainingBudgetLine.__table__.columns
                if column.name not in {"id", "budget_id", "created_at", "updated_at"}
            },
            budget_id=revision.id,
        )
        db.add(clone)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="training.budget",
        entity_id=str(revision.id),
        action="REVISED",
        after={"supersedes": source.id, "revision": revision.revision_no},
    )
    return revision


def update_budget_line(
    db: Session,
    *,
    actor: account_models.User,
    budget_id: str,
    line_id: str,
    payload: schemas.TrainingBudgetLineUpdate,
) -> models.TrainingBudgetLine:
    amo_id = _amo_id(actor)
    budget = _get_scoped(db, models.TrainingBudget, budget_id, amo_id, "Training budget")
    if budget.status not in MUTABLE_STATES:
        raise HTTPException(status_code=409, detail="Only a draft or returned budget may be edited.")
    line = db.query(models.TrainingBudgetLine).filter(
        models.TrainingBudgetLine.id == line_id,
        models.TrainingBudgetLine.budget_id == budget.id,
        models.TrainingBudgetLine.amo_id == amo_id,
    ).first()
    if not line:
        raise HTTPException(status_code=404, detail="Budget line was not found in this AMO budget.")
    before = {
        "unit_cost": str(line.unit_cost), "trainee_count": line.trainee_count,
        "approved_amount": str(line.approved_amount), "committed_amount": str(line.committed_amount),
        "actual_amount": str(line.actual_amount), "exchange_rate": str(line.exchange_rate),
    }
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(line, key, value)
    line.planned_amount = _money(line.unit_cost) * int(line.trainee_count or 0)
    rate = Decimal(str(line.exchange_rate))
    line.converted_planned_amount = _money(Decimal(str(line.planned_amount)) * rate)
    line.converted_approved_amount = _money(Decimal(str(line.approved_amount)) * rate)
    line.converted_committed_amount = _money(Decimal(str(line.committed_amount)) * rate)
    line.converted_actual_amount = _money(Decimal(str(line.actual_amount)) * rate)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.budget_line", entity_id=str(line.id), action="UPDATED", before=before, after={key: str(value) for key, value in payload.model_dump(exclude_unset=True).items()})
    return line


def transition_budget(
    db: Session,
    *,
    actor: account_models.User,
    budget_id: str,
    target: str,
    comment: str | None,
) -> models.TrainingBudget:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingBudget, budget_id, amo_id, "Training budget")
    target = target.upper()
    if not rules.budget_transition_allowed(row.status, target):
        raise HTTPException(status_code=409, detail=f"Training budget cannot move from {row.status} to {target}.")
    now = utcnow()
    if target == "SUBMITTED":
        row.submitted_at = now
    elif target == "REVIEWED":
        require_not_self_approval(
            actor_user_id=str(actor.id),
            originator_user_id=row.prepared_by_user_id,
            action="review",
        )
        row.reviewed_by_user_id, row.reviewed_at = str(actor.id), now
    elif target == "APPROVED":
        require_not_self_approval(
            actor_user_id=str(actor.id),
            originator_user_id=row.prepared_by_user_id,
            action="approve",
        )
        row.approved_by_user_id, row.approved_at = str(actor.id), now
        for line in row.lines:
            line.approved_amount = line.planned_amount
            line.converted_approved_amount = line.converted_planned_amount
        older = db.query(models.TrainingBudget).filter(
            models.TrainingBudget.amo_id == amo_id,
            models.TrainingBudget.plan_id == row.plan_id,
            models.TrainingBudget.id != row.id,
            models.TrainingBudget.status == "APPROVED",
        ).all()
        for previous in older:
            previous.status = "SUPERSEDED"
    row.status = target
    if comment:
        row.notes = ((row.notes or "") + f"\n[{target}] {comment}").strip()
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="training.budget",
        entity_id=str(row.id),
        action=target,
        critical=target == "APPROVED",
    )
    return row


def budget_totals(budget: models.TrainingBudget) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    quarters = {f"Q{number}": Decimal("0") for number in range(1, 5)}
    annual = {name: Decimal("0") for name in ("planned", "approved", "committed", "actual")}
    for line in budget.lines:
        quarters[f"Q{line.quarter}"] += _money(line.converted_planned_amount)
        for name in annual:
            annual[name] += _money(getattr(line, f"converted_{name}_amount"))
    annual["variance_to_approved"] = annual["approved"] - annual["actual"]
    annual["variance_to_plan"] = annual["planned"] - annual["actual"]
    return ({key: _money(value) for key, value in quarters.items()}, {key: _money(value) for key, value in annual.items()})


def open_attendance_window(
    db: Session,
    *,
    actor: account_models.User,
    payload: schemas.AttendanceWindowCreate,
) -> tuple[models.TrainingAttendanceWindow, str, str, int]:
    amo_id = _amo_id(actor)
    event = _get_scoped(db, legacy_models.TrainingEvent, payload.event_id, amo_id, "Training session")
    if _enum(event.status) in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Attendance cannot be opened for a closed or cancelled session.")
    db.query(models.TrainingAttendanceWindow).filter(
        models.TrainingAttendanceWindow.amo_id == amo_id,
        models.TrainingAttendanceWindow.event_id == event.id,
        models.TrainingAttendanceWindow.status == "OPEN",
    ).update({"status": "CLOSED", "closed_at": utcnow(), "closed_by_user_id": str(actor.id)}, synchronize_session=False)
    settings = get_or_create_settings(db, amo_id=amo_id)
    lifetime = payload.lifetime_minutes or settings.attendance_qr_lifetime_minutes
    code = secrets.token_urlsafe(32)
    row = models.TrainingAttendanceWindow(
        amo_id=amo_id,
        event_id=event.id,
        token_hash=hashlib.sha256(code.encode()).hexdigest(),
        opened_by_user_id=str(actor.id),
        opened_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=lifetime),
    )
    db.add(row)
    db.flush()
    base_path = payload.sign_in_path or "/training/attendance"
    separator = "&" if "?" in base_path else "?"
    sign_in_path = f"{base_path}{separator}attendance={code}&event={event.id}"
    participant_ids = [
        str(user_id)
        for (user_id,) in db.query(legacy_models.TrainingEventParticipant.user_id)
        .filter(
            legacy_models.TrainingEventParticipant.amo_id == amo_id,
            legacy_models.TrainingEventParticipant.event_id == event.id,
            legacy_models.TrainingEventParticipant.status.in_([
                legacy_models.TrainingParticipantStatus.SCHEDULED,
                legacy_models.TrainingParticipantStatus.INVITED,
                legacy_models.TrainingParticipantStatus.CONFIRMED,
            ]),
        )
        .distinct()
        .all()
        if user_id
    ]
    expiry_label = row.expires_at.strftime("%H:%M UTC")
    title = "Attendance sign-in is open"
    body = f"Sign in for '{event.title}' before {expiry_label}."
    if participant_ids:
        db.add_all([
            legacy_models.TrainingNotification(
                amo_id=amo_id,
                user_id=user_id,
                title=title,
                body=body,
                severity=legacy_models.TrainingNotificationSeverity.ACTION_REQUIRED,
                link_path=sign_in_path,
                dedupe_key=f"attendance:{row.id}:{user_id}",
                created_by_user_id=str(actor.id),
            )
            for user_id in participant_ids
        ])
        db.add_all([
            realtime_models.PortalNotification(
                amo_id=amo_id,
                user_id=user_id,
                kind="TRAINING_ATTENDANCE_OPEN",
                title=title,
                body=body,
                entity_type="training_event",
                entity_id=str(event.id),
                action_url=sign_in_path,
                dedupe_key=f"attendance:{row.id}:{user_id}",
                metadata_json={"event_id": str(event.id), "attendance_window_id": str(row.id), "expires_at": row.expires_at.isoformat()},
            )
            for user_id in participant_ids
        ])
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type="training.attendance_window",
        entity_id=str(row.id),
        action="OPENED",
        after={"event_id": event.id, "expires_at": row.expires_at.isoformat(), "notifications_queued": len(participant_ids)},
    )
    return row, code, sign_in_path, len(participant_ids)


def current_attendance_window(db: Session, *, actor: account_models.User, event_id: str) -> models.TrainingAttendanceWindow | None:
    amo_id = _amo_id(actor)
    _get_scoped(db, legacy_models.TrainingEvent, event_id, amo_id, "Training session")
    return db.query(models.TrainingAttendanceWindow).filter(
        models.TrainingAttendanceWindow.amo_id == amo_id,
        models.TrainingAttendanceWindow.event_id == event_id,
    ).order_by(models.TrainingAttendanceWindow.opened_at.desc()).first()


def close_attendance_window(db: Session, *, actor: account_models.User, window_id: str) -> models.TrainingAttendanceWindow:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingAttendanceWindow, window_id, amo_id, "Attendance window")
    if row.status == "CERTIFIED":
        raise HTTPException(status_code=409, detail="A certified attendance register is immutable.")
    if row.status not in {"OPEN", "EXPIRED"}:
        return row
    row.status = "CLOSED"
    row.closed_by_user_id = str(actor.id)
    row.closed_at = utcnow()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.attendance_window", entity_id=str(row.id), action="CLOSED", after={"event_id": row.event_id}, critical=True)
    return row


def _attendance_entry(
    db: Session,
    *,
    actor: account_models.User,
    event: legacy_models.TrainingEvent,
    participant: legacy_models.TrainingEventParticipant,
    window_id: str | None,
    entry_status: str,
    method: str,
    idempotency_key: str,
    attestation: str | None,
) -> models.TrainingAttendanceEntry:
    amo_id = _amo_id(actor)
    existing_key = db.query(models.TrainingAttendanceEntry).filter(models.TrainingAttendanceEntry.idempotency_key == idempotency_key).first()
    if existing_key:
        if existing_key.amo_id == amo_id and existing_key.event_id == event.id and existing_key.user_id == participant.user_id:
            return existing_key
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "That idempotency key belongs to another attendance action."})
    existing = db.query(models.TrainingAttendanceEntry).filter(
        models.TrainingAttendanceEntry.amo_id == amo_id,
        models.TrainingAttendanceEntry.event_id == event.id,
        models.TrainingAttendanceEntry.user_id == participant.user_id,
    ).first()
    if existing:
        return existing
    now = utcnow()
    row = models.TrainingAttendanceEntry(
        amo_id=amo_id, window_id=window_id, event_id=event.id, participant_id=participant.id,
        user_id=participant.user_id, status=entry_status, method=method,
        signed_by_user_id=str(actor.id), signed_at=now, attestation=attestation,
        idempotency_key=idempotency_key, source_metadata={"actor_user_id": str(actor.id)},
    )
    db.add(row)
    if entry_status == "PRESENT":
        participant.status = legacy_models.TrainingParticipantStatus.ATTENDED
        participant.attended_at = now
    elif entry_status == "ABSENT":
        participant.status = legacy_models.TrainingParticipantStatus.NO_SHOW
    participant.attendance_marked_at = now
    participant.attendance_marked_by_user_id = str(actor.id)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.attendance", entity_id=str(row.id), action="SIGNED", after={"event_id": event.id, "user_id": participant.user_id, "method": method, "status": entry_status})
    return row


def self_sign_attendance(db: Session, *, actor: account_models.User, payload: schemas.AttendanceSelfSignCreate) -> models.TrainingAttendanceEntry:
    amo_id = _amo_id(actor)
    token_hash = hashlib.sha256(payload.attendance_code.encode()).hexdigest()
    now = utcnow()
    window = db.query(models.TrainingAttendanceWindow).filter(
        models.TrainingAttendanceWindow.amo_id == amo_id,
        models.TrainingAttendanceWindow.token_hash == token_hash,
        models.TrainingAttendanceWindow.status == "OPEN",
    ).first()
    if not window:
        raise HTTPException(status_code=404, detail={"code": "ATTENDANCE_CODE_INVALID", "message": "Attendance code is invalid."})
    if window.expires_at <= now:
        window.status = "EXPIRED"
        raise HTTPException(status_code=410, detail={"code": "ATTENDANCE_CODE_EXPIRED", "message": "Attendance code has expired."})
    event = _get_scoped(db, legacy_models.TrainingEvent, window.event_id, amo_id, "Training session")
    participant = db.query(legacy_models.TrainingEventParticipant).filter(
        legacy_models.TrainingEventParticipant.amo_id == amo_id,
        legacy_models.TrainingEventParticipant.event_id == event.id,
        legacy_models.TrainingEventParticipant.user_id == str(actor.id),
    ).first()
    if not participant:
        raise HTTPException(status_code=403, detail={"code": "NOT_SESSION_PARTICIPANT", "message": "Only a scheduled participant may self-sign attendance."})
    return _attendance_entry(
        db, actor=actor, event=event, participant=participant, window_id=window.id,
        entry_status="PRESENT", method="QR_SELF", idempotency_key=payload.idempotency_key,
        attestation=payload.attestation,
    )


def mark_attendance(
    db: Session,
    *,
    actor: account_models.User,
    event_id: str,
    payload: schemas.AttendanceAdminMarkCreate,
) -> models.TrainingAttendanceEntry:
    amo_id = _amo_id(actor)
    event = _get_scoped(db, legacy_models.TrainingEvent, event_id, amo_id, "Training session")
    participant = db.query(legacy_models.TrainingEventParticipant).filter(
        legacy_models.TrainingEventParticipant.amo_id == amo_id,
        legacy_models.TrainingEventParticipant.event_id == event.id,
        legacy_models.TrainingEventParticipant.user_id == payload.user_id,
    ).first()
    if not participant:
        raise HTTPException(status_code=422, detail="The selected person is not a participant in this session.")
    return _attendance_entry(
        db, actor=actor, event=event, participant=participant, window_id=None,
        entry_status=payload.status, method=payload.method, idempotency_key=payload.idempotency_key,
        attestation=payload.note,
    )


def correct_attendance(
    db: Session,
    *,
    actor: account_models.User,
    entry_id: str,
    payload: schemas.AttendanceCorrectionCreate,
) -> models.TrainingAttendanceEntry:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingAttendanceEntry, entry_id, amo_id, "Attendance entry")
    old = row.status
    if old == payload.new_status:
        return row
    db.add(models.TrainingAttendanceCorrection(
        amo_id=amo_id, attendance_entry_id=row.id, old_status=old, new_status=payload.new_status,
        reason=payload.reason, actor_user_id=str(actor.id),
    ))
    row.status = payload.new_status
    participant = _get_scoped(db, legacy_models.TrainingEventParticipant, row.participant_id, amo_id, "Session participant")
    participant.status = (
        legacy_models.TrainingParticipantStatus.ATTENDED
        if payload.new_status == "PRESENT"
        else legacy_models.TrainingParticipantStatus.NO_SHOW
        if payload.new_status == "ABSENT"
        else legacy_models.TrainingParticipantStatus.CONFIRMED
    )
    register_revision = None
    if row.window_id:
        window = _get_scoped(db, models.TrainingAttendanceWindow, row.window_id, amo_id, "Attendance window")
        if window.status == "CERTIFIED":
            window.register_revision = int(window.register_revision or 1) + 1
            register_revision = window.register_revision
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.attendance", entity_id=str(row.id), action="CORRECTED", before={"status": old}, after={"status": row.status, "reason": payload.reason, "register_revision": register_revision}, critical=True)
    return row


def certify_attendance(
    db: Session,
    *,
    actor: account_models.User,
    event_id: str,
    note: str | None,
) -> models.TrainingAttendanceWindow:
    amo_id = _amo_id(actor)
    event = _get_scoped(db, legacy_models.TrainingEvent, event_id, amo_id, "Training session")
    require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=event.created_by_user_id, action="certify attendance for")
    window = db.query(models.TrainingAttendanceWindow).filter(
        models.TrainingAttendanceWindow.amo_id == amo_id,
        models.TrainingAttendanceWindow.event_id == event.id,
    ).order_by(models.TrainingAttendanceWindow.opened_at.desc()).first()
    if not window:
        window = models.TrainingAttendanceWindow(
            amo_id=amo_id, event_id=event.id, status="CLOSED", token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
            opened_by_user_id=str(actor.id), opened_at=utcnow() - timedelta(seconds=1), expires_at=utcnow(),
        )
        db.add(window)
        db.flush()
    window.status = "CERTIFIED"
    window.closed_by_user_id = str(actor.id)
    window.closed_at = window.closed_at or utcnow()
    window.certified_by_user_id = str(actor.id)
    window.certified_at = utcnow()
    window.certification_note = note
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.attendance_window", entity_id=str(window.id), action="CERTIFIED", after={"event_id": event.id}, critical=True)
    return window


def create_assessment_template(db: Session, *, actor: account_models.User, payload: schemas.AssessmentTemplateCreate) -> models.TrainingAssessmentTemplate:
    amo_id = _amo_id(actor)
    max_revision = db.query(func.max(models.TrainingAssessmentTemplate.revision_no)).filter(
        models.TrainingAssessmentTemplate.amo_id == amo_id,
        func.upper(models.TrainingAssessmentTemplate.code) == payload.code.upper(),
    ).scalar() or 0
    questions = payload.questions
    template_payload = payload.model_dump(exclude={"questions"})
    row = models.TrainingAssessmentTemplate(
        amo_id=amo_id, revision_no=int(max_revision) + 1, created_by_user_id=str(actor.id),
        **template_payload,
    )
    row.code = row.code.upper().strip()
    db.add(row)
    db.flush()
    for question in questions:
        db.add(models.TrainingAssessmentQuestion(
            amo_id=amo_id,
            template_id=row.id,
            **question.model_dump(),
        ))
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.assessment_template", entity_id=str(row.id), action="CREATED", after={"code": row.code, "revision": row.revision_no})
    return row


def create_assessment(db: Session, *, actor: account_models.User, payload: schemas.AssessmentCreate) -> models.TrainingAssessmentInstance:
    amo_id = _amo_id(actor)
    template = _get_scoped(db, models.TrainingAssessmentTemplate, payload.template_id, amo_id, "Assessment template")
    _get_scoped(db, account_models.User, payload.candidate_user_id, amo_id, "Candidate")
    row = models.TrainingAssessmentInstance(
        amo_id=amo_id, template_id=template.id, candidate_user_id=payload.candidate_user_id,
        course_id=payload.course_id, event_id=payload.event_id, authorization_case_id=payload.authorization_case_id,
        assessor_user_id=payload.assessor_user_id or str(actor.id), planned_at=payload.planned_at,
        status="DRAFT", created_by_user_id=str(actor.id),
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.assessment", entity_id=str(row.id), action="CREATED", after={"candidate_user_id": row.candidate_user_id, "template_id": row.template_id})
    return row


def submit_assessment(
    db: Session,
    *,
    actor: account_models.User,
    assessment_id: str,
    payload: schemas.AssessmentSubmit,
) -> models.TrainingAssessmentInstance:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingAssessmentInstance, assessment_id, amo_id, "Assessment")
    if row.status not in {"DRAFT", "RETURNED"}:
        raise HTTPException(status_code=409, detail="Only a draft or returned assessment may be submitted.")
    if row.assessor_user_id and str(row.assessor_user_id) != str(actor.id):
        raise HTTPException(status_code=403, detail="Only the assigned assessor may submit this assessment.")
    template = _get_scoped(db, models.TrainingAssessmentTemplate, row.template_id, amo_id, "Assessment template")
    mandatory_questions = db.query(models.TrainingAssessmentQuestion).filter(
        models.TrainingAssessmentQuestion.amo_id == amo_id,
        models.TrainingAssessmentQuestion.template_id == template.id,
        models.TrainingAssessmentQuestion.mandatory.is_(True),
        models.TrainingAssessmentQuestion.active.is_(True),
    ).all()
    missing = [
        str(question.id)
        for question in mandatory_questions
        if str(question.id) not in payload.results or payload.results.get(str(question.id)) in (None, "", [])
    ]
    if missing:
        raise HTTPException(status_code=422, detail={"code": "MANDATORY_ASSESSMENT_RESPONSES_MISSING", "question_ids": missing})
    score = payload.score
    threshold = Decimal(str(template.pass_threshold)) if template.pass_threshold is not None else None
    outcome = payload.outcome
    if template.outcome_scheme == "NUMERIC":
        if score is None:
            raise HTTPException(status_code=422, detail="A numeric score is required by this assessment template.")
        outcome = "PASS" if threshold is None else rules.assessment_outcome(score, threshold)
    if not outcome:
        raise HTTPException(status_code=422, detail="Assessment outcome is required.")
    row.results, row.score, row.outcome, row.comments = payload.results, score, outcome.upper(), payload.comments
    row.performed_at = utcnow()
    row.status = "SUBMITTED" if template.approval_required else "APPROVED"
    if row.status == "APPROVED":
        row.approved_at = utcnow()
    if row.outcome in {"FAIL", "NOT_COMPETENT", "UNSATISFACTORY"}:
        task_services.create_task(
            db, amo_id=amo_id, title="Remedial training action required",
            description=f"Assessment {row.id} for candidate {row.candidate_user_id} did not meet the required standard.",
            owner_user_id=row.assessor_user_id, due_at=utcnow() + timedelta(days=14),
            entity_type="training.assessment", entity_id=str(row.id), priority=2,
            metadata={"module": "training", "candidate_user_id": row.candidate_user_id},
        )
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.assessment", entity_id=str(row.id), action="SUBMITTED", after={"score": str(score) if score is not None else None, "outcome": row.outcome, "threshold": str(threshold) if threshold is not None else None})
    return row


def review_assessment(
    db: Session,
    *,
    actor: account_models.User,
    assessment_id: str,
    payload: schemas.AssessmentReview,
) -> models.TrainingAssessmentInstance:
    amo_id = _amo_id(actor)
    row = _get_scoped(db, models.TrainingAssessmentInstance, assessment_id, amo_id, "Assessment")
    if row.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only a submitted assessment may be reviewed.")
    require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=row.assessor_user_id, action="review")
    row.reviewer_user_id = str(actor.id)
    row.review_decision = payload.decision
    row.reviewed_at = utcnow()
    row.status = "APPROVED" if payload.decision == "APPROVED" else "RETURNED" if payload.decision == "RETURNED" else payload.decision
    if row.status == "APPROVED":
        row.approved_at = utcnow()
    if payload.comment:
        row.comments = ((row.comments or "") + f"\nReview: {payload.comment}").strip()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.assessment", entity_id=str(row.id), action="REVIEWED", after={"decision": payload.decision}, critical=True)
    return row


def completion_gate(db: Session, *, record: legacy_models.TrainingRecord) -> list[dict[str, str]]:
    """Return blocking completion/certificate gates for a training record."""
    course = db.query(legacy_models.TrainingCourse).filter(
        legacy_models.TrainingCourse.id == record.course_id,
        legacy_models.TrainingCourse.amo_id == record.amo_id,
    ).first()
    if not course:
        return [{"code": "COURSE_MISSING", "message": "The course master record is unavailable."}]
    blockers: list[dict[str, str]] = []
    if course.attendance_required and record.event_id:
        attendance = db.query(models.TrainingAttendanceEntry).filter(
            models.TrainingAttendanceEntry.amo_id == record.amo_id,
            models.TrainingAttendanceEntry.event_id == record.event_id,
            models.TrainingAttendanceEntry.user_id == record.user_id,
            models.TrainingAttendanceEntry.status == "PRESENT",
        ).first()
        certified = db.query(models.TrainingAttendanceWindow.id).filter(
            models.TrainingAttendanceWindow.amo_id == record.amo_id,
            models.TrainingAttendanceWindow.event_id == record.event_id,
            models.TrainingAttendanceWindow.status == "CERTIFIED",
        ).first()
        if not attendance or not certified:
            blockers.append({"code": "ATTENDANCE_MISSING", "message": "Certified attendance is required."})
    if course.assessment_required:
        assessment = db.query(models.TrainingAssessmentInstance).filter(
            models.TrainingAssessmentInstance.amo_id == record.amo_id,
            models.TrainingAssessmentInstance.course_id == record.course_id,
            models.TrainingAssessmentInstance.candidate_user_id == record.user_id,
            models.TrainingAssessmentInstance.status == "APPROVED",
            models.TrainingAssessmentInstance.outcome.in_(["PASS", "COMPETENT", "SATISFACTORY"]),
        ).order_by(models.TrainingAssessmentInstance.approved_at.desc()).first()
        if not assessment:
            blockers.append({"code": "ASSESSMENT_MISSING", "message": "A passing approved assessment is required."})
    if course.ojt_signoff_required:
        verified = db.query(models.TrainingExperienceLog).filter(
            models.TrainingExperienceLog.amo_id == record.amo_id,
            models.TrainingExperienceLog.candidate_user_id == record.user_id,
            models.TrainingExperienceLog.verification_status == "VERIFIED",
        ).first()
        if not verified:
            blockers.append({"code": "OJT_SIGNOFF_MISSING", "message": "Verified OJT/experience evidence is required."})
    if course.evidence_required:
        evidence = db.query(legacy_models.TrainingFile.id).filter(
            legacy_models.TrainingFile.amo_id == record.amo_id,
            legacy_models.TrainingFile.record_id == record.id,
            legacy_models.TrainingFile.review_status == legacy_models.TrainingFileReviewStatus.APPROVED,
        ).first()
        if not evidence:
            blockers.append({"code": "EVIDENCE_MISSING", "message": "Approved completion evidence is required."})
    return blockers


def revoke_certificate(
    db: Session,
    *,
    actor: account_models.User,
    record_id: str,
    reason: str,
) -> legacy_models.TrainingCertificateIssue:
    amo_id = _amo_id(actor)
    record = _get_scoped(db, legacy_models.TrainingRecord, record_id, amo_id, "Training record")
    issue = db.query(legacy_models.TrainingCertificateIssue).filter(
        legacy_models.TrainingCertificateIssue.amo_id == amo_id,
        legacy_models.TrainingCertificateIssue.record_id == record.id,
        legacy_models.TrainingCertificateIssue.status == "VALID",
    ).order_by(legacy_models.TrainingCertificateIssue.issued_at.desc()).first()
    if not issue:
        raise HTTPException(status_code=409, detail={"code": "NO_VALID_CERTIFICATE", "message": "This training record has no valid certificate to revoke."})
    issue.status = "REVOKED"
    db.add(legacy_models.TrainingCertificateStatusHistory(
        amo_id=amo_id,
        certificate_issue_id=issue.id,
        status="REVOKED",
        reason=reason,
        actor_user_id=str(actor.id),
    ))
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.certificate", entity_id=str(issue.id), action="REVOKED", after={"record_id": str(record.id), "reason": reason}, critical=True)
    return issue


def reissue_certificate(
    db: Session,
    *,
    actor: account_models.User,
    record_id: str,
    reason: str,
) -> legacy_models.TrainingCertificateIssue:
    amo_id = _amo_id(actor)
    record = _get_scoped(db, legacy_models.TrainingRecord, record_id, amo_id, "Training record")
    blockers = completion_gate(db, record=record)
    if blockers:
        raise HTTPException(status_code=409, detail={"code": "TRAINING_COMPLETION_GATE_BLOCKED", "message": "Certificate reissue is blocked until completion controls are satisfied.", "blockers": blockers})
    current = db.query(legacy_models.TrainingCertificateIssue).filter(
        legacy_models.TrainingCertificateIssue.amo_id == amo_id,
        legacy_models.TrainingCertificateIssue.record_id == record.id,
    ).order_by(legacy_models.TrainingCertificateIssue.issued_at.desc()).first()
    if current and current.status == "VALID":
        current.status = "REVOKED"
        db.add(legacy_models.TrainingCertificateStatusHistory(
            amo_id=amo_id, certificate_issue_id=current.id, status="REVOKED",
            reason=f"Superseded by controlled reissue: {reason}", actor_user_id=str(actor.id),
        ))
    from .router import _certificate_verification_url, _next_certificate_number

    certificate_number = _next_certificate_number(db, amo_id)
    artifact_hash = hashlib.sha256(f"{record.id}:{certificate_number}:{record.completion_date}".encode("utf-8")).hexdigest()
    issue = legacy_models.TrainingCertificateIssue(
        amo_id=amo_id,
        record_id=record.id,
        certificate_number=certificate_number,
        issued_by_user_id=str(actor.id),
        status="VALID",
        qr_value=_certificate_verification_url(certificate_number, db, html_page=True),
        barcode_value=certificate_number,
        artifact_hash=artifact_hash,
    )
    db.add(issue)
    db.flush()
    db.add(legacy_models.TrainingCertificateStatusHistory(
        amo_id=amo_id, certificate_issue_id=issue.id, status="VALID",
        reason=f"Controlled reissue: {reason}", actor_user_id=str(actor.id),
    ))
    record.certificate_reference = certificate_number
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.certificate", entity_id=str(issue.id), action="REISSUED", after={"record_id": str(record.id), "supersedes_issue_id": str(current.id) if current else None, "reason": reason}, critical=True)
    return issue


def create_experience_log(db: Session, *, actor: account_models.User, payload: schemas.ExperienceLogCreate) -> models.TrainingExperienceLog:
    amo_id = _amo_id(actor)
    _get_scoped(db, account_models.User, payload.candidate_user_id, amo_id, "Candidate")
    row = models.TrainingExperienceLog(amo_id=amo_id, **payload.model_dump())
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.experience_log", entity_id=str(row.id), action="CREATED", after={"candidate_user_id": row.candidate_user_id, "activity_date": str(row.activity_date)})
    return row


def review_experience(db: Session, *, actor: account_models.User, payload: schemas.ExperienceReviewCreate) -> models.TrainingExperienceReview:
    amo_id = _amo_id(actor)
    settings = get_or_create_settings(db, amo_id=amo_id)
    row = models.TrainingExperienceReview(
        amo_id=amo_id, candidate_user_id=payload.candidate_user_id,
        authorization_case_id=payload.authorization_case_id,
        required_period_months=settings.experience_review_frequency_months,
        review_status=payload.review_status, reviewed_on=payload.reviewed_on,
        next_review_due=compliance.add_months(payload.reviewed_on, settings.experience_review_frequency_months),
        reviewer_user_id=str(actor.id), evidence_summary=payload.evidence_summary,
        training_file_id=payload.training_file_id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.experience_review", entity_id=str(row.id), action="RECORDED", after={"status": row.review_status, "next_review_due": str(row.next_review_due)})
    return row


def auditor_qualification_progress(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
) -> schemas.AuditorQualificationRead:
    _get_scoped(db, account_models.User, user_id, amo_id, "Person")
    target = get_or_create_settings(db, amo_id=amo_id).auditor_observer_count
    audits = db.query(quality_models.QMSAudit).filter(
        quality_models.QMSAudit.amo_id == amo_id,
        quality_models.QMSAudit.deleted_at.is_(None),
        quality_models.QMSAudit.status == quality_models.QMSAuditStatus.CLOSED,
        or_(
            quality_models.QMSAudit.observer_auditor_user_id == user_id,
            quality_models.QMSAudit.assistant_auditor_user_id == user_id,
        ),
    ).order_by(quality_models.QMSAudit.actual_end.desc(), quality_models.QMSAudit.created_at.desc()).all()
    audit_ids = list(dict.fromkeys(str(row.id) for row in audits))
    completed = len(audit_ids)
    return schemas.AuditorQualificationRead(
        user_id=user_id,
        completed_observer_audits=completed,
        required_observer_audits=target,
        remaining_observer_audits=max(0, target - completed),
        status="QUALIFIED" if completed >= target else "IN_PROGRESS",
        source="QMS closed audits where the person served as observer or assistant auditor",
        audit_ids=audit_ids,
    )


def create_authorization_case(db: Session, *, actor: account_models.User, payload: schemas.AuthorizationCaseCreate) -> models.TrainingAuthorizationCase:
    amo_id = _amo_id(actor)
    _get_scoped(db, account_models.User, payload.candidate_user_id, amo_id, "Candidate")
    _get_scoped(db, account_models.AuthorisationType, payload.authorisation_type_id, amo_id, "Authorisation type")
    row = models.TrainingAuthorizationCase(
        amo_id=amo_id, requested_by_user_id=str(actor.id),
        required_committee_positions=payload.required_committee_positions or DEFAULT_COMMITTEE_POSITIONS,
        **payload.model_dump(exclude={"required_committee_positions"}),
    )
    db.add(row)
    db.flush()
    compute_authorization_readiness(db, case=row)
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.authorization_case", entity_id=str(row.id), action="CREATED", after={"candidate_user_id": row.candidate_user_id, "authorisation_type_id": row.authorisation_type_id})
    return row


def _committee_holder(db: Session, *, amo_id: str, position_code: str) -> tuple[str | None, str]:
    label = position_code.replace("_", " ").title()
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(text("""
            SELECT COALESCE(delegated_to_user_id, user_id), postholder_code
            FROM auth_postholder_assignments
            WHERE amo_id = :amo_id AND postholder_code = :code AND status = 'ACTIVE'
              AND (valid_from IS NULL OR valid_from <= NOW())
              AND (valid_to IS NULL OR valid_to >= NOW())
            ORDER BY created_at DESC LIMIT 1
        """), {"amo_id": amo_id, "code": position_code}).first()
        if row:
            return str(row[0]), str(row[1]).replace("_", " ").title()
    return None, label


def compute_authorization_readiness(db: Session, *, case: models.TrainingAuthorizationCase) -> schemas.AuthorizationReadiness:
    amo_id = case.amo_id
    candidate = _get_scoped(db, account_models.User, case.candidate_user_id, amo_id, "Candidate")
    auth_type = _get_scoped(db, account_models.AuthorisationType, case.authorisation_type_id, amo_id, "Authorisation type")
    items: list[schemas.ReadinessItem] = []
    policy = compliance.evaluate_user_training_policy(db, candidate, required_only=True)
    missing_training = len(policy.overdue_items) + len(policy.not_done_items)
    items.append(schemas.ReadinessItem(
        key="mandatory_training", label="Mandatory training", status="COMPLETE" if not missing_training else "MISSING",
        blocking=True, reason="All mandatory training is current." if not missing_training else f"{missing_training} mandatory course(s) are overdue or not completed.",
        source="training requirements and training records",
    ))
    if auth_type.requires_valid_licence:
        licence = db.query(workbook_models.PersonnelLicence).filter(
            workbook_models.PersonnelLicence.amo_id == amo_id,
            workbook_models.PersonnelLicence.user_id == candidate.id,
            workbook_models.PersonnelLicence.status == "ACTIVE",
            or_(workbook_models.PersonnelLicence.expires_on.is_(None), workbook_models.PersonnelLicence.expires_on >= date.today()),
        ).first()
        items.append(schemas.ReadinessItem(
            key="licence", label="Regulatory licence", status="CURRENT" if licence else "MISSING", blocking=True,
            reason="A current licence is recorded." if licence else "A current licence is required by this authorization type.", source="personnel licence register",
        ))
    latest_review = db.query(models.TrainingExperienceReview).filter(
        models.TrainingExperienceReview.amo_id == amo_id,
        models.TrainingExperienceReview.candidate_user_id == candidate.id,
        or_(models.TrainingExperienceReview.authorization_case_id == case.id, models.TrainingExperienceReview.authorization_case_id.is_(None)),
    ).order_by(models.TrainingExperienceReview.reviewed_on.desc()).first()
    experience_ok = bool(latest_review and latest_review.review_status == "SATISFACTORY" and latest_review.next_review_due >= date.today())
    items.append(schemas.ReadinessItem(
        key="experience_review", label="Recent experience review", status="COMPLETE" if experience_ok else "MISSING", blocking=True,
        reason="Recent experience is satisfactory." if experience_ok else "A current satisfactory experience review is required.", source="experience review register",
    ))
    assessments = db.query(models.TrainingAssessmentInstance, models.TrainingAssessmentTemplate).join(
        models.TrainingAssessmentTemplate, models.TrainingAssessmentTemplate.id == models.TrainingAssessmentInstance.template_id,
    ).filter(
        models.TrainingAssessmentInstance.amo_id == amo_id,
        models.TrainingAssessmentInstance.candidate_user_id == candidate.id,
        models.TrainingAssessmentInstance.authorization_case_id == case.id,
    ).all()
    passed_types = {
        template.assessment_type
        for assessment, template in assessments
        if assessment.status == "APPROVED" and assessment.outcome in {"PASS", "COMPETENT", "SATISFACTORY"}
    }
    for assessment_type in case.required_assessment_types or []:
        passed = assessment_type in passed_types
        items.append(schemas.ReadinessItem(
            key=f"assessment_{assessment_type.lower()}", label=f"{assessment_type.title()} assessment",
            status="COMPLETE" if passed else "NOT_STARTED", blocking=True,
            reason="Approved passing outcome recorded." if passed else "Approved passing outcome is required.", source="assessment register",
        ))
    committee_ready = True
    for position in case.required_committee_positions or []:
        holder, label = _committee_holder(db, amo_id=amo_id, position_code=position)
        decided = db.query(models.TrainingCommitteeDecision).filter(
            models.TrainingCommitteeDecision.authorization_case_id == case.id,
            models.TrainingCommitteeDecision.position_code == position,
        ).first()
        status_value = "COMPLETE" if decided else "READY" if holder else "BLOCKED"
        committee_ready = committee_ready and bool(decided)
        items.append(schemas.ReadinessItem(
            key=f"committee_{position.lower()}", label=label, status=status_value, blocking=True,
            reason=f"Decision recorded: {decided.decision}." if decided else "Assigned postholder decision is required." if holder else "No active postholder/delegate is assigned.",
            source="postholder assignments and committee decisions",
        ))
    pre_committee_blockers = [item for item in items if item.blocking and item.key.startswith("committee_") is False and item.status not in {"CURRENT", "COMPLETE", "READY", "NOT_APPLICABLE"}]
    decisions = db.query(models.TrainingCommitteeDecision).filter(models.TrainingCommitteeDecision.authorization_case_id == case.id).all()
    if any(row.decision == "REJECT" for row in decisions):
        overall = "REJECTED"
    elif any(row.decision == "DEFER" for row in decisions):
        overall = "DEFERRED"
    elif pre_committee_blockers:
        overall = "NOT_READY"
    elif len(passed_types) < len(set(case.required_assessment_types or [])):
        overall = "ASSESSMENT_IN_PROGRESS"
    elif committee_ready and decisions:
        overall = "APPROVED"
    elif decisions:
        overall = "DECISION_REQUIRED"
    else:
        overall = "READY_FOR_COMMITTEE"
    case.status = overall
    case.readiness_snapshot = {"overall_status": overall, "items": [item.model_dump(mode="json") for item in items]}
    case.readiness_computed_at = utcnow()
    return schemas.AuthorizationReadiness(
        case_id=str(case.id), overall_status=overall, items=items,
        next_required_action="Issue authorization" if overall == "APPROVED" else "Complete the first blocking readiness item" if pre_committee_blockers else "Record remaining committee decisions",
        action_owner=case.owner_user_id, computed_at=case.readiness_computed_at,
    )


def decide_committee(
    db: Session,
    *,
    actor: account_models.User,
    case_id: str,
    payload: schemas.CommitteeDecisionCreate,
) -> models.TrainingCommitteeDecision:
    amo_id = _amo_id(actor)
    case = _get_scoped(db, models.TrainingAuthorizationCase, case_id, amo_id, "Authorization case")
    if payload.position_code not in (case.required_committee_positions or []):
        raise HTTPException(status_code=422, detail="That position is not a required member of this case committee.")
    holder_id, label = _committee_holder(db, amo_id=amo_id, position_code=payload.position_code)
    if not holder_id:
        raise HTTPException(status_code=409, detail={"code": "POSTHOLDER_NOT_ASSIGNED", "position_code": payload.position_code})
    if holder_id != str(actor.id):
        raise HTTPException(status_code=403, detail="Only the active postholder or recorded delegate may decide for this position.")
    require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=case.requested_by_user_id, action="decide")
    existing = db.query(models.TrainingCommitteeDecision).filter(
        models.TrainingCommitteeDecision.authorization_case_id == case.id,
        models.TrainingCommitteeDecision.position_code == payload.position_code,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This committee position has already recorded a decision.")
    row = models.TrainingCommitteeDecision(
        amo_id=amo_id, authorization_case_id=case.id, member_user_id=str(actor.id),
        position_code=payload.position_code, position_label_snapshot=label,
        decision=payload.decision, comments=payload.comments,
        evidence_snapshot=case.readiness_snapshot or {},
    )
    db.add(row)
    db.flush()
    compute_authorization_readiness(db, case=case)
    if payload.decision in {"REJECT", "DEFER"}:
        case.decision = payload.decision
        case.decision_at = utcnow()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.authorization_case", entity_id=str(case.id), action=f"COMMITTEE_{payload.decision}", after={"position_code": payload.position_code}, critical=True)
    return row


def issue_authorization(
    db: Session,
    *,
    actor: account_models.User,
    case_id: str,
    payload: schemas.AuthorizationIssueCreate,
) -> account_models.UserAuthorisation:
    amo_id = _amo_id(actor)
    case = _get_scoped(db, models.TrainingAuthorizationCase, case_id, amo_id, "Authorization case")
    readiness = compute_authorization_readiness(db, case=case)
    if readiness.overall_status != "APPROVED":
        raise HTTPException(status_code=409, detail={"code": "AUTHORIZATION_NOT_READY", "readiness": readiness.model_dump(mode="json")})
    require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=case.requested_by_user_id, action="issue")
    if payload.expires_at and payload.expires_at < payload.effective_from:
        raise HTTPException(status_code=422, detail="Authorization expiry cannot precede its effective date.")
    existing = db.query(account_models.UserAuthorisation).filter(
        account_models.UserAuthorisation.user_id == case.candidate_user_id,
        account_models.UserAuthorisation.authorisation_type_id == case.authorisation_type_id,
        account_models.UserAuthorisation.effective_from == payload.effective_from,
    ).first()
    if existing:
        case.issued_user_authorisation_id = existing.id
        return existing
    scope = case.requested_scope
    restrictions = payload.restrictions or case.restrictions
    if restrictions:
        scope = f"{scope or ''}\nRestrictions: {restrictions}".strip()
    row = account_models.UserAuthorisation(
        user_id=case.candidate_user_id,
        authorisation_type_id=case.authorisation_type_id,
        scope_text=scope,
        effective_from=payload.effective_from,
        expires_at=payload.expires_at,
        granted_by_user_id=str(actor.id),
    )
    db.add(row)
    db.flush()
    case.issued_user_authorisation_id = row.id
    case.status = "ISSUED"
    case.decision = "APPROVE"
    case.decision_at = utcnow()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="accounts.user_authorisation", entity_id=str(row.id), action="ISSUED_FROM_TRAINING_CASE", after={"case_id": case.id, "candidate_user_id": case.candidate_user_id}, critical=True)
    return row


def recommend_authorization(
    db: Session,
    *,
    actor: account_models.User,
    case_id: str,
    payload: schemas.AuthorizationRecommendationCreate,
) -> models.TrainingAuthorizationCase:
    amo_id = _amo_id(actor)
    case = _get_scoped(db, models.TrainingAuthorizationCase, case_id, amo_id, "Authorization case")
    readiness = compute_authorization_readiness(db, case=case)
    if readiness.overall_status not in {"READY_FOR_COMMITTEE", "DECISION_REQUIRED", "APPROVED"}:
        raise HTTPException(status_code=409, detail={"code": "AUTHORIZATION_NOT_READY_FOR_RECOMMENDATION", "readiness": readiness.model_dump(mode="json")})
    require_not_self_approval(actor_user_id=str(actor.id), originator_user_id=case.requested_by_user_id, action="recommend")
    case.recommendation = f"{payload.recommendation}: {payload.rationale}"
    if payload.proposed_restrictions:
        case.restrictions = payload.proposed_restrictions
    if payload.recommendation == "DO_NOT_RECOMMEND":
        case.status = "REJECTED"
    elif payload.recommendation == "DEFER":
        case.status = "DEFERRED"
    else:
        case.status = "DECISION_REQUIRED"
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.authorization_case", entity_id=str(case.id), action="RECOMMENDED", after={"recommendation": payload.recommendation, "rationale": payload.rationale}, critical=True)
    return case


def authorization_lifecycle(
    db: Session,
    *,
    actor: account_models.User,
    case_id: str,
    payload: schemas.AuthorizationLifecycleAction,
) -> models.TrainingAuthorizationCase:
    amo_id = _amo_id(actor)
    case = _get_scoped(db, models.TrainingAuthorizationCase, case_id, amo_id, "Authorization case")
    if not case.issued_user_authorisation_id:
        raise HTTPException(status_code=409, detail="This case has no issued canonical authorization.")
    authorization = db.query(account_models.UserAuthorisation).join(account_models.User).filter(
        account_models.UserAuthorisation.id == case.issued_user_authorisation_id,
        account_models.User.amo_id == amo_id,
    ).first()
    if not authorization:
        raise HTTPException(status_code=404, detail="The issued canonical authorization was not found in this tenant.")
    if payload.action == "RESTRICT":
        if not payload.restrictions:
            raise HTTPException(status_code=422, detail="Restrictions are required for a restriction action.")
        case.restrictions = payload.restrictions
        authorization.scope_text = f"{case.requested_scope or ''}\nRestrictions: {payload.restrictions}".strip()
        case.status = "RESTRICTED"
    else:
        authorization.revoked_at = utcnow()
        authorization.revoked_reason = f"{payload.action}: {payload.reason}"
        case.status = "SUSPENDED" if payload.action == "SUSPEND" else "WITHDRAWN"
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="accounts.user_authorisation", entity_id=str(authorization.id), action=payload.action, after={"case_id": str(case.id), "reason": payload.reason, "restrictions": payload.restrictions}, critical=True)
    return case


def create_effectiveness(db: Session, *, actor: account_models.User, payload: schemas.EffectivenessCreate) -> models.TrainingEffectivenessEvaluation:
    amo_id = _amo_id(actor)
    _get_scoped(db, legacy_models.TrainingCourse, payload.course_id, amo_id, "Course")
    if payload.evaluation_period_start and payload.evaluation_period_end and payload.evaluation_period_end < payload.evaluation_period_start:
        raise HTTPException(status_code=422, detail="Effectiveness period end must be on or after its start.")
    if payload.level == 4 and not rules.level_four_causation_allowed(causation_claimed=payload.causation_claimed, evidence=payload.evidence, conclusion=payload.conclusion):
        raise HTTPException(status_code=422, detail={"code": "CAUSATION_EVIDENCE_INSUFFICIENT", "required_evidence": ["baseline", "comparison", "confounders", "method", "conclusion"]})
    row = models.TrainingEffectivenessEvaluation(
        amo_id=amo_id, reviewer_user_id=str(actor.id), **payload.model_dump()
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.effectiveness", entity_id=str(row.id), action="CREATED", after={"course_id": row.course_id, "level": row.level, "causation_claimed": row.causation_claimed})
    return row


def create_competence_review(db: Session, *, actor: account_models.User, payload: schemas.CompetenceReviewCreate) -> models.TrainingCompetenceReview:
    amo_id = _amo_id(actor)
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="Competence review period end must be on or after its start.")
    row = models.TrainingCompetenceReview(
        amo_id=amo_id, reviewer_user_id=str(actor.id), status="SUBMITTED", **payload.model_dump()
    )
    db.add(row)
    db.flush()
    if payload.outcome != "COMPETENT":
        task_services.create_task(
            db, amo_id=amo_id, title="Competence gap action required",
            description=payload.gaps or payload.actions or f"Competence review outcome: {payload.outcome}",
            owner_user_id=str(actor.id), due_at=utcnow() + timedelta(days=14),
            entity_type="training.competence_review", entity_id=str(row.id), priority=2,
            metadata={"module": "training", "candidate_user_id": payload.candidate_user_id},
        )
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.competence_review", entity_id=str(row.id), action="RECORDED", after={"candidate_user_id": row.candidate_user_id, "outcome": row.outcome})
    return row


def create_remedial_action(db: Session, *, actor: account_models.User, payload: schemas.RemedialActionCreate) -> models.TrainingRemedialAction:
    amo_id = _amo_id(actor)
    row = models.TrainingRemedialAction(amo_id=amo_id, status="OPEN", **payload.model_dump())
    db.add(row)
    db.flush()
    task_services.create_task(
        db, amo_id=amo_id, title="Complete remedial training",
        description=f"Gap: {payload.gap}\nRequired activity: {payload.required_activity}",
        owner_user_id=payload.owner_user_id or payload.candidate_user_id,
        due_at=datetime.combine(payload.due_date, time(23, 59), tzinfo=UTC),
        entity_type="training.remedial_action", entity_id=str(row.id), priority=2,
        metadata={"module": "training", "candidate_user_id": payload.candidate_user_id},
    )
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.remedial_action", entity_id=str(row.id), action="CREATED", after={"candidate_user_id": row.candidate_user_id, "due_date": str(row.due_date)})
    return row


def next_batch(db: Session, *, amo_id: str, course_id: str, limit: int = 50) -> schemas.NextBatchRead:
    course = _get_scoped(db, legacy_models.TrainingCourse, course_id, amo_id, "Course")
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    candidates: list[schemas.NextBatchCandidate] = []
    today = date.today()
    for user in users:
        evaluation = compliance.evaluate_user_training_policy(db, user, required_only=True, today=today)
        item = next((value for value in evaluation.items if value.course_id == course.course_id), None)
        if not item:
            continue
        event = db.query(legacy_models.TrainingEvent).join(legacy_models.TrainingEventParticipant).filter(
            legacy_models.TrainingEvent.amo_id == amo_id,
            legacy_models.TrainingEvent.course_id == course.id,
            legacy_models.TrainingEvent.starts_on >= today,
            legacy_models.TrainingEventParticipant.user_id == user.id,
            legacy_models.TrainingEventParticipant.status.in_([
                legacy_models.TrainingParticipantStatus.SCHEDULED,
                legacy_models.TrainingParticipantStatus.INVITED,
                legacy_models.TrainingParticipantStatus.CONFIRMED,
            ]),
        ).order_by(legacy_models.TrainingEvent.starts_on.asc()).first()
        availability = db.query(quality_models.UserAvailability).filter(
            quality_models.UserAvailability.amo_id == amo_id,
            quality_models.UserAvailability.user_id == user.id,
            quality_models.UserAvailability.status != quality_models.UserAvailabilityStatus.ON_DUTY,
            or_(quality_models.UserAvailability.effective_to.is_(None), quality_models.UserAvailability.effective_to >= utcnow()),
        ).order_by(quality_models.UserAvailability.effective_from.desc()).first()
        item_status = str(item.status)
        days = getattr(item, "days_until_due", None)
        rank_reason = "Never completed" if item_status == "NOT_DONE" else f"{item_status.replace('_', ' ').title()} ({days} day(s))" if days is not None else item_status
        candidates.append(schemas.NextBatchCandidate(
            user_id=str(user.id), full_name=user.full_name, staff_code=user.staff_code,
            department=getattr(getattr(user, "department", None), "code", None), status=item_status,
            due_date=getattr(item, "due_date", None), days_remaining=days,
            existing_booking=f"{event.title} on {event.starts_on}" if event else None,
            availability_conflict=f"{_enum(availability.status)} until {availability.effective_to.date() if availability.effective_to else 'open-ended'}" if availability else None,
            authorization_impact="Mandatory training gap may block authorization readiness." if item_status in {"OVERDUE", "NOT_DONE"} else None,
            eligible=not bool(event), rank_reason=rank_reason,
        ))
    severity = {"OVERDUE": 0, "NOT_DONE": 1, "DUE_SOON": 2, "SCHEDULED_ONLY": 3, "OK": 4}
    candidates.sort(key=lambda value: (severity.get(value.status, 9), value.days_remaining if value.days_remaining is not None else 999999, value.full_name.lower()))
    return schemas.NextBatchRead(course_id=str(course.id), course_code=course.course_id, course_name=course.course_name, candidates=candidates[: max(1, min(limit, 200))])


def course_audit(db: Session, *, amo_id: str, course_id: str) -> schemas.CourseAuditRead:
    course = _get_scoped(db, legacy_models.TrainingCourse, course_id, amo_id, "Course")
    users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True), account_models.User.is_system_account.is_(False)).all()
    exceptions: list[schemas.CourseAuditException] = []
    current = overdue = never = required = 0
    for user in users:
        evaluation = compliance.evaluate_user_training_policy(db, user, required_only=True)
        item = next((value for value in evaluation.items if value.course_id == course.course_id), None)
        if not item:
            continue
        required += 1
        if item.status == "OK":
            current += 1
        elif item.status == "OVERDUE":
            overdue += 1
        elif item.status == "NOT_DONE":
            never += 1
        if item.status in {"OVERDUE", "NOT_DONE", "DUE_SOON"}:
            exceptions.append(schemas.CourseAuditException(
                user_id=str(user.id), full_name=user.full_name, staff_code=user.staff_code,
                exception_code=f"TRAINING_{item.status}", severity="CRITICAL" if item.status in {"OVERDUE", "NOT_DONE"} else "WARNING",
                detail=f"{course.course_name}: {item.status.replace('_', ' ').lower()}.",
                correction_path=f"/training/competence/people/{user.id}",
            ))
    return schemas.CourseAuditRead(course_id=str(course.id), course_code=course.course_id, course_name=course.course_name, required_people=required, current_people=current, overdue_people=overdue, never_completed_people=never, exceptions=exceptions)


def _tenant_training_counts(db: Session, *, amo_id: str, today: date) -> dict[str, int]:
    """Evaluate tenant obligations in bounded, set-based reads.

    The legacy dashboard called the full per-person policy evaluator for every
    employee. That is accurate for an individual profile, but it multiplies
    catalogue, requirement, record, deferral and event queries by headcount.
    This projection loads each source once and evaluates the same due-date
    categories in memory, so dashboard cost grows with rows rather than queries.
    """

    users = db.query(
        account_models.User.id,
        account_models.User.staff_code,
        account_models.User.position_title,
        account_models.Department.code,
    ).outerjoin(
        account_models.Department,
        account_models.Department.id == account_models.User.department_id,
    ).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    courses = db.query(legacy_models.TrainingCourse).filter(
        legacy_models.TrainingCourse.amo_id == amo_id,
        legacy_models.TrainingCourse.is_active.is_(True),
    ).all()
    course_by_id = {str(course.id): course for course in courses}
    requirements = db.query(legacy_models.TrainingRequirement).options(noload("*")).filter(
        legacy_models.TrainingRequirement.amo_id == amo_id,
        legacy_models.TrainingRequirement.is_active.is_(True),
        legacy_models.TrainingRequirement.is_mandatory.is_(True),
        or_(legacy_models.TrainingRequirement.effective_from.is_(None), legacy_models.TrainingRequirement.effective_from <= today),
        or_(legacy_models.TrainingRequirement.effective_to.is_(None), legacy_models.TrainingRequirement.effective_to >= today),
    ).all()

    required_for_all: set[str] = set()
    required_by_user: dict[str, set[str]] = {}
    required_by_department: dict[str, set[str]] = {}
    required_by_job: dict[str, set[str]] = {}
    for requirement in requirements:
        course_id = str(requirement.course_id)
        scope = _enum(requirement.scope).upper()
        if scope == "ALL":
            required_for_all.add(course_id)
        elif scope == "USER" and requirement.user_id:
            required_by_user.setdefault(str(requirement.user_id), set()).add(course_id)
        elif scope == "DEPARTMENT" and requirement.department_code:
            required_by_department.setdefault(requirement.department_code.strip().upper(), set()).add(course_id)
        elif scope == "JOB_ROLE" and requirement.job_role:
            required_by_job.setdefault(requirement.job_role.strip().lower(), set()).add(course_id)
    fallback_courses = {str(course.id) for course in courses if bool(course.is_mandatory)} if not requirements else set()

    role_courses_by_user: dict[str, set[str]] = {}
    role_courses_by_staff: dict[str, set[str]] = {}
    table_names = set(inspect(db.connection()).get_table_names())
    if {"training_role_groups", "training_person_roles", "training_course_role_rules"}.issubset(table_names):
        all_role_ids = {
            str(group_id)
            for (group_id,) in db.query(workbook_models.TrainingRoleGroup.id).filter(
                workbook_models.TrainingRoleGroup.amo_id == amo_id,
                workbook_models.TrainingRoleGroup.is_active.is_(True),
                workbook_models.TrainingRoleGroup.code == "ALL",
            ).all()
        }
        courses_by_role: dict[str, set[str]] = {}
        for role_id, course_id in db.query(
            workbook_models.TrainingCourseRoleRule.role_group_id,
            workbook_models.TrainingCourseRoleRule.course_id,
        ).filter(
            workbook_models.TrainingCourseRoleRule.amo_id == amo_id,
            workbook_models.TrainingCourseRoleRule.is_active.is_(True),
            workbook_models.TrainingCourseRoleRule.is_required.is_(True),
        ).all():
            courses_by_role.setdefault(str(role_id), set()).add(str(course_id))
        all_role_courses = set().union(*(courses_by_role.get(role_id, set()) for role_id in all_role_ids)) if all_role_ids else set()
        for user_id, person_id, role_id in db.query(
            workbook_models.TrainingPersonRole.user_id,
            workbook_models.TrainingPersonRole.person_id,
            workbook_models.TrainingPersonRole.role_group_id,
        ).filter(
            workbook_models.TrainingPersonRole.amo_id == amo_id,
            workbook_models.TrainingPersonRole.is_active.is_(True),
        ).all():
            role_courses = all_role_courses | courses_by_role.get(str(role_id), set())
            if user_id:
                role_courses_by_user.setdefault(str(user_id), set()).update(role_courses)
            if person_id:
                role_courses_by_staff.setdefault(str(person_id).strip().upper(), set()).update(role_courses)
        if all_role_courses:
            for user_id, staff_code, _position_title, _department_code in users:
                role_courses_by_user.setdefault(str(user_id), set()).update(all_role_courses)

    latest_records: dict[tuple[str, str], legacy_models.TrainingRecord] = {}
    ranked_records = db.query(
        legacy_models.TrainingRecord.id.label("record_id"),
        func.row_number().over(
            partition_by=(legacy_models.TrainingRecord.user_id, legacy_models.TrainingRecord.course_id),
            order_by=(
                legacy_models.TrainingRecord.valid_until.desc().nullslast(),
                legacy_models.TrainingRecord.completion_date.desc().nullslast(),
                legacy_models.TrainingRecord.created_at.desc().nullslast(),
            ),
        ).label("record_rank"),
    ).filter(
        legacy_models.TrainingRecord.amo_id == amo_id,
        legacy_models.TrainingRecord.verification_status == legacy_models.TrainingRecordVerificationStatus.VERIFIED,
        training_record_lifecycle.active_records_filter(legacy_models.TrainingRecord),
    ).subquery()
    record_rows = db.query(legacy_models.TrainingRecord).options(noload("*")).join(
        ranked_records,
        and_(ranked_records.c.record_id == legacy_models.TrainingRecord.id, ranked_records.c.record_rank == 1),
    ).all()
    for record in record_rows:
        key = (str(record.user_id), str(record.course_id))
        existing = latest_records.get(key)
        record_rank = (record.valid_until or date.min, record.completion_date or date.min, record.created_at.isoformat() if record.created_at else "")
        if existing is None:
            latest_records[key] = record
            continue
        existing_rank = (existing.valid_until or date.min, existing.completion_date or date.min, existing.created_at.isoformat() if existing.created_at else "")
        if record_rank > existing_rank:
            latest_records[key] = record

    deferrals: dict[tuple[str, str], date] = {}
    for user_id, course_id, requested_due in db.query(
        legacy_models.TrainingDeferralRequest.user_id,
        legacy_models.TrainingDeferralRequest.course_id,
        func.max(legacy_models.TrainingDeferralRequest.requested_new_due_date),
    ).filter(
        legacy_models.TrainingDeferralRequest.amo_id == amo_id,
        legacy_models.TrainingDeferralRequest.status == legacy_models.DeferralStatus.APPROVED,
    ).group_by(
        legacy_models.TrainingDeferralRequest.user_id,
        legacy_models.TrainingDeferralRequest.course_id,
    ).all():
        key = (str(user_id), str(course_id))
        if requested_due and requested_due > deferrals.get(key, date.min):
            deferrals[key] = requested_due

    upcoming = {
        (str(user_id), str(course_id))
        for user_id, course_id in db.query(
            legacy_models.TrainingEventParticipant.user_id,
            legacy_models.TrainingEvent.course_id,
        ).join(
            legacy_models.TrainingEvent,
            legacy_models.TrainingEvent.id == legacy_models.TrainingEventParticipant.event_id,
        ).filter(
            legacy_models.TrainingEvent.amo_id == amo_id,
            legacy_models.TrainingEvent.starts_on >= today,
            legacy_models.TrainingEvent.status == legacy_models.TrainingEventStatus.PLANNED,
            legacy_models.TrainingEventParticipant.amo_id == amo_id,
            legacy_models.TrainingEventParticipant.status.in_([
                legacy_models.TrainingParticipantStatus.SCHEDULED,
                legacy_models.TrainingParticipantStatus.INVITED,
                legacy_models.TrainingParticipantStatus.CONFIRMED,
            ]),
        ).all()
    }

    counts = {"overdue": 0, "due_soon": 0, "never": 0}
    for user_id, staff_code, position_title, department_code in users:
        user_key = str(user_id)
        required = set(fallback_courses or required_for_all)
        required.update(required_by_user.get(user_key, set()))
        if department_code:
            required.update(required_by_department.get(str(department_code).strip().upper(), set()))
        if position_title:
            required.update(required_by_job.get(str(position_title).strip().lower(), set()))
        required.update(role_courses_by_user.get(user_key, set()))
        if staff_code:
            required.update(role_courses_by_staff.get(str(staff_code).strip().upper(), set()))
        for course_id in required:
            course = course_by_id.get(course_id)
            if not course:
                continue
            key = (user_key, course_id)
            record = latest_records.get(key)
            if not record:
                if key not in upcoming:
                    counts["never"] += 1
                continue
            due_date = record.valid_until
            if due_date is None and course.frequency_months:
                due_date = compliance.add_months(record.completion_date, int(course.frequency_months))
            deferral_due = deferrals.get(key)
            if deferral_due and (due_date is None or deferral_due > due_date):
                due_date = deferral_due
            if due_date is None:
                continue
            if due_date < today:
                counts["overdue"] += 1
            elif (due_date - today).days <= int(course.planning_lead_days or compliance.DEFAULT_DUE_SOON_WINDOW):
                counts["due_soon"] += 1
    return counts


def control_room(db: Session, *, actor: account_models.User) -> schemas.TrainingControlRoomRead:
    amo_id = _amo_id(actor)
    queues: list[schemas.ActionQueueItem] = []
    source_errors: list[str] = []

    def add(key: str, label: str, count: int | None, severity: str, reason: str, action: str, path: str, *, available: bool = True) -> None:
        queues.append(schemas.ActionQueueItem(key=key, label=label, count=count, severity=severity, reason=reason, action_label=action, path=path, available=available))

    try:
        counts = _tenant_training_counts(db, amo_id=amo_id, today=date.today())
        overdue, due_soon, never = counts["overdue"], counts["due_soon"], counts["never"]
        add("overdue", "Overdue mandatory training", overdue, "CRITICAL", "Current mandatory obligations have passed their due date.", "Resolve overdue", "/training/competence/overdue")
        add("due_soon", "Training due soon", due_soon, "WARNING", "Training is inside its configurable planning lead window.", "Build a batch", "/training/competence/plan")
        add("never_completed", "Never completed", never, "CRITICAL", "Mandatory training has no valid completion record.", "Review people", "/training/competence/people")
    except Exception as exc:
        source_errors.append(f"training_compliance: {type(exc).__name__}")
        for key, label, path in (
            ("overdue", "Overdue mandatory training", "/training/competence/overdue"),
            ("due_soon", "Training due soon", "/training/competence/plan"),
            ("never_completed", "Never completed", "/training/competence/people"),
        ):
            add(key, label, None, "CRITICAL", "Source unavailable. This count is Unknown, not zero.", "Retry source", path, available=False)

    count_specs = [
        ("assessments", "Assessments awaiting review", models.TrainingAssessmentInstance, models.TrainingAssessmentInstance.status == "SUBMITTED", "WARNING", "Independent assessment review is pending.", "Review assessments", "/training/competence/assessments"),
        ("authorization", "Authorization decisions", models.TrainingAuthorizationCase, models.TrainingAuthorizationCase.status.in_(["READY_FOR_COMMITTEE", "DECISION_REQUIRED", "APPROVED"]), "WARNING", "Authorization readiness or committee action is pending.", "Open authorization cases", "/training/competence/authorizations"),
        ("experience", "Experience reviews due", models.TrainingExperienceReview, models.TrainingExperienceReview.next_review_due <= date.today(), "WARNING", "The configured recent-experience review interval has elapsed.", "Review experience", "/training/competence/authorizations"),
        ("remedial", "Open remedial actions", models.TrainingRemedialAction, models.TrainingRemedialAction.status == "OPEN", "CRITICAL", "Training or competence gaps have open corrective work.", "Manage remedial actions", "/training/competence/assessments"),
    ]
    for key, label, model, criterion, severity, reason, action, path in count_specs:
        try:
            count = db.query(func.count(model.id)).filter(model.amo_id == amo_id, criterion).scalar() or 0
            add(key, label, int(count), severity, reason, action, path)
        except Exception as exc:
            source_errors.append(f"{key}: {type(exc).__name__}")
            add(key, label, None, severity, "Source unavailable. This count is Unknown, not zero.", "Retry source", path, available=False)
    operational_specs = [
        ("import_review", "Imports needing resolution", workbook_models.TrainingWorkbookImportJob, workbook_models.TrainingWorkbookImportJob.status.in_(["REVIEW_REQUIRED", "FAILED"]), "WARNING", "A retained workbook preview has unresolved identities, conflicts or a failed stage.", "Resolve imports", "/training/competence/settings#import-history"),
        ("plan_changes", "Plan changes awaiting acceptance", models.TrainingChangeRequest, and_(models.TrainingChangeRequest.object_type == "PLAN", models.TrainingChangeRequest.status == "PREVIEW"), "WARNING", "An autonomous recalculation has a durable change set awaiting planner acceptance.", "Review plan changes", "/training/competence/plan"),
        ("attendance_windows", "Open or expired sign-in windows", models.TrainingAttendanceWindow, models.TrainingAttendanceWindow.status.in_(["OPEN", "EXPIRED"]), "WARNING", "An attendance window still needs closure, roster review or certification.", "Open attendance", "/training/competence/attendance"),
        ("invitation_failures", "Invitation delivery failures", models.TrainingSessionInvitation, models.TrainingSessionInvitation.delivery_status == "FAILED", "WARNING", "One or more scheduled attendees did not receive a configured invitation channel.", "Resolve delivery", "/training/competence/sessions"),
        ("workflow_backlog", "Controlled forms in progress", models.TrainingWorkflowInstance, ~models.TrainingWorkflowInstance.status.in_(["COMPLETED", "CANCELLED"]), "WARNING", "Induction, competence, experience, OJT or authorization form steps remain open.", "Open workflows", "/training/competence/assessments"),
        ("evidence_review", "Evidence awaiting review", legacy_models.TrainingFile, legacy_models.TrainingFile.review_status == legacy_models.TrainingFileReviewStatus.PENDING, "WARNING", "Uploaded completion evidence is not yet approved for a completion gate.", "Review evidence", "/training/competence/people"),
        ("budget_variance", "Budget lines over approval", models.TrainingBudgetLine, models.TrainingBudgetLine.actual_amount > models.TrainingBudgetLine.approved_amount, "CRITICAL", "Actual training spend exceeds its approved amount.", "Review variance", "/training/competence/budget"),
        ("report_failures", "Failed retained report jobs", models.TrainingReportJob, models.TrainingReportJob.status == "FAILED", "WARNING", "A complete server export failed and remains available for diagnosis and retry.", "Review report jobs", "/training/competence/reports"),
    ]
    for key, label, model, criterion, severity, reason, action, path in operational_specs:
        try:
            count = int(db.query(func.count(model.id)).filter(model.amo_id == amo_id, criterion).scalar() or 0)
            add(key, label, count, severity, reason, action, path)
        except Exception as exc:
            source_errors.append(f"{key}: {type(exc).__name__}")
            add(key, label, None, severity, "Source unavailable. This count is Unknown, not zero.", "Retry source", path, available=False)
    try:
        active_setup = db.query(models.TrainingSetupVersion.id).filter(models.TrainingSetupVersion.amo_id == amo_id, models.TrainingSetupVersion.status == "ACTIVE").first()
        add("setup", "Tenant setup readiness", 0 if active_setup else 1, "CRITICAL", "A validated, independently activated tenant setup version is required for governed go-live.", "Complete setup", "/training/competence/settings")
    except Exception as exc:
        source_errors.append(f"setup: {type(exc).__name__}")
        add("setup", "Tenant setup readiness", None, "CRITICAL", "Setup source unavailable. Readiness is Unknown.", "Retry setup", "/training/competence/settings", available=False)
    try:
        expiry_horizon = date.today() + timedelta(days=90)
        expiring_auth = db.query(func.count(account_models.UserAuthorisation.id)).join(
            account_models.User, account_models.User.id == account_models.UserAuthorisation.user_id,
        ).filter(
            account_models.User.amo_id == amo_id,
            account_models.UserAuthorisation.revoked_at.is_(None),
            account_models.UserAuthorisation.expires_at.isnot(None),
            account_models.UserAuthorisation.expires_at <= expiry_horizon,
        ).scalar() or 0
        add("authorization_expiry", "Authorizations expiring", int(expiring_auth), "CRITICAL", "Canonical personnel privileges expire within 90 days or are already overdue.", "Start renewal", "/training/competence/authorizations")
    except Exception as exc:
        source_errors.append(f"authorization_expiry: {type(exc).__name__}")
        add("authorization_expiry", "Authorizations expiring", None, "CRITICAL", "Authorization source unavailable. This count is Unknown.", "Retry source", "/training/competence/authorizations", available=False)
    try:
        uncertified = db.query(func.count(legacy_models.TrainingEvent.id)).filter(
            legacy_models.TrainingEvent.amo_id == amo_id,
            legacy_models.TrainingEvent.status == legacy_models.TrainingEventStatus.COMPLETED,
            ~legacy_models.TrainingEvent.id.in_(
                db.query(models.TrainingAttendanceWindow.event_id).filter(
                    models.TrainingAttendanceWindow.amo_id == amo_id,
                    models.TrainingAttendanceWindow.status == "CERTIFIED",
                )
            ),
        ).scalar() or 0
        add("attendance", "Attendance awaiting certification", int(uncertified), "WARNING", "Completed sessions need a certified attendance register.", "Certify registers", "/training/competence/attendance")
    except Exception as exc:
        source_errors.append(f"attendance: {type(exc).__name__}")
        add("attendance", "Attendance awaiting certification", None, "WARNING", "Source unavailable. This count is Unknown, not zero.", "Retry source", "/training/competence/attendance", available=False)
    return schemas.TrainingControlRoomRead(generated_at=utcnow(), queues=queues, source_errors=source_errors)
