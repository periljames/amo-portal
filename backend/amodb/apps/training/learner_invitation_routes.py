from __future__ import annotations

"""Learner-facing Training invitation projection.

The operating system owns invitation mutation/RSVP. This projection gives the
learner cockpit a tenant-safe list enriched with the event/course details needed
for an actionable schedule without duplicating invitation state.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from ...database import get_read_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models as training_models
from . import operating_models


def _enum(value) -> str:
    return str(getattr(value, "value", value) or "")


def install_training_learner_invitation_routes(router_module) -> None:
    router = router_module.router

    @router.get("/invitations/me")
    def list_my_training_invitations(
        include_past: bool = False,
        limit: int = 100,
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        bounded_limit = max(1, min(int(limit or 100), 250))
        query = db.query(operating_models.TrainingSessionInvitation).filter(
            operating_models.TrainingSessionInvitation.amo_id == amo_id,
            operating_models.TrainingSessionInvitation.user_id == str(current_user.id),
        )
        invitations = query.order_by(
            operating_models.TrainingSessionInvitation.created_at.desc()
        ).limit(bounded_limit).all()
        event_ids = {str(row.event_id) for row in invitations}
        events = db.query(training_models.TrainingEvent).filter(
            training_models.TrainingEvent.amo_id == amo_id,
            training_models.TrainingEvent.id.in_(event_ids or {""}),
        ).all()
        event_by_id = {str(row.id): row for row in events}
        course_ids = {str(row.course_id) for row in events}
        courses = db.query(training_models.TrainingCourse).filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.id.in_(course_ids or {""}),
        ).all()
        course_by_id = {str(row.id): row for row in courses}

        items: list[dict] = []
        for invitation in invitations:
            event = event_by_id.get(str(invitation.event_id))
            if event is None:
                continue
            if not include_past and _enum(event.status).upper() == "COMPLETED":
                continue
            course = course_by_id.get(str(event.course_id))
            items.append({
                "id": str(invitation.id),
                "event_id": str(invitation.event_id),
                "course_id": str(event.course_id),
                "course_code": getattr(course, "course_id", None),
                "course_name": getattr(course, "course_name", None) or event.title,
                "event_title": event.title,
                "starts_on": event.starts_on.isoformat(),
                "ends_on": event.ends_on.isoformat() if event.ends_on else None,
                "location": event.location,
                "provider": event.provider,
                "event_status": _enum(event.status),
                "channel": invitation.channel,
                "delivery_status": invitation.delivery_status,
                "rsvp_status": invitation.rsvp_status,
                "responded_at": invitation.responded_at.isoformat() if invitation.responded_at else None,
                "sent_at": invitation.sent_at.isoformat() if invitation.sent_at else None,
                "delivered_at": invitation.delivered_at.isoformat() if invitation.delivered_at else None,
                "read_at": invitation.read_at.isoformat() if invitation.read_at else None,
                "calendar_path": f"/training/invitations/{invitation.id}/calendar.ics",
            })
        return {"items": items, "total": len(items)}


__all__ = ["install_training_learner_invitation_routes"]
