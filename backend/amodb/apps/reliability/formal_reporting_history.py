from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from .formal_reporting import ANALYSIS_ROLES, _amo_id, _profile, _report, _require_editable, _require_role

MAX_HISTORY_MONTHS = 60
SOURCE_DOMAINS = (
    "AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "SB", "CS", "AS", "UR",
    "STRUCTURES", "RECURRING", "ECTM", "ADD",
)


def month_start(value: date) -> date:
    return value.replace(day=1)


def shift_months(value: date, delta: int) -> date:
    base = value.year * 12 + (value.month - 1) + delta
    year, month0 = divmod(base, 12)
    return date(year, month0 + 1, 1)


def history_start(period_end: date, months: int) -> date:
    if months < 1 or months > MAX_HISTORY_MONTHS:
        raise ValueError(f"History window must be between 1 and {MAX_HISTORY_MONTHS} months.")
    return shift_months(month_start(period_end), -(months - 1))


def exact(value: Decimal | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    return format(value, "f")


def rate_per_100(events: int, hours: Decimal | None) -> Decimal | None:
    if hours is None or hours <= 0:
        return None
    with localcontext() as context:
        context.prec = 34
        return Decimal(events) / hours * Decimal("100")


def _params(report, start: date, aircraft: list[str]) -> dict[str, Any]:
    cutoff = report.data_cutoff_at
    if cutoff is None:
        raise HTTPException(status_code=409, detail="Freeze report data before generating long-term history.")
    return {
        "amo_id": report.amo_id,
        "start_date": start,
        "end_date": report.period_end,
        "cutoff": cutoff,
        "aircraft": aircraft,
        "use_aircraft": bool(aircraft),
    }


def _aircraft_filter(params: dict[str, Any]) -> tuple[str, bool]:
    """Return a typed-safe optional aircraft predicate for PostgreSQL.

    SQLAlchemy represents an empty expanding parameter as a synthetic integer
    subquery. Comparing a varchar aircraft serial to that empty integer subquery
    fails in PostgreSQL even when the surrounding boolean branch is false. Do
    not compile the expanding predicate at all when the frozen effectivity is
    whole-fleet.
    """
    use_aircraft = bool(params.get("use_aircraft"))
    return ("AND aircraft_serial_number IN :aircraft" if use_aircraft else "", use_aircraft)


def _prepare(statement_sql: str, *, use_aircraft: bool):
    statement = text(statement_sql)
    if use_aircraft:
        statement = statement.bindparams(bindparam("aircraft", expanding=True))
    return statement


def _utilisation_rows(db: Session, params: dict[str, Any]) -> list[dict[str, Any]]:
    aircraft_filter, use_aircraft = _aircraft_filter(params)
    statement = _prepare(f"""
        WITH approved_au AS (
          SELECT
            date_trunc('month', event_date)::date AS month,
            COALESCE(derived_values->>'flight_hours', payload->>'flight_hours') AS fh_text,
            COALESCE(derived_values->>'flight_cycles', derived_values->>'cycles', payload->>'flight_cycles', payload->>'cycles') AS fc_text
          FROM reliability_workbook_records
          WHERE amo_id = :amo_id
            AND dataset_code = 'AU'
            AND status IN ('APPROVED', 'CLOSED')
            AND event_date BETWEEN :start_date AND :end_date
            AND created_at <= :cutoff
            {aircraft_filter}
        )
        SELECT
          month,
          COALESCE(SUM(CASE WHEN fh_text ~ '^[+]?[0-9]+([.][0-9]+)?$' THEN fh_text::numeric ELSE NULL END), 0::numeric) AS flight_hours,
          COALESCE(SUM(CASE WHEN fc_text ~ '^[+]?[0-9]+([.][0-9]+)?$' THEN fc_text::numeric ELSE NULL END), 0::numeric) AS flight_cycles,
          COUNT(*) FILTER (WHERE fh_text ~ '^[+]?[0-9]+([.][0-9]+)?$') AS fh_observations,
          COUNT(*) FILTER (WHERE fc_text ~ '^[+]?[0-9]+([.][0-9]+)?$') AS fc_observations,
          COUNT(*) AS source_rows
        FROM approved_au
        GROUP BY month
        ORDER BY month
    """, use_aircraft=use_aircraft)
    return [dict(row) for row in db.execute(statement, params).mappings().all()]


def _event_rows(db: Session, params: dict[str, Any]) -> list[dict[str, Any]]:
    aircraft_filter, use_aircraft = _aircraft_filter(params)
    statement = _prepare(f"""
        SELECT
          date_trunc('month', occurred_at)::date AS month,
          COUNT(*) AS event_count
        FROM reliability_events
        WHERE amo_id = :amo_id
          AND occurred_at >= CAST(:start_date AS date)
          AND occurred_at < (CAST(:end_date AS date) + INTERVAL '1 day')
          AND created_at <= :cutoff
          AND validation_status = 'VALID'
          {aircraft_filter}
        GROUP BY month
        ORDER BY month
    """, use_aircraft=use_aircraft)
    return [dict(row) for row in db.execute(statement, params).mappings().all()]


def _domain_rows(db: Session, params: dict[str, Any]) -> list[dict[str, Any]]:
    aircraft_filter, use_aircraft = _aircraft_filter(params)
    statement = _prepare(f"""
        SELECT
          date_trunc('month', event_date)::date AS month,
          dataset_code,
          COUNT(*) AS record_count
        FROM reliability_workbook_records
        WHERE amo_id = :amo_id
          AND dataset_code IN ('AU','AI','FI','PM','OOS','RM','SM','SR','SB','CS','AS','UR','STRUCTURES','RECURRING','ECTM','ADD')
          AND status IN ('APPROVED', 'CLOSED')
          AND event_date BETWEEN :start_date AND :end_date
          AND created_at <= :cutoff
          {aircraft_filter}
        GROUP BY month, dataset_code
        ORDER BY month, dataset_code
    """, use_aircraft=use_aircraft)
    return [dict(row) for row in db.execute(statement, params).mappings().all()]


def _month_sequence(start: date, end: date) -> list[date]:
    output: list[date] = []
    current = month_start(start)
    terminal = month_start(end)
    while current <= terminal:
        output.append(current)
        current = shift_months(current, 1)
    return output


def _monthly_series(
    start: date,
    end: date,
    utilisation: list[dict[str, Any]],
    events: list[dict[str, Any]],
    domains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    util_by_month = {row["month"]: row for row in utilisation}
    event_by_month = {row["month"]: int(row["event_count"]) for row in events}
    domain_by_month: dict[date, dict[str, int]] = {}
    for row in domains:
        domain_by_month.setdefault(row["month"], {})[str(row["dataset_code"])] = int(row["record_count"])
    output: list[dict[str, Any]] = []
    for month in _month_sequence(start, end):
        util = util_by_month.get(month)
        hours = Decimal(str(util["flight_hours"])) if util and int(util["fh_observations"]) > 0 else None
        cycles = Decimal(str(util["flight_cycles"])) if util and int(util["fc_observations"]) > 0 else None
        event_count = event_by_month.get(month, 0)
        event_rate = rate_per_100(event_count, hours)
        domain_counts = {code: domain_by_month.get(month, {}).get(code, 0) for code in SOURCE_DOMAINS}
        output.append({
            "month": month.isoformat(),
            "exact_flight_hours": exact(hours),
            "exact_flight_cycles": exact(cycles),
            "canonical_event_count": event_count,
            "exact_event_rate_per_100_fh": exact(event_rate),
            "event_rate_quality": "VALID" if event_rate is not None else "WITHHELD_NO_FLIGHT_HOURS",
            "utilisation_source_rows": int(util["source_rows"]) if util else 0,
            "source_domain_counts": domain_counts,
        })
    return output


def _window_summary(series: list[dict[str, Any]], months: int) -> dict[str, Any]:
    subset = series[-months:]
    hours_values = [Decimal(item["exact_flight_hours"]) for item in subset if item["exact_flight_hours"] is not None]
    cycle_values = [Decimal(item["exact_flight_cycles"]) for item in subset if item["exact_flight_cycles"] is not None]
    hours = sum(hours_values, Decimal(0)) if hours_values else None
    cycles = sum(cycle_values, Decimal(0)) if cycle_values else None
    events = sum(int(item["canonical_event_count"]) for item in subset)
    rate = rate_per_100(events, hours)
    return {
        "months": months,
        "period_start": subset[0]["month"] if subset else None,
        "period_end": subset[-1]["month"] if subset else None,
        "exact_flight_hours": exact(hours),
        "exact_flight_cycles": exact(cycles),
        "canonical_event_count": events,
        "exact_event_rate_per_100_fh": exact(rate),
        "event_rate_quality": "VALID" if rate is not None else "WITHHELD_NO_FLIGHT_HOURS",
        "months_with_flight_hours": len(hours_values),
        "months_with_flight_cycles": len(cycle_values),
    }


def build_long_term_history(db: Session, report) -> dict[str, Any]:
    profile = _profile(db, report.amo_id, report.profile_id)
    configured = sorted({int(item) for item in (profile.historical_windows or [12]) if int(item) > 0})
    windows = [item for item in configured if item <= MAX_HISTORY_MONTHS]
    if not windows:
        windows = [12]
    max_window = max(windows)
    start = history_start(report.period_end, max_window)
    aircraft = [str(item) for item in (report.effectivity_json or {}).get("aircraft_serial_numbers", []) if str(item).strip()]
    params = _params(report, start, aircraft)
    utilisation = _utilisation_rows(db, params)
    events = _event_rows(db, params)
    domains = _domain_rows(db, params)
    series = _monthly_series(start, report.period_end, utilisation, events, domains)
    return {
        "method": "INDEXED_MONTHLY_BACKEND_AGGREGATION",
        "cutoff_at": report.data_cutoff_at.isoformat() if report.data_cutoff_at else None,
        "effectivity": {
            "scope": "SELECTED_AIRCRAFT" if aircraft else "TENANT_FLEET",
            "aircraft_serial_numbers": aircraft,
        },
        "max_window_months": max_window,
        "configured_windows": windows,
        "series": series,
        "summaries": [_window_summary(series, months) for months in windows],
        "denominator_policy": "Rates are WITHHELD when approved flight-hour exposure is unavailable or zero; missing exposure is never converted to zero reliability.",
        "source_policy": "Approved/CLOSED governed workbook records and VALID canonical Reliability events created on or before the formal report data cutoff.",
    }


def freeze_long_term_history(db: Session, report) -> dict[str, Any]:
    _require_editable(report)
    if report.data_cutoff_at is None or report.effectivity_frozen_at is None:
        raise HTTPException(status_code=409, detail="Freeze the report data cutoff/effectivity before long-term history.")
    current = dict(report.calculation_snapshots_json or {})
    history = build_long_term_history(db, report)
    current["long_term_history"] = history
    report.calculation_snapshots_json = current
    charts = dict(report.chart_data_json or {})
    charts["long_term_history"] = history["series"]
    report.chart_data_json = charts
    db.commit()
    return history


def register(router: APIRouter) -> None:
    @router.post("/formal-reporting/reports/{report_id}/long-term-history")
    def generate_history(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        report = _report(db, amo_id, report_id)
        return freeze_long_term_history(db, report)

    @router.get("/formal-reporting/reports/{report_id}/long-term-history")
    def get_history(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        report = _report(db, amo_id, report_id)
        history = (report.calculation_snapshots_json or {}).get("long_term_history")
        if history is None:
            raise HTTPException(status_code=404, detail="Long-term Reliability history has not been frozen for this report revision.")
        return history
