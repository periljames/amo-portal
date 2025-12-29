# backend/amodb/apps/reliability/schemas.py

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from .models import RecommendationPriorityEnum, RecommendationStatusEnum


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
