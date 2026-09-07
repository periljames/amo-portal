from __future__ import annotations

from datetime import date, datetime, time, timezone
import json
from typing import Any
import uuid

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
from .audit_programme_occurrence_models import QualityAuditProgrammeOccurrenceLink
from .enums import QMSAuditKind, QMSAuditScheduleFrequency
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
    scheduled_count: int = 0
    adjusted_count: int = 0
    occurrences: list[dict[str, Any]] = Field(default_factory=list)


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
        programme_query = programme_query.with_for_update(of=QualityAuditProgramme)
        # QualityAuditProgrammeItem eagerly joins its audit-area relationship.
        # Restrict the lock to the programme-item table so PostgreSQL does not
        # attempt to lock the nullable side of that outer join.
        item_query = item_query.with_for_update(of=QualityAuditProgrammeItem)
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
    occurrence_links = db.query(QualityAuditProgrammeOccurrenceLink).filter(
        QualityAuditProgrammeOccurrenceLink.amo_id == ctx.amo_id,
        QualityAuditProgrammeOccurrenceLink.programme_id == programme_id,
        QualityAuditProgrammeOccurrenceLink.occurrence_type == "FIXED_DATE",
    ).order_by(QualityAuditProgrammeOccurrenceLink.occurrence_key.asc()).all()
    occurrence_by_item: dict[str, list[QualityAuditProgrammeOccurrenceLink]] = {}
    for occurrence in occurrence_links:
        occurrence_by_item.setdefault(str(occurrence.programme_item_id), []).append(occurrence)
    schedule_ids = list({
        *[item.schedule_id for item in items if item.schedule_id],
        *[link.schedule_id for link in occurrence_links],
    })
    schedules = {
        str(schedule.id): schedule
        for schedule in db.query(models.QMSAuditSchedule).filter(
            models.QMSAuditSchedule.amo_id == ctx.amo_id,
            models.QMSAuditSchedule.id.in_(schedule_ids),
            models.QMSAuditSchedule.deleted_at.is_(None),
        ).all()
    } if schedule_ids else {}
    metadata = {
        str(row.schedule_id): row
        for row in db.query(QMSPlannerScheduleMetadata).filter(
            QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
            QMSPlannerScheduleMetadata.schedule_id.in_(schedule_ids),
        ).all()
    } if schedule_ids else {}

    response_items: list[ProgrammeScheduleLink] = []
    for item in items:
        item_occurrences = occurrence_by_item.get(str(item.id), [])
        occurrence_payload = []
        for link in item_occurrences:
            snapshot = link.source_snapshot if isinstance(link.source_snapshot, dict) else {}
            linked_schedule = schedules.get(str(link.schedule_id))
            linked_metadata = metadata.get(str(link.schedule_id))
            occurrence_payload.append({
                "schedule_id": str(link.schedule_id),
                "occurrence_key": link.occurrence_key,
                "requested_date": snapshot.get("requested_date"),
                "scheduled_date": linked_schedule.next_due_date.isoformat() if linked_schedule else snapshot.get("scheduled_date"),
                "adjusted": bool(snapshot.get("adjusted")),
                "adjustment_message": snapshot.get("adjustment_message"),
                "lifecycle_status": linked_metadata.lifecycle_status if linked_metadata else None,
            })
        response_items.append(ProgrammeScheduleLink(
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
            scheduled_count=len(occurrence_payload) or (1 if item.schedule_id else 0),
            adjusted_count=sum(1 for entry in occurrence_payload if entry["adjusted"]),
            occurrences=occurrence_payload,
        ))
    return ProgrammeScheduleLinksResponse(items=response_items)


def materialize_fixed_date_programme(
    *,
    db: Session,
    programme: QualityAuditProgramme,
    request: Request,
    ctx: TenantContext,
) -> dict[str, Any]:
    """Create idempotent one-time Planner schedules for approved calendar anchors."""
    from .planner_assignment_guard_router import _create_guarded_planner_audit_schedule

    today = date.today()
    generated = 0
    existing_count = 0
    adjusted: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    pending_activation: list[dict[str, Any]] = []
    for item in list(programme.items or []):
        if item.state == "CANCELLED" or item.recurrence != "FIXED_DATES" or not item.auto_schedule:
            continue
        existing_links = {
            row.occurrence_key: row
            for row in db.query(QualityAuditProgrammeOccurrenceLink).filter(
                QualityAuditProgrammeOccurrenceLink.amo_id == ctx.amo_id,
                QualityAuditProgrammeOccurrenceLink.programme_item_id == item.id,
                QualityAuditProgrammeOccurrenceLink.occurrence_type == "FIXED_DATE",
            ).all()
        }
        item_generated = 0
        for month_day in list(item.fixed_dates or []):
            requested = date.fromisoformat(f"{programme.programme_year}-{month_day}")
            occurrence_key = f"FIXED_DATE:{requested.isoformat()}"
            if occurrence_key in existing_links:
                existing_count += 1
                continue
            if requested < today:
                skipped.append({
                    "programme_item_id": str(item.id),
                    "requested_date": requested.isoformat(),
                    "reason": "Date already passed before programme activation.",
                })
                continue
            resolved_start, resolved_end, duration_days = resolve_schedule_window(
                start=requested,
                duration_days=int(item.default_duration_days or 1),
                weekend_policy="SKIP_WEEKEND",
                title=item.title,
                require_confirmation=False,
            )
            adjustment_message = None
            if resolved_start != requested:
                adjustment_message = (
                    f"{requested.strftime('%A %d %B %Y')} falls on a weekend; "
                    f"the audit was scheduled for {resolved_start.strftime('%A %d %B %Y')}."
                )
                adjusted.append({
                    "programme_item_id": str(item.id),
                    "requested_date": requested.isoformat(),
                    "scheduled_date": resolved_start.isoformat(),
                    "message": adjustment_message,
                })
            criteria = "\n".join(
                value if isinstance(value, str) else json.dumps(value, sort_keys=True)
                for value in list(item.criteria or [])
            )
            supporting_auditors = list(item.supporting_auditor_user_ids or [])
            payload = PlannerAuditScheduleCreate(
                title=item.title,
                kind=QMSAuditKind(str(programme.programme_kind or "INTERNAL")),
                frequency=QMSAuditScheduleFrequency.ONE_TIME,
                next_due_date=requested,
                start_time=item.default_start_time or time(hour=9),
                end_time=item.default_end_time or time(hour=17),
                duration_days=int(item.default_duration_days or 1),
                location=item.default_location,
                scope=item.scope,
                criteria=criteria or None,
                notes=(
                    f"Generated from approved programme {programme.programme_ref}; "
                    f"calendar anchor {requested.isoformat()}."
                ),
                auditee=item.universe_item.display_label if item.universe_item else None,
                auditee_user_id=item.auditee_user_id,
                lead_auditor_user_id=item.lead_auditor_user_id,
                observer_auditor_user_id=item.observer_auditor_user_id,
                assistant_auditor_user_id=supporting_auditors[0] if supporting_auditors else None,
                attendee_user_ids=supporting_auditors[1:],
                notify_auditors=bool(item.notify_auditors),
                notify_auditees=bool(item.notify_auditees),
                automation_active=True,
                weekend_policy="SKIP_WEEKEND",
                conflict_override_reason=adjustment_message or f"Activated from approved programme {programme.programme_ref}.",
            )
            try:
                schedule = _create_guarded_planner_audit_schedule(
                    payload=payload,
                    request=request,
                    ctx=ctx,
                    db=db,
                    commit=False,
                )
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                if exc.status_code != status.HTTP_409_CONFLICT or "assignment_gate" not in detail:
                    raise
                pending_reason = (
                    f"{adjustment_message + ' ' if adjustment_message else ''}"
                    "The date is reserved; activate it after the required auditor independence declaration."
                )
                schedule = _create_guarded_planner_audit_schedule(
                    payload=payload.model_copy(update={
                        "automation_active": False,
                        "conflict_override_reason": pending_reason,
                    }),
                    request=request,
                    ctx=ctx,
                    db=db,
                    commit=False,
                )
                pending_activation.append({
                    "programme_item_id": str(item.id),
                    "requested_date": requested.isoformat(),
                    "scheduled_date": resolved_start.isoformat(),
                    "reason": "Auditor independence declaration required before activation.",
                    "assignment_gate": detail.get("assignment_gate", []),
                })
            schedule_uuid = uuid.UUID(str(schedule.id))
            now = datetime.now(timezone.utc)
            db.add(QualityAuditProgrammeOccurrenceLink(
                amo_id=ctx.amo_id,
                programme_id=programme.id,
                programme_item_id=item.id,
                schedule_id=schedule_uuid,
                occurrence_type="FIXED_DATE",
                occurrence_key=occurrence_key,
                rationale="Generated from an approved recurring calendar date in the annual audit programme.",
                source_snapshot={
                    "programme_ref": programme.programme_ref,
                    "requested_date": requested.isoformat(),
                    "scheduled_date": resolved_start.isoformat(),
                    "end_date": resolved_end.isoformat(),
                    "adjusted": resolved_start != requested,
                    "adjustment_message": adjustment_message,
                    "non_working_day_policy": item.non_working_day_policy,
                },
                created_by_user_id=ctx.user_id,
                created_at=now,
            ))
            if item.schedule_id is None:
                item.schedule_id = schedule_uuid
            item.state = "SCHEDULED"
            item.scheduled_by_user_id = ctx.user_id
            item.scheduled_at = now
            item.updated_by_user_id = ctx.user_id
            item.updated_at = now
            db.add(QualityAuditProgrammeEvent(
                amo_id=ctx.amo_id,
                programme_id=programme.id,
                event_type="ITEM_SCHEDULED",
                reason=adjustment_message or f"Scheduled {item.title} for {resolved_start.isoformat()} from the approved programme.",
                before_snapshot={"programme_item_id": str(item.id), "occurrence_key": occurrence_key},
                after_snapshot={
                    "programme_item_id": str(item.id),
                    "schedule_id": str(schedule.id),
                    "requested_date": requested.isoformat(),
                    "scheduled_date": resolved_start.isoformat(),
                    "adjusted": resolved_start != requested,
                },
                actor_user_id=ctx.user_id,
                created_at=now,
            ))
            generated += 1
            item_generated += 1
        if item_generated == 0 and not existing_links and all(
            date.fromisoformat(f"{programme.programme_year}-{value}") < today for value in list(item.fixed_dates or [])
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"{item.title} has no remaining date that can be scheduled in {programme.programme_year}.",
                    "required_action": "Return the programme to draft or create an amendment with a future calendar date.",
                },
            )
    return {
        "generated": generated,
        "already_scheduled": existing_count,
        "adjustments": adjusted,
        "skipped_past_dates": skipped,
        "pending_activation": pending_activation,
    }


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
