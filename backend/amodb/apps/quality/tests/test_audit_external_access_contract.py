from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

import amodb.apps.quality.audit_external_access_router as access_router
import amodb.apps.quality.audit_public_collaboration_scope_router as collaboration_router
from amodb.apps.quality.audit_external_access_router import (
    AUDITEE_ALLOWED,
    EXTERNAL_AUDITOR_ALLOWED,
    ExternalParticipantCreate,
    _decode_access_token,
    _hash_token,
    _make_access_token,
    _scope_for,
)
from amodb.apps.quality.audit_external_fieldwork_router import _csrf_for_session, _require_csrf
from amodb.apps.quality.audit_external_participant_guard_router import (
    _assert_identity_assurance_stable,
    create_external_participant_guarded,
)
from amodb.apps.quality.audit_external_passkey_router import _set_guest_cookie
from amodb.apps.quality.canonical_router import router as canonical_quality_router


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


def test_external_auditor_scope_is_assignment_bounded():
    payload = ExternalParticipantCreate(
        email="external.auditor@example.test",
        display_name="External Auditor",
        participant_type="EXTERNAL_AUDITOR",
        role="AUDITOR",
        permissions=["audit:read_assigned", "audit:read_progress", "audit:checklist_execute", "audit:finding_draft"],
        expires_at=_future(),
    )
    scope = set(_scope_for(payload))
    assert scope <= EXTERNAL_AUDITOR_ALLOWED
    assert "audit:checklist_execute" in scope
    assert "audit:finding_draft" in scope
    assert "audit:read_released_findings" not in scope


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


def test_external_audit_fieldwork_csrf_is_session_bound():
    token_a = _make_access_token(amo_id="tenant-a", grant_id="grant-a", expires_at=_future())
    token_b = _make_access_token(amo_id="tenant-a", grant_id="grant-b", expires_at=_future())
    csrf_a = _csrf_for_session(token_a)
    assert len(csrf_a) == 64
    assert csrf_a != _csrf_for_session(token_b)
    _require_csrf(token_a, csrf_a)
    with pytest.raises(HTTPException) as exc:
        _require_csrf(token_a, _csrf_for_session(token_b))
    assert exc.value.status_code == 403


def test_unimplemented_mfa_and_auditee_passkey_fail_closed_before_db_write():
    cases = (
        ("MFA", "EXTERNAL_AUDITOR"),
        ("PASSKEY", "AUDITEE_GUEST"),
    )
    for assurance, participant_type in cases:
        payload = ExternalParticipantCreate(
            email=f"{assurance.lower()}.{participant_type.lower()}@example.test",
            display_name="External Participant",
            participant_type=participant_type,
            role="AUDITOR" if participant_type == "EXTERNAL_AUDITOR" else "AUDITEE",
            assurance_level=assurance,
            expires_at=_future(),
        )
        with pytest.raises(HTTPException) as exc:
            create_external_participant_guarded(
                audit_id=__import__("uuid").uuid4(),
                payload=payload,
                ctx=None,
                db=None,
            )
        assert exc.value.status_code == 422


def test_existing_external_identity_assurance_cannot_be_silently_changed():
    _assert_identity_assurance_stable("PASSKEY", "PASSKEY")
    _assert_identity_assurance_stable("EMAIL_LINK", "EMAIL_LINK")

    for existing, requested in (("PASSKEY", "EMAIL_LINK"), ("EMAIL_LINK", "PASSKEY")):
        with pytest.raises(HTTPException) as exc:
            _assert_identity_assurance_stable(existing, requested)
        assert exc.value.status_code == 409


def test_guarded_external_participant_creation_precedes_legacy_handler():
    routes = [
        route
        for route in canonical_quality_router.routes
        if str(getattr(route, "path", "")).endswith("/external-participants")
        and "POST" in set(getattr(route, "methods", None) or ())
    ]
    names = [str(getattr(route, "name", "")) for route in routes]
    assert "create_external_participant_guarded" in names
    if "create_external_participant" in names:
        assert names.index("create_external_participant_guarded") < names.index("create_external_participant")


def test_regular_exchange_rejects_passkey_external_auditor_before_session_mutation(monkeypatch):
    identity = SimpleNamespace(assurance_level="PASSKEY")
    participant = SimpleNamespace(
        participant_type="EXTERNAL_AUDITOR",
        external_identity=identity,
        accepted_at=None,
        status="INVITED",
    )
    grant = SimpleNamespace(participant=participant, last_used_at=None)
    commits: list[bool] = []
    db = SimpleNamespace(commit=lambda: commits.append(True))
    monkeypatch.setattr(access_router, "_active_grant", lambda _db, _token: grant)

    response = Response()
    request = SimpleNamespace(url=SimpleNamespace(scheme="https"))
    payload = access_router.AuditAccessExchange(token="x" * 32)

    with pytest.raises(HTTPException) as exc:
        access_router.exchange_audit_access(payload=payload, request=request, response=response, db=db)

    assert exc.value.status_code == 403
    assert "passkey assurance" in str(exc.value.detail).lower()
    assert grant.last_used_at is None
    assert participant.accepted_at is None
    assert participant.status == "INVITED"
    assert commits == []
    assert response.headers.get("set-cookie") is None


def test_passkey_session_cookie_uses_same_path_as_logout():
    response = Response()
    request = SimpleNamespace(url=SimpleNamespace(scheme="https"))
    _set_guest_cookie(response, request, "x" * 64, _future())
    cookie = response.headers.get("set-cookie") or ""
    assert "Path=/quality/audit-access" in cookie
    assert "Path=/;" not in cookie


def test_document_only_grant_cannot_query_collaboration_summary(monkeypatch):
    participant = SimpleNamespace(participant_type="AUDITEE_GUEST")
    grant = SimpleNamespace(
        participant=participant,
        scope_json=["audit:document_submit"],
        amo_id="tenant-a",
        audit_id=__import__("uuid").uuid4(),
    )

    monkeypatch.setattr(collaboration_router, "_active_grant", lambda _db, _token: grant)

    def unexpected_query(*_args, **_kwargs):
        pytest.fail("A document-only grant must not query meetings, closing narrative, or CAR data.")

    db = SimpleNamespace(query=unexpected_query)
    result = collaboration_router.get_public_occurrence_collaboration_scoped(
        db=db,
        amo_qms_audit_guest="x" * 64,
    )

    assert result == {"meetings": [], "cars": [], "closing_narrative": {}}
