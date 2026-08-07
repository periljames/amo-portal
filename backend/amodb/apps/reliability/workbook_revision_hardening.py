"""Governed correction workflow for immutable Reliability workbook records."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from . import workbook_parity as wp


class SupersedeRequest(BaseModel):
    rationale: str = Field(min_length=2, max_length=2000)
    replacement: dict[str, Any]


def register(router: APIRouter) -> None:
    @router.post("/workbook-parity/records/{record_id}/supersede", status_code=201)
    def supersede_record(
        record_id: int,
        request: SupersedeRequest,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = wp._amo_id(current_user)
        source = (
            db.query(wp.ReliabilityWorkbookRecord)
            .filter(
                wp.ReliabilityWorkbookRecord.id == record_id,
                wp.ReliabilityWorkbookRecord.amo_id == amo_id,
            )
            .one_or_none()
        )
        if source is None:
            raise HTTPException(status_code=404, detail="Workbook record not found.")
        if source.status not in {wp.WorkbookRecordStatus.APPROVED.value, wp.WorkbookRecordStatus.CLOSED.value}:
            raise HTTPException(status_code=409, detail="Only approved or closed records can be superseded.")

        replacement = wp.WorkbookRecordCreate.model_validate(request.replacement)
        if replacement.dataset_code.value != source.dataset_code:
            raise HTTPException(status_code=422, detail="A superseding revision must remain in the same workbook dataset.")
        wp._validate_aircraft(db, amo_id, replacement.aircraft_serial_number)
        if replacement.dataset_code != wp.WorkbookDatasetCode.AI and not replacement.aircraft_serial_number:
            raise HTTPException(status_code=422, detail="Aircraft is required for this workbook dataset.")

        definition = wp.DATASET_CATALOG[replacement.dataset_code]
        normalised, derived = wp._normalise_payload(definition, replacement.payload)
        max_revision = (
            db.query(func.max(wp.ReliabilityWorkbookRecord.revision))
            .filter(
                wp.ReliabilityWorkbookRecord.amo_id == amo_id,
                wp.ReliabilityWorkbookRecord.dataset_code == source.dataset_code,
                wp.ReliabilityWorkbookRecord.record_number == source.record_number,
            )
            .scalar()
            or source.revision
        )
        revision = int(max_revision) + 1
        derived = {
            **derived,
            "supersedes_record_id": source.id,
            "supersedes_revision": source.revision,
            "supersession_rationale": request.rationale.strip(),
        }
        serialised = {
            "dataset_code": source.dataset_code,
            "record_number": source.record_number,
            "revision": revision,
            "event_date": replacement.event_date.isoformat(),
            "aircraft": replacement.aircraft_serial_number,
            "payload": normalised,
            "supersedes_record_id": source.id,
        }
        row = wp.ReliabilityWorkbookRecord(
            amo_id=amo_id,
            dataset_code=source.dataset_code,
            record_number=source.record_number,
            revision=revision,
            status=wp.WorkbookRecordStatus.DRAFT.value,
            event_date=replacement.event_date,
            event_end_date=replacement.event_end_date,
            aircraft_serial_number=replacement.aircraft_serial_number,
            ata_chapter=replacement.ata_chapter,
            reference_code=replacement.reference_code,
            title=replacement.title,
            description=replacement.description,
            payload=normalised,
            derived_values=derived,
            source_workbook=replacement.source_workbook,
            source_sheet=replacement.source_sheet,
            source_row_number=replacement.source_row_number,
            source_hash=hashlib.sha256(json.dumps(serialised, sort_keys=True).encode()).hexdigest(),
            created_by_user_id=current_user.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return wp.WorkbookRecordRead.model_validate(row).model_dump(mode="json")
