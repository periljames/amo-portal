from __future__ import annotations

import pytest

from amodb.apps.platform import ai_gateway, ai_openai


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


def test_openai_transport_failure_is_normalized_for_gateway_callers(monkeypatch) -> None:
    def fail_request(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(ai_openai.saas_providers, "_json_request", fail_request)

    with pytest.raises(RuntimeError, match="OpenAI transport request failed") as raised:
        ai_openai.responses_request(
            secret={"api_key": "test-key"},
            config={},
            model="gpt-5.6-luna",
            instructions="Be concise.",
            prompt="Test provider failure handling.",
            max_output_tokens=64,
        )

    assert isinstance(raised.value.__cause__, OSError)