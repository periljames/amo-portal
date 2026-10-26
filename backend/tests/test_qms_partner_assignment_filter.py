"""Partner QMS deep-link filtering is an authenticated, assigned-only API."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from amodb.apps.procurement import external_partner_router


def test_unassigned_audit_is_denied_before_any_quality_record_query(monkeypatch):
    user = {
        "capabilities_json": ["task.read"],
        "object_scope_json": {"assignments": ["assigned-audit"]},
        "portal_state": "ACTIVE",
    }
    monkeypatch.setattr(external_partner_router, "_ctx", lambda *a, **k: user)
    monkeypatch.setattr(external_partner_router, "_allowed",
                        lambda u, scope: ["assigned-audit"] if scope == "assignments" else [])
    monkeypatch.setattr(external_partner_router, "_context",
                        lambda u: {"amo": "tenant-a", "provider": "provider-a", "person": "person-a"})
    db = MagicMock()
    with pytest.raises(HTTPException) as denied:
        external_partner_router.quality(
            tenant_slug="tenant-a", request=SimpleNamespace(),
            db=db, limit=20, offset=0, audit_id="another-provider-audit",
        )
    assert denied.value.status_code == 404
    db.execute.assert_not_called()


def test_no_assignment_returns_empty_qms_records(monkeypatch):
    user = {"capabilities_json": ["task.read"], "portal_state": "ACTIVE"}
    monkeypatch.setattr(external_partner_router, "_ctx", lambda *a, **k: user)
    monkeypatch.setattr(external_partner_router, "_allowed", lambda *a: [])
    monkeypatch.setattr(external_partner_router, "_context",
                        lambda u: {"amo": "tenant-a", "supplier": 7,
                                   "provider": "provider-a", "person": "person-a"})
    db = MagicMock()
    result = external_partner_router.quality(
        tenant_slug="tenant-a", request=SimpleNamespace(),
        db=db, limit=20, offset=0, audit_id=None,
    )
    assert result["cars"]["items"] == []
    assert result["notices"]["items"] == []
    db.execute.assert_not_called()
