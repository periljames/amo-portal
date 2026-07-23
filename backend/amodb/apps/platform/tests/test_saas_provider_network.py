from __future__ import annotations

import socket
from unittest.mock import MagicMock

import pytest

from amodb.apps.platform import saas_provider_network, saas_providers


def _addr(address: str, port: int = 443):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/api",
        "https://10.0.0.2/api",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/api",
        "https://localhost/api",
        "https://service.internal/api",
        "https://user:password@example.com/api",
    ],
)
def test_safe_url_rejects_direct_internal_targets(url: str):
    with pytest.raises(ValueError):
        saas_provider_network.safe_url(url)


def test_dns_resolution_rejects_any_non_public_address(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        saas_provider_network.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [_addr("93.184.216.34"), _addr("10.0.0.5")],
    )

    with pytest.raises(ValueError, match="public internet addresses"):
        saas_provider_network.resolve_public_addresses("provider.example.com", 443)


def test_dns_resolution_returns_only_validated_public_addresses(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        saas_provider_network.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [_addr("93.184.216.34"), _addr("93.184.216.34")],
    )

    assert saas_provider_network.resolve_public_addresses("provider.example.com", 443) == (
        "93.184.216.34",
    )


@pytest.mark.parametrize(
    "destination",
    [
        "https://169.254.169.254/latest/meta-data",
        "http://public.example.com/downgrade",
    ],
)
def test_redirect_handler_rejects_private_or_plaintext_destination(destination: str):
    handler = saas_provider_network._SafeRedirectHandler()
    request = MagicMock()

    with pytest.raises(ValueError):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            destination,
        )


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._host = ""
        self.source_address = None
        self.calls: list[tuple[str, object]] = []
        self.__class__.instances.append(self)

    def connect(self, host, port):
        self.calls.append(("connect", (host, port, self._host)))
        return 220, b"ready"

    def ehlo(self):
        self.calls.append(("ehlo", None))
        return 250, b"hello"

    def starttls(self, *, context):
        self.calls.append(("starttls", context))
        return 220, b"tls"

    def login(self, username, password):
        self.calls.append(("login", (username, password)))
        return 235, b"authenticated"

    def noop(self):
        self.calls.append(("noop", None))
        return 250, b"ok"

    def send_message(self, message):
        self.calls.append(("send_message", message))
        return {}

    def quit(self):
        self.calls.append(("quit", None))
        return 221, b"bye"

    def close(self):
        self.calls.append(("close", None))


def _public_smtp(monkeypatch: pytest.MonkeyPatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(
        saas_provider_network,
        "resolve_public_addresses",
        lambda host, port: ("93.184.216.34",),
    )


def test_smtp_health_check_uses_starttls_and_login(monkeypatch: pytest.MonkeyPatch):
    _public_smtp(monkeypatch)
    monkeypatch.setattr(saas_provider_network.smtplib, "SMTP", FakeSMTP)

    result = saas_provider_network.smtp_health_check(
        secret={"password": "correct-password"},
        config={
            "host": "smtp.example.com",
            "port": 587,
            "username": "mailer@example.com",
            "use_tls": True,
            "use_ssl": False,
        },
    )

    client = FakeSMTP.instances[-1]
    call_names = [name for name, _ in client.calls]
    assert call_names == ["connect", "ehlo", "starttls", "ehlo", "login", "noop", "quit"]
    assert client.calls[0][1] == ("93.184.216.34", 587, "")
    assert client._host == "smtp.example.com"
    assert client.calls[4][1] == ("mailer@example.com", "correct-password")
    assert result["transport"] == "starttls"
    assert result["authenticated"] is True


def test_smtp_health_check_uses_implicit_tls_and_login(monkeypatch: pytest.MonkeyPatch):
    _public_smtp(monkeypatch)
    monkeypatch.setattr(saas_provider_network.smtplib, "SMTP_SSL", FakeSMTP)

    result = saas_provider_network.smtp_health_check(
        secret={"password": "correct-password"},
        config={
            "host": "smtp.example.com",
            "port": 465,
            "username": "mailer@example.com",
            "use_tls": False,
            "use_ssl": True,
        },
    )

    client = FakeSMTP.instances[-1]
    call_names = [name for name, _ in client.calls]
    assert call_names == ["connect", "ehlo", "login", "noop", "quit"]
    assert client.calls[0][1] == ("smtp.example.com", 465, "")
    assert callable(client._get_socket)
    assert result["transport"] == "ssl"


def test_pinned_smtp_ssl_socket_uses_validated_ip_and_original_sni(monkeypatch: pytest.MonkeyPatch):
    client = FakeSMTP()
    raw_socket = object()
    wrapped_socket = object()
    context = MagicMock()
    context.wrap_socket.return_value = wrapped_socket
    create_connection = MagicMock(return_value=raw_socket)
    monkeypatch.setattr(saas_provider_network.socket, "create_connection", create_connection)

    saas_provider_network._pin_smtp_ssl_socket(
        client,
        hostname="smtp.example.com",
        pinned_ip="93.184.216.34",
        port=465,
        context=context,
    )
    result = client._get_socket("smtp.example.com", 465, 8)

    create_connection.assert_called_once_with(("93.184.216.34", 465), 8, None)
    context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="smtp.example.com")
    assert result is wrapped_socket


def test_installed_provider_health_check_uses_hardened_smtp_path(monkeypatch: pytest.MonkeyPatch):
    sentinel = {"ok": True, "provider": "smtp", "authenticated": True}
    monkeypatch.setattr(
        saas_provider_network,
        "smtp_health_check",
        lambda **kwargs: sentinel,
    )

    assert saas_provider_network._INSTALLED is True
    assert saas_providers.check_provider(
        "smtp",
        secret={"password": "value"},
        config={"host": "smtp.example.com"},
    ) is sentinel
