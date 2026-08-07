from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from collections import Counter

from sqlalchemy import or_

from . import advanced_models, models, operational_sources
from .analytics_common import (
    CLOSED_ACTION_STATES, DISPATCH_EVENT_TYPES, OPEN_DEFERRAL_STATES, UTC,
    _bucket_for_window, _bucket_key, _end, _enum_value, _load_events,
    _normalise_date, _start,
)
from .analytics_drilldown_context import DrilldownContext, _event_drilldown_records
from .analytics_types import DrilldownRecord, DrilldownResponse

def _values(ctx: DrilldownContext):
    return (ctx.dimension, ctx.key, ctx.period_start, ctx.period_end, ctx.bucket, ctx.limit, ctx.offset,
            ctx.db, ctx.amo_id, ctx.selected_aircraft, ctx.selected_ata, ctx.selected_stations,
            ctx.selected_types, ctx.selected_severities, ctx.selected_sources)

def drilldown_events(ctx: DrilldownContext) -> DrilldownResponse | None:
    (dimension, key, period_start, period_end, bucket, limit, offset, db, amo_id, selected_aircraft,
     selected_ata, selected_stations, selected_types, selected_severities, selected_sources) = _values(ctx)
    if dimension in {"period", "event_type", "ata", "aircraft", "station", "route", "component"}:
        rows = _load_events(
            db,
            amo_id=amo_id,
            period_start=period_start,
            period_end=period_end,
            aircraft=selected_aircraft,
            ata_chapters=selected_ata,
            stations=selected_stations,
            event_types=selected_types,
            severities=selected_severities,
            source_systems=selected_sources,
        )
        selected: list[models.ReliabilityEvent] = []
        actual_bucket = _bucket_for_window(period_start, period_end, bucket)
        for row in rows:
            if dimension == "period":
                occurred = _normalise_date(row.occurred_at)
                if key != "ALL" and (not occurred or _bucket_key(occurred, actual_bucket)[0] != key):
                    continue
            elif dimension == "event_type":
                if key == "DISPATCH_INTERRUPTIONS":
                    if _enum_value(row.event_type) not in DISPATCH_EVENT_TYPES:
                        continue
                elif _enum_value(row.event_type) != key:
                    continue
            elif dimension == "ata" and (row.ata_chapter or "UNALLOCATED") != key:
                continue
            elif dimension == "aircraft" and (row.aircraft_serial_number or "FLEET/UNALLOCATED") != key:
                continue
            elif dimension == "station" and (row.origin_station or "UNALLOCATED") != key:
                continue
            elif dimension == "route":
                route_key = f"{row.origin_station or 'UNALLOCATED'}|{row.destination_station or 'UNALLOCATED'}"
                if route_key != key:
                    continue
            elif dimension == "component" and (row.part_number or "UNALLOCATED") != key:
                continue
            selected.append(row)
        total = len(selected)
        records = _event_drilldown_records(selected[offset: offset + limit])
        return DrilldownResponse(dimension=dimension, key=key, total=total, limit=limit, offset=offset, records=records)

    return None
