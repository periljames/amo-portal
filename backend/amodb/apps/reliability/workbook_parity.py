from __future__ import annotations

import hashlib
import html
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.database import Base, get_write_db
from amodb.security import get_current_active_user

from . import models as reliability_models

UTC = timezone.utc
MAX_PAGE_SIZE = 250
MAX_EXPORT_ROWS = 10_000


class WorkbookDatasetCode(str, Enum):
    AU = "AU"
    AI = "AI"
    PM = "PM"
    OOS = "OOS"
    RM = "RM"
    SM = "SM"
    STRUCTURES = "STRUCTURES"
    RECURRING = "RECURRING"
    ECTM = "ECTM"


class WorkbookRecordStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class ReliabilityWorkbookRecord(Base):
    __tablename__ = "reliability_workbook_records"
    __table_args__ = (
        UniqueConstraint("amo_id", "dataset_code", "record_number", "revision", name="uq_rel_workbook_record_revision"),
        Index("ix_rel_workbook_records_scope_date", "amo_id", "dataset_code", "event_date"),
        Index("ix_rel_workbook_records_aircraft", "amo_id", "aircraft_serial_number", "event_date"),
        Index("ix_rel_workbook_records_status", "amo_id", "dataset_code", "status"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_code = Column(String(24), nullable=False, index=True)
    record_number = Column(String(80), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default=WorkbookRecordStatus.DRAFT.value, index=True)
    event_date = Column(Date, nullable=False, index=True)
    event_end_date = Column(Date, nullable=True, index=True)
    aircraft_serial_number = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="SET NULL"), nullable=True, index=True)
    ata_chapter = Column(String(20), nullable=True, index=True)
    reference_code = Column(String(128), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    derived_values = Column(JSONB, nullable=False, default=dict)
    source_workbook = Column(String(255), nullable=True)
    source_sheet = Column(String(128), nullable=True)
    source_row_number = Column(Integer, nullable=True)
    source_hash = Column(String(64), nullable=True, index=True)
    canonical_event_id = Column(Integer, ForeignKey("reliability_events.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    approved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityWorkbookFieldMapping(Base):
    __tablename__ = "reliability_workbook_field_mappings"
    __table_args__ = (
        UniqueConstraint("amo_id", "profile_code", "dataset_code", "source_sheet", "source_column", name="uq_rel_workbook_field_mapping"),
        Index("ix_rel_workbook_mapping_profile", "amo_id", "profile_code"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_code = Column(String(64), nullable=False, index=True)
    profile_name = Column(String(255), nullable=False)
    workbook_family = Column(String(64), nullable=False, index=True)
    dataset_code = Column(String(24), nullable=False, index=True)
    source_sheet = Column(String(128), nullable=False)
    source_column = Column(String(255), nullable=False)
    canonical_field = Column(String(128), nullable=False)
    data_type = Column(String(32), nullable=False)
    required = Column(Boolean, nullable=False, default=False)
    unit = Column(String(32), nullable=True)
    aliases = Column(JSONB, nullable=False, default=list)
    transform = Column(JSONB, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityStatisticalAlertResult(Base):
    __tablename__ = "reliability_statistical_alert_results"
    __table_args__ = (
        Index("ix_rel_stat_alert_metric_scope", "amo_id", "metric_code", "scope_type", "scope_value"),
        Index("ix_rel_stat_alert_period", "amo_id", "period_start", "period_end"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_code = Column(String(128), nullable=False, index=True)
    metric_label = Column(String(255), nullable=False)
    source_kind = Column(String(32), nullable=False)
    dataset_code = Column(String(24), nullable=True)
    metric_field = Column(String(128), nullable=True)
    scope_type = Column(String(32), nullable=False, default="FLEET")
    scope_value = Column(String(128), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    bucket = Column(String(16), nullable=False)
    sample_size = Column(Integer, nullable=False)
    mean_value = Column(Numeric(20, 6), nullable=False)
    sample_stddev = Column(Numeric(20, 6), nullable=False)
    warning_multiplier = Column(Numeric(10, 4), nullable=False)
    alert_multiplier = Column(Numeric(10, 4), nullable=False)
    warning_level = Column(Numeric(20, 6), nullable=False)
    alert_level = Column(Numeric(20, 6), nullable=False)
    formula = Column(Text, nullable=False)
    series = Column(JSONB, nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityReportLayout(Base):
    __tablename__ = "reliability_report_layouts"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", "revision", name="uq_rel_report_layout_revision"),
        Index("ix_rel_report_layout_active", "amo_id", "active", "aircraft_family"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    aircraft_family = Column(String(64), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    sections = Column(JSONB, nullable=False)
    page_settings = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityWorkbookReportSnapshot(Base):
    __tablename__ = "reliability_workbook_report_snapshots"
    __table_args__ = (
        Index("ix_rel_workbook_report_period", "amo_id", "period_start", "period_end"),
        Index("ix_rel_workbook_report_layout", "layout_id", "generated_at"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    layout_id = Column(Integer, ForeignKey("reliability_report_layouts.id", ondelete="RESTRICT"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    aircraft_filter = Column(JSONB, nullable=False, default=list)
    rendered_data = Column(JSONB, nullable=False)
    rendered_html = Column(Text, nullable=False)
    sha256_hash = Column(String(64), nullable=False, index=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class FieldDefinition(BaseModel):
    key: str
    label: str
    data_type: Literal["text", "textarea", "date", "datetime", "decimal", "integer", "boolean", "select"]
    required: bool = False
    unit: str | None = None
    options: list[str] = Field(default_factory=list)
    help_text: str | None = None


class DatasetDefinition(BaseModel):
    code: WorkbookDatasetCode
    name: str
    workbook_sheet_names: list[str]
    description: str
    event_type: str | None = None
    fields: list[FieldDefinition]


class WorkbookRecordCreate(BaseModel):
    dataset_code: WorkbookDatasetCode
    event_date: date
    event_end_date: date | None = None
    aircraft_serial_number: str | None = Field(default=None, max_length=50)
    ata_chapter: str | None = Field(default=None, max_length=20)
    reference_code: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    payload: dict[str, Any]
    source_workbook: str | None = Field(default=None, max_length=255)
    source_sheet: str | None = Field(default=None, max_length=128)
    source_row_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.event_end_date and self.event_end_date < self.event_date:
            raise ValueError("Event end date cannot precede event date.")
        return self


class WorkbookRecordRead(BaseModel):
    id: int
    dataset_code: str
    record_number: str
    revision: int
    status: str
    event_date: date
    event_end_date: date | None
    aircraft_serial_number: str | None
    ata_chapter: str | None
    reference_code: str | None
    title: str
    description: str | None
    payload: dict[str, Any]
    derived_values: dict[str, Any]
    source_workbook: str | None
    source_sheet: str | None
    source_row_number: int | None
    canonical_event_id: int | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    closed_at: datetime | None

    class Config:
        from_attributes = True


class RecordAction(BaseModel):
    note: str = Field(min_length=2, max_length=2000)


class MappingCreate(BaseModel):
    profile_code: str = Field(min_length=2, max_length=64)
    profile_name: str = Field(min_length=2, max_length=255)
    workbook_family: str = Field(min_length=2, max_length=64)
    dataset_code: WorkbookDatasetCode
    source_sheet: str = Field(min_length=1, max_length=128)
    source_column: str = Field(min_length=1, max_length=255)
    canonical_field: str = Field(min_length=1, max_length=128)
    data_type: str = Field(min_length=1, max_length=32)
    required: bool = False
    unit: str | None = Field(default=None, max_length=32)
    aliases: list[str] = Field(default_factory=list)
    transform: dict[str, Any] = Field(default_factory=dict)


class StatisticalAlertRequest(BaseModel):
    metric_code: str = Field(min_length=2, max_length=128)
    metric_label: str = Field(min_length=2, max_length=255)
    source_kind: Literal["EVENT_COUNT", "EVENT_RATE_PER_100_FH", "DATASET_COUNT", "DATASET_FIELD"]
    period_start: date
    period_end: date
    bucket: Literal["WEEK", "MONTH"] = "MONTH"
    event_types: list[str] = Field(default_factory=list)
    dataset_code: WorkbookDatasetCode | None = None
    metric_field: str | None = None
    aircraft_serial_number: str | None = None
    ata_chapter: str | None = None
    warning_multiplier: Decimal = Decimal("1")
    alert_multiplier: Decimal = Decimal("2")

    @model_validator(mode="after")
    def validate_contract(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end must be on or after period start.")
        if (self.period_end - self.period_start).days > 1826:
            raise ValueError("Statistical alert windows are limited to five years.")
        if self.source_kind.startswith("DATASET") and not self.dataset_code:
            raise ValueError("Dataset code is required for dataset-based alert calculations.")
        if self.source_kind == "DATASET_FIELD" and not self.metric_field:
            raise ValueError("Metric field is required for dataset-field calculations.")
        if self.warning_multiplier < 0 or self.alert_multiplier <= 0:
            raise ValueError("Alert multipliers must be non-negative and the alert multiplier must be positive.")
        if self.alert_multiplier < self.warning_multiplier:
            raise ValueError("Alert multiplier cannot be less than warning multiplier.")
        return self


class ReportLayoutCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    aircraft_family: str = Field(min_length=2, max_length=64)
    sections: list[dict[str, Any]]
    page_settings: dict[str, Any] = Field(default_factory=dict)


class ReportRenderRequest(BaseModel):
    layout_id: int
    period_start: date
    period_end: date
    aircraft: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end must be on or after period start.")
        if (self.period_end - self.period_start).days > 1826:
            raise ValueError("Report windows are limited to five years.")
        return self


def _field(key: str, label: str, data_type: str = "text", *, required: bool = False, unit: str | None = None, options: Iterable[str] = (), help_text: str | None = None) -> FieldDefinition:
    return FieldDefinition(key=key, label=label, data_type=data_type, required=required, unit=unit, options=list(options), help_text=help_text)


DATASET_CATALOG: dict[WorkbookDatasetCode, DatasetDefinition] = {
    WorkbookDatasetCode.AU: DatasetDefinition(code=WorkbookDatasetCode.AU, name="Aircraft utilisation", workbook_sheet_names=["AU", "AIRCRAFT UTILIZATION", "AIRCRAFT UTILISATION"], description="Daily aircraft, engine and APU exposure used as controlled Reliability denominators.", fields=[_field("flight_hours", "Aircraft flight hours", "decimal", required=True, unit="FH"), _field("flight_cycles", "Aircraft flight cycles", "integer", required=True, unit="FC"), _field("landings", "Landings", "integer", unit="LDG"), _field("engine_1_hours", "Engine 1 hours", "decimal", unit="EH"), _field("engine_1_cycles", "Engine 1 cycles", "integer"), _field("engine_2_hours", "Engine 2 hours", "decimal", unit="EH"), _field("engine_2_cycles", "Engine 2 cycles", "integer"), _field("apu_hours", "APU hours", "decimal", unit="AH"), _field("apu_cycles", "APU cycles", "integer"), _field("source_reference", "Logbook / utilisation reference", required=True), _field("remarks", "Remarks", "textarea")]),
    WorkbookDatasetCode.AI: DatasetDefinition(code=WorkbookDatasetCode.AI, name="Aircraft incidents", workbook_sheet_names=["AI", "AIRCRAFT INCIDENTS"], description="Aircraft incident and serious technical-event evidence with investigation and operational consequence fields.", event_type="SAFETY_EVENT", fields=[_field("incident_number", "Incident number", required=True), _field("event_type", "Incident type", "select", required=True, options=["ACCIDENT", "SERIOUS_INCIDENT", "INCIDENT", "GROUND_DAMAGE", "OTHER"]), _field("occurred_at", "Occurrence date and time", "datetime", required=True), _field("location", "Location / station", required=True), _field("phase_of_flight", "Phase of flight", "select", options=["GROUND", "TAXI", "TAKEOFF", "CLIMB", "CRUISE", "DESCENT", "APPROACH", "LANDING", "MAINTENANCE"]), _field("component_part_number", "Component part number"), _field("component_serial_number", "Component serial number"), _field("damage_description", "Aircraft / component damage", "textarea"), _field("injury_information", "Injury information", "textarea"), _field("operational_consequence", "Operational consequence", "textarea"), _field("investigation_reference", "Investigation reference"), _field("action_taken", "Immediate / corrective action", "textarea", required=True), _field("severity", "Severity", "select", required=True, options=["LOW", "MEDIUM", "HIGH", "CRITICAL"])]),
    WorkbookDatasetCode.PM: DatasetDefinition(code=WorkbookDatasetCode.PM, name="Pilot and maintenance reports", workbook_sheet_names=["PM", "PILOT REPORTS", "MAINTENANCE REPORTS", "PIREP", "MAREP"], description="Technical-log pilot, cabin and maintenance reports with rectification, component and recurrence evidence.", event_type="PILOT_REPORT", fields=[_field("report_type", "Report type", "select", required=True, options=["PILOT", "MAINTENANCE", "CABIN"]), _field("logbook_reference", "Technical log reference", required=True), _field("flight_number", "Flight number"), _field("station", "Station"), _field("defect_description", "Defect / report", "textarea", required=True), _field("action_taken", "Maintenance action", "textarea", required=True), _field("deferred_reference", "MEL/CDL / deferred reference"), _field("component_part_number", "Part number"), _field("component_serial_number", "Serial number"), _field("work_order_reference", "Work order reference"), _field("repeat_key", "Controlled recurrence key"), _field("is_repeat", "Repeat report", "boolean"), _field("closed_date", "Closure date", "date")]),
    WorkbookDatasetCode.OOS: DatasetDefinition(code=WorkbookDatasetCode.OOS, name="Aircraft out of service", workbook_sheet_names=["OS", "OOS", "OUT OF SERVICE"], description="Out-of-service intervals, downtime cause, availability exposure, restoration evidence and MTTR inputs.", event_type="OTHER", fields=[_field("start_at", "Out-of-service start", "datetime", required=True), _field("end_at", "Returned-to-service time", "datetime"), _field("reason_category", "Reason category", "select", required=True, options=["TECHNICAL", "SCHEDULED_MAINTENANCE", "UNSCHEDULED_MAINTENANCE", "PARTS", "MANPOWER", "FACILITY", "OTHER"]), _field("defect_reference", "Defect reference"), _field("work_order_reference", "Work order / workpack reference"), _field("maintenance_action", "Maintenance action", "textarea", required=True), _field("scheduled_available_hours", "Scheduled available hours", "decimal", unit="h"), _field("cancelled_flights", "Cancelled flights", "integer"), _field("delay_minutes", "Associated delay minutes", "integer", unit="min"), _field("release_reference", "Return-to-service / CRS reference"), _field("responsible_area", "Responsible area")]),
    WorkbookDatasetCode.RM: DatasetDefinition(code=WorkbookDatasetCode.RM, name="Component removals", workbook_sheet_names=["RM", "COMPONENT REMOVALS", "REMOVALS"], description="Complete off/on component identity, removal classification, life at removal and disposition evidence.", event_type="UNSCHEDULED_REMOVAL", fields=[_field("removed_at", "Removal date and time", "datetime", required=True), _field("position", "Installed position"), _field("component_description", "Component description", required=True), _field("off_part_number", "Removed part number", required=True), _field("off_serial_number", "Removed serial number", required=True), _field("on_part_number", "Installed part number"), _field("on_serial_number", "Installed serial number"), _field("removal_type", "Removal type", "select", required=True, options=["SCHEDULED", "UNSCHEDULED", "ROBBERY", "MODIFICATION", "TEST"]), _field("reason_code", "Removal reason / failure mode", required=True), _field("confirmed_failure", "Confirmed failure", "boolean"), _field("hours_at_removal", "Component hours at removal", "decimal", unit="h"), _field("cycles_at_removal", "Component cycles at removal", "integer", unit="cy"), _field("time_since_new", "Time since new", "decimal", unit="h"), _field("cycles_since_new", "Cycles since new", "integer"), _field("shop_order_reference", "Shop order reference"), _field("vendor", "Vendor / repair agency"), _field("disposition", "Disposition", "textarea")]),
    WorkbookDatasetCode.SM: DatasetDefinition(code=WorkbookDatasetCode.SM, name="Scheduled maintenance findings", workbook_sheet_names=["SM", "SCHEDULED MAINTENANCE"], description="Findings raised during scheduled checks with workpack, task, programme-item and closure provenance.", event_type="DEFECT", fields=[_field("check_type", "Check / maintenance package", required=True), _field("workpack_reference", "Workpack reference", required=True), _field("task_card_reference", "Task card reference"), _field("programme_item_reference", "AMP / programme item reference"), _field("finding_classification", "Finding classification", "select", required=True, options=["ROUTINE", "NON_ROUTINE", "STRUCTURAL", "CORROSION", "FUNCTIONAL_FAILURE", "OTHER"]), _field("finding_description", "Finding description", "textarea", required=True), _field("corrective_action", "Corrective action", "textarea", required=True), _field("component_part_number", "Part number"), _field("component_serial_number", "Serial number"), _field("man_hours", "Finding man-hours", "decimal", unit="MH"), _field("deferred_reference", "Deferral reference"), _field("close_date", "Closure date", "date"), _field("release_reference", "Release reference")]),
    WorkbookDatasetCode.STRUCTURES: DatasetDefinition(code=WorkbookDatasetCode.STRUCTURES, name="Aircraft structures", workbook_sheet_names=["AIRCRAFT STRUCTURES", "STRUCTURES", "STRUCTURAL REPORTS"], description="Structural damage, location, limits, repair classification, repeat inspections and permanent-record evidence.", event_type="DEFECT", fields=[_field("damage_reference", "Damage / dent reference", required=True), _field("zone", "Aircraft zone"), _field("station", "Fuselage / wing station"), _field("frame", "Frame"), _field("stringer", "Stringer"), _field("skin_panel", "Skin / panel"), _field("damage_type", "Damage type", "select", required=True, options=["DENT", "CRACK", "CORROSION", "GOUGE", "PUNCTURE", "DELAMINATION", "OTHER"]), _field("dimensions", "Damage dimensions", required=True), _field("allowable_limits_reference", "SRM / approved limits reference", required=True), _field("repair_class", "Repair classification", "select", required=True, options=["WITHIN_LIMITS", "TEMPORARY_REPAIR", "PERMANENT_REPAIR", "OEM_DISPOSITION_REQUIRED"]), _field("repair_reference", "Repair / engineering order reference"), _field("inspection_interval", "Repeat inspection interval"), _field("next_inspection_due", "Next inspection due", "date"), _field("status", "Structural item status", "select", required=True, options=["OPEN", "MONITORING", "REPAIRED", "CLOSED"]), _field("evidence_reference", "Photo / drawing / NDT evidence reference"), _field("description", "Structural description", "textarea", required=True)]),
    WorkbookDatasetCode.RECURRING: DatasetDefinition(code=WorkbookDatasetCode.RECURRING, name="Recurring defects", workbook_sheet_names=["RECURRING DEFECTS", "REPEAT DEFECTS"], description="Dedicated recurrence groups with controlled repeat key, occurrence history, corrective action and effectiveness evidence.", event_type="REPEAT_DEFECT", fields=[_field("repeat_key", "Controlled repeat key", required=True), _field("first_seen", "First occurrence", "date", required=True), _field("last_seen", "Latest occurrence", "date", required=True), _field("origin", "Origin / source", "select", required=True, options=["PIREP", "MAREP", "SCHEDULED_MAINTENANCE", "COMPONENT_REMOVAL", "SHOP", "OTHER"]), _field("defect_description", "Recurring defect", "textarea", required=True), _field("occurrence_count", "Occurrence count", "integer", required=True), _field("recurrence_window_days", "Recurrence window", "integer", required=True, unit="days"), _field("corrective_action", "Corrective action", "textarea"), _field("part_number", "Part number"), _field("serial_number", "Serial number"), _field("work_order_reference", "Work order reference"), _field("fracas_case_id", "FRACAS case ID", "integer"), _field("effectiveness_result", "Effectiveness result", "select", options=["PENDING", "EFFECTIVE", "INEFFECTIVE"]), _field("status", "Recurrence status", "select", required=True, options=["OPEN", "UNDER_INVESTIGATION", "ACTIONED", "MONITORING", "CLOSED"])]),
    WorkbookDatasetCode.ECTM: DatasetDefinition(code=WorkbookDatasetCode.ECTM, name="Engine condition and trend monitoring", workbook_sheet_names=["NC", "ECTM", "EHM", "ENGINE CONDITION"], description="Numeric engine trend parameters plus oil-analysis, borescope, analyst review and OEM recommendation status.", event_type="ECTM", fields=[_field("engine_position", "Engine position", required=True), _field("engine_serial_number", "Engine serial number"), _field("flight_leg", "Flight leg"), _field("phase", "Measurement phase"), _field("pressure_altitude_ft", "Pressure altitude", "decimal", unit="ft"), _field("oat_c", "Outside air temperature", "decimal", unit="°C"), _field("isa_dev_c", "ISA deviation", "decimal", unit="°C"), _field("power_reference", "Power reference", "decimal"), _field("itt_c", "ITT / EGT", "decimal", unit="°C"), _field("ng_pct", "Ng / N1", "decimal", unit="%"), _field("nh_pct", "Nh / N2", "decimal", unit="%"), _field("np_rpm", "Propeller speed", "decimal", unit="rpm"), _field("torque", "Torque", "decimal"), _field("fuel_flow", "Fuel flow", "decimal"), _field("oil_pressure", "Oil pressure", "decimal"), _field("oil_temperature", "Oil temperature", "decimal", unit="°C"), _field("vibration", "Vibration", "decimal"), _field("oil_analysis_status", "Oil analysis status", "select", options=["NOT_DUE", "PENDING", "NORMAL", "WATCH", "ALERT"]), _field("oil_analysis_reference", "Oil analysis report reference"), _field("borescope_status", "Borescope status", "select", options=["NOT_DUE", "PENDING", "SATISFACTORY", "MONITOR", "UNSATISFACTORY"]), _field("borescope_reference", "Borescope report reference"), _field("trend_status", "Trend status", "select", required=True, options=["NOT_EVALUATED", "NORMAL", "WATCH", "SHIFT", "ALERT"]), _field("analyst_comments", "Analyst comments", "textarea"), _field("oem_recommendation", "OEM recommendation", "textarea"), _field("review_date", "Review date", "date"), _field("reviewed_by", "Reviewed by"), _field("action_required", "Action required", "textarea")]),
}


DEFAULT_LAYOUTS = [
    {"code": "C208B-RP", "name": "Cessna 208B Reliability Programme Report", "aircraft_family": "C208B", "sections": [{"code": "EXECUTIVE", "title": "Executive summary", "kind": "SUMMARY"}, {"code": "AU", "title": "Aircraft utilisation", "kind": "DATASET", "dataset_code": "AU"}, {"code": "EVENTS", "title": "Operational interruptions", "kind": "EVENTS"}, {"code": "PM", "title": "Pilot and maintenance reports", "kind": "DATASET", "dataset_code": "PM"}, {"code": "RM", "title": "Component removals", "kind": "DATASET", "dataset_code": "RM"}, {"code": "OOS", "title": "Out-of-service and availability", "kind": "DATASET", "dataset_code": "OOS"}, {"code": "RECURRING", "title": "Recurring defects", "kind": "DATASET", "dataset_code": "RECURRING"}, {"code": "ECTM", "title": "Engine condition monitoring", "kind": "DATASET", "dataset_code": "ECTM"}, {"code": "ALERTS", "title": "Statistical alert calculations", "kind": "STATISTICAL_ALERTS"}]},
    {"code": "DHC8-RP", "name": "DHC8 Reliability Programme Report", "aircraft_family": "DHC8", "sections": [{"code": "EXECUTIVE", "title": "Executive summary", "kind": "SUMMARY"}, {"code": "AU", "title": "Fleet and engine utilisation", "kind": "DATASET", "dataset_code": "AU"}, {"code": "AI", "title": "Aircraft incidents", "kind": "DATASET", "dataset_code": "AI"}, {"code": "EVENTS", "title": "Flight interruptions", "kind": "EVENTS"}, {"code": "SM", "title": "Scheduled maintenance findings", "kind": "DATASET", "dataset_code": "SM"}, {"code": "STRUCTURES", "title": "Structural damage and repairs", "kind": "DATASET", "dataset_code": "STRUCTURES"}, {"code": "RM", "title": "Component removals", "kind": "DATASET", "dataset_code": "RM"}, {"code": "OOS", "title": "Out-of-service and availability", "kind": "DATASET", "dataset_code": "OOS"}, {"code": "RECURRING", "title": "Recurring defects", "kind": "DATASET", "dataset_code": "RECURRING"}, {"code": "ECTM", "title": "Engine condition monitoring", "kind": "DATASET", "dataset_code": "ECTM"}, {"code": "ALERTS", "title": "Statistical alert calculations", "kind": "STATISTICAL_ALERTS"}]},
    {"code": "OPERATOR-RP", "name": "Operator-configurable Reliability Programme Report", "aircraft_family": "OPERATOR", "sections": [{"code": code.value, "title": definition.name, "kind": "DATASET", "dataset_code": code.value} for code, definition in DATASET_CATALOG.items()] + [{"code": "ALERTS", "title": "Statistical alert calculations", "kind": "STATISTICAL_ALERTS"}]},
]


def _amo_id(user: account_models.User) -> str:
    amo_id = user.effective_amo_id
    if not amo_id:
        raise HTTPException(status_code=403, detail="A tenant context is required.")
    return str(amo_id)


def _now() -> datetime:
    return datetime.now(UTC)


def _decimal(value: Any, field_name: str, *, minimum: Decimal | None = Decimal("0")) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a valid number.")
    if not result.is_finite():
        raise HTTPException(status_code=422, detail=f"{field_name} must be finite.")
    if minimum is not None and result < minimum:
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be less than {minimum}.")
    return result


def _integer(value: Any, field_name: str, *, minimum: int = 0) -> int:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a whole number.")
    if number != number.to_integral_value() or number < minimum:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a whole number of at least {minimum}.")
    return int(number)


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{field_name} must be an ISO date-time.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalise_payload(dataset: DatasetDefinition, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalised: dict[str, Any] = {}
    derived: dict[str, Any] = {}
    fields = {field.key: field for field in dataset.fields}
    unknown = sorted(set(payload) - set(fields))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown {dataset.code.value} fields: {', '.join(unknown)}")
    for key, definition in fields.items():
        raw = payload.get(key)
        if raw in (None, ""):
            if definition.required:
                raise HTTPException(status_code=422, detail=f"{definition.label} is required.")
            normalised[key] = None
            continue
        if definition.data_type == "decimal":
            normalised[key] = format(_decimal(raw, definition.label), "f")
        elif definition.data_type == "integer":
            normalised[key] = _integer(raw, definition.label)
        elif definition.data_type == "boolean":
            if isinstance(raw, bool):
                normalised[key] = raw
            elif str(raw).lower() in {"true", "1", "yes", "on"}:
                normalised[key] = True
            elif str(raw).lower() in {"false", "0", "no", "off"}:
                normalised[key] = False
            else:
                raise HTTPException(status_code=422, detail=f"{definition.label} must be true or false.")
        elif definition.data_type == "select":
            value = str(raw).strip().upper()
            if definition.options and value not in definition.options:
                raise HTTPException(status_code=422, detail=f"{definition.label} must be one of: {', '.join(definition.options)}")
            normalised[key] = value
        elif definition.data_type == "date":
            try:
                normalised[key] = date.fromisoformat(str(raw)).isoformat()
            except ValueError:
                raise HTTPException(status_code=422, detail=f"{definition.label} must be an ISO date.")
        elif definition.data_type == "datetime":
            normalised[key] = _parse_datetime(raw, definition.label).isoformat()
        else:
            normalised[key] = str(raw).strip()

    if dataset.code == WorkbookDatasetCode.OOS:
        start_at = _parse_datetime(normalised["start_at"], "Out-of-service start")
        end_raw = normalised.get("end_at")
        if end_raw:
            end_at = _parse_datetime(end_raw, "Returned-to-service time")
            if end_at < start_at:
                raise HTTPException(status_code=422, detail="Returned-to-service time cannot precede the out-of-service start.")
            downtime_hours = Decimal(str((end_at - start_at).total_seconds())) / Decimal("3600")
            derived["downtime_hours"] = format(downtime_hours.quantize(Decimal("0.001")), "f")
            scheduled = normalised.get("scheduled_available_hours")
            if scheduled not in (None, ""):
                scheduled_hours = _decimal(scheduled, "Scheduled available hours")
                available = max(scheduled_hours - downtime_hours, Decimal("0"))
                derived["available_hours"] = format(available.quantize(Decimal("0.001")), "f")
                derived["availability_pct"] = format(((available / scheduled_hours) * Decimal("100")).quantize(Decimal("0.001")), "f") if scheduled_hours > 0 else None
    if dataset.code == WorkbookDatasetCode.RM and normalised.get("removal_type") == "UNSCHEDULED" and not normalised.get("reason_code"):
        raise HTTPException(status_code=422, detail="An unscheduled removal requires a failure mode or reason code.")
    if dataset.code == WorkbookDatasetCode.RECURRING:
        first = date.fromisoformat(normalised["first_seen"])
        last = date.fromisoformat(normalised["last_seen"])
        if last < first:
            raise HTTPException(status_code=422, detail="Latest recurrence cannot precede the first occurrence.")
        if int(normalised["occurrence_count"]) < 2:
            raise HTTPException(status_code=422, detail="A recurring defect must contain at least two occurrences.")
    return normalised, derived


def _record_number(db: Session, amo_id: str, dataset_code: str, event_date: date) -> str:
    prefix = f"{dataset_code}-{event_date:%Y%m}"
    count = db.query(func.count(ReliabilityWorkbookRecord.id)).filter(ReliabilityWorkbookRecord.amo_id == amo_id, ReliabilityWorkbookRecord.dataset_code == dataset_code, ReliabilityWorkbookRecord.record_number.like(f"{prefix}-%")).scalar() or 0
    return f"{prefix}-{int(count) + 1:05d}"


def _validate_aircraft(db: Session, amo_id: str, serial: str | None) -> None:
    if not serial:
        return
    exists = db.query(fleet_models.Aircraft.serial_number).filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.serial_number == serial).first()
    if not exists:
        raise HTTPException(status_code=422, detail="The selected aircraft is not active in this tenant fleet.")


def _event_type_for(record: ReliabilityWorkbookRecord) -> reliability_models.ReliabilityEventTypeEnum | None:
    code = WorkbookDatasetCode(record.dataset_code)
    if code == WorkbookDatasetCode.AU:
        return None
    if code == WorkbookDatasetCode.PM:
        report_type = str(record.payload.get("report_type") or "PILOT")
        return reliability_models.ReliabilityEventTypeEnum.CABIN_REPORT if report_type == "CABIN" else reliability_models.ReliabilityEventTypeEnum.PILOT_REPORT if report_type == "PILOT" else reliability_models.ReliabilityEventTypeEnum.DEFECT
    if code == WorkbookDatasetCode.RM:
        return reliability_models.ReliabilityEventTypeEnum.SCHEDULED_REMOVAL if record.payload.get("removal_type") == "SCHEDULED" else reliability_models.ReliabilityEventTypeEnum.UNSCHEDULED_REMOVAL
    return {WorkbookDatasetCode.AI: reliability_models.ReliabilityEventTypeEnum.SAFETY_EVENT, WorkbookDatasetCode.OOS: reliability_models.ReliabilityEventTypeEnum.OTHER, WorkbookDatasetCode.SM: reliability_models.ReliabilityEventTypeEnum.DEFECT, WorkbookDatasetCode.STRUCTURES: reliability_models.ReliabilityEventTypeEnum.DEFECT, WorkbookDatasetCode.RECURRING: reliability_models.ReliabilityEventTypeEnum.REPEAT_DEFECT, WorkbookDatasetCode.ECTM: reliability_models.ReliabilityEventTypeEnum.ECTM}.get(code)


def _approve_to_canonical(db: Session, record: ReliabilityWorkbookRecord, user_id: str | None) -> None:
    if record.dataset_code == WorkbookDatasetCode.AU.value:
        existing = db.query(reliability_models.AircraftUtilizationDaily).filter(reliability_models.AircraftUtilizationDaily.amo_id == record.amo_id, reliability_models.AircraftUtilizationDaily.aircraft_serial_number == record.aircraft_serial_number, reliability_models.AircraftUtilizationDaily.date == record.event_date).one_or_none()
        values = {"flight_hours": float(Decimal(record.payload["flight_hours"])), "cycles": float(Decimal(str(record.payload["flight_cycles"]))), "source": record.reference_code or record.payload.get("source_reference") or record.record_number}
        if existing:
            existing.flight_hours = values["flight_hours"]
            existing.cycles = values["cycles"]
            existing.source = values["source"]
        else:
            db.add(reliability_models.AircraftUtilizationDaily(amo_id=record.amo_id, aircraft_serial_number=record.aircraft_serial_number, date=record.event_date, **values))
        return

    event_type = _event_type_for(record)
    if event_type is None:
        return
    existing_event = db.query(reliability_models.ReliabilityEvent).filter(reliability_models.ReliabilityEvent.amo_id == record.amo_id, reliability_models.ReliabilityEvent.source_system == f"WORKBOOK-{record.dataset_code}", reliability_models.ReliabilityEvent.source_record_id == str(record.id)).one_or_none()
    severity_raw = str(record.payload.get("severity") or "MEDIUM")
    try:
        severity = reliability_models.ReliabilitySeverityEnum(severity_raw)
    except ValueError:
        severity = reliability_models.ReliabilitySeverityEnum.MEDIUM
    occurred = datetime.combine(record.event_date, time.min, tzinfo=UTC)
    if record.payload.get("occurred_at"):
        occurred = _parse_datetime(record.payload["occurred_at"], "Occurrence time")
    if record.payload.get("removed_at"):
        occurred = _parse_datetime(record.payload["removed_at"], "Removal time")
    description = record.description or record.payload.get("defect_description") or record.payload.get("finding_description") or record.payload.get("description") or record.title
    event = reliability_models.ReliabilityEvent(amo_id=record.amo_id, aircraft_serial_number=record.aircraft_serial_number, engine_position=record.payload.get("engine_position"), event_type=event_type, severity=severity, ata_chapter=record.ata_chapter, reference_code=record.reference_code or record.record_number, source_system=f"WORKBOOK-{record.dataset_code}", source_record_id=str(record.id), source_payload_hash=record.source_hash, occurred_at=occurred, description=description, repeat_key=record.payload.get("repeat_key"), part_number=record.payload.get("off_part_number") or record.payload.get("component_part_number") or record.payload.get("part_number"), component_serial_number=record.payload.get("off_serial_number") or record.payload.get("component_serial_number") or record.payload.get("serial_number"), created_by_user_id=user_id)
    db.add(event)
    db.flush()
    record.canonical_event_id = event.id
    if record.dataset_code == WorkbookDatasetCode.ECTM.value:
        metrics = {key: float(Decimal(str(value))) for key, value in record.payload.items() if key in {"pressure_altitude_ft", "oat_c", "isa_dev_c", "power_reference", "itt_c", "ng_pct", "nh_pct", "np_rpm", "torque", "fuel_flow", "oil_pressure", "oil_temperature", "vibration"} and value not in (None, "")}
        metrics.update({key: value for key, value in record.payload.items() if key in {"oil_analysis_status", "oil_analysis_reference", "borescope_status", "borescope_reference", "trend_status", "analyst_comments", "oem_recommendation", "review_date", "reviewed_by", "action_required"} and value not in (None, "")})
        db.add(reliability_models.EngineFlightSnapshot(amo_id=record.amo_id, aircraft_serial_number=record.aircraft_serial_number, engine_position=record.payload["engine_position"], engine_serial_number=record.payload.get("engine_serial_number"), flight_date=record.event_date, flight_leg=record.payload.get("flight_leg") or record.record_number, phase=record.payload.get("phase"), metrics=metrics, data_source="WORKBOOK-ECTM", source_record_id=str(record.id)))


def _seed_layouts(db: Session, amo_id: str, user_id: str | None) -> list[ReliabilityReportLayout]:
    existing = {(row.code, row.revision): row for row in db.query(ReliabilityReportLayout).filter(ReliabilityReportLayout.amo_id == amo_id).all()}
    output = []
    for definition in DEFAULT_LAYOUTS:
        row = existing.get((definition["code"], 1))
        if not row:
            row = ReliabilityReportLayout(amo_id=amo_id, code=definition["code"], name=definition["name"], aircraft_family=definition["aircraft_family"], revision=1, active=True, sections=definition["sections"], page_settings={"size": "A4", "orientation": "portrait", "margin_mm": 10}, created_by_user_id=user_id)
            db.add(row)
        output.append(row)
    db.flush()
    return output


def _serialise_record(record: ReliabilityWorkbookRecord) -> dict[str, Any]:
    return WorkbookRecordRead.model_validate(record).model_dump(mode="json")


def _render_report(db: Session, amo_id: str, layout: ReliabilityReportLayout, request: ReportRenderRequest) -> tuple[dict[str, Any], str]:
    sections: list[dict[str, Any]] = []
    aircraft_filter = set(request.aircraft)
    for definition in layout.sections:
        kind = str(definition.get("kind") or "DATASET")
        title = str(definition.get("title") or definition.get("code") or "Section")
        section: dict[str, Any] = {"code": definition.get("code"), "title": title, "kind": kind}
        if kind == "DATASET":
            query = db.query(ReliabilityWorkbookRecord).filter(ReliabilityWorkbookRecord.amo_id == amo_id, ReliabilityWorkbookRecord.dataset_code == definition.get("dataset_code"), ReliabilityWorkbookRecord.status.in_([WorkbookRecordStatus.APPROVED.value, WorkbookRecordStatus.CLOSED.value]), ReliabilityWorkbookRecord.event_date >= request.period_start, ReliabilityWorkbookRecord.event_date <= request.period_end)
            if aircraft_filter:
                query = query.filter(ReliabilityWorkbookRecord.aircraft_serial_number.in_(sorted(aircraft_filter)))
            rows = query.order_by(ReliabilityWorkbookRecord.event_date.asc()).limit(MAX_EXPORT_ROWS).all()
            section["records"] = [_serialise_record(row) for row in rows]
            section["count"] = len(rows)
        elif kind == "EVENTS":
            query = db.query(reliability_models.ReliabilityEvent).filter(reliability_models.ReliabilityEvent.amo_id == amo_id, reliability_models.ReliabilityEvent.occurred_at >= datetime.combine(request.period_start, time.min, tzinfo=UTC), reliability_models.ReliabilityEvent.occurred_at <= datetime.combine(request.period_end, time.max, tzinfo=UTC))
            if aircraft_filter:
                query = query.filter(reliability_models.ReliabilityEvent.aircraft_serial_number.in_(sorted(aircraft_filter)))
            rows = query.order_by(reliability_models.ReliabilityEvent.occurred_at.asc()).limit(MAX_EXPORT_ROWS).all()
            section["records"] = [{"id": row.id, "date": row.occurred_at.isoformat(), "aircraft": row.aircraft_serial_number, "event_type": str(getattr(row.event_type, "value", row.event_type)), "ata": row.ata_chapter, "description": row.description} for row in rows]
            section["count"] = len(rows)
        elif kind == "STATISTICAL_ALERTS":
            rows = db.query(ReliabilityStatisticalAlertResult).filter(ReliabilityStatisticalAlertResult.amo_id == amo_id, ReliabilityStatisticalAlertResult.period_start <= request.period_end, ReliabilityStatisticalAlertResult.period_end >= request.period_start).order_by(ReliabilityStatisticalAlertResult.metric_code.asc()).all()
            section["records"] = [{"metric_code": row.metric_code, "metric_label": row.metric_label, "mean": float(row.mean_value), "stddev": float(row.sample_stddev), "warning_level": float(row.warning_level), "alert_level": float(row.alert_level), "formula": row.formula, "series": row.series} for row in rows]
            section["count"] = len(rows)
        else:
            section["summary"] = {"period_start": request.period_start.isoformat(), "period_end": request.period_end.isoformat(), "aircraft": sorted(aircraft_filter), "generated_at": _now().isoformat()}
        sections.append(section)
    data = {"layout": {"code": layout.code, "name": layout.name, "revision": layout.revision, "aircraft_family": layout.aircraft_family}, "period_start": request.period_start.isoformat(), "period_end": request.period_end.isoformat(), "aircraft": sorted(aircraft_filter), "sections": sections}
    css = "body{font-family:Arial,sans-serif;margin:10mm;color:#17202a}h1{font-size:20px}h2{font-size:15px;border-bottom:1px solid #777;padding-bottom:3px}table{width:100%;border-collapse:collapse;font-size:9px;margin-bottom:14px}th,td{border:1px solid #bbb;padding:4px;vertical-align:top}th{background:#eef2f5}@media print{button{display:none}}"
    body = [f"<h1>{html.escape(layout.name)}</h1><p>Period: {request.period_start.isoformat()} to {request.period_end.isoformat()} | Layout revision {layout.revision}</p>"]
    for section in sections:
        body.append(f"<h2>{html.escape(section['title'])}</h2>")
        if "summary" in section:
            body.append(f"<pre>{html.escape(json.dumps(section['summary'], indent=2))}</pre>")
            continue
        records = section.get("records", [])
        if not records:
            body.append("<p>No approved records for this section.</p>")
            continue
        keys = list(records[0].keys())
        body.append("<table><thead><tr>" + "".join(f"<th>{html.escape(str(key).replace('_',' ').title())}</th>" for key in keys) + "</tr></thead><tbody>")
        for row in records:
            body.append("<tr>" + "".join(f"<td>{html.escape(json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else str(row.get(key) or ''))}</td>" for key in keys) + "</tr>")
        body.append("</tbody></table>")
    rendered = f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(layout.name)}</title><style>{css}</style></head><body><button onclick='window.print()'>Print / save PDF</button>{''.join(body)}</body></html>"
    return data, rendered


def register(router: APIRouter) -> None:
    @router.get("/workbook-parity/catalog", response_model=list[DatasetDefinition])
    def catalog(current_user: account_models.User = Depends(get_current_active_user)):
        _amo_id(current_user)
        return list(DATASET_CATALOG.values())

    @router.get("/workbook-parity/records", response_model=list[WorkbookRecordRead])
    def list_records(dataset_code: WorkbookDatasetCode | None = None, aircraft_serial_number: str | None = None, status_filter: str | None = Query(default=None, alias="status"), period_start: date | None = None, period_end: date | None = None, q: str | None = None, limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE), offset: int = Query(default=0, ge=0), current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        query = db.query(ReliabilityWorkbookRecord).filter(ReliabilityWorkbookRecord.amo_id == _amo_id(current_user))
        if dataset_code: query = query.filter(ReliabilityWorkbookRecord.dataset_code == dataset_code.value)
        if aircraft_serial_number: query = query.filter(ReliabilityWorkbookRecord.aircraft_serial_number == aircraft_serial_number)
        if status_filter: query = query.filter(ReliabilityWorkbookRecord.status == status_filter.upper())
        if period_start: query = query.filter(ReliabilityWorkbookRecord.event_date >= period_start)
        if period_end: query = query.filter(ReliabilityWorkbookRecord.event_date <= period_end)
        if q:
            pattern = f"%{q.strip()}%"
            query = query.filter((ReliabilityWorkbookRecord.record_number.ilike(pattern)) | (ReliabilityWorkbookRecord.title.ilike(pattern)) | (ReliabilityWorkbookRecord.description.ilike(pattern)) | (ReliabilityWorkbookRecord.reference_code.ilike(pattern)))
        return query.order_by(ReliabilityWorkbookRecord.event_date.desc(), ReliabilityWorkbookRecord.id.desc()).offset(offset).limit(limit).all()

    @router.post("/workbook-parity/records", response_model=WorkbookRecordRead, status_code=201)
    def create_record(payload: WorkbookRecordCreate, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user)
        _validate_aircraft(db, amo_id, payload.aircraft_serial_number)
        if payload.dataset_code != WorkbookDatasetCode.AI and not payload.aircraft_serial_number:
            raise HTTPException(status_code=422, detail="Aircraft is required for this workbook dataset.")
        definition = DATASET_CATALOG[payload.dataset_code]
        normalised, derived = _normalise_payload(definition, payload.payload)
        serialised = {"dataset_code": payload.dataset_code.value, "event_date": payload.event_date.isoformat(), "aircraft": payload.aircraft_serial_number, "payload": normalised}
        record = ReliabilityWorkbookRecord(amo_id=amo_id, dataset_code=payload.dataset_code.value, record_number=_record_number(db, amo_id, payload.dataset_code.value, payload.event_date), revision=1, status=WorkbookRecordStatus.DRAFT.value, event_date=payload.event_date, event_end_date=payload.event_end_date, aircraft_serial_number=payload.aircraft_serial_number, ata_chapter=payload.ata_chapter, reference_code=payload.reference_code, title=payload.title, description=payload.description, payload=normalised, derived_values=derived, source_workbook=payload.source_workbook, source_sheet=payload.source_sheet, source_row_number=payload.source_row_number, source_hash=hashlib.sha256(json.dumps(serialised, sort_keys=True).encode()).hexdigest(), created_by_user_id=current_user.id)
        db.add(record); db.commit(); db.refresh(record); return record

    @router.post("/workbook-parity/records/{record_id}/approve", response_model=WorkbookRecordRead)
    def approve_record(record_id: int, action: RecordAction, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        record = db.query(ReliabilityWorkbookRecord).filter(ReliabilityWorkbookRecord.id == record_id, ReliabilityWorkbookRecord.amo_id == _amo_id(current_user)).one_or_none()
        if not record: raise HTTPException(status_code=404, detail="Workbook record not found.")
        if record.status != WorkbookRecordStatus.DRAFT.value: raise HTTPException(status_code=409, detail="Only draft records can be approved.")
        record.derived_values = {**(record.derived_values or {}), "approval_note": action.note}; record.status = WorkbookRecordStatus.APPROVED.value; record.approved_at = _now(); record.approved_by_user_id = current_user.id
        _approve_to_canonical(db, record, current_user.id); db.commit(); db.refresh(record); return record

    @router.post("/workbook-parity/records/{record_id}/close", response_model=WorkbookRecordRead)
    def close_record(record_id: int, action: RecordAction, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        record = db.query(ReliabilityWorkbookRecord).filter(ReliabilityWorkbookRecord.id == record_id, ReliabilityWorkbookRecord.amo_id == _amo_id(current_user)).one_or_none()
        if not record: raise HTTPException(status_code=404, detail="Workbook record not found.")
        if record.status != WorkbookRecordStatus.APPROVED.value: raise HTTPException(status_code=409, detail="Only approved records can be closed.")
        record.status = WorkbookRecordStatus.CLOSED.value; record.closed_at = _now(); record.closed_by_user_id = current_user.id; record.derived_values = {**(record.derived_values or {}), "closure_note": action.note}
        db.commit(); db.refresh(record); return record

    @router.get("/workbook-parity/oos-metrics")
    def oos_metrics(period_start: date, period_end: date, aircraft_serial_number: str | None = None, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        query = db.query(ReliabilityWorkbookRecord).filter(ReliabilityWorkbookRecord.amo_id == _amo_id(current_user), ReliabilityWorkbookRecord.dataset_code == WorkbookDatasetCode.OOS.value, ReliabilityWorkbookRecord.status.in_([WorkbookRecordStatus.APPROVED.value, WorkbookRecordStatus.CLOSED.value]), ReliabilityWorkbookRecord.event_date >= period_start, ReliabilityWorkbookRecord.event_date <= period_end)
        if aircraft_serial_number: query = query.filter(ReliabilityWorkbookRecord.aircraft_serial_number == aircraft_serial_number)
        rows = query.all(); downtime = sum((Decimal(str(row.derived_values.get("downtime_hours") or 0)) for row in rows), Decimal("0")); scheduled = sum((Decimal(str(row.payload.get("scheduled_available_hours") or 0)) for row in rows), Decimal("0")); completed = [Decimal(str(row.derived_values.get("downtime_hours"))) for row in rows if row.derived_values.get("downtime_hours") not in (None, "")]; available = max(scheduled - downtime, Decimal("0"))
        return {"records": len(rows), "downtime_hours": float(downtime), "scheduled_available_hours": float(scheduled), "available_hours": float(available), "availability_pct": float(available / scheduled * Decimal("100")) if scheduled > 0 else None, "mttr_hours": float(sum(completed, Decimal("0")) / Decimal(len(completed))) if completed else None}

    @router.get("/workbook-parity/statistical-alerts")
    def list_statistical_alerts(limit: int = Query(default=100, ge=1, le=250), current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        rows = db.query(ReliabilityStatisticalAlertResult).filter(ReliabilityStatisticalAlertResult.amo_id == _amo_id(current_user)).order_by(ReliabilityStatisticalAlertResult.generated_at.desc()).limit(limit).all()
        return [{"id": row.id, "metric_code": row.metric_code, "metric_label": row.metric_label, "source_kind": row.source_kind, "dataset_code": row.dataset_code, "scope_type": row.scope_type, "scope_value": row.scope_value, "period_start": row.period_start, "period_end": row.period_end, "bucket": row.bucket, "sample_size": row.sample_size, "mean": float(row.mean_value), "sample_stddev": float(row.sample_stddev), "warning_level": float(row.warning_level), "alert_level": float(row.alert_level), "formula": row.formula, "series": row.series, "generated_at": row.generated_at} for row in rows]

    @router.post("/workbook-parity/mappings", status_code=201)
    def create_mapping(payload: MappingCreate, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        definition = DATASET_CATALOG[payload.dataset_code]; valid_fields = {field.key for field in definition.fields} | {"event_date", "event_end_date", "aircraft_serial_number", "ata_chapter", "reference_code", "title", "description"}
        if payload.canonical_field not in valid_fields: raise HTTPException(status_code=422, detail="Canonical field is not defined for the selected dataset.")
        row = ReliabilityWorkbookFieldMapping(amo_id=_amo_id(current_user), created_by_user_id=current_user.id, **payload.model_dump(mode="json")); db.add(row); db.commit(); db.refresh(row); return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    @router.get("/workbook-parity/mappings")
    def list_mappings(profile_code: str | None = None, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        query = db.query(ReliabilityWorkbookFieldMapping).filter(ReliabilityWorkbookFieldMapping.amo_id == _amo_id(current_user), ReliabilityWorkbookFieldMapping.active.is_(True))
        if profile_code: query = query.filter(ReliabilityWorkbookFieldMapping.profile_code == profile_code)
        rows = query.order_by(ReliabilityWorkbookFieldMapping.workbook_family, ReliabilityWorkbookFieldMapping.dataset_code, ReliabilityWorkbookFieldMapping.source_sheet, ReliabilityWorkbookFieldMapping.id).all(); return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows]

    @router.get("/workbook-parity/parity")
    def parity(current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user); mappings = db.query(ReliabilityWorkbookFieldMapping).filter(ReliabilityWorkbookFieldMapping.amo_id == amo_id, ReliabilityWorkbookFieldMapping.active.is_(True)).all(); mapped = defaultdict(set)
        for row in mappings: mapped[row.dataset_code].add(row.canonical_field)
        result = []
        for code, definition in DATASET_CATALOG.items():
            required = {field.key for field in definition.fields if field.required}; optional = {field.key for field in definition.fields if not field.required}
            result.append({"dataset_code": code.value, "dataset_name": definition.name, "required_fields": sorted(required), "optional_fields": sorted(optional), "mapped_required_fields": sorted(required & mapped[code.value]), "missing_required_fields": sorted(required - mapped[code.value]), "coverage_pct": round((len(mapped[code.value] & (required | optional)) / max(len(required | optional), 1)) * 100, 1), "record_count": db.query(func.count(ReliabilityWorkbookRecord.id)).filter(ReliabilityWorkbookRecord.amo_id == amo_id, ReliabilityWorkbookRecord.dataset_code == code.value).scalar() or 0})
        return result

    @router.post("/workbook-parity/report-layouts/seed")
    def seed_report_layouts(current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        rows = _seed_layouts(db, _amo_id(current_user), current_user.id); db.commit(); return [{"id": row.id, "code": row.code, "name": row.name, "aircraft_family": row.aircraft_family, "revision": row.revision, "active": row.active, "sections": row.sections, "page_settings": row.page_settings} for row in rows]

    @router.post("/workbook-parity/report-layouts", status_code=201)
    def create_report_layout(payload: ReportLayoutCreate, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user); latest = db.query(func.max(ReliabilityReportLayout.revision)).filter(ReliabilityReportLayout.amo_id == amo_id, ReliabilityReportLayout.code == payload.code).scalar() or 0; db.query(ReliabilityReportLayout).filter(ReliabilityReportLayout.amo_id == amo_id, ReliabilityReportLayout.code == payload.code, ReliabilityReportLayout.active.is_(True)).update({"active": False}, synchronize_session=False)
        row = ReliabilityReportLayout(amo_id=amo_id, revision=int(latest) + 1, active=True, created_by_user_id=current_user.id, **payload.model_dump(mode="json")); db.add(row); db.commit(); db.refresh(row); return {"id": row.id, "code": row.code, "name": row.name, "aircraft_family": row.aircraft_family, "revision": row.revision, "active": row.active, "sections": row.sections, "page_settings": row.page_settings}

    @router.get("/workbook-parity/report-layouts")
    def list_report_layouts(current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user)
        if not db.query(ReliabilityReportLayout.id).filter(ReliabilityReportLayout.amo_id == amo_id).first(): _seed_layouts(db, amo_id, current_user.id); db.commit()
        rows = db.query(ReliabilityReportLayout).filter(ReliabilityReportLayout.amo_id == amo_id).order_by(ReliabilityReportLayout.code, ReliabilityReportLayout.revision.desc()).all(); return [{"id": row.id, "code": row.code, "name": row.name, "aircraft_family": row.aircraft_family, "revision": row.revision, "active": row.active, "sections": row.sections, "page_settings": row.page_settings} for row in rows]

    @router.post("/workbook-parity/reports/render", status_code=201)
    def render_report(payload: ReportRenderRequest, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user); layout = db.query(ReliabilityReportLayout).filter(ReliabilityReportLayout.id == payload.layout_id, ReliabilityReportLayout.amo_id == amo_id).one_or_none()
        if not layout: raise HTTPException(status_code=404, detail="Reliability report layout not found.")
        data, rendered = _render_report(db, amo_id, layout, payload); checksum = hashlib.sha256(rendered.encode()).hexdigest(); snapshot = ReliabilityWorkbookReportSnapshot(amo_id=amo_id, layout_id=layout.id, period_start=payload.period_start, period_end=payload.period_end, aircraft_filter=payload.aircraft, rendered_data=data, rendered_html=rendered, sha256_hash=checksum, generated_by_user_id=current_user.id); db.add(snapshot); db.commit(); db.refresh(snapshot)
        return {"id": snapshot.id, "layout_id": layout.id, "layout_code": layout.code, "period_start": payload.period_start, "period_end": payload.period_end, "sha256_hash": checksum, "generated_at": snapshot.generated_at, "download_url": f"/reliability/workbook-parity/reports/{snapshot.id}/html"}

    @router.get("/workbook-parity/reports")
    def list_reports(limit: int = Query(default=100, ge=1, le=250), current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        rows = db.query(ReliabilityWorkbookReportSnapshot, ReliabilityReportLayout).join(ReliabilityReportLayout, ReliabilityReportLayout.id == ReliabilityWorkbookReportSnapshot.layout_id).filter(ReliabilityWorkbookReportSnapshot.amo_id == _amo_id(current_user)).order_by(ReliabilityWorkbookReportSnapshot.generated_at.desc()).limit(limit).all(); return [{"id": snapshot.id, "layout_id": layout.id, "layout_code": layout.code, "layout_name": layout.name, "period_start": snapshot.period_start, "period_end": snapshot.period_end, "aircraft": snapshot.aircraft_filter, "sha256_hash": snapshot.sha256_hash, "generated_at": snapshot.generated_at, "download_url": f"/reliability/workbook-parity/reports/{snapshot.id}/html"} for snapshot, layout in rows]

    @router.get("/workbook-parity/reports/{report_id}/html", response_class=Response)
    def download_report(report_id: int, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        row = db.query(ReliabilityWorkbookReportSnapshot).filter(ReliabilityWorkbookReportSnapshot.id == report_id, ReliabilityWorkbookReportSnapshot.amo_id == _amo_id(current_user)).one_or_none()
        if not row: raise HTTPException(status_code=404, detail="Reliability report snapshot not found.")
        return Response(content=row.rendered_html, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="reliability-report-{report_id}.html"', "ETag": row.sha256_hash})
