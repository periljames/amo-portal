# backend/amodb/apps/work/models.py
"""
Work module ORM models.

- WorkOrder: administrative maintenance order for an aircraft, aligned with
  ATA Spec 2000 work-package / work-order concepts.
- TaskCard: technical work card / job card under a work order (scheduled or
  non-routine), with HF-aware fields and status tracking.
- TaskAssignment: allocation of a task card to certifying staff / technicians.
- WorkLogEntry: actual man-hours booked against a task card.

This revision hardens the schema for long-run safety:
- Uses timezone-aware UTC timestamps (consistent across apps).
- Uses non-native enums to avoid Postgres enum lifecycle headaches in Alembic.
- Adds indexes for common planning queries (aircraft/status/due dates).
- Adds non-negative and date/time ordering check constraints.
- Adds uniqueness constraints to prevent silent duplication where it matters.
- Aligns program item FK to maintenance_program module hardened table name
  (`amp_program_items`) to avoid table-name collisions.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Enum as SAEnum,
    desc,
)
from sqlalchemy.orm import relationship

from ...database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    DRAFT = "DRAFT"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    INSPECTED = "INSPECTED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"
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
    INSPECTED = "INSPECTED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
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
    __table_args__ = (
        UniqueConstraint("amo_id", "wo_number", name="uq_work_orders_amo_number"),
        Index("ix_work_orders_amo_status", "amo_id", "status"),
        Index("ix_work_orders_amo_aircraft", "amo_id", "aircraft_serial_number"),
        Index(
            "ix_work_orders_amo_aircraft_created",
            "amo_id",
            "aircraft_serial_number",
            desc("created_at"),
        ),
        Index("ix_work_orders_aircraft_status", "aircraft_serial_number", "status"),
        Index("ix_work_orders_status_due", "status", "due_date"),
        Index("ix_work_orders_type_status", "wo_type", "status"),
        CheckConstraint(
            "open_date IS NULL OR closed_date IS NULL OR closed_date >= open_date",
            name="ck_work_orders_closed_after_open",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Organisation-specific work order number (e.g. YYNNNN or similar)
    wo_number = Column(String(32), nullable=False, index=True)

    # Link to aircraft
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Optional references for multi-AMO / CAMO integration or Spec 2000 payloads
    amo_code = Column(String(20), nullable=True)
    originating_org = Column(String(64), nullable=True)
    work_package_ref = Column(String(64), nullable=True)  # planning system pack reference
    operator_event_id = Column(String(36), nullable=True, index=True)

    description = Column(String(255), nullable=True)

    # Optional short check code (e.g. "A", "C", "200FH", "L")
    check_type = Column(String(32), nullable=True)

    wo_type = Column(
        SAEnum(WorkOrderTypeEnum, name="work_order_type_enum", native_enum=False),
        nullable=False,
        default=WorkOrderTypeEnum.PERIODIC,
        index=True,
    )

    status = Column(
        SAEnum(WorkOrderStatusEnum, name="work_order_status_enum", native_enum=False),
        nullable=False,
        default=WorkOrderStatusEnum.DRAFT,
        index=True,
    )

    is_scheduled = Column(Boolean, nullable=False, default=True, index=True)

    # Dates (planning and execution)
    due_date = Column(Date, nullable=True, index=True)
    open_date = Column(Date, nullable=True, index=True)
    closed_date = Column(Date, nullable=True, index=True)
    closure_reason = Column(String(64), nullable=True, index=True)
    closure_notes = Column(Text, nullable=True)

    # Audit (accounts.users.id is GUID string)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    aircraft = relationship("Aircraft", back_populates="work_orders", lazy="joined")

    tasks = relationship(
        "TaskCard",
        back_populates="work_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    crs_list = relationship(
        "CRS",
        back_populates="work_order",
        lazy="selectin",
    )

    inspector_signoffs = relationship(
        "InspectorSignOff",
        back_populates="work_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<WorkOrder id={self.id} wo_number={self.wo_number} status={self.status}>"


# ---------------------------------------------------------------------------
# TaskCard – scheduled & non-routine work cards
# ---------------------------------------------------------------------------


class TaskCard(Base):
    """
    Maintenance task card (job card / work card) under a WorkOrder.

    - For scheduled work, cards are created from the maintenance program.
    - For non-routine work, cards are raised by engineering / certifying staff.

    Supports:
    - link to maintenance program item and component;
    - staging and status tracking;
    - HF-aware fields like error-capturing method and HF notes.
    """

    __tablename__ = "task_cards"
    __table_args__ = (
        # Note: Postgres allows multiple NULLs for a UNIQUE constraint.
        # That is acceptable for non-coded ad-hoc cards.
        UniqueConstraint("work_order_id", "task_code", name="uq_taskcard_workorder_taskcode"),
        Index("ix_task_cards_amo_status", "amo_id", "status"),
        Index("ix_task_cards_amo_aircraft", "amo_id", "aircraft_serial_number"),
        Index("ix_task_cards_workorder_status", "work_order_id", "status"),
        Index("ix_task_cards_amo_workorder_status", "amo_id", "work_order_id", "status"),
        Index("ix_task_cards_aircraft_status", "aircraft_serial_number", "status"),
        Index("ix_task_cards_status_priority", "status", "priority"),
        Index("ix_task_cards_program_item", "program_item_id"),
        Index("ix_task_cards_component", "aircraft_component_id"),
        Index("ix_task_cards_ata", "ata_chapter"),
        CheckConstraint(
            "planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start",
            name="ck_task_cards_planned_end_after_start",
        ),
        CheckConstraint(
            "actual_start IS NULL OR actual_end IS NULL OR actual_end >= actual_start",
            name="ck_task_cards_actual_end_after_start",
        ),
        CheckConstraint(
            "estimated_manhours IS NULL OR estimated_manhours >= 0",
            name="ck_task_cards_estimated_manhours_nonneg",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    work_order_id = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Redundant aircraft link for easier querying / reporting
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Optional link to a specific component position
    aircraft_component_id = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional link to the maintenance program template item
    # (Aligned with maintenance_program hardened table name)
    program_item_id = Column(
        Integer,
        ForeignKey("amp_program_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # For non-routine tasks raised from a scheduled task
    parent_task_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Technical classification
    ata_chapter = Column(String(20), nullable=True, index=True)
    task_code = Column(String(64), nullable=True, index=True)  # internal card number or OEM task number
    operator_event_id = Column(String(36), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    category = Column(
        SAEnum(TaskCategoryEnum, name="task_category_enum", native_enum=False),
        nullable=False,
        default=TaskCategoryEnum.SCHEDULED,
        index=True,
    )

    origin_type = Column(
        SAEnum(TaskOriginTypeEnum, name="task_origin_type_enum", native_enum=False),
        nullable=False,
        default=TaskOriginTypeEnum.SCHEDULED,
        index=True,
    )

    priority = Column(
        SAEnum(TaskPriorityEnum, name="task_priority_enum", native_enum=False),
        nullable=False,
        default=TaskPriorityEnum.MEDIUM,
        index=True,
    )

    # Location / access metadata (ATA style)
    zone = Column(String(32), nullable=True)
    access_panel = Column(String(64), nullable=True)

    # Planning
    planned_start = Column(DateTime(timezone=True), nullable=True)
    planned_end = Column(DateTime(timezone=True), nullable=True)
    estimated_manhours = Column(Float, nullable=True)

    # Execution
    status = Column(
        SAEnum(TaskStatusEnum, name="task_status_enum", native_enum=False),
        nullable=False,
        default=TaskStatusEnum.PLANNED,
        index=True,
    )
    actual_start = Column(DateTime(timezone=True), nullable=True)
    actual_end = Column(DateTime(timezone=True), nullable=True)

    # Human factors / error-capturing
    error_capturing_method = Column(
        SAEnum(ErrorCapturingMethodEnum, name="task_error_capturing_method_enum", native_enum=False),
        nullable=True,
    )
    requires_duplicate_inspection = Column(Boolean, nullable=False, default=False)

    hf_notes = Column(Text, nullable=True)  # free-text HF remarks / cautions / instructions

    # Audit
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    work_order = relationship("WorkOrder", back_populates="tasks", lazy="joined")
    aircraft = relationship("Aircraft", lazy="joined")  # navigation helper

    component = relationship("AircraftComponent", lazy="joined")
    program_item = relationship("AmpProgramItem", lazy="joined")

    parent_task = relationship(
        "TaskCard",
        remote_side=[id],
        backref="child_tasks",
    )

    assignments = relationship(
        "TaskAssignment",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    steps = relationship(
        "TaskStep",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    inspector_signoffs = relationship(
        "InspectorSignOff",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    work_logs = relationship(
        "WorkLogEntry",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<TaskCard id={self.id} wo={self.work_order_id} status={self.status} title={self.title!r}>"


# ---------------------------------------------------------------------------
# TaskAssignment – who is allocated to the task
# ---------------------------------------------------------------------------


class TaskAssignment(Base):
    """
    Assignment of a TaskCard to a user (engineer / technician / inspector).

    Tracks:
    - role on task (LEAD / SUPPORT / INSPECTOR);
    - allocated man-hours;
    - assignment lifecycle (ASSIGNED / ACCEPTED / REJECTED / COMPLETED).
    """

    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", "role_on_task", name="uq_task_assignments_task_user_role"),
        Index("ix_task_assignments_amo_status", "amo_id", "status"),
        Index("ix_task_assignments_amo_user", "amo_id", "user_id"),
        Index("ix_task_assignments_task_status", "task_id", "status"),
        Index("ix_task_assignments_user_status", "user_id", "status"),
        CheckConstraint(
            "allocated_hours IS NULL OR allocated_hours >= 0",
            name="ck_task_assignments_allocated_hours_nonneg",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role_on_task = Column(
        SAEnum(TaskRoleOnTaskEnum, name="task_assignment_role_enum", native_enum=False),
        nullable=False,
        default=TaskRoleOnTaskEnum.SUPPORT,
        index=True,
    )

    allocated_hours = Column(Float, nullable=True)

    status = Column(
        SAEnum(TaskAssignmentStatusEnum, name="task_assignment_status_enum", native_enum=False),
        nullable=False,
        default=TaskAssignmentStatusEnum.ASSIGNED,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    task = relationship("TaskCard", back_populates="assignments", lazy="joined")
    user = relationship("User", lazy="joined")  # apps.accounts.models via "users"

    def __repr__(self) -> str:
        return f"<TaskAssignment id={self.id} task={self.task_id} user={self.user_id} role={self.role_on_task}>"


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
    __table_args__ = (
        Index("ix_work_log_amo_time", "amo_id", "start_time"),
        Index("ix_work_log_task_time", "task_id", "start_time"),
        Index("ix_work_log_user_time", "user_id", "start_time"),
        CheckConstraint("end_time >= start_time", name="ck_work_log_end_after_start"),
        CheckConstraint("actual_hours >= 0", name="ck_work_log_actual_hours_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Stored explicitly to make reporting easier and robust to timezone changes
    actual_hours = Column(Float, nullable=False)

    description = Column(Text, nullable=True)
    station = Column(String(16), nullable=True)  # ICAO / IATA / base

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    task = relationship("TaskCard", back_populates="work_logs", lazy="joined")
    user = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        return f"<WorkLogEntry id={self.id} task={self.task_id} hours={self.actual_hours}>"


# ---------------------------------------------------------------------------
# TaskStep – step-level execution scaffolding
# ---------------------------------------------------------------------------


class TaskStep(Base):
    """
    Step-by-step execution instructions for a TaskCard.
    """

    __tablename__ = "task_steps"
    __table_args__ = (
        UniqueConstraint("task_id", "step_no", name="uq_task_steps_task_stepno"),
        Index("ix_task_steps_task", "task_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_no = Column(Integer, nullable=False)
    instruction_text = Column(Text, nullable=False)
    required_flag = Column(Boolean, nullable=False, default=True)
    measurement_type = Column(String(32), nullable=True)
    expected_range = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    task = relationship("TaskCard", back_populates="steps", lazy="joined")
    executions = relationship(
        "TaskStepExecution",
        back_populates="task_step",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<TaskStep id={self.id} task={self.task_id} step_no={self.step_no}>"


class TaskStepExecution(Base):
    """
    Execution record for a TaskStep.
    """

    __tablename__ = "task_step_executions"
    __table_args__ = (
        Index("ix_task_step_exec_task", "task_id", "performed_at"),
        Index("ix_task_step_exec_user", "performed_by_user_id", "performed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_step_id = Column(
        Integer,
        ForeignKey("task_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    performed_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    performed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    result_text = Column(Text, nullable=True)
    measurement_value = Column(Float, nullable=True)
    attachment_id = Column(String(64), nullable=True)
    signed_flag = Column(Boolean, nullable=False, default=False)
    signature_hash = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    task_step = relationship("TaskStep", back_populates="executions", lazy="joined")
    task = relationship("TaskCard", lazy="joined")

    def __repr__(self) -> str:
        return f"<TaskStepExecution id={self.id} step={self.task_step_id} task={self.task_id}>"


class InspectorSignOff(Base):
    """
    Inspector sign-off at task or work-order level.
    """

    __tablename__ = "inspector_signoffs"
    __table_args__ = (
        Index("ix_inspector_signoffs_task", "amo_id", "task_card_id"),
        Index("ix_inspector_signoffs_workorder", "amo_id", "work_order_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_card_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    work_order_id = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    inspector_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    notes = Column(Text, nullable=True)
    signed_flag = Column(Boolean, nullable=False, default=False)
    signature_hash = Column(String(128), nullable=True)

    task = relationship("TaskCard", back_populates="inspector_signoffs", lazy="joined")
    work_order = relationship("WorkOrder", back_populates="inspector_signoffs", lazy="joined")

    def __repr__(self) -> str:
        return f"<InspectorSignOff id={self.id} task={self.task_card_id} work_order={self.work_order_id}>"
