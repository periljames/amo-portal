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
    from amodb.apps.quality import models as quality_models

    portal_notifications = (
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
    quality_notifications = (
        db.query(func.count(quality_models.QMSNotification.id))
        .filter(
            quality_models.QMSNotification.amo_id == amo_id,
            quality_models.QMSNotification.user_id == str(user.id),
            quality_models.QMSNotification.read_at.is_(None),
        )
        .scalar()
        or 0
    )
    notifications = int(portal_notifications) + int(quality_notifications)
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
