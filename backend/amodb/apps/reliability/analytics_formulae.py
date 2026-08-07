from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any, Iterable

from .analytics_types import CalculationFormula


def _math_text(value: str) -> str:
    return f"<mtext>{escape(value)}</mtext>"


def _identifier(value: str) -> str:
    return f"<mi>{escape(value)}</mi>"


def _number(value: str | int | float | Decimal) -> str:
    return f"<mn>{escape(str(value))}</mn>"


def _fraction(numerator: str, denominator: str) -> str:
    return f"<mfrac><mrow>{numerator}</mrow><mrow>{denominator}</mrow></mfrac>"


def _times(left: str, right: str) -> str:
    return f"<mrow>{left}<mo>×</mo>{right}</mrow>"


def _minus(left: str, right: str) -> str:
    return f"<mrow>{left}<mo>−</mo>{right}</mrow>"


def _math(body: str) -> str:
    return (
        '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block" '
        'aria-label="Reliability calculation formula"><mrow>'
        f"{body}</mrow></math>"
    )


def _formula(
    *,
    code: str,
    name: str,
    latex: str,
    mathml: str,
    expression: dict[str, Any],
    unit: str,
    numerator_label: str,
    denominator_label: str | None,
    multiplier: Decimal | int | float | None,
    methodology: str,
    denominator_policy: str,
    source_fields: list[str],
    applied_to: list[str],
    version: str = "1.0",
    precision: int = 3,
    rounding_mode: str = "HALF_UP",
    origin: str = "SYSTEM",
) -> CalculationFormula:
    return CalculationFormula(
        code=code,
        name=name,
        version=version,
        origin=origin,
        latex=latex,
        mathml=mathml,
        expression=expression,
        unit=unit,
        precision=precision,
        rounding_mode=rounding_mode,
        numerator_label=numerator_label,
        denominator_label=denominator_label,
        multiplier=None if multiplier is None else float(multiplier),
        methodology=methodology,
        denominator_policy=denominator_policy,
        source_fields=source_fields,
        applied_to=applied_to,
    )


def _system_formulae() -> list[CalculationFormula]:
    fh = _identifier("FH")
    fc = _identifier("FC")
    events = _identifier("N_events")
    dispatch = _identifier("N_dispatch")
    delays = _identifier("N_delays")
    delay_minutes = _identifier("Σ delay_minutes")
    unscheduled = _identifier("N_unscheduled_removals")
    shop = _identifier("N_shop_outcomes")
    nff = _identifier("N_NFF")
    completed = _identifier("N_completed_actions")
    actions = _identifier("N_actions")
    successful = _identifier("N_effective_reviews")
    approved = _identifier("N_approved_reviews")

    return [
        _formula(
            code="dispatch_reliability_pct",
            name="Dispatch reliability",
            latex=r"DR=\frac{FC-N_{dispatch}}{FC}\times100",
            mathml=_math(_times(_fraction(_minus(fc, dispatch), fc), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": {"op": "subtract", "left": "flight_cycles", "right": "dispatch_interruptions"}, "denominator": "flight_cycles"}, "right": 100},
            unit="%",
            numerator_label="Recorded flight cycles less qualifying dispatch interruptions",
            denominator_label="Recorded flight cycles",
            multiplier=100,
            methodology="Qualifying technical cancellations, return-to-gate events, air turnbacks, diversions, in-flight shutdowns and aborted take-offs are treated as dispatch interruptions.",
            denominator_policy="Withhold the percentage when matching recorded flight-cycle exposure is zero or absent.",
            source_fields=["aircraft_utilization_daily.cycles", "reliability_events.event_type", "reliability_events.occurred_at"],
            applied_to=["summary.dispatch_reliability_pct", "chart.time_series.dispatch_reliability_pct"],
        ),
        _formula(
            code="event_rate_per_100_fh",
            name="Reliability-event rate per 100 flight hours",
            latex=r"R_{100FH}=\frac{N_{events}}{FH}\times100",
            mathml=_math(_times(_fraction(events, fh), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "reliability_event_count", "denominator": "flight_hours"}, "right": 100},
            unit="events / 100 FH",
            numerator_label="Canonical Reliability events",
            denominator_label="Recorded flight hours",
            multiplier=100,
            methodology="Counts canonical, tenant-scoped Reliability events after the active dashboard filters are applied.",
            denominator_policy="Withhold the rate when matching recorded flight-hour exposure is zero or absent.",
            source_fields=["reliability_events.id", "reliability_events.occurred_at", "aircraft_utilization_daily.flight_hours"],
            applied_to=["summary.event_rate_per_100_fh", "chart.time_series.event_rate_per_100_fh", "chart.aircraft_performance.event_rate_per_100_fh"],
        ),
        _formula(
            code="average_delay_minutes",
            name="Average technical delay",
            latex=r"\bar{D}=\frac{\sum D_{minutes}}{N_{technical\ delays}}",
            mathml=_math(_fraction(delay_minutes, delays)),
            expression={"op": "divide", "numerator": "sum_delay_minutes", "denominator": "technical_delay_count"},
            unit="minutes",
            numerator_label="Total derived technical-delay minutes",
            denominator_label="Technical-delay events",
            multiplier=1,
            methodology="Delay minutes are derived from actual departure minus scheduled departure and are not manually re-entered.",
            denominator_policy="Withhold the average when no qualifying technical-delay event exists.",
            source_fields=["reliability_flight_operations.scheduled_departure_at", "reliability_flight_operations.actual_departure_at", "reliability_events.delay_minutes"],
            applied_to=["summary.average_delay_minutes", "chart.event_mix.delay_minutes", "chart.station_delay.delay_minutes", "chart.route_delay.delay_minutes"],
        ),
        _formula(
            code="removal_rate_per_1000_fc",
            name="Unscheduled-removal rate per 1,000 flight cycles",
            latex=r"URR_{1000FC}=\frac{N_{unscheduled\ removals}}{FC}\times1000",
            mathml=_math(_times(_fraction(unscheduled, fc), _number(1000))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "unscheduled_removal_count", "denominator": "flight_cycles"}, "right": 1000},
            unit="removals / 1,000 FC",
            numerator_label="Unscheduled component removals",
            denominator_label="Recorded flight cycles",
            multiplier=1000,
            methodology="Uses canonical unscheduled-removal events in the selected population.",
            denominator_policy="Withhold the rate when matching flight-cycle exposure is zero or absent.",
            source_fields=["reliability_events.event_type", "reliability_events.part_number", "aircraft_utilization_daily.cycles"],
            applied_to=["summary.removal_rate_per_1000_fc", "chart.component_reliability.removal_rate_per_1000_fc"],
        ),
        _formula(
            code="removal_rate_per_1000_fh",
            name="Unscheduled-removal rate per 1,000 flight hours",
            latex=r"URR_{1000FH}=\frac{N_{unscheduled\ removals}}{FH}\times1000",
            mathml=_math(_times(_fraction(unscheduled, fh), _number(1000))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "unscheduled_removal_count", "denominator": "flight_hours"}, "right": 1000},
            unit="removals / 1,000 FH",
            numerator_label="Unscheduled component removals",
            denominator_label="Recorded flight hours",
            multiplier=1000,
            methodology="Uses canonical unscheduled-removal events in the selected population.",
            denominator_policy="Withhold the rate when matching flight-hour exposure is zero or absent.",
            source_fields=["reliability_events.event_type", "reliability_events.part_number", "aircraft_utilization_daily.flight_hours"],
            applied_to=["chart.component_reliability.removal_rate_per_1000_fh"],
        ),
        _formula(
            code="fleet_exposure_per_unscheduled_removal",
            name="Fleet exposure per unscheduled removal",
            latex=r"E_{fleet/removal}=\frac{FH}{N_{unscheduled\ removals}}",
            mathml=_math(_fraction(fh, unscheduled)),
            expression={"op": "divide", "numerator": "flight_hours", "denominator": "unscheduled_removal_count"},
            unit="FH / removal",
            numerator_label="Fleet flight-hour exposure",
            denominator_label="Unscheduled removals",
            multiplier=1,
            methodology="This is a fleet exposure indicator. It must not be represented as component MTBUR unless the installed component population exposure is available.",
            denominator_policy="Withhold when no unscheduled removal exists.",
            source_fields=["aircraft_utilization_daily.flight_hours", "reliability_events.event_type"],
            applied_to=["summary.mtbur_fleet_hours", "chart.component_reliability.fleet_hours_per_unscheduled_removal"],
        ),
        _formula(
            code="nff_rate_pct",
            name="No-fault-found rate",
            latex=r"NFF\%=\frac{N_{NFF}}{N_{shop\ outcomes}}\times100",
            mathml=_math(_times(_fraction(nff, shop), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "no_fault_found_count", "denominator": "shop_outcome_count"}, "right": 100},
            unit="%",
            numerator_label="Controlled no-fault-found outcomes",
            denominator_label="Controlled component-shop outcomes",
            multiplier=100,
            methodology="The denominator includes controlled shop findings and no-fault-found outcomes in the selected population.",
            denominator_policy="Withhold the percentage when no controlled shop outcome exists.",
            source_fields=["reliability_events.event_type", "reliability_component_shop_events.confirmed_failure"],
            applied_to=["summary.nff_rate_pct", "chart.component_reliability.nff_rate_pct"],
        ),
        _formula(
            code="average_deferral_closure_days",
            name="Average deferral closure duration",
            latex=r"\bar{T}_{closure}=\frac{\sum(t_{closed}-t_{applied})}{N_{closed\ deferrals}}",
            mathml=_math(_fraction(_identifier("Σ(t_closed−t_applied)"), _identifier("N_closed_deferrals"))),
            expression={"op": "divide", "numerator": {"op": "sum", "value": {"op": "duration_days", "start": "applied_at", "end": "closed_at"}}, "denominator": "closed_deferral_count"},
            unit="days",
            numerator_label="Total non-negative application-to-closure duration",
            denominator_label="Closed deferrals",
            multiplier=1,
            methodology="Negative durations are rejected by using a zero lower bound; only records with both controlled application and closure timestamps are included.",
            denominator_policy="Withhold the average when no controlled closure is available.",
            source_fields=["reliability_mel_cdl_deferrals.applied_at", "reliability_mel_cdl_deferrals.closed_at"],
            applied_to=["summary.average_deferral_closure_days", "chart.deferral_closure.average_days"],
        ),
        _formula(
            code="repeat_deferral_groups",
            name="Repeated deferral groups",
            latex=r"N_{repeat\ groups}=\sum_g\mathbf{1}(n_g>1)",
            mathml=_math(_identifier("Σg 1(ng>1)")),
            expression={"op": "count_groups", "group_by": ["aircraft_serial_number", "item_reference"], "predicate": {"op": "gt", "left": "group_count", "right": 1}},
            unit="groups",
            numerator_label="Aircraft/item-reference groups occurring more than once",
            denominator_label=None,
            multiplier=None,
            methodology="Groups controlled deferral records by aircraft serial number and MEL/CDL item reference.",
            denominator_policy="A group contributes one only when its controlled occurrence count exceeds one.",
            source_fields=["reliability_mel_cdl_deferrals.aircraft_serial_number", "reliability_mel_cdl_deferrals.item_reference"],
            applied_to=["summary.repeat_deferral_groups", "chart.deferral_repeats.count"],
        ),
        _formula(
            code="fracas_action_completion_pct",
            name="FRACAS action completion",
            latex=r"AC\%=\frac{N_{DONE}+N_{VERIFIED}}{N_{actions}}\times100",
            mathml=_math(_times(_fraction(completed, actions), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": {"op": "count", "statuses": ["DONE", "VERIFIED"]}, "denominator": "fracas_action_count"}, "right": 100},
            unit="%",
            numerator_label="Done or verified FRACAS actions",
            denominator_label="FRACAS actions",
            multiplier=100,
            methodology="Cancelled actions remain in the population unless explicitly excluded by the governed programme definition.",
            denominator_policy="Withhold the percentage when no FRACAS action exists.",
            source_fields=["fracas_actions.status", "fracas_actions.completed_at", "fracas_actions.verified_at"],
            applied_to=["summary.action_completion_pct", "chart.fracas_actions.count", "chart.fracas_action_trend.completed"],
        ),
        _formula(
            code="effectiveness_pass_pct",
            name="Approved effectiveness pass rate",
            latex=r"EP\%=\frac{N_{effective\ approved}}{N_{approved\ reviews}}\times100",
            mathml=_math(_times(_fraction(successful, approved), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "successful_approved_review_count", "denominator": "approved_review_count"}, "right": 100},
            unit="%",
            numerator_label="Approved reviews with effective/pass outcome",
            denominator_label="Approved effectiveness reviews",
            multiplier=100,
            methodology="Pending or unapproved reviews are not counted as successful.",
            denominator_policy="Withhold the percentage when no approved effectiveness review exists.",
            source_fields=["reliability_effectiveness_reviews.outcome", "reliability_effectiveness_reviews.approved_at"],
            applied_to=["summary.effectiveness_pass_pct", "chart.effectiveness.count"],
        ),
        _formula(
            code="ata_cumulative_pct",
            name="ATA Pareto cumulative share",
            latex=r"C_k=\frac{\sum_{i=1}^{k}N_i}{\sum_{i=1}^{m}N_i}\times100",
            mathml=_math(_times(_fraction(_identifier("Σ(i=1…k) Ni"), _identifier("Σ(i=1…m) Ni")), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "cumulative_ranked_ata_event_count", "denominator": "total_ata_event_count"}, "right": 100},
            unit="%",
            numerator_label="Cumulative event count through ranked ATA chapter k",
            denominator_label="All events with an ATA allocation in the selected population",
            multiplier=100,
            methodology="ATA chapters are ordered by descending event count before the cumulative share is calculated.",
            denominator_policy="Withhold when no ATA-scoped event exists.",
            source_fields=["reliability_events.ata_chapter", "reliability_events.id"],
            applied_to=["chart.ata_pareto.cumulative_pct"],
        ),
        _formula(
            code="source_invalid_rate_pct",
            name="Source invalid-record rate",
            latex=r"IR\%=\frac{N_{invalid}}{N_{received}}\times100",
            mathml=_math(_times(_fraction(_identifier("N_invalid"), _identifier("N_received")), _number(100))),
            expression={"op": "multiply", "left": {"op": "divide", "numerator": "invalid_record_count", "denominator": "received_record_count"}, "right": 100},
            unit="%",
            numerator_label="Invalid ingestion records",
            denominator_label="Received ingestion records",
            multiplier=100,
            methodology="Uses controlled ingestion-batch counts for the selected period and source.",
            denominator_policy="Withhold when the source has no received records in the selected period.",
            source_fields=["reliability_ingestion_batches.invalid_count", "reliability_ingestion_batches.record_count"],
            applied_to=["chart.source_health.invalid_rate_pct"],
        ),
        _formula(
            code="oil_consumption_qt_per_fh",
            name="Engine oil-consumption rate",
            latex=r"OCR=\frac{Q_{oil\ added}}{FH}",
            mathml=_math(_fraction(_identifier("Q_oil_added"), fh)),
            expression={"op": "divide", "numerator": "oil_quantity_added_quarts", "denominator": "flight_hours"},
            unit="qt / FH",
            numerator_label="Oil quantity added",
            denominator_label="Engine flight-hour exposure",
            multiplier=1,
            methodology="The dashboard consumes governed oil-consumption rate records and does not reconstruct rates from incomplete uplift records.",
            denominator_policy="Withhold when the underlying governed rate has no valid flight-hour exposure.",
            source_fields=["oil_consumption_rates.rate_quarts_per_hour", "oil_consumption_rates.window_start", "oil_consumption_rates.window_end"],
            applied_to=["chart.oil_consumption.latest_qt_per_hour", "chart.oil_consumption.average_qt_per_hour"],
        ),
    ]


def _custom_metric_formula(metric: Any) -> CalculationFormula:
    event_types = [str(value) for value in list(metric.numerator_event_types or [])]
    numerator_symbol = "N_{" + ("+".join(event_types) if event_types else "events") + "}"
    numerator_math = _identifier("N(" + (", ".join(event_types) if event_types else "events") + ")")
    denominator_type = str(metric.denominator_type or "NONE")
    denominator_symbol = denominator_type
    multiplier = Decimal(str(metric.multiplier or 1))
    method = str(metric.method or "RATE").upper()

    if method == "COUNT" or denominator_type == "NONE":
        latex = numerator_symbol
        mathml = _math(numerator_math)
        expression: dict[str, Any] = {"op": "count", "event_types": event_types}
        denominator_label = None
    elif method == "MTBUR":
        latex = rf"MTBUR=\frac{{{denominator_symbol}}}{{{numerator_symbol}}}"
        mathml = _math(_fraction(_identifier(denominator_type), numerator_math))
        expression = {"op": "divide", "numerator": denominator_type, "denominator": {"op": "count", "event_types": event_types}}
        denominator_label = "Qualifying event count"
    else:
        latex = rf"R=\frac{{{numerator_symbol}}}{{{denominator_symbol}}}\times {multiplier}"
        mathml = _math(_times(_fraction(numerator_math, _identifier(denominator_type)), _number(multiplier)))
        expression = {"op": "multiply", "left": {"op": "divide", "numerator": {"op": "count", "event_types": event_types}, "denominator": denominator_type}, "right": float(multiplier)}
        denominator_label = denominator_type

    unit = "count" if denominator_type == "NONE" or method == "COUNT" else f"per {multiplier:g} {denominator_type}"
    return _formula(
        code=f"programme.{metric.code}",
        name=str(metric.name),
        version=str(metric.formula_version or "1"),
        origin="PROGRAMME",
        latex=latex,
        mathml=mathml,
        expression=expression,
        unit=unit,
        numerator_label=", ".join(event_types) if event_types else "Configured qualifying events",
        denominator_label=denominator_label,
        multiplier=multiplier,
        methodology=str(metric.description or f"Controlled {method} metric from the effective Reliability programme definition."),
        denominator_policy=f"Minimum exposure: {metric.minimum_exposure}. Direction: {metric.direction}.",
        source_fields=["reliability_events.event_type", f"exposure.{denominator_type.lower()}"],
        applied_to=[f"programme_metric.{metric.code}"],
        precision=3,
    )


def build_formula_catalog(metric_definitions: Iterable[Any] = ()) -> list[CalculationFormula]:
    formulae = _system_formulae()
    formulae.extend(_custom_metric_formula(metric) for metric in metric_definitions)
    return sorted(formulae, key=lambda row: (row.origin, row.name.lower(), row.code))
