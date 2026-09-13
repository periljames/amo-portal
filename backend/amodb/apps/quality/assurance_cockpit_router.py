from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .assurance_metrics_router import _full_metrics, _priority_queue, _readiness, _count
from .assurance_sources import (AUDIT_ACTORS, SourceFailure, actor_condition, programme_responsibility,
    responsibility, source_columns, source_result, query_rows, require_source_access)
from .assurance_wiring_router import _safe_identifier
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context, has_quality_permission


router = APIRouter(prefix="/excellence", tags=["Quality assurance cockpit"])
ViewContext = Literal["global", "mine"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _audit_scope_condition(alias: str, ctx: TenantContext, columns: set[str]) -> tuple[str, dict[str, Any]]:
    return actor_condition(columns, AUDIT_ACTORS, alias), {"actor_user_id": ctx.user_id}


def _period_window(period: int) -> tuple[date, date]:
    return date(period, 1, 1), date(period, 12, 31)


def _programme_metrics(db: Session, ctx: TenantContext, *, period: int, view: ViewContext) -> dict[str, int | float]:
    source_columns(db, "quality_audit_programmes")
    source_columns(db, "quality_audit_programme_items")
    where = ["p.amo_id = :amo_id", "p.programme_year = :period", "p.status IN ('APPROVED','ACTIVE','UNDER_REVIEW')"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "period": period}
    if view == "mine":
        where.append(programme_responsibility(db))
        params["actor_user_id"] = ctx.user_id
    rows = query_rows(
        db,
        "SELECT "
        "COUNT(i.id) AS total, "
        "COUNT(i.id) FILTER (WHERE i.schedule_id IS NOT NULL) AS scheduled, "
        "COUNT(i.id) FILTER (WHERE i.schedule_id IS NULL AND COALESCE(i.state, 'PLANNED') NOT IN ('COMPLETED','CANCELLED')) AS unscheduled, "
        "COUNT(i.id) FILTER (WHERE i.state = 'COMPLETED') AS completed "
        "FROM quality_audit_programmes p "
        "LEFT JOIN quality_audit_programme_items i ON i.programme_id = p.id AND i.amo_id = p.amo_id "
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
    columns = source_columns(db, "qms_audits", ("planned_start", "created_at", "status"))
    start, end = _period_window(period)
    date_column = _first(columns, "planned_start", "created_at")
    where = ["a.amo_id = :amo_id"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "start": start, "end": end + timedelta(days=1)}
    if not date_column:
        raise SourceFailure("SCHEMA_UNAVAILABLE", "Audit period date is unavailable.")
    if date_column:
        where.append("COALESCE(a.planned_start, CAST(a.created_at AS DATE)) >= :start")
        where.append("COALESCE(a.planned_start, CAST(a.created_at AS DATE)) < :end")
    if "deleted_at" in columns:
        where.append("a.deleted_at IS NULL")
    if view == "mine":
        scope, scope_params = _audit_scope_condition("a", ctx, source_columns(db, "qms_audits"))
        where.append(scope)
        params.update(scope_params)
    return query_rows(
        db,
        "SELECT COALESCE(a.status, 'UNKNOWN') AS status, COUNT(*) AS count "
        "FROM qms_audits a WHERE " + " AND ".join(where) + " GROUP BY a.status ORDER BY a.status",
        params,
    )


def _finding_trend(db: Session, ctx: TenantContext, *, period: int, view: ViewContext) -> list[dict[str, Any]]:
    finding_columns = source_columns(db, "qms_audit_findings", ("audit_id", "closed_at"))
    audit_columns = source_columns(db, "qms_audits")
    if "created_at" not in finding_columns:
        raise SourceFailure("SCHEMA_UNAVAILABLE", "Finding occurrence date is unavailable.")
    start, end = _period_window(period)
    severity = _first(finding_columns, "level", "severity", "finding_type")
    severity_expr = f"UPPER(COALESCE(CAST(f.{_safe_identifier(severity)} AS TEXT), 'OTHER'))" if severity else "'OTHER'"
    where = ["f.amo_id = :amo_id", "f.created_at >= :start", "f.created_at < :end_exclusive"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "start": start, "end_exclusive": end + timedelta(days=1)}
    source_columns(db, "qms_audits", ("deleted_at",))
    where.append("a.deleted_at IS NULL")
    join = " JOIN qms_audits a ON a.id = f.audit_id AND a.amo_id = f.amo_id "
    if view == "mine" and audit_columns and "audit_id" in finding_columns:
        join = " JOIN qms_audits a ON a.id = f.audit_id AND a.amo_id = f.amo_id "
        scope, scope_params = _audit_scope_condition("a", ctx, source_columns(db, "qms_audits"))
        where.append(scope)
        params.update(scope_params)
    elif view == "mine":
        return []
    rows = query_rows(
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
    columns = source_columns(db, "quality_cars", ("status",))
    due = _first(columns, "due_date", "target_closure_date")
    if not due:
        raise SourceFailure("SCHEMA_UNAVAILABLE", "CAR due date is unavailable.")
    where = ["amo_id = :amo_id", f"{_safe_identifier(due)} IS NOT NULL"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "today": date.today()}
    if "status" in columns:
        where.append("UPPER(COALESCE(status, 'OPEN')) NOT IN ('CLOSED','CANCELLED')")
    if view == "mine":
        where.append(responsibility(db, "quality_cars", columns))
        params["actor_user_id"] = ctx.user_id
    sql = (
        "SELECT CASE "
        f"WHEN {_safe_identifier(due)} >= :today THEN 'not_due' "
        f"WHEN :today - {_safe_identifier(due)} <= 30 THEN '0_30' "
        f"WHEN :today - {_safe_identifier(due)} <= 60 THEN '31_60' "
        f"WHEN :today - {_safe_identifier(due)} <= 90 THEN '61_90' "
        "ELSE 'over_90' END AS bucket, COUNT(*) AS count "
        "FROM quality_cars WHERE " + " AND ".join(where) + " GROUP BY 1"
    )
    rows = query_rows(db, sql, params)
    order = ["not_due", "0_30", "31_60", "61_90", "over_90"]
    counts = {str(row.get("bucket")): int(row.get("count") or 0) for row in rows}
    return [{"bucket": bucket, "count": counts.get(bucket, 0)} for bucket in order]


def _control_exposure(db: Session, ctx: TenantContext, *, view: ViewContext) -> list[dict[str, Any]]:
    columns = source_columns(db, "qms_audit_findings", ("audit_id", "closed_at"))
    category = _first(columns, "category", "finding_type", "source_section", "section")
    if not category:
        raise SourceFailure("SCHEMA_UNAVAILABLE", "Finding classification is unavailable.")
    where = ["f.amo_id = :amo_id"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id}
    if "closed_at" in columns:
        where.append("f.closed_at IS NULL")
    source_columns(db, "qms_audits", ("deleted_at",))
    where.append("a.deleted_at IS NULL")
    join = " JOIN qms_audits a ON a.id = f.audit_id AND a.amo_id = f.amo_id "
    if view == "mine" and "audit_id" in columns and source_columns(db, "qms_audits"):
        join = " JOIN qms_audits a ON a.id = f.audit_id AND a.amo_id = f.amo_id "
        scope, scope_params = _audit_scope_condition("a", ctx, source_columns(db, "qms_audits"))
        where.append(scope)
        params.update(scope_params)
    elif view == "mine":
        return []
    return query_rows(
        db,
        "SELECT COALESCE(NULLIF(TRIM(CAST(f." + _safe_identifier(category) + " AS TEXT)), ''), 'Unclassified') AS category, COUNT(*) AS count "
        "FROM qms_audit_findings f" + join + " WHERE " + " AND ".join(where) +
        " GROUP BY 1 ORDER BY 2 DESC, 1",
        params,
    )


def _scoped_metrics(db: Session, ctx: TenantContext, *, period: int, view: ViewContext):
    metrics, warnings = _full_metrics(db, ctx, view=view)
    def programme():
        require_source_access(db, ctx, "quality_audit_programmes")
        return _programme_metrics(db, ctx, period=period, view=view)
    result = source_result(programme)
    programme_keys = ("programme_requirements_total", "programme_requirements_scheduled", "programme_requirements_unscheduled", "programme_requirements_completed", "programme_coverage_pct")
    metrics.update(result.value if result.status == "SUCCESS" else dict.fromkeys(programme_keys))
    if result.status != "SUCCESS":
        warnings.append(result.warning("programme"))
    start, end = date(period, 1, 1), date(period + 1, 1, 1)
    keys = []
    for status, key in (("PLANNED", "planned_audits"), ("IN_PROGRESS", "in_progress_audits"), ("CAP_OPEN", "cap_open_audits"), ("CLOSED", "closed_audits")):
        keys.append(key)
        metrics[key] = _count(db, ctx, source=key, table="qms_audits", view=view,
            conditions=["status = :status", "COALESCE(planned_start, CAST(created_at AS DATE)) >= :start", "COALESCE(planned_start, CAST(created_at AS DATE)) < :end"],
            params={"status": status, "start": start, "end": end}, warnings=warnings)
    values = [metrics[key] for key in keys]
    metrics["open_audits"] = sum(values[:3]) if all(value is not None for value in values[:3]) else None
    metrics["audit_completion_pct"] = (round(values[3] / sum(values) * 100, 1) if sum(values) else 0.0) if all(value is not None for value in values) else None
    return metrics, warnings


def _metric_drilldowns(ctx: TenantContext, *, period: int, view: ViewContext) -> dict[str, dict[str, Any]]:
    base = f"/maintenance/{ctx.amo_code}/quality"
    common = {"period": str(period), "view": view}
    return {
        "programme_requirements_unscheduled": {"path": f"{base}/audits/program", "query": {**common, "focus": "unscheduled"}, "drawer": "unscheduled-requirements"},
        "programme_coverage_pct": {"path": f"{base}/audits/program", "query": common},
        "audit_completion_pct": {"path": f"{base}/audits", "query": common},
        "open_findings": {"path": f"{base}/audits/register", "query": {"view": view, "status": "open"}},
        "overdue_cars": {"path": f"{base}/cars/overdue", "query": {"view": view}},
        "open_cars": {"path": f"{base}/cars/register", "query": {"view": view, "status": "active"}},
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
    unscheduled = metrics.get("programme_requirements_unscheduled")
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
    projections = {}
    for name, table, query in (
        ("audit_pipeline", "qms_audits", lambda: _audit_pipeline(db, ctx, period=period, view=view)),
        ("finding_trend", "qms_audit_findings", lambda: _finding_trend(db, ctx, period=period, view=view)),
        ("closure_ageing", "quality_cars", lambda: _closure_ageing(db, ctx, view=view)),
        ("control_exposure", "qms_audit_findings", lambda: _control_exposure(db, ctx, view=view)),
    ):
        def run():
            require_source_access(db, ctx, table)
            return query()
        result = source_result(run)
        projections[name] = result.value
        if result.status != "SUCCESS":
            warnings.append(result.warning(name))
    # Partial source loss cannot make either the score or an empty queue healthy.
    if warnings:
        readiness = _readiness({**metrics, "source_health": None})
    for item in priorities:
        separator = "&" if "?" in item["path"] else "?"
        item["path"] += f"{separator}view={view}&period={period}"
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "view": view,
        "period": period,
        "as_of": _now().isoformat(),
        "readiness": readiness,
        "metrics": metrics,
        "priority_queue": priorities[:12],
        **projections,
        "metric_basis": {
            **{key: "AS_OF_CURRENT" for key in metrics},
            **{key: "PERIOD_DUE" for key in metrics if key.startswith("programme_")},
            **{key: "PERIOD_EVENT" for key in ("planned_audits", "in_progress_audits", "cap_open_audits", "closed_audits", "open_audits", "audit_completion_pct", "audit_pipeline", "finding_trend")},
            "closure_ageing": "AS_OF_CURRENT", "control_exposure": "AS_OF_CURRENT",
        },
        "period_note": "Audit cohort uses planned start, falling back to creation date; completion is the current status of that cohort. Exposure and readiness are current, not historical snapshots.",
        "source_health": "PARTIAL" if warnings else "SUCCESS",
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
    view: ViewContext = "global",
) -> list[dict[str, Any]]:
    columns = source_columns(db, table)
    reference = _first(columns, *reference_candidates)
    title = _first(columns, *title_candidates)
    status = _first(columns, *status_candidates)
    if not reference and not title:
        raise SourceFailure("SCHEMA_UNAVAILABLE", "Searchable source fields are unavailable.")
    searchable = [column for column in (reference, title) if column]
    where = ["amo_id = :amo_id"]
    if view == "mine":
        where.append(responsibility(db, table, columns))
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
    rows = query_rows(db, sql, {"actor_user_id": ctx.user_id, "amo_id": ctx.amo_id, "needle": f"%{query}%", "exact": query, "prefix": f"{query}%", "limit": limit})
    base = f"/maintenance/{ctx.amo_code}/quality"
    items: list[dict[str, Any]] = []
    for row in rows:
        record_id = str(row.get("id") or "")
        reference_value = str(row.get("reference") or "").strip()
        title_value = str(row.get("title") or reference_value or record_id).strip()
        if route_builder == "audit":
            path = f"{base}/audits/{quote(record_id)}/setup"
        elif route_builder == "car":
            path = f"{base}/cars/{quote(record_id)}/overview"
        elif route_builder == "document":
            path = f"{base}/documents/{quote(record_id)}/overview"
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
            "rank": int(row.get("rank", 2)),
        })
    return items


@router.get("/command-search")
def command_search(
    q: str = Query(min_length=1, max_length=120),
    view: ViewContext = Query(default="global"),
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
        ("Schedule audit", "Commit a programme requirement in the Planner", f"{base}/audits/plan", ("schedule", "audit", "planner", "calendar")),
        ("Create CAR", "Open corrective-action control", f"{base}/cars/new", ("create", "car", "corrective", "action")),
        ("Open Audit Programme", "Review governed coverage and readiness", f"{base}/audits/program", ("programme", "coverage", "audit", "plan")),
        ("Open Findings Register", "Review findings and linked corrective actions", f"{base}/audits/register?tab=findings", ("finding", "register", "nonconformity", "nc")),
        ("Open Evidence Vault", "Find retained audit and assurance evidence", f"{base}/evidence-vault/search", ("evidence", "vault", "record")),
    ]
    command_permissions = ("qms.calendar.view", "qms.car.create", "qms.audit.view", "qms.finding.view", "qms.evidence.view")
    tokens = set(clean.lower().split())
    action_items = [
        {"kind": "action", "id": f"action-{index}", "reference": None, "title": title, "subtitle": subtitle, "status": None, "path": path, "rank": 1}
        for index, (title, subtitle, path, keywords) in enumerate(commands)
        if has_quality_permission(db, ctx, command_permissions[index]) and any(token in " ".join((title.lower(), subtitle.lower(), *keywords)) for token in tokens)
    ]

    per_source = limit
    records: list[dict[str, Any]] = []
    warnings = []
    for spec in (
        ("qms_audits", "audit", ("audit_ref",), ("title", "scope", "auditee"), ("status",), "audit"),
        ("quality_cars", "car", ("car_number", "car_ref", "reference"), ("title", "description", "problem_statement"), ("status",), "car"),
        ("qms_documents", "controlled_document", ("doc_code",), ("title", "description"), ("status",), "document"),
        ("quality_assurance_controls", "assurance_control", ("control_code", "clause_reference"), ("title", "description", "control_objective"), ("status", "approval_status"), "control"),
    ):
        if not has_quality_permission(db, ctx, {"qms_audits": "qms.audit.view", "quality_cars": "qms.car.view", "qms_documents": "qms.document.view"}.get(spec[0], "qms.dashboard.view")):
            continue
        result = source_result(lambda: _search_rows(
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
            view=view,
        ))
        if result.status == "SUCCESS":
            records.extend(result.value)
        else:
            warnings.append(result.warning(spec[0]))

    combined = sorted([*action_items, *records], key=lambda item: (int(item.get("rank", 2)), str(item.get("kind")), str(item.get("title"))))[:limit]
    for item in combined:
        item.pop("rank", None)
    return {
        "items": combined,
        "query": clean,
        "view": view,
        "warnings": warnings,
        "as_of": _now().isoformat(),
        "ranking": "exact reference, reference prefix, then tenant-scoped textual match; current application permissions remain authoritative",
    }
