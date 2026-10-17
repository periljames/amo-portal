"""SL/MCM/1 technical-log PAGE capture for governed OCTM source drafts.

The paper form records flight legs and per-leg *oil levels*, but oil ADDED
is recorded at PAGE level (L/H, R/H, APU). Never invent sector-specific
uplifts or infer that a blank oil-added field is a checked zero.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError

from amodb.apps.fleet.models import Aircraft
from . import octm
from . import advanced_services as access


class TechlogLeg(BaseModel):
    number: int = Field(ge=1, le=9)
    from_airport: str | None = Field(default=None, max_length=8)
    to_airport: str | None = Field(default=None, max_length=8)
    flight_hours: float = Field(ge=0, le=30, allow_inf_nan=False)
    left_oil_level: str | None = Field(default=None, max_length=50)
    right_oil_level: str | None = Field(default=None, max_length=50)
    comment: str | None = Field(default=None, max_length=250)


class TechlogEngineOil(BaseModel):
    position: Literal["1", "2"]
    engine_serial_number: str = Field(min_length=2, max_length=100)
    installation_ref: str = Field(min_length=2, max_length=120)
    observation: Literal["TOP_UP", "CHECK_ZERO", "MISSING"]
    quantity_added: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    original_unit: Literal["QT", "L", "US_GAL"] | None = None
    oil_specification: str | None = Field(default=None, max_length=100)
    reference_method: str | None = Field(default=None, max_length=120)
    reference_level: str | None = Field(default=None, max_length=120)

    @field_validator("engine_serial_number", "installation_ref")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Engine identity and installation must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def consistent_observation(self):
        if self.observation == "TOP_UP" and (self.quantity_added is None or not self.original_unit):
            raise ValueError("Recorded oil uplift must have its original quantity and explicit unit")
        if self.observation != "TOP_UP" and (self.quantity_added is not None or self.original_unit is not None):
            raise ValueError("Blank/checked-zero events cannot contain a positive oil uplift or units")
        return self


class TechlogPage(BaseModel):
    aircraft_serial_number: str = Field(min_length=1, max_length=50)
    techsheet_ref: str = Field(min_length=1, max_length=160)
    event_date: date
    source_evidence_ref: str = Field(min_length=3, max_length=512)
    source_type: Literal["PAPER_TECHSHEET", "REVIEWED_OCR"] = "PAPER_TECHSHEET"
    legs: list[TechlogLeg] = Field(min_length=1, max_length=9)
    page_flight_hours: float = Field(ge=0, le=100, allow_inf_nan=False)
    ttaf_brought_forward: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ttaf_updated: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tcsn_brought_forward: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tcsn_updated: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    maintenance_complete: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    maintenance_release_ref: str | None = Field(default=None, max_length=160)
    check_24h_ref: str | None = Field(default=None, max_length=160)
    defect_references: list[str] = Field(default_factory=list, max_length=5)
    deferred_defect_references: list[str] = Field(default_factory=list, max_length=5)
    apu_oil_added: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    apu_oil_unit: Literal["QT", "L", "US_GAL"] | None = None
    engines: list[TechlogEngineOil] = Field(min_length=1, max_length=2)

    @field_validator("aircraft_serial_number", "techsheet_ref", "source_evidence_ref")
    @classmethod
    def clean_reference(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Aircraft, page and source evidence references are required")
        return value.strip()

    @model_validator(mode="after")
    def validate_original_log(self):
        if self.event_date > octm.utcnow().date():
            raise ValueError("A future technical-log date cannot be submitted")
        numbers = [leg.number for leg in self.legs]
        if len(set(numbers)) != len(numbers):
            raise ValueError("Each technical-log leg number may appear only once")
        positions = [engine.position for engine in self.engines]
        if len(set(positions)) != len(positions):
            raise ValueError("Each engine position may appear only once")
        if "2" in positions and "1" not in positions:
            raise ValueError("The source page must include the L/H engine when R/H is entered")
        total = sum(leg.flight_hours for leg in self.legs)
        if abs(total - self.page_flight_hours) > 0.02:
            raise ValueError("Sum of the Flight Time column must agree with page flight hours")
        if (self.ttaf_brought_forward is not None and self.ttaf_updated is not None
                and abs(self.ttaf_updated - self.ttaf_brought_forward - self.page_flight_hours) > 0.02):
            raise ValueError("Updated TTAF minus brought-forward TTAF does not equal page flight time")
        if self.tcsn_brought_forward is not None and self.tcsn_updated is not None:
            if self.tcsn_updated < self.tcsn_brought_forward:
                raise ValueError("Updated TCSN cannot be below brought-forward TCSN")
        if self.apu_oil_added is not None and not self.apu_oil_unit:
            raise ValueError("APU uplift requires an explicit original unit")
        if any(not ref.strip() or len(ref) > 160 for ref in
               self.defect_references + self.deferred_defect_references):
            raise ValueError("Defect references must be nonblank and no longer than 160 characters")
        return self


def build_page_entries(page: TechlogPage) -> list[octm.EntryPayload]:
    """Create per-engine drafts; page-hours are recorded once PER ENGINE."""
    context = {
        "document_type": "SL/MCM/1",
        "capture_scope": "PAGE_TOTAL",
        "techsheet_ref": page.techsheet_ref,
        "original_legs": [leg.model_dump() for leg in sorted(page.legs, key=lambda x: x.number)],
        "page_flight_hours": page.page_flight_hours,
        "ttaf_brought_forward": page.ttaf_brought_forward,
        "ttaf_updated": page.ttaf_updated,
        "tcsn_brought_forward": page.tcsn_brought_forward,
        "tcsn_updated": page.tcsn_updated,
        "check_24h_ref": page.check_24h_ref,
        "maintenance_release_ref": page.maintenance_release_ref,
        "apu_oil_added": page.apu_oil_added,
        "apu_oil_unit": page.apu_oil_unit,
        "defect_references": page.defect_references,
        "deferred_defect_references": page.deferred_defect_references,
    }
    results = []
    for eng in page.engines:
        results.append(octm.EntryPayload(
            aircraft_serial_number=page.aircraft_serial_number,
            engine_position=eng.position,
            engine_serial_number=eng.engine_serial_number,
            installation_ref=eng.installation_ref,
            event_date=page.event_date,
            event_sequence=int(eng.position),
            techsheet_ref=page.techsheet_ref,
            sector_ref="TECHLOG_PAGE:" + page.techsheet_ref,
            source_scope="TECHLOG_PAGE",
            source_context=context,
            source_type=page.source_type,
            source_evidence_ref=page.source_evidence_ref,
            maintenance_complete=page.maintenance_complete,
            event_type=eng.observation,
            oil_quantity=eng.quantity_added,
            oil_unit=eng.original_unit,
            oil_specification=eng.oil_specification,
            reference_method=eng.reference_method,
            reference_level=eng.reference_level,
            # The paper form gives AIRCRAFT TTAF, not engine ETSN.
            engine_counter_hours=None,
            flight_hours=page.page_flight_hours,
            remarks=("SL/MCM/1 page total; original per-leg oil levels retained. "
                     "APU oil excluded from engine rates. "
                     + ("Blank uplift is NOT checked zero. " if eng.observation == "MISSING" else "")
                     + ("Associated deferred defects: " + ", ".join(page.deferred_defect_references)
                        if page.deferred_defect_references else "")),
        ))
    return results


router = APIRouter()



class TechlogPageCorrection(BaseModel):
    aircraft_serial_number: str = Field(min_length=1, max_length=50)
    techsheet_ref: str = Field(min_length=1, max_length=160)
    replacement: TechlogPage
    reason: str = Field(min_length=8, max_length=2000)


def _source_page_rows(db, amo_id: str, aircraft: str, techsheet: str, lock: bool = False):
    query = db.query(octm.OCTMEntry).filter(
        octm.OCTMEntry.amo_id == amo_id,
        octm.OCTMEntry.aircraft_serial_number == aircraft,
        octm.OCTMEntry.techsheet_ref == techsheet,
        octm.OCTMEntry.source_scope == "TECHLOG_PAGE",
    ).order_by(octm.OCTMEntry.engine_position)
    return (query.with_for_update() if lock else query).all()


@router.get("/octm/techlog-pages/detail")
def detail_techlog_page(aircraft: str, techsheet_ref: str, ctx=Depends(octm.context)):
    octm.require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    rows = _source_page_rows(db, amo_id, aircraft, techsheet_ref)
    if not rows:
        raise HTTPException(404, "Original SL/MCM/1 technical-log page not found")
    reference = rows[0]
    page = reference.source_context or {}
    return TechlogPage(
        aircraft_serial_number=aircraft, techsheet_ref=techsheet_ref,
        event_date=reference.event_date, source_evidence_ref=reference.source_evidence_ref,
        source_type=reference.source_type,
        legs=[TechlogLeg(**leg) for leg in page.get("original_legs", [])],
        page_flight_hours=page.get("page_flight_hours"),
        ttaf_brought_forward=page.get("ttaf_brought_forward"),
        ttaf_updated=page.get("ttaf_updated"),
        tcsn_brought_forward=page.get("tcsn_brought_forward"),
        tcsn_updated=page.get("tcsn_updated"),
        maintenance_complete=reference.maintenance_complete,
        maintenance_release_ref=page.get("maintenance_release_ref"),
        check_24h_ref=page.get("check_24h_ref"),
        defect_references=page.get("defect_references", []),
        deferred_defect_references=page.get("deferred_defect_references", []),
        apu_oil_added=page.get("apu_oil_added"),
        apu_oil_unit=page.get("apu_oil_unit"),
        engines=[TechlogEngineOil(
            position=row.engine_position, engine_serial_number=row.engine_serial_number,
            installation_ref=row.installation_ref, observation=row.event_type,
            quantity_added=row.oil_quantity, original_unit=row.oil_unit,
            oil_specification=row.oil_specification,
            reference_method=row.reference_method, reference_level=row.reference_level,
        ) for row in rows],
    ).model_dump(mode="json")


@router.post("/octm/techlog-pages/correct")
def correct_techlog_page(payload: TechlogPageCorrection, ctx=Depends(octm.context)):
    db, amo_id, actor = ctx
    original = _source_page_rows(db, amo_id, payload.aircraft_serial_number,
                                 payload.techsheet_ref, lock=True)
    if not original:
        raise HTTPException(404, "Original SL/MCM/1 page not found")
    rights = access.capabilities_for_user(db, actor)
    resolver = "reliability.data_quality.resolve" in rights
    author_of_drafts = "reliability.ingest" in rights and all(
        row.review_status != "VERIFIED" and str(row.created_by_user_id) == str(actor.id)
        for row in original
    )
    if not (resolver or author_of_drafts):
        raise HTTPException(403, "Only an authorized reviewer or original entrant of draft records may correct the page")
    page = payload.replacement
    if (page.aircraft_serial_number != payload.aircraft_serial_number
            or page.techsheet_ref != payload.techsheet_ref):
        raise HTTPException(422, "Aircraft and page identity cannot be changed in-place")
    if not db.query(Aircraft).filter_by(serial_number=page.aircraft_serial_number, amo_id=amo_id).first():
        raise HTTPException(422, "Aircraft is not registered to this tenant")
    from .octm_source_assets import validate_source_reference
    validate_source_reference(db, amo_id, page.aircraft_serial_number, page.techsheet_ref,
                              page.source_evidence_ref)
    candidates = build_page_entries(page)
    by_position = {row.engine_position: row for row in original}
    if set(by_position) != {candidate.engine_position for candidate in candidates}:
        raise HTTPException(422, "Changing the number of engines requires supervised source supersession")
    modifications = []
    for candidate in candidates:
        row = by_position[candidate.engine_position]
        before = {field: getattr(row, field) for field in octm.EntryPayload.model_fields}
        after = candidate.model_dump()
        modifications.append((row, before, after))
    if not any(before != after for _, before, after in modifications):
        raise HTTPException(422, "The corrected page contains no changes")
    # Page is an indivisible document source: a change to one engine's
    # evidence invalidates BOTH engine verifications for this page.
    for row, before, after in modifications:
        for field, value in after.items():
            setattr(row, field, value)
        row.review_status = "DRAFT"
        row.reviewed_by_user_id = None
        row.reviewed_at = None
        row.review_note = "Source page amended. Independent verification required."
        row.last_changed_by_user_id = str(actor.id)
        db.add(octm.OCTMRevision(
            amo_id=amo_id, entry_id=row.id,
            before_json={key: value.isoformat() if isinstance(value, date) else value for key, value in before.items()},
            after_json={key: value.isoformat() if isinstance(value, date) else value for key, value in after.items()},
            reason=payload.reason, actor_user_id=str(actor.id),
        ))
        access.append_audit(
            db, amo_id=amo_id, entity_type="OCTM_ENTRY", entity_id=row.id,
            action="PAGE_SOURCE_CORRECTED", payload={"reason": payload.reason,
                "changed_fields": [key for key in after if before[key] != after[key]]},
            actor_user_id=str(actor.id),
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "A conflicting source entry prevents page correction") from exc
    return {"saved_entry_ids": [row.id for row in original], "review_status": "DRAFT",
            "note": "Page corrections preserved as revisions; all associated engine observations require re-review."}


@router.post("/octm/techlog-pages/preview")
def preview_techlog_page(payload: TechlogPage, ctx=Depends(octm.context)):
    octm.require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    if not db.query(Aircraft).filter_by(amo_id=amo_id, serial_number=payload.aircraft_serial_number).first():
        raise HTTPException(422, "Aircraft is not registered to this tenant")
    from .octm_source_assets import validate_source_reference
    validate_source_reference(db, amo_id, payload.aircraft_serial_number,
                              payload.techsheet_ref, payload.source_evidence_ref)
    candidates = build_page_entries(payload)
    return {
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "warnings": [
            "Original paper log records OIL ADDED by PAGE, not by flight sector. All source flight hours are treated as page totals.",
            "Engine serial, historical installation and reference-level method require independent checking before verification.",
            "Blank OIL ADDED is unrecorded, never assumed zero.",
            "APU oil is excluded from engine oil-consumption monitoring.",
            "This page capture does not create or certify a technical log or maintenance release.",
        ],
    }


@router.post("/octm/techlog-pages", status_code=201)
def create_techlog_page(payload: TechlogPage, ctx=Depends(octm.context)):
    octm.require(ctx, "reliability.ingest")
    db, amo_id, actor = ctx
    if not db.query(Aircraft).filter_by(amo_id=amo_id, serial_number=payload.aircraft_serial_number).first():
        raise HTTPException(422, "Aircraft is not registered to this tenant")
    from .octm_source_assets import validate_source_reference
    validate_source_reference(db, amo_id, payload.aircraft_serial_number,
                              payload.techsheet_ref, payload.source_evidence_ref)
    candidates = build_page_entries(payload)
    for candidate in candidates:
        original = db.query(octm.OCTMEntry).filter_by(
            amo_id=amo_id,
            aircraft_serial_number=candidate.aircraft_serial_number,
            techsheet_ref=candidate.techsheet_ref,
            engine_position=candidate.engine_position,
            event_sequence=candidate.event_sequence,
        ).first()
        if original:
            raise HTTPException(409, "A record already exists for this technical-log page and engine. Use the controlled correction workflow.")
    records = []
    try:
        for candidate in candidates:
            row = octm.OCTMEntry(
                **candidate.model_dump(), amo_id=amo_id, review_status="DRAFT",
                created_by_user_id=str(actor.id), last_changed_by_user_id=str(actor.id),
            )
            db.add(row)
            db.flush()
            access.append_audit(db, amo_id=amo_id, entity_type="OCTM_ENTRY",
                                entity_id=row.id, action="PAGE_SOURCE_REGISTERED",
                                payload={"techsheet": row.techsheet_ref, "position": row.engine_position,
                                         "source_scope": "TECHLOG_PAGE"},
                                actor_user_id=str(actor.id))
            records.append(row)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Conflicting page/engine source entry was created concurrently") from exc
    return {
        "saved_entry_ids": [row.id for row in records],
        "review_status": "DRAFT",
        "source_scope": "TECHLOG_PAGE",
        "note": "Source page entered; independent verification required before monitoring.",
    }
