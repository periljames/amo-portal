from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.fleet.models import Aircraft

from . import projection
from . import service as program_services
from .models import (
    AmpAircraftProgramItem,
    AmpProgramItem,
    ProgramItemStatusEnum,
)
from .revision_models import AmpAircraftBaseline, AmpProgramRevision
from .revision_schemas import (
    AmpBaselineRead,
    AmpCoverageRead,
    AmpCoverageRow,
    AmpRevisionCreate,
    AmpRevisionRead,
    AmpRevisionUpdate,
)


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict | None,
    after: dict | None,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
        ),
    )


def _get_revision(db: Session, *, amo_id: str, revision_id: int) -> AmpProgramRevision:
    revision = (
        db.query(AmpProgramRevision)
        .filter(AmpProgramRevision.amo_id == amo_id, AmpProgramRevision.id == revision_id)
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="AMP revision not found")
    return revision


def _revision_read(db: Session, revision: AmpProgramRevision) -> AmpRevisionRead:
    task_count = (
        db.query(AmpProgramItem)
        .filter(
            AmpProgramItem.template_code == revision.template_code,
            AmpProgramItem.status == ProgramItemStatusEnum.ACTIVE,
        )
        .count()
    )
    active_aircraft_count = (
        db.query(AmpAircraftBaseline)
        .filter(
            AmpAircraftBaseline.amo_id == revision.amo_id,
            AmpAircraftBaseline.revision_id == revision.id,
            AmpAircraftBaseline.status == "ACTIVE",
        )
        .count()
    )
    return AmpRevisionRead(
        id=revision.id,
        template_code=revision.template_code,
        revision_code=revision.revision_code,
        title=revision.title,
        status=revision.status,
        effective_date=revision.effective_date,
        source_reference=revision.source_reference,
        notes=revision.notes,
        approved_by_user_id=revision.approved_by_user_id,
        approved_at=revision.approved_at,
        created_by_user_id=revision.created_by_user_id,
        created_at=revision.created_at,
        updated_at=revision.updated_at,
        task_count=task_count,
        active_aircraft_count=active_aircraft_count,
    )


def list_revisions(
    db: Session,
    *,
    amo_id: str,
    template_code: str | None = None,
    status_filter: str | None = None,
) -> list[AmpRevisionRead]:
    query = db.query(AmpProgramRevision).filter(AmpProgramRevision.amo_id == amo_id)
    if template_code:
        query = query.filter(AmpProgramRevision.template_code == template_code)
    if status_filter:
        query = query.filter(AmpProgramRevision.status == status_filter.upper())
    revisions = query.order_by(
        AmpProgramRevision.template_code.asc(),
        AmpProgramRevision.created_at.desc(),
    ).all()
    return [_revision_read(db, revision) for revision in revisions]


def create_revision(
    db: Session,
    *,
    amo_id: str,
    payload: AmpRevisionCreate,
    actor: User,
) -> AmpProgramRevision:
    duplicate = (
        db.query(AmpProgramRevision)
        .filter(
            AmpProgramRevision.amo_id == amo_id,
            AmpProgramRevision.template_code == payload.template_code,
            AmpProgramRevision.revision_code == payload.revision_code,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This AMP revision already exists")
    revision = AmpProgramRevision(
        amo_id=amo_id,
        template_code=payload.template_code.strip(),
        revision_code=payload.revision_code.strip(),
        title=payload.title.strip(),
        status="DRAFT",
        effective_date=payload.effective_date,
        source_reference=payload.source_reference,
        notes=payload.notes,
        created_by_user_id=actor.id,
    )
    db.add(revision)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor.id,
        entity_type="AmpProgramRevision",
        entity_id=str(revision.id),
        action="create",
        before=None,
        after={
            "template_code": revision.template_code,
            "revision_code": revision.revision_code,
            "status": revision.status,
        },
    )
    return revision


def update_revision(
    db: Session,
    *,
    revision: AmpProgramRevision,
    payload: AmpRevisionUpdate,
    actor: User,
) -> AmpProgramRevision:
    if revision.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft AMP revisions can be edited")
    before = _revision_read(db, revision).model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(revision, field, value)
    db.add(revision)
    _audit(
        db,
        amo_id=revision.amo_id,
        actor_user_id=actor.id,
        entity_type="AmpProgramRevision",
        entity_id=str(revision.id),
        action="update",
        before=before,
        after=_revision_read(db, revision).model_dump(mode="json"),
    )
    return revision


def approve_revision(
    db: Session,
    *,
    revision: AmpProgramRevision,
    actor: User,
    approval_notes: str | None,
) -> AmpProgramRevision:
    if revision.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft AMP revisions can be approved")
    task_count = (
        db.query(AmpProgramItem)
        .filter(
            AmpProgramItem.template_code == revision.template_code,
            AmpProgramItem.status == ProgramItemStatusEnum.ACTIVE,
        )
        .count()
    )
    if task_count == 0:
        raise HTTPException(
            status_code=409,
            detail="The template has no active maintenance programme items and cannot be approved.",
        )
    previous_approved = (
        db.query(AmpProgramRevision)
        .filter(
            AmpProgramRevision.amo_id == revision.amo_id,
            AmpProgramRevision.template_code == revision.template_code,
            AmpProgramRevision.status == "APPROVED",
            AmpProgramRevision.id != revision.id,
        )
        .all()
    )
    for previous in previous_approved:
        previous.status = "SUPERSEDED"
        db.add(previous)
    revision.status = "APPROVED"
    revision.effective_date = revision.effective_date or date.today()
    revision.approved_by_user_id = actor.id
    revision.approved_at = datetime.now(UTC)
    if approval_notes:
        revision.notes = "\n\n".join(filter(None, [revision.notes, f"Approval: {approval_notes}"]))
    db.add(revision)
    _audit(
        db,
        amo_id=revision.amo_id,
        actor_user_id=actor.id,
        entity_type="AmpProgramRevision",
        entity_id=str(revision.id),
        action="approve",
        before={"status": "DRAFT"},
        after={"status": revision.status, "task_count": task_count},
    )
    return revision


def apply_revision_to_aircraft(
    db: Session,
    *,
    revision: AmpProgramRevision,
    aircraft_serial_number: str,
    notes: str | None,
    actor: User,
) -> AmpBaselineRead:
    if revision.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only an approved AMP revision can be applied")
    aircraft = (
        db.query(Aircraft)
        .filter(
            Aircraft.amo_id == revision.amo_id,
            Aircraft.serial_number == aircraft_serial_number,
        )
        .first()
    )
    if not aircraft:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    current_baselines = (
        db.query(AmpAircraftBaseline)
        .filter(
            AmpAircraftBaseline.amo_id == revision.amo_id,
            AmpAircraftBaseline.aircraft_serial_number == aircraft_serial_number,
            AmpAircraftBaseline.status == "ACTIVE",
        )
        .all()
    )
    for current in current_baselines:
        if current.revision_id == revision.id:
            return AmpBaselineRead(
                id=current.id,
                aircraft_serial_number=current.aircraft_serial_number,
                revision_id=revision.id,
                template_code=revision.template_code,
                revision_code=revision.revision_code,
                revision_title=revision.title,
                status=current.status,
                applied_by_user_id=current.applied_by_user_id,
                applied_at=current.applied_at,
                notes=current.notes,
                requirements_created=0,
                requirements_existing=(
                    db.query(AmpAircraftProgramItem)
                    .join(AmpProgramItem, AmpProgramItem.id == AmpAircraftProgramItem.program_item_id)
                    .filter(
                        AmpAircraftProgramItem.aircraft_serial_number == aircraft_serial_number,
                        AmpProgramItem.template_code == revision.template_code,
                    )
                    .count()
                ),
            )
        current.status = "SUPERSEDED"
        db.add(current)

    items = (
        db.query(AmpProgramItem)
        .filter(
            AmpProgramItem.template_code == revision.template_code,
            AmpProgramItem.status == ProgramItemStatusEnum.ACTIVE,
        )
        .order_by(AmpProgramItem.ata_chapter.asc(), AmpProgramItem.task_number.asc())
        .all()
    )
    if not items:
        raise HTTPException(status_code=409, detail="Approved revision has no active maintenance items")
    existing_ids = {
        row.program_item_id
        for row in (
            db.query(AmpAircraftProgramItem)
            .filter(AmpAircraftProgramItem.aircraft_serial_number == aircraft_serial_number)
            .all()
        )
    }
    created = 0
    existing = 0
    for item in items:
        if item.id in existing_ids:
            existing += 1
            continue
        program_services.create_aircraft_program_item(
            db,
            amo_id=revision.amo_id,
            aircraft_serial_number=aircraft_serial_number,
            program_item=item,
            created_by_user_id=actor.id,
        )
        created += 1

    baseline = AmpAircraftBaseline(
        amo_id=revision.amo_id,
        aircraft_serial_number=aircraft_serial_number,
        revision_id=revision.id,
        template_code=revision.template_code,
        status="ACTIVE",
        applied_by_user_id=actor.id,
        notes=notes,
    )
    db.add(baseline)
    db.flush()
    projection.recompute_due_for_aircraft(
        db,
        amo_id=revision.amo_id,
        aircraft_serial_number=aircraft_serial_number,
    )
    _audit(
        db,
        amo_id=revision.amo_id,
        actor_user_id=actor.id,
        entity_type="AmpAircraftBaseline",
        entity_id=str(baseline.id),
        action="apply",
        before=None,
        after={
            "aircraft_serial_number": aircraft_serial_number,
            "revision_id": revision.id,
            "requirements_created": created,
            "requirements_existing": existing,
        },
    )
    return AmpBaselineRead(
        id=baseline.id,
        aircraft_serial_number=baseline.aircraft_serial_number,
        revision_id=revision.id,
        template_code=revision.template_code,
        revision_code=revision.revision_code,
        revision_title=revision.title,
        status=baseline.status,
        applied_by_user_id=baseline.applied_by_user_id,
        applied_at=baseline.applied_at,
        notes=baseline.notes,
        requirements_created=created,
        requirements_existing=existing,
    )


def list_baselines(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str | None = None,
) -> list[AmpBaselineRead]:
    query = (
        db.query(AmpAircraftBaseline, AmpProgramRevision)
        .join(AmpProgramRevision, AmpProgramRevision.id == AmpAircraftBaseline.revision_id)
        .filter(AmpAircraftBaseline.amo_id == amo_id)
    )
    if aircraft_serial_number:
        query = query.filter(AmpAircraftBaseline.aircraft_serial_number == aircraft_serial_number)
    rows = query.order_by(AmpAircraftBaseline.applied_at.desc()).all()
    return [
        AmpBaselineRead(
            id=baseline.id,
            aircraft_serial_number=baseline.aircraft_serial_number,
            revision_id=revision.id,
            template_code=revision.template_code,
            revision_code=revision.revision_code,
            revision_title=revision.title,
            status=baseline.status,
            applied_by_user_id=baseline.applied_by_user_id,
            applied_at=baseline.applied_at,
            notes=baseline.notes,
        )
        for baseline, revision in rows
    ]


def coverage(db: Session, *, amo_id: str) -> AmpCoverageRead:
    aircraft_rows = (
        db.query(Aircraft)
        .filter(Aircraft.amo_id == amo_id, Aircraft.is_active.is_(True))
        .order_by(Aircraft.registration.asc())
        .all()
    )
    active_baselines = {
        baseline.aircraft_serial_number: (baseline, revision)
        for baseline, revision in (
            db.query(AmpAircraftBaseline, AmpProgramRevision)
            .join(AmpProgramRevision, AmpProgramRevision.id == AmpAircraftBaseline.revision_id)
            .filter(
                AmpAircraftBaseline.amo_id == amo_id,
                AmpAircraftBaseline.status == "ACTIVE",
            )
            .all()
        )
    }
    requirement_rows = (
        db.query(AmpAircraftProgramItem)
        .join(Aircraft, Aircraft.serial_number == AmpAircraftProgramItem.aircraft_serial_number)
        .filter(Aircraft.amo_id == amo_id)
        .all()
    )
    requirements_by_aircraft: Counter[str] = Counter()
    unbaselined_by_aircraft: Counter[str] = Counter()
    for item in requirement_rows:
        requirements_by_aircraft[item.aircraft_serial_number] += 1
        program = item.program_item
        has_due_anchor = any(
            value is not None
            for value in (
                item.last_done_date,
                item.last_done_hours,
                item.last_done_cycles,
                program.threshold_days if program else None,
                program.threshold_hours if program else None,
                program.threshold_cycles if program else None,
            )
        )
        if not has_due_anchor:
            unbaselined_by_aircraft[item.aircraft_serial_number] += 1

    rows: list[AmpCoverageRow] = []
    for aircraft in aircraft_rows:
        pair = active_baselines.get(aircraft.serial_number)
        baseline, revision = pair if pair else (None, None)
        rows.append(
            AmpCoverageRow(
                aircraft_serial_number=aircraft.serial_number,
                registration=aircraft.registration,
                model=aircraft.model or aircraft.aircraft_model_code or aircraft.template,
                template_code=revision.template_code if revision else aircraft.template,
                revision_code=revision.revision_code if revision else None,
                revision_status=revision.status if revision else None,
                baseline_status="ACTIVE" if baseline else "MISSING",
                applied_at=baseline.applied_at if baseline else None,
                active_requirement_count=requirements_by_aircraft[aircraft.serial_number],
                unbaselined_requirement_count=unbaselined_by_aircraft[aircraft.serial_number],
            )
        )
    return AmpCoverageRead(
        generated_at=datetime.now(UTC),
        summary={
            "fleet_aircraft": len(rows),
            "active_baselines": sum(1 for row in rows if row.baseline_status == "ACTIVE"),
            "missing_baselines": sum(1 for row in rows if row.baseline_status == "MISSING"),
            "active_requirements": sum(row.active_requirement_count for row in rows),
            "unbaselined_requirements": sum(row.unbaselined_requirement_count for row in rows),
        },
        rows=rows,
    )
