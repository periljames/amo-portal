from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from amodb.apps.platform import ai_execution_policy, ai_gateway, ai_openai


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


def test_hard_budget_caps_customer_charge_at_remaining_amount() -> None:
    assert ai_gateway._bounded_customer_charge(
        20,
        used_microusd=90,
        budget_microusd=100,
        hard_limit=True,
    ) == 10
    assert ai_gateway._bounded_customer_charge(
        20,
        used_microusd=100,
        budget_microusd=100,
        hard_limit=True,
    ) == 0


def test_soft_budget_does_not_cap_measured_charge() -> None:
    assert ai_gateway._bounded_customer_charge(
        20,
        used_microusd=90,
        budget_microusd=100,
        hard_limit=False,
    ) == 20


def test_subscription_effective_period_controls_current_entitlement() -> None:
    now = datetime(2026, 8, 23, 9, 30, tzinfo=timezone.utc)
    active = SimpleNamespace(
        effective_from=now - timedelta(days=1),
        effective_to=now + timedelta(days=1),
    )
    scheduled = SimpleNamespace(
        effective_from=now + timedelta(seconds=1),
        effective_to=None,
    )
    expired = SimpleNamespace(
        effective_from=now - timedelta(days=2),
        effective_to=now,
    )
    naive_scheduled = SimpleNamespace(
        effective_from=(now + timedelta(hours=1)).replace(tzinfo=None),
        effective_to=None,
    )

    assert ai_gateway._subscription_is_current(active, "ENABLED", now=now) is True
    assert ai_gateway._subscription_is_current(active, "TRIAL", now=now) is True
    assert ai_gateway._subscription_is_current(active, "SUSPENDED", now=now) is False
    assert ai_gateway._subscription_is_current(scheduled, "ENABLED", now=now) is False
    assert ai_gateway._subscription_is_current(expired, "ENABLED", now=now) is False
    assert ai_gateway._subscription_is_current(naive_scheduled, "ENABLED", now=now) is False


def test_provider_model_mismatch_records_tenant_cost_and_audited_rejection(monkeypatch) -> None:
    class FakeDB:
        def __init__(self) -> None:
            self.commit_count = 0

        def commit(self) -> None:
            self.commit_count += 1

    db = FakeDB()
    recorded_usage: dict[str, object] = {}
    audits: list[dict[str, object]] = []
    policy = {
        "enabled": True,
        "provider": "openai",
        "allow_external_documents": True,
        "monthly_budget_microusd": 100_000,
        "hard_limit": True,
        "model": "gpt-5.6-luna",
        "max_model_tier": "STANDARD",
        "markup_bps": 0,
    }
    credential = SimpleNamespace(config_json={}, tenant_id=None)

    monkeypatch.setattr(ai_gateway, "tenant_policy", lambda *_args, **_kwargs: policy)
    monkeypatch.setattr(ai_gateway, "_meter_value", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        ai_gateway.saas_services,
        "get_provider_credential",
        lambda *_args, **_kwargs: credential,
    )
    monkeypatch.setattr(
        ai_gateway.saas_services,
        "require_operational_provider",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(ai_gateway.saas_services, "provider_secrets", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(ai_gateway, "operation_span", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(ai_gateway, "record_provider_call", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ai_gateway.ai_openai,
        "responses_request",
        lambda **_kwargs: {
            "response_id": "resp-mismatch",
            "model": "unexpected-model",
            "text": "discard this provider response",
            "usage": {"input_tokens": 1_000, "output_tokens": 100},
        },
    )

    def record_usage(_db, **kwargs):
        recorded_usage.update(kwargs)
        return 0, 0

    monkeypatch.setattr(ai_gateway, "_record_tenant_usage", record_usage)
    monkeypatch.setattr(ai_gateway, "_audit", lambda _db, **kwargs: audits.append(kwargs))

    base_run_ai = ai_execution_policy._ORIGINAL_RUN_AI
    assert base_run_ai is not None
    with pytest.raises(RuntimeError, match="does not match requested rated model"):
        base_run_ai(
            db,
            prompt="Test governed mismatch accounting.",
            instructions="Be concise.",
            actor_user_id="user-1",
            tenant_id="tenant-1",
            billing_scope="TENANT",
        )

    assert recorded_usage["tenant_id"] == "tenant-1"
    assert recorded_usage["usage"] == {
        "input_tokens": 1_000,
        "cached_input_tokens": 0,
        "output_tokens": 100,
        "total_tokens": 1_100,
    }
    assert recorded_usage["provider_cost_microusd"] == 320
    assert recorded_usage["customer_charge_microusd"] == 0
    assert len(audits) == 1
    assert audits[0]["action"] == "ai.request.rejected"
    assert audits[0]["details"]["rated_model"] == "gpt-5.6-luna"
    assert audits[0]["details"]["provider_model"] == "unexpected-model"
    assert audits[0]["details"]["provider_cost_microusd"] == 320
    assert audits[0]["details"]["customer_charge_microusd"] == 0
    assert db.commit_count == 1


def test_managed_openai_request_ignores_configured_alternate_base_url(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def request(url, **kwargs):
        observed["url"] = url
        observed["headers"] = kwargs["headers"]
        return 200, {
            "id": "resp-1",
            "model": "gpt-5.6-luna",
            "output_text": "ok",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }, 1.0

    monkeypatch.setattr(ai_openai.saas_providers, "_json_request", request)
    ai_openai.responses_request(
        secret={"api_key": "test-key"},
        config={"api_base_url": "https://attacker.example", "project": "proj-1"},
        model="gpt-5.6-luna",
        instructions="Be concise.",
        prompt="Test fixed provider endpoint.",
        max_output_tokens=64,
    )

    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert observed["headers"]["OpenAI-Project"] == "proj-1"


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
