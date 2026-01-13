# backend/amodb/apps/reliability/schemas.py

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from .models import (
    AlertComparatorEnum,
    ControlChartMethodEnum,
    FRACASActionStatusEnum,
    FRACASActionTypeEnum,
    FRACASStatusEnum,
    KPIBaseScopeEnum,
    PartMovementTypeEnum,
    RecommendationPriorityEnum,
    RecommendationStatusEnum,
    ReliabilityAlertStatusEnum,
    ReliabilityEventTypeEnum,
    ReliabilityReportStatusEnum,
    ReliabilitySeverityEnum,
)
from ..accounts.models import AccountRole


class ReliabilityProgramTemplateCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    focus_areas: Optional[str] = None
    is_default: bool = False


class ReliabilityProgramTemplateRead(ReliabilityProgramTemplateCreate):
    id: int
    amo_id: str

    class Config:
        from_attributes = True


class DefectTrendCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    ata_chapter: Optional[str] = None
    window_start: date
    window_end: date
    defects_count: int = 0
    repeat_defects: int = 0
    finding_events: int = 0
    utilisation_hours: float = 0.0
    utilisation_cycles: float = 0.0
    notes: Optional[str] = None


class DefectTrendRead(DefectTrendCreate):
    id: int
    amo_id: str
    defect_rate_per_100_fh: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecurringFindingCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    ata_chapter: Optional[str] = None
    program_item_id: Optional[int] = None
    task_card_id: Optional[int] = None
    quality_finding_id: Optional[str] = None
    occurrence_count: int = 1
    recommendation: Optional[str] = None


class RecurringFindingRead(RecurringFindingCreate):
    id: int
    amo_id: str
    last_seen_at: datetime

    class Config:
        from_attributes = True


class ReliabilityRecommendationCreate(BaseModel):
    title: str
    summary: Optional[str] = None
    priority: RecommendationPriorityEnum = RecommendationPriorityEnum.MEDIUM
    status: RecommendationStatusEnum = RecommendationStatusEnum.OPEN
    trend_id: Optional[int] = None
    recurring_finding_id: Optional[int] = None


class ReliabilityRecommendationRead(ReliabilityRecommendationCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReliabilityEventCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    engine_position: Optional[str] = None
    component_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: ReliabilityEventTypeEnum
    severity: Optional[ReliabilitySeverityEnum] = None
    ata_chapter: Optional[str] = None
    reference_code: Optional[str] = None
    source_system: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[datetime] = None


class ReliabilityEventRead(ReliabilityEventCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReliabilityKPICreate(BaseModel):
    kpi_code: str
    scope_type: KPIBaseScopeEnum = KPIBaseScopeEnum.FLEET
    aircraft_serial_number: Optional[str] = None
    engine_position: Optional[str] = None
    component_id: Optional[int] = None
    ata_chapter: Optional[str] = None
    window_start: date
    window_end: date
    value: float
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    unit: Optional[str] = None
    calculation_version: Optional[str] = None


class ReliabilityKPIRead(ReliabilityKPICreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReliabilityAlertCreate(BaseModel):
    kpi_id: Optional[int] = None
    threshold_set_id: Optional[int] = None
    alert_code: str
    status: ReliabilityAlertStatusEnum = ReliabilityAlertStatusEnum.OPEN
    severity: ReliabilitySeverityEnum = ReliabilitySeverityEnum.MEDIUM
    message: Optional[str] = None
    triggered_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class ReliabilityAlertRead(ReliabilityAlertCreate):
    id: int
    amo_id: str
    created_at: datetime
    created_by_user_id: Optional[str] = None
    resolved_by_user_id: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class ReliabilityAlertAcknowledge(BaseModel):
    message: Optional[str] = None


class ReliabilityAlertResolve(BaseModel):
    message: Optional[str] = None


class FRACASCaseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: FRACASStatusEnum = FRACASStatusEnum.OPEN
    severity: Optional[ReliabilitySeverityEnum] = None
    classification: Optional[str] = None
    aircraft_serial_number: Optional[str] = None
    engine_position: Optional[str] = None
    component_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    reliability_event_id: Optional[int] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    root_cause: Optional[str] = None
    corrective_action_summary: Optional[str] = None


class FRACASCaseRead(FRACASCaseCreate):
    id: int
    amo_id: str
    created_at: datetime
    updated_at: datetime
    verification_notes: Optional[str] = None
    verified_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    verified_by_user_id: Optional[str] = None
    approved_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class FRACASCaseApprove(BaseModel):
    approval_notes: Optional[str] = None


class FRACASCaseVerify(BaseModel):
    verification_notes: Optional[str] = None
    status: Optional[FRACASStatusEnum] = None


class FRACASActionCreate(BaseModel):
    fracas_case_id: int
    action_type: FRACASActionTypeEnum = FRACASActionTypeEnum.CORRECTIVE
    status: FRACASActionStatusEnum = FRACASActionStatusEnum.OPEN
    description: str
    owner_user_id: Optional[str] = None
    due_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    effectiveness_notes: Optional[str] = None


class FRACASActionRead(FRACASActionCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None
    verified_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class FRACASActionVerify(BaseModel):
    effectiveness_notes: Optional[str] = None


class ReliabilityAlertEvaluationRequest(BaseModel):
    kpi_id: int
    threshold_set_id: Optional[int] = None


class ReliabilityAlertEvaluationResult(BaseModel):
    created_alerts: list[ReliabilityAlertRead]
    evaluated_rules: int


class ReliabilityNotificationRuleCreate(BaseModel):
    department_id: Optional[str] = None
    role: Optional[AccountRole] = None
    severity: ReliabilitySeverityEnum = ReliabilitySeverityEnum.MEDIUM
    is_active: bool = True


class ReliabilityNotificationRuleRead(ReliabilityNotificationRuleCreate):
    id: int
    amo_id: str
    created_at: datetime
    created_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class ReliabilityNotificationRead(BaseModel):
    id: int
    amo_id: str
    user_id: str
    department_id: Optional[str] = None
    alert_id: Optional[int] = None
    title: str
    message: Optional[str] = None
    severity: ReliabilitySeverityEnum
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReliabilityNotificationMarkRead(BaseModel):
    read: bool = True


class ReliabilityReportCreate(BaseModel):
    window_start: date
    window_end: date


class ReliabilityReportRead(BaseModel):
    id: int
    amo_id: str
    window_start: date
    window_end: date
    status: ReliabilityReportStatusEnum
    file_ref: Optional[str] = None
    created_at: datetime
    created_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class EngineFlightSnapshotCreate(BaseModel):
    aircraft_serial_number: str
    engine_position: str
    flight_date: date
    flight_leg: Optional[str] = None
    flight_hours: Optional[float] = None
    cycles: Optional[float] = None
    metrics: Optional[dict] = None
    data_source: Optional[str] = None


class EngineFlightSnapshotRead(EngineFlightSnapshotCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReliabilityEventIngestCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    engine_position: Optional[str] = None
    component_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: ReliabilityEventTypeEnum
    severity: Optional[ReliabilitySeverityEnum] = None
    ata_chapter: Optional[str] = None
    reference_code: str
    source_system: str
    description: Optional[str] = None
    occurred_at: datetime


class ReliabilityEventIngestBatch(BaseModel):
    events: list[ReliabilityEventIngestCreate]


class ReliabilityEventIngestBatchResult(BaseModel):
    created: list[ReliabilityEventRead]


class EngineFlightSnapshotIngestCreate(BaseModel):
    aircraft_serial_number: str
    engine_position: str
    flight_date: date
    flight_leg: Optional[str] = None
    flight_hours: Optional[float] = None
    cycles: Optional[float] = None
    metrics: Optional[dict] = None
    data_source: str


class EngineFlightSnapshotIngestBatch(BaseModel):
    snapshots: list[EngineFlightSnapshotIngestCreate]


class EngineFlightSnapshotIngestBatchResult(BaseModel):
    created: list[EngineFlightSnapshotRead]


class OilUpliftCreate(BaseModel):
    aircraft_serial_number: str
    engine_position: Optional[str] = None
    uplift_date: date
    quantity_quarts: float
    source: Optional[str] = None
    notes: Optional[str] = None


class OilUpliftRead(OilUpliftCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class OilConsumptionRateCreate(BaseModel):
    aircraft_serial_number: str
    engine_position: Optional[str] = None
    window_start: date
    window_end: date
    oil_used_quarts: float
    flight_hours: Optional[float] = None
    rate_qt_per_hour: Optional[float] = None


class OilConsumptionRateRead(OilConsumptionRateCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ComponentInstanceCreate(BaseModel):
    part_number: str
    serial_number: str
    description: Optional[str] = None
    component_class: Optional[str] = None
    ata: Optional[str] = None
    manufacturer_code: Optional[str] = None
    operator_code: Optional[str] = None


class ComponentInstanceRead(ComponentInstanceCreate):
    id: int
    amo_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PartMovementLedgerCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    component_id: Optional[int] = None
    component_instance_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: PartMovementTypeEnum
    event_date: date
    notes: Optional[str] = None


class PartMovementLedgerRead(PartMovementLedgerCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class RemovalEventCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    component_id: Optional[int] = None
    component_instance_id: Optional[int] = None
    part_movement_id: Optional[int] = None
    removal_reason: Optional[str] = None
    hours_at_removal: Optional[float] = None
    cycles_at_removal: Optional[float] = None
    removed_at: Optional[datetime] = None


class RemovalEventRead(RemovalEventCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class AircraftUtilizationDailyCreate(BaseModel):
    aircraft_serial_number: str
    date: date
    flight_hours: float = 0.0
    cycles: float = 0.0
    source: Optional[str] = None


class AircraftUtilizationDailyRead(AircraftUtilizationDailyCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class EngineUtilizationDailyCreate(BaseModel):
    aircraft_serial_number: str
    engine_position: str
    date: date
    flight_hours: float = 0.0
    cycles: float = 0.0
    source: Optional[str] = None


class EngineUtilizationDailyRead(EngineUtilizationDailyCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ThresholdSetCreate(BaseModel):
    name: str
    scope_type: KPIBaseScopeEnum
    scope_value: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class ThresholdSetRead(ThresholdSetCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class AlertRuleCreate(BaseModel):
    threshold_set_id: int
    kpi_code: str
    comparator: AlertComparatorEnum
    threshold_value: float
    severity: ReliabilitySeverityEnum = ReliabilitySeverityEnum.MEDIUM
    enabled: bool = True


class AlertRuleRead(AlertRuleCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ControlChartConfigCreate(BaseModel):
    kpi_code: str
    method: ControlChartMethodEnum
    parameters: Optional[dict] = None


class ControlChartConfigRead(ControlChartConfigCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True
