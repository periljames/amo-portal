from __future__ import annotations

"""Keep best-effort roster email delivery outside authoritative roster writes.

Roster notification correlation identifiers are derived from human-readable
workflow names plus 64-character validation/consent fingerprints. Those values
can exceed the canonical 64-character identifier width used by both
``email_logs.correlation_id`` and ``audit_events.entity_id``.

More importantly, roster notifications are explicitly best-effort. They must
never flush through the same SQLAlchemy session as the roster mutation because
an email-log persistence failure would mark the authoritative roster
transaction rollback-only.

This policy therefore:
* compacts overlong correlation identifiers deterministically to SHA-256 hex
  (exactly 64 characters), retaining stable deduplication semantics; and
* executes notification delivery in its own write session while keeping the
  roster audit event in the authoritative roster session.
"""

import hashlib
from typing import Any, Optional

from ..notifications import service as notification_service
from . import common

_MAX_IDENTIFIER_LENGTH = 64
_INSTALLED = False


def compact_correlation_id(value: str) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) <= _MAX_IDENTIFIER_LENGTH:
        return cleaned
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    def notify_email(
        db,
        *,
        amo_id: str,
        recipient: Optional[str],
        template_key: str,
        subject: str,
        context: dict[str, Any],
        correlation_id: str,
    ) -> None:
        safe_correlation_id = compact_correlation_id(correlation_id)

        if not recipient:
            common.audit(
                db,
                amo_id=amo_id,
                actor_user_id=None,
                entity_type="RosterNotification",
                entity_id=safe_correlation_id,
                action="roster_notification_skipped",
                metadata={"template_key": template_key, "reason": "recipient_missing"},
            )
            return

        try:
            # Best-effort delivery must not share the authoritative roster
            # transaction. ``db=None`` makes the notification service own and
            # close a dedicated WriteSessionLocal transaction.
            notification_service.send_email(
                template_key=template_key,
                recipient=recipient,
                subject=subject,
                context=context,
                correlation_id=safe_correlation_id,
                critical=False,
                amo_id=amo_id,
                db=None,
                audit_context={"purpose": "rostering-nonblocking"},
            )
        except Exception as exc:
            common.audit(
                db,
                amo_id=amo_id,
                actor_user_id=None,
                entity_type="RosterNotification",
                entity_id=safe_correlation_id,
                action="roster_notification_delivery_failed",
                metadata={"template_key": template_key, "error_type": type(exc).__name__},
                critical=False,
            )
            return

        common.audit(
            db,
            amo_id=amo_id,
            actor_user_id=None,
            entity_type="RosterNotification",
            entity_id=safe_correlation_id,
            action="roster_notification_delivered",
            metadata={"template_key": template_key},
        )

    common.notify_email = notify_email
    _INSTALLED = True


__all__ = ["compact_correlation_id", "install"]
