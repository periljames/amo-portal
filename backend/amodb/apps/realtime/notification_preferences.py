from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import messaging as legacy
from . import models, notification_policy


MANDATORY_EMAIL_CLASSES = ("ESSENTIAL", "CRITICAL")


def preference_payload(row: models.NotificationPreference) -> dict[str, Any]:
    return {
        "in_app_enabled": bool(row.in_app_enabled),
        "desktop_enabled": bool(row.desktop_enabled),
        "sound_enabled": bool(row.sound_enabled),
        "email_enabled": bool(row.email_enabled),
        "receipt_email_enabled": bool(row.receipt_email_enabled),
        "marketing_email_enabled": bool(row.marketing_email_enabled),
        "chat_enabled": bool(row.chat_enabled),
        "quiet_hours_start": row.quiet_hours_start,
        "quiet_hours_end": row.quiet_hours_end,
        "timezone_name": row.timezone_name or "UTC",
        "mandatory_email_classes": list(MANDATORY_EMAIL_CLASSES),
        "updated_at": row.updated_at,
    }


def get_preferences(db: Session, *, user: account_models.User) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    row = legacy._preferences(db, amo_id=amo_id, user_id=str(user.id))
    if not row.timezone_name:
        row.timezone_name = "UTC"
    db.commit()
    return preference_payload(row)


def update_preferences(
    db: Session,
    *,
    user: account_models.User,
    payload: dict[str, Any],
) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    row = legacy._preferences(db, amo_id=amo_id, user_id=str(user.id))
    for key in (
        "in_app_enabled",
        "desktop_enabled",
        "sound_enabled",
        "email_enabled",
        "receipt_email_enabled",
        "marketing_email_enabled",
        "chat_enabled",
    ):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    if "quiet_hours_start" in payload:
        row.quiet_hours_start = notification_policy.validate_clock(
            payload.get("quiet_hours_start"),
            field_name="quiet_hours_start",
        )
    if "quiet_hours_end" in payload:
        row.quiet_hours_end = notification_policy.validate_clock(
            payload.get("quiet_hours_end"),
            field_name="quiet_hours_end",
        )
    if "timezone_name" in payload:
        row.timezone_name = notification_policy.validate_timezone(
            payload.get("timezone_name")
        )
    elif not row.timezone_name:
        row.timezone_name = "UTC"
    row.updated_at = legacy.utcnow()
    db.commit()
    return preference_payload(row)


def _tenant_preferences(db: Session, *, amo_id: str) -> models.NotificationTenantPreference:
    row = (
        db.query(models.NotificationTenantPreference)
        .filter(models.NotificationTenantPreference.amo_id == amo_id)
        .first()
    )
    if row is None:
        row = models.NotificationTenantPreference(amo_id=amo_id)
        db.add(row)
        db.flush()
    return row


def tenant_preference_payload(row: models.NotificationTenantPreference) -> dict[str, Any]:
    return {
        "routine_email_enabled": bool(row.routine_email_enabled),
        "receipt_email_enabled": bool(row.receipt_email_enabled),
        "marketing_email_enabled": bool(row.marketing_email_enabled),
        "mandatory_email_classes": list(MANDATORY_EMAIL_CLASSES),
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at,
    }


def get_tenant_preferences(
    db: Session,
    *,
    user: account_models.User,
) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    row = _tenant_preferences(db, amo_id=amo_id)
    db.commit()
    return tenant_preference_payload(row)


def update_tenant_preferences(
    db: Session,
    *,
    user: account_models.User,
    payload: dict[str, Any],
) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    row = _tenant_preferences(db, amo_id=amo_id)
    for key in (
        "routine_email_enabled",
        "receipt_email_enabled",
        "marketing_email_enabled",
    ):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    row.updated_by_user_id = str(user.id)
    row.updated_at = legacy.utcnow()
    db.commit()
    return tenant_preference_payload(row)


def allows_chat_notification(
    db: Session,
    *,
    amo_id: str,
    member: models.ChatThreadMember,
    mentioned_user_ids: set[str],
    now: datetime | None = None,
) -> bool:
    level = str(member.notification_level or "ALL").upper()
    if level == "NONE":
        return False
    if level == "MENTIONS" and str(member.user_id) not in mentioned_user_ids:
        return False
    if member.muted_until and member.muted_until > legacy.utcnow():
        return False
    preferences = legacy._preferences(
        db,
        amo_id=amo_id,
        user_id=str(member.user_id),
    )
    if not preferences.in_app_enabled or not preferences.chat_enabled:
        return False
    return not notification_policy.is_quiet_now(
        start=preferences.quiet_hours_start,
        end=preferences.quiet_hours_end,
        timezone_name=preferences.timezone_name or "UTC",
        now=now,
    )
