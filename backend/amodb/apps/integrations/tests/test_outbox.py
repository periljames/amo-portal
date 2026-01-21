from __future__ import annotations

from amodb.apps.accounts import models as account_models
from amodb.apps.integrations import models as integration_models
from amodb.apps.integrations import services


def _create_amo(db_session):
    amo = account_models.AMO(
        amo_code="AMO-INT",
        name="Integration AMO",
        login_slug="integration-amo",
        country="KE",
    )
    db_session.add(amo)
    db_session.commit()
    return amo


def _create_user(db_session, amo_id: str):
    user = account_models.User(
        amo_id=amo_id,
        staff_code="INT-001",
        email="integration@example.com",
        first_name="Integration",
        last_name="User",
        full_name="Integration User",
        hashed_password="hashed-password",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
        is_amo_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _create_config(db_session, amo_id: str, user_id: str):
    config = integration_models.IntegrationConfig(
        amo_id=amo_id,
        integration_key="demo-webhook",
        display_name="Demo Webhook",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db_session.add(config)
    db_session.commit()
    return config


def test_outbox_enqueue_idempotent(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)
    config = _create_config(db_session, amo.id, user.id)

    payload = {"event": "work_order.created", "id": "WO-100"}

    event = services.enqueue_outbound_event(
        db_session,
        amo_id=amo.id,
        integration_id=config.id,
        event_type="work_order.created",
        payload_json=payload,
        idempotency_key="idem-001",
        created_by_user_id=user.id,
    )
    db_session.commit()

    duplicate = services.enqueue_outbound_event(
        db_session,
        amo_id=amo.id,
        integration_id=config.id,
        event_type="work_order.created",
        payload_json=payload,
        idempotency_key="idem-001",
        created_by_user_id=user.id,
    )
    db_session.commit()

    rows = (
        db_session.query(integration_models.IntegrationOutboundEvent)
        .filter(integration_models.IntegrationOutboundEvent.amo_id == amo.id)
        .all()
    )

    assert event.id == duplicate.id
    assert len(rows) == 1
    assert event.created_at is not None
    assert event.created_by_user_id == user.id
