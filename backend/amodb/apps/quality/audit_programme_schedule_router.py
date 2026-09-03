from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_write_db

from . import models
from .audit_programme_models import (
    QualityAuditProgramme,
    QualityAuditProgrammeEvent,
    QualityAuditProgrammeItem,
)
from .enums import QMSAuditScheduleFrequency
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .schedule_weekend import annotate_notes_with_weekend_policy, resolve_schedule_window
from .planner_schedule_router import (
    PlannerAuditScheduleCreate,
    PlannerAuditScheduleResponse,
    _Candidate,
    _collect_conflicts,
    _dedupe,
    _dump_json_list,
    _enforce_conflicts,
    _notify_schedule_change,
    _schedule_response,
    _user_display_name,
    _validate_people,
)
from .router import (
    _audit_metadata,
    _resolve_audit_scope,
    _serialize_external_auditees,
    _validate_one_calendar_year,
)
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)


router = APIRouter(prefix="/audit-programmes", tags=["Quality audit programme scheduling"])

_RECURRENCE_TO_FREQUENCY: dict[str, QMSAuditScheduleFrequency] = {
    "ONE_TIME": QMSAuditScheduleFrequency.ONE_TIME,
    "MONTHLY": QMSAuditScheduleFrequency.MONTHLY,
    "QUARTERLY": QMSAuditScheduleFrequency.QUARTERLY,
    "SEMI_ANNUAL": QMSAuditScheduleFrequency.BI_ANNUAL,
    "ANNUAL": QMSAuditScheduleFrequency.ANNUAL,
}


class ProgrammeScheduleLink(BaseModel):
    programme_item_id: str
    state: str
    schedule_id: str | None = None
    scheduled_by_user_id: str | None = None
    scheduled_at: datetime | None = None
    schedule_title: str | None = None
    next_due_date: str | None = None
    frequency: str | None = None
    lifecycle_status: str | None = None
    version: int | None = None


class ProgrammeScheduleLinksResponse(BaseModel):
    items: list[ProgrammeScheduleLink] = Field(default_factory=list)


def _programme_and_item(
    db: Session,
    *,
    amo_id: str,
    programme_id: str,
    item_id: str,
    lock: bool,
) -> tuple[QualityAuditProgramme, QualityAuditProgrammeItem]:
    programme_query = db.query(QualityAuditProgramme).filter(
        QualityAuditProgramme.amo_id == amo_id,
        QualityAuditProgramme.id == programme_id,
    )
    item_query = db.query(QualityAuditProgrammeItem).filter(
        QualityAuditProgrammeItem.amo_id == amo_id,
        QualityAuditProgrammeItem.programme_id == programme_id,
        QualityAuditProgrammeItem.id == item_id,
    )
    if lock:
        programme_query = programme_query.with_for_update()
        item_query = item_query.with_for_update()
    programme = programme_query.first()
    item = item_query.first()
    if programme is None or item is None:
        raise HTTPException(status_code=404, detail="Audit programme requirement not found.")
    return programme, item


def _expected_frequency(item: QualityAuditProgrammeItem) -> QMSAuditScheduleFrequency:
    recurrence = str(item.recurrence or "").upper()
    frequency = _RECURRENCE_TO_FREQUENCY.get(recurrence)
    if frequency is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This programme requirement does not have a deterministic recurring cadence supported by the authoritative Quality Planner.",
                "programme_recurrence": recurrence,
                "supported_recurrences": sorted(_RECURRENCE_TO_FREQUENCY),
                "required_action": "Amend the governed programme requirement to a concrete supported cadence before linking a recurring planner schedule.",
            },
        )
    return frequency


def _validate_programme_window(
    *,
    programme: QualityAuditProgramme,
    item: QualityAuditProgrammeItem,
    start_date,
    end_date,
) -> None:
    if programme.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only APPROVED or ACTIVE audit programme revisions may create authoritative schedules.",
        )
    if item.state not in {"PLANNED", "DEFERRED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Only a PLANNED or governed DEFERRED programme requirement can be linked to a new authoritative schedule.",
                "current_state": item.state,
                "schedule_id": str(item.schedule_id) if item.schedule_id else None,
            },
        )
    if item.schedule_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This programme requirement is already linked to an authoritative schedule.")
    if start_date < programme.period_start or end_date > programme.period_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "The proposed schedule falls outside the approved programme period.",
                "programme_start": programme.period_start.isoformat(),
                "programme_end": programme.period_end.isoformat(),
            },
        )
    if item.target_start and start_date < item.target_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "The proposed schedule starts before the requirement target window.", "target_start": item.target_start.isoformat()},
        )
    if item.target_end and end_date > item.target_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "The proposed schedule ends after the requirement target window.", "target_end": item.target_end.isoformat()},
        )


def _item_snapshot(item: QualityAuditProgrammeItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "programme_id": str(item.programme_id),
        "state": item.state,
        "schedule_id": str(item.schedule_id) if item.schedule_id else None,
        "recurrence": item.recurrence,
        "target_start": item.target_start.isoformat() if item.target_start else None,
        "target_end": item.target_end.isoformat() if item.target_end else None,
        "scheduled_by_user_id": item.scheduled_by_user_id,
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
    }


@router.get("/{programme_id}/schedule-links", response_model=ProgrammeScheduleLinksResponse)
def list_programme_schedule_links(
    programme_id: str,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> ProgrammeScheduleLinksResponse:
    assert_quality_permission(db, ctx, "qms.audit.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme = db.query(QualityAuditProgramme).filter(
        QualityAuditProgramme.amo_id == ctx.amo_id,
        QualityAuditProgramme.id == programme_id,
    ).first()
    if programme is None:
        raise HTTPException(status_code=404, detail="Audit programme not found.")

    items = db.query(QualityAuditProgrammeItem).filter(
        QualityAuditProgrammeItem.amo_id == ctx.amo_id,
        QualityAuditProgrammeItem.programme_id == programme_id,
    ).order_by(QualityAuditProgrammeItem.target_start.asc(), QualityAuditProgrammeItem.title.asc()).all()
    schedule_ids = [item.schedule_id for item in items if item.schedule_id]
    schedules = {
        str(schedule.id): schedule
        for schedule in db.query(models.QMSAuditSchedule).filter(
            models.QMSAuditSchedule.amo_id == ctx.amo_id,
            models.QMSAuditSchedule.id.in_(schedule_ids),
        ).all()
    } if schedule_ids else {}
    metadata = {
        str(row.schedule_id): row
        for row in db.query(QMSPlannerScheduleMetadata).filter(
            QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
            QMSPlannerScheduleMetadata.schedule_id.in_(schedule_ids),
        ).all()
    } if schedule_ids else {}

    return ProgrammeScheduleLinksResponse(items=[
        ProgrammeScheduleLink(
            programme_item_id=str(item.id),
            state=item.state,
            schedule_id=str(item.schedule_id) if item.schedule_id else None,
            scheduled_by_user_id=item.scheduled_by_user_id,
            scheduled_at=item.scheduled_at,
            schedule_title=schedules.get(str(item.schedule_id)).title if item.schedule_id and str(item.schedule_id) in schedules else None,
            next_due_date=schedules.get(str(item.schedule_id)).next_due_date.isoformat() if item.schedule_id and str(item.schedule_id) in schedules else None,
            frequency=str(getattr(schedules.get(str(item.schedule_id)).frequency, "value", schedules.get(str(item.schedule_id)).frequency)) if item.schedule_id and str(item.schedule_id) in schedules else None,
            lifecycle_status=metadata.get(str(item.schedule_id)).lifecycle_status if item.schedule_id and str(item.schedule_id) in metadata else None,
            version=int(metadata.get(str(item.schedule_id)).version or 1) if item.schedule_id and str(item.schedule_id) in metadata else None,
        )
        for item in items
    ])


def _schedule_programme_requirement(
    programme_id: str,
    item_id: str,
    payload: PlannerAuditScheduleCreate,
    request: Request,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> PlannerAuditScheduleResponse:
    """Create one authoritative planner schedule and atomically link the governed requirement."""

    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    programme, item = _programme_and_item(
        db,
        amo_id=ctx.amo_id,
        programme_id=programme_id,
        item_id=item_id,
        lock=True,
    )
    start_date, end_date, duration_days = resolve_schedule_window(
        start=payload.next_due_date,
        duration_days=payload.duration_days,
        weekend_policy=payload.weekend_policy,
        title=payload.title or item.title,
    )
    _validate_one_calendar_year(start=start_date, end=end_date)
    _validate_programme_window(
        programme=programme,
        item=item,
        start_date=start_date,
        end_date=end_date,
    )
    expected_frequency = _expected_frequency(item)
    if payload.frequency != expected_frequency:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Planner frequency must match the approved programme requirement recurrence.",
                "programme_recurrence": item.recurrence,
                "expected_frequency": expected_frequency.value,
                "received_frequency": payload.frequency.value,
            },
        )

    selected_ids = _dedupe([
        payload.lead_auditor_user_id,
        payload.observer_auditor_user_id,
        payload.assistant_auditor_user_id,
        payload.auditee_user_id,
        *payload.attendee_user_ids,
    ])
    selected_users = _validate_people(db, amo_id=ctx.amo_id, user_ids=selected_ids)
    resolved_scope = _resolve_audit_scope(
        db,
        amo_id=ctx.amo_id,
        audit_scope_id=payload.audit_scope_id,
        audit_scope_code=payload.audit_scope_code,
        kind=payload.kind,
    )
    candidate = _Candidate(
        subject_type="AUDIT_SCHEDULE",
        subject_id=f"programme:{item.id}",
        title=payload.title.strip(),
        start_date=start_date,
        end_date=end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        user_ids=set(selected_ids),
    )
    conflicts = _collect_conflicts(db, amo_id=ctx.amo_id, candidate=candidate)
    _enforce_conflicts(conflicts, allow=payload.allow_conflicts)

    external_auditees = [entry.model_dump(mode="json") for entry in payload.external_auditees]
    first_external = external_auditees[0] if external_auditees else {}
    auditee_user = selected_users.get(str(payload.auditee_user_id)) if payload.auditee_user_id else None
    schedule = models.QMSAuditSchedule(
        amo_id=ctx.amo_id,
        domain=payload.domain,
        kind=payload.kind,
        audit_scope_id=resolved_scope.id,
        audit_scope_code=resolved_scope.code,
        frequency=payload.frequency,
        title=payload.title.strip(),
        scope=payload.scope,
        criteria=payload.criteria,
        auditee=payload.auditee or _user_display_name(auditee_user) or f"{first_external.get('first_name', '')} {first_external.get('last_name', '')}".strip() or first_external.get("designation"),
        auditee_email=str(payload.auditee_email or "") or (auditee_user.email if auditee_user else None) or first_external.get("email"),
        auditee_user_id=payload.auditee_user_id,
        external_auditees_json=_serialize_external_auditees(external_auditees),
        lead_auditor_user_id=payload.lead_auditor_user_id,
        observer_auditor_user_id=payload.observer_auditor_user_id,
        assistant_auditor_user_id=payload.assistant_auditor_user_id,
        notify_auditors=payload.notify_auditors,
        notify_auditees=payload.notify_auditees,
        reminder_interval_days=payload.reminder_interval_days,
        duration_days=duration_days,
        next_due_date=start_date,
        is_active=payload.automation_active,
        created_by_user_id=ctx.user_id,
    )
    db.add(schedule)
    db.flush()

    metadata = QMSPlannerScheduleMetadata(
        amo_id=ctx.amo_id,
        schedule_id=schedule.id,
        occurrence_date=start_date,
        end_date=end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        timezone_name=payload.timezone_name,
        location=payload.location.strip() if payload.location else None,
        notes=annotate_notes_with_weekend_policy(payload.notes, payload.weekend_policy),
        responsible_user_id=payload.lead_auditor_user_id,
        attendee_user_ids_json=_dump_json_list(payload.attendee_user_ids),
        external_attendees_json=_dump_json_list([entry.model_dump(mode="json") for entry in payload.external_attendees]),
        notify_attendees=payload.notify_attendees,
        lifecycle_status="ACTIVE" if payload.automation_active else "SUSPENDED",
        version=1,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(metadata)
    db.flush()

    before = _item_snapshot(item)
    now = datetime.now(timezone.utc)
    item.schedule_id = schedule.id
    item.state = "SCHEDULED"
    item.scheduled_by_user_id = ctx.user_id
    item.scheduled_at = now
    item.updated_by_user_id = ctx.user_id
    item.updated_at = now
    after = _item_snapshot(item)
    db.add(QualityAuditProgrammeEvent(
        amo_id=ctx.amo_id,
        programme_id=programme.id,
        event_type="ITEM_SCHEDULED",
        reason="Programme requirement scheduled in the authoritative Quality Planner after deterministic conflict validation.",
        before_snapshot=before,
        after_snapshot={
            **after,
            "schedule": {
                "id": str(schedule.id),
                "next_due_date": schedule.next_due_date.isoformat(),
                "frequency": payload.frequency.value,
                "start_time": payload.start_time.isoformat(timespec="minutes"),
                "end_date": end_date.isoformat(),
                "location": metadata.location,
            },
        },
        actor_user_id=ctx.user_id,
        created_at=now,
    ))
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="create_from_audit_programme",
        after={
            "programme_id": str(programme.id),
            "programme_item_id": str(item.id),
            "programme_ref": programme.programme_ref,
            "next_due_date": schedule.next_due_date.isoformat(),
            "end_date": end_date.isoformat(),
            "start_time": payload.start_time.isoformat(timespec="minutes"),
            "location": metadata.location,
            "version": metadata.version,
            "weekend_policy": payload.weekend_policy,
            "conflict_override_reason": payload.conflict_override_reason if conflicts else None,
            "conflicts": [entry.model_dump(mode="json") for entry in conflicts],
        },
        correlation_id=f"qms-programme-planner-create:{item.id}:{schedule.id}",
        metadata=_audit_metadata(request),
        critical=True,
    )
    notifications_queued = _notify_schedule_change(
        db,
        schedule=schedule,
        metadata=metadata,
        state="created",
        reason=payload.conflict_override_reason or f"Created from audit programme {programme.programme_ref}.",
    )
    db.commit()
    db.refresh(schedule)
    db.refresh(metadata)
    return _schedule_response(schedule, metadata, notifications_queued=notifications_queued, conflicts=conflicts)
