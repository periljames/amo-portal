import hashlib
import importlib.util
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

spec = importlib.util.spec_from_file_location("portal_gateway", Path(__file__).with_name("portal_gateway.py"))
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class Chunks(httpx.AsyncByteStream):
    def __init__(self, *parts):
        self.parts = parts
        self.closed = False

    async def __aiter__(self):
        for part in self.parts:
            yield part

    async def aclose(self):
        self.closed = True


@pytest.fixture
def root(tmp_path):
    (tmp_path / "index.html").write_text("<html>portal shell</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/test-12345678.js").write_bytes(b"0123456789" * 400)
    return tmp_path


def test_static_routes_ranges_and_missing_chunks(root):
    with TestClient(gateway.create_app(root), base_url="http://localhost") as client:
        assert client.get("/maintenance/amo/quality").text == "<html>portal shell</html>"
        response = client.get("/assets/test-12345678.js", headers={"Range": "bytes=10-29"})
        assert response.status_code == 206
        assert response.content == b"0123456789" * 2
        assert response.headers["content-range"] == "bytes 10-29/4000"
        assert "content-encoding" not in response.headers
        assert "immutable" in response.headers["cache-control"]
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/pdfjs/missing.wasm").status_code == 404
        assert client.get("/portal-sw.js").status_code == 404
        assert client.get("/", headers={"Host": "attacker.invalid"}).status_code == 400
        assert client.get("/", headers={"Accept-Encoding": "gzip"}).headers["cache-control"] == "no-cache"


def test_api_streams_bytes_headers_and_cookies_without_sharing_sessions(root):
    requests = []
    stream = Chunks(b"a" * 1024, b"b" * 1024)

    async def upstream(request):
        requests.append(request)
        return httpx.Response(200, stream=stream if len(requests) == 1 else Chunks(b"ok"), headers=[("set-cookie", "session=private; HttpOnly"), ("set-cookie", "csrf=one"), ("content-disposition", 'attachment; filename="evidence.pdf"'), ("connection", "keep-alive, x-hop"), ("x-hop", "remove")])

    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        response = client.get("/api/files/a/download?version=2", headers={"Authorization": "Bearer one"})
        assert response.content == b"a" * 1024 + b"b" * 1024
        assert len(response.headers.get_list("set-cookie")) == 2
        assert "x-hop" not in response.headers
        assert response.headers["content-disposition"].endswith('"evidence.pdf"')
        assert requests[0].headers["authorization"] == "Bearer one"
        assert requests[0].headers["host"] == "localhost"
        assert str(requests[0].url) == "http://127.0.0.1:8080/api/files/a/download?version=2"
        client.cookies.clear()
        client.get("/api/another-user")
        assert "cookie" not in requests[1].headers
        assert stream.closed


def test_upload_preserves_payload_and_never_replays_failure(root):
    calls = []

    async def upstream(request):
        calls.append(await request.aread())
        return httpx.Response(409, stream=Chunks(b'{"detail":"Receipt requires review"}'), headers={"content-type": "application/json"})

    payload = b"synthetic-upload" * 200000
    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        response = client.post("/api/upload", content=payload, headers={"Content-Type": "application/octet-stream"})
        assert response.status_code == 409
        assert len(calls) == 1
        assert hashlib.sha256(calls[0]).digest() == hashlib.sha256(payload).digest()


def test_disconnected_backend_returns_actionable_503_without_spa_fallback(root):
    def upstream(request):
        raise httpx.ConnectError("refused", request=request)

    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.headers["retry-after"] == "3"
        assert response.headers["x-amo-proxy-transport-error"] == "1"
        assert response.headers["cache-control"] == "no-store"


def test_stale_connection_is_retried_once_for_a_bodyless_read(root):
    calls = []
    def upstream(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("Upstream closed its idle connection", request=request)
        return httpx.Response(200, stream=Chunks(b"complete response"))
    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        response = client.get("/api/maintenance/amo/quality/reports/audit-performance?limit=30", headers={"Authorization":"Bearer test-token"})
        assert response.status_code == 200 and response.content == b"complete response"
        assert len(calls) == 2
        assert calls[0].url == calls[1].url
        assert calls[1].headers["authorization"] == "Bearer test-token"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_interrupted_mutations_return_structured_failure_without_replay(root, method):
    calls = []
    async def upstream(request):
        calls.append(await request.aread())
        raise httpx.ReadError("Acknowledgement lost", request=request)
    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        response = client.request(method, "/api/upload", content=b"uploaded once")
        assert response.status_code == 502 and response.json()["retryable"] is False
        assert calls == [b"uploaded once"]


def test_repeated_read_transport_failures_are_bounded_and_never_become_an_unhandled_500(root):
    calls = []
    def upstream(request):
        calls.append(request)
        raise httpx.ReadError("Connection reset", request=request)
    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        response = client.get("/api/report")
        assert len(calls) == 2 and response.status_code == 502
        assert response.json()["retryable"] is True


def test_public_navigation_stays_spa_while_ops_and_json_stay_api(root):
    requests = []

    def upstream(request):
        requests.append(request)
        return httpx.Response(200, stream=Chunks(b"{}"), headers={"content-type": "application/json"})

    with TestClient(gateway.create_app(root, transport=httpx.MockTransport(upstream)), base_url="http://localhost") as client:
        for path in ("/platform/control", "/qms/audit-access/token", "/qms/car-access/signed.token.value", "/verify/signed.token.value"):
            assert "portal shell" in client.get(path, headers={"Accept": "text/html"}).text
        assert not requests
        client.get("/platform/settings", headers={"Accept": "application/json"})
        client.get("/ops/readyz")
        assert requests[0].url.port == 8080
        assert requests[1].url.port == 8090
