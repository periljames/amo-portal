from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ExecutionSessionCreate(BaseModel):
    work_package_id: int
    work_order_id: Optional[int] = None
    shift_reference: Optional[str] = Field(default=None, max_length=64)
    station: Optional[str] = Field(default=None, max_length=16)


class ExecutionEventCreate(BaseModel):
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: Literal[
        "SESSION_NOTE",
        "TASK_START",
        "TASK_PAUSE",
        "TASK_RESUME",
        "TASK_COMPLETE",
        "TASK_INSPECT",
        "EVIDENCE_ADDED",
        "SHIFT_HANDOVER",
        "PACKAGE_BLOCKED",
        "PACKAGE_UNBLOCKED",
    ]
    to_status: Optional[str] = Field(default=None, max_length=24)
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ExecutionEventRead(BaseModel):
    id: str
    session_id: str
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    payload_json: dict[str, Any]
    actor_user_id: Optional[str] = None
    occurred_at: datetime

    class Config:
        from_attributes = True


class TaskIssueCreate(BaseModel):
    work_order_id: int
    task_card_id: Optional[int] = None
    category: Literal["TECHNICAL", "MATERIAL", "TOOL", "DOCUMENT", "ACCESS", "HUMAN_FACTOR", "OTHER"]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3, max_length=4000)
    evidence_json: list[str] = Field(default_factory=list)


class TaskIssueResolve(BaseModel):
    disposition: Literal["RECTIFIED", "NON_ROUTINE", "DEFERRED", "NO_FAULT_FOUND", "CANCELLED"]
    resolution_notes: str = Field(min_length=3, max_length=4000)
    linked_non_routine_task_id: Optional[int] = None

    @model_validator(mode="after")
    def require_non_routine(self):
        if self.disposition == "NON_ROUTINE" and not self.linked_non_routine_task_id:
            raise ValueError("linked_non_routine_task_id is required for NON_ROUTINE disposition")
        return self


class TaskIssueRead(BaseModel):
    id: str
    session_id: str
    work_order_id: int
    task_card_id: Optional[int] = None
    category: str
    severity: str
    title: str
    description: str
    status: str
    disposition: Optional[str] = None
    linked_non_routine_task_id: Optional[int] = None
    evidence_json: list[str]
    raised_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None

    class Config:
        from_attributes = True


class ExecutionSessionClose(BaseModel):
    closure_notes: str = Field(min_length=3, max_length=4000)


class ExecutionSessionRead(BaseModel):
    id: str
    work_package_id: int
    work_order_id: Optional[int] = None
    package_freeze_id: str
    shift_reference: Optional[str] = None
    station: Optional[str] = None
    status: str
    started_at: datetime
    closed_at: Optional[datetime] = None
    closure_notes: Optional[str] = None
    events: list[ExecutionEventRead] = Field(default_factory=list)
    issues: list[TaskIssueRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class HandbackBuildRequest(BaseModel):
    work_package_id: int


class HandbackSubmitRequest(BaseModel):
    submission_notes: str = Field(min_length=3, max_length=4000)


class HandbackFindingCreate(BaseModel):
    category: Literal["MISSING_EVIDENCE", "TASK_INCOMPLETE", "SIGNOFF", "CRS", "CONFIGURATION", "UTILISATION", "DOCUMENT", "OTHER"]
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] = "ERROR"
    description: str = Field(min_length=3, max_length=4000)


class HandbackFindingResolve(BaseModel):
    response_notes: str = Field(min_length=3, max_length=4000)


class HandbackFindingRead(BaseModel):
    id: str
    handback_id: str
    category: str
    severity: str
    description: str
    status: str
    response_notes: Optional[str] = None
    raised_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HandbackReviewRequest(BaseModel):
    decision: Literal["ACCEPT", "REJECT"]
    review_notes: str = Field(min_length=3, max_length=4000)


class HandbackEventRead(BaseModel):
    id: str
    handback_id: str
    event_type: str
    from_status: Optional[str] = None
    to_status: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class HandbackRead(BaseModel):
    id: str
    work_package_id: int
    package_freeze_id: str
    version: int
    status: str
    manifest_hash: str
    manifest_json: dict[str, Any]
    readiness_json: dict[str, Any]
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    accepted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    findings: list[HandbackFindingRead] = Field(default_factory=list)
    events: list[HandbackEventRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ExecutionDashboardRead(BaseModel):
    open_sessions: int
    blocked_sessions: int
    open_issues: int
    critical_issues: int
    draft_handbacks: int
    submitted_handbacks: int
    rejected_handbacks: int
    accepted_handbacks: int
