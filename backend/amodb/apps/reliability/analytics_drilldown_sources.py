from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from . import advanced_models, models
from .analytics_common import _bucket_for_window, _bucket_key, _end, _enum_value, _start
from .analytics_drilldown_context import DrilldownContext
from .analytics_types import DrilldownRecord, DrilldownResponse


def _values(ctx: DrilldownContext):
    return (
        ctx.dimension,
        ctx.key,
        ctx.period_start,
        ctx.period_end,
        ctx.bucket,
        ctx.limit,
        ctx.offset,
        ctx.db,
        ctx.amo_id,
        ctx.selected_aircraft,
        ctx.selected_ata,
        ctx.selected_stations,
        ctx.selected_types,
        ctx.selected_severities,
        ctx.selected_sources,
    )


def drilldown_sources(ctx: DrilldownContext) -> DrilldownResponse | None:
    (
        dimension,
        key,
        period_start,
        period_end,
        bucket,
        limit,
        offset,
        db,
        amo_id,
        selected_aircraft,
        _selected_ata,
        _selected_stations,
        _selected_types,
        _selected_severities,
        _selected_sources,
    ) = _values(ctx)

    if dimension == "component_age":
        query = db.query(models.RemovalEvent).filter(
            models.RemovalEvent.amo_id == amo_id,
            models.RemovalEvent.removed_at >= _start(period_start),
            models.RemovalEvent.removed_at <= _end(period_end),
        )
        if selected_aircraft:
            query = query.filter(models.RemovalEvent.aircraft_serial_number.in_(selected_aircraft))
        rows = []
        for row in query.order_by(models.RemovalEvent.removed_at.desc()).all():
            if row.hours_at_removal is None:
                bucket_key = "UNKNOWN"
            else:
                hours = float(row.hours_at_removal)
                bucket_key = (
                    "UNDER_100_FH" if hours < 100 else
                    "100_499_FH" if hours < 500 else
                    "500_999_FH" if hours < 1000 else
                    "1000_2999_FH" if hours < 3000 else
                    "3000_PLUS_FH"
                )
            if bucket_key == key:
                rows.append(row)
        total = len(rows)
        records = [
            DrilldownRecord(
                id=str(row.id),
                record_type="REMOVAL_EVENT",
                occurred_at=row.removed_at,
                aircraft_serial_number=row.aircraft_serial_number,
                reference=row.removal_tracking_id,
                category=row.removal_reason,
                status=row.event_type,
                summary=row.removal_reason or "Component removal",
                route="components",
                details={
                    "component_id": row.component_id,
                    "component_instance_id": row.component_instance_id,
                    "hours_at_removal": float(row.hours_at_removal) if row.hours_at_removal is not None else None,
                    "cycles_at_removal": float(row.cycles_at_removal) if row.cycles_at_removal is not None else None,
                },
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    if dimension == "shop_visit_period":
        actual_bucket = _bucket_for_window(period_start, period_end, bucket)
        query = db.query(models.ShopVisit).filter(
            models.ShopVisit.amo_id == amo_id,
            models.ShopVisit.created_at >= _start(period_start),
            models.ShopVisit.created_at <= _end(period_end),
        )
        rows = [
            row
            for row in query.order_by(models.ShopVisit.created_at.desc()).all()
            if _bucket_key(row.created_at.date(), actual_bucket)[0] == key
        ]
        total = len(rows)
        records = [
            DrilldownRecord(
                id=str(row.id),
                record_type="SHOP_VISIT",
                occurred_at=row.created_at,
                reference=row.shop_record_id,
                category="SHOP_VISIT",
                status="RECORDED",
                summary=row.notes or "Component shop visit",
                route="components",
                details={
                    "component_instance_id": row.component_instance_id,
                    "work_order_id": row.work_order_id,
                },
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    if dimension == "oil_consumption":
        try:
            aircraft_serial, engine_position = key.split("|", 1)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Oil-consumption key is invalid.") from exc
        query = db.query(models.OilConsumptionRate).filter(
            models.OilConsumptionRate.amo_id == amo_id,
            models.OilConsumptionRate.aircraft_serial_number == aircraft_serial,
            models.OilConsumptionRate.window_end >= period_start,
            models.OilConsumptionRate.window_start <= period_end,
        )
        if engine_position == "UNALLOCATED":
            query = query.filter(models.OilConsumptionRate.engine_position.is_(None))
        else:
            query = query.filter(models.OilConsumptionRate.engine_position == engine_position)
        rows = query.order_by(models.OilConsumptionRate.window_end.desc()).all()
        total = len(rows)
        records = [
            DrilldownRecord(
                id=str(row.id),
                record_type="OIL_CONSUMPTION_RATE",
                occurred_at=row.window_end,
                aircraft_serial_number=row.aircraft_serial_number,
                reference=row.engine_position,
                category="OIL_CONSUMPTION",
                status="CALCULATED",
                summary=(
                    f"{float(row.rate_qt_per_hour):g} qt/FH"
                    if row.rate_qt_per_hour is not None
                    else "Rate unavailable"
                ),
                route="engines",
                details={
                    "window_start": row.window_start.isoformat(),
                    "window_end": row.window_end.isoformat(),
                    "oil_used_quarts": float(row.oil_used_quarts),
                    "flight_hours": float(row.flight_hours) if row.flight_hours is not None else None,
                    "rate_qt_per_hour": float(row.rate_qt_per_hour) if row.rate_qt_per_hour is not None else None,
                },
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    if dimension == "source":
        source = (
            db.query(advanced_models.ReliabilitySource)
            .filter(
                advanced_models.ReliabilitySource.amo_id == amo_id,
                advanced_models.ReliabilitySource.code == key,
            )
            .first()
        )
        if not source:
            return DrilldownResponse(
                dimension=dimension,
                key=key,
                total=0,
                limit=limit,
                offset=offset,
                records=[],
            )
        query = (
            db.query(advanced_models.ReliabilityIngestionBatch)
            .filter(
                advanced_models.ReliabilityIngestionBatch.amo_id == amo_id,
                advanced_models.ReliabilityIngestionBatch.source_id == source.id,
                advanced_models.ReliabilityIngestionBatch.received_at >= _start(period_start),
                advanced_models.ReliabilityIngestionBatch.received_at <= _end(period_end),
            )
            .order_by(advanced_models.ReliabilityIngestionBatch.received_at.desc())
        )
        rows = query.all()
        total = len(rows)
        records = [
            DrilldownRecord(
                id=row.id,
                record_type="INGESTION_BATCH",
                occurred_at=row.received_at,
                reference=source.code,
                category=source.source_type,
                status=row.status,
                summary=(
                    row.error_summary
                    or f"{row.record_count} received; {row.valid_count} valid; {row.invalid_count} invalid"
                ),
                route="ingestion",
                details={
                    "source_name": source.name,
                    "record_count": row.record_count,
                    "valid_count": row.valid_count,
                    "duplicate_count": row.duplicate_count,
                    "invalid_count": row.invalid_count,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                },
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    if dimension == "engine_reading":
        try:
            metric, raw_date = key.split("::", 1)
            reading_date = date.fromisoformat(raw_date)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Engine reading key must contain a metric and ISO date.",
            ) from exc
        query = db.query(models.EngineFlightSnapshot).filter(
            models.EngineFlightSnapshot.amo_id == amo_id,
            models.EngineFlightSnapshot.flight_date == reading_date,
        )
        if selected_aircraft:
            query = query.filter(models.EngineFlightSnapshot.aircraft_serial_number.in_(selected_aircraft))
        rows = []
        for row in query.all():
            value = (row.metrics or {}).get(metric)
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                rows.append((row, float(value)))
        total = len(rows)
        records = [
            DrilldownRecord(
                id=str(row.id),
                record_type="ENGINE_FLIGHT_SNAPSHOT",
                occurred_at=row.flight_date,
                aircraft_serial_number=row.aircraft_serial_number,
                reference=row.engine_serial_number or row.source_record_id,
                category=row.engine_position,
                status="MEASURED",
                summary=f"{metric}: {value:g}",
                route="engines",
                details={
                    "metric": metric,
                    "value": value,
                    "flight_leg": row.flight_leg,
                    "phase": row.phase,
                    "data_source": row.data_source,
                    "source_record_id": row.source_record_id,
                },
            )
            for row, value in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    if dimension == "engine_status":
        query = db.query(models.EngineTrendStatus).filter(models.EngineTrendStatus.amo_id == amo_id)
        if selected_aircraft:
            query = query.filter(models.EngineTrendStatus.aircraft_serial_number.in_(selected_aircraft))
        rows = [
            row
            for row in query.all()
            if (_enum_value(row.current_status) or "NOT_EVALUATED") == key
        ]
        total = len(rows)
        records = [
            DrilldownRecord(
                id=str(row.id),
                record_type="ENGINE_TREND_STATUS",
                occurred_at=row.last_trend_date,
                aircraft_serial_number=row.aircraft_serial_number,
                reference=row.engine_serial_number,
                category=row.engine_position,
                status=_enum_value(row.current_status) or "NOT_EVALUATED",
                summary=f"{row.aircraft_serial_number} {row.engine_position}",
                route="engines",
                details={
                    "last_upload_date": str(row.last_upload_date or ""),
                    "last_review_date": str(row.last_review_date or ""),
                },
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    if dimension == "data_quality":
        query = db.query(advanced_models.ReliabilityDataQualityIssue).filter(
            advanced_models.ReliabilityDataQualityIssue.amo_id == amo_id
        )
        if key == "OPEN":
            rows = [row for row in query.all() if row.status not in {"RESOLVED", "CLOSED"}]
        else:
            rows = query.filter(
                advanced_models.ReliabilityDataQualityIssue.issue_code == key
            ).all()
        total = len(rows)
        records = [
            DrilldownRecord(
                id=row.id,
                record_type="DATA_QUALITY_ISSUE",
                occurred_at=row.created_at,
                reference=row.issue_code,
                category=row.issue_code,
                status=row.status,
                severity=row.severity,
                summary=row.message,
                route="data-quality",
                details=row.details_json or {},
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(
            dimension=dimension,
            key=key,
            total=total,
            limit=limit,
            offset=offset,
            records=records,
        )

    return None
