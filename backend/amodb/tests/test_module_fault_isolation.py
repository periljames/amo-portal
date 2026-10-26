from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from amodb import main


def test_module_database_error_does_not_open_shared_circuit(monkeypatch):
    failures = []
    monkeypatch.setattr(main, "database_circuit", SimpleNamespace(
        allow_request=lambda: True, mark_failure=failures.append,
    ))
    error = OperationalError("SELECT module_table", {}, Exception("no such table: module_table"))

    async def fail(_request):
        raise error

    request = Request({"type": "http", "method": "GET", "path": "/quality/audits", "headers": []})
    with pytest.raises(OperationalError):
        asyncio.run(main.meter_api_calls(request, fail))
    assert failures == []


def test_stopped_module_worker_does_not_disable_api_readiness(monkeypatch):
    monkeypatch.setattr(main, "probe_database", lambda **kw: True)
    monkeypatch.setattr(main, "_migration_readiness", lambda: (True, "Ready"))
    monkeypatch.setattr(main, "portal_job_supervisor_status", lambda: {
        "enabled": True, "running": True, "families": {"quality": False, "training": True},
    })
    response = main._readiness_response()
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["jobs_ready"] is False
    assert payload["jobs"]["families"]["quality"] is False


def test_liveness_works_without_database_or_request_worker_threads(monkeypatch):
    async def no_worker(*a, **kw):
        raise AssertionError("Liveness must not wait for the database request thread pool")
    monkeypatch.setattr("fastapi.routing.run_in_threadpool", no_worker)
    monkeypatch.setattr(main, "probe_database", lambda **kw: pytest.fail("Liveness probed the database"))
    monkeypatch.setattr(main.database_circuit, "allow_request", lambda: False)

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.get("/livez")
            assert response.status_code == 200
            assert response.json() == {"status": "alive", "process": True}
    asyncio.run(check())
