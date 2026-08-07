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

def drilldown_deferrals(ctx: DrilldownContext) -> DrilldownResponse | None:
    (dimension, key, period_start, period_end, bucket, limit, offset, db, amo_id, selected_aircraft,
     selected_ata, selected_stations, selected_types, selected_severities, selected_sources) = _values(ctx)
    if dimension in {"deferral_status", "deferral_expiry", "deferral_category", "deferral_extension", "deferral_repeat", "deferral_closure"}:
        query = db.query(operational_sources.ReliabilityMelCdlDeferral).filter(
            operational_sources.ReliabilityMelCdlDeferral.amo_id == amo_id,
            operational_sources.ReliabilityMelCdlDeferral.applied_at <= _end(period_end),
        )
        if selected_aircraft:
            query = query.filter(operational_sources.ReliabilityMelCdlDeferral.aircraft_serial_number.in_(selected_aircraft))
        if selected_ata:
            query = query.filter(operational_sources.ReliabilityMelCdlDeferral.ata_chapter.in_(selected_ata))
        rows = query.order_by(operational_sources.ReliabilityMelCdlDeferral.expires_at.asc()).all()
        now = datetime.now(UTC)
        selected_rows = []
        repeat_counts = Counter(
            (row.aircraft_serial_number or "UNALLOCATED", row.item_reference or "UNALLOCATED", row.ata_chapter or "UNALLOCATED")
            for row in rows
        )
        for row in rows:
            if dimension == "deferral_status":
                if key == "OPEN" and row.status not in OPEN_DEFERRAL_STATES:
                    continue
                if key == "OVERDUE" and not (row.status in OPEN_DEFERRAL_STATES and row.expires_at and row.expires_at < now):
                    continue
                if key not in {"OPEN", "OVERDUE"} and row.status != key:
                    continue
            elif dimension == "deferral_expiry":
                if row.status not in OPEN_DEFERRAL_STATES or not row.expires_at:
                    continue
                delta = (row.expires_at.date() - now.date()).days
                bucket_key = "OVERDUE" if delta < 0 else "0_7_DAYS" if delta <= 7 else "8_14_DAYS" if delta <= 14 else "15_30_DAYS" if delta <= 30 else "OVER_30_DAYS"
                if bucket_key != key:
                    continue
            elif dimension == "deferral_category":
                if row.status not in OPEN_DEFERRAL_STATES or (row.category or "UNCLASSIFIED").upper() != key:
                    continue
            elif dimension == "deferral_extension":
                reasons = [
                    str(item.get("reason") or "UNCLASSIFIED").strip() or "UNCLASSIFIED"
                    for item in list(row.extension_history_json or [])
                    if isinstance(item, dict)
                ]
                if key == "ALL":
                    if not reasons:
                        continue
                elif key not in reasons:
                    continue
            elif dimension == "deferral_repeat":
                group = (row.aircraft_serial_number or "UNALLOCATED", row.item_reference or "UNALLOCATED", row.ata_chapter or "UNALLOCATED")
                if repeat_counts[group] <= 1:
                    continue
                if key != "ALL" and "|".join(group) != key:
                    continue
            elif dimension == "deferral_closure":
                if not row.closed_at:
                    continue
                if key != "ALL" and (row.category or "UNCLASSIFIED").upper() != key:
                    continue
            selected_rows.append(row)
        total = len(selected_rows)
        records = [
            DrilldownRecord(
                id=row.id,
                record_type="MEL_CDL_DEFERRAL",
                occurred_at=row.applied_at,
                aircraft_serial_number=row.aircraft_serial_number,
                reference=row.deferral_number,
                category=row.deferral_type,
                status=row.status,
                severity=row.severity,
                ata_chapter=row.ata_chapter,
                summary=row.description,
                route="operations",
                details={
                    "expires_at": row.expires_at.isoformat(),
                    "item_reference": row.item_reference,
                    "category": row.category,
                    "extension_history": row.extension_history_json or [],
                    "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                    "closure_days": round((row.closed_at - row.applied_at).total_seconds() / 86400, 2) if row.closed_at and row.applied_at else None,
                },
            )
            for row in selected_rows[offset: offset + limit]
        ]
        return DrilldownResponse(dimension=dimension, key=key, total=total, limit=limit, offset=offset, records=records)

    return None
