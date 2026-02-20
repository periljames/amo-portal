from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field


class CourseBase(BaseModel):
    course_id: str
    name: str
    category: str | None = None
    owner_department: str | None = None
    delivery_mode: str = "Class"
    is_recurrent: bool = False
    recurrence_interval_months: int | None = None
    grace_window_days: int | None = None
    prerequisites_text: str | None = None
    minimum_outcome_type: str = "PassFail"
    minimum_score_optional: int | None = None
    active_flag: bool = True
    purpose: str | None = None
    evidence_requirements_json: dict = Field(default_factory=lambda: {"certificate_required": False, "attendance_required": True, "other_required_text": ""})


class CourseCreate(CourseBase):
    pass


class CourseRead(CourseBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True


class SessionRead(BaseModel):
    id: str
    tenant_id: str
    session_id: str
    course_id: str
    start_datetime: datetime
    end_datetime: datetime
    location_text: str | None = None
    instructor_user_id: str | None = None
    status: str
    capacity_optional: int | None = None
    notes_text: str | None = None

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    session_id: str
    course_id: str
    start_datetime: datetime
    end_datetime: datetime
    location_text: str | None = None
    instructor_user_id: str | None = None
    status: str = "Planned"
    capacity_optional: int | None = None
    notes_text: str | None = None


class AttendeeRead(BaseModel):
    id: str
    session_id: str
    staff_id: str
    attendance_status: str
    attendance_marked_at: datetime | None = None
    result_outcome: str | None = None
    score_optional: int | None = None
    remarks_text: str | None = None
    evidence_asset_ids: dict | None = None

    class Config:
        from_attributes = True


class AttendeeUpsert(BaseModel):
    staff_id: str
    attendance_status: str = "Unknown"
    result_outcome: str | None = None
    score_optional: int | None = None
    remarks_text: str | None = None
    evidence_asset_ids: dict | None = None


class CompletionRead(BaseModel):
    id: str
    completion_id: str
    staff_id: str
    course_id: str
    completion_date: date
    outcome: str
    next_due_date: date | None = None
    evidence_asset_ids: dict | None = None

    class Config:
        from_attributes = True


class SettingsRead(BaseModel):
    default_recurrence_interval_months: int
    default_grace_window_days: int
    certificate_mandatory_default: bool
    attendance_sheet_mandatory_default: bool


class SettingsUpdate(SettingsRead):
    pass
