from starlette.requests import Request

from amodb.apps.realtime.services import resolve_broker_ws_url


def _request(host: str, scheme: str = "http") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/realtime/token",
        "headers": [(b"host", host.encode("utf-8"))],
        "scheme": scheme,
        "query_string": b"",
        "server": (host.split(":")[0], int(host.split(":")[1]) if ":" in host else 80),
        "client": ("127.0.0.1", 12345),
        "http_version": "1.1",
    }
    return Request(scope)


def test_resolve_broker_ws_url_rewrites_loopback_config_for_lan(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_WS_URL", "ws://127.0.0.1:8080/mqtt")

    req = _request("192.168.1.25:8080", scheme="http")
    assert resolve_broker_ws_url(req) == "ws://192.168.1.25:8080/mqtt"


def test_resolve_broker_ws_url_keeps_public_config(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_WS_URL", "wss://broker.example.com/mqtt")

    req = _request("192.168.1.25:8080", scheme="http")
    assert resolve_broker_ws_url(req) == "wss://broker.example.com/mqtt"


def test_resolve_broker_ws_url_derives_from_request_when_unset(monkeypatch):
    monkeypatch.delenv("MQTT_BROKER_WS_URL", raising=False)
    monkeypatch.setenv("MQTT_BROKER_WS_PORT", "8084")

    req = _request("10.0.0.50:8080", scheme="http")
    assert resolve_broker_ws_url(req) == "ws://10.0.0.50:8084/mqtt"
