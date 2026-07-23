from __future__ import annotations

from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.platform import (
    saas_execution_policy,
    saas_queue,
    saas_services,
    tenant_saas_job_router,
)


def _job_query(rows: list[object]) -> MagicMock:
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = rows
    return query


def test_tenant_job_router_remains_importable_as_a_module() -> None:
    assert isinstance(tenant_saas_job_router, ModuleType)
    assert callable(tenant_saas_job_router.job_status)
    assert tenant_saas_job_router.router.prefix == "/tenant-saas"


@pytest.mark.parametrize("status", ["DISABLED", "NOT_CONFIGURED", "UNHEALTHY", ""])
def test_disabled_provider_statuses_are_not_operational(status: str) -> None:
    with pytest.raises(ValueError, match="disabled or not operational"):
        saas_execution_policy.require_operational_provider(
            SimpleNamespace(status=status),
            label="OpenAI",
        )


@pytest.mark.parametrize("status", ["CONFIGURED", "HEALTHY"])
def test_configured_or_healthy_provider_is_operational(status: str) -> None:
    saas_execution_policy.require_operational_provider(
        SimpleNamespace(status=status),
        label="OpenAI",
    )


def test_disabled_etims_provider_cannot_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(amo_id="amo-1")
    monkeypatch.setattr(
        saas_services,
        "get_provider_credential",
        MagicMock(return_value=SimpleNamespace(status="DISABLED")),
    )

    with pytest.raises(ValueError, match="eTIMS provider is disabled"):
        saas_services.enqueue_fiscalization(
            db,
            invoice_id="invoice-1",
            provider="etims_oscu",
            actor_user_id="user-1",
        )


def test_disabled_openai_provider_cannot_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(tenant_id="amo-1")
    monkeypatch.setattr(
        saas_services,
        "get_provider_credential",
        MagicMock(return_value=SimpleNamespace(status="DISABLED")),
    )

    with pytest.raises(ValueError, match="OpenAI provider is disabled"):
        saas_services.enqueue_ai_support_reply(
            db,
            ticket_id="ticket-1",
            actor_user_id="user-1",
        )


def test_explicit_ai_request_gets_fresh_reconciled_sequence_after_dead_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = SimpleNamespace(
        tenant_id="amo-1",
        updated_at=datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc),
    )
    dead_job = SimpleNamespace(
        status="DEAD",
        payload_json={"ticket_id": "ticket-1"},
    )
    db = MagicMock()
    db.get.return_value = ticket
    db.query.return_value = _job_query([dead_job])
    credential = SimpleNamespace(id="credential-1", status="CONFIGURED")
    monkeypatch.setattr(
        saas_services,
        "get_provider_credential",
        MagicMock(return_value=credential),
    )
    queued = SimpleNamespace(id="new-job")
    enqueue = MagicMock(return_value=queued)
    monkeypatch.setattr(saas_queue, "enqueue_job", enqueue)

    first = saas_services.enqueue_ai_support_reply(
        db,
        ticket_id="ticket-1",
        actor_user_id="user-1",
    )
    second = saas_services.enqueue_ai_support_reply(
        db,
        ticket_id="ticket-1",
        actor_user_id="user-1",
    )

    assert first is queued
    assert second is queued
    first_call = enqueue.call_args_list[0].kwargs
    second_call = enqueue.call_args_list[1].kwargs
    assert first_call["idempotency_key"] == second_call["idempotency_key"]
    assert first_call["idempotency_key"].endswith(":2")
    assert first_call["payload"]["request_sequence"] == 2
    assert first_call["payload"]["request_version"] == 1784800800000000


def test_duplicate_ai_submission_returns_active_job_without_reenqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = SimpleNamespace(
        tenant_id="amo-1",
        updated_at=datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc),
    )
    active_job = SimpleNamespace(
        status="PENDING",
        payload_json={"ticket_id": "ticket-1", "request_sequence": 1},
    )
    db = MagicMock()
    db.get.return_value = ticket
    db.query.return_value = _job_query([active_job])
    monkeypatch.setattr(
        saas_services,
        "get_provider_credential",
        MagicMock(return_value=SimpleNamespace(id="credential-1", status="HEALTHY")),
    )
    enqueue = MagicMock()
    monkeypatch.setattr(saas_queue, "enqueue_job", enqueue)

    result = saas_services.enqueue_ai_support_reply(
        db,
        ticket_id="ticket-1",
        actor_user_id="user-1",
    )

    assert result is active_job
    enqueue.assert_not_called()
