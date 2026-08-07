from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DashboardFilterOptions(BaseModel):
    aircraft: list[str] = Field(default_factory=list)
    aircraft_types: list[str] = Field(default_factory=list)
    ata_chapters: list[str] = Field(default_factory=list)
    stations: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    severities: list[str] = Field(default_factory=list)
    source_systems: list[str] = Field(default_factory=list)
    engine_positions: list[str] = Field(default_factory=list)
    engine_metrics: list[str] = Field(default_factory=list)


class CalculationFormula(BaseModel):
    code: str
    name: str
    version: str
    origin: Literal["SYSTEM", "PROGRAMME"] = "SYSTEM"
    latex: str
    mathml: str
    expression: dict[str, Any] = Field(default_factory=dict)
    unit: str
    precision: int = 3
    rounding_mode: str = "HALF_UP"
    numerator_label: str
    denominator_label: str | None = None
    multiplier: float | None = None
    methodology: str
    denominator_policy: str
    source_fields: list[str] = Field(default_factory=list)
    applied_to: list[str] = Field(default_factory=list)


class DashboardMetric(BaseModel):
    code: str
    label: str
    value: float | int | None = None
    unit: str = "count"
    delta_pct: float | None = None
    direction: Literal["UP", "DOWN", "FLAT", "UNKNOWN"] = "UNKNOWN"
    status: Literal["GOOD", "WATCH", "ALERT", "NEUTRAL", "NO_DATA"] = "NEUTRAL"
    denominator: float | int | None = None
    detail: str = ""
    formula_code: str | None = None
    drilldown: dict[str, Any] = Field(default_factory=dict)


class ChartPoint(BaseModel):
    key: str
    label: str
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    drilldown: dict[str, Any] = Field(default_factory=dict)


class EngineSeriesPoint(BaseModel):
    timestamp: str
    value: float
    aircraft_serial_number: str
    engine_position: str
    engine_serial_number: str | None = None


class EngineThreshold(BaseModel):
    label: str
    value: float
    comparator: str
    severity: str
    scope: str | None = None


class EngineMarker(BaseModel):
    timestamp: str
    label: str
    status: str
    aircraft_serial_number: str
    engine_position: str


class EngineSeriesResponse(BaseModel):
    generated_at: datetime
    period_start: date
    period_end: date
    metric: str
    unit: str | None = None
    series: dict[str, list[EngineSeriesPoint]] = Field(default_factory=dict)
    thresholds: list[EngineThreshold] = Field(default_factory=list)
    markers: list[EngineMarker] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    generated_at: datetime
    period_start: date
    period_end: date
    comparison_start: date
    comparison_end: date
    bucket: Literal["DAY", "WEEK", "MONTH"]
    filters: DashboardFilterOptions
    formulae: list[CalculationFormula] = Field(default_factory=list)
    summary: list[DashboardMetric]
    time_series: list[ChartPoint]
    event_mix: list[ChartPoint]
    ata_pareto: list[ChartPoint]
    aircraft_performance: list[ChartPoint]
    station_delay: list[ChartPoint]
    route_delay: list[ChartPoint]
    component_reliability: list[ChartPoint]
    component_removal_age: list[ChartPoint]
    shop_visit_trend: list[ChartPoint]
    oil_consumption: list[ChartPoint]
    deferral_status: list[ChartPoint]
    deferral_expiry: list[ChartPoint]
    deferral_categories: list[ChartPoint]
    deferral_extensions: list[ChartPoint]
    deferral_repeats: list[ChartPoint]
    deferral_closure: list[ChartPoint]
    fracas_stages: list[ChartPoint]
    fracas_ageing: list[ChartPoint]
    root_causes: list[ChartPoint]
    effectiveness: list[ChartPoint]
    fracas_actions: list[ChartPoint]
    fracas_action_trend: list[ChartPoint]
    fracas_reopened: list[ChartPoint]
    engine_status: list[ChartPoint]
    source_health: list[ChartPoint]
    data_quality: list[ChartPoint]
    warnings: list[str] = Field(default_factory=list)


class DrilldownRecord(BaseModel):
    id: str
    record_type: str
    occurred_at: datetime | date | None = None
    aircraft_serial_number: str | None = None
    reference: str | None = None
    category: str | None = None
    status: str | None = None
    severity: str | None = None
    ata_chapter: str | None = None
    summary: str = ""
    route: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DrilldownResponse(BaseModel):
    dimension: str
    key: str
    total: int
    limit: int
    offset: int
    records: list[DrilldownRecord]
