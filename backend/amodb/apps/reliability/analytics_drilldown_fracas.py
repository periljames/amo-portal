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

def drilldown_fracas(ctx: DrilldownContext) -> DrilldownResponse | None:
    (dimension, key, period_start, period_end, bucket, limit, offset, db, amo_id, selected_aircraft,
     selected_ata, selected_stations, selected_types, selected_severities, selected_sources) = _values(ctx)
    if dimension in {"fracas_stage", "fracas_age", "root_cause"}:
        cases = db.query(models.FRACASCase).filter(
            models.FRACASCase.amo_id == amo_id,
            models.FRACASCase.opened_at <= _end(period_end),
            or_(models.FRACASCase.closed_at.is_(None), models.FRACASCase.closed_at >= _start(period_start)),
        ).all()
        case_ids = [row.id for row in cases]
        lifecycles = db.query(advanced_models.ReliabilityFracasLifecycle).filter(
            advanced_models.ReliabilityFracasLifecycle.amo_id == amo_id,
            advanced_models.ReliabilityFracasLifecycle.fracas_case_id.in_(case_ids),
        ).all() if case_ids else []
        lifecycle_by_case = {row.fracas_case_id: row for row in lifecycles}
        now = datetime.now(UTC)
        selected_cases = []
        for case in cases:
            lifecycle = lifecycle_by_case.get(case.id)
            if dimension == "fracas_stage":
                if key == "OPEN":
                    if _enum_value(case.status) == "CLOSED":
                        continue
                elif key == "OVERDUE_ACTIONS":
                    has_overdue = any(action.status not in CLOSED_ACTION_STATES and action.due_date and action.due_date < now.date() for action in case.actions)
                    if not has_overdue:
                        continue
                elif (lifecycle.stage if lifecycle else _enum_value(case.status)) != key:
                    continue
            elif dimension == "fracas_age":
                opened = case.opened_at if case.opened_at.tzinfo else case.opened_at.replace(tzinfo=UTC)
                age = max((now - opened).days, 0)
                age_key = "0_30_DAYS" if age <= 30 else "31_60_DAYS" if age <= 60 else "61_90_DAYS" if age <= 90 else "OVER_90_DAYS"
                if age_key != key:
                    continue
            else:
                root = (case.root_cause or "").strip()
                if not root and lifecycle:
                    payload = lifecycle.root_cause_json or {}
                    root = str(payload.get("category") or payload.get("root_cause") or "").strip()
                if (root or "UNCLASSIFIED") != key:
                    continue
            selected_cases.append(case)
        total = len(selected_cases)
        records = [
            DrilldownRecord(
                id=str(case.id),
                record_type="FRACAS_CASE",
                occurred_at=case.opened_at,
                aircraft_serial_number=case.aircraft_serial_number,
                reference=str(case.id),
                category=case.classification,
                status=_enum_value(case.status),
                severity=_enum_value(case.severity) or None,
                summary=case.title,
                route=f"cases/{case.id}",
                details={"root_cause": case.root_cause, "closed_at": case.closed_at.isoformat() if case.closed_at else None},
            )
            for case in selected_cases[offset: offset + limit]
        ]
        return DrilldownResponse(dimension=dimension, key=key, total=total, limit=limit, offset=offset, records=records)

    if dimension in {"fracas_action_status", "fracas_action_period"}:
        cases = db.query(models.FRACASCase).filter(
            models.FRACASCase.amo_id == amo_id,
            models.FRACASCase.opened_at <= _end(period_end),
            or_(models.FRACASCase.closed_at.is_(None), models.FRACASCase.closed_at >= _start(period_start)),
        ).all()
        case_ids = [case.id for case in cases]
        query = db.query(models.FRACASAction).filter(models.FRACASAction.fracas_case_id.in_(case_ids)) if case_ids else None
        rows = query.all() if query is not None else []
        actual_bucket = _bucket_for_window(period_start, period_end, bucket)
        selected_rows = []
        for row in rows:
            row_status = _enum_value(row.status)
            if dimension == "fracas_action_status":
                if key == "OVERDUE":
                    if row_status in CLOSED_ACTION_STATES or not row.due_date or row.due_date >= datetime.now(UTC).date():
                        continue
                elif key == "COMPLETED":
                    if row_status not in {"DONE", "VERIFIED"}:
                        continue
                elif row_status != key:
                    continue
            else:
                dates = [value for value in (_normalise_date(row.created_at), _normalise_date(row.completed_at), row.due_date) if value]
                if not any(_bucket_key(value, actual_bucket)[0] == key for value in dates):
                    continue
            selected_rows.append(row)
        total = len(selected_rows)
        records = [
            DrilldownRecord(
                id=str(row.id),
                record_type="FRACAS_ACTION",
                occurred_at=row.completed_at or row.created_at,
                reference=str(row.fracas_case_id),
                category=_enum_value(row.action_type),
                status=_enum_value(row.status),
                summary=row.description,
                route=f"cases/{row.fracas_case_id}",
                details={
                    "owner_user_id": row.owner_user_id,
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "verified_at": row.verified_at.isoformat() if row.verified_at else None,
                },
            )
            for row in selected_rows[offset: offset + limit]
        ]
        return DrilldownResponse(dimension=dimension, key=key, total=total, limit=limit, offset=offset, records=records)

    if dimension == "fracas_reopened":
        query = db.query(advanced_models.ReliabilityFracasLifecycle).filter(
            advanced_models.ReliabilityFracasLifecycle.amo_id == amo_id
        )
        rows = []
        for row in query.all():
            count = int(row.reopened_count or 0)
            category = "NEVER" if count == 0 else "ONCE" if count == 1 else "MULTIPLE"
            if category == key:
                rows.append(row)
        total = len(rows)
        records = [
            DrilldownRecord(
                id=row.id,
                record_type="FRACAS_LIFECYCLE",
                occurred_at=row.updated_at,
                reference=str(row.fracas_case_id),
                category=key,
                status=row.stage,
                summary=f"FRACAS case {row.fracas_case_id} reopened {row.reopened_count or 0} time(s)",
                route=f"cases/{row.fracas_case_id}",
                details={"reopened_count": row.reopened_count, "stage_entered_at": row.stage_entered_at.isoformat()},
            )
            for row in rows[offset: offset + limit]
        ]
        return DrilldownResponse(dimension=dimension, key=key, total=total, limit=limit, offset=offset, records=records)

    if dimension == "effectiveness":
        query = db.query(advanced_models.ReliabilityEffectivenessReview).filter(
            advanced_models.ReliabilityEffectivenessReview.amo_id == amo_id,
            advanced_models.ReliabilityEffectivenessReview.review_date >= period_start,
            advanced_models.ReliabilityEffectivenessReview.review_date <= period_end,
        )
        all_reviews = query.all()
        successful_outcomes = {"PASS", "PASSED", "EFFECTIVE", "SUCCESSFUL"}
        if key == "SUCCESSFUL":
            rows = [row for row in all_reviews if row.approved_at is not None and (row.outcome or "").upper() in successful_outcomes]
        else:
            rows = [row for row in all_reviews if (row.outcome or "UNASSESSED").upper() == key]
        lifecycle_ids = [row.lifecycle_id for row in rows]
        lifecycles = (
            db.query(advanced_models.ReliabilityFracasLifecycle)
            .filter(
                advanced_models.ReliabilityFracasLifecycle.amo_id == amo_id,
                advanced_models.ReliabilityFracasLifecycle.id.in_(lifecycle_ids),
            )
            .all()
            if lifecycle_ids
            else []
        )
        lifecycle_by_id = {row.id: row for row in lifecycles}
        total = len(rows)
        records = []
        for row in rows[offset: offset + limit]:
            lifecycle = lifecycle_by_id.get(row.lifecycle_id)
            case_id = lifecycle.fracas_case_id if lifecycle else None
            records.append(
                DrilldownRecord(
                    id=row.id,
                    record_type="EFFECTIVENESS_REVIEW",
                    occurred_at=row.review_date,
                    reference=str(case_id) if case_id is not None else row.lifecycle_id,
                    category=(row.outcome or "UNASSESSED").upper(),
                    status="APPROVED" if row.approved_at else "PENDING_APPROVAL",
                    summary=row.acceptance_criteria,
                    route=f"cases/{case_id}" if case_id is not None else "cases",
                    details={
                        "metric_code": row.metric_code,
                        "baseline_value": str(row.baseline_value) if row.baseline_value is not None else None,
                        "current_value": str(row.current_value) if row.current_value is not None else None,
                        "notes": row.notes,
                    },
                )
            )
        return DrilldownResponse(dimension=dimension, key=key, total=total, limit=limit, offset=offset, records=records)

    return None
