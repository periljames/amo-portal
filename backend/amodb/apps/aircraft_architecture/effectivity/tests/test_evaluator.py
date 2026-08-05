import pytest

from amodb.apps.aircraft_architecture.effectivity.evaluator import (
    evaluate_expression,
    impact_analysis,
)


def test_nested_expression_is_explainable():
    expression = {
        "operator": "ALL",
        "conditions": [
            {"path": "aircraft.model", "op": "in", "value": ["DHC8-311", "DHC8-315"]},
            {"path": "aircraft.serial_number", "op": "between", "value": [100, 700]},
            {
                "operator": "ANY",
                "conditions": [
                    {"path": "configuration.engines", "op": "eq", "value": 2},
                    {"path": "configuration.special_mod", "op": "eq", "value": "SB-123"},
                ],
            },
        ],
    }
    result = evaluate_expression(
        expression,
        {
            "aircraft": {"model": "dhc8-315", "serial_number": "315"},
            "configuration": {"engines": "2"},
        },
    )
    assert result.applicable is True
    assert len(result.trace) == 4
    assert result.unresolved_paths == ("configuration.special_mod",)


def test_missing_value_fails_closed_and_is_reported():
    result = evaluate_expression(
        {"path": "configuration.propeller.model", "op": "eq", "value": "14SF"},
        {"configuration": {}},
    )
    assert result.applicable is False
    assert result.unresolved_paths == ("configuration.propeller.model",)
    assert "not available" in result.trace[0].reason


def test_impact_analysis_returns_only_changed_aircraft():
    previous = {"path": "aircraft.serial_number", "op": "gte", "value": 100}
    proposed = {"path": "aircraft.serial_number", "op": "gte", "value": 200}
    changes = impact_analysis(
        previous,
        proposed,
        [
            {"registration": "5Y-AAA", "aircraft": {"serial_number": 150}},
            {"registration": "5Y-BBB", "aircraft": {"serial_number": 250}},
        ],
    )
    assert [item["context_key"] for item in changes] == ["5Y-AAA"]


def test_invalid_between_expression_is_rejected():
    with pytest.raises(ValueError, match="exactly two"):
        evaluate_expression(
            {"path": "aircraft.serial_number", "op": "between", "value": [100]},
            {"aircraft": {"serial_number": 150}},
        )
