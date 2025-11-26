# backend/amodb/apps/work/models.py

"""
Work module ORM models.

- WorkOrder: administrative maintenance order for an aircraft, aligned with
  ATA Spec 2000 work-package / work-order concepts.
- TaskCard: technical work card / job card under a work order (scheduled or
  non-routine), with HF-aware fields and status tracking.
- TaskAssignment: allocation of a task card to certifying staff / technicians.
- WorkLogEntry: actual man-hours booked against a task card.
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from ...database import Base


# ---------------------------------------------------------------------------
# Enumerations – kept as strings to match API and DB values
# ---------------------------------------------------------------------------


class WorkOrderTypeEnum(str, Enum):
    """High-level type of maintenance event."""

    LINE = "LINE"              # line maintenance visit
    BASE = "BASE"              # base / heavy check
    PERIODIC = "PERIODIC"      # scheduled check (A/B/C/etc.)
    UNSCHEDULED = "UNSCHEDULED"
    MODIFICATION = "MODIFICATION"
    DEFECT = "DEFECT"
    OTHER = "OTHER"


class WorkOrderStatusEnum(str, Enum):
    """Lifecycle state of the work order."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TaskCategoryEnum(str, Enum):
    """Category of task as used in planning / reporting."""

    SCHEDULED = "SCHEDULED"
    UNSCHEDULED = "UNSCHEDULED"
    DEFECT = "DEFECT"
    MODIFICATION = "MODIFICATION"


class TaskOriginTypeEnum(str, Enum):
    """
    Origin of the task card.

    - SCHEDULED: created from an approved maintenance program / package.
    - NON_ROUTINE: raised as a finding or additional work during execution.
    """

    SCHEDULED = "SCHEDULED"
    NON_ROUTINE = "NON_ROUTINE"


class TaskPriorityEnum(str, Enum):
    """Planning priority indicator."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskStatusEnum(str, Enum):
    """Execution status of a task card."""

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    DEFERRED = "DEFERRED"
    CANCELLED = "CANCELLED"


class TaskRoleOnTaskEnum(str, Enum):
    """Role of an assignee on a task card."""

    LEAD = "LEAD"
    SUPPORT = "SUPPORT"
    INSPECTOR = "INSPECTOR"


class TaskAssignmentStatusEnum(str, Enum):
    """Status of an assignment to a user."""

    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class ErrorCapturingMethodEnum(str, Enum):
    """
    Error-capturing method as referenced in AMC 145.A.45(e).

    This allows us to distinguish independent inspections, functional checks,
    duplicate inspections, etc.
    """

    INDEPENDENT_INSPECTION = "INDEPENDENT_INSPECTION"
    FUNCTIONAL_TEST = "FUNCTIONAL_TEST"
    OPERATIONAL_CHECK = "OPERATIONAL_CHECK"
    DUPLICATE_INSPECTION = "DUPLICATE_INSPECTION"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------


class WorkOrder(Base):
    """
    Administrative work order for a maintenance event on a specific aircraft.

    Conceptually:
    - WorkOrder corresponds to an order / work package line item in Spec 2000.
    - Detailed execution is tracked via TaskCard records linked to this WO.
    """

    __tablename__ = "work_orders"

    id: int = Column(Integer, primary_key=True, index=True)

    # Organisation-specific work order number (e.g. YYNNNN or similar)
    wo_number: str = Column(String(32), nullable=False, unique=True, index=True)

    # Link to aircraft
    aircraft_serial_number: str = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Optional references for multi-AMO / CAMO integration or Spec 2000 payloads
    amo_code: str | None = Column(String(20), nullable=True)
    originating_org: str | None = Column(String(64), nullable=True)
    work_package_ref: str | None = Column(
        String(64), nullable=True
    )  # identifier of the work package in planning system

    description: str | None = Column(String(255), nullable=True)

    # Optional short check code (e.g. "A", "C", "200FH", "L")
    check_type: str | None = Column(String(32), nullable=True)

    wo_type: WorkOrderTypeEnum = Column(
        SQLEnum(WorkOrderTypeEnum, name="work_order_type"),
        nullable=False,
        default=WorkOrderTypeEnum.PERIODIC,
    )

    status: WorkOrderStatusEnum = Column(
        SQLEnum(WorkOrderStatusEnum, name="work_order_status"),
        nullable=False,
        default=WorkOrderStatusEnum.OPEN,
    )

    is_scheduled: bool = Column(Boolean, nullable=False, default=True)

    # Dates (planning and execution)
    due_date: date | None = Column(Date, nullable=True)
    open_date: date | None = Column(Date, nullable=True)
    closed_date: date | None = Column(Date, nullable=True)

    # Audit
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by_user_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    aircraft = relationship("Aircraft", back_populates="work_orders")

    tasks = relationship(
        "TaskCard",
        back_populates="work_order",
        cascade="all, delete-orphan",
    )

    crs_list = relationship(
        "CRS",
        back_populates="work_order",
    )


# ---------------------------------------------------------------------------
# TaskCard – scheduled & non-routine work cards
# ---------------------------------------------------------------------------


class TaskCard(Base):
    """
    Maintenance task card (job card / work card) under a WorkOrder.

    - For scheduled work, cards are created from the maintenance program.
    - For non-routine work, cards are raised by engineering / certifying staff
      as findings during execution.

    This model supports:
    - link to maintenance program item and component;
    - staging and status tracking;
    - HF-aware fields like error-capturing method and HF notes.
    """

    __tablename__ = "task_cards"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id",
            "task_code",
            name="uq_taskcard_workorder_taskcode",
        ),
    )

    id: int = Column(Integer, primary_key=True, index=True)

    work_order_id: int = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Redundant aircraft link for easier querying / reporting
    aircraft_serial_number: str = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Optional link to a specific component position
    aircraft_component_id: int | None = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional link to the maintenance program template item
    program_item_id: int | None = Column(
        Integer,
        ForeignKey("maintenance_program_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # For non-routine tasks raised from a scheduled task
    parent_task_id: int | None = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Technical classification
    ata_chapter: str | None = Column(String(20), nullable=True, index=True)
    task_code: str | None = Column(
        String(64),
        nullable=True,
        index=True,
    )  # internal card number or OEM task number

    title: str = Column(String(255), nullable=False)
    description: str | None = Column(Text, nullable=True)

    category: TaskCategoryEnum = Column(
        SQLEnum(TaskCategoryEnum, name="task_category"),
        nullable=False,
        default=TaskCategoryEnum.SCHEDULED,
    )

    origin_type: TaskOriginTypeEnum = Column(
        SQLEnum(TaskOriginTypeEnum, name="task_origin_type"),
        nullable=False,
        default=TaskOriginTypeEnum.SCHEDULED,
    )

    priority: TaskPriorityEnum = Column(
        SQLEnum(TaskPriorityEnum, name="task_priority"),
        nullable=False,
        default=TaskPriorityEnum.MEDIUM,
    )

    # Location / access metadata (ATA style)
    zone: str | None = Column(String(32), nullable=True)
    access_panel: str | None = Column(String(64), nullable=True)

    # Planning
    planned_start: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    planned_end: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    estimated_manhours: float | None = Column(Float, nullable=True)

    # Execution
    status: TaskStatusEnum = Column(
        SQLEnum(TaskStatusEnum, name="task_status"),
        nullable=False,
        default=TaskStatusEnum.PLANNED,
    )
    actual_start: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    actual_end: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Human factors / error-capturing
    error_capturing_method: ErrorCapturingMethodEnum | None = Column(
        SQLEnum(ErrorCapturingMethodEnum, name="task_error_capturing_method"),
        nullable=True,
    )
    requires_duplicate_inspection: bool = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    hf_notes: str | None = Column(
        Text,
        nullable=True,
    )  # free-text HF remarks / cautions / special instructions

    # Audit
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by_user_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    work_order = relationship("WorkOrder", back_populates="tasks")
    aircraft = relationship("Aircraft")  # simple navigation, no back_populates

    component = relationship("AircraftComponent")
    program_item = relationship("MaintenanceProgramItem")

    parent_task = relationship(
        "TaskCard",
        remote_side=[id],
        backref="child_tasks",
    )

    assignments = relationship(
        "TaskAssignment",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    work_logs = relationship(
        "WorkLogEntry",
        back_populates="task",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# TaskAssignment – who is allocated to the task
# ---------------------------------------------------------------------------


class TaskAssignment(Base):
    """
    Assignment of a TaskCard to a user (engineer / technician / inspector).

    Allows tracking of:
    - who is responsible for the task (LEAD / SUPPORT / INSPECTOR);
    - agreed man-hour allocation;
    - assignment lifecycle (ASSIGNED / ACCEPTED / REJECTED / COMPLETED).
    """

    __tablename__ = "task_assignments"

    id: int = Column(Integer, primary_key=True, index=True)

    task_id: int = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: int = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role_on_task: TaskRoleOnTaskEnum = Column(
        SQLEnum(TaskRoleOnTaskEnum, name="task_assignment_role"),
        nullable=False,
        default=TaskRoleOnTaskEnum.SUPPORT,
    )

    allocated_hours: float | None = Column(Float, nullable=True)

    status: TaskAssignmentStatusEnum = Column(
        SQLEnum(TaskAssignmentStatusEnum, name="task_assignment_status"),
        nullable=False,
        default=TaskAssignmentStatusEnum.ASSIGNED,
    )

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    task = relationship("TaskCard", back_populates="assignments")
    user = relationship("User")  # from apps.accounts.models via table "users"


# ---------------------------------------------------------------------------
# WorkLogEntry – actual man-hours booked to a task
# ---------------------------------------------------------------------------


class WorkLogEntry(Base):
    """
    Time booking / work record for a task card.

    Each entry represents a continuous block of work by one user
    (start → end), with optional station information and narrative.
    """

    __tablename__ = "work_log_entries"

    id: int = Column(Integer, primary_key=True, index=True)

    task_id: int = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: int | None = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    start_time: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_time: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Stored explicitly to make reporting easier and robust to timezone changes
    actual_hours: float = Column(Float, nullable=False)

    description: str | None = Column(Text, nullable=True)
    station: str | None = Column(String(16), nullable=True)  # ICAO / IATA / base

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    task = relationship("TaskCard", back_populates="work_logs")
    user = relationship("User")
