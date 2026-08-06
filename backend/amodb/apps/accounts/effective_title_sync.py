"""Keep the legacy ``User.position_title`` cache aligned to effective records.

Canonical positions and approved display-title preferences are authoritative.
Some older portal surfaces still read ``users.position_title`` directly, so this
listener updates that cache at commit time for users whose assignments or title
preferences changed. Future assignments cannot change today's title early, and
ending or transferring an assignment cannot leave a stale title behind.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import event, or_
from sqlalchemy.orm import Session

from . import corporate_structure_models as org_models
from . import models
from . import reporting_line_models as line_models

ACTIVE_STATUSES = {"ACTIVE", "ACTING", "APPROVED"}
_LISTENER_FLAG = "_effective_position_title_sync_listener"
_SYNC_GUARD = "_effective_position_title_sync_running"


def _affected_user_ids(session: Session) -> set[str]:
    result: set[str] = set()
    for row in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(row, org_models.PositionAssignment) and row.user_id:
            result.add(str(row.user_id))
        elif isinstance(row, line_models.PersonnelTitlePreference) and row.user_id:
            result.add(str(row.user_id))
    return result


def _effective_title(session: Session, user_id: str) -> str | None:
    today = date.today()
    assignment = (
        session.query(org_models.PositionAssignment)
        .filter(
            org_models.PositionAssignment.user_id == user_id,
            org_models.PositionAssignment.is_primary.is_(True),
            org_models.PositionAssignment.status.in_(ACTIVE_STATUSES),
            org_models.PositionAssignment.effective_from <= today,
            or_(
                org_models.PositionAssignment.effective_to.is_(None),
                org_models.PositionAssignment.effective_to >= today,
            ),
        )
        .order_by(org_models.PositionAssignment.effective_from.desc())
        .first()
    )
    if not assignment:
        return None

    preference = (
        session.query(line_models.PersonnelTitlePreference.requested_title)
        .filter(
            line_models.PersonnelTitlePreference.assignment_id == assignment.id,
            line_models.PersonnelTitlePreference.status == "APPROVED",
        )
        .order_by(
            line_models.PersonnelTitlePreference.decided_at.desc(),
            line_models.PersonnelTitlePreference.created_at.desc(),
        )
        .first()
    )
    if preference:
        return str(preference[0])

    position = (
        session.query(org_models.OrganizationPosition.title)
        .filter(org_models.OrganizationPosition.id == assignment.position_id)
        .first()
    )
    return str(position[0]) if position else None


def synchronize_effective_position_titles(session: Session) -> None:
    if session.info.get(_SYNC_GUARD):
        return
    user_ids = _affected_user_ids(session)
    if not user_ids:
        return

    session.info[_SYNC_GUARD] = True
    try:
        session.flush()
        with session.no_autoflush:
            for user_id in user_ids:
                user = session.query(models.User).filter(models.User.id == user_id).first()
                if not user:
                    continue
                user.position_title = _effective_title(session, user_id)
                session.add(user)
        session.flush()
    finally:
        session.info.pop(_SYNC_GUARD, None)


def install_effective_title_sync_listener() -> None:
    if getattr(Session, _LISTENER_FLAG, False):
        return
    event.listen(Session, "before_commit", synchronize_effective_position_titles)
    setattr(Session, _LISTENER_FLAG, True)


install_effective_title_sync_listener()
