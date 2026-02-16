from datetime import datetime, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import models, schemas, services


def _seed_users(db_session):
    amo = account_models.AMO(amo_code="AMO1", name="AMO One", login_slug="amo-one")
    db_session.add(amo)
    db_session.flush()
    user = account_models.User(
        amo_id=amo.id,
        staff_code="U001",
        email="u1@example.com",
        first_name="U",
        last_name="One",
        full_name="U One",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    other = account_models.User(
        amo_id=amo.id,
        staff_code="U002",
        email="u2@example.com",
        first_name="U",
        last_name="Two",
        full_name="U Two",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    db_session.add_all([user, other])
    db_session.commit()
    return amo, user, other


def test_chat_send_is_idempotent(db_session):
    amo, user, other = _seed_users(db_session)
    thread = models.ChatThread(amo_id=amo.id, created_by=user.id)
    db_session.add(thread)
    db_session.flush()
    db_session.add(models.ChatThreadMember(thread_id=thread.id, user_id=user.id))
    db_session.add(models.ChatThreadMember(thread_id=thread.id, user_id=other.id))
    db_session.commit()

    envelope = schemas.RealtimeEnvelope(
        v=1,
        id="evt-1",
        ts=1,
        amoId=amo.id,
        userId=user.id,
        kind=schemas.RealtimeKind.CHAT_SEND,
        payload={"threadId": thread.id, "body": "hello", "clientMsgId": "cli-1"},
    )

    first = services.store_chat_send(db_session, envelope=envelope)
    second = services.store_chat_send(db_session, envelope=envelope)
    db_session.commit()

    assert first.id == second.id
    assert db_session.query(models.ChatMessage).count() == 1


def test_receipt_state_transitions(db_session):
    amo, user, other = _seed_users(db_session)
    thread = models.ChatThread(amo_id=amo.id, created_by=user.id)
    db_session.add(thread)
    db_session.flush()
    db_session.add(models.ChatThreadMember(thread_id=thread.id, user_id=user.id))
    db_session.add(models.ChatThreadMember(thread_id=thread.id, user_id=other.id))
    message = models.ChatMessage(
        amo_id=amo.id,
        thread_id=thread.id,
        sender_id=user.id,
        body_bin=b"hello",
        body_mime="text/plain",
        client_msg_id="cm-1",
    )
    db_session.add(message)
    db_session.commit()

    delivered = schemas.RealtimeEnvelope(
        v=1,
        id="ack-1",
        ts=1,
        amoId=amo.id,
        userId=other.id,
        kind=schemas.RealtimeKind.ACK_DELIVERED,
        payload={"messageId": message.id},
    )
    services.apply_ack(db_session, envelope=delivered)

    read = schemas.RealtimeEnvelope(
        v=1,
        id="ack-2",
        ts=2,
        amoId=amo.id,
        userId=other.id,
        kind=schemas.RealtimeKind.ACK_READ,
        payload={"messageId": message.id},
    )
    services.apply_ack(db_session, envelope=read)
    db_session.commit()

    receipt = db_session.query(models.MessageReceipt).filter_by(message_id=message.id, user_id=other.id).one()
    assert receipt.delivered_at is not None
    assert receipt.read_at is not None
    assert receipt.read_at >= receipt.delivered_at


def test_realtime_sync_roundtrip(db_session):
    amo, user, other = _seed_users(db_session)
    thread = models.ChatThread(amo_id=amo.id, created_by=user.id)
    db_session.add(thread)
    db_session.flush()
    db_session.add(models.ChatThreadMember(thread_id=thread.id, user_id=user.id))
    db_session.add(models.ChatThreadMember(thread_id=thread.id, user_id=other.id))
    db_session.add(
        models.ChatMessage(
            amo_id=amo.id,
            thread_id=thread.id,
            sender_id=other.id,
            body_bin=b"offline sync",
            body_mime="text/plain",
            client_msg_id="cm-sync",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    data = services.sync_since(db_session, user=user, since_ts_ms=0)
    assert len(data.messages) == 1
    assert data.messages[0].body_text == "offline sync"
