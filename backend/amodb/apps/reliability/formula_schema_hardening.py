from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import model_validator

from . import advanced_schemas as schemas


class GovernedMetricDefinitionCreate(schemas.MetricDefinitionCreate):
    @model_validator(mode="after")
    def normalize_method_contract(self):
        method = str(self.method or "RATE").upper()
        denominator = str(self.denominator_type or "NONE").upper()

        if method == "NFF_RATE":
            object.__setattr__(self, "numerator_event_types", ["NO_FAULT_FOUND"])
            object.__setattr__(self, "denominator_type", "NONE")
        elif method == "PERCENT":
            if not self.numerator_event_types:
                raise ValueError("PERCENT metrics require at least one numerator event type.")
            object.__setattr__(self, "denominator_type", "NONE")
        elif method == "COUNT":
            object.__setattr__(self, "denominator_type", "NONE")
            object.__setattr__(self, "multiplier", Decimal("1"))
        elif method in {"RATE", "MTBUR"} and denominator == "NONE":
            raise ValueError(f"{method} metrics require an exposure denominator.")

        return self


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
    schemas.MetricDefinitionCreate = GovernedMetricDefinitionCreate
    schemas.MetricDefinitionRead = GovernedMetricDefinitionRead
    schemas.CalculationRunRead = GovernedCalculationRunRead
    schemas._reliability_formula_schema_hardening_applied = True


apply()
