from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any
import time
import uuid

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .canonical_router import (
    _pg_set_read_timeout,
    _recover_qms_read_session,
    _table_columns,
    qms_calendar,
    qms_dashboard_lite,
    qms_inbox,
    router as canonical_router,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


DASHBOARD_V2_CONTRACT = "qms-operational-dashboard.v2"


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _safe_rows(
    db: Session,
    *,
    sql: str,
    params: dict[str, Any],
    label: str,
    ctx: TenantContext,
    source_errors: list[dict[str, Any]],
    timeout_ms: int = 1800,
) -> list[dict[str, Any]]:
    try:
        _pg_set_read_timeout(db, timeout_ms)
        return [dict(row) for row in db.execute(text(sql), params).mappings().all()]
    except Exception as exc:
        source_errors.append({"label": label, "message": str(exc), "type": exc.__class__.__name__})
        _recover_qms_read_session(db, amo_id=ctx.amo_id, user_id=ctx.user_id, timeout_ms=timeout_ms)
        return []


def _safe_scalar(
    db: Session,
    *,
    sql: str,
    params: dict[str, Any],
    label: str,
    ctx: TenantContext,
    source_errors: list[dict[str, Any]],
    timeout_ms: int = 1800,
) -> int | None:
    rows = _safe_rows(
        db,
        sql=sql,
        params=params,
        label=label,
        ctx=ctx,
        source_errors=source_errors,
        timeout_ms=timeout_ms,
    )
    if not rows:
        return None
    value = next(iter(rows[0].values()), None)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return None


def _pct(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def _direction(current: float | None, previous: float | None, *, lower_is_better: bool) -> str:
    if current is None or previous is None:
        return "not_available"
    if current == previous:
        return "flat"
    improved = current < previous if lower_is_better else current > previous
    return "improving" if improved else "deteriorating"


def _owner_summary(total: int, unassigned: int | None) -> str:
    if total <= 0:
        return "none"
    if unassigned is None:
        return "not_available"
    if unassigned <= 0:
        return "assigned"
    if unassigned >= total:
        return "unassigned"
    return "partially_assigned"


def _age_days(value: Any, today: date) -> int | None:
    parsed = _as_date(value)
    if not parsed:
        return None
    return max(0, (today - parsed).days)


def _build_action_queue(
    *,
    amo_code: str,
    counters: dict[str, int],
    oldest_car_age: int | None,
    car_unassigned: int | None,
    oldest_training_age: int | None,
    finding_unassigned: int | None,
) -> list[dict[str, Any]]:
    base = f"/maintenance/{amo_code}/quality"
    definitions = [
        {
            "id": "overdue-cars",
            "label": "Overdue CARs",
            "count": int(counters.get("overdue_cars", 0)),
            "oldest_age_days": oldest_car_age,
            "owner_status": _owner_summary(int(counters.get("overdue_cars", 0)), car_unassigned),
            "next_action": "Review overdue corrective actions",
            "route": f"{base}/cars/overdue",
            "tone": "danger",
            "priority": 100,
            "regulatory_consequence": "corrective_action_overdue",
        },
        {
            "id": "expired-training",
            "label": "Expired training",
            "count": int(counters.get("training_expired_records", 0)),
            "oldest_age_days": oldest_training_age,
            "owner_status": "department_owner",
            "next_action": "Confirm competence restrictions and renewal plan",
            "route": f"/maintenance/{amo_code}/training/competence/overdue",
            "tone": "danger",
            "priority": 95,
            "regulatory_consequence": "competence_expired",
        },
        {
            "id": "cars-due-soon",
            "label": "CARs due within 30 days",
            "count": int(counters.get("cars_due_soon", 0)),
            "oldest_age_days": None,
            "owner_status": "mixed",
            "next_action": "Intervene before the approved due date",
            "route": f"{base}/cars/due-soon",
            "tone": "warning",
            "priority": 80,
            "regulatory_consequence": "corrective_action_at_risk",
        },
        {
            "id": "audits-due-soon",
            "label": "Audits due within 30 days",
            "count": int(counters.get("audits_due_soon", 0)),
            "oldest_age_days": None,
            "owner_status": "audit_programme",
            "next_action": "Confirm scope, team, notice, and preparation",
            "route": f"{base}/audits/schedule",
            "tone": "warning",
            "priority": 75,
            "regulatory_consequence": "assurance_commitment_due",
        },
        {
            "id": "open-findings",
            "label": "Open findings",
            "count": int(counters.get("open_findings", 0)),
            "oldest_age_days": None,
            "owner_status": _owner_summary(int(counters.get("open_findings", 0)), finding_unassigned),
            "next_action": "Confirm classification, ownership, and linked CAR",
            "route": f"{base}/findings/register",
            "tone": "warning",
            "priority": 60,
            "regulatory_consequence": "finding_open",
        },
    ]
    return sorted(
        (item for item in definitions if item["count"] > 0),
        key=lambda item: (-int(item["priority"]), -int(item["count"]), str(item["label"])),
    )[:5]


def _car_operational_stats(
    db: Session,
    *,
    ctx: TenantContext,
    today: date,
    source_errors: list[dict[str, Any]],
) -> tuple[int | None, int | None, dict[str, int]]:
    columns = _table_columns(db, "quality_cars")
    owner_column = "assigned_to_user_id" if "assigned_to_user_id" in columns else "owner_user_id" if "owner_user_id" in columns else None
    selected_owner = f", {owner_column} AS owner_id" if owner_column else ""
    rows = _safe_rows(
        db,
        sql=f"""
            SELECT due_date {selected_owner}
            FROM quality_cars
            WHERE amo_id = :amo_id
              AND due_date IS NOT NULL
              AND due_date < :today
              AND COALESCE(status, 'DRAFT') NOT IN ('CLOSED', 'CANCELLED')
            ORDER BY due_date ASC
            LIMIT 5000
        """,
        params={"amo_id": ctx.amo_id, "today": today},
        label="dashboard_v2_overdue_car_detail",
        ctx=ctx,
        source_errors=source_errors,
    )
    ages = [age for age in (_age_days(row.get("due_date"), today) for row in rows) if age is not None]
    buckets = {"1_7": 0, "8_30": 0, "31_90": 0, "over_90": 0}
    for age in ages:
        if age <= 7:
            buckets["1_7"] += 1
        elif age <= 30:
            buckets["8_30"] += 1
        elif age <= 90:
            buckets["31_90"] += 1
        else:
            buckets["over_90"] += 1
    unassigned = None if not owner_column else sum(1 for row in rows if not row.get("owner_id"))
    return (max(ages) if ages else None, unassigned, buckets)


def _training_stats(
    db: Session,
    *,
    ctx: TenantContext,
    today: date,
    source_errors: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    rows = _safe_rows(
        db,
        sql="""
            SELECT valid_until
            FROM training_records
            WHERE amo_id = :amo_id AND valid_until IS NOT NULL AND valid_until < :today
            ORDER BY valid_until ASC
            LIMIT 1
        """,
        params={"amo_id": ctx.amo_id, "today": today},
        label="dashboard_v2_oldest_expired_training",
        ctx=ctx,
        source_errors=source_errors,
        timeout_ms=1200,
    )
    oldest = _age_days(rows[0].get("valid_until"), today) if rows else None
    total = _safe_scalar(
        db,
        sql="""
            SELECT COUNT(DISTINCT CAST(user_id AS TEXT) || ':' || CAST(course_id AS TEXT)) AS total
            FROM training_records
            WHERE amo_id = :amo_id
        """,
        params={"amo_id": ctx.amo_id},
        label="dashboard_v2_training_population",
        ctx=ctx,
        source_errors=source_errors,
        timeout_ms=1200,
    )
    return oldest, total


def _finding_stats(
    db: Session,
    *,
    ctx: TenantContext,
    source_errors: list[dict[str, Any]],
) -> tuple[int | None, dict[str, int]]:
    columns = _table_columns(db, "qms_audit_findings")
    owner_column = next((name for name in ("owner_user_id", "assigned_to_user_id", "responsible_user_id") if name in columns), None)
    unassigned = None
    if owner_column:
        unassigned = _safe_scalar(
            db,
            sql=f"""
                SELECT COUNT(*) AS total
                FROM qms_audit_findings
                WHERE amo_id = :amo_id AND closed_at IS NULL AND {owner_column} IS NULL
            """,
            params={"amo_id": ctx.amo_id},
            label="dashboard_v2_unassigned_findings",
            ctx=ctx,
            source_errors=source_errors,
        )
    severity: dict[str, int] = {}
    if "severity" in columns:
        rows = _safe_rows(
            db,
            sql="""
                SELECT COALESCE(NULLIF(UPPER(CAST(severity AS TEXT)), ''), 'UNCLASSIFIED') AS severity, COUNT(*) AS total
                FROM qms_audit_findings
                WHERE amo_id = :amo_id AND closed_at IS NULL
                GROUP BY COALESCE(NULLIF(UPPER(CAST(severity AS TEXT)), ''), 'UNCLASSIFIED')
            """,
            params={"amo_id": ctx.amo_id},
            label="dashboard_v2_finding_severity",
            ctx=ctx,
            source_errors=source_errors,
        )
        severity = {str(row.get("severity") or "UNCLASSIFIED"): int(row.get("total") or 0) for row in rows}
    return unassigned, severity


def _car_closure_kpi(
    db: Session,
    *,
    ctx: TenantContext,
    today: date,
    source_errors: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    columns = _table_columns(db, "quality_cars")
    if not {"created_at", "closed_at"}.issubset(columns):
        return None, None
    current_start = today - timedelta(days=90)
    previous_start = current_start - timedelta(days=90)
    rows = _safe_rows(
        db,
        sql="""
            SELECT created_at, closed_at
            FROM quality_cars
            WHERE amo_id = :amo_id
              AND closed_at IS NOT NULL
              AND created_at IS NOT NULL
              AND closed_at >= :previous_start
            ORDER BY closed_at ASC
            LIMIT 5000
        """,
        params={"amo_id": ctx.amo_id, "previous_start": previous_start},
        label="dashboard_v2_car_closure_cycle",
        ctx=ctx,
        source_errors=source_errors,
    )
    current: list[float] = []
    previous: list[float] = []
    current_start_dt = datetime.combine(current_start, datetime.min.time(), tzinfo=timezone.utc)
    previous_start_dt = datetime.combine(previous_start, datetime.min.time(), tzinfo=timezone.utc)
    for row in rows:
        created = _as_datetime(row.get("created_at"))
        closed = _as_datetime(row.get("closed_at"))
        if not created or not closed or closed < created:
            continue
        days = (closed - created).total_seconds() / 86400.0
        if closed >= current_start_dt:
            current.append(days)
        elif closed >= previous_start_dt:
            previous.append(days)
    return (round(float(median(current)), 1) if current else None, round(float(median(previous)), 1) if previous else None)


def _audit_completion_kpi(
    db: Session,
    *,
    ctx: TenantContext,
    today: date,
    source_errors: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    columns = _table_columns(db, "qms_audits")
    if not {"status", "planned_start"}.issubset(columns):
        return None, None

    def period(year: int, label: str) -> float | None:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        rows = _safe_rows(
            db,
            sql="""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN UPPER(CAST(status AS TEXT)) IN ('CLOSED', 'COMPLETED') THEN 1 ELSE 0 END) AS completed
                FROM qms_audits
                WHERE amo_id = :amo_id AND planned_start >= :start AND planned_start < :end
            """,
            params={"amo_id": ctx.amo_id, "start": start, "end": end},
            label=label,
            ctx=ctx,
            source_errors=source_errors,
        )
        if not rows:
            return None
        return _pct(int(rows[0].get("completed") or 0), int(rows[0].get("total") or 0))

    return period(today.year, "dashboard_v2_audit_completion_current"), period(today.year - 1, "dashboard_v2_audit_completion_previous")


def _repeat_finding_kpi(
    db: Session,
    *,
    ctx: TenantContext,
    source_errors: list[dict[str, Any]],
) -> float | None:
    columns = _table_columns(db, "qms_audit_findings")
    process_column = next((name for name in ("process_id", "process", "process_name") if name in columns), None)
    if not process_column:
        return None
    rows = _safe_rows(
        db,
        sql=f"""
            SELECT CAST({process_column} AS TEXT) AS process_key, COUNT(*) AS total
            FROM qms_audit_findings
            WHERE amo_id = :amo_id AND {process_column} IS NOT NULL
            GROUP BY CAST({process_column} AS TEXT)
        """,
        params={"amo_id": ctx.amo_id},
        label="dashboard_v2_repeat_findings",
        ctx=ctx,
        source_errors=source_errors,
    )
    total = sum(int(row.get("total") or 0) for row in rows)
    repeated = sum(int(row.get("total") or 0) for row in rows if int(row.get("total") or 0) > 1)
    return _pct(repeated, total)


def _performance_kpis(
    db: Session,
    *,
    ctx: TenantContext,
    today: date,
    counters: dict[str, int],
    training_total: int | None,
    source_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audit_current, audit_previous = _audit_completion_kpi(db, ctx=ctx, today=today, source_errors=source_errors)
    closure_current, closure_previous = _car_closure_kpi(db, ctx=ctx, today=today, source_errors=source_errors)
    repeat_current = _repeat_finding_kpi(db, ctx=ctx, source_errors=source_errors)
    overdue_rate = _pct(int(counters.get("overdue_cars", 0)), int(counters.get("open_cars", 0)))
    training_compliance = None
    if training_total is not None and training_total > 0:
        training_compliance = round(max(0.0, ((training_total - int(counters.get("training_expired_records", 0))) / training_total) * 100.0), 1)

    base = f"/maintenance/{ctx.amo_code}/quality"
    return [
        {
            "id": "audit-programme-completion",
            "label": "Audit programme completed",
            "current": audit_current,
            "target": 100.0,
            "previous": audit_previous,
            "direction": _direction(audit_current, audit_previous, lower_is_better=False),
            "unit": "%",
            "route": f"{base}/audits/program",
            "data_status": "available" if audit_current is not None else "not_available",
        },
        {
            "id": "overdue-car-rate",
            "label": "Overdue CAR rate",
            "current": overdue_rate,
            "target": 0.0,
            "previous": None,
            "direction": "not_available",
            "unit": "%",
            "route": f"{base}/cars/overdue",
            "data_status": "available" if overdue_rate is not None else "not_available",
        },
        {
            "id": "median-car-closure-days",
            "label": "Median CAR closure time",
            "current": closure_current,
            "target": None,
            "previous": closure_previous,
            "direction": _direction(closure_current, closure_previous, lower_is_better=True),
            "unit": "days",
            "route": f"{base}/reports/car-performance",
            "data_status": "available" if closure_current is not None else "not_available",
        },
        {
            "id": "repeat-finding-rate",
            "label": "Repeat-finding rate",
            "current": repeat_current,
            "target": 0.0,
            "previous": None,
            "direction": "not_available",
            "unit": "%",
            "route": f"{base}/reports/finding-trends",
            "data_status": "available" if repeat_current is not None else "not_available",
        },
        {
            "id": "training-compliance",
            "label": "Training compliance",
            "current": training_compliance,
            "target": 100.0,
            "previous": None,
            "direction": "not_available",
            "unit": "%",
            "route": f"/maintenance/{ctx.amo_code}/training/competence/matrix",
            "data_status": "available" if training_compliance is not None else "not_available",
        },
    ]


@canonical_router.get("/dashboard-v2")
def qms_operational_dashboard_v2(
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    today = date.today()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)

    base = qms_dashboard_lite(ctx=ctx, db=db)
    counters = {key: int(value or 0) for key, value in dict(base.get("counters") or {}).items()}
    source_errors = list(base.get("source_errors") or [])

    inbox_data: dict[str, Any] = {"items": []}
    try:
        inbox_data = qms_inbox(status_filter="unread", ctx=ctx, db=db)
    except Exception as exc:
        source_errors.append({"label": "my_work", "message": str(exc), "type": exc.__class__.__name__})
        _recover_qms_read_session(db, amo_id=ctx.amo_id, user_id=ctx.user_id, timeout_ms=1800)

    calendar_data: dict[str, Any] = {"items": []}
    try:
        calendar_data = qms_calendar(
            start=today,
            end=today + timedelta(days=30),
            limit=100,
            offset=0,
            source=None,
            ctx=ctx,
            db=db,
        )
        source_errors.extend(calendar_data.get("source_errors") or [])
    except Exception as exc:
        source_errors.append({"label": "upcoming_obligations", "message": str(exc), "type": exc.__class__.__name__})
        _recover_qms_read_session(db, amo_id=ctx.amo_id, user_id=ctx.user_id, timeout_ms=1800)

    oldest_car_age, car_unassigned, car_aging = _car_operational_stats(
        db,
        ctx=ctx,
        today=today,
        source_errors=source_errors,
    )
    oldest_training_age, training_total = _training_stats(
        db,
        ctx=ctx,
        today=today,
        source_errors=source_errors,
    )
    finding_unassigned, severity_breakdown = _finding_stats(
        db,
        ctx=ctx,
        source_errors=source_errors,
    )

    action_queue = _build_action_queue(
        amo_code=ctx.amo_code,
        counters=counters,
        oldest_car_age=oldest_car_age,
        car_unassigned=car_unassigned,
        oldest_training_age=oldest_training_age,
        finding_unassigned=finding_unassigned,
    )
    kpis = _performance_kpis(
        db,
        ctx=ctx,
        today=today,
        counters=counters,
        training_total=training_total,
        source_errors=source_errors,
    )

    my_work = []
    for item in list(inbox_data.get("items") or [])[:10]:
        my_work.append({
            "id": str(item.get("id") or ""),
            "title": str(item.get("message") or "Quality work item"),
            "severity": item.get("severity"),
            "created_at": item.get("created_at"),
            "route": f"/maintenance/{ctx.amo_code}/quality/inbox/assigned-to-me",
        })

    upcoming = sorted(
        list(calendar_data.get("items") or []),
        key=lambda item: (str(item.get("date") or "9999-12-31"), str(item.get("title") or "")),
    )[:12]

    source_counts = Counter(str(error.get("label") or "unknown") for error in source_errors)
    health_status = "healthy" if not source_errors else "partial"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    return {
        "contract": DASHBOARD_V2_CONTRACT,
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "as_of": datetime.now(timezone.utc).isoformat(),
        "action_queue": action_queue,
        "my_work": my_work,
        "upcoming_obligations": upcoming,
        "performance_kpis": kpis,
        "aging_buckets": {"overdue_cars": car_aging},
        "unassigned_counts": {
            "overdue_cars": car_unassigned,
            "open_findings": finding_unassigned,
        },
        "severity_breakdown": {"open_findings": severity_breakdown},
        "period_comparisons": {
            "status": "partial",
            "note": "Historical comparisons are returned only where timestamped source records support them. Snapshot history is not fabricated.",
        },
        "data_freshness": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counter_source": base.get("source"),
            "counter_as_of": base.get("as_of"),
            "calendar_start": today.isoformat(),
            "calendar_end": (today + timedelta(days=30)).isoformat(),
        },
        "source_health": {
            "status": health_status,
            "error_count": len(source_errors),
            "errors_by_source": dict(source_counts),
            "errors": source_errors,
        },
        "counters": counters,
        "trace_id": trace_id,
        "elapsed_ms": elapsed_ms,
    }
