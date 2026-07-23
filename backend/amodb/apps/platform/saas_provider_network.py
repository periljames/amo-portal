from __future__ import annotations

import http.client
import ipaddress
import json
import smtplib
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from types import MethodType
from typing import Any, Callable

from . import saas_providers


_INSTALLED = False
_ORIGINAL_CHECK_PROVIDER: Callable[..., dict[str, Any]] | None = None


def _public_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise ValueError("Provider endpoints must resolve only to public internet addresses")
    return str(address)


def _validate_hostname(hostname: str) -> str:
    clean = hostname.strip().rstrip(".").lower()
    if not clean:
        raise ValueError("Provider endpoint hostname is required")
    if clean == "localhost" or clean.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Provider endpoints cannot target local or internal hostnames")
    try:
        _public_ip(clean)
    except ValueError as exc:
        # A syntactically valid IP that is not public must stay rejected. A DNS
        # name is resolved and pinned immediately before opening the connection.
        try:
            ipaddress.ip_address(clean)
        except ValueError:
            if "." not in clean:
                raise ValueError("Provider endpoints must use a public fully-qualified hostname") from exc
        else:
            raise
    return clean


def safe_url(url: str, *, allowed_schemes: tuple[str, ...] = ("https",)) -> str:
    value = str(url or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        schemes = ", ".join(sorted(allowed_schemes))
        raise ValueError(f"Provider endpoint must be an absolute URL using: {schemes}")
    if parsed.username or parsed.password:
        raise ValueError("Provider endpoint URLs cannot contain embedded credentials")
    _validate_hostname(parsed.hostname)
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Provider endpoint port is invalid") from exc
    return value.rstrip("/")


def resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    host = _validate_hostname(hostname)
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Provider endpoint hostname could not be resolved: {host}") from exc
    addresses: list[str] = []
    for row in rows:
        raw = str(row[4][0])
        address = _public_ip(raw)
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ValueError("Provider endpoint did not resolve to a public address")
    return tuple(addresses)


def _endpoint(url: str, allowed_schemes: tuple[str, ...]) -> tuple[str, str, int, str]:
    clean = safe_url(url, allowed_schemes=allowed_schemes)
    parsed = urllib.parse.urlsplit(clean)
    assert parsed.hostname is not None
    port = int(parsed.port or (443 if parsed.scheme.lower() == "https" else 80))
    pinned_ip = resolve_public_addresses(parsed.hostname, port)[0]
    return clean, parsed.hostname, port, pinned_ip


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, *, pinned_ip: str, **kwargs: Any) -> None:
        self._pinned_ip = pinned_ip
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, *, pinned_ip: str, **kwargs: Any) -> None:
        self._pinned_ip = pinned_ip
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _SafeHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, request: urllib.request.Request):
        _, _, _, pinned_ip = _endpoint(request.full_url, ("http",))

        def factory(host: str, **kwargs: Any) -> _PinnedHTTPConnection:
            return _PinnedHTTPConnection(host, pinned_ip=pinned_ip, **kwargs)

        return self.do_open(factory, request)


class _SafeHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request: urllib.request.Request):
        _, _, _, pinned_ip = _endpoint(request.full_url, ("https",))

        def factory(host: str, **kwargs: Any) -> _PinnedHTTPSConnection:
            return _PinnedHTTPSConnection(host, pinned_ip=pinned_ip, **kwargs)

        return self.do_open(
            factory,
            request,
            context=self._context,
            check_hostname=self._check_hostname,
        )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # Provider calls begin on HTTPS and may not downgrade to plaintext.
        safe_url(newurl, allowed_schemes=("https",))
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | bytes | None = None,
    timeout: float = 8.0,
) -> tuple[int, dict[str, Any] | list[Any] | str, float]:
    clean = safe_url(url)
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
        effective_headers = {"Content-Type": "application/json", **(headers or {})}
    else:
        data = body
        effective_headers = headers or {}
    request = urllib.request.Request(
        clean,
        data=data,
        method=method,
        headers=effective_headers,
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _SafeHTTPHandler(),
        _SafeHTTPSHandler(context=ssl.create_default_context()),
        _SafeRedirectHandler(),
    )
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=max(1.0, min(timeout, 20.0))) as response:
            raw = response.read(2 * 1024 * 1024)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read(2 * 1024 * 1024)
        status = int(exc.code)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed: dict[str, Any] | list[Any] | str = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = text[:4000]
    return status, parsed, elapsed_ms


def _smtp_context(config: dict[str, Any]) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if bool(config.get("allow_self_signed")):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _pin_smtp_ssl_socket(
    client: smtplib.SMTP_SSL,
    *,
    hostname: str,
    pinned_ip: str,
    port: int,
    context: ssl.SSLContext,
) -> None:
    def pinned_get_socket(self, _host: str, _port: int, timeout: float):
        sock = socket.create_connection(
            (pinned_ip, port),
            timeout,
            self.source_address,
        )
        return context.wrap_socket(sock, server_hostname=hostname)

    client._get_socket = MethodType(pinned_get_socket, client)  # type: ignore[method-assign]


def open_smtp_client(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    timeout: float,
) -> smtplib.SMTP:
    host = _validate_hostname(str(config.get("host") or ""))
    use_ssl = bool(config.get("use_ssl"))
    use_tls = bool(config.get("use_tls", True))
    port = int(config.get("port") or (465 if use_ssl else 587))
    pinned_ip = resolve_public_addresses(host, port)[0]
    context = _smtp_context(config)
    if use_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(timeout=timeout, context=context)
        _pin_smtp_ssl_socket(
            client,
            hostname=host,
            pinned_ip=pinned_ip,
            port=port,
            context=context,
        )
        client.connect(host, port)
    else:
        client = smtplib.SMTP(timeout=timeout)
        client.connect(pinned_ip, port)
        # STARTTLS validates the configured hostname even though TCP is pinned.
        client._host = host
    try:
        code, _ = client.ehlo()
        if int(code) >= 400:
            raise RuntimeError(f"SMTP EHLO failed ({code})")
        if use_tls and not use_ssl:
            client.starttls(context=context)
            code, _ = client.ehlo()
            if int(code) >= 400:
                raise RuntimeError(f"SMTP EHLO after STARTTLS failed ({code})")
        username = str(config.get("username") or "").strip()
        password = str(secret.get("password") or "")
        if username:
            if not password:
                raise ValueError("SMTP password is required when username is configured")
            client.login(username, password)
        return client
    except Exception:
        try:
            client.close()
        finally:
            raise


def _close_smtp(client: smtplib.SMTP) -> None:
    try:
        client.quit()
    except Exception:
        client.close()


def smtp_health_check(*, secret: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    client = open_smtp_client(secret=secret, config=config, timeout=8)
    try:
        code, _ = client.noop()
        if int(code) >= 400:
            raise RuntimeError(f"SMTP health check failed ({code})")
    finally:
        _close_smtp(client)
    return {
        "ok": True,
        "provider": "smtp",
        "transport": "ssl" if bool(config.get("use_ssl")) else "starttls" if bool(config.get("use_tls", True)) else "plain",
        "authenticated": bool(str(config.get("username") or "").strip()),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def send_smtp_email(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    to_email: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    username = str(config.get("username") or "").strip()
    from_email = str(config.get("from_email") or username).strip()
    if not from_email or not str(to_email or "").strip():
        raise ValueError("SMTP from_email and recipient are required")
    started = time.perf_counter()
    client = open_smtp_client(secret=secret, config=config, timeout=10)
    try:
        message = EmailMessage()
        message["From"] = f"{config.get('from_name')} <{from_email}>" if config.get("from_name") else from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        client.send_message(message)
    finally:
        _close_smtp(client)
    return {
        "provider": "smtp",
        "recipient": to_email,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def install_provider_network_hardening() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_PROVIDER
    if _INSTALLED:
        return
    _ORIGINAL_CHECK_PROVIDER = saas_providers.check_provider
    saas_providers._safe_url = safe_url
    saas_providers._json_request = json_request
    saas_providers.send_smtp_email = send_smtp_email

    def hardened_check_provider(
        provider: str,
        *,
        secret: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if str(provider or "").strip().lower() == "smtp":
            return smtp_health_check(secret=secret, config=config)
        assert _ORIGINAL_CHECK_PROVIDER is not None
        return _ORIGINAL_CHECK_PROVIDER(provider, secret=secret, config=config)

    saas_providers.check_provider = hardened_check_provider
    _INSTALLED = True
