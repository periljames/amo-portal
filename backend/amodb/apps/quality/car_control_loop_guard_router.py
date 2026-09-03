from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from . import models
from .car_control_loop import compute_car_health
from .car_control_loop_models import QualityCARDeadlineChange
from .car_control_loop_router import (
    CloseControlLoop,
    ControlLoopInitialize,
    DeadlineChangeCreate,
    DeadlineChangeDecision,
    _add_event,
    _assert_milestone,
    _dependencies,
    _enum_value,
    _event_exists,
    _load_car,
    _load_profile,
    _milestones,
    _require_profile,
    _result,
    _utcnow,
    _close_control_loop as _close_control_loop_base,
    _initialize_control_loop as _initialize_control_loop_base,
)
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)
from .transitions import transition_car


router = APIRouter(prefix="/cars/{car_id}/control-loop", tags=["Quality CAR control loop governance"])

_RESOLVED_DEPENDENCY_STATUSES = {"RESOLVED", "MITIGATED", "ACCEPTED_RISK", "CANCELLED"}
_TERMINAL_MILESTONE_STATUSES = {"ACCEPTED", "COMPLETED", "WAIVED"}
_CAR_EVIDENCE_REF_MAX_LENGTH = 512


def _archive_sent_car_reminders_before_reseed(
    db: Session,
    *,
    car: models.CorrectiveActionRequest,
    approved_due_date: date,
) -> None:
    """Preserve sent/escalated reminder evidence without blocking a revised schedule."""

    historical = (
        db.query(models.QualityReminderMilestone)
        .filter(
            models.QualityReminderMilestone.amo_id == car.amo_id,
            models.QualityReminderMilestone.entity_type == "quality_car",
            models.QualityReminderMilestone.entity_id == str(car.id),
            or_(
                models.QualityReminderMilestone.sent_at.isnot(None),
                models.QualityReminderMilestone.escalated_at.isnot(None),
            ),
        )
        .all()
    )
    for reminder in historical:
        if reminder.due_date == approved_due_date or "@" in str(reminder.milestone_key or ""):
            continue
        due_token = reminder.due_date.isoformat() if reminder.due_date else "undated"
        suffix = f"@{due_token}:{str(reminder.id)[:8]}"
        base_key = str(reminder.milestone_key or "CAR_REMINDER")
        reminder.milestone_key = f"{base_key[: max(1, 64 - len(suffix))]}{suffix}"
    db.flush()


def _synchronize_authoritative_car_deadline(
    db: Session,
    *,
    car: models.CorrectiveActionRequest,
    approved_due_date: date,
) -> None:
    """Keep register, target and active reminder deadlines synchronized."""

    car.due_date = approved_due_date
    car.target_closure_date = approved_due_date

    # Historical sent/escalated reminders remain auditable under a distinct key
    # so the normal seeder can recreate the same reminder stages for the newly
    # approved due date. Obsolete unsent reminders are removed entirely.
    _archive_sent_car_reminders_before_reseed(
        db,
        car=car,
        approved_due_date=approved_due_date,
    )
    (
        db.query(models.QualityReminderMilestone)
        .filter(
            models.QualityReminderMilestone.amo_id == car.amo_id,
            models.QualityReminderMilestone.entity_type == "quality_car",
            models.QualityReminderMilestone.entity_id == str(car.id),
            models.QualityReminderMilestone.sent_at.is_(None),
            models.QualityReminderMilestone.escalated_at.is_(None),
        )
        .delete(synchronize_session=False)
    )

    from .router import _seed_car_reminders

    _seed_car_reminders(db, car)


def _prepare_initial_authoritative_deadline(
    db: Session,
    *,
    car: models.CorrectiveActionRequest,
    final_due_date: date,
) -> None:
    """Establish both legacy and staged deadline sources before initialization commits."""

    car.due_date = final_due_date
    car.target_closure_date = final_due_date
    from .router import _seed_car_reminders

    _seed_car_reminders(db, car)


def _validated_closure_evidence_ref(payload: CloseControlLoop, milestones: list[Any]) -> str:
    evidence_ref = (payload.evidence_ref or "").strip()
    if not evidence_ref:
        for key in ("EFFECTIVENESS_REVIEW", "EVIDENCE_COMPLETE"):
            evidence_ref = next(
                (
                    str(item.evidence_ref).strip()
                    for item in milestones
                    if item.milestone_key == key and item.evidence_ref
                ),
                "",
            )
            if evidence_ref:
                break
    if len(evidence_ref) > _CAR_EVIDENCE_REF_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                "Closure evidence reference exceeds the authoritative 512-character CAR evidence limit. "
                "Use a shorter canonical evidence reference before closing the CAR."
            ),
        )
    return evidence_ref


def _milestone_extension_ceiling(db: Session, *, amo_id: str, car_id: UUID, milestone_id: UUID) -> date | None:
    rows = _milestones(db, amo_id=amo_id, car_id=car_id)
    for index, row in enumerate(rows):
        if row.id != milestone_id:
            continue
        if index + 1 < len(rows):
            return rows[index + 1].current_due_date
        return None
    raise HTTPException(status_code=404, detail="CAR control milestone not found.")


def _validate_milestone_extension_order(
    db: Session,
    *,
    amo_id: str,
    car_id: UUID,
    milestone_id: UUID,
    requested_due_date: date,
    final_due_date: date,
) -> None:
    if requested_due_date > final_due_date:
        raise HTTPException(status_code=422, detail="A milestone deadline cannot extend beyond the current final CAR deadline.")
    ceiling = _milestone_extension_ceiling(db, amo_id=amo_id, car_id=car_id, milestone_id=milestone_id)
    if ceiling is not None and requested_due_date > ceiling:
        raise HTTPException(
            status_code=422,
            detail="A milestone deadline cannot move beyond the current deadline of the next lifecycle stage.",
        )


def _notify_control_owner(
    db: Session,
    *,
    ctx: TenantContext,
    car: models.CorrectiveActionRequest,
    recipient_user_id: str | None,
    message: str,
    severity: str,
) -> None:
    if not recipient_user_id:
        return
    db.add(
        models.QMSNotification(
            amo_id=ctx.amo_id,
            user_id=recipient_user_id,
            message=message,
            severity=severity,
            created_by_user_id=ctx.user_id,
            action_url=f"/maintenance/{ctx.amo_code}/quality/cars?control={car.id}",
            action_label="Open CAR control loop",
            entity_type="quality.car",
            entity_id=str(car.id),
        )
    )


@router.post("/initialize", status_code=status.HTTP_201_CREATED)
def initialize_control_loop_guarded(
    car_id: UUID,
    payload: ControlLoopInitialize,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    existing = _load_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)

    if existing is None and car.target_closure_date is None and car.due_date is None and payload.final_due_date is not None:
        opened_on = car.created_at.date() if car.created_at else date.today()
        if payload.final_due_date < opened_on:
            raise HTTPException(status_code=422, detail="The controlled final due date cannot precede the CAR creation date.")
        _prepare_initial_authoritative_deadline(
            db,
            car=car,
            final_due_date=payload.final_due_date,
        )

    return _initialize_control_loop_base(str(car_id), payload, ctx, db)


def _request_deadline_change_guarded(
    car_id: UUID,
    payload: DeadlineChangeCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)

    milestone = None
    previous_due = profile.current_due_date
    if payload.milestone_id:
        try:
            milestone_id = UUID(payload.milestone_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="milestone_id must be a valid UUID.") from exc
        milestone = _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=milestone_id, lock=True)
        previous_due = milestone.current_due_date
        _validate_milestone_extension_order(
            db,
            amo_id=ctx.amo_id,
            car_id=car_id,
            milestone_id=milestone.id,
            requested_due_date=payload.requested_due_date,
            final_due_date=profile.current_due_date,
        )

    if payload.requested_due_date <= previous_due:
        raise HTTPException(status_code=422, detail="A deadline extension must move the controlled due date later than its current value.")

    pending = db.query(QualityCARDeadlineChange.id).filter(
        QualityCARDeadlineChange.amo_id == ctx.amo_id,
        QualityCARDeadlineChange.car_id == car.id,
        QualityCARDeadlineChange.milestone_id == (milestone.id if milestone else None),
        QualityCARDeadlineChange.status == "PENDING",
    ).first()
    if pending:
        raise HTTPException(status_code=409, detail="A pending deadline change already exists for this controlled deadline.")

    row = QualityCARDeadlineChange(
        amo_id=ctx.amo_id,
        car_id=car.id,
        milestone_id=milestone.id if milestone else None,
        previous_due_date=previous_due,
        requested_due_date=payload.requested_due_date,
        reason=payload.reason.strip(),
        impact_statement=(payload.impact_statement or "").strip() or None,
        status="PENDING",
        requested_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(
        db,
        car=car,
        profile=profile,
        milestone=milestone,
        event_type="DEADLINE_CHANGE_REQUESTED",
        reason=row.reason,
        actor_user_id=ctx.user_id,
        severity="ACTION_REQUIRED",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


def _decide_deadline_change_guarded(
    car_id: UUID,
    change_id: UUID,
    payload: DeadlineChangeDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    row = db.query(QualityCARDeadlineChange).filter(
        QualityCARDeadlineChange.amo_id == ctx.amo_id,
        QualityCARDeadlineChange.car_id == car.id,
        QualityCARDeadlineChange.id == change_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Deadline change request not found.")
    if row.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only a pending deadline change may be decided.")

    milestone = None
    if row.milestone_id:
        milestone = _assert_milestone(db, amo_id=ctx.amo_id, car_id=car_id, milestone_id=row.milestone_id, lock=True)

    if payload.decision == "APPROVE":
        if milestone is not None:
            _validate_milestone_extension_order(
                db,
                amo_id=ctx.amo_id,
                car_id=car_id,
                milestone_id=milestone.id,
                requested_due_date=row.requested_due_date,
                final_due_date=profile.current_due_date,
            )
            milestone.current_due_date = row.requested_due_date
        else:
            if row.previous_due_date != profile.current_due_date:
                raise HTTPException(status_code=409, detail="The final CAR deadline changed after this request was created. Submit a new controlled deadline request.")
            profile.current_due_date = row.requested_due_date
            _synchronize_authoritative_car_deadline(
                db,
                car=car,
                approved_due_date=row.requested_due_date,
            )
        row.status = "APPROVED"
    else:
        row.status = "REJECTED"

    row.reviewed_by_user_id = ctx.user_id
    row.reviewed_at = _utcnow()
    row.review_note = payload.review_note.strip()
    profile.updated_by_user_id = ctx.user_id
    _add_event(
        db,
        car=car,
        profile=profile,
        milestone=milestone,
        event_type=f"DEADLINE_CHANGE_{row.status}",
        reason=row.review_note,
        actor_user_id=ctx.user_id,
        severity="WARNING" if row.status == "REJECTED" else "INFO",
    )
    db.commit()
    return _result(db, car=car, profile=profile)


def _close_control_loop_guarded(
    car_id: UUID,
    payload: CloseControlLoop,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    milestones = _milestones(db, amo_id=ctx.amo_id, car_id=car_id)
    _validated_closure_evidence_ref(payload, milestones)
    return _close_control_loop_base(str(car_id), payload, ctx, db)


@router.post("/evaluate")
def evaluate_control_loop_guarded(
    car_id: UUID,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    profile = _require_profile(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    today = date.today()
    created = 0
    milestones = _milestones(db, amo_id=ctx.amo_id, car_id=car_id)
    dependencies = _dependencies(db, amo_id=ctx.amo_id, car_id=car_id)

    for milestone in milestones:
        if milestone.milestone_key == "EFFECTIVENESS_REVIEW" and not profile.effectiveness_required:
            continue
        if milestone.status in _TERMINAL_MILESTONE_STATUSES:
            continue
        days = (milestone.current_due_date - today).days
        if days < -7:
            stage, severity, notification_severity = "CRITICAL_OVERDUE", "CRITICAL", "WARNING"
        elif days < 0:
            stage, severity, notification_severity = "OVERDUE", "WARNING", "WARNING"
        elif days <= 3:
            stage, severity, notification_severity = "FINAL_WARNING", "WARNING", "WARNING"
        elif days <= 7:
            stage, severity, notification_severity = "DUE_SOON", "ACTION_REQUIRED", "ACTION_REQUIRED"
        elif days <= 14:
            stage, severity, notification_severity = "REMINDER", "ACTION_REQUIRED", "ACTION_REQUIRED"
        else:
            continue

        event_key = f"milestone:{milestone.id}:{milestone.current_due_date.isoformat()}:{stage}"
        if _event_exists(db, amo_id=ctx.amo_id, car_id=car_id, event_key=event_key):
            continue
        descriptor = "overdue by" if days < 0 else "due in"
        count = abs(days) if days < 0 else days
        message = f"{milestone.title} is {descriptor} {count} day(s)."
        _add_event(
            db,
            car=car,
            profile=profile,
            milestone=milestone,
            event_type=f"MILESTONE_{stage}",
            reason=message,
            actor_user_id=ctx.user_id,
            severity=severity,
            event_key=event_key,
            system_generated=True,
        )
        _notify_control_owner(
            db,
            ctx=ctx,
            car=car,
            recipient_user_id=milestone.owner_user_id or profile.accountable_owner_user_id,
            message=message,
            severity=notification_severity,
        )
        created += 1

    for dependency in dependencies:
        if dependency.status in _RESOLVED_DEPENDENCY_STATUSES:
            continue

        due_date = dependency.due_date
        if due_date is not None:
            days = (due_date - today).days
            deadline_stage: tuple[str, str, str] | None
            if days < -7:
                deadline_stage = ("CRITICAL_OVERDUE", "CRITICAL", "WARNING")
            elif days < 0:
                deadline_stage = ("OVERDUE", "WARNING", "WARNING")
            elif days <= 3:
                deadline_stage = ("FINAL_WARNING", "WARNING", "WARNING")
            elif days <= 7:
                deadline_stage = ("DUE_SOON", "ACTION_REQUIRED", "ACTION_REQUIRED")
            elif days <= 14:
                deadline_stage = ("REMINDER", "ACTION_REQUIRED", "ACTION_REQUIRED")
            else:
                deadline_stage = None

            if deadline_stage is not None:
                stage, severity, notification_severity = deadline_stage
                event_key = f"dependency-deadline:{dependency.id}:{due_date.isoformat()}:{stage}"
                if not _event_exists(db, amo_id=ctx.amo_id, car_id=car_id, event_key=event_key):
                    descriptor = "overdue by" if days < 0 else "due in"
                    count = abs(days) if days < 0 else days
                    message = f"Dependency {dependency.title} is {descriptor} {count} day(s)."
                    _add_event(
                        db,
                        car=car,
                        profile=profile,
                        event_type=f"DEPENDENCY_{stage}",
                        reason=message,
                        actor_user_id=ctx.user_id,
                        severity=severity,
                        event_key=event_key,
                        system_generated=True,
                    )
                    _notify_control_owner(
                        db,
                        ctx=ctx,
                        car=car,
                        recipient_user_id=dependency.owner_user_id or profile.accountable_owner_user_id,
                        message=message,
                        severity=notification_severity,
                    )
                    created += 1

        if dependency.risk_level not in {"HIGH", "CRITICAL"} and not dependency.blocks_closure:
            continue
        stage = "CRITICAL" if dependency.risk_level == "CRITICAL" else "BLOCKER"
        event_key = f"dependency:{dependency.id}:{dependency.status}:{dependency.risk_level}:{stage}"
        if _event_exists(db, amo_id=ctx.amo_id, car_id=car_id, event_key=event_key):
            continue
        message = f"Open {dependency.risk_level.lower()}-risk dependency requires action: {dependency.title}."
        _add_event(
            db,
            car=car,
            profile=profile,
            event_type=f"DEPENDENCY_{stage}",
            reason=message,
            actor_user_id=ctx.user_id,
            severity="CRITICAL" if dependency.risk_level == "CRITICAL" else "WARNING",
            event_key=event_key,
            system_generated=True,
        )
        _notify_control_owner(
            db,
            ctx=ctx,
            car=car,
            recipient_user_id=dependency.owner_user_id or profile.accountable_owner_user_id,
            message=message,
            severity="WARNING",
        )
        created += 1

    health = compute_car_health(
        today=today,
        car_status=str(_enum_value(car.status)),
        final_due_date=profile.current_due_date,
        accountable_owner_user_id=profile.accountable_owner_user_id,
        milestones=milestones,
        dependencies=dependencies,
        effectiveness_required=profile.effectiveness_required,
    )
    current = str(_enum_value(car.status))
    if health.state in {"OVERDUE", "CRITICAL"} and current not in {"CLOSED", "CANCELLED", "ESCALATED"}:
        if current == "DRAFT":
            transition_car(
                db,
                amo_id=ctx.amo_id,
                actor_user_id=ctx.user_id,
                car=car,
                target_status="OPEN",
                evidence_ref=None,
            )
        transition_car(
            db,
            amo_id=ctx.amo_id,
            actor_user_id=ctx.user_id,
            car=car,
            target_status="ESCALATED",
            evidence_ref=None,
        )
        car.escalated_at = _utcnow()

    db.commit()
    result = _result(db, car=car, profile=profile)
    result["new_events_created"] = created
    return result
