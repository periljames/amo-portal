from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from amodb import serve


def test_uvicorn_workers_follow_portal_api_process_count() -> None:
    with patch.dict(
        os.environ,
        {
            "PORTAL_API_PROCESS_COUNT": "4",
            "RELOAD": "false",
            "PORT": "8080",
        },
        clear=False,
    ):
        options = serve._uvicorn_options()
    assert options["workers"] == 4
    assert options["port"] == 8080
    assert options["backlog"] >= 2048


def test_reload_forces_single_worker() -> None:
    with patch.dict(
        os.environ,
        {"PORTAL_API_PROCESS_COUNT": "4", "RELOAD": "true"},
        clear=False,
    ):
        options = serve._uvicorn_options()
    assert options["workers"] == 1
    assert options["reload"] is True


def test_forwarded_proxy_trust_is_loopback_only_outside_production() -> None:
    with patch.dict(os.environ, {}, clear=True):
        options = serve._uvicorn_options()
    assert options["forwarded_allow_ips"] == "127.0.0.1"


def test_production_requires_explicit_trusted_proxy_addresses() -> None:
    with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
        with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
            serve._uvicorn_options()


def test_production_uses_configured_proxy_cidrs() -> None:
    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "FORWARDED_ALLOW_IPS": "10.42.0.0/16,10.43.0.0/16",
        },
        clear=True,
    ):
        options = serve._uvicorn_options()
    assert options["forwarded_allow_ips"] == "10.42.0.0/16,10.43.0.0/16"


def test_optional_concurrency_ceiling_is_applied_only_when_configured() -> None:
    with patch.dict(os.environ, {"UVICORN_LIMIT_CONCURRENCY": "750"}, clear=True):
        options = serve._uvicorn_options()
    assert options["limit_concurrency"] == 750
