from __future__ import annotations

from datetime import datetime, timezone
import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, String

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_amo_status", "amo_id", "status"),
        Index("ix_tasks_owner_status", "owner_user_id", "status"),
        Index("ix_tasks_due", "amo_id", "due_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)

    status = Column(
        SAEnum(TaskStatus, name="task_status_enum", native_enum=False),
        nullable=False,
        default=TaskStatus.OPEN,
        index=True,
    )

    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    supervisor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    entity_type = Column(String(64), nullable=True, index=True)
    entity_id = Column(String(64), nullable=True, index=True)

    priority = Column(Integer, nullable=False, default=3)
    metadata_json = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Task id={self.id} status={self.status} owner={self.owner_user_id}>"
