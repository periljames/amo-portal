from __future__ import annotations

from datetime import datetime, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.integrations import dispatcher
from amodb.apps.integrations import models as integration_models


def _create_amo(db_session):
    amo = account_models.AMO(
        amo_code="AMO-DISP",
        name="Dispatch AMO",
        login_slug="dispatch",
    )
    db_session.add(amo)
    db_session.commit()
    return amo


def _create_config(db_session, amo_id: str, base_url: str):
    config = integration_models.IntegrationConfig(
        amo_id=amo_id,
        integration_key="dispatch",
        display_name="Dispatch",
        base_url=base_url,
        enabled=True,
        status=integration_models.IntegrationConfigStatus.ACTIVE,
    )
    db_session.add(config)
    db_session.commit()
    return config


def _create_event(db_session, amo_id: str, integration_id: str, attempt_count: int = 0):
    event = integration_models.IntegrationOutboundEvent(
        amo_id=amo_id,
        integration_id=integration_id,
        event_type="work_order.created",
        payload_json={"id": "WO-1"},
        status=integration_models.IntegrationOutboundStatus.PENDING,
        attempt_count=attempt_count,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    return event


def test_dispatcher_status_transitions(db_session, monkeypatch):
    amo = _create_amo(db_session)
    config = _create_config(db_session, amo.id, "https://example.com/webhook")

    event_success = _create_event(db_session, amo.id, config.id)

    def fake_post_success(url, payload, signature):
        return 200, "ok"

    monkeypatch.setattr(dispatcher, "_post_event", fake_post_success)
    dispatcher.dispatch_due_events(db_session, now=datetime.now(timezone.utc), limit=10)

    db_session.refresh(event_success)
    assert event_success.status == integration_models.IntegrationOutboundStatus.SENT
    assert event_success.attempt_count == 1
    assert event_success.last_error is None

    event_fail = _create_event(db_session, amo.id, config.id)

    def fake_post_fail(url, payload, signature):
        return 500, "error"

    monkeypatch.setattr(dispatcher, "_post_event", fake_post_fail)
    dispatcher.dispatch_due_events(db_session, now=datetime.now(timezone.utc), limit=10)

    db_session.refresh(event_fail)
    assert event_fail.status == integration_models.IntegrationOutboundStatus.FAILED
    assert event_fail.next_attempt_at is not None

    event_dead = _create_event(db_session, amo.id, config.id, attempt_count=dispatcher.MAX_ATTEMPTS - 1)
    dispatcher.dispatch_due_events(db_session, now=datetime.now(timezone.utc), limit=10)

    db_session.refresh(event_dead)
    assert event_dead.status == integration_models.IntegrationOutboundStatus.DEAD_LETTER
