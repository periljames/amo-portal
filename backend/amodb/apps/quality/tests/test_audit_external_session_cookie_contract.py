from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import Response

import amodb.apps.quality.audit_external_access_router as access_router
from amodb.apps.quality.audit_external_access_router import AuditAccessExchange
from amodb.apps.quality.router import public_router


def _future():
    return datetime.now(timezone.utc) + timedelta(hours=4)


def _set_cookie_headers(response: Response) -> list[str]:
    return response.headers.getlist("set-cookie")


def test_logout_clears_canonical_and_legacy_cookie_paths():
    response = Response()

    result = access_router.end_audit_access_session(response)

    assert result is response
    cookies = _set_cookie_headers(response)
    assert len(cookies) == 2
    assert any("amo_qms_audit_guest=" in cookie and "Path=/quality/audit-access" in cookie for cookie in cookies)
    assert any("amo_qms_audit_guest=" in cookie and "Path=/;" in cookie for cookie in cookies)
    assert all("Max-Age=0" in cookie for cookie in cookies)


def test_email_exchange_writes_only_canonical_cookie_path(monkeypatch):
    identity = SimpleNamespace(assurance_level="EMAIL_LINK")
    participant = SimpleNamespace(
        external_identity=identity,
        accepted_at=None,
        status="INVITED",
    )
    grant = SimpleNamespace(
        participant=participant,
        expires_at=_future(),
        last_used_at=None,
    )
    commits: list[bool] = []
    db = SimpleNamespace(commit=lambda: commits.append(True))

    monkeypatch.setattr(access_router, "_active_grant", lambda _db, _token: grant)
    monkeypatch.setattr(access_router, "_append_access_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(access_router, "_public_read_model", lambda *_args, **_kwargs: {"ok": True})

    response = Response()
    request = SimpleNamespace(url=SimpleNamespace(scheme="https"))
    payload = AuditAccessExchange(token="x" * 64)

    result = access_router.exchange_audit_access(
        payload=payload,
        request=request,
        response=response,
        db=db,
    )

    assert result == {"ok": True}
    assert commits == [True]
    cookies = _set_cookie_headers(response)
    assert len(cookies) == 1
    assert "Path=/quality/audit-access" in cookies[0]
    assert "Path=/;" not in cookies[0]


def test_logout_is_the_only_registered_external_session_delete_handler():
    handlers = [
        route
        for route in public_router.routes
        if str(getattr(route, "path", "")) == "/quality/audit-access/session"
        and "DELETE" in set(getattr(route, "methods", None) or ())
    ]

    assert len(handlers) == 1
    assert str(getattr(handlers[0], "name", "")) == "end_audit_access_session"


def test_external_session_exchange_and_fieldwork_have_one_handler_each():
    expected = {
        ("/quality/audit-access/exchange", "POST"): "exchange_audit_access",
        ("/quality/audit-access/fieldwork", "GET"): "get_external_auditor_fieldwork",
    }
    for (path, method), endpoint_name in expected.items():
        handlers = [
            route
            for route in public_router.routes
            if str(getattr(route, "path", "")) == path
            and method in set(getattr(route, "methods", None) or ())
        ]
        assert len(handlers) == 1
        assert str(getattr(handlers[0], "name", "")) == endpoint_name
