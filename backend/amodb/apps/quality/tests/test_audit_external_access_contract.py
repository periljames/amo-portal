from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from amodb.apps.quality.audit_external_access_router import (
    AUDITEE_ALLOWED,
    EXTERNAL_AUDITOR_ALLOWED,
    ExternalParticipantCreate,
    _decode_access_token,
    _hash_token,
    _make_access_token,
    _scope_for,
)


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=4)


def test_access_token_is_signed_tenant_and_grant_bound():
    token = _make_access_token(amo_id="tenant-a", grant_id="grant-a", expires_at=_future())
    payload = _decode_access_token(token)
    assert payload["amo_id"] == "tenant-a"
    assert payload["grant_id"] == "grant-a"
    assert len(_hash_token(token)) == 64


def test_access_token_tampering_fails_before_tenant_context_can_be_used():
    token = _make_access_token(amo_id="tenant-a", grant_id="grant-a", expires_at=_future())
    payload, signature = token.split(".", 1)
    tampered = f"{payload[:-1]}A.{signature}"
    with pytest.raises(HTTPException) as exc:
        _decode_access_token(tampered)
    assert exc.value.status_code == 404


def test_access_token_expiry_is_enforced():
    token = _make_access_token(
        amo_id="tenant-a",
        grant_id="grant-a",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(HTTPException) as exc:
        _decode_access_token(token)
    assert exc.value.status_code == 404


def test_auditee_permissions_are_bounded_to_released_data_contract():
    payload = ExternalParticipantCreate(
        email="auditee@example.test",
        display_name="Auditee User",
        participant_type="AUDITEE_GUEST",
        role="AUDITEE",
        permissions=["audit:read_summary", "audit:read_released_findings", "audit:acknowledge"],
        expires_at=_future(),
    )
    scope = set(_scope_for(payload))
    assert scope <= AUDITEE_ALLOWED
    assert "audit:checklist_execute" not in scope
    assert "audit:finding_draft" not in scope


def test_external_auditor_cannot_request_auditee_only_permission():
    payload = ExternalParticipantCreate(
        email="external.auditor@example.test",
        display_name="External Auditor",
        participant_type="EXTERNAL_AUDITOR",
        role="AUDITOR",
        permissions=["audit:read_assigned", "audit:acknowledge"],
        expires_at=_future(),
    )
    with pytest.raises(HTTPException) as exc:
        _scope_for(payload)
    assert exc.value.status_code == 422
    assert "audit:acknowledge" not in EXTERNAL_AUDITOR_ALLOWED
