from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import models, realtime_auth, secure_messaging


def _seed(db_session, code: str = "SEC"):
    amo = account_models.AMO(amo_code=code, name=f"{code} AMO", login_slug=code.lower())
    db_session.add(amo)
    db_session.flush()
    quality = account_models.Department(amo_id=amo.id, code="QUALITY", name="Quality", is_active=True)
    planning = account_models.Department(amo_id=amo.id, code="PLANNING", name="Planning", is_active=True)
    db_session.add_all([quality, planning])
    db_session.flush()
    first = account_models.User(
        amo_id=amo.id,
        department_id=quality.id,
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
        department_id=quality.id,
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
    return amo, quality, planning, first, second


def test_mqtt_envelope_requires_matching_unexpired_token(db_session):
    amo, _, _, first, _ = _seed(db_session, "AUTH")
    raw = "connect-token-that-is-long-enough-for-validation"
    token = models.RealtimeConnectToken(
        amo_id=amo.id,
        user_id=first.id,
        token_hash=realtime_auth.token_digest(raw),
        session_id="session-auth-test",
        expires_at=realtime_auth.utcnow() + timedelta(minutes=5),
    )
    db_session.add(token)
    db_session.commit()

    assert realtime_auth.validate_connect_token(
        db_session,
        raw_token=raw,
        amo_id=amo.id,
        user_id=first.id,
    ).id == token.id

    with pytest.raises(HTTPException) as invalid:
        realtime_auth.validate_connect_token(
            db_session,
            raw_token="wrong-token-that-is-long-enough-for-validation",
            amo_id=amo.id,
            user_id=first.id,
        )
    assert invalid.value.status_code == 401


def test_department_transfer_revokes_channel_access(db_session):
    _, quality, planning, first, second = _seed(db_session, "MOVE")
    thread = secure_messaging.open_department_thread(db_session, user=first, department_id=quality.id)
    assert second.id in thread["member_user_ids"]

    second.department_id = planning.id
    db_session.commit()

    assert all(row["id"] != thread["id"] for row in secure_messaging.list_threads(db_session, user=second))
    membership = db_session.query(models.ChatThreadMember).filter_by(
        thread_id=thread["id"],
        user_id=second.id,
    ).one()
    assert membership.left_at is not None
    with pytest.raises(HTTPException) as denied:
        secure_messaging.list_messages(db_session, user=second, thread_id=thread["id"])
    assert denied.value.status_code == 404


def test_mentions_only_creates_notification_only_for_valid_mentions(db_session):
    _, _, _, first, second = _seed(db_session, "MENTION")
    thread = secure_messaging.open_direct_thread(db_session, user=first, peer_user_id=second.id)
    membership = db_session.query(models.ChatThreadMember).filter_by(
        thread_id=thread["id"],
        user_id=second.id,
    ).one()
    membership.notification_level = "MENTIONS"
    db_session.commit()

    secure_messaging.send_message(
        db_session,
        user=first,
        thread_id=thread["id"],
        body="Routine update",
        client_msg_id="mention-none",
        metadata={},
    )
    assert db_session.query(models.PortalNotification).filter_by(user_id=second.id).count() == 0

    secure_messaging.send_message(
        db_session,
        user=first,
        thread_id=thread["id"],
        body="Please review this update",
        client_msg_id="mention-valid",
        metadata={"mention_user_ids": [second.id]},
    )
    assert db_session.query(models.PortalNotification).filter_by(user_id=second.id).count() == 1

    with pytest.raises(HTTPException) as invalid:
        secure_messaging.send_message(
            db_session,
            user=first,
            thread_id=thread["id"],
            body="Invalid mention",
            client_msg_id="mention-invalid",
            metadata={"mention_user_ids": ["cross-tenant-user"]},
        )
    assert invalid.value.status_code == 422
