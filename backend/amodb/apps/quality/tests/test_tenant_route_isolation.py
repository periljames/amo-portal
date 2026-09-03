from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from amodb.apps.quality import tenant_security


def test_quality_tenant_context_rejects_user_from_another_amo(monkeypatch) -> None:
    db = MagicMock()
    amo = SimpleNamespace(id="amo-b")
    user = SimpleNamespace(
        id="user-a",
        amo_id="amo-a",
        effective_amo_id="amo-a",
        is_superuser=False,
        is_platform_context=False,
    )
    monkeypatch.setattr(tenant_security, "_resolve_amo", lambda _db, _code: amo)

    with pytest.raises(HTTPException) as exc:
        tenant_security._resolve_tenant_context_impl(
            amo_code="tenant-b",
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 403
    assert "not a member" in str(exc.value.detail).lower()


def test_quality_tenant_context_uses_resolved_tenant_not_url_claim(monkeypatch) -> None:
    db = MagicMock()
    amo = SimpleNamespace(id="amo-a")
    user = SimpleNamespace(
        id="user-a",
        amo_id="amo-a",
        effective_amo_id="amo-a",
        is_superuser=False,
        is_platform_context=False,
    )
    applied = {}
    monkeypatch.setattr(tenant_security, "_resolve_amo", lambda _db, _code: amo)
    monkeypatch.setattr(
        tenant_security,
        "set_postgres_tenant_context",
        lambda _db, *, amo_id, user_id: applied.update({"amo_id": amo_id, "user_id": user_id}),
    )

    context = tenant_security._resolve_tenant_context_impl(
        amo_code="tenant-a",
        current_user=user,
        db=db,
    )

    assert context.amo_id == "amo-a"
    assert context.user_id == "user-a"
    assert applied == {"amo_id": "amo-a", "user_id": "user-a"}


def test_platform_superuser_requires_active_support_session(monkeypatch) -> None:
    db = MagicMock()
    amo = SimpleNamespace(id="amo-a")
    user = SimpleNamespace(
        id="platform-user",
        amo_id=None,
        effective_amo_id=None,
        is_superuser=True,
        is_platform_context=True,
    )
    monkeypatch.setattr(tenant_security, "_resolve_amo", lambda _db, _code: amo)
    monkeypatch.setattr(tenant_security, "_active_support_session", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc:
        tenant_security._resolve_tenant_context_impl(
            amo_code="tenant-a",
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 403
    assert "support session" in str(exc.value.detail).lower()


def test_capability_store_failure_fails_closed() -> None:
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.execute.side_effect = OperationalError("authorization lookup", {}, Exception("database unavailable"))

    with pytest.raises(HTTPException) as exc:
        tenant_security._has_capability_permission(
            db,
            amo_id="amo-a",
            user_id="user-a",
            permission="qms.audit.manage",
        )

    assert exc.value.status_code == 503
    assert "could not be verified" in str(exc.value.detail).lower()
