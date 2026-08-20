from __future__ import annotations

import pytest

from amodb.apps.platform import ai_gateway


def test_catalog_defaults_to_luna_for_standard_tier() -> None:
    assert ai_gateway.DEFAULT_MODEL == "gpt-5.6-luna"
    assert ai_gateway.PLAN_DEFAULT_MODEL == {
        "STANDARD": "gpt-5.6-luna",
        "ADVANCED": "gpt-5.6-terra",
        "PROFESSIONAL": "gpt-5.6-sol",
    }
    assert [item["model"] for item in ai_gateway.model_catalog()] == [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    ]


def test_luna_cost_uses_cached_input_rate_without_float_money_rounding() -> None:
    result = ai_gateway.calculate_provider_cost(
        "gpt-5.6-luna",
        {
            "input_tokens": 5_000,
            "input_tokens_details": {"cached_tokens": 2_000},
            "output_tokens": 1_000,
            "total_tokens": 6_000,
        },
    )
    assert result["usage"] == {
        "input_tokens": 5_000,
        "cached_input_tokens": 2_000,
        "output_tokens": 1_000,
        "total_tokens": 6_000,
    }
    assert result["provider_cost_microusd"] == 1_840
    assert result["rate_snapshot"]["long_context"] is False


def test_long_context_multiplier_is_applied_to_full_request() -> None:
    result = ai_gateway.calculate_provider_cost(
        "gpt-5.6-luna",
        {
            "input_tokens": 300_000,
            "output_tokens": 1_000,
        },
    )
    assert result["provider_cost_microusd"] == 121_800
    assert result["rate_snapshot"]["input_microusd_per_million"] == 400_000
    assert result["rate_snapshot"]["output_microusd_per_million"] == 1_800_000
    assert result["rate_snapshot"]["long_context"] is True


def test_standard_policy_cannot_select_professional_model() -> None:
    with pytest.raises(PermissionError):
        ai_gateway._resolve_model(
            {"model": "gpt-5.6-luna", "max_model_tier": "STANDARD"},
            "gpt-5.6-sol",
        )


def test_unknown_model_has_no_implicit_price() -> None:
    with pytest.raises(ValueError, match="No audited price snapshot"):
        ai_gateway.calculate_provider_cost("unknown-model", {"input_tokens": 1})
