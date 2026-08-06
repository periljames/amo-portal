from __future__ import annotations

from typing import Any

from . import advanced_schemas as schemas


class GovernedMetricDefinitionRead(schemas.MetricDefinitionRead):
    formula_latex: str
    formula_mathml: str
    formula_expression_json: dict[str, Any]
    formula_unit: str
    formula_precision: int
    formula_rounding_mode: str
    denominator_policy: str
    formula_source_fields_json: list[str]


class GovernedCalculationRunRead(schemas.CalculationRunRead):
    formula_snapshot_json: dict[str, Any]
    formula_snapshot_hash: str


def apply() -> None:
    if getattr(schemas, "_reliability_formula_schema_hardening_applied", False):
        return
    schemas.MetricDefinitionRead = GovernedMetricDefinitionRead
    schemas.CalculationRunRead = GovernedCalculationRunRead
    schemas._reliability_formula_schema_hardening_applied = True


apply()
