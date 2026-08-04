from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


MigrationDataset = Literal[
    "AIRCRAFT_MASTER",
    "UTILISATION",
    "COMPONENT",
    "AMP_BASELINE",
    "DEFERRAL",
    "MAINTENANCE_RECORD",
]


class MigrationBatchCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    preset: Optional[str] = Field(default=None, max_length=64)
    target_aircraft_serial_number: Optional[str] = Field(default=None, max_length=50)
    target_registration: Optional[str] = Field(default=None, max_length=20)
    source_type: Literal["SPREADSHEET", "WINAIR", "CSV", "JSON", "MANUAL"] = "SPREADSHEET"
    source_reference: Optional[str] = Field(default=None, max_length=255)
    scope_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_target(self):
        if not self.target_aircraft_serial_number and not self.target_registration:
            raise ValueError("target aircraft serial number or registration is required")
        return self


class MigrationPresetCreate(BaseModel):
    source_reference: Optional[str] = Field(default=None, max_length=255)


class MigrationStageRow(BaseModel):
    dataset: MigrationDataset
    source_key: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any]


class MigrationStageRequest(BaseModel):
    rows: list[MigrationStageRow] = Field(min_length=1, max_length=10000)
    replace_existing_stage: bool = False


class MigrationCheckpointUpdate(BaseModel):
    status: Literal["PENDING", "COMPLETE", "BLOCKED", "NOT_APPLICABLE"]
    notes: Optional[str] = Field(default=None, max_length=2000)
    evidence_json: list[str] = Field(default_factory=list, max_length=100)


class MigrationReconciliationDecision(BaseModel):
    resolution: Literal["ACCEPT_SOURCE", "KEEP_LOCAL", "MERGE", "WAIVE"]
    resolution_notes: str = Field(min_length=3, max_length=2000)
    merged_payload: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def require_merged_payload(self):
        if self.resolution == "MERGE" and not self.merged_payload:
            raise ValueError("merged_payload is required when resolution is MERGE")
        return self


class MigrationApprovalRequest(BaseModel):
    approval_notes: str = Field(min_length=8, max_length=2000)


class MigrationCommitRequest(BaseModel):
    commit_notes: str = Field(min_length=8, max_length=2000)
    allow_partial: bool = False


class MigrationRollbackRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)


class MigrationRowRead(BaseModel):
    id: str
    batch_id: str
    dataset: str
    source_row_number: int
    source_key: str
    raw_json: dict[str, Any]
    normalized_json: dict[str, Any]
    status: str
    action: str
    errors_json: list[Any]
    warnings_json: list[Any]
    local_object_type: Optional[str] = None
    local_object_id: Optional[str] = None
    before_json: Optional[dict[str, Any]] = None
    after_json: Optional[dict[str, Any]] = None
    applied_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MigrationReconciliationRead(BaseModel):
    id: str
    batch_id: str
    row_id: str
    category: str
    severity: str
    status: str
    summary: str
    source_json: dict[str, Any]
    local_json: dict[str, Any]
    differences_json: dict[str, Any]
    resolution: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MigrationCheckpointRead(BaseModel):
    id: str
    batch_id: str
    checkpoint_key: str
    label: str
    status: str
    evidence_json: list[str]
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MigrationBatchRead(BaseModel):
    id: str
    name: str
    preset: Optional[str] = None
    target_aircraft_serial_number: Optional[str] = None
    target_registration: Optional[str] = None
    source_type: str
    source_reference: Optional[str] = None
    status: str
    mode: str
    scope_json: dict[str, Any]
    summary_json: dict[str, Any]
    cutover_checklist_json: dict[str, Any]
    rollback_manifest_json: list[dict[str, Any]]
    approved_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    rows: list[MigrationRowRead] = Field(default_factory=list)
    reconciliation_items: list[MigrationReconciliationRead] = Field(default_factory=list)
    checkpoints: list[MigrationCheckpointRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class MigrationSummaryRead(BaseModel):
    batches: int
    active_batches: int
    open_reconciliation: int
    staged_rows: int
    applied_rows: int
    failed_rows: int
    latest_batch: Optional[MigrationBatchRead] = None
