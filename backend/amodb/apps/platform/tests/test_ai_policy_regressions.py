from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import ai_gateway

ai_router = importlib.import_module("amodb.apps.platform.ai_router")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_policy_edit_preserves_suspended_commercial_entitlement(monkeypatch) -> None:
    effective_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
    effective_to = datetime(2026, 9, 1, tzinfo=timezone.utc)
    existing = SimpleNamespace(
        status=account_models.ModuleSubscriptionStatus.SUSPENDED,
        effective_from=effective_from,
        effective_to=effective_to,
        metadata_json='{"model":"gpt-5.6-luna"}',
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(ai_gateway, "_ai_subscription", lambda *_args, **_kwargs: existing)

    def update_modules(_db, **kwargs):
        captured.update(kwargs)
        return [{"module_code": "ai"}]

    monkeypatch.setattr(ai_router.saas_services, "update_tenant_modules", update_modules)
    monkeypatch.setattr(ai_gateway, "tenant_policy", lambda *_args, **_kwargs: {"enabled": False})

    payload = ai_router.AITenantPolicyRequest(
        enabled=False,
        plan_code="STANDARD",
        monthly_budget_microusd=250_000,
        hard_limit=True,
        allow_external_documents=True,
        markup_bps=250,
        reason="Adjust AI policy while billing suspension remains active",
    )
    ai_router.ai_tenant_policy_update(
        "tenant-1",
        payload,
        db=object(),
        user=SimpleNamespace(id="admin-1"),
    )

    change = captured["changes"][0]
    assert change["status"] == "SUSPENDED"
    assert change["effective_from"] == effective_from
    assert change["effective_to"] == effective_to
    assert change["metadata"]["monthly_budget_microusd"] == 250_000
    assert change["metadata"]["allow_external_documents"] is True
    assert change["metadata"]["markup_bps"] == 250


def test_usage_meter_bigint_migration_covers_ai_cost_and_token_counters() -> None:
    migration = (
        _repository_root()
        / "backend/amodb/alembic/versions/ai_meter_bigint_260823.py"
    )
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "1b2c3d4e6f70"' in source
    assert '"usage_meters"' in source
    assert '"used_units"' in source
    assert "existing_type=sa.Integer()" in source
    assert "type_=sa.BigInteger()" in source
