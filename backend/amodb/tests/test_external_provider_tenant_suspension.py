"""Provider sessions must die at the parent-tenant boundary."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.procurement import external_auth_core as core


def test_suspended_parent_amo_denies_existing_partner_cookie(monkeypatch):
    from uuid import uuid4

    amo_id = str(uuid4())
    request = SimpleNamespace(cookies={core.COOKIE: amo_id + ".session-secret"})
    monkeypatch.setattr(core, "context", lambda db, *args, **kwargs: None)
    query_calls = []

    def fake_one(sql, db, **params):
        query_calls.append(sql)
        assert params["amo"] == amo_id
        return {"amo_id": amo_id, "identity_id": str(uuid4()), "tenant_active": False}

    monkeypatch.setattr(core, "one", fake_one)
    with pytest.raises(HTTPException) as exc:
        core.active_session(MagicMock(), request, required="profile.read")
    assert exc.value.status_code == 403
    assert "tenant" in str(exc.value.detail).lower()
    assert "JOIN amos" in query_calls[0]
    assert "tenant_active" in query_calls[0]


def test_session_query_uses_live_amo_suspension_state(monkeypatch):
    """No cached tenant state or previously accepted session can bypass closure."""
    from uuid import uuid4

    amo_id = str(uuid4())
    request = SimpleNamespace(cookies={core.COOKIE: amo_id + ".session-secret"})
    monkeypatch.setattr(core, "context", lambda db, *args, **kwargs: None)
    monkeypatch.setattr(core, "one", lambda *args, **kwargs: {
        "amo_id": amo_id, "identity_id": "identity", "tenant_active": False,
        "portal_state": "ACTIVE", "grant_state": "ACTIVE",
    })
    with pytest.raises(HTTPException) as exc:
        core.active_session(MagicMock(), request, required="document.read")
    assert exc.value.status_code == 403


def test_tenant_suspension_blocks_invitation_and_password_recovery_tokens(monkeypatch):
    from uuid import uuid4
    tenant_id = str(uuid4())
    identity_id = str(uuid4())
    monkeypatch.setattr(core, "context", lambda db, *args, **kwargs: None)
    stored = []
    def query(sql, db, **params):
        stored.append(sql)
        return {
            "id": str(uuid4()), "amo_id": tenant_id, "identity_id": identity_id,
            "tenant_active": False, "used_at": None, "revoked_at": None,
            "expires_at": core.now() + __import__("datetime").timedelta(hours=1),
        }
    monkeypatch.setattr(core, "one", query)
    monkeypatch.setattr(core, "run", lambda *args, **kwargs: pytest.fail("Suspended token was consumed"))
    for token_kind in ("INVITE", "PASSWORD_RESET"):
        with pytest.raises(HTTPException) as blocked:
            core.redeem_token(MagicMock(), tenant_id + ".valid-high-entropy-code", token_kind)
        assert blocked.value.status_code == 403
    assert all("JOIN amos" in sql and "tenant_active" in sql for sql in stored)
