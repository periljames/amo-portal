from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


WinAirDataset = Literal[
    "AIRCRAFT_MASTER",
    "AIRCRAFT_COUNTER",
    "FLIGHT_LOG",
    "MAINTENANCE_DUE",
    "INSPECTION_STATUS",
    "DEFERRAL",
]


class WinAirProfileCreate(BaseModel):
    integration_config_id: str
    name: str = Field(min_length=3, max_length=128)
    status: Literal["ACTIVE", "DISABLED"] = "ACTIVE"
    mode: Literal["SHADOW", "ACTIVE"] = "SHADOW"
    transport: Literal["API", "FILE", "WEBHOOK"] = "API"
    direction: Literal["BIDIRECTIONAL", "INBOUND_ONLY", "OUTBOUND_ONLY"] = "BIDIRECTIONAL"
    authority_json: dict[str, Literal["PORTAL", "WINAIR", "SHARED"]] = Field(
        default_factory=lambda: {
            "AIRCRAFT_MASTER": "PORTAL",
            "AIRCRAFT_COUNTER": "WINAIR",
            "FLIGHT_LOG": "WINAIR",
            "MAINTENANCE_DUE": "PORTAL",
            "INSPECTION_STATUS": "PORTAL",
            "DEFERRAL": "PORTAL",
        }
    )
    mapping_json: dict[str, Any] = Field(default_factory=dict)
    dataset_config_json: dict[str, Any] = Field(default_factory=dict)
    hours_tolerance: float = Field(default=0.05, ge=0, le=10)
    cycles_tolerance: int = Field(default=0, ge=0, le=100)


class WinAirProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=128)
    status: Optional[Literal["ACTIVE", "DISABLED"]] = None
    mode: Optional[Literal["SHADOW", "ACTIVE"]] = None
    transport: Optional[Literal["API", "FILE", "WEBHOOK"]] = None
    direction: Optional[Literal["BIDIRECTIONAL", "INBOUND_ONLY", "OUTBOUND_ONLY"]] = None
    authority_json: Optional[dict[str, Literal["PORTAL", "WINAIR", "SHARED"]]] = None
    mapping_json: Optional[dict[str, Any]] = None
    dataset_config_json: Optional[dict[str, Any]] = None
    hours_tolerance: Optional[float] = Field(default=None, ge=0, le=10)
    cycles_tolerance: Optional[int] = Field(default=None, ge=0, le=100)


class WinAirProfileRead(BaseModel):
    id: str
    integration_config_id: str
    name: str
    status: str
    mode: str
    transport: str
    direction: str
    authority_json: dict[str, Any]
    mapping_json: dict[str, Any]
    dataset_config_json: dict[str, Any]
    last_cursor_json: dict[str, Any]
    hours_tolerance: float
    cycles_tolerance: int
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WinAirInboundRecord(BaseModel):
    dataset: WinAirDataset
    external_key: str = Field(min_length=1, max_length=160)
    occurred_at: Optional[datetime] = None
    payload: dict[str, Any]


class WinAirInboundBatch(BaseModel):
    records: list[WinAirInboundRecord] = Field(min_length=1, max_length=5000)
    cursor: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class WinAirExportRequest(BaseModel):
    datasets: list[Literal["MAINTENANCE_DUE", "INSPECTION_STATUS", "DEFERRAL"]] = Field(
        default_factory=lambda: ["MAINTENANCE_DUE", "INSPECTION_STATUS", "DEFERRAL"]
    )
    horizon_days: int = Field(default=90, ge=1, le=730)
    aircraft_serial_numbers: list[str] = Field(default_factory=list, max_length=500)


class WinAirReconcileRequest(BaseModel):
    datasets: list[WinAirDataset] = Field(
        default_factory=lambda: ["AIRCRAFT_COUNTER", "FLIGHT_LOG", "MAINTENANCE_DUE", "DEFERRAL"]
    )


class WinAirRunRead(BaseModel):
    id: str
    profile_id: str
    run_type: str
    status: str
    dry_run: bool
    requested_datasets_json: list[str]
    cursor_before_json: dict[str, Any]
    cursor_after_json: dict[str, Any]
    counts_json: dict[str, Any]
    started_at: datetime
    finished_at: Optional[datetime] = None
    error_summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WinAirRecordRead(BaseModel):
    id: str
    run_id: str
    profile_id: str
    dataset: str
    direction: str
    external_key: str
    local_object_type: Optional[str] = None
    local_object_id: Optional[str] = None
    action: str
    status: str
    source_payload_json: dict[str, Any]
    normalized_payload_json: dict[str, Any]
    error: Optional[str] = None
    created_at: datetime
    applied_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WinAirConflictRead(BaseModel):
    id: str
    profile_id: str
    run_id: str
    record_id: str
    dataset: str
    external_key: str
    conflict_type: str
    source_payload_json: dict[str, Any]
    local_payload_json: dict[str, Any]
    field_differences_json: dict[str, Any]
    status: str
    resolution_notes: Optional[str] = None
    resolved_by_user_id: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WinAirConflictDecision(BaseModel):
    decision: Literal["ACCEPT_EXTERNAL", "KEEP_LOCAL", "MERGED", "IGNORED"]
    resolution_notes: str = Field(min_length=3, max_length=2000)
    merged_payload: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def require_merged_payload(self):
        if self.decision == "MERGED" and not self.merged_payload:
            raise ValueError("merged_payload is required for a MERGED decision")
        return self


class WinAirDashboardRead(BaseModel):
    profiles: int
    active_profiles: int
    shadow_profiles: int
    open_conflicts: int
    failed_records: int
    pending_outbox: int
    latest_run: Optional[WinAirRunRead] = None
    dataset_counts: dict[str, int] = Field(default_factory=dict)


class WinAirAircraftCounterPayload(BaseModel):
    aircraft_serial_number: Optional[str] = None
    registration: Optional[str] = None
    entry_date: date
    techlog_no: str = Field(min_length=1, max_length=64)
    total_hours: float = Field(ge=0)
    total_cycles: float = Field(ge=0)
    station: Optional[str] = Field(default=None, max_length=16)
    remarks: Optional[str] = None

    @model_validator(mode="after")
    def require_aircraft_identity(self):
        if not self.aircraft_serial_number and not self.registration:
            raise ValueError("aircraft_serial_number or registration is required")
        return self
