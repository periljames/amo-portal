from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import messaging, models


def unread_notification_count(
    db: Session,
    *,
    user: account_models.User,
) -> dict[str, int]:
    """Return mutually exclusive counts so one chat message is never counted twice."""

    amo_id = messaging.effective_amo_id(user)
    notifications = (
        db.query(func.count(models.PortalNotification.id))
        .filter(
            models.PortalNotification.amo_id == amo_id,
            models.PortalNotification.user_id == str(user.id),
            models.PortalNotification.kind != "CHAT_MESSAGE",
            models.PortalNotification.read_at.is_(None),
            models.PortalNotification.archived_at.is_(None),
        )
        .scalar()
        or 0
    )
    messages = (
        db.query(func.count(models.MessageReceipt.id))
        .filter(
            models.MessageReceipt.amo_id == amo_id,
            models.MessageReceipt.user_id == str(user.id),
            models.MessageReceipt.read_at.is_(None),
        )
        .scalar()
        or 0
    )
    return {
        "notifications": int(notifications),
        "messages": int(messages),
        "total": int(notifications) + int(messages),
    }
