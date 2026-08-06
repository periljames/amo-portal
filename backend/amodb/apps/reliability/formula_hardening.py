from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import Column, Integer, String, Text, event, select

from . import advanced_models as domain
from .analytics_formulae import _custom_metric_formula, _system_formulae
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


def _snapshot(metric: Any) -> dict[str, Any]:
    generated = _custom_metric_formula(metric)
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
    formulae = _system_formulae()
    formulae.extend(CalculationFormula.model_validate(_snapshot(metric)) for metric in metric_definitions)
    return sorted(formulae, key=lambda row: (row.origin, row.name.lower(), row.code))


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _populate_metric_formula(_mapper, _connection, target: domain.ReliabilityMetricDefinition) -> None:
    snapshot = _snapshot(target)
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
    domain._reliability_formula_hardening_applied = True


apply()
