from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..audit import models as audit_models
from ..audit import services as audit_services
from ..doc_control import models as doc_control_models
from ..notifications import service as notification_service
from ..quality import models as quality_models
from ..realtime import models as realtime_models
from . import compliance
from . import models as legacy_models
from . import operating_models as models
from . import operating_schemas as schemas
from .permissions import tenant_id_for


UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(db: Session, *, actor: account_models.User, entity_type: str, entity_id: str, action: str, after: dict | None = None, critical: bool = False) -> None:
    audit_services.log_event(
        db,
        amo_id=tenant_id_for(actor),
        actor_user_id=str(actor.id),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        after=after,
        metadata={"module": "training", "readiness_audit_control": True},
        critical=critical,
    )


def _scoped(db: Session, model: type, record_id: str, amo_id: str, label: str):
    row = db.query(model).filter(model.id == record_id, model.amo_id == amo_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label} was not found in this tenant.")
    return row


def source_health(db: Session, *, actor: account_models.User) -> schemas.SourceHealthRead:
    amo_id = tenant_id_for(actor)
    checked = _now()
    checks: list[tuple[str, Any, Any, str]] = [
        ("workforce", account_models.User, account_models.User.amo_id, "/maintenance/people"),
        ("training", legacy_models.TrainingCourse, legacy_models.TrainingCourse.amo_id, "/training/competence/settings"),
        ("qms", quality_models.QMSAudit, quality_models.QMSAudit.amo_id, "/quality/audits"),
        ("dms", doc_control_models.ControlledDocument, doc_control_models.ControlledDocument.tenant_id, "/documents"),
    ]
    items: list[schemas.SourceHealthItem] = []
    for name, model, tenant_column, action_path in checks:
        try:
            count = int(db.query(func.count()).select_from(model).filter(tenant_column == amo_id).scalar() or 0)
            items.append(schemas.SourceHealthItem(
                source=name, status="HEALTHY", checked_at=checked, freshness_at=checked,
                detail=f"Source reachable; {count} tenant records visible.", retryable=False, action_path=action_path,
            ))
        except Exception as exc:
            db.rollback()
            items.append(schemas.SourceHealthItem(
                source=name, status="UNAVAILABLE", checked_at=checked,
                detail=f"{type(exc).__name__}: source query failed. Counts depending on this source are Unknown.",
                retryable=True, action_path=action_path,
            ))
    unavailable = sum(item.status == "UNAVAILABLE" for item in items)
    overall = "UNAVAILABLE" if unavailable == len(items) else "DEGRADED" if unavailable else "HEALTHY"
    return schemas.SourceHealthRead(generated_at=checked, overall_status=overall, sources=items)


def _requirement_indexes(requirements: list[legacy_models.TrainingRequirement]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ALL": set(), "USER": defaultdict(set), "DEPARTMENT": defaultdict(set), "JOB_ROLE": defaultdict(set), "source": defaultdict(list),
    }
    for requirement in requirements:
        scope = str(getattr(requirement.scope, "value", requirement.scope)).upper()
        course_id = str(requirement.course_id)
        if scope == "ALL":
            result["ALL"].add(course_id)
        elif scope == "USER" and requirement.user_id:
            result["USER"][str(requirement.user_id)].add(course_id)
        elif scope == "DEPARTMENT" and requirement.department_code:
            result["DEPARTMENT"][requirement.department_code.strip().upper()].add(course_id)
        elif scope == "JOB_ROLE" and requirement.job_role:
            result["JOB_ROLE"][requirement.job_role.strip().lower()].add(course_id)
        result["source"][course_id].append({
            "requirement_id": str(requirement.id), "scope": scope,
            "manual_reference": requirement.manual_reference, "source_type": requirement.source_type, "source_id": requirement.source_id,
        })
    return result


def people_compliance_page(
    db: Session, *, actor: account_models.User, search: str | None, active: bool | None, limit: int, offset: int,
) -> schemas.PersonCompliancePage:
    amo_id = tenant_id_for(actor)
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_system_account.is_(False),
    )
    if active is not None:
        query = query.filter(account_models.User.is_active.is_(active))
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(or_(
            account_models.User.full_name.ilike(token), account_models.User.staff_code.ilike(token),
            account_models.User.email.ilike(token), account_models.User.position_title.ilike(token),
        ))
    total = int(query.count())
    summary_people = query.with_entities(
        account_models.User.id,
        account_models.User.position_title,
        account_models.User.department_id,
    ).all()
    users = query.order_by(account_models.User.full_name, account_models.User.id).offset(offset).limit(limit).all()
    all_user_ids = [str(row[0]) for row in summary_people]
    department_ids = {str(row[2]) for row in summary_people if row[2]}
    departments = db.query(account_models.Department).filter(
        account_models.Department.amo_id == amo_id,
        account_models.Department.id.in_(department_ids or {""}),
    ).all()
    department_by_id = {str(row.id): str(row.code or "").upper() for row in departments}
    today = date.today()
    requirements = db.query(legacy_models.TrainingRequirement).filter(
        legacy_models.TrainingRequirement.amo_id == amo_id,
        legacy_models.TrainingRequirement.is_active.is_(True),
        or_(legacy_models.TrainingRequirement.effective_from.is_(None), legacy_models.TrainingRequirement.effective_from <= today),
        or_(legacy_models.TrainingRequirement.effective_to.is_(None), legacy_models.TrainingRequirement.effective_to >= today),
    ).all()
    requirement_index = _requirement_indexes(requirements)
    course_ids = {str(row.course_id) for row in requirements}
    courses = db.query(legacy_models.TrainingCourse).filter(
        legacy_models.TrainingCourse.amo_id == amo_id,
        legacy_models.TrainingCourse.id.in_(course_ids or {""}),
    ).all()
    course_by_id = {str(course.id): course for course in courses}
    records = db.query(legacy_models.TrainingRecord).filter(
        legacy_models.TrainingRecord.amo_id == amo_id,
        legacy_models.TrainingRecord.user_id.in_(all_user_ids or {""}),
        legacy_models.TrainingRecord.course_id.in_(course_ids or {""}),
        or_(legacy_models.TrainingRecord.record_status.is_(None), legacy_models.TrainingRecord.record_status == "ACTIVE"),
    ).order_by(legacy_models.TrainingRecord.completion_date.desc()).all()
    latest: dict[tuple[str, str], legacy_models.TrainingRecord] = {}
    for record in records:
        latest.setdefault((str(record.user_id), str(record.course_id)), record)

    rows: list[schemas.PersonComplianceRow] = []
    def obligation_counts(user_id: str, position_title: str | None, department_id: str | None) -> tuple[int, int, int]:
        department_code = department_by_id.get(str(department_id or ""), "")
        position = str(position_title or "").lower()
        required = set(requirement_index["ALL"])
        required.update(requirement_index["USER"].get(user_id, set()))
        required.update(requirement_index["DEPARTMENT"].get(department_code, set()))
        required.update(requirement_index["JOB_ROLE"].get(position, set()))
        overdue = due_soon = never = 0
        for course_id in required:
            course = course_by_id.get(course_id)
            if course is None:
                continue
            record = latest.get((user_id, course_id))
            if record is None:
                never += 1
                continue
            due = record.valid_until
            if due is None and course.frequency_months:
                due = compliance.add_months(record.completion_date, int(course.frequency_months))
            if due is not None and due < today:
                overdue += 1
            elif due is not None and (due - today).days <= int(course.planning_lead_days or 45):
                due_soon += 1
        return overdue, due_soon, never

    tenant_counts = {"overdue": 0, "due_soon": 0, "never_completed": 0}
    for user_id, position_title, department_id in summary_people:
        overdue, due_soon, never = obligation_counts(str(user_id), position_title, str(department_id) if department_id else None)
        tenant_counts["overdue"] += overdue
        tenant_counts["due_soon"] += due_soon
        tenant_counts["never_completed"] += never
    for user in users:
        user_id = str(user.id)
        department_code = department_by_id.get(str(user.department_id or ""), "")
        position = str(user.position_title or "").lower()
        required = set(requirement_index["ALL"])
        required.update(requirement_index["USER"].get(user_id, set()))
        required.update(requirement_index["DEPARTMENT"].get(department_code, set()))
        required.update(requirement_index["JOB_ROLE"].get(position, set()))
        overdue = due_soon = never = 0
        due_dates: list[date] = []
        provenance: list[dict[str, Any]] = []
        for course_id in required:
            course = course_by_id.get(course_id)
            if course is None:
                continue
            record = latest.get((user_id, course_id))
            due: date | None = None
            if record is None:
                never += 1
            else:
                due = record.valid_until
                if due is None and course.frequency_months:
                    due = compliance.add_months(record.completion_date, int(course.frequency_months))
                if due is not None:
                    due_dates.append(due)
                    if due < today:
                        overdue += 1
                    elif (due - today).days <= int(course.planning_lead_days or 45):
                        due_soon += 1
            provenance.append({
                "course_id": course_id, "course_code": course.course_id, "course_name": course.course_name,
                "record_id": str(record.id) if record else None, "completion_date": str(record.completion_date) if record else None,
                "expiry_date": str(due) if due else None, "requirements": requirement_index["source"].get(course_id, []),
            })
        if overdue:
            status, action = "OVERDUE", "Resolve overdue training"
        elif never:
            status, action = "INCOMPLETE", "Schedule never-completed training"
        elif due_soon:
            status, action = "DUE_SOON", "Add to the next training batch"
        else:
            status, action = "CURRENT", "No action required"
        rows.append(schemas.PersonComplianceRow(
            id=user_id, full_name=user.full_name, staff_code=user.staff_code, email=user.email,
            position_title=user.position_title, department=department_code or None, active=bool(user.is_active),
            outstanding=overdue + due_soon + never, overdue=overdue, due_soon=due_soon, never_completed=never,
            next_due=min(due_dates) if due_dates else None, next_action=action, status=status,
            provenance={"calculated_at": _now().isoformat(), "obligations": provenance},
        ))
    return schemas.PersonCompliancePage(
        items=rows, total=total, limit=limit, offset=offset, has_more=offset + len(rows) < total,
        filtered_totals={**tenant_counts, "people": total},
    )


def canonical_references(db: Session, *, actor: account_models.User, source: str, search: str | None, limit: int) -> list[dict[str, Any]]:
    amo_id = tenant_id_for(actor)
    token = f"%{(search or '').strip()}%"
    source = source.upper()
    if source == "PEOPLE":
        query = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_system_account.is_(False))
        if search:
            query = query.filter(or_(account_models.User.full_name.ilike(token), account_models.User.staff_code.ilike(token), account_models.User.email.ilike(token)))
        return [{"id": str(row.id), "code": row.staff_code, "label": row.full_name, "description": row.position_title, "source": source} for row in query.order_by(account_models.User.full_name).limit(limit)]
    if source == "COURSES":
        query = db.query(legacy_models.TrainingCourse).filter(legacy_models.TrainingCourse.amo_id == amo_id)
        if search:
            query = query.filter(or_(legacy_models.TrainingCourse.course_id.ilike(token), legacy_models.TrainingCourse.course_name.ilike(token)))
        return [{"id": str(row.id), "code": row.course_id, "label": row.course_name, "description": str(getattr(row.category, "value", row.category)), "source": source} for row in query.order_by(legacy_models.TrainingCourse.course_id).limit(limit)]
    if source in {"PROVIDERS", "LOCATIONS", "INSTRUCTORS"}:
        resource_type = {"PROVIDERS": "PROVIDER", "LOCATIONS": "LOCATION", "INSTRUCTORS": "INSTRUCTOR"}[source]
        query = db.query(models.TrainingReferenceResource).filter(models.TrainingReferenceResource.amo_id == amo_id, models.TrainingReferenceResource.resource_type == resource_type)
        if search:
            query = query.filter(or_(models.TrainingReferenceResource.code.ilike(token), models.TrainingReferenceResource.name.ilike(token)))
        return [{"id": str(row.id), "code": row.code, "label": row.name, "description": row.contact_name, "source": source} for row in query.order_by(models.TrainingReferenceResource.name).limit(limit)]
    if source == "AUTHORIZATION_TYPES":
        query = db.query(account_models.AuthorisationType).filter(account_models.AuthorisationType.amo_id == amo_id)
        if search:
            query = query.filter(or_(account_models.AuthorisationType.code.ilike(token), account_models.AuthorisationType.name.ilike(token)))
        return [{"id": str(row.id), "code": row.code, "label": row.name, "description": None, "source": source} for row in query.order_by(account_models.AuthorisationType.code).limit(limit)]
    if source == "DMS":
        query = db.query(doc_control_models.ControlledDocument).filter(doc_control_models.ControlledDocument.tenant_id == amo_id)
        if search:
            query = query.filter(or_(doc_control_models.ControlledDocument.doc_id.ilike(token), doc_control_models.ControlledDocument.title.ilike(token)))
        return [{"id": str(row.id), "code": row.doc_id, "label": row.title, "description": f"Issue {row.issue_no}, Rev {row.revision_no} · {row.status}", "source": source} for row in query.order_by(doc_control_models.ControlledDocument.doc_id).limit(limit)]
    if source == "QMS":
        query = db.query(quality_models.QMSAudit).filter(quality_models.QMSAudit.amo_id == amo_id, quality_models.QMSAudit.deleted_at.is_(None))
        if search:
            query = query.filter(or_(quality_models.QMSAudit.audit_ref.ilike(token), quality_models.QMSAudit.title.ilike(token)))
        return [{"id": str(row.id), "code": row.audit_ref, "label": row.title, "description": str(getattr(row.status, "value", row.status)), "source": source} for row in query.order_by(quality_models.QMSAudit.created_at.desc()).limit(limit)]
    raise HTTPException(status_code=422, detail="Unsupported canonical reference source.")


def _configuration_snapshot(db: Session, amo_id: str) -> dict[str, Any]:
    def json_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if hasattr(value, "value"):
            return value.value
        return value

    def row_payload(row: Any, *, omit: set[str]) -> dict[str, Any]:
        return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns if column.name not in omit}

    settings = db.query(models.TrainingOperatingSettings).filter(models.TrainingOperatingSettings.amo_id == amo_id).first()
    return {
        "settings": row_payload(settings, omit={"id", "amo_id"}) if settings else {},
        "resources": [row_payload(row, omit={"amo_id"}) for row in db.query(models.TrainingReferenceResource).filter(models.TrainingReferenceResource.amo_id == amo_id).all()],
        "forms": [row_payload(row, omit={"amo_id"}) for row in db.query(models.TrainingControlledFormTemplate).filter(models.TrainingControlledFormTemplate.amo_id == amo_id).all()],
        "exported_at": _now().isoformat(), "schema_version": 1,
    }


def create_setup_version(db: Session, *, actor: account_models.User, payload: schemas.SetupVersionCreate) -> models.TrainingSetupVersion:
    amo_id = tenant_id_for(actor)
    version_no = int(db.query(func.max(models.TrainingSetupVersion.version_no)).filter(models.TrainingSetupVersion.amo_id == amo_id).scalar() or 0) + 1
    snapshot = payload.snapshot or _configuration_snapshot(db, amo_id)
    row = models.TrainingSetupVersion(
        amo_id=amo_id, version_no=version_no, source_mode=payload.source_mode, title=payload.title,
        change_summary=payload.change_summary, snapshot=snapshot, validation_result={"status": "NOT_RUN", "blockers": []},
        created_by_user_id=str(actor.id),
    )
    db.add(row); db.flush()
    _audit(db, actor=actor, entity_type="training.setup_version", entity_id=str(row.id), action="DRAFT_CREATED", after={"version_no": version_no, "source_mode": row.source_mode})
    return row


def validate_setup_version(db: Session, *, actor: account_models.User, row: models.TrainingSetupVersion) -> dict[str, Any]:
    amo_id = tenant_id_for(actor)
    checks = {
        "settings": db.query(models.TrainingOperatingSettings.id).filter(models.TrainingOperatingSettings.amo_id == amo_id).first() is not None,
        "courses": int(db.query(func.count(legacy_models.TrainingCourse.id)).filter(legacy_models.TrainingCourse.amo_id == amo_id, legacy_models.TrainingCourse.is_active.is_(True)).scalar() or 0) > 0,
        "requirements": int(db.query(func.count(legacy_models.TrainingRequirement.id)).filter(legacy_models.TrainingRequirement.amo_id == amo_id, legacy_models.TrainingRequirement.is_active.is_(True)).scalar() or 0) > 0,
        "controlled_forms": int(db.query(func.count(models.TrainingControlledFormTemplate.id)).filter(models.TrainingControlledFormTemplate.amo_id == amo_id, models.TrainingControlledFormTemplate.status == "ACTIVE").scalar() or 0) > 0,
        "providers": int(db.query(func.count(models.TrainingReferenceResource.id)).filter(models.TrainingReferenceResource.amo_id == amo_id, models.TrainingReferenceResource.resource_type == "PROVIDER", models.TrainingReferenceResource.active.is_(True)).scalar() or 0) > 0,
    }
    blockers = [key for key, passed in checks.items() if not passed]
    result = {"status": "BLOCKED" if blockers else "READY", "checks": checks, "blockers": blockers, "validated_at": _now().isoformat()}
    row.validation_result = result
    db.flush()
    return result


def transition_setup_version(db: Session, *, actor: account_models.User, row: models.TrainingSetupVersion, payload: schemas.SetupVersionTransition) -> models.TrainingSetupVersion:
    target = payload.target
    allowed = {"DRAFT": {"IN_REVIEW"}, "IN_REVIEW": {"ACTIVE", "DRAFT"}, "ACTIVE": {"ROLLED_BACK"}}
    if target not in allowed.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Setup version cannot move from {row.status} to {target}.")
    if target == "IN_REVIEW":
        validate_setup_version(db, actor=actor, row=row)
        row.reviewed_by_user_id = str(actor.id)
    elif target == "ACTIVE":
        if str(row.created_by_user_id) == str(actor.id):
            raise HTTPException(status_code=409, detail="Segregation of duties requires a different user to activate this setup version.")
        result = validate_setup_version(db, actor=actor, row=row)
        if result["blockers"]:
            raise HTTPException(status_code=409, detail={"message": "Setup has blocking readiness failures.", **result})
        prior = db.query(models.TrainingSetupVersion).filter(models.TrainingSetupVersion.amo_id == row.amo_id, models.TrainingSetupVersion.status == "ACTIVE", models.TrainingSetupVersion.id != row.id).first()
        if prior:
            prior.status = "SUPERSEDED"
            row.supersedes_version_id = str(prior.id)
        row.activated_by_user_id = str(actor.id)
        row.effective_from = payload.effective_from or _now()
        settings = db.query(models.TrainingOperatingSettings).filter(models.TrainingOperatingSettings.amo_id == row.amo_id).first()
        if settings:
            settings.setup_status = "ACTIVE"
            settings.updated_by_user_id = str(actor.id)
    row.status = target
    db.flush()
    _audit(db, actor=actor, entity_type="training.setup_version", entity_id=str(row.id), action=target, after={"reason": payload.reason, "version_no": row.version_no}, critical=target == "ACTIVE")
    return row


def create_change_preview(db: Session, *, actor: account_models.User, payload: schemas.ChangePreviewCreate) -> models.TrainingChangeRequest:
    amo_id = tenant_id_for(actor)
    affected_ids = list(dict.fromkeys(str(value) for value in payload.requested_payload.get("ids", []) if value))
    impact = {
        "affected_count": len(affected_ids) or (1 if payload.object_id else 0), "affected_ids": affected_ids[:100],
        "operation": payload.operation, "requires_independent_review": payload.object_type in {"REQUIREMENT", "CERTIFICATE", "AUTHORIZATION"},
        "warnings": ["Preview must be accepted before the mutation is applied."],
    }
    row = models.TrainingChangeRequest(
        amo_id=amo_id, object_type=payload.object_type, object_id=payload.object_id, operation=payload.operation,
        requested_payload=payload.requested_payload, impact_summary=impact,
        validation_result={"status": "VALID", "errors": []}, requested_by_user_id=str(actor.id),
    )
    db.add(row); db.flush()
    _audit(db, actor=actor, entity_type="training.change_request", entity_id=str(row.id), action="PREVIEWED", after=impact)
    return row


def decide_change_request(db: Session, *, actor: account_models.User, row: models.TrainingChangeRequest, payload: schemas.ChangeDecision) -> models.TrainingChangeRequest:
    if row.status != "PREVIEW":
        raise HTTPException(status_code=409, detail="Only an unapplied preview can be decided.")
    if str(row.requested_by_user_id) == str(actor.id) and row.impact_summary.get("requires_independent_review"):
        raise HTTPException(status_code=409, detail="Segregation of duties requires a different user to accept this controlled change.")
    row.status = "ACCEPTED" if payload.decision == "ACCEPT" else "REJECTED"
    row.decided_by_user_id = str(actor.id); row.decision_reason = payload.reason
    if payload.decision == "ACCEPT":
        row.applied_at = _now()
    db.flush()
    _audit(db, actor=actor, entity_type="training.change_request", entity_id=str(row.id), action=row.status, after={"reason": payload.reason}, critical=payload.decision == "ACCEPT")
    return row


def _workflow_steps(db: Session, amo_id: str, workflow_id: str) -> list[models.TrainingWorkflowStep]:
    return db.query(models.TrainingWorkflowStep).filter(models.TrainingWorkflowStep.amo_id == amo_id, models.TrainingWorkflowStep.workflow_instance_id == workflow_id).order_by(models.TrainingWorkflowStep.sequence_no).all()


def workflow_read(db: Session, row: models.TrainingWorkflowInstance) -> schemas.WorkflowInstanceRead:
    payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    payload["steps"] = _workflow_steps(db, str(row.amo_id), str(row.id))
    return schemas.WorkflowInstanceRead.model_validate(payload)


def create_workflow(db: Session, *, actor: account_models.User, payload: schemas.WorkflowInstanceCreate) -> models.TrainingWorkflowInstance:
    amo_id = tenant_id_for(actor)
    existing = db.query(models.TrainingWorkflowInstance).filter(
        models.TrainingWorkflowInstance.amo_id == amo_id, models.TrainingWorkflowInstance.workflow_type == payload.workflow_type,
        models.TrainingWorkflowInstance.idempotency_key == payload.idempotency_key,
    ).first()
    if existing:
        return existing
    form = None
    if payload.form_template_id:
        form = _scoped(db, models.TrainingControlledFormTemplate, payload.form_template_id, amo_id, "Controlled form")
        if form.status != "ACTIVE":
            raise HTTPException(status_code=409, detail="The selected controlled form revision is not active.")
    for field, model, label in (("subject_user_id", account_models.User, "Person"), ("owner_user_id", account_models.User, "Owner"), ("reviewer_user_id", account_models.User, "Reviewer")):
        value = getattr(payload, field)
        if value:
            _scoped(db, model, value, amo_id, label)
    row = models.TrainingWorkflowInstance(
        amo_id=amo_id, workflow_type=payload.workflow_type, form_template_id=str(form.id) if form else None,
        form_revision_no=form.revision_no if form else None, subject_user_id=payload.subject_user_id,
        owner_user_id=payload.owner_user_id or str(actor.id), reviewer_user_id=payload.reviewer_user_id,
        event_id=payload.event_id, course_id=payload.course_id, authorization_case_id=payload.authorization_case_id,
        title=payload.title, due_at=payload.due_at, data_json=payload.data_json, idempotency_key=payload.idempotency_key,
        provenance={"form_code": form.code if form else None, "form_revision": form.revision_no if form else None, "created_via": "FRONTEND_API"},
        created_by_user_id=str(actor.id),
    )
    db.add(row); db.flush()
    steps = payload.steps or [schemas.WorkflowStepInput(step_key="complete", label="Complete controlled form", assigned_user_id=row.owner_user_id)]
    db.add_all([models.TrainingWorkflowStep(
        amo_id=amo_id, workflow_instance_id=str(row.id), step_key=step.step_key, label=step.label,
        sequence_no=step.sequence_no, assigned_user_id=step.assigned_user_id or row.owner_user_id,
    ) for step in steps])
    db.flush()
    _audit(db, actor=actor, entity_type="training.workflow", entity_id=str(row.id), action="CREATED", after={"workflow_type": row.workflow_type, "subject_user_id": row.subject_user_id})
    return row


def complete_workflow_step(db: Session, *, actor: account_models.User, workflow: models.TrainingWorkflowInstance, step: models.TrainingWorkflowStep, payload: schemas.WorkflowStepComplete) -> models.TrainingWorkflowStep:
    if workflow.status in {"APPROVED", "COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="This workflow is immutable in its current state.")
    if step.assigned_user_id and str(step.assigned_user_id) != str(actor.id) and not getattr(actor, "is_amo_admin", False):
        raise HTTPException(status_code=403, detail="This workflow step is assigned to another user.")
    step.response_json = payload.response_json
    step.signature_json = {"meaning": payload.signature or "Completed by authenticated user", "user_id": str(actor.id), "signed_at": _now().isoformat()}
    step.status = "COMPLETED"; step.completed_by_user_id = str(actor.id); step.completed_at = _now()
    db.flush()
    _audit(db, actor=actor, entity_type="training.workflow_step", entity_id=str(step.id), action="COMPLETED", after={"workflow_id": str(workflow.id), "step_key": step.step_key})
    return step


def transition_workflow(db: Session, *, actor: account_models.User, row: models.TrainingWorkflowInstance, payload: schemas.WorkflowTransition) -> models.TrainingWorkflowInstance:
    allowed = {
        "DRAFT": {"SUBMITTED", "CANCELLED"}, "RETURNED": {"SUBMITTED", "CANCELLED"},
        "SUBMITTED": {"RETURNED", "APPROVED", "CANCELLED"}, "APPROVED": {"COMPLETED"},
    }
    if payload.target not in allowed.get(row.status, set()):
        raise HTTPException(status_code=409, detail=f"Workflow cannot move from {row.status} to {payload.target}.")
    steps = _workflow_steps(db, str(row.amo_id), str(row.id))
    if payload.target in {"SUBMITTED", "APPROVED", "COMPLETED"}:
        incomplete = [step.step_key for step in steps if step.status != "COMPLETED"]
        if incomplete:
            row.validation_result = {"status": "BLOCKED", "incomplete_steps": incomplete}
            raise HTTPException(status_code=409, detail={"message": "Required controlled-form steps are incomplete.", "incomplete_steps": incomplete})
    if payload.target == "APPROVED" and str(row.created_by_user_id) == str(actor.id):
        raise HTTPException(status_code=409, detail="Segregation of duties requires a different user to approve this workflow.")
    if payload.target in {"RETURNED", "APPROVED"} and row.reviewer_user_id and str(row.reviewer_user_id) != str(actor.id):
        raise HTTPException(status_code=403, detail="Only the assigned reviewer may decide this workflow.")
    row.status = payload.target; row.revision_no = int(row.revision_no or 0) + 1
    row.validation_result = {"status": "VALID", "validated_at": _now().isoformat()}
    if payload.target == "SUBMITTED": row.submitted_at = _now()
    if payload.target == "COMPLETED": row.completed_at = _now()
    db.flush()
    _audit(db, actor=actor, entity_type="training.workflow", entity_id=str(row.id), action=payload.target, after={"comment": payload.comment, "revision_no": row.revision_no}, critical=payload.target in {"APPROVED", "COMPLETED"})
    return row


def send_session_invitations(db: Session, *, actor: account_models.User, event_id: str, payload: schemas.InvitationCreate) -> list[models.TrainingSessionInvitation]:
    amo_id = tenant_id_for(actor)
    event = _scoped(db, legacy_models.TrainingEvent, event_id, amo_id, "Training session")
    participant_ids = {str(user_id) for (user_id,) in db.query(legacy_models.TrainingEventParticipant.user_id).filter(legacy_models.TrainingEventParticipant.amo_id == amo_id, legacy_models.TrainingEventParticipant.event_id == event_id).all()}
    requested = list(dict.fromkeys(payload.participant_user_ids))
    invalid = [user_id for user_id in requested if user_id not in participant_ids]
    if invalid:
        raise HTTPException(status_code=422, detail={"message": "Invitations are limited to the canonical session roster.", "invalid_user_ids": invalid})
    users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.id.in_(requested)).all()
    user_by_id = {str(user.id): user for user in users}
    rows: list[models.TrainingSessionInvitation] = []
    action_url = f"/training/my?session={event.id}"
    for user_id in requested:
        user = user_by_id.get(user_id)
        if not user:
            continue
        for channel in payload.channels:
            row = db.query(models.TrainingSessionInvitation).filter(
                models.TrainingSessionInvitation.amo_id == amo_id, models.TrainingSessionInvitation.event_id == event_id,
                models.TrainingSessionInvitation.user_id == user_id, models.TrainingSessionInvitation.channel == channel,
            ).first()
            if row is None:
                row = models.TrainingSessionInvitation(amo_id=amo_id, event_id=event_id, user_id=user_id, channel=channel, created_by_user_id=str(actor.id))
                db.add(row); db.flush()
            row.attempt_count = int(row.attempt_count or 0) + 1; row.last_error = None; row.delivery_status = "QUEUED"
            if channel == "IN_APP":
                db.add(realtime_models.PortalNotification(
                    amo_id=amo_id, user_id=user_id, kind="TRAINING_SESSION_INVITATION", title=f"Training invitation: {event.title}",
                    body=payload.message or f"You are invited to {event.title} on {event.starts_on}.", entity_type="training_event",
                    entity_id=str(event.id), action_url=action_url, dedupe_key=f"training-invite:{event.id}:{user_id}:{row.attempt_count}",
                    metadata_json={"event_id": str(event.id), "starts_on": str(event.starts_on)},
                ))
                row.delivery_status = "DELIVERED"; row.sent_at = _now(); row.delivered_at = _now()
            else:
                log = notification_service.send_email(
                    "training-session-invitation", user.email, f"Training invitation: {event.title}",
                    {"name": user.full_name, "event_title": event.title, "starts_on": str(event.starts_on), "action_url": action_url, "message": payload.message},
                    f"training-invite:{row.id}:{row.attempt_count}", amo_id=amo_id, db=db, recipient_user_id=user_id,
                    audit_context={"purpose": "training-session-invitation", "event_id": str(event.id), "user_id": user_id},
                )
                row.email_log_id = str(log.id); row.sent_at = getattr(log, "sent_at", None)
                row.delivery_status = str(getattr(getattr(log, "status", None), "value", getattr(log, "delivery_status", "QUEUED")))
                row.last_error = getattr(log, "error", None)
            rows.append(row)
    db.flush()
    _audit(db, actor=actor, entity_type="training.session_invitation", entity_id=event_id, action="SENT", after={"recipient_count": len(requested), "channels": payload.channels})
    return rows


def invitation_rsvp(db: Session, *, actor: account_models.User, invitation: models.TrainingSessionInvitation, response: str) -> models.TrainingSessionInvitation:
    if str(invitation.user_id) != str(actor.id):
        raise HTTPException(status_code=403, detail="You may respond only to your own invitation.")
    invitation.rsvp_status = response; invitation.responded_at = _now(); invitation.read_at = invitation.read_at or _now()
    db.flush()
    _audit(db, actor=actor, entity_type="training.session_invitation", entity_id=str(invitation.id), action="RSVP", after={"response": response})
    return invitation


def create_report_job(db: Session, *, actor: account_models.User, payload: schemas.ReportJobCreate) -> models.TrainingReportJob:
    amo_id = tenant_id_for(actor)
    definition = db.query(models.TrainingReportDefinition).filter(models.TrainingReportDefinition.amo_id == amo_id, models.TrainingReportDefinition.code == payload.report_code, models.TrainingReportDefinition.active.is_(True)).first()
    builtin = {"PEOPLE_COMPLIANCE", "TRAINING_PLAN", "ATTENDANCE", "ASSESSMENTS", "AUTHORIZATIONS", "CERTIFICATES", "BUDGET", "AUDIT"}
    if definition is None and payload.report_code not in builtin:
        raise HTTPException(status_code=404, detail="Report definition was not found in this tenant.")
    if definition and payload.output_format not in (definition.allowed_formats or []):
        raise HTTPException(status_code=422, detail="The requested output format is not enabled for this report.")
    dataset = str(definition.dataset if definition else payload.report_code).upper()
    total_map = {
        "PEOPLE_COMPLIANCE": account_models.User, "TRAINING_PLAN": models.TrainingPlanParticipant,
        "ATTENDANCE": models.TrainingAttendanceEntry, "ASSESSMENTS": models.TrainingAssessmentInstance,
        "AUTHORIZATIONS": models.TrainingAuthorizationCase, "CERTIFICATES": legacy_models.TrainingCertificateIssue,
        "BUDGET": models.TrainingBudgetLine, "AUDIT": audit_models.AuditEvent,
    }
    model = total_map.get(dataset)
    total = int(db.query(func.count(model.id)).filter(model.amo_id == amo_id).scalar() or 0) if model else 0
    scope = {"tenant_id": amo_id, "report_code": payload.report_code, "dataset": dataset, "filters": payload.filters_json, "record_count": total, "source_cutoff_at": _now().isoformat(), "complete_server_population": True}
    row = models.TrainingReportJob(
        amo_id=amo_id, report_definition_id=str(definition.id) if definition else None, report_code=payload.report_code,
        output_format=payload.output_format, filters_json=payload.filters_json, scope_manifest=scope,
        requested_by_user_id=str(actor.id), expires_at=_now() + timedelta(days=int(definition.retention_days if definition else 365)),
    )
    db.add(row); db.flush()
    _audit(db, actor=actor, entity_type="training.report_job", entity_id=str(row.id), action="QUEUED", after=scope)
    return row


def upsert_saved_view(db: Session, *, actor: account_models.User, payload: schemas.SavedViewCreate) -> models.TrainingSavedView:
    amo_id = tenant_id_for(actor)
    row = db.query(models.TrainingSavedView).filter(models.TrainingSavedView.amo_id == amo_id, models.TrainingSavedView.user_id == str(actor.id), models.TrainingSavedView.workspace == payload.workspace, models.TrainingSavedView.name == payload.name).first()
    if row is None:
        row = models.TrainingSavedView(amo_id=amo_id, user_id=str(actor.id), workspace=payload.workspace, name=payload.name)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    if payload.is_default:
        db.query(models.TrainingSavedView).filter(models.TrainingSavedView.amo_id == amo_id, models.TrainingSavedView.user_id == str(actor.id), models.TrainingSavedView.workspace == payload.workspace, models.TrainingSavedView.id != row.id).update({"is_default": False}, synchronize_session=False)
    db.flush()
    return row
