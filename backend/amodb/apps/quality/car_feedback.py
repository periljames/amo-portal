"""Shared decisions and conversation reuse the authoritative CAR activity log."""
from . import models


def record_shared_feedback(db, car, message, *, user=None, actor_name=None, actor_kind="STAFF", client_message_id=None):
    name = actor_name or (getattr(user, "full_name", None) if user else None) or ("System" if actor_kind=="SYSTEM" else "Quality reviewer")
    row = models.CARActionLog(car_id=car.id, action_type=models.CARActionType.COMMENT,
        message=message, visibility="SHARED", actor_kind=actor_kind,
        actor_user_id=getattr(user, "id", None), actor_name=name[:255], client_message_id=client_message_id)
    db.add(row)
    return row


def feedback_changed(car, actor_user_id=None):
    # Publish only after the caller commits. Reconnect/fallback reads always use DB history.
    import uuid
    from datetime import datetime, timezone
    from amodb.apps.events.broker import EventEnvelope, publish_event
    publish_event(EventEnvelope(id=str(uuid.uuid4()), type="qms_car.feedback", entityType="qms_car",
        entityId=str(car.id), action="feedback", timestamp=datetime.now(timezone.utc).isoformat(),
        actor={"id": actor_user_id} if actor_user_id else None,
        metadata={"amoId": str(car.amo_id), "module": "quality"}))
