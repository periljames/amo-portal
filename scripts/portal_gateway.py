"""Serve a built portal and stream same-origin API traffic for shared access."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
import re

import anyio
import httpx
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

API_PATH = re.compile(r"^/(auth|accounts|admin|billing|aircraft|work-orders|crs|training|public|quality|qms|platform|reliability|resilience|audit|audit-events|bootstrap|integrations|api|notifications|email-logs|tasks|health|healthz|livez|readyz|time|manuals|doc-control|records|foundations|rostering|workforce)(?:/|$)", re.I)
HOP_HEADERS = {b"connection", b"keep-alive", b"proxy-authenticate", b"proxy-authorization", b"te", b"trailer", b"transfer-encoding", b"upgrade"}
class NoUpstreamCookies(DefaultCookiePolicy):
    def set_ok(self, cookie, request):
        return False


class StaticCompression:
    def __init__(self, app):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        ranged = any(name.lower() == b"range" for name, _ in scope.get("headers", []))
        streaming = API_PATH.match(path) or re.match(r"^/ops(?:/|$)", path)
        await (self.app if ranged or streaming else self.compressed)(scope, receive, send)


def forwarded_headers(raw_headers):
    # Connection can nominate additional hop-by-hop headers.
    excluded = set(HOP_HEADERS)
    for name, value in raw_headers:
        if name.lower() == b"connection":
            excluded.update(part.strip().lower() for part in value.split(b","))
    return [(name, value) for name, value in raw_headers if name.lower() not in excluded]


def spa_navigation(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"} or "text/html" not in request.headers.get("accept", "").lower():
        return False
    return bool(re.match(r"^/(?:platform(?:/|$)|qms/(?:audit-access|car-access)(?:/|$)|verify/[^/]+(?:/|$))", request.url.path, re.I))


def create_app(root: Path, api_target="http://127.0.0.1:8080", ops_target="http://127.0.0.1:8090", *, transport=None, allowed_hosts=None):
    root = root.resolve()
    if not (root / "index.html").is_file():
        raise ValueError("Build the frontend before starting the shared gateway")
    static = StaticFiles(directory=root, follow_symlink=False)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, pool=10, read=180, write=180),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=24, keepalive_expiry=20),
            follow_redirects=False, trust_env=False, transport=transport,
            cookies=CookieJar(policy=NoUpstreamCookies()),
        ) as client:
            app.state.upstream = client
            yield

    async def proxy(request: Request):
        target = ops_target if re.match(r"^/ops(?:/|$)", request.url.path) else api_target
        base = httpx.URL(target.rstrip("/"))
        upstream_url = base.copy_with(raw_path=request.scope.get("raw_path", request.url.path.encode()) + (b"?" + request.scope["query_string"] if request.scope["query_string"] else b""))
        # Keep the public host so backend slash redirects and signed links do
        # not point a remote browser at its own 127.0.0.1.
        headers = forwarded_headers(request.headers.raw)
        # The backend's existing auth, tenant and CORS rules remain authoritative.
        safe_read = request.method in {"GET", "HEAD"} and request.headers.get("content-length", "0") == "0" and "transfer-encoding" not in request.headers
        def build_request():
            return request.app.state.upstream.build_request(
                request.method, upstream_url, headers=headers, content=None if safe_read else request.stream(),
            )
        try:
            try:
                response = await request.app.state.upstream.send(build_request(), stream=True)
            except (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError):
                # A stale pooled connection may reset before response headers.
                # Retry one bodyless read; never replay an upload or mutation.
                if not safe_read:
                    raise
                response = await request.app.state.upstream.send(build_request(), stream=True)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return JSONResponse({"detail": "The backend is temporarily unavailable. Please retry.", "retryable": True}, status_code=503, headers={"Retry-After": "3", "X-AMO-Proxy-Transport-Error": "1", "Cache-Control": "no-store"})
        except httpx.TimeoutException:
            # Uploads are never replayed: a failed acknowledgement may follow a commit.
            return JSONResponse({"detail": "The backend transfer stalled. Check the record before retrying an upload.", "retryable": False}, status_code=504, headers={"Cache-Control": "no-store"})
        except httpx.TransportError:
            return JSONResponse({"detail": "The backend connection was interrupted. Retry the read; check the record before repeating a write.", "retryable": safe_read}, status_code=502, headers={"X-AMO-Proxy-Transport-Error": "1", "Cache-Control": "no-store"})

        async def body():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                # A tab closing cancels the stream task. Shield cleanup so its
                # upstream socket still returns to the bounded connection pool.
                with anyio.CancelScope(shield=True):
                    await response.aclose()

        result = StreamingResponse(body(), status_code=response.status_code)
        # Uvicorn supplies the gateway's Date/Server headers itself.
        result.raw_headers = [(k, v) for k, v in forwarded_headers(response.headers.raw) if k.lower() not in {b"date", b"server"}]
        return result

    async def handle(request: Request):
        path = request.url.path
        if not spa_navigation(request) and (API_PATH.match(path) or re.match(r"^/ops(?:/|$)", path)):
            return await proxy(request)
        try:
            response = await static.get_response(request.path_params.get("path", ""), request.scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            # Missing release assets must be 404, never HTML pretending to be JS/PDF.
            if path.startswith(("/assets/", "/pdfjs/")) or (Path(path).suffix and not spa_navigation(request)):
                raise
            response = await static.get_response("index.html", request.scope)
        if path.startswith(("/assets/", "/pdfjs/")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    app = Starlette(routes=[Route("/{path:path}", handle, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])], lifespan=lifespan)
    app.add_middleware(StaticCompression)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["localhost", "127.0.0.1", "*.ts.net"])
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--api-target", default="http://127.0.0.1:8080")
    parser.add_argument("--ops-target", default="http://127.0.0.1:8090")
    parser.add_argument("--allowed-host", action="append", default=[])
    args = parser.parse_args()
    hosts = ["localhost", "127.0.0.1", "*.ts.net", *args.allowed_host]
    uvicorn.run(create_app(args.root, args.api_target, args.ops_target, allowed_hosts=hosts), host=args.host, port=args.port, timeout_keep_alive=30, timeout_graceful_shutdown=180)


if __name__ == "__main__":
    main()
