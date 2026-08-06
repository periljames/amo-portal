from __future__ import annotations

from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit.models import AuditEvent
from amodb.apps.fleet import models as fleet_models
from amodb.apps.technical_records import models as technical_models
from amodb.database import get_db
from amodb.security import get_current_active_user, require_roles

from . import models, schemas, services
from .common import (
    ENTRY_ROLES,
    _aircraft,
    _amo_id,
    _build_preview,
    _entry_read,
    _require_authority,
)

def preview_entry(
    serial_number: str,
    payload: schemas.DailyUtilisationInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if payload.operation_date > date.today():
        raise HTTPException(
            status_code=422,
            detail="Future operating dates are not allowed",
        )
    amo_id = _amo_id(user)
    aircraft = _aircraft(db, amo_id, serial_number)
    return _build_preview(db, amo_id, aircraft, payload)

def create_draft(
    serial_number: str,
    payload: schemas.DailyUtilisationInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ENTRY_ROLES)),
):
    _require_authority(user, ENTRY_ROLES, "Daily utilisation entry")
    if payload.operation_date > date.today():
        raise HTTPException(
            status_code=422,
            detail="Future operating dates are not allowed",
        )
    amo_id = _amo_id(user)
    aircraft = _aircraft(db, amo_id, serial_number)
    preview = _build_preview(db, amo_id, aircraft, payload)

    hash_payload = payload.model_dump(mode="json")
    hash_payload["aircraft_serial_number"] = serial_number
    digest = services.content_hash(hash_payload)
    existing = (
        db.query(models.DailyUtilisationEntry)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.idempotency_key
            == payload.idempotency_key,
        )
        .first()
    )
    if existing:
        if existing.content_hash != digest:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was reused with different content",
            )
        return schemas.DailyUtilisationDraftRead(
            entry=_entry_read(existing),
            preview=preview,
        )

    legacy_usage = (
        db.query(fleet_models.AircraftUsage.id)
        .filter(
            fleet_models.AircraftUsage.amo_id == amo_id,
            fleet_models.AircraftUsage.aircraft_serial_number == serial_number,
            fleet_models.AircraftUsage.date == payload.operation_date,
        )
        .first()
    )
    technical_usage = (
        db.query(technical_models.AircraftUtilisation.id)
        .filter(
            technical_models.AircraftUtilisation.amo_id == amo_id,
            technical_models.AircraftUtilisation.tail_id == serial_number,
            technical_models.AircraftUtilisation.entry_date
            == payload.operation_date,
        )
        .first()
    )
    if legacy_usage or technical_usage:
        raise HTTPException(
            status_code=409,
            detail=(
                "Existing utilisation data for this aircraft/date must be "
                "reconciled before using the daily ledger"
            ),
        )

    active = (
        db.query(models.DailyUtilisationEntry.id)
        .filter(
            models.DailyUtilisationEntry.amo_id == amo_id,
            models.DailyUtilisationEntry.aircraft_serial_number == serial_number,
            models.DailyUtilisationEntry.operation_date
            == payload.operation_date,
            models.DailyUtilisationEntry.status.in_(["DRAFT", "POSTED"]),
        )
        .first()
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail=(
                "An active daily utilisation entry already exists for this "
                "aircraft and date"
            ),
        )

    entry = models.DailyUtilisationEntry(
        amo_id=amo_id,
        aircraft_serial_number=serial_number,
        operation_date=payload.operation_date,
        techlog_no=payload.techlog_no,
        station=payload.station,
        flight_hours=payload.flight_hours,
        cycles=payload.cycles,
        nil_operation=payload.nil_operation,
        source_type="MANUAL",
        source_reference=payload.source_reference,
        idempotency_key=payload.idempotency_key,
        content_hash=digest,
        remarks=payload.remarks,
        created_by_user_id=user.id,
    )
    db.add(entry)
    db.flush()
    for item in preview.exposures:
        db.add(
            models.DailyUtilisationExposure(
                entry_id=entry.id,
                **item.model_dump(),
            )
        )
    db.add(
        AuditEvent(
            amo_id=amo_id,
            entity_type="DailyUtilisationEntry",
            entity_id=entry.id,
            action="CREATE_DRAFT",
            actor_user_id=user.id,
            after={
                "aircraft": serial_number,
                "date": payload.operation_date.isoformat(),
            },
        )
    )
    db.commit()
    db.refresh(entry)
    return schemas.DailyUtilisationDraftRead(
        entry=_entry_read(entry),
        preview=preview,
    )
