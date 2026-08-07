from decimal import Decimal

import pytest
from pydantic import ValidationError

from amodb.apps.reliability import advanced_schemas


def _payload(**overrides):
    payload = {
        "code": "TEST_METRIC",
        "name": "Test metric",
        "method": "RATE",
        "numerator_event_types": ["DEFECT"],
        "denominator_type": "FH",
        "multiplier": Decimal("100"),
        "window_days": 30,
        "schedule_interval_minutes": 1440,
        "minimum_exposure": Decimal("1"),
        "direction": "ABOVE",
        "formula_version": "1",
    }
    payload.update(overrides)
    return payload


def test_count_metrics_are_normalized_to_no_denominator_and_unit_multiplier():
    metric = advanced_schemas.MetricDefinitionCreate.model_validate(
        _payload(method="COUNT", denominator_type="FC", multiplier=1000)
    )

    assert metric.denominator_type == "NONE"
    assert metric.multiplier == Decimal("1")


def test_percent_metrics_use_event_denominator_and_require_numerator_types():
    metric = advanced_schemas.MetricDefinitionCreate.model_validate(
        _payload(method="PERCENT", denominator_type="FH")
    )

    assert metric.denominator_type == "NONE"

    with pytest.raises(ValidationError, match="require at least one numerator event type"):
        advanced_schemas.MetricDefinitionCreate.model_validate(
            _payload(method="PERCENT", numerator_event_types=[])
        )


def test_nff_rate_uses_fixed_event_contract():
    metric = advanced_schemas.MetricDefinitionCreate.model_validate(
        _payload(
            method="NFF_RATE",
            numerator_event_types=["DEFECT"],
            denominator_type="FC",
        )
    )

    assert metric.numerator_event_types == ["NO_FAULT_FOUND"]
    assert metric.denominator_type == "NONE"


def test_rate_and_mtbur_require_exposure_denominators():
    for method in ("RATE", "MTBUR"):
        with pytest.raises(ValidationError, match="require an exposure denominator"):
            advanced_schemas.MetricDefinitionCreate.model_validate(
                _payload(method=method, denominator_type="NONE")
            )
