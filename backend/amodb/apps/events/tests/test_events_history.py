from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services
from amodb.apps.events import router as events_router
from amodb.apps.events.broker import EventBroker, EventEnvelope


class _DummyRequest:
    query_params = {}
    headers = {}


def _create_amo_and_user(db_session):
    amo = account_models.AMO(amo_code="EVM01", name="Events AMO", login_slug="evm01", is_active=True)
    db_session.add(amo)
    db_session.commit()
    db_session.refresh(amo)

    user = account_models.User(
        amo_id=amo.id,
        staff_code="ADMIN1",
        email="admin-events@example.com",
        first_name="Admin",
        last_name="Events",
        full_name="Admin Events",
        role=account_models.AccountRole.AMO_ADMIN,
        hashed_password="hashed",
        is_active=True,
        is_amo_admin=True,
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return amo, user


def test_event_broker_replay_since_and_reset_behavior():
    broker = EventBroker(replay_size=3)
    for idx in range(4):
        broker.publish(
            EventEnvelope(
                id=f"E{idx}",
                type="accounts.user.updated",
                entityType="accounts.user",
                entityId=str(idx),
                action="UPDATED",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor={"userId": "A1"},
                metadata={"amoId": "AMO1"},
            )
        )

    replay, reset = broker.replay_since(last_event_id="E1", amo_id="AMO1")
    assert reset is False
    assert [event.id for event in replay] == ["E2", "E3"]

    replay_old, reset_old = broker.replay_since(last_event_id="E0", amo_id="AMO1")
    assert replay_old == []
    assert reset_old is True


def test_list_event_history_cursor_pagination(db_session):
    amo, user = _create_amo_and_user(db_session)

    now = datetime.now(timezone.utc)
    for idx in range(4):
        audit_services.log_event(
            db_session,
            amo_id=amo.id,
            actor_user_id=user.id,
            entity_type="tasks.task",
            entity_id=f"T{idx}",
            action="UPDATED",
            metadata={"module": "tasks"},
        )
    db_session.commit()

    page1 = events_router.list_event_history(
        request=_DummyRequest(),
        cursor=None,
        limit=2,
        db=db_session,
        user=user,
    )
    assert len(page1.items) == 2
    assert page1.next_cursor is not None

    page2 = events_router.list_event_history(
        request=_DummyRequest(),
        cursor=page1.next_cursor,
        limit=2,
        db=db_session,
        user=user,
    )
    assert len(page2.items) >= 1
    ids1 = {item.id for item in page1.items}
    ids2 = {item.id for item in page2.items}
    assert ids1.isdisjoint(ids2)
