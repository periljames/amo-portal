from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import models, schemas, services


def test_two_user_chat_and_receipts_persist(db_session):
    amo = account_models.AMO(amo_code="AMO2", name="AMO Two", login_slug="amo-two")
    db_session.add(amo)
    db_session.flush()

    sender = account_models.User(
        amo_id=amo.id,
        staff_code="S001",
        email="s@example.com",
        first_name="Send",
        last_name="Er",
        full_name="Send Er",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    recipient = account_models.User(
        amo_id=amo.id,
        staff_code="R001",
        email="r@example.com",
        first_name="Read",
        last_name="Er",
        full_name="Read Er",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    db_session.add_all([sender, recipient])
    db_session.flush()

    thread = models.ChatThread(amo_id=amo.id, created_by=sender.id)
    db_session.add(thread)
    db_session.flush()
    db_session.add_all([
        models.ChatThreadMember(thread_id=thread.id, user_id=sender.id),
        models.ChatThreadMember(thread_id=thread.id, user_id=recipient.id),
    ])
    db_session.commit()

    send_env = schemas.RealtimeEnvelope(
        v=1,
        id="send-1",
        ts=1,
        amoId=amo.id,
        userId=sender.id,
        kind=schemas.RealtimeKind.CHAT_SEND,
        payload={"threadId": thread.id, "body": "hi", "clientMsgId": "x1"},
    )
    msg = services.store_chat_send(db_session, envelope=send_env)
    db_session.commit()

    services.apply_ack(
        db_session,
        envelope=schemas.RealtimeEnvelope(
            v=1,
            id="ack-del",
            ts=2,
            amoId=amo.id,
            userId=recipient.id,
            kind=schemas.RealtimeKind.ACK_DELIVERED,
            payload={"messageId": msg.id},
        ),
    )
    services.apply_ack(
        db_session,
        envelope=schemas.RealtimeEnvelope(
            v=1,
            id="ack-read",
            ts=3,
            amoId=amo.id,
            userId=recipient.id,
            kind=schemas.RealtimeKind.ACK_READ,
            payload={"messageId": msg.id},
        ),
    )
    db_session.commit()

    receipt = db_session.query(models.MessageReceipt).filter_by(message_id=msg.id, user_id=recipient.id).one()
    assert receipt.delivered_at is not None
    assert receipt.read_at is not None
