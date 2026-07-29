from __future__ import annotations

from enum import Enum

from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import models as realtime_models


class EmailClass(str, Enum):
    """Delivery classes used to enforce portal-owned email policy."""

    ESSENTIAL = "ESSENTIAL"
    CRITICAL = "CRITICAL"
    RECEIPT = "RECEIPT"
    ROUTINE = "ROUTINE"
    MARKETING = "MARKETING"


MANDATORY_EMAIL_CLASSES = frozenset({EmailClass.ESSENTIAL, EmailClass.CRITICAL})


def normalize_email_class(value: EmailClass | str | None, *, critical: bool = False) -> EmailClass:
    if critical:
        return EmailClass.CRITICAL
    if isinstance(value, EmailClass):
        return value
    normalized = str(value or EmailClass.ROUTINE.value).strip().upper()
    try:
        return EmailClass(normalized)
    except ValueError as exc:
        raise ValueError(
            "email_class must be ESSENTIAL, CRITICAL, RECEIPT, ROUTINE or MARKETING"
        ) from exc


def _tenant_preferences(
    db: Session,
    *,
    amo_id: str,
) -> realtime_models.NotificationTenantPreference | None:
    return (
        db.query(realtime_models.NotificationTenantPreference)
        .filter(realtime_models.NotificationTenantPreference.amo_id == amo_id)
        .first()
    )


def _user_preferences(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
) -> realtime_models.NotificationPreference | None:
    return (
        db.query(realtime_models.NotificationPreference)
        .filter(
            realtime_models.NotificationPreference.amo_id == amo_id,
            realtime_models.NotificationPreference.user_id == user_id,
        )
        .first()
    )


def _internal_recipient_user_id(
    db: Session,
    *,
    amo_id: str,
    recipient_email: str | None,
) -> str | None:
    """Resolve a tenant user from an email before treating it as external.

    Operational producers historically supplied only an employee email address.
    Resolving that address here prevents those calls from bypassing an explicit
    user opt-out while still allowing genuinely external recipients.
    """

    normalized_email = str(recipient_email or "").strip().lower()
    if not normalized_email:
        return None
    row = (
        db.query(account_models.User.id)
        .filter(
            account_models.User.amo_id == amo_id,
            func.lower(account_models.User.email) == normalized_email,
        )
        .first()
    )
    return str(row[0]) if row else None


def email_allowed(
    db: Session,
    *,
    amo_id: str,
    recipient_user_id: str | None,
    recipient_email: str | None,
    email_class: EmailClass | str,
) -> tuple[bool, str | None]:
    """Return whether an outbound email may be sent under tenant/user policy.

    Essential account/security messages and critical operational/compliance
    messages are portal features and cannot be disabled. All other classes are
    explicit opt-ins at tenant level and, for internal users, at user level.
    """

    classification = normalize_email_class(email_class)
    if classification in MANDATORY_EMAIL_CLASSES:
        return True, None

    tenant = _tenant_preferences(db, amo_id=amo_id)
    tenant_field = {
        EmailClass.ROUTINE: "routine_email_enabled",
        EmailClass.RECEIPT: "receipt_email_enabled",
        EmailClass.MARKETING: "marketing_email_enabled",
    }[classification]
    if tenant is None or not bool(getattr(tenant, tenant_field, False)):
        return False, f"{classification.value.title()} email is disabled for this tenant"

    resolved_user_id = recipient_user_id or _internal_recipient_user_id(
        db,
        amo_id=amo_id,
        recipient_email=recipient_email,
    )
    if not resolved_user_id:
        return True, None

    user = _user_preferences(db, amo_id=amo_id, user_id=resolved_user_id)
    user_field = {
        EmailClass.ROUTINE: "email_enabled",
        EmailClass.RECEIPT: "receipt_email_enabled",
        EmailClass.MARKETING: "marketing_email_enabled",
    }[classification]
    if user is None or not bool(getattr(user, user_field, False)):
        return False, f"{classification.value.title()} email is disabled by the recipient"
    return True, None
