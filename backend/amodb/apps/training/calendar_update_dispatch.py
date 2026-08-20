from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..notifications import service as notification_service
from ..realtime import models as realtime_models
from . import models as training_models
from . import operating_models

UTC = timezone.utc
PENDING_STATES = {"UPDATE_PENDING", "CANCEL_PENDING"}


def _now() -> datetime:
    return datetime.now(UTC)


def _event_change_key(event) -> str:
    stamp = event.updated_at or event.created_at or _now()
    return str(int(stamp.timestamp()))


def dispatch_pending_calendar_updates(db: Session, *, limit: int = 500) -> dict[str, int]:
    summary = {"scanned": 0, "delivered": 0, "queued": 0, "failed": 0}
    invitations = db.query(operating_models.TrainingSessionInvitation).filter(
        operating_models.TrainingSessionInvitation.delivery_status.in_(tuple(PENDING_STATES))
    ).order_by(operating_models.TrainingSessionInvitation.updated_at.asc()).limit(max(1, min(int(limit), 2000))).all()

    event_ids = {str(row.event_id) for row in invitations}
    user_ids = {str(row.user_id) for row in invitations}
    events = {
        str(row.id): row
        for row in db.query(training_models.TrainingEvent).filter(
            training_models.TrainingEvent.id.in_(event_ids or {""})
        ).all()
    }
    users = {
        (str(row.amo_id), str(row.id)): row
        for row in db.query(account_models.User).filter(
            account_models.User.id.in_(user_ids or {""})
        ).all()
    }

    for invitation in invitations:
        summary["scanned"] += 1
        event = events.get(str(invitation.event_id))
        user = users.get((str(invitation.amo_id), str(invitation.user_id)))
        if event is None or str(event.amo_id) != str(invitation.amo_id) or user is None:
            invitation.delivery_status = "FAILED"
            invitation.last_error = "Calendar update source event or tenant recipient is unavailable."
            summary["failed"] += 1
            continue

        cancelled = str(getattr(event.status, "value", event.status) or "").upper() == "CANCELLED"
        change = "cancelled" if cancelled else "updated"
        action_url = f"/training/my?session={event.id}"
        calendar_path = f"/training/invitations/{invitation.id}/calendar.ics"
        message = (
            f"Training session {event.title} has been {change}. "
            f"Current dates: {event.starts_on} to {event.ends_on or event.starts_on}. "
            "Open Training to review the change and download the same calendar event again."
        )
        invitation.attempt_count = int(invitation.attempt_count or 0) + 1
        invitation.last_error = None
        invitation.sent_at = _now()
        dedupe_version = _event_change_key(event)

        try:
            channel = str(invitation.channel or "").upper()
            if channel == "IN_APP":
                existing = db.query(realtime_models.PortalNotification.id).filter(
                    realtime_models.PortalNotification.amo_id == invitation.amo_id,
                    realtime_models.PortalNotification.user_id == invitation.user_id,
                    realtime_models.PortalNotification.dedupe_key == f"training-calendar-change:{invitation.id}:{dedupe_version}",
                ).first()
                if existing is None:
                    db.add(realtime_models.PortalNotification(
                        amo_id=invitation.amo_id,
                        user_id=invitation.user_id,
                        kind="TRAINING_SESSION_CANCELLED" if cancelled else "TRAINING_SESSION_UPDATED",
                        title=f"Training session {change}: {event.title}",
                        body=message,
                        entity_type="training_event",
                        entity_id=str(event.id),
                        action_url=action_url,
                        dedupe_key=f"training-calendar-change:{invitation.id}:{dedupe_version}",
                        metadata_json={
                            "event_id": str(event.id),
                            "invitation_id": str(invitation.id),
                            "calendar_path": calendar_path,
                            "cancelled": cancelled,
                        },
                    ))
                invitation.delivery_status = "DELIVERED"
                invitation.delivered_at = _now()
                summary["delivered"] += 1
            elif channel == "EMAIL":
                if not str(user.email or "").strip():
                    raise RuntimeError("Recipient has no email address")
                log = notification_service.send_email(
                    "training-session-invitation",
                    user.email,
                    f"Training session {change}: {event.title}",
                    {
                        "name": user.full_name,
                        "event_title": event.title,
                        "starts_on": str(event.starts_on),
                        "ends_on": str(event.ends_on or event.starts_on),
                        "action_url": action_url,
                        "calendar_path": calendar_path,
                        "message": message,
                        "calendar_method": "CANCEL" if cancelled else "REQUEST",
                    },
                    f"training-calendar-change:{invitation.id}:{dedupe_version}",
                    amo_id=str(invitation.amo_id),
                    db=db,
                    recipient_user_id=str(invitation.user_id),
                    audit_context={
                        "purpose": "training-session-calendar-change",
                        "event_id": str(event.id),
                        "invitation_id": str(invitation.id),
                        "cancelled": cancelled,
                    },
                )
                invitation.email_log_id = str(log.id)
                invitation.delivery_status = str(
                    getattr(getattr(log, "status", None), "value", getattr(log, "delivery_status", "QUEUED"))
                )
                invitation.last_error = getattr(log, "error", None)
                if invitation.delivery_status in {"FAILED", "BOUNCED"}:
                    summary["failed"] += 1
                else:
                    summary["queued"] += 1
            else:
                raise RuntimeError(f"Unsupported Training invitation channel: {invitation.channel}")
        except Exception as exc:
            invitation.delivery_status = "FAILED"
            invitation.last_error = f"{type(exc).__name__}: {exc}"[:4000]
            summary["failed"] += 1

        db.add(training_models.TrainingAuditLog(
            amo_id=str(invitation.amo_id),
            actor_user_id=None,
            action="SESSION_CALENDAR_CANCEL_DISPATCH" if cancelled else "SESSION_CALENDAR_UPDATE_DISPATCH",
            entity_type="TrainingSessionInvitation",
            entity_id=str(invitation.id),
            details={
                "event_id": str(event.id),
                "channel": invitation.channel,
                "delivery_status": invitation.delivery_status,
                "calendar_path": calendar_path,
                "rsvp_status_preserved": invitation.rsvp_status,
            },
        ))
    return summary


__all__ = ["PENDING_STATES", "dispatch_pending_calendar_updates"]
