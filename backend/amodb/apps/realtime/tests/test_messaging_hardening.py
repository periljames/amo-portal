from __future__ import annotations

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import messaging, models, notification_counts, secure_messaging


def _seed_tenant(db_session, code: str = "MSG"):
    amo = account_models.AMO(amo_code=code, name=f"{code} AMO", login_slug=code.lower())
    db_session.add(amo)
    db_session.flush()
    department = account_models.Department(amo_id=amo.id, code="QUALITY", name="Quality", is_active=True)
    db_session.add(department)
    db_session.flush()
    first = account_models.User(
        amo_id=amo.id,
        department_id=department.id,
        staff_code=f"{code}-1",
        email=f"{code.lower()}1@example.com",
        first_name="First",
        last_name="User",
        full_name="First User",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    second = account_models.User(
        amo_id=amo.id,
        department_id=department.id,
        staff_code=f"{code}-2",
        email=f"{code.lower()}2@example.com",
        first_name="Second",
        last_name="User",
        full_name="Second User",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    db_session.add_all([first, second])
    db_session.commit()
    return amo, department, first, second


def test_direct_thread_is_deduplicated_and_tenant_scoped(db_session):
    amo, _, first, second = _seed_tenant(db_session, "DIRECT")
    first_thread = secure_messaging.open_direct_thread(db_session, user=first, peer_user_id=second.id)
    second_thread = secure_messaging.open_direct_thread(db_session, user=second, peer_user_id=first.id)

    assert first_thread["id"] == second_thread["id"]
    assert first_thread["kind"] == "DIRECT"
    assert set(first_thread["member_user_ids"]) == {first.id, second.id}
    assert db_session.query(models.ChatThread).filter_by(amo_id=amo.id, kind="DIRECT").count() == 1

    other_amo, _, outsider, _ = _seed_tenant(db_session, "OUTSIDE")
    assert other_amo.id != amo.id
    with pytest.raises(HTTPException) as exc:
        secure_messaging.open_direct_thread(db_session, user=first, peer_user_id=outsider.id)
    assert exc.value.status_code == 404


def test_department_channel_syncs_active_department_members(db_session):
    _, department, first, second = _seed_tenant(db_session, "DEPT")
    thread = secure_messaging.open_department_thread(db_session, user=first, department_id=department.id)

    assert thread["kind"] == "DEPARTMENT"
    assert thread["department_id"] == department.id
    assert set(thread["member_user_ids"]) == {first.id, second.id}


def test_message_delivery_creates_receipt_notification_and_one_unread_item(db_session):
    _, _, first, second = _seed_tenant(db_session, "READ")
    thread = secure_messaging.open_direct_thread(db_session, user=first, peer_user_id=second.id)

    message = secure_messaging.send_message(
        db_session,
        user=first,
        thread_id=thread["id"],
        body="Please review the audit pack.",
        client_msg_id="client-message-1",
    )
    duplicate = secure_messaging.send_message(
        db_session,
        user=first,
        thread_id=thread["id"],
        body="This duplicate must not create a second row.",
        client_msg_id="client-message-1",
    )

    assert duplicate["id"] == message["id"]
    receipt = db_session.query(models.MessageReceipt).filter_by(message_id=message["id"], user_id=second.id).one()
    notification = db_session.query(models.PortalNotification).filter_by(user_id=second.id, entity_id=thread["id"]).one()
    assert receipt.read_at is None
    assert notification.read_at is None
    assert notification_counts.unread_notification_count(db_session, user=second) == {
        "notifications": 0,
        "messages": 1,
        "total": 1,
    }

    result = secure_messaging.mark_thread_read(db_session, user=second, thread_id=thread["id"])
    assert result["updated_receipts"] == 1
    db_session.refresh(receipt)
    db_session.refresh(notification)
    assert receipt.delivered_at is not None
    assert receipt.read_at is not None
    assert notification.read_at is not None


def test_non_member_cannot_read_or_send_to_thread(db_session):
    _, _, first, second = _seed_tenant(db_session, "MEMBERS")
    _, _, third, _ = _seed_tenant(db_session, "THIRD")
    thread = secure_messaging.open_direct_thread(db_session, user=first, peer_user_id=second.id)

    with pytest.raises(HTTPException) as read_exc:
        secure_messaging.list_messages(db_session, user=third, thread_id=thread["id"])
    assert read_exc.value.status_code == 404

    with pytest.raises(HTTPException) as send_exc:
        secure_messaging.send_message(
            db_session,
            user=third,
            thread_id=thread["id"],
            body="Not allowed",
            client_msg_id="cross-tenant",
        )
    assert send_exc.value.status_code == 404


def test_email_notifications_remain_opt_in(db_session):
    _, _, first, _ = _seed_tenant(db_session, "PREF")
    preferences = messaging.get_preferences(db_session, user=first)
    assert preferences["in_app_enabled"] is True
    assert preferences["chat_enabled"] is True
    assert preferences["email_enabled"] is False
