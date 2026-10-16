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
