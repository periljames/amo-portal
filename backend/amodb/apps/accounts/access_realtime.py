"""Post-commit realtime signals for tenant access governance.

Audit events are retained separately.  These signals are deliberately emitted
only after the caller commits the authoritative access transaction so connected
portal clients never refetch a change that is not visible yet.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import uuid4

from amodb.apps.events.broker import EventEnvelope, publish_event


logger = logging.getLogger(__name__)


def publish_access_sync(
    *,
    amo_id: str,
    action: str,
    entity_id: str,
    actor_user_id: str | None = None,
    subject_user_id: str | None = None,
    profile_id: str | None = None,
    request_id: str | None = None,
    status: str | None = None,
) -> None:
    """Publish a tenant-scoped access change after the database commit.

    Delivery is best effort because the committed database record remains the
    source of truth.  Realtime consumers also retain normal reconnect/refetch
    behaviour when the broker is unavailable.
    """
    metadata: dict[str, str] = {"amoId": str(amo_id)}
    if subject_user_id:
        metadata["subjectUserId"] = str(subject_user_id)
    if profile_id:
        metadata["profileId"] = str(profile_id)
    if request_id:
        metadata["requestId"] = str(request_id)
    if status:
        metadata["status"] = str(status)

    envelope = EventEnvelope(
        id=str(uuid4()),
        type=f"accounts.access_sync.{str(action).lower()}",
        entityType="accounts.access_sync",
        entityId=str(entity_id),
        action=str(action),
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor={"userId": str(actor_user_id)} if actor_user_id else None,
        metadata=metadata,
    )
    try:
        publish_event(envelope)
    except Exception:
        logger.warning(
            "Failed to publish committed access sync event",
            extra={
                "amo_id": str(amo_id),
                "action": str(action),
                "entity_id": str(entity_id),
                "subject_user_id": str(subject_user_id or ""),
            },
            exc_info=True,
        )
