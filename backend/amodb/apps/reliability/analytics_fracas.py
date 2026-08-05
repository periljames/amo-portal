from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.fleet import models as fleet_models

from . import advanced_models, models, operational_sources
from .analytics_common import CLOSED_ACTION_STATES, OPEN_DEFERRAL_STATES, UTC, _aircraft_type_label, _bucket_key, _enum_value, _normalise_date, _safe_float
from .analytics_types import ChartPoint, DashboardFilterOptions

def _fracas_charts(
    cases: list[models.FRACASCase],
    lifecycles: list[advanced_models.ReliabilityFracasLifecycle],
    reviews: list[advanced_models.ReliabilityEffectivenessReview],
    now: datetime,
) -> tuple[list[ChartPoint], list[ChartPoint], list[ChartPoint], list[ChartPoint]]:
    lifecycle_by_case = {row.fracas_case_id: row for row in lifecycles}
    stage_counts: Counter[str] = Counter()
    ageing_counts = {"0_30_DAYS": 0, "31_60_DAYS": 0, "61_90_DAYS": 0, "OVER_90_DAYS": 0}
    root_causes: Counter[str] = Counter()
    for case in cases:
        lifecycle = lifecycle_by_case.get(case.id)
        stage = lifecycle.stage if lifecycle else _enum_value(case.status)
        stage_counts[stage] += 1
        if _enum_value(case.status) != "CLOSED":
            opened = case.opened_at
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=UTC)
            age = max((now - opened).days, 0)
            if age <= 30:
                ageing_counts["0_30_DAYS"] += 1
            elif age <= 60:
                ageing_counts["31_60_DAYS"] += 1
            elif age <= 90:
                ageing_counts["61_90_DAYS"] += 1
            else:
                ageing_counts["OVER_90_DAYS"] += 1
        root = (case.root_cause or "").strip()
        if not root and lifecycle:
            root_payload = lifecycle.root_cause_json or {}
            root = str(root_payload.get("category") or root_payload.get("root_cause") or "").strip()
        root_causes[root or "UNCLASSIFIED"] += 1

    stages = [
        ChartPoint(
            key=key,
            label=key.replace("_", " ").title(),
            metrics={"count": count},
            drilldown={"dimension": "fracas_stage", "key": key},
        )
        for key, count in stage_counts.most_common()
    ]
    ageing_labels = {
        "0_30_DAYS": "0–30 days",
        "31_60_DAYS": "31–60 days",
        "61_90_DAYS": "61–90 days",
        "OVER_90_DAYS": "Over 90 days",
    }
    ageing = [
        ChartPoint(
            key=key,
            label=ageing_labels[key],
            metrics={"count": count},
            drilldown={"dimension": "fracas_age", "key": key},
        )
        for key, count in ageing_counts.items()
    ]
    roots = [
        ChartPoint(
            key=key,
            label=key[:80],
            metrics={"count": count},
            drilldown={"dimension": "root_cause", "key": key},
        )
        for key, count in root_causes.most_common(15)
    ]
    effectiveness_counts = Counter((row.outcome or "UNASSESSED").upper() for row in reviews)
    effectiveness = [
        ChartPoint(
            key=key,
            label=key.replace("_", " ").title(),
            metrics={"count": count, "approved": sum(1 for row in reviews if (row.outcome or "").upper() == key and row.approved_at is not None)},
            drilldown={"dimension": "effectiveness", "key": key},
        )
        for key, count in effectiveness_counts.most_common()
    ]
    return stages, ageing, roots, effectiveness

def _fracas_action_charts(
    actions: list[models.FRACASAction],
    lifecycles: list[advanced_models.ReliabilityFracasLifecycle],
    *,
    period_start: date,
    period_end: date,
    bucket: str,
    now: datetime,
) -> tuple[list[ChartPoint], list[ChartPoint], list[ChartPoint]]:
    status_counts: Counter[str] = Counter(_enum_value(row.status) or "UNCLASSIFIED" for row in actions)
    overdue_count = sum(
        1
        for row in actions
        if _enum_value(row.status) not in CLOSED_ACTION_STATES and row.due_date and row.due_date < now.date()
    )
    status_counts["OVERDUE"] = overdue_count
    status_points = [
        ChartPoint(
            key=key,
            label=key.replace("_", " ").title(),
            metrics={"count": count},
            drilldown={"dimension": "fracas_action_status", "key": key},
        )
        for key, count in status_counts.items()
        if count
    ]

    labels: dict[str, str] = {}
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in actions:
        created_day = _normalise_date(row.created_at)
        completed_day = _normalise_date(row.completed_at)
        due_day = row.due_date
        if created_day and period_start <= created_day <= period_end:
            key, label = _bucket_key(created_day, bucket)
            labels[key] = label
            grouped[key]["created"] += 1
        if completed_day and period_start <= completed_day <= period_end:
            key, label = _bucket_key(completed_day, bucket)
            labels[key] = label
            grouped[key]["completed"] += 1
        if due_day and period_start <= due_day <= period_end and _enum_value(row.status) not in CLOSED_ACTION_STATES and due_day < now.date():
            key, label = _bucket_key(due_day, bucket)
            labels[key] = label
            grouped[key]["overdue"] += 1
    trend_points = [
        ChartPoint(
            key=key,
            label=labels.get(key, key),
            metrics={
                "created": values.get("created", 0),
                "completed": values.get("completed", 0),
                "overdue": values.get("overdue", 0),
            },
            drilldown={"dimension": "fracas_action_period", "key": key, "bucket": bucket},
        )
        for key, values in sorted(grouped.items())
    ]

    reopened_counts = {"NEVER": 0, "ONCE": 0, "MULTIPLE": 0}
    for row in lifecycles:
        count = int(row.reopened_count or 0)
        reopened_counts["NEVER" if count == 0 else "ONCE" if count == 1 else "MULTIPLE"] += 1
    reopened_labels = {"NEVER": "Never reopened", "ONCE": "Reopened once", "MULTIPLE": "Reopened multiple times"}
    reopened_points = [
        ChartPoint(
            key=key,
            label=reopened_labels[key],
            metrics={"count": count},
            drilldown={"dimension": "fracas_reopened", "key": key},
        )
        for key, count in reopened_counts.items()
    ]
    return status_points, trend_points, reopened_points
