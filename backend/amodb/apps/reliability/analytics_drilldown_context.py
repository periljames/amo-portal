from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from . import models
from .analytics_common import _enum_value
from .analytics_types import DrilldownRecord

@dataclass(frozen=True)
class DrilldownContext:
    dimension: str
    key: str
    period_start: date
    period_end: date
    bucket: str
    limit: int
    offset: int
    db: Session
    amo_id: str
    selected_aircraft: set[str]
    selected_ata: set[str]
    selected_stations: set[str]
    selected_types: set[str]
    selected_severities: set[str]
    selected_sources: set[str]

def _event_drilldown_records(rows: list[models.ReliabilityEvent]) -> list[DrilldownRecord]:
    return [
        DrilldownRecord(
            id=str(row.id), record_type="RELIABILITY_EVENT", occurred_at=row.occurred_at,
            aircraft_serial_number=row.aircraft_serial_number, reference=row.reference_code or row.source_record_id,
            category=_enum_value(row.event_type), status=row.validation_status,
            severity=_enum_value(row.severity) or None, ata_chapter=row.ata_chapter,
            summary=row.description or "No description recorded", route=f"events/{row.id}",
            details={
                "flight_number": row.flight_number, "origin_station": row.origin_station,
                "destination_station": row.destination_station, "delay_minutes": row.delay_minutes,
                "part_number": row.part_number, "component_serial_number": row.component_serial_number,
                "source_system": row.source_system,
            },
        )
        for row in rows
    ]
