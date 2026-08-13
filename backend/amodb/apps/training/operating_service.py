from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..audit import services as audit_services
from ..quality import models as quality_models
from ..tasks import services as task_services
from . import compliance
from . import models as legacy_models
from . import operating_models as models
from . import operating_schemas as schemas
from . import operating_rules as rules
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


def update_settings(
    db: Session,
    *,
    actor: account_models.User,
    payload: schemas.TrainingOperatingSettingsUpdate,
) -> models.TrainingOperatingSettings:
    amo_id = _amo_id(actor)
    row = get_or_create_settings(db, amo_id=amo_id)
    before = {key: getattr(row, key) for key in payload.model_fields}
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by_user_id = str(actor.id)
    db.flush()
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.settings", entity_id=str(row.id), action="UPDATED", before=before, after=payload.model_dump(mode="json"))
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
    participant_ids = list(dict.fromkeys(item.participant_ids))
    if participant_ids:
        valid_ids = {
            str(value)
            for (value,) in db.query(account_models.User.id).filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id.in_(participant_ids),
                account_models.User.is_active.is_(True),
                account_models.User.is_system_account.is_(False),
            )
        }
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
        db.add(models.TrainingPlanParticipant(amo_id=amo_id, plan_item_id=row.id, user_id=user_id))
    return row


def _demand_items(db: Session, *, amo_id: str, year: int) -> list[schemas.TrainingPlanItemCreate]:
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    buckets: dict[str, dict[str, Any]] = {}
    for user in users:
        evaluation = compliance.evaluate_user_training_policy(db, user, required_only=True, today=date(year, 1, 1))
        for item in evaluation.mandatory_items:
            due = getattr(item, "due_date", None)
            if due and due.year > year:
                continue
            course = db.query(legacy_models.TrainingCourse).filter(
                legacy_models.TrainingCourse.amo_id == amo_id,
                legacy_models.TrainingCourse.course_id == item.course_id,
            ).first()
            if not course:
                continue
            bucket = buckets.setdefault(str(course.id), {"course": course, "users": [], "due": []})
            bucket["users"].append(str(user.id))
            if due:
                bucket["due"].append(due)
    result: list[schemas.TrainingPlanItemCreate] = []
    for bucket in buckets.values():
        course = bucket["course"]
        earliest = min(bucket["due"]) if bucket["due"] else None
        month = earliest.month if earliest else 1
        result.append(schemas.TrainingPlanItemCreate(
            course_id=str(course.id),
            training_kind=_enum(course.kind) or "OTHER",
            provider=course.default_provider,
            participant_ids=bucket["users"],
            planned_month=month,
            duration_days=course.default_duration_days,
            justification="Generated from current mandatory training obligations and due dates.",
            source_type="REQUIREMENTS_MATRIX",
            manual_reference=course.regulatory_reference,
            priority="HIGH" if month <= 3 else "NORMAL",
        ))
    return result


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
            db.add(models.TrainingPlanParticipant(amo_id=amo_id, plan_item_id=clone.id, user_id=participant.user_id, status=participant.status, exclusion_reason=participant.exclusion_reason))
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
) -> tuple[models.TrainingAttendanceWindow, str]:
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
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.attendance_window", entity_id=str(row.id), action="OPENED", after={"event_id": event.id, "expires_at": row.expires_at.isoformat()})
    return row, code


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
    _audit(db, amo_id=amo_id, actor_user_id=str(actor.id), entity_type="training.attendance", entity_id=str(row.id), action="CORRECTED", before={"status": old}, after={"status": row.status, "reason": payload.reason}, critical=True)
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
    row = models.TrainingAssessmentTemplate(
        amo_id=amo_id, revision_no=int(max_revision) + 1, created_by_user_id=str(actor.id),
        **payload.model_dump(),
    )
    row.code = row.code.upper().strip()
    db.add(row)
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


def control_room(db: Session, *, actor: account_models.User) -> schemas.TrainingControlRoomRead:
    amo_id = _amo_id(actor)
    queues: list[schemas.ActionQueueItem] = []
    source_errors: list[str] = []

    def add(key: str, label: str, count: int, severity: str, reason: str, action: str, path: str) -> None:
        queues.append(schemas.ActionQueueItem(key=key, label=label, count=count, severity=severity, reason=reason, action_label=action, path=path))

    try:
        overdue = due_soon = never = 0
        users = db.query(account_models.User).filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).all()
        for user in users:
            policy = compliance.evaluate_user_training_policy(db, user, required_only=True)
            overdue += len(policy.overdue_items)
            due_soon += len(policy.due_soon_items)
            never += len(policy.not_done_items)
        add("overdue", "Overdue mandatory training", overdue, "CRITICAL", "Current mandatory obligations have passed their due date.", "Resolve overdue", "/training/competence/requirements")
        add("due_soon", "Training due soon", due_soon, "WARNING", "Training is inside its configurable planning lead window.", "Build a batch", "/training/competence/plan")
        add("never_completed", "Never completed", never, "CRITICAL", "Mandatory training has no valid completion record.", "Review people", "/training/competence/people")
    except Exception as exc:
        source_errors.append(f"training_compliance: {type(exc).__name__}")

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
    return schemas.TrainingControlRoomRead(generated_at=utcnow(), queues=queues, source_errors=source_errors)
