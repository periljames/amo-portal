from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from amodb.apps.platform import ai_execution_policy, ai_gateway


def _result(**overrides):
    value = {"provider": "openai", "text": "ok"}
    value.update(overrides)
    return value


def test_platform_only_ai_does_not_require_tenant_data_authority(monkeypatch) -> None:
    original = MagicMock(return_value=_result())
    access = MagicMock()
    monkeypatch.setattr(ai_execution_policy, "_ORIGINAL_RUN_AI", original)
    monkeypatch.setattr(ai_execution_policy.ai_access, "require_tenant_data_access", access)

    result = ai_gateway.run_ai(
        MagicMock(),
        prompt="test",
        instructions="test",
        actor_user_id="platform-user",
        tenant_id=None,
        billing_scope="PLATFORM_TEST",
    )

    assert result["text"] == "ok"
    access.assert_not_called()
    original.assert_called_once()


def test_any_tenant_scoped_ai_requires_actor_authority(monkeypatch) -> None:
    original = MagicMock(return_value=_result())
    monkeypatch.setattr(ai_execution_policy, "_ORIGINAL_RUN_AI", original)

    with pytest.raises(PermissionError, match="authenticated actor"):
        ai_gateway.run_ai(
            MagicMock(),
            prompt="test",
            instructions="test",
            actor_user_id=None,
            tenant_id="tenant-a",
            billing_scope="PLATFORM",
        )

    original.assert_not_called()


def test_tenant_scoped_platform_funded_ai_still_checks_tenant_access(monkeypatch) -> None:
    db = MagicMock()
    original = MagicMock(return_value=_result())
    access = MagicMock(return_value="support-session-1")
    monkeypatch.setattr(ai_execution_policy, "_ORIGINAL_RUN_AI", original)
    monkeypatch.setattr(ai_execution_policy.ai_access, "require_tenant_data_access", access)

    result = ai_gateway.run_ai(
        db,
        prompt="tenant support text",
        instructions="draft only",
        actor_user_id="platform-user",
        tenant_id="tenant-a",
        billing_scope="PLATFORM",
    )

    assert result["text"] == "ok"
    access.assert_called_once_with(
        db,
        tenant_id="tenant-a",
        actor_user_id="platform-user",
    )
    original.assert_called_once()


def test_denied_tenant_scope_never_reaches_provider_gateway(monkeypatch) -> None:
    original = MagicMock(return_value=_result())
    monkeypatch.setattr(ai_execution_policy, "_ORIGINAL_RUN_AI", original)
    monkeypatch.setattr(
        ai_execution_policy.ai_access,
        "require_tenant_data_access",
        MagicMock(side_effect=PermissionError("tenant mismatch")),
    )

    with pytest.raises(PermissionError, match="tenant mismatch"):
        ai_gateway.run_ai(
            MagicMock(),
            prompt="tenant text",
            instructions="test",
            actor_user_id="user-a",
            tenant_id="tenant-b",
            billing_scope="TENANT",
        )

    original.assert_not_called()
