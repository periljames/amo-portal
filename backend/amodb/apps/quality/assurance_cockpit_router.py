from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .assurance_metrics_router import _full_metrics, _priority_queue, _readiness
from .assurance_wiring_router import _safe_identifier, _table_columns
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence", tags=["Quality assurance cockpit"])
ViewContext = Literal["global", "mine"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _user_scope(columns: set[str], *, user_id: str, candidates: tuple[str, ...]) -> tuple[str, dict[str, Any]]:
    usable = [column for column in candidates if column in columns]
    if not usable:
        return "1 = 0", {"actor_user_id": user_id}
    return "(" + " OR ".join(f"{_safe_identifier(column)} = :actor_user_id" for column in usable) + ")", {"actor_user_id": user_id}


def _safe_rows(db: Session, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        with db.begin_nested():
            return [dict(row) for row in db.execute(text(sql), params).mappings().all()]
    except Exception:
        return []


def _safe_scalar(db: Session, sql: str, params: dict[str, Any]) -> int:
    try:
        with db.begin_nested():
            return int(db.execute(text(sql), params).scalar() or 0)
    except Exception:
        return 0


def _scoped_count(
    db: Session,
    ctx: TenantContext,
    *,
    table: str,
    view: ViewContext,
    user_columns: tuple[str, ...] = (),
    conditions: tuple[str, ...] = (),
    params: dict[str, Any] | None = None,
) -> int:
    columns = _table_columns(db, table)
    if not columns:
        return 0
    where = list(conditions)
    query_params: dict[str, Any] = dict(params or {})
    if "amo_id" in columns:
        where.insert(0, "amo_id = :amo_id")
        query_params["amo_id"] = ctx.amo_id
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    if view == "mine":
        scope, scope_params = _user_scope(columns, user_id=ctx.user_id, candidates=user_columns)
        where.append(scope)
        query_params.update(scope_params)
    sql = f"SELECT COUNT(*) FROM {_safe_identifier(table)}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return _safe_scalar(db, sql, query_params)


def _audit_scope_condition(alias: str, ctx: TenantContext) -> tuple[str, dict[str, Any]]:
    return (
        "(" + " OR ".join(
            f"{alias}.{column} = :actor_user_id"
            for column in (
                "lead_auditor_user_id",
                "observer_auditor_user_id",
                "assistant_auditor_user_id",
                "auditee_user_id",
                "created_by_user_id",
            )
        ) + ")",
        {"actor_user_id": ctx.user_id},
    )


def _period_window(period: int) -> tuple[date, date]:
    return date(period, 1, 1), date(period, 12, 31)


def _programme_metrics(db: Session, ctx: TenantContext, *, period: int, view: ViewContext) -> dict[str, int | float]:
    programme_columns = _table_columns(db, "quality_audit_programmes")
    item_columns = _table_columns(db, "quality_audit_programme_items")
    if not programme_columns or not item_columns:
        return {
            "programme_requirements_total": 0,
            "programme_requirements_scheduled": 0,
            "programme_requirements_unscheduled": 0,
            "programme_requirements_completed": 0,
            "programme_coverage_pct": 0.0,
        }
    where = ["p.amo_id = :amo_id", "p.programme_year = :period", "p.status IN ('APPROVED','ACTIVE','UNDER_REVIEW')"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "period": period}
    if view == "mine":
        where.append("p.owner_user_id = :actor_user_id")
        params["actor_user_id"] = ctx.user_id
    rows = _safe_rows(
        db,
        "SELECT "
        "COUNT(i.id) AS total, "
        "COUNT(i.id) FILTER (WHERE i.schedule_id IS NOT NULL) AS scheduled, "
        "COUNT(i.id) FILTER (WHERE i.schedule_id IS NULL AND COALESCE(i.state, 'PLANNED') NOT IN ('COMPLETED','CANCELLED')) AS unscheduled, "
        "COUNT(i.id) FILTER (WHERE i.state = 'COMPLETED') AS completed "
        "FROM quality_audit_programmes p "
        "LEFT JOIN quality_audit_programme_items i ON i.programme_id = p.id "
        "WHERE " + " AND ".join(where),
        params,
    )
    row = rows[0] if rows else {}
    total = int(row.get("total") or 0)
    scheduled = int(row.get("scheduled") or 0)
    completed = int(row.get("completed") or 0)
    return {
        "programme_requirements_total": total,
        "programme_requirements_scheduled": scheduled,
        "programme_requirements_unscheduled": int(row.get("unscheduled") or 0),
        "programme_requirements_completed": completed,
        "programme_coverage_pct": round((scheduled / total * 100.0) if total else 0.0, 1),
    }


def _audit_pipeline(db: Session, ctx: TenantContext, *, period: int, view: ViewContext) -> list[dict[str, Any]]:
    columns = _table_columns(db, "qms_audits")
    if not columns:
        return []
    start, end = _period_window(period)
    date_column = _first(columns, "planned_start", "created_at")
    where = ["a.amo_id = :amo_id"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "start": start, "end": end}
    if date_column:
        where.append(f"a.{_safe_identifier(date_column)} >= :start")
        where.append(f"a.{_safe_identifier(date_column)} <= :end")
    if "deleted_at" in columns:
        where.append("a.deleted_at IS NULL")
    if view == "mine":
        scope, scope_params = _audit_scope_condition("a", ctx)
        where.append(scope)
        params.update(scope_params)
    return _safe_rows(
        db,
        "SELECT COALESCE(a.status, 'UNKNOWN') AS status, COUNT(*) AS count "
        "FROM qms_audits a WHERE " + " AND ".join(where) + " GROUP BY a.status ORDER BY a.status",
        params,
    )


def _finding_trend(db: Session, ctx: TenantContext, *, period: int, view: ViewContext) -> list[dict[str, Any]]:
    finding_columns = _table_columns(db, "qms_audit_findings")
    audit_columns = _table_columns(db, "qms_audits")
    if not finding_columns or "created_at" not in finding_columns:
        return []
    start, end = _period_window(period)
    severity = _first(finding_columns, "level", "severity", "finding_type")
    severity_expr = f"UPPER(COALESCE(CAST(f.{_safe_identifier(severity)} AS TEXT), 'OTHER'))" if severity else "'OTHER'"
    where = ["f.amo_id = :amo_id", "f.created_at >= :start", "f.created_at < :end_exclusive"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "start": start, "end_exclusive": end + timedelta(days=1)}
    join = ""
    if view == "mine" and audit_columns and "audit_id" in finding_columns:
        join = " JOIN qms_audits a ON a.id = f.audit_id AND a.amo_id = f.amo_id "
        scope, scope_params = _audit_scope_condition("a", ctx)
        where.append(scope)
        params.update(scope_params)
    elif view == "mine":
        return []
    rows = _safe_rows(
        db,
        "SELECT date_trunc('month', f.created_at)::date AS month, "
        f"{severity_expr} AS severity, COUNT(*) AS count "
        "FROM qms_audit_findings f" + join + " WHERE " + " AND ".join(where) +
        " GROUP BY 1, 2 ORDER BY 1, 2",
        params,
    )
    by_month: dict[str, dict[str, Any]] = {}
    for row in rows:
        month = str(row.get("month"))[:10]
        target = by_month.setdefault(month, {"month": month, "level_1": 0, "level_2": 0, "level_3": 0, "observations": 0, "other": 0})
        raw = str(row.get("severity") or "OTHER").upper()
        count = int(row.get("count") or 0)
        if "1" in raw or "CRITICAL" in raw:
            target["level_1"] += count
        elif "2" in raw or "MAJOR" in raw:
            target["level_2"] += count
        elif "3" in raw or "MINOR" in raw:
            target["level_3"] += count
        elif "4" in raw or "OBSERV" in raw:
            target["observations"] += count
        else:
            target["other"] += count
    return list(by_month.values())


def _closure_ageing(db: Session, ctx: TenantContext, *, view: ViewContext) -> list[dict[str, Any]]:
    columns = _table_columns(db, "quality_cars")
    if not columns:
        return []
    due = _first(columns, "due_date", "target_closure_date")
    if not due:
        return []
    where = ["amo_id = :amo_id", f"{_safe_identifier(due)} IS NOT NULL"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "today": date.today()}
    if "closed_at" in columns:
        where.append("closed_at IS NULL")
    elif "status" in columns:
        where.append("UPPER(COALESCE(status, 'OPEN')) NOT IN ('CLOSED','CANCELLED')")
    if view == "mine":
        scope, scope_params = _user_scope(
            columns,
            user_id=ctx.user_id,
            candidates=("assigned_to_user_id", "responsible_user_id", "requested_by_user_id", "created_by_user_id"),
        )
        where.append(scope)
        params.update(scope_params)
    sql = (
        "SELECT CASE "
        f"WHEN {_safe_identifier(due)} >= :today THEN 'not_due' "
        f"WHEN :today - {_safe_identifier(due)} <= 30 THEN '0_30' "
        f"WHEN :today - {_safe_identifier(due)} <= 60 THEN '31_60' "
        f"WHEN :today - {_safe_identifier(due)} <= 90 THEN '61_90' "
        "ELSE 'over_90' END AS bucket, COUNT(*) AS count "
        "FROM quality_cars WHERE " + " AND ".join(where) + " GROUP BY 1"
    )
    rows = _safe_rows(db, sql, params)
    order = ["not_due", "0_30", "31_60", "61_90", "over_90"]
    counts = {str(row.get("bucket")): int(row.get("count") or 0) for row in rows}
    return [{"bucket": bucket, "count": counts.get(bucket, 0)} for bucket in order]


def _control_exposure(db: Session, ctx: TenantContext, *, view: ViewContext) -> list[dict[str, Any]]:
    columns = _table_columns(db, "qms_audit_findings")
    if not columns:
        return []
    category = _first(columns, "category", "finding_type", "source_section", "section")
    if not category:
        return []
    where = ["f.amo_id = :amo_id"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id}
    if "closed_at" in columns:
        where.append("f.closed_at IS NULL")
    join = ""
    if view == "mine" and "audit_id" in columns and _table_columns(db, "qms_audits"):
        join = " JOIN qms_audits a ON a.id = f.audit_id AND a.amo_id = f.amo_id "
        scope, scope_params = _audit_scope_condition("a", ctx)
        where.append(scope)
        params.update(scope_params)
    elif view == "mine":
        return []
    return _safe_rows(
        db,
        "SELECT COALESCE(NULLIF(TRIM(CAST(f." + _safe_identifier(category) + " AS TEXT)), ''), 'Unclassified') AS category, COUNT(*) AS count "
        "FROM qms_audit_findings f" + join + " WHERE " + " AND ".join(where) +
        " GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 8",
        params,
    )


def _scoped_metrics(db: Session, ctx: TenantContext, *, period: int, view: ViewContext) -> tuple[dict[str, int | float], list[dict[str, str]]]:
    metrics, warnings = _full_metrics(db, ctx)
    metrics = dict(metrics)
    metrics.update(_programme_metrics(db, ctx, period=period, view=view))

    audit_columns = _table_columns(db, "qms_audits")
    audit_scope = ("lead_auditor_user_id", "observer_auditor_user_id", "assistant_auditor_user_id", "auditee_user_id", "created_by_user_id")
    for status, key in (("PLANNED", "planned_audits"), ("IN_PROGRESS", "in_progress_audits"), ("CAP_OPEN", "cap_open_audits"), ("CLOSED", "closed_audits")):
        metrics[key] = _scoped_count(db, ctx, table="qms_audits", view=view, user_columns=audit_scope, conditions=("status = :status",), params={"status": status})
    metrics["open_audits"] = int(metrics.get("planned_audits", 0)) + int(metrics.get("in_progress_audits", 0)) + int(metrics.get("cap_open_audits", 0))

    if view == "mine":
        car_scope = ("assigned_to_user_id", "responsible_user_id", "requested_by_user_id", "created_by_user_id")
        car_columns = _table_columns(db, "quality_cars")
        if car_columns:
            open_condition = "UPPER(COALESCE(status, 'OPEN')) NOT IN ('CLOSED','CANCELLED')" if "status" in car_columns else "1=1"
            metrics["open_cars"] = _scoped_count(db, ctx, table="quality_cars", view=view, user_columns=car_scope, conditions=(open_condition,))
            due = _first(car_columns, "due_date", "target_closure_date")
            if due:
                metrics["overdue_cars"] = _scoped_count(db, ctx, table="quality_cars", view=view, user_columns=car_scope, conditions=(open_condition, f"{_safe_identifier(due)} < :today"), params={"today": date.today()})
                metrics["cars_due_30"] = _scoped_count(db, ctx, table="quality_cars", view=view, user_columns=car_scope, conditions=(open_condition, f"{_safe_identifier(due)} BETWEEN :today AND :due_30"), params={"today": date.today(), "due_30": date.today() + timedelta(days=30)})

        control_columns = _table_columns(db, "quality_assurance_controls")
        if control_columns:
            control_scope = ("owner_user_id", "created_by_user_id")
            active_condition = "status = 'ACTIVE'" if "status" in control_columns else "1=1"
            metrics["active_controls"] = _scoped_count(db, ctx, table="quality_assurance_controls", view=view, user_columns=control_scope, conditions=(active_condition,))
            if "next_test_due" in control_columns:
                metrics["controls_due"] = _scoped_count(db, ctx, table="quality_assurance_controls", view=view, user_columns=control_scope, conditions=(active_condition, "(next_test_due IS NULL OR next_test_due <= :due_30)"), params={"due_30": date.today() + timedelta(days=30)})

    total_audits = int(metrics.get("planned_audits", 0)) + int(metrics.get("in_progress_audits", 0)) + int(metrics.get("cap_open_audits", 0)) + int(metrics.get("closed_audits", 0))
    metrics["audit_completion_pct"] = round((int(metrics.get("closed_audits", 0)) / total_audits * 100.0) if total_audits else 0.0, 1)
    return metrics, warnings


def _metric_drilldowns(ctx: TenantContext, *, period: int, view: ViewContext) -> dict[str, dict[str, Any]]:
    base = f"/maintenance/{ctx.amo_code}/quality"
    common = {"period": str(period), "view": view}
    return {
        "programme_requirements_unscheduled": {"path": f"{base}/audits/program", "query": {**common, "focus": "unscheduled"}, "drawer": "unscheduled-requirements"},
        "programme_coverage_pct": {"path": f"{base}/audits/program", "query": common},
        "audit_completion_pct": {"path": f"{base}/audits", "query": common},
        "open_findings": {"path": f"{base}/audits/register", "query": {**common, "tab": "findings", "status": "open"}},
        "overdue_cars": {"path": f"{base}/audits/register", "query": {**common, "tab": "cars", "timing": "overdue"}},
        "open_cars": {"path": f"{base}/audits/register", "query": {**common, "tab": "cars", "status": "open"}},
        "open_regulator_findings": {"path": f"{base}/external-interface/regulator-findings", "query": common},
    }


@router.get("/cockpit")
def assurance_cockpit(
    view: ViewContext = Query(default="global"),
    period: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200),
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, warnings = _scoped_metrics(db, ctx, period=period, view=view)
    priorities = _priority_queue(metrics, ctx.amo_code)
    readiness = _readiness(metrics)
    unscheduled = int(metrics.get("programme_requirements_unscheduled", 0))
    if unscheduled:
        priorities = [
            {
                "id": "programme-unscheduled",
                "label": "Programme requirements awaiting scheduling",
                "count": unscheduled,
                "severity": "HIGH",
                "why": "Approved or review-stage programme requirements are not yet committed to the authoritative Planner.",
                "path": f"/maintenance/{ctx.amo_code}/quality/audits/program?focus=unscheduled",
            },
            *priorities,
        ]
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "view": view,
        "period": period,
        "as_of": _now().isoformat(),
        "readiness": readiness,
        "metrics": metrics,
        "priority_queue": priorities[:12],
        "audit_pipeline": _audit_pipeline(db, ctx, period=period, view=view),
        "finding_trend": _finding_trend(db, ctx, period=period, view=view),
        "closure_ageing": _closure_ageing(db, ctx, view=view),
        "control_exposure": _control_exposure(db, ctx, view=view),
        "drilldowns": _metric_drilldowns(ctx, period=period, view=view),
        "scope": {
            "mode": view,
            "label": "My Work" if view == "mine" else "Global",
            "server_resolved_user": ctx.user_id if view == "mine" else None,
            "note": "Personal scope is resolved from the authenticated session; the client cannot nominate another user.",
        },
        "warnings": warnings,
    }


def _search_rows(
    db: Session,
    ctx: TenantContext,
    *,
    table: str,
    entity_type: str,
    reference_candidates: tuple[str, ...],
    title_candidates: tuple[str, ...],
    status_candidates: tuple[str, ...],
    route_builder: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    columns = _table_columns(db, table)
    if not columns:
        return []
    reference = _first(columns, *reference_candidates)
    title = _first(columns, *title_candidates)
    status = _first(columns, *status_candidates)
    if not reference and not title:
        return []
    searchable = [column for column in (reference, title) if column]
    where = ["amo_id = :amo_id"] if "amo_id" in columns else []
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    needle_parts = [f"COALESCE(CAST({_safe_identifier(column)} AS TEXT), '')" for column in searchable]
    search_text = " || ' ' || ".join(needle_parts)
    where.append(f"({search_text}) ILIKE :needle")
    reference_expr = f"COALESCE(CAST({_safe_identifier(reference)} AS TEXT), '')" if reference else "''"
    title_expr = f"COALESCE(CAST({_safe_identifier(title)} AS TEXT), '')" if title else reference_expr
    status_expr = f"COALESCE(CAST({_safe_identifier(status)} AS TEXT), '')" if status else "''"
    sql = (
        "SELECT CAST(id AS TEXT) AS id, "
        f"{reference_expr} AS reference, {title_expr} AS title, {status_expr} AS status, "
        f"CASE WHEN LOWER({reference_expr}) = LOWER(:exact) THEN 0 WHEN LOWER({reference_expr}) LIKE LOWER(:prefix) THEN 1 ELSE 2 END AS rank "
        f"FROM {_safe_identifier(table)} WHERE " + " AND ".join(where) + " ORDER BY rank, title LIMIT :limit"
    )
    rows = _safe_rows(db, sql, {"amo_id": ctx.amo_id, "needle": f"%{query}%", "exact": query, "prefix": f"{query}%", "limit": limit})
    base = f"/maintenance/{ctx.amo_code}/quality"
    items: list[dict[str, Any]] = []
    for row in rows:
        record_id = str(row.get("id") or "")
        reference_value = str(row.get("reference") or "").strip()
        title_value = str(row.get("title") or reference_value or record_id).strip()
        if route_builder == "audit":
            path = f"{base}/audits/register?auditId={quote(record_id)}"
        elif route_builder == "car":
            path = f"{base}/cars/{quote(record_id)}/overview"
        elif route_builder == "document":
            path = f"{base}/documents?focusId={quote(record_id)}"
        elif route_builder == "control":
            path = f"{base}?hub=controls&focusId={quote(record_id)}"
        else:
            path = base
        items.append({
            "kind": entity_type,
            "id": record_id,
            "reference": reference_value or None,
            "title": title_value,
            "subtitle": reference_value if reference_value and reference_value != title_value else entity_type.replace("_", " ").title(),
            "status": row.get("status") or None,
            "path": path,
            "rank": int(row.get("rank") or 2),
        })
    return items


@router.get("/command-search")
def command_search(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=40),
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    clean = " ".join(q.strip().split())
    if not clean:
        return {"items": [], "query": q, "as_of": _now().isoformat()}

    base = f"/maintenance/{ctx.amo_code}/quality"
    commands = [
        ("Schedule audit", "Commit a programme requirement in the Planner", f"{base}/calendar/week", ("schedule", "audit", "planner", "calendar")),
        ("Create CAR", "Open corrective-action control", f"{base}/cars/new", ("create", "car", "corrective", "action")),
        ("Open Audit Programme", "Review governed coverage and readiness", f"{base}/audits/program", ("programme", "coverage", "audit", "plan")),
        ("Open Findings Register", "Review findings and linked corrective actions", f"{base}/audits/register?tab=findings", ("finding", "register", "nonconformity", "nc")),
        ("Open Evidence Vault", "Find retained audit and assurance evidence", f"{base}/audits/evidence-vault", ("evidence", "vault", "record")),
    ]
    tokens = set(clean.lower().split())
    action_items = [
        {"kind": "action", "id": f"action-{index}", "reference": None, "title": title, "subtitle": subtitle, "status": None, "path": path, "rank": 1}
        for index, (title, subtitle, path, keywords) in enumerate(commands)
        if any(token in " ".join((title.lower(), subtitle.lower(), *keywords)) for token in tokens)
    ]

    per_source = max(4, min(12, limit))
    records: list[dict[str, Any]] = []
    for spec in (
        ("qms_audits", "audit", ("audit_ref",), ("title", "scope", "auditee"), ("status",), "audit"),
        ("quality_cars", "car", ("car_number", "car_ref", "reference"), ("title", "description", "problem_statement"), ("status",), "car"),
        ("qms_documents", "controlled_document", ("doc_code",), ("title", "description"), ("status",), "document"),
        ("quality_assurance_controls", "assurance_control", ("control_code", "clause_reference"), ("title", "description", "control_objective"), ("status", "approval_status"), "control"),
    ):
        records.extend(_search_rows(
            db,
            ctx,
            table=spec[0],
            entity_type=spec[1],
            reference_candidates=spec[2],
            title_candidates=spec[3],
            status_candidates=spec[4],
            route_builder=spec[5],
            query=clean,
            limit=per_source,
        ))

    combined = sorted([*action_items, *records], key=lambda item: (int(item.get("rank", 2)), str(item.get("kind")), str(item.get("title"))))[:limit]
    for item in combined:
        item.pop("rank", None)
    return {
        "items": combined,
        "query": clean,
        "as_of": _now().isoformat(),
        "ranking": "exact reference, reference prefix, then tenant-scoped textual match; current application permissions remain authoritative",
    }
