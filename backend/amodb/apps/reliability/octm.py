"""Governed oil-consumption monitoring (MCM 3.10.6.14).

Source observations are never authoritative rates until reviewed. External EFB
data enters the same draft/review flow as paper technical-log entries.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from amodb.database import Base, get_write_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models
from amodb.apps.fleet.models import Aircraft
from amodb.utils.identifiers import generate_uuid7
from . import advanced_services as access
from .models import EngineFlightSnapshot

def utcnow():
    return datetime.now(timezone.utc)

# Source-native values are retained. No implicit mass-to-volume conversions.
QT_PER_UNIT = {"QT": Decimal("1"), "L": Decimal("1.0566882094"), "US_GAL": Decimal("4")}
SOURCE_TYPES = {"PAPER_TECHSHEET", "REVIEWED_OCR", "AVI_PRO_EXPORT", "AVI_PRO_API"}
EVENT_TYPES = {"TOP_UP", "CHECK_ZERO", "MISSING", "NO_OPERATION", "OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING"}


class OCTMEntry(Base):
    __tablename__ = "reliability_octm_entries"
    __table_args__ = (
        UniqueConstraint("amo_id", "aircraft_serial_number", "techsheet_ref", "engine_serial_number",
                         "event_sequence", name="uq_octm_source_event"),
        Index("ix_octm_engine_date", "amo_id", "engine_serial_number", "installation_ref", "event_date"),
        Index("ix_octm_queue", "amo_id", "review_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False)
    engine_position = Column(String(32), nullable=False)
    engine_serial_number = Column(String(100), nullable=False)
    installation_ref = Column(String(120), nullable=False)
    event_date = Column(Date, nullable=False)
    event_sequence = Column(Integer, nullable=False)
    techsheet_ref = Column(String(160), nullable=False)
    sector_ref = Column(String(100))
    source_type = Column(String(32), nullable=False)
    external_record_id = Column(String(180))
    source_evidence_ref = Column(String(512))
    maintenance_complete = Column(String(24), nullable=False, default="UNKNOWN")
    event_type = Column(String(32), nullable=False)
    oil_quantity = Column(Float)
    oil_unit = Column(String(16))
    oil_specification = Column(String(100))
    reference_method = Column(String(120))
    reference_level = Column(String(120))
    engine_counter_hours = Column(Float)
    flight_hours = Column(Float)
    remarks = Column(Text)
    review_status = Column(String(24), nullable=False, default="DRAFT")
    review_note = Column(Text)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    last_changed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    reviewed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class OCTMRevision(Base):
    __tablename__ = "reliability_octm_revisions"
    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_id = Column(String(36), ForeignKey("reliability_octm_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    before_json = Column(JSON, nullable=False)
    after_json = Column(JSON, nullable=False)
    reason = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    changed_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class OCTMProfile(Base):
    __tablename__ = "reliability_octm_profiles"
    __table_args__ = (
        UniqueConstraint("amo_id", "engine_serial_number", "installation_ref", "version", name="uq_octm_profile_version"),
        Index("ix_octm_profile_effective", "amo_id", "engine_serial_number", "installation_ref", "effective_from"),
    )
    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    engine_serial_number = Column(String(100), nullable=False)
    installation_ref = Column(String(120), nullable=False)
    version = Column(Integer, nullable=False)
    engine_model = Column(String(120), nullable=False)
    limit_qt_per_fh = Column(Float, nullable=False)
    alert_increase_percent = Column(Float)
    technical_data_ref = Column(String(200), nullable=False)
    technical_data_revision = Column(String(100), nullable=False)
    effective_from = Column(Date, nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class EntryPayload(BaseModel):
    aircraft_serial_number: str = Field(min_length=1, max_length=50)
    engine_position: str = Field(min_length=1, max_length=32)
    engine_serial_number: str = Field(min_length=1, max_length=100)
    installation_ref: str = Field(min_length=1, max_length=120)
    event_date: date
    event_sequence: int = Field(ge=1, le=99999)
    techsheet_ref: str = Field(min_length=1, max_length=160)
    sector_ref: str | None = Field(default=None, max_length=100)
    source_type: Literal["PAPER_TECHSHEET", "REVIEWED_OCR", "AVI_PRO_EXPORT", "AVI_PRO_API"] = "PAPER_TECHSHEET"
    external_record_id: str | None = Field(default=None, max_length=180)
    source_evidence_ref: str | None = Field(default=None, max_length=512)
    maintenance_complete: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    event_type: Literal["TOP_UP", "CHECK_ZERO", "MISSING", "NO_OPERATION", "OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING"]
    oil_quantity: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    oil_unit: Literal["QT", "L", "US_GAL"] | None = None
    oil_specification: str | None = Field(default=None, max_length=100)
    reference_method: str | None = Field(default=None, max_length=120)
    reference_level: str | None = Field(default=None, max_length=120)
    engine_counter_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    flight_hours: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    remarks: str | None = None

    @field_validator("aircraft_serial_number", "engine_position", "engine_serial_number", "installation_ref",
                     "techsheet_ref")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field must not be blank")
        return value.strip()

    @field_validator("sector_ref", "source_evidence_ref", "reference_method", "reference_level", "oil_specification")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def check_quantities(self):
        # Incomplete top-ups are permitted as drafts but never verifiable.
        if self.event_type == "TOP_UP" and self.oil_quantity == 0:
            raise ValueError("A top-up with zero oil must be recorded as CHECK_ZERO")
        if self.event_type == "CHECK_ZERO" and self.oil_quantity not in (None, 0):
            raise ValueError("CHECK_ZERO must not contain an uplift")
        if self.event_type in {"MISSING", "NO_OPERATION"} and self.oil_quantity is not None:
            raise ValueError("Missing/not-operated entries cannot imply an oil quantity")
        if self.event_type == "NO_OPERATION" and self.flight_hours not in (None, 0):
            raise ValueError("NO_OPERATION cannot record positive flight hours")
        if self.oil_quantity is not None and not self.oil_unit:
            raise ValueError("Oil quantity requires an explicit unit")
        if self.event_type == "CHECK_ZERO" and self.oil_quantity == 0:
            self.oil_quantity = None
            self.oil_unit = None
        if self.event_type in {"MISSING", "NO_OPERATION"} and self.oil_unit:
            raise ValueError("A missing/no-operation observation cannot specify an oil unit")
        if self.flight_hours is not None and self.flight_hours > 0 and not self.sector_ref:
            raise ValueError("Flight hours require a sector/flight reference to prevent duplicate exposure")
        if self.event_date > utcnow().date():
            raise ValueError("OCTM event date cannot be in the future")
        return self


class EntryRead(EntryPayload):
    model_config = ConfigDict(from_attributes=True)
    id: str
    review_status: str
    review_note: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class EntryReview(BaseModel):
    decision: Literal["VERIFIED", "RETURNED"]
    note: str = Field(min_length=3, max_length=2000)


class EntryCorrection(BaseModel):
    replacement: EntryPayload
    reason: str = Field(min_length=5, max_length=2000)


class ProfilePayload(BaseModel):
    engine_serial_number: str = Field(min_length=1, max_length=100)
    installation_ref: str = Field(min_length=1, max_length=120)
    engine_model: str = Field(min_length=1, max_length=120)
    limit_qt_per_fh: float = Field(gt=0, allow_inf_nan=False)
    alert_increase_percent: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    technical_data_ref: str = Field(min_length=3, max_length=200)
    technical_data_revision: str = Field(min_length=1, max_length=100)
    effective_from: date


class ProfileRead(ProfilePayload):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    status: str
    approved_at: datetime | None = None


router = APIRouter()


def context(current_user: account_models.User = Depends(get_current_active_user),
            db: Session = Depends(get_write_db)):
    return db, access.tenant_id(current_user), current_user


def require(ctx, capability: str):
    db, _, actor = ctx
    access.require_capability(db, actor, capability)


def entry_dict(payload: EntryPayload):
    return payload.model_dump()


def get_entry(ctx, entry_id: str, *, for_update: bool = False) -> OCTMEntry:
    db, amo_id, _ = ctx
    query = db.query(OCTMEntry).filter_by(id=entry_id, amo_id=amo_id)
    row = (query.with_for_update() if for_update else query).first()
    if row is None:
        raise HTTPException(404, "OCTM entry not found")
    return row


def validate_review(row: OCTMEntry, db: Session, amo_id: str) -> list[str]:
    errors = []
    if not db.query(Aircraft).filter_by(serial_number=row.aircraft_serial_number, amo_id=amo_id).first():
        errors.append("Aircraft is not registered for this tenant")
    if row.event_type != "NO_OPERATION" and row.maintenance_complete != "YES":
        errors.append("Maintenance completion must be confirmed; crew closure alone is insufficient")
    if not row.source_evidence_ref:
        errors.append("Source document reference is required before verification")
    if row.event_type in {"TOP_UP", "CHECK_ZERO", "OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING"} and not row.techsheet_ref:
        errors.append("Techsheet reference is required")
    if row.event_type == "MISSING" and not row.remarks:
        errors.append("Explain why the oil information is missing")
    if row.event_type == "NO_OPERATION" and row.flight_hours not in (None, 0):
        errors.append("A no-operation event cannot record flight hours")
    if row.event_type in {"TOP_UP", "CHECK_ZERO"}:
        if row.flight_hours is None:
            errors.append("Verified flight-hour exposure is required")
        if not row.reference_method or not row.reference_level:
            errors.append("Reference method and level are required")
    if row.event_type == "TOP_UP" and (row.oil_quantity is None or row.oil_quantity <= 0):
        errors.append("Positive oil uplift is required")
    verified = (db.query(OCTMEntry).filter(
        OCTMEntry.amo_id == amo_id, OCTMEntry.engine_serial_number == row.engine_serial_number,
        OCTMEntry.installation_ref == row.installation_ref, OCTMEntry.review_status == "VERIFIED",
        OCTMEntry.id != row.id,
    ).order_by(OCTMEntry.event_date.asc(), OCTMEntry.event_sequence.asc()).all())
    key = (row.event_date, row.event_sequence)
    for other in verified:
        other_key = (other.event_date, other.event_sequence)
        if other_key == key and other.aircraft_serial_number == row.aircraft_serial_number:
            errors.append("Engine installation has another verified event with the same date and sequence")
        if (row.sector_ref and row.flight_hours and other.sector_ref == row.sector_ref
                and other.event_date == row.event_date
                and other.aircraft_serial_number == row.aircraft_serial_number
                and other.flight_hours and abs(other.flight_hours - row.flight_hours) > 0.00001):
            errors.append("Flight hours conflict with an existing entry for the same engine/sector")
        if row.engine_counter_hours is not None and other.engine_counter_hours is not None:
            if other_key < key and other.engine_counter_hours > row.engine_counter_hours:
                errors.append("Engine counter is below an earlier verified counter")
            if other_key > key and other.engine_counter_hours < row.engine_counter_hours:
                errors.append("Engine counter exceeds a later verified counter")
        if (other_key <= key and other.aircraft_serial_number == row.aircraft_serial_number
                and other.engine_position != row.engine_position):
            errors.append("Engine position differs within the same installation history")
    if row.event_type == "TOP_UP":
        if row.oil_quantity is None or row.oil_quantity <= 0 or not row.oil_unit:
            errors.append("A positive oil uplift and original volume unit are required")
        if not row.oil_specification:
            errors.append("Oil specification is required for top-ups")
    return sorted(set(errors))


@router.get("/octm/entries", response_model=list[EntryRead])
def entries(aircraft: str | None = None, status: str | None = None, limit: int = Query(200, ge=1, le=500),
            ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    query = db.query(OCTMEntry).filter(OCTMEntry.amo_id == amo_id)
    if aircraft:
        query = query.filter(OCTMEntry.aircraft_serial_number == aircraft)
    if status:
        query = query.filter(OCTMEntry.review_status == status)
    return query.order_by(OCTMEntry.event_date.desc(), OCTMEntry.event_sequence.desc()).limit(limit).all()


@router.post("/octm/entries", response_model=EntryRead, status_code=201)
def create_entry(payload: EntryPayload, ctx=Depends(context)):
    require(ctx, "reliability.ingest")
    db, amo_id, actor = ctx
    if payload.source_type not in {"PAPER_TECHSHEET", "REVIEWED_OCR"}:
        raise HTTPException(422, "Direct entry supports paper techsheets or reviewed OCR only. Electronic EFB imports require a controlled adapter.")
    if not db.query(Aircraft).filter_by(amo_id=amo_id, serial_number=payload.aircraft_serial_number).first():
        raise HTTPException(422, "Aircraft is not registered for this tenant")
    match = db.query(OCTMEntry).filter_by(
        amo_id=amo_id, aircraft_serial_number=payload.aircraft_serial_number,
        techsheet_ref=payload.techsheet_ref, engine_serial_number=payload.engine_serial_number,
        event_sequence=payload.event_sequence,
    ).first()
    if match:
        # Manual entry and later EFB import share one logical event. Never overwrite
        # a human-reviewed value silently with data from an external source.
        if all(getattr(match, key) == value for key, value in entry_dict(payload).items()):
            return match
        raise HTTPException(409, "Conflicting OCTM event exists; send to Reliability for correction")
    entry = OCTMEntry(**entry_dict(payload), amo_id=amo_id,
                      created_by_user_id=str(actor.id), last_changed_by_user_id=str(actor.id), review_status="DRAFT")
    db.add(entry)
    db.flush()
    access.append_audit(db, amo_id=amo_id, entity_type="OCTM_ENTRY", entity_id=entry.id,
                        action="SOURCE_REGISTERED", payload={"source": entry.source_type, "techsheet": entry.techsheet_ref},
                        actor_user_id=str(actor.id))
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/octm/entries/{entry_id}/review", response_model=EntryRead)
def review_entry(entry_id: str, payload: EntryReview, ctx=Depends(context)):
    require(ctx, "reliability.data_quality.resolve")
    db, amo_id, actor = ctx
    row = get_entry(ctx, entry_id, for_update=True)
    if row.review_status == "VERIFIED":
        raise HTTPException(409, "Verified source records require a recorded correction")
    if payload.decision == "VERIFIED" and str(actor.id) in {
        str(row.created_by_user_id), str(row.last_changed_by_user_id)
    }:
        raise HTTPException(403, "A second authorized person must verify the source entry")
    if payload.decision == "VERIFIED":
        issues = validate_review(row, db, amo_id)
        if issues:
            raise HTTPException(422, detail={"validation_issues": issues})
    row.review_status = payload.decision
    row.review_note = payload.note
    row.reviewed_by_user_id = str(actor.id)
    row.reviewed_at = utcnow()
    access.append_audit(db, amo_id=amo_id, entity_type="OCTM_ENTRY", entity_id=row.id,
                        action="SOURCE_" + payload.decision,
                        payload={"note": payload.note, "source": row.techsheet_ref}, actor_user_id=str(actor.id))
    db.commit()
    db.refresh(row)
    return row


@router.post("/octm/entries/{entry_id}/correct", response_model=EntryRead)
def correct_entry(entry_id: str, payload: EntryCorrection, ctx=Depends(context)):
    db, amo_id, actor = ctx
    row = get_entry(ctx, entry_id, for_update=True)
    codes = access.capabilities_for_user(db, actor)
    is_resolver = "reliability.data_quality.resolve" in codes
    is_owner_draft = ("reliability.ingest" in codes and row.review_status != "VERIFIED"
                      and str(row.created_by_user_id) == str(actor.id))
    if not (is_resolver or is_owner_draft):
        raise HTTPException(403, "Only an authorized reviewer or the original entrant of an unverified record may correct it")
    if not db.query(Aircraft).filter_by(amo_id=amo_id, serial_number=payload.replacement.aircraft_serial_number).first():
        raise HTTPException(422, "Replacement aircraft does not belong to this tenant")
    if payload.replacement.source_type not in {"PAPER_TECHSHEET", "REVIEWED_OCR"}:
        raise HTTPException(422, "Corrections to EFB imports require the controlled source adapter")
    before = {key: getattr(row, key) for key in EntryPayload.model_fields}
    after = entry_dict(payload.replacement)
    if before == after:
        raise HTTPException(422, "Correction has no changes")
    dup = db.query(OCTMEntry).filter(
        OCTMEntry.amo_id == amo_id, OCTMEntry.id != entry_id,
        OCTMEntry.aircraft_serial_number == after["aircraft_serial_number"],
        OCTMEntry.techsheet_ref == after["techsheet_ref"],
        OCTMEntry.engine_serial_number == after["engine_serial_number"],
        OCTMEntry.event_sequence == after["event_sequence"],
    ).first()
    if dup:
        raise HTTPException(409, "Correction would duplicate an existing source event")
    for key, value in after.items():
        setattr(row, key, value)
    row.review_status = "DRAFT"
    row.last_changed_by_user_id = str(actor.id)
    row.reviewed_by_user_id = None
    row.reviewed_at = None
    row.review_note = "Corrected; re-verification required"
    db.add(OCTMRevision(amo_id=amo_id, entry_id=entry_id,
                        before_json={k: v.isoformat() if isinstance(v, date) else v for k,v in before.items()},
                        after_json={k: v.isoformat() if isinstance(v, date) else v for k,v in after.items()},
                        reason=payload.reason, actor_user_id=str(actor.id)))
    access.append_audit(db, amo_id=amo_id, entity_type="OCTM_ENTRY", entity_id=row.id,
                        action="SOURCE_CORRECTED", payload={"reason": payload.reason, "changed_fields": [
                            key for key in after if before.get(key) != after[key]]}, actor_user_id=str(actor.id))
    db.commit()
    db.refresh(row)
    return row


@router.get("/octm/entries/{entry_id}/history")
def entry_history(entry_id: str, ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    get_entry(ctx, entry_id)
    rows = db.query(OCTMRevision).filter_by(amo_id=amo_id, entry_id=entry_id).order_by(OCTMRevision.changed_at).all()
    return [{"changed_at": r.changed_at, "reason": r.reason, "before": r.before_json,
             "after": r.after_json, "actor_user_id": r.actor_user_id} for r in rows]


@router.get("/octm/profiles", response_model=list[ProfileRead])
def profiles(ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    return db.query(OCTMProfile).filter_by(amo_id=amo_id).order_by(OCTMProfile.created_at.desc()).all()


@router.post("/octm/profiles", response_model=ProfileRead, status_code=201)
def create_profile(payload: ProfilePayload, ctx=Depends(context)):
    require(ctx, "reliability.metric.manage")
    db, amo_id, actor = ctx
    prev = (db.query(OCTMProfile).filter_by(
        amo_id=amo_id, engine_serial_number=payload.engine_serial_number,
        installation_ref=payload.installation_ref
    ).order_by(OCTMProfile.version.desc()).first())
    row = OCTMProfile(**payload.model_dump(), amo_id=amo_id, status="DRAFT",
                      version=(prev.version + 1 if prev else 1), created_by_user_id=str(actor.id))
    db.add(row)
    db.flush()
    access.append_audit(db, amo_id=amo_id, entity_type="OCTM_PROFILE", entity_id=row.id,
                        action="PROFILE_DRAFTED", payload={"version": row.version, "technical_data_ref": row.technical_data_ref},
                        actor_user_id=str(actor.id))
    db.commit()
    db.refresh(row)
    return row


@router.post("/octm/profiles/{profile_id}/approve", response_model=ProfileRead)
def approve_profile(profile_id: str, ctx=Depends(context)):
    require(ctx, "reliability.programme.approve")
    db, amo_id, actor = ctx
    row = db.query(OCTMProfile).filter_by(amo_id=amo_id, id=profile_id).first()
    if not row:
        raise HTTPException(404, "OCTM profile not found")
    if row.status != "DRAFT":
        raise HTTPException(409, "Only draft profiles can be approved")
    if row.created_by_user_id == str(actor.id):
        raise HTTPException(403, "A second authorized person must approve the manufacturer limit")
    row.status = "APPROVED"
    row.approved_by_user_id = str(actor.id)
    row.approved_at = utcnow()
    access.append_audit(db, amo_id=amo_id, entity_type="OCTM_PROFILE", entity_id=row.id,
                        action="PROFILE_APPROVED", payload={"version": row.version, "limit_qt_per_fh": row.limit_qt_per_fh,
                        "technical_data_ref": row.technical_data_ref, "technical_data_revision": row.technical_data_revision},
                        actor_user_id=str(actor.id))
    db.commit()
    db.refresh(row)
    return row


def calculate_windows(rows: list[OCTMEntry], profiles: list[OCTMProfile]) -> list[dict]:
    """Disjoint 30–50 FH monitoring intervals, targeting 40 FH.

    Missing events, maintenance refills and reference changes break continuity.
    No profile => still calculate an observation, but never invent an OEM limit.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for row in rows:
        if row.review_status == "VERIFIED":
            groups[(row.engine_serial_number, row.installation_ref)].append(row)
    output = []
    for (engine, installation), events in groups.items():
        events.sort(key=lambda r: (r.event_date, r.event_sequence, r.created_at))
        active = []
        qty = Decimal(0)
        hours = Decimal(0)
        prior_key = None
        prev_rate = None
        for event in events:
            key = (event.reference_method, event.reference_level)
            if event.event_type not in {"TOP_UP", "CHECK_ZERO"} or (prior_key and key != prior_key):
                active, qty, hours, prior_key = [], Decimal(0), Decimal(0), None
                prev_rate = None
                if event.event_type not in {"TOP_UP", "CHECK_ZERO"}:
                    continue
            if event.flight_hours is None or not event.reference_method or not event.reference_level:
                active, qty, hours, prior_key = [], Decimal(0), Decimal(0), None
                continue
            prior_key = key
            active.append(event)
            hours += Decimal(str(event.flight_hours))
            if event.event_type == "TOP_UP" and event.oil_unit in QT_PER_UNIT:
                qty += Decimal(str(event.oil_quantity)) * QT_PER_UNIT[event.oil_unit]
            if hours < 40:
                continue
            accepted = Decimal("30") <= hours <= Decimal("50")
            rate = qty / hours if accepted and hours > 0 else None
            profile = next((p for p in sorted(profiles, key=lambda p: (p.effective_from, p.version), reverse=True)
                            if p.engine_serial_number == engine and p.installation_ref == installation
                            and p.status == "APPROVED" and p.effective_from <= event.event_date), None)
            limit = Decimal(str(profile.limit_qt_per_fh)) if profile else None
            increase = (float((rate / prev_rate - 1) * 100) if rate is not None and prev_rate and prev_rate > 0 else None)
            output.append({
                "engine_serial_number": engine, "installation_ref": installation,
                "aircraft_serial_number": event.aircraft_serial_number,
                "engine_position": event.engine_position,
                "window_start": active[0].event_date.isoformat(),
                "window_end": event.event_date.isoformat(),
                "source_ids": [r.id for r in active],
                "oil_added_quarts": round(float(qty), 5),
                "flight_hours": round(float(hours), 5),
                "rate_qt_per_fh": round(float(rate), 6) if rate is not None else None,
                "status": "VALID" if accepted else "OUT_OF_RANGE",
                "manufacturer_limit_qt_per_fh": float(limit) if limit else None,
                "manufacturer_limit_exceeded": bool(rate > limit) if rate is not None and limit is not None else None,
                "trend_increase_percent": round(increase, 3) if increase is not None else None,
                "trend_alert": bool(increase > profile.alert_increase_percent) if
                    increase is not None and profile and profile.alert_increase_percent is not None else None,
                "profile_id": profile.id if profile else None,
            })
            if rate is not None:
                prev_rate = rate
            active, qty, hours, prior_key = [], Decimal(0), Decimal(0), None
    return sorted(output, key=lambda x: (x["window_end"], x["engine_serial_number"]), reverse=True)


@router.get("/octm/monitoring")
def monitoring(engine_serial_number: str | None = None, ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    q = db.query(OCTMEntry).filter_by(amo_id=amo_id, review_status="VERIFIED")
    if engine_serial_number:
        q = q.filter(OCTMEntry.engine_serial_number == engine_serial_number)
    # Bounded query. Large historical exports must be paginated separately.
    rows = q.order_by(OCTMEntry.event_date.desc()).limit(20000).all()
    profiles = db.query(OCTMProfile).filter_by(amo_id=amo_id).all()
    return {"intervals": calculate_windows(rows, profiles),
            "verified_source_count": len(rows),
            "truncated": len(rows) == 20000,
            "method": "DISJOINT_VERIFIED_40_PLUS_MINUS_10_FLIGHT_HOURS"}
