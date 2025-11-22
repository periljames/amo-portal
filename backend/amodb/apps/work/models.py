# backend/amodb/apps/work/models.py
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from ...database import Base


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)

    # Your WO format: YYNNNN, e.g. 250579
    wo_number = Column(String(10), nullable=False, unique=True)

    # Link to aircraft (574, 510, 331, etc.)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
    )

    amo_code = Column(String(20))  # optional multi-AMO support later

    description = Column(String(255))
    # 'A', 'C', '200HR', 'L', etc.
    check_type = Column(String(20))

    due_date = Column(Date)
    open_date = Column(Date)
    is_scheduled = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="Open")

    # Relationships
    aircraft = relationship("Aircraft", back_populates="work_orders")

    tasks = relationship(
        "WorkOrderTask",
        back_populates="work_order",
        cascade="all, delete-orphan",
    )

    crs_list = relationship(
        "CRS",
        back_populates="work_order",
    )


class WorkOrderTask(Base):
    __tablename__ = "work_order_tasks"

    id = Column(Integer, primary_key=True, index=True)

    work_order_id = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    task_code = Column(String(50), nullable=False)
    description = Column(Text)
    is_non_routine = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="Open")

    work_order = relationship("WorkOrder", back_populates="tasks")
