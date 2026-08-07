from __future__ import annotations

from collections import Counter
from datetime import datetime

from . import advanced_models, models, operational_sources
from .analytics_common import (
    CLOSED_ACTION_STATES, OPEN_DEFERRAL_STATES, UTC,
    _delta, _enum_value, _metric_status, _ratio,
    _event_totals, _utilisation_totals,
)
from .analytics_types import DashboardMetric


FORMULA_CODES = {
    "dispatch_reliability_pct": "dispatch_reliability_pct",
    "event_rate_per_100_fh": "event_rate_per_100_fh",
    "average_delay_minutes": "average_delay_minutes",
    "removal_rate_per_1000_fc": "removal_rate_per_1000_fc",
    "mtbur_fleet_hours": "fleet_exposure_per_unscheduled_removal",
    "nff_rate_pct": "nff_rate_pct",
    "repeat_deferral_groups": "repeat_deferral_groups",
    "average_deferral_closure_days": "average_deferral_closure_days",
    "action_completion_pct": "fracas_action_completion_pct",
    "effectiveness_pass_pct": "effectiveness_pass_pct",
}


def _summary_metrics(
    *,
    current_events: list[models.ReliabilityEvent],
    previous_events: list[models.ReliabilityEvent],
    current_utilisation: list[models.AircraftUtilizationDaily],
    previous_utilisation: list[models.AircraftUtilizationDaily],
    deferrals: list[operational_sources.ReliabilityMelCdlDeferral],
    fracas_cases: list[models.FRACASCase],
    fracas_actions: list[models.FRACASAction],
    engine_statuses: list[models.EngineTrendStatus],
    data_quality_issues: list[advanced_models.ReliabilityDataQualityIssue],
    effectiveness_reviews: list[advanced_models.ReliabilityEffectivenessReview],
    now: datetime,
) -> list[DashboardMetric]:
    current = _event_totals(current_events)
    previous = _event_totals(previous_events)
    current_exposure = _utilisation_totals(current_utilisation)
    previous_exposure = _utilisation_totals(previous_utilisation)

    current_rate = _ratio(current["events"], current_exposure["flight_hours"], 100)
    previous_rate = _ratio(previous["events"], previous_exposure["flight_hours"], 100)
    dispatch_reliability = _ratio(
        max(current_exposure["flight_cycles"] - current["dispatch_events"], 0),
        current_exposure["flight_cycles"],
        100,
    )
    previous_dispatch_reliability = _ratio(
        max(previous_exposure["flight_cycles"] - previous["dispatch_events"], 0),
        previous_exposure["flight_cycles"],
        100,
    )
    average_delay = _ratio(current["delay_minutes"], current["delays"], 1)
    previous_average_delay = _ratio(previous["delay_minutes"], previous["delays"], 1)
    nff_rate = _ratio(current["nff"], current["shop_events"], 100)
    previous_nff_rate = _ratio(previous["nff"], previous["shop_events"], 100)
    mtbur = _ratio(current_exposure["flight_hours"], current["unscheduled_removals"], 1)
    previous_mtbur = _ratio(previous_exposure["flight_hours"], previous["unscheduled_removals"], 1)

    open_deferrals = [row for row in deferrals if row.status in OPEN_DEFERRAL_STATES]
    overdue_deferrals = [row for row in open_deferrals if row.expires_at and row.expires_at < now]
    overdue_actions = [
        row for row in fracas_actions
        if row.status not in CLOSED_ACTION_STATES and row.due_date and row.due_date < now.date()
    ]
    open_cases = [row for row in fracas_cases if _enum_value(row.status) != "CLOSED"]
    engine_shifts = [row for row in engine_statuses if _enum_value(row.current_status) == "Trend Shift"]
    open_dq = [row for row in data_quality_issues if row.status not in {"RESOLVED", "CLOSED"}]
    approved_reviews = [row for row in effectiveness_reviews if row.approved_at is not None]
    successful_reviews = [
        row for row in approved_reviews
        if str(row.outcome).upper() in {"PASS", "PASSED", "EFFECTIVE", "SUCCESSFUL"}
    ]
    effectiveness_pass = _ratio(len(successful_reviews), len(approved_reviews), 100)
    closed_deferrals = [row for row in deferrals if row.closed_at and row.applied_at]
    closure_durations = []
    for row in closed_deferrals:
        applied = row.applied_at if row.applied_at.tzinfo else row.applied_at.replace(tzinfo=UTC)
        closed = row.closed_at if row.closed_at.tzinfo else row.closed_at.replace(tzinfo=UTC)
        closure_durations.append(max((closed - applied).total_seconds() / 86400, 0))
    average_deferral_closure = (
        round(sum(closure_durations) / len(closure_durations), 3)
        if closure_durations else None
    )
    extension_count = sum(len(list(row.extension_history_json or [])) for row in deferrals)
    repeat_deferral_groups = Counter(
        (row.aircraft_serial_number or "UNALLOCATED", row.item_reference or "UNALLOCATED")
        for row in deferrals
    )
    repeat_deferral_count = sum(1 for count in repeat_deferral_groups.values() if count > 1)
    completed_actions = [
        row for row in fracas_actions if _enum_value(row.status) in {"DONE", "VERIFIED"}
    ]
    action_completion = _ratio(len(completed_actions), len(fracas_actions), 100)
    removal_rate_per_1000_fc = _ratio(
        current["unscheduled_removals"], current_exposure["flight_cycles"], 1000
    )
    previous_removal_rate_per_1000_fc = _ratio(
        previous["unscheduled_removals"], previous_exposure["flight_cycles"], 1000
    )

    definitions = [
        ("dispatch_reliability_pct", "Dispatch reliability", dispatch_reliability, previous_dispatch_reliability, "%", current_exposure["flight_cycles"], "Technical dispatch interruptions normalised by recorded flight cycles.", {"dimension": "event_type", "key": "DISPATCH_INTERRUPTIONS"}),
        ("event_rate_per_100_fh", "Event rate", current_rate, previous_rate, "/100 FH", current_exposure["flight_hours"], "Canonical reliability events per 100 recorded flight hours.", {"dimension": "period", "key": "ALL"}),
        ("average_delay_minutes", "Average technical delay", average_delay, previous_average_delay, "min", current["delays"], "Total technical delay minutes divided by technical delay events.", {"dimension": "event_type", "key": "TECHNICAL_DELAY"}),
        ("repeat_defects", "Repeat defects", int(current["repeat_defects"]), int(previous["repeat_defects"]), "count", None, "Canonical repeat-defect occurrences in the selected period.", {"dimension": "event_type", "key": "REPEAT_DEFECT"}),
        ("unscheduled_removals", "Unscheduled removals", int(current["unscheduled_removals"]), int(previous["unscheduled_removals"]), "count", None, "Unscheduled component removals in the selected period.", {"dimension": "event_type", "key": "UNSCHEDULED_REMOVAL"}),
        ("removal_rate_per_1000_fc", "Removal rate", removal_rate_per_1000_fc, previous_removal_rate_per_1000_fc, "/1,000 FC", current_exposure["flight_cycles"], "Unscheduled component removals per 1,000 recorded flight cycles.", {"dimension": "event_type", "key": "UNSCHEDULED_REMOVAL"}),
        ("mtbur_fleet_hours", "Fleet exposure per unscheduled removal", mtbur, previous_mtbur, "FH/removal", current["unscheduled_removals"], "Fleet flight-hour exposure divided by unscheduled removals. This is not component MTBUR unless component population exposure is available.", {"dimension": "event_type", "key": "UNSCHEDULED_REMOVAL"}),
        ("nff_rate_pct", "No-fault-found rate", nff_rate, previous_nff_rate, "%", current["shop_events"], "No-fault-found outcomes as a share of controlled shop outcomes.", {"dimension": "event_type", "key": "NO_FAULT_FOUND"}),
        ("open_deferrals", "Open MEL/CDL", len(open_deferrals), None, "count", None, "Approved, extended or expired deferrals that are not closed.", {"dimension": "deferral_status", "key": "OPEN"}),
        ("overdue_deferrals", "Overdue MEL/CDL", len(overdue_deferrals), None, "count", None, "Open deferrals whose approved expiry has passed.", {"dimension": "deferral_status", "key": "OVERDUE"}),
        ("deferral_extensions", "MEL/CDL extensions", extension_count, None, "count", None, "Controlled extensions recorded in the selected deferral population.", {"dimension": "deferral_extension", "key": "ALL"}),
        ("repeat_deferral_groups", "Repeat deferral groups", repeat_deferral_count, None, "count", None, "Aircraft and MEL/CDL item combinations occurring more than once.", {"dimension": "deferral_repeat", "key": "ALL"}),
        ("average_deferral_closure_days", "Average deferral closure", average_deferral_closure, None, "days", len(closed_deferrals), "Average elapsed time from deferral application to controlled closure.", {"dimension": "deferral_closure", "key": "ALL"}),
        ("open_fracas", "Open FRACAS", len(open_cases), None, "count", None, "FRACAS cases not yet closed.", {"dimension": "fracas_stage", "key": "OPEN"}),
        ("overdue_actions", "Overdue FRACAS actions", len(overdue_actions), None, "count", None, "Open FRACAS actions past their due date.", {"dimension": "fracas_stage", "key": "OVERDUE_ACTIONS"}),
        ("action_completion_pct", "FRACAS action completion", action_completion, None, "%", len(fracas_actions), "Done or verified FRACAS actions as a share of all actions in the selected case population.", {"dimension": "fracas_action_status", "key": "COMPLETED"}),
        ("engine_shifts", "Engine trend shifts", len(engine_shifts), None, "count", None, "Engines currently classified as Trend Shift.", {"dimension": "engine_status", "key": "Trend Shift"}),
        ("effectiveness_pass_pct", "Approved effectiveness pass", effectiveness_pass, None, "%", len(approved_reviews), "Approved effectiveness reviews with an effective/pass outcome.", {"dimension": "effectiveness", "key": "SUCCESSFUL"}),
        ("data_quality_open", "Open data-quality issues", len(open_dq), None, "count", None, "Unresolved Reliability ingestion and validation issues.", {"dimension": "data_quality", "key": "OPEN"}),
    ]
    result: list[DashboardMetric] = []
    for code, label, value, previous_value, unit, denominator, detail, drilldown in definitions:
        delta_pct, direction = _delta(value, previous_value)
        result.append(
            DashboardMetric(
                code=code,
                label=label,
                value=None if value is None else round(float(value), 3),
                unit=unit,
                delta_pct=delta_pct,
                direction=direction,  # type: ignore[arg-type]
                status=_metric_status(code, value),  # type: ignore[arg-type]
                denominator=denominator,
                detail=detail,
                formula_code=FORMULA_CODES.get(code),
                drilldown=drilldown,
            )
        )
    return result
