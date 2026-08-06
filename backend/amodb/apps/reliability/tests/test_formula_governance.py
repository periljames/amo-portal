from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from amodb.apps.reliability import advanced_models, advanced_schemas
from amodb.apps.reliability.formula_hardening import (
    _governed_metric_formula,
    _governed_system_formulae,
    _populate_metric_formula,
    _snapshot,
    _snapshot_hash,
    build_persisted_formula_catalog,
)


def _metric(**overrides):
    values = {
        "code": "DEFECT_RATE_100FH",
        "name": "Defect rate per 100 flight hours",
        "description": "Counts qualifying defects against recorded flight-hour exposure.",
        "method": "RATE",
        "numerator_event_types": ["DEFECT", "REPEAT_DEFECT"],
        "denominator_type": "FH",
        "multiplier": 100,
        "minimum_exposure": 10,
        "direction": "ABOVE",
        "formula_version": "3",
        "formula_latex": None,
        "formula_mathml": None,
        "formula_expression_json": None,
        "formula_unit": None,
        "formula_precision": None,
        "formula_rounding_mode": None,
        "denominator_policy": None,
        "formula_source_fields_json": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_system_formulae_are_structured_and_match_guarded_dispatch_calculation():
    formulae = {formula.code: formula for formula in _governed_system_formulae()}
    dispatch = formulae["dispatch_reliability_pct"]

    assert "\\frac" in dispatch.latex
    assert "\\max" in dispatch.latex
    assert "<math" in dispatch.mathml
    assert "<mfrac>" in dispatch.mathml
    assert dispatch.expression["op"] == "multiply"
    assert dispatch.expression["left"]["numerator"]["op"] == "maximum"
    assert dispatch.denominator_policy
    assert dispatch.source_fields


def test_programme_rate_formula_has_latex_mathml_and_expression_tree():
    formula = _governed_metric_formula(_metric())

    assert formula.code == "programme.DEFECT_RATE_100FH"
    assert formula.version == "3"
    assert "\\frac" in formula.latex
    assert "<mfrac>" in formula.mathml
    assert formula.expression["op"] == "multiply"
    assert formula.expression["left"]["denominator"] == {"op": "exposure", "type": "FH"}
    assert formula.unit == "events / 100 FH"


def test_percent_formula_uses_all_reliability_events_as_execution_denominator():
    formula = _governed_metric_formula(_metric(method="PERCENT", denominator_type="FC"))

    assert formula.unit == "%"
    assert formula.expression["left"]["numerator"]["event_types"] == ["DEFECT", "REPEAT_DEFECT"]
    assert formula.expression["left"]["denominator"] == {"op": "count", "event_types": []}
    assert "all reliability events" in (formula.denominator_label or "").lower()


def test_nff_formula_matches_execution_event_contract():
    formula = _governed_metric_formula(
        _metric(method="NFF_RATE", numerator_event_types=["DEFECT"], denominator_type="FH")
    )

    assert formula.unit == "%"
    assert formula.expression["left"]["numerator"]["event_types"] == ["NO_FAULT_FOUND"]
    assert formula.expression["left"]["denominator"]["event_types"] == ["UNSCHEDULED_REMOVAL"]
    assert formula.denominator_label == "Unscheduled-removal events"


def test_mtbur_formula_reverses_exposure_and_event_count():
    formula = _governed_metric_formula(_metric(method="MTBUR", denominator_type="FH"))

    assert formula.expression["op"] == "divide"
    assert formula.expression["numerator"] == {"op": "exposure", "type": "FH"}
    assert formula.expression["denominator"]["op"] == "count"
    assert formula.unit == "FH / event"


def test_persisted_metric_values_override_regenerated_display_values():
    metric = _metric(
        formula_latex=r"R=\\frac{N_D}{FH}\\times100",
        formula_mathml='<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>N_D</mi><mi>FH</mi></mfrac></math>',
        formula_expression_json={"op": "controlled"},
        formula_unit="defects / 100 FH",
        formula_precision=4,
        formula_rounding_mode="HALF_EVEN",
        denominator_policy="Withhold below 10 FH.",
        formula_source_fields_json=["reliability_events.id", "aircraft_usage.block_hours"],
    )
    snapshot = _snapshot(metric)

    assert snapshot["latex"] == metric.formula_latex
    assert snapshot["mathml"] == metric.formula_mathml
    assert snapshot["expression"] == {"op": "controlled"}
    assert snapshot["precision"] == 4
    assert snapshot["rounding_mode"] == "HALF_EVEN"
    assert snapshot["source_fields"] == metric.formula_source_fields_json
    assert len(_snapshot_hash(snapshot)) == 64


def test_metric_insert_and_update_hooks_regenerate_formula_storage_fields():
    metric = _metric()
    _populate_metric_formula(None, None, metric)

    assert metric.formula_latex
    assert "<math" in metric.formula_mathml
    assert metric.formula_expression_json
    assert metric.formula_unit == "events / 100 FH"
    assert metric.formula_precision == 3
    assert metric.formula_rounding_mode == "HALF_UP"
    assert metric.denominator_policy
    assert metric.formula_source_fields_json

    metric.method = "COUNT"
    metric.denominator_type = "NONE"
    metric.formula_version = "4"
    _populate_metric_formula(None, None, metric)

    assert "\\frac" not in metric.formula_latex
    assert metric.formula_expression_json == {
        "op": "count",
        "event_types": ["DEFECT", "REPEAT_DEFECT"],
    }
    assert metric.formula_unit == "count"


def test_formula_catalog_uses_persisted_programme_formulae():
    metric = _metric(
        formula_latex=r"CUSTOM=\\frac{A}{B}",
        formula_mathml='<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>A</mi><mi>B</mi></mfrac></math>',
        formula_expression_json={"op": "custom"},
        formula_unit="custom unit",
        formula_precision=2,
        formula_rounding_mode="HALF_UP",
        denominator_policy="Controlled custom denominator.",
        formula_source_fields_json=["source.a", "source.b"],
    )
    formulae = build_persisted_formula_catalog([metric])
    custom = next(formula for formula in formulae if formula.code == "programme.DEFECT_RATE_100FH")

    assert custom.latex == metric.formula_latex
    assert custom.mathml == metric.formula_mathml
    assert custom.expression == {"op": "custom"}
    assert custom.unit == "custom unit"


def test_formula_columns_and_api_schema_fields_are_registered():
    metric_columns = advanced_models.ReliabilityMetricDefinition.__table__.c
    run_columns = advanced_models.ReliabilityCalculationRun.__table__.c

    for name in (
        "formula_latex",
        "formula_mathml",
        "formula_expression_json",
        "formula_unit",
        "formula_precision",
        "formula_rounding_mode",
        "denominator_policy",
        "formula_source_fields_json",
    ):
        assert name in metric_columns
        assert name in advanced_schemas.MetricDefinitionRead.model_fields

    for name in ("formula_snapshot_json", "formula_snapshot_hash"):
        assert name in run_columns
        assert name in advanced_schemas.CalculationRunRead.model_fields


def test_postgresql_migration_exposes_formula_snapshot_columns():
    database_url = os.getenv("RELIABILITY_FORMULA_SCHEMA_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL formula schema check requires RELIABILITY_FORMULA_SCHEMA_DATABASE_URL.")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        metric_columns = set(connection.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'reliability_metric_definitions'
        """)).scalars())
        run_columns = set(connection.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'reliability_calculation_runs'
        """)).scalars())
        constraints = set(connection.execute(text("""
            SELECT conname FROM pg_constraint
            WHERE conrelid IN (
                'reliability_metric_definitions'::regclass,
                'reliability_calculation_runs'::regclass
            )
        """)).scalars())

    assert "formula_latex" in metric_columns
    assert "formula_mathml" in metric_columns
    assert "formula_expression_json" in metric_columns
    assert "formula_snapshot_json" in run_columns
    assert "formula_snapshot_hash" in run_columns
    assert "ck_reliability_metric_formula_latex_present" in constraints
    assert "ck_reliability_metric_formula_mathml_present" in constraints
    assert "ck_reliability_formula_snapshot_hash_format" in constraints
