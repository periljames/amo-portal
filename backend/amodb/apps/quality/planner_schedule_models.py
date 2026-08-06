from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


class QMSPlannerScheduleMetadata(Base):
    """Timed planner details that do not belong in the regulatory audit record.

    Audit schedules and generated audits remain authoritative in their existing
    tables. This metadata layer stores planner-only timing, location, and attendee
    information without overloading scope/criteria fields or creating a second
    source of truth for the audit lifecycle.
    """

    __tablename__ = "qms_planner_schedule_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_schedules.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    occurrence_date = Column(Date, nullable=True, index=True)

    start_time = Column(Time(timezone=False), nullable=True)
    end_time = Column(Time(timezone=False), nullable=True)
    timezone_name = Column(String(64), nullable=False, default="Africa/Nairobi")
    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    attendee_user_ids_json = Column(Text, nullable=False, default="[]")
    external_attendees_json = Column(Text, nullable=False, default="[]")

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    @property
    def attendee_user_ids(self) -> list[str]:
        return [str(item) for item in _json_list(self.attendee_user_ids_json) if item]

    @property
    def external_attendees(self) -> list[dict[str, Any]]:
        return [dict(item) for item in _json_list(self.external_attendees_json) if isinstance(item, dict)]

    __table_args__ = (
        UniqueConstraint("amo_id", "schedule_id", name="uq_qms_planner_metadata_schedule"),
        UniqueConstraint("amo_id", "audit_id", name="uq_qms_planner_metadata_audit"),
        UniqueConstraint(
            "amo_id",
            "source_schedule_id",
            "occurrence_date",
            name="uq_qms_planner_metadata_occurrence",
        ),
        Index("ix_qms_planner_metadata_amo_occurrence", "amo_id", "occurrence_date"),
    )
