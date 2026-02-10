from __future__ import annotations

from starlette.requests import Request

from amodb.apps.accounts import router_public


def _make_request(client_host: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [],
            "client": (client_host, 12345),
            "method": "POST",
            "path": "/auth/password-reset/confirm",
        }
    )


def test_client_ip_returns_request_host_without_recursion():
    request = _make_request("10.10.10.10")
    assert router_public._client_ip(request) == "10.10.10.10"


def test_enforce_auth_rate_limit_tracks_requests_per_ip_endpoint():
    router_public._RATE_LIMIT_STATE.clear()
    request = _make_request("10.0.0.1")

    for _ in range(router_public._AUTH_RATE_LIMIT_MAX_ATTEMPTS):
        router_public._enforce_auth_rate_limit(request, "password-reset-confirm")

    try:
        router_public._enforce_auth_rate_limit(request, "password-reset-confirm")
        raised = False
    except Exception as exc:  # noqa: BLE001 - explicit assertion below
        raised = True
        assert getattr(exc, "status_code", None) == 429

    assert raised is True
