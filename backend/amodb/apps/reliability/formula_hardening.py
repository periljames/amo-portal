from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import Column, Integer, String, Text, event, select

from . import advanced_models as domain
from . import analytics_formulae
from .analytics_types import CalculationFormula


_FORMULA_FIELDS = {
    "formula_latex": Column(Text, nullable=False, default=""),
    "formula_mathml": Column(Text, nullable=False, default=""),
    "formula_expression_json": Column(domain.JSON_VALUE, nullable=False, default=dict),
    "formula_unit": Column(String(80), nullable=False, default="count"),
    "formula_precision": Column(Integer, nullable=False, default=3),
    "formula_rounding_mode": Column(String(24), nullable=False, default="HALF_UP"),
    "denominator_policy": Column(Text, nullable=False, default=""),
    "formula_source_fields_json": Column(domain.JSON_VALUE, nullable=False, default=list),
}

_RUN_FIELDS = {
    "formula_snapshot_json": Column(domain.JSON_VALUE, nullable=False, default=dict),
    "formula_snapshot_hash": Column(String(64), nullable=False, default=""),
}


def _attach_columns() -> None:
    for name, column in _FORMULA_FIELDS.items():
        if name not in domain.ReliabilityMetricDefinition.__table__.c:
            setattr(domain.ReliabilityMetricDefinition, name, column)
    for name, column in _RUN_FIELDS.items():
        if name not in domain.ReliabilityCalculationRun.__table__.c:
            setattr(domain.ReliabilityCalculationRun, name, column)


def _decimal_text(value: Any) -> str:
    number = Decimal(str(value if value is not None else 1))
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _event_latex(event_types: list[str], fallback: str = "events") -> str:
    if not event_types:
        return rf"N_{{\mathrm{{{fallback}}}}}"
    text = "+".join(event_types).replace("_", r"\_")
    return rf"N_{{\mathrm{{{text}}}}}"


def _event_mathml(event_types: list[str], fallback: str = "events") -> str:
    label = ", ".join(event_types) if event_types else fallback
    return analytics_formulae._identifier(f"N({label})")


def _governed_metric_formula(metric: Any) -> CalculationFormula:
    configured_types = [str(value) for value in list(metric.numerator_event_types or [])]
    method = str(metric.method or "RATE").upper()
    denominator_type = str(metric.denominator_type or "NONE").upper()
    multiplier = Decimal(str(metric.multiplier if metric.multiplier is not None else 1))
    multiplier_text = _decimal_text(multiplier)
    numerator_types = configured_types
    denominator_label: str | None
    source_fields = ["reliability_events.event_type"]

    if method == "NFF_RATE":
        numerator_types = ["NO_FAULT_FOUND"]
        numerator_latex = _event_latex(numerator_types)
        denominator_latex = _event_latex(["UNSCHEDULED_REMOVAL"])
        numerator_math = _event_mathml(numerator_types)
        denominator_math = _event_mathml(["UNSCHEDULED_REMOVAL"])
        latex = rf"NFF\%=\frac{{{numerator_latex}}}{{{denominator_latex}}}\times {multiplier_text}"
        mathml = analytics_formulae._math(
            analytics_formulae._times(
                analytics_formulae._fraction(numerator_math, denominator_math),
                analytics_formulae._number(multiplier_text),
            )
        )
        expression = {
            "op": "multiply",
            "left": {
                "op": "divide",
                "numerator": {"op": "count", "event_types": numerator_types},
                "denominator": {"op": "count", "event_types": ["UNSCHEDULED_REMOVAL"]},
            },
            "right": float(multiplier),
        }
        denominator_label = "Unscheduled-removal events"
        unit = "%" if multiplier == Decimal("100") else f"ratio × {multiplier_text}"
        methodology = (
            "Counts no-fault-found events and divides them by unscheduled-removal events "
            "within the same governed period and scope, matching the execution service."
        )
        source_fields.append("reliability_events.event_type=UNSCHEDULED_REMOVAL")
    elif method == "PERCENT":
        numerator_latex = _event_latex(numerator_types)
        numerator_math = _event_mathml(numerator_types)
        denominator_latex = r"N_{\mathrm{ALL\ RELIABILITY\ EVENTS}}"
        denominator_math = analytics_formulae._identifier("N(all reliability events)")
        latex = rf"P\%=\frac{{{numerator_latex}}}{{{denominator_latex}}}\times {multiplier_text}"
        mathml = analytics_formulae._math(
            analytics_formulae._times(
                analytics_formulae._fraction(numerator_math, denominator_math),
                analytics_formulae._number(multiplier_text),
            )
        )
        expression = {
            "op": "multiply",
            "left": {
                "op": "divide",
                "numerator": {"op": "count", "event_types": numerator_types},
                "denominator": {"op": "count", "event_types": []},
            },
            "right": float(multiplier),
        }
        denominator_label = "All Reliability events in the same governed period and scope"
        unit = "%" if multiplier == Decimal("100") else f"ratio × {multiplier_text}"
        methodology = (
            "Divides the configured event population by all Reliability events in the same "
            "period and scope, matching the governed event-denominator contract."
        )
        source_fields.append("reliability_events.id")
    elif method == "COUNT" or denominator_type == "NONE":
        numerator_latex = _event_latex(numerator_types)
        numerator_math = _event_mathml(numerator_types)
        latex = numerator_latex
        mathml = analytics_formulae._math(numerator_math)
        expression = {"op": "count", "event_types": numerator_types}
        denominator_label = None
        unit = "count"
        methodology = "Counts the configured Reliability event types in the governed period and scope."
    elif method == "MTBUR":
        numerator_latex = _event_latex(numerator_types)
        numerator_math = _event_mathml(numerator_types)
        latex = rf"MTBUR=\frac{{{denominator_type}}}{{{numerator_latex}}}"
        mathml = analytics_formulae._math(
            analytics_formulae._fraction(
                analytics_formulae._identifier(denominator_type),
                numerator_math,
            )
        )
        expression = {
            "op": "divide",
            "numerator": {"op": "exposure", "type": denominator_type},
            "denominator": {"op": "count", "event_types": numerator_types},
        }
        denominator_label = "Configured qualifying event count"
        unit = f"{denominator_type} / event"
        methodology = (
            f"Divides governed {denominator_type} exposure by the configured qualifying event count."
        )
        source_fields.append(f"exposure.{denominator_type.lower()}")
    else:
        numerator_latex = _event_latex(numerator_types)
        numerator_math = _event_mathml(numerator_types)
        latex = rf"R=\frac{{{numerator_latex}}}{{{denominator_type}}}\times {multiplier_text}"
        mathml = analytics_formulae._math(
            analytics_formulae._times(
                analytics_formulae._fraction(
                    numerator_math,
                    analytics_formulae._identifier(denominator_type),
                ),
                analytics_formulae._number(multiplier_text),
            )
        )
        expression = {
            "op": "multiply",
            "left": {
                "op": "divide",
                "numerator": {"op": "count", "event_types": numerator_types},
                "denominator": {"op": "exposure", "type": denominator_type},
            },
            "right": float(multiplier),
        }
        denominator_label = f"Governed {denominator_type} exposure"
        unit = f"events / {multiplier_text} {denominator_type}"
        methodology = (
            f"Divides the configured qualifying event count by governed {denominator_type} "
            f"exposure and multiplies the result by {multiplier_text}."
        )
        source_fields.append(f"exposure.{denominator_type.lower()}")

    configured_description = str(metric.description or "").strip()
    if configured_description:
        methodology = f"{configured_description} Calculation contract: {methodology}"

    return analytics_formulae._formula(
        code=f"programme.{metric.code}",
        name=str(metric.name),
        version=str(metric.formula_version or "1"),
        origin="PROGRAMME",
        latex=latex,
        mathml=mathml,
        expression=expression,
        unit=unit,
        numerator_label=", ".join(numerator_types) if numerator_types else "Configured qualifying events",
        denominator_label=denominator_label,
        multiplier=None if method in {"COUNT", "MTBUR"} or denominator_type == "NONE" else multiplier,
        methodology=methodology,
        denominator_policy=(
            f"Withhold or classify as insufficient exposure below {metric.minimum_exposure}. "
            f"Configured threshold direction: {metric.direction}."
        ),
        source_fields=source_fields,
        applied_to=[f"programme_metric.{metric.code}"],
        precision=3,
    )


def _governed_system_formulae() -> list[CalculationFormula]:
    formulae = analytics_formulae._system_formulae()
    corrected: list[CalculationFormula] = []
    for formula in formulae:
        if formula.code != "dispatch_reliability_pct":
            corrected.append(formula)
            continue
        fc = analytics_formulae._identifier("FC")
        dispatch = analytics_formulae._identifier("N_dispatch")
        guarded_numerator = (
            "<mrow><mi>max</mi><mo>(</mo>"
            f"{analytics_formulae._minus(fc, dispatch)}"
            "<mo>,</mo><mn>0</mn><mo>)</mo></mrow>"
        )
        corrected.append(
            formula.model_copy(
                update={
                    "latex": r"DR=\frac{\max(FC-N_{dispatch},0)}{FC}\times100",
                    "mathml": analytics_formulae._math(
                        analytics_formulae._times(
                            analytics_formulae._fraction(guarded_numerator, fc),
                            analytics_formulae._number(100),
                        )
                    ),
                    "expression": {
                        "op": "multiply",
                        "left": {
                            "op": "divide",
                            "numerator": {
                                "op": "maximum",
                                "values": [
                                    {
                                        "op": "subtract",
                                        "left": "flight_cycles",
                                        "right": "dispatch_interruptions",
                                    },
                                    0,
                                ],
                            },
                            "denominator": "flight_cycles",
                        },
                        "right": 100,
                    },
                    "methodology": (
                        "Subtracts qualifying technical dispatch interruptions from recorded flight cycles, "
                        "with a zero lower bound, then expresses the result as a percentage."
                    ),
                }
            )
        )
    return corrected


def _generated_snapshot(metric: Any) -> dict[str, Any]:
    return _governed_metric_formula(metric).model_dump(mode="json")


def _snapshot(metric: Any) -> dict[str, Any]:
    generated = _governed_metric_formula(metric)
    stored_updates: dict[str, Any] = {}
    mapping = {
        "latex": "formula_latex",
        "mathml": "formula_mathml",
        "expression": "formula_expression_json",
        "unit": "formula_unit",
        "precision": "formula_precision",
        "rounding_mode": "formula_rounding_mode",
        "denominator_policy": "denominator_policy",
        "source_fields": "formula_source_fields_json",
    }
    for output_name, stored_name in mapping.items():
        stored_value = getattr(metric, stored_name, None)
        if stored_value not in (None, "", [], {}):
            stored_updates[output_name] = stored_value
    if stored_updates:
        generated = generated.model_copy(update=stored_updates)
    return generated.model_dump(mode="json")


def build_persisted_formula_catalog(metric_definitions: Iterable[Any]) -> list[CalculationFormula]:
    formulae = _governed_system_formulae()
    formulae.extend(CalculationFormula.model_validate(_snapshot(metric)) for metric in metric_definitions)
    return sorted(formulae, key=lambda row: (row.origin, row.name.lower(), row.code))


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _populate_metric_formula(_mapper, _connection, target: domain.ReliabilityMetricDefinition) -> None:
    snapshot = _generated_snapshot(target)
    target.formula_latex = snapshot["latex"]
    target.formula_mathml = snapshot["mathml"]
    target.formula_expression_json = snapshot["expression"]
    target.formula_unit = snapshot["unit"]
    target.formula_precision = snapshot["precision"]
    target.formula_rounding_mode = snapshot["rounding_mode"]
    target.denominator_policy = snapshot["denominator_policy"]
    target.formula_source_fields_json = snapshot["source_fields"]


def _populate_run_formula(_mapper, connection, target: domain.ReliabilityCalculationRun) -> None:
    metric_table = domain.ReliabilityMetricDefinition.__table__
    row = connection.execute(
        select(metric_table).where(metric_table.c.id == target.metric_definition_id)
    ).mappings().first()
    if row is None:
        target.formula_snapshot_json = {}
        target.formula_snapshot_hash = hashlib.sha256(b"{}").hexdigest()
        return
    snapshot = _snapshot(SimpleNamespace(**dict(row)))
    target.formula_snapshot_json = snapshot
    target.formula_snapshot_hash = _snapshot_hash(snapshot)
    lineage = dict(target.source_lineage_json or {})
    lineage["formula_snapshot_hash"] = target.formula_snapshot_hash
    lineage["formula_code"] = snapshot.get("code")
    lineage["formula_version"] = snapshot.get("version")
    target.source_lineage_json = lineage


def apply() -> None:
    if getattr(domain, "_reliability_formula_hardening_applied", False):
        return
    _attach_columns()
    event.listen(domain.ReliabilityMetricDefinition, "before_insert", _populate_metric_formula)
    event.listen(domain.ReliabilityMetricDefinition, "before_update", _populate_metric_formula)
    event.listen(domain.ReliabilityCalculationRun, "before_insert", _populate_run_formula)
    analytics_formulae.build_formula_catalog = build_persisted_formula_catalog
    domain._reliability_formula_hardening_applied = True


apply()
