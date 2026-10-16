"""Governed oil-consumption monitoring (MCM 3.10.6.14).

Source observations are never authoritative rates until reviewed. External EFB
data enters the same draft/review flow as paper technical-log entries.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
        UniqueConstraint("amo_id", "aircraft_serial_number", "techsheet_ref", "engine_position",
                         "event_sequence", name="uq_octm_source_engine_position"),
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
    source_scope = Column(String(20), nullable=False, default="SECTOR")
    source_context = Column(JSON)
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
    source_scope: Literal["SECTOR", "TECHLOG_PAGE"] = "SECTOR"
    source_context: dict | None = None
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
        from json import dumps
        if self.source_context is not None and len(dumps(self.source_context, default=str)) > 12000:
            raise ValueError("Source context exceeds the maximum supported structured data size")
        if self.source_scope == "TECHLOG_PAGE":
            if not self.sector_ref or not self.sector_ref.startswith("TECHLOG_PAGE:"):
                raise ValueError("Page-scope observations must identify their original technical-log page")
            if not self.source_context or self.source_context.get("document_type") != "SL/MCM/1":
                raise ValueError("Page-scope entries require linked SL/MCM/1 page context")
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
        if self.event_date > utcnow().date() + timedelta(days=1):
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
    source_checked: bool = False
    engine_identity_checked: bool = False
    exposure_checked: bool = False

    @model_validator(mode="after")
    def validate_attestation(self):
        if self.decision == "VERIFIED" and not (
            self.source_checked and self.engine_identity_checked and self.exposure_checked
        ):
            raise ValueError("Verification requires confirmation of source, engine identity and exposure")
        return self


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


class ProfileApproval(BaseModel):
    confirmed_current_technical_data: bool
    note: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed_current_technical_data:
            raise ValueError("Approve only after checking the referenced current manufacturer instructions")
        return self


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
    elif row.source_evidence_ref.startswith("OCTM_ASSET:"):
        from .octm_source_assets import validate_source_reference
        try:
            validate_source_reference(db, amo_id, row.aircraft_serial_number,
                                      row.techsheet_ref, row.source_evidence_ref)
        except HTTPException:
            errors.append("Retained source file no longer resolves to this tenant, aircraft and technical-log page")
    if row.event_type in {"TOP_UP", "CHECK_ZERO", "OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING"} and not row.techsheet_ref:
        errors.append("Techsheet reference is required")
    if row.event_type == "MISSING" and not row.remarks:
        errors.append("Explain why the oil information is missing")
    if row.event_type in {"OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING"} and not row.remarks:
        errors.append("Record the reason and technical-log context of non-routine oil servicing")
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
        if other.event_date == row.event_date and other.aircraft_serial_number == row.aircraft_serial_number:
            if other.source_scope != row.source_scope:
                errors.append("Source granularity conflict: page-total and sector records cannot both be verified for this engine/date")
        other_key = (other.event_date, other.event_sequence)
        if (other_key == key and other.techsheet_ref == row.techsheet_ref
                and other.aircraft_serial_number == row.aircraft_serial_number):
            errors.append("Duplicate verified event sequence within the same techsheet")
        if (row.sector_ref and other.sector_ref == row.sector_ref
                and other.event_date == row.event_date
                and other.aircraft_serial_number == row.aircraft_serial_number):
            if (row.flight_hours and other.flight_hours
                    and abs(other.flight_hours - row.flight_hours) > 0.00001):
                errors.append("Flight hours conflict with an existing entry for the same engine/sector")
            if (row.reference_method != other.reference_method
                    or row.reference_level != other.reference_level):
                errors.append("Reference method/level conflicts within the same engine/sector")
            if row.event_type == "NO_OPERATION" or other.event_type == "NO_OPERATION":
                errors.append("No-operation cannot coexist with servicing for the same sector")
        if row.engine_counter_hours is not None and other.engine_counter_hours is not None:
            older = (other.event_date < row.event_date or (
                other.event_date == row.event_date and other.techsheet_ref == row.techsheet_ref
                and other.event_sequence < row.event_sequence))
            newer = (other.event_date > row.event_date or (
                other.event_date == row.event_date and other.techsheet_ref == row.techsheet_ref
                and other.event_sequence > row.event_sequence))
            if older and other.engine_counter_hours > row.engine_counter_hours:
                errors.append("Engine counter is below an earlier verified counter")
            if newer and other.engine_counter_hours < row.engine_counter_hours:
                errors.append("Engine counter exceeds a later verified counter")
        if (other_key <= key and other.aircraft_serial_number == row.aircraft_serial_number
                and other.engine_position != row.engine_position):
            errors.append("Engine position differs within the same installation history")
    if row.source_scope == "TECHLOG_PAGE" and (
        not row.source_context or row.source_context.get("document_type") != "SL/MCM/1"
    ):
        errors.append("Verified page-scope uplift requires source technical-log page context")
    if (row.source_scope == "TECHLOG_PAGE" and row.maintenance_complete == "YES"
            and not (row.source_context or {}).get("maintenance_release_ref")):
        errors.append("Confirm the signed technical-log maintenance-release reference before page verification")
    if row.event_type == "TOP_UP":
        if row.oil_quantity is None or row.oil_quantity <= 0 or not row.oil_unit:
            errors.append("A positive oil uplift and original volume unit are required")
        if not row.oil_specification:
            errors.append("Oil specification is required for top-ups")
    # A same-day source snapshot can disprove an operator-typed engine serial,
    # but no old snapshot is treated as proof of the current installation.
    snapshot = (db.query(EngineFlightSnapshot).filter(
        EngineFlightSnapshot.amo_id == amo_id,
        EngineFlightSnapshot.aircraft_serial_number == row.aircraft_serial_number,
        EngineFlightSnapshot.engine_position == row.engine_position,
        EngineFlightSnapshot.flight_date == row.event_date,
        EngineFlightSnapshot.engine_serial_number.isnot(None),
    ).order_by(EngineFlightSnapshot.id.desc()).first())
    if snapshot and snapshot.engine_serial_number and (
        snapshot.engine_serial_number.strip().upper() != row.engine_serial_number.strip().upper()
    ):
        errors.append("Engine serial conflicts with the same-day fleet engine snapshot; reconcile installation history")
    return sorted(set(errors))


@router.get("/octm/aircraft")
def aircraft_options(ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    rows = (db.query(Aircraft).filter_by(amo_id=amo_id)
            .order_by(Aircraft.registration.asc()).limit(500).all())
    return [{"serial_number": r.serial_number, "registration": r.registration,
             "is_active": r.is_active} for r in rows]


@router.get("/octm/engine-hints")
def engine_hints(aircraft: str, event_date: date, ctx=Depends(context)):
    """Hints only: source documents must confirm actual historical installation."""
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    if not db.query(Aircraft).filter_by(amo_id=amo_id, serial_number=aircraft).first():
        raise HTTPException(404, "Aircraft not registered for this tenant")
    entries = (db.query(OCTMEntry).filter(
        OCTMEntry.amo_id == amo_id, OCTMEntry.aircraft_serial_number == aircraft,
        OCTMEntry.event_date <= event_date, OCTMEntry.review_status == "VERIFIED",
    ).order_by(OCTMEntry.event_date.desc(), OCTMEntry.event_sequence.desc()).limit(300).all())
    seen = set()
    hints = []
    for row in entries:
        key = (row.engine_position, row.engine_serial_number, row.installation_ref)
        if key not in seen:
            seen.add(key)
            hints.append({"engine_position": row.engine_position, "engine_serial_number": row.engine_serial_number,
                          "installation_ref": row.installation_ref, "last_observed": row.event_date.isoformat(),
                          "basis": "PREVIOUS_OCTM_ENTRY"})
    return hints[:100]


@router.get("/octm/entries/{entry_id}/readiness")
def entry_readiness(entry_id: str, ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, actor = ctx
    row = get_entry(ctx, entry_id)
    errors = validate_review(row, db, amo_id)
    if str(actor.id) in {str(row.created_by_user_id), str(row.last_changed_by_user_id)}:
        errors.append("A different authorized person must verify this entry")
    if row.review_status == "VERIFIED":
        errors.append("Verified entries require a recorded correction before re-review")
    if row.review_status == "RETURNED":
        errors.append("Returned entries must be corrected and resubmitted before verification")
    warnings = []
    if row.source_type != "PAPER_TECHSHEET":
        warnings.append("Confirm extracted/imported values against the original source")
    if row.event_type in {"OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING", "MISSING"}:
        warnings.append("This event interrupts the formal consumption interval; review surrounding entries")
    return {"errors": errors, "warnings": warnings, "ready_for_verification": not errors}


def summarize_daily_coverage(snapshots, entries) -> dict:
    """Reconcile observed engine-flight legs, never infer that absent legs did not fly."""
    expected = {}
    for flight in snapshots:
        if flight.flight_leg:
            key = (flight.aircraft_serial_number, flight.engine_position, flight.flight_leg.strip().upper())
            expected[key] = {
                "aircraft_serial_number": flight.aircraft_serial_number,
                "engine_position": flight.engine_position,
                "flight_leg": flight.flight_leg,
                "engine_serial_number": flight.engine_serial_number,
            }
    observed = {}
    for row in entries:
        if row.sector_ref and row.event_type != "NO_OPERATION":
            key = (row.aircraft_serial_number, row.engine_position, row.sector_ref.strip().upper())
            observed.setdefault(key, set()).add(row.engine_serial_number.strip().upper())
    pending = [value for key, value in expected.items()
               if key not in observed or (
                   value["engine_serial_number"] and
                   value["engine_serial_number"].strip().upper() not in observed[key])]
    return {
        "registered_snapshot_sectors": len(expected),
        "matched_sectors": len(expected) - len(pending),
        "unmatched_sectors": pending,
        "entered_octm_observations": len(entries),
        "verified_observations": sum(row.review_status == "VERIFIED" for row in entries),
        "unverified_observations": sum(row.review_status != "VERIFIED" for row in entries),
        "coverage_basis": "RECORDED_ENGINE_FLIGHT_SNAPSHOTS_ONLY",
        "important": "Unmatched is a reconciliation prompt, not proof a flight or techsheet is missing. No snapshot data does not mean the aircraft did not operate.",
    }


@router.get("/octm/daily-coverage")
def daily_coverage(operating_date: date, ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    snapshots = (db.query(EngineFlightSnapshot).filter(
        EngineFlightSnapshot.amo_id == amo_id, EngineFlightSnapshot.flight_date == operating_date,
    ).order_by(EngineFlightSnapshot.id.desc()).limit(5000).all())
    entries = (db.query(OCTMEntry).filter(
        OCTMEntry.amo_id == amo_id, OCTMEntry.event_date == operating_date,
    ).order_by(OCTMEntry.event_sequence.asc()).limit(5000).all())
    result = summarize_daily_coverage(snapshots, entries)
    result["operating_date"] = operating_date.isoformat()
    result["truncated"] = len(snapshots) >= 5000 or len(entries) >= 5000
    return result


@router.get("/octm/entries", response_model=list[EntryRead])
def entries(aircraft: str | None = None, status: str | None = None, limit: int = Query(200, ge=1, le=500),
            offset: int = Query(0, ge=0), ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    query = db.query(OCTMEntry).filter(OCTMEntry.amo_id == amo_id)
    if aircraft:
        query = query.filter(OCTMEntry.aircraft_serial_number == aircraft)
    if status == "UNVERIFIED":
        query = query.filter(OCTMEntry.review_status != "VERIFIED")
    elif status:
        query = query.filter(OCTMEntry.review_status == status)
    return query.order_by(OCTMEntry.event_date.desc(), OCTMEntry.event_sequence.desc(), OCTMEntry.id.desc()).offset(offset).limit(limit).all()


@router.get("/octm/status-summary")
def octm_status_summary(ctx=Depends(context)):
    require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    rows = (db.query(OCTMEntry.review_status, func.count(OCTMEntry.id))
            .filter(OCTMEntry.amo_id == amo_id).group_by(OCTMEntry.review_status).all())
    counts = {str(code): int(count) for code, count in rows}
    return {"total": sum(counts.values()), "unverified": sum(
        amount for code, amount in counts.items() if code != "VERIFIED"),
        "status_counts": counts}


@router.post("/octm/entries", response_model=EntryRead, status_code=201)
def create_entry(payload: EntryPayload, ctx=Depends(context)):
    require(ctx, "reliability.ingest")
    db, amo_id, actor = ctx
    if payload.source_type not in {"PAPER_TECHSHEET", "REVIEWED_OCR"}:
        raise HTTPException(422, "Direct entry supports paper techsheets or reviewed OCR only. Electronic EFB imports require a controlled adapter.")
    if not db.query(Aircraft).filter_by(amo_id=amo_id, serial_number=payload.aircraft_serial_number).first():
        raise HTTPException(422, "Aircraft is not registered for this tenant")
    from .octm_source_assets import validate_source_reference
    validate_source_reference(db, amo_id, payload.aircraft_serial_number,
                              payload.techsheet_ref, payload.source_evidence_ref)
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        conflict = db.query(OCTMEntry).filter_by(
            amo_id=amo_id, aircraft_serial_number=payload.aircraft_serial_number,
            techsheet_ref=payload.techsheet_ref, engine_serial_number=payload.engine_serial_number,
            event_sequence=payload.event_sequence,
        ).first()
        if conflict and all(getattr(conflict, key) == value for key, value in entry_dict(payload).items()):
            return conflict
        raise HTTPException(409, "A concurrent entry created a conflicting source event") from exc
    db.refresh(entry)
    return entry


@router.post("/octm/entries/{entry_id}/review", response_model=EntryRead)
def review_entry(entry_id: str, payload: EntryReview, ctx=Depends(context)):
    require(ctx, "reliability.data_quality.resolve")
    db, amo_id, actor = ctx
    row = get_entry(ctx, entry_id, for_update=True)
    if row.review_status == "VERIFIED":
        raise HTTPException(409, "Verified source records require a recorded correction")
    if row.review_status == "RETURNED" and payload.decision == "VERIFIED":
        raise HTTPException(409, "Returned entries must be corrected and resubmitted before verification")
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
                        payload={"note": payload.note, "source": row.techsheet_ref,
                                 "source_checked": payload.source_checked,
                                 "engine_identity_checked": payload.engine_identity_checked,
                                 "exposure_checked": payload.exposure_checked}, actor_user_id=str(actor.id))
    db.commit()
    db.refresh(row)
    return row


@router.post("/octm/entries/{entry_id}/correct", response_model=EntryRead)
def correct_entry(entry_id: str, payload: EntryCorrection, ctx=Depends(context)):
    db, amo_id, actor = ctx
    row = get_entry(ctx, entry_id, for_update=True)
    if row.source_scope == "TECHLOG_PAGE":
        raise HTTPException(422, "A paper-page source must be corrected through the full Techlog Page workflow")
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
def approve_profile(profile_id: str, payload: ProfileApproval, ctx=Depends(context)):
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
                        "technical_data_ref": row.technical_data_ref,
                        "technical_data_revision": row.technical_data_revision, "note": payload.note,
                        "confirmed_current_technical_data": payload.confirmed_current_technical_data},
                        actor_user_id=str(actor.id))
    db.commit()
    db.refresh(row)
    return row


def calculate_windows(rows: list[OCTMEntry], profiles: list[OCTMProfile]) -> list[dict]:
    """Calculate non-overlapping 30–50 FH observations targeting 40 FH.

    First consolidate all servicing events against the same flight/sector,
    then count each sector's utilization only once. Do not carry
    incompleteness, oil changes or reference changes into a new interval.
    """
    from collections import defaultdict

    grouped = defaultdict(list)
    for row in rows:
        if row.review_status == "VERIFIED":
            grouped[(row.aircraft_serial_number, row.engine_serial_number, row.installation_ref)].append(row)
    output = []
    ordered_profiles = sorted(profiles, key=lambda p: (p.effective_from, p.version), reverse=True)
    for (aircraft, engine, installation), events in grouped.items():
        scopes_by_date = defaultdict(set)
        for row in events:
            scopes_by_date[row.event_date].add(getattr(row, "source_scope", "SECTOR"))
        mixed_dates = {day for day, scopes in scopes_by_date.items() if len(scopes) > 1}
        events.sort(key=lambda row: (row.event_date, row.event_sequence, row.created_at))
        # A sector can have multiple top-ups/checked-zero events.
        # No sector reference is only permitted for events with no flight exposure.
        sectors = {}
        for row in events:
            sector_key = (row.event_date, row.sector_ref) if row.sector_ref else (row.event_date, "ENTRY:" + row.id)
            sectors.setdefault(sector_key, []).append(row)
        window_events = []
        window_oil = Decimal("0")
        window_hours = Decimal("0")
        last_reference = None
        prev_rate = None

        def reset(*, clear_baseline: bool = False):
            nonlocal window_events, window_oil, window_hours, last_reference, prev_rate
            window_events = []
            window_oil = Decimal("0")
            window_hours = Decimal("0")
            last_reference = None
            if clear_baseline:
                prev_rate = None

        for segment in sectors.values():
            if segment[0].event_date in mixed_dates:
                reset(clear_baseline=True)
                continue
            relevant = [row for row in segment if row.event_type != "NO_OPERATION"]
            if not relevant:
                # No flying is not evidence of missing oil data.
                continue
            if any(row.event_type not in {"TOP_UP", "CHECK_ZERO"} for row in relevant):
                reset(clear_baseline=True)
                continue
            reference = (relevant[0].reference_method, relevant[0].reference_level)
            if not all((row.reference_method, row.reference_level) == reference for row in relevant):
                reset(clear_baseline=True)
                continue
            if last_reference and reference != last_reference:
                reset(clear_baseline=True)
            last_reference = reference
            exposures = {Decimal(str(row.flight_hours)) for row in relevant if row.flight_hours is not None and row.flight_hours > 0}
            if len(exposures) > 1 or any(row.flight_hours is None for row in relevant):
                reset(clear_baseline=True)
                continue
            segment_hours = next(iter(exposures), Decimal("0"))
            window_hours += segment_hours
            window_events.extend(relevant)
            for row in relevant:
                if row.event_type == "TOP_UP" and row.oil_quantity is not None and row.oil_unit in QT_PER_UNIT:
                    window_oil += Decimal(str(row.oil_quantity)) * QT_PER_UNIT[row.oil_unit]
            if window_hours < Decimal("40"):
                continue
            end = segment[-1]
            accepted = Decimal("30") <= window_hours <= Decimal("50")
            rate = window_oil / window_hours if accepted and window_hours > 0 else None
            profile = next((p for p in ordered_profiles
                            if p.engine_serial_number == engine and p.installation_ref == installation
                            and p.status == "APPROVED" and p.effective_from <= end.event_date), None)
            limit = Decimal(str(profile.limit_qt_per_fh)) if profile else None
            increase = float((rate / prev_rate - 1) * 100) if rate is not None and prev_rate and prev_rate > 0 else None
            output.append({
                "engine_serial_number": engine, "installation_ref": installation,
                "aircraft_serial_number": aircraft, "engine_position": end.engine_position,
                "window_start": window_events[0].event_date.isoformat(),
                "window_end": end.event_date.isoformat(),
                "source_ids": [row.id for row in window_events],
                "oil_added_quarts": round(float(window_oil), 5),
                "flight_hours": round(float(window_hours), 5),
                "rate_qt_per_fh": round(float(rate), 6) if rate is not None else None,
                "status": "VALID" if accepted else "OUT_OF_RANGE",
                "manufacturer_limit_qt_per_fh": float(limit) if limit is not None else None,
                "manufacturer_limit_exceeded": bool(rate > limit) if rate is not None and limit is not None else None,
                "trend_increase_percent": round(increase, 3) if increase is not None else None,
                "trend_alert": bool(increase > profile.alert_increase_percent) if
                    increase is not None and profile and profile.alert_increase_percent is not None else None,
                "profile_id": profile.id if profile else None,
            })
            if rate is not None:
                prev_rate = rate
            reset()
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
