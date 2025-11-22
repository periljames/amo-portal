# backend/amodb/apps/work/schemas.py
from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class WorkOrderTaskBase(BaseModel):
    task_code: str
    description: Optional[str] = None
    is_non_routine: bool = False
    status: str = "Open"


class WorkOrderTaskCreate(WorkOrderTaskBase):
    pass


class WorkOrderTaskRead(WorkOrderTaskBase):
    id: int

    class Config:
        from_attributes = True


class WorkOrderBase(BaseModel):
    wo_number: str
    aircraft_serial_number: str
    amo_code: Optional[str] = None
    description: Optional[str] = None
    check_type: Optional[str] = None  # 'A', 'C', '200HR', 'L', etc.
    due_date: Optional[date] = None
    open_date: Optional[date] = None
    is_scheduled: bool = True
    status: str = "Open"


class WorkOrderCreate(WorkOrderBase):
    tasks: List[WorkOrderTaskCreate] = []


class WorkOrderUpdate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    amo_code: Optional[str] = None
    description: Optional[str] = None
    check_type: Optional[str] = None
    due_date: Optional[date] = None
    open_date: Optional[date] = None
    is_scheduled: Optional[bool] = None
    status: Optional[str] = None


class WorkOrderRead(WorkOrderBase):
    id: int
    tasks: List[WorkOrderTaskRead] = []

    class Config:
        from_attributes = True
