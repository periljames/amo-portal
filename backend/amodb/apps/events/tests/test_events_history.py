from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.audit import services as audit_services
from amodb.apps.events import router as events_router


class _DummyRequest:
    query_params = {}
    headers = {}


def _create_amo_and_user(db_session, code: str = "EVM01"):
    amo = account_models.AMO(amo_code=code, name=f"Events {code}", login_slug=code.lower(), is_active=True)
    db_session.add(amo)
    db_session.commit()
    db_session.refresh(amo)

    user = account_models.User(
        amo_id=amo.id,
        staff_code=f"ADMIN-{code}",
        email=f"admin-{code.lower()}@example.com",
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


def test_replay_events_since_persists_via_audit_store(db_session):
    amo, user = _create_amo_and_user(db_session)

    first = audit_services.log_event(
        db_session,
        amo_id=amo.id,
        actor_user_id=user.id,
        entity_type="tasks.task",
        entity_id="T-1",
        action="UPDATED",
        metadata={"module": "tasks"},
    )
    second = audit_services.log_event(
        db_session,
        amo_id=amo.id,
        actor_user_id=user.id,
        entity_type="tasks.task",
        entity_id="T-2",
        action="UPDATED",
        metadata={"module": "tasks"},
    )
    db_session.commit()

    replay, reset = events_router._replay_events_since(db_session, amo_id=amo.id, last_event_id=str(first.id))
    assert reset is False
    assert [event.id for event in replay] == [str(second.id)]


def test_replay_events_since_requires_reset_for_unknown_or_expired_cursor(db_session):
    amo, user = _create_amo_and_user(db_session, code="EVM02")
    old_event = audit_services.log_event(
        db_session,
        amo_id=amo.id,
        actor_user_id=user.id,
        entity_type="accounts.user.command",
        entity_id=user.id,
        action="DISABLE",
    )
    db_session.commit()

    stale_ts = datetime.now(timezone.utc) - timedelta(days=events_router.REPLAY_RETENTION_DAYS + 1)
    db_session.query(audit_models.AuditEvent).filter(audit_models.AuditEvent.id == old_event.id).update(
        {audit_models.AuditEvent.occurred_at: stale_ts}
    )
    db_session.commit()

    _, reset_unknown = events_router._replay_events_since(db_session, amo_id=amo.id, last_event_id="missing")
    assert reset_unknown is True

    _, reset_stale = events_router._replay_events_since(db_session, amo_id=amo.id, last_event_id=str(old_event.id))
    assert reset_stale is True


def test_replay_events_since_respects_tenant_scope(db_session):
    amo_a, user_a = _create_amo_and_user(db_session, code="TENANTA")
    amo_b, user_b = _create_amo_and_user(db_session, code="TENANTB")

    anchor = audit_services.log_event(
        db_session,
        amo_id=amo_a.id,
        actor_user_id=user_a.id,
        entity_type="tasks.task",
        entity_id="A-1",
        action="UPDATED",
    )
    later_a = audit_services.log_event(
        db_session,
        amo_id=amo_a.id,
        actor_user_id=user_a.id,
        entity_type="tasks.task",
        entity_id="A-2",
        action="UPDATED",
    )
    _later_b = audit_services.log_event(
        db_session,
        amo_id=amo_b.id,
        actor_user_id=user_b.id,
        entity_type="tasks.task",
        entity_id="B-1",
        action="UPDATED",
    )
    db_session.commit()

    replay, reset = events_router._replay_events_since(db_session, amo_id=amo_a.id, last_event_id=str(anchor.id))
    assert reset is False
    assert [event.id for event in replay] == [str(later_a.id)]


def test_list_event_history_cursor_pagination(db_session):
    amo, user = _create_amo_and_user(db_session, code="EVM03")

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
