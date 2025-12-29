# backend/amodb/apps/reliability/services.py

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from ..work.models import TaskCategoryEnum, TaskCard, TaskOriginTypeEnum
from ..fleet.models import AircraftUsage
from ..quality.models import QMSAuditFinding


def seed_default_templates(db: Session, *, amo_id: str, created_by_user_id: Optional[str] = None) -> Iterable[models.ReliabilityProgramTemplate]:
    """
    Idempotently seed baseline reliability programme templates for an AMO.
    """

    existing = {
        tpl.code: tpl
        for tpl in db.query(models.ReliabilityProgramTemplate)
        .filter(models.ReliabilityProgramTemplate.amo_id == amo_id)
        .all()
    }

    seeds = [
        schemas.ReliabilityProgramTemplateCreate(
            code="GENERIC-RELIABILITY",
            name="Generic Reliability Program",
            description="Baseline reliability program template aligned with AMP and QMS findings.",
            focus_areas="defect trends, repeat defects, utilisation-normalised rates",
            is_default=True,
        ),
        schemas.ReliabilityProgramTemplateCreate(
            code="POWERPLANT-FOCUS",
            name="Powerplant Reliability Focus",
            description="Template focused on engine/APU recurring findings and TBO tracking.",
            focus_areas="engines, apu, HSI/TBO monitoring",
        ),
    ]

    created = []
    for seed in seeds:
        if seed.code in existing:
            continue
        tpl = models.ReliabilityProgramTemplate(
            amo_id=amo_id,
            created_by_user_id=created_by_user_id,
            **seed.model_dump(),
        )
        db.add(tpl)
        created.append(tpl)

    if created:
        db.commit()
        for tpl in created:
            db.refresh(tpl)
    return created


def _calc_defect_rate(defects_count: int, utilisation_hours: float) -> Optional[float]:
    if utilisation_hours <= 0:
        return None
    return round((defects_count / utilisation_hours) * 100, 3)


def compute_defect_trend(
    db: Session,
    *,
    amo_id: str,
    window_start: date,
    window_end: date,
    aircraft_serial_number: Optional[str] = None,
    ata_chapter: Optional[str] = None,
) -> models.ReliabilityDefectTrend:
    """
    Calculate and persist a defect trend snapshot for the window.
    """

    utilisation_q = db.query(
        func.coalesce(func.sum(AircraftUsage.block_hours), 0.0),
        func.coalesce(func.sum(AircraftUsage.cycles), 0.0),
    ).filter(
        AircraftUsage.date >= window_start,
        AircraftUsage.date <= window_end,
    )
    if aircraft_serial_number:
        utilisation_q = utilisation_q.filter(AircraftUsage.aircraft_serial_number == aircraft_serial_number)
    utilisation_hours, utilisation_cycles = utilisation_q.one()

    defects_q = db.query(func.count(TaskCard.id)).filter(
        TaskCard.category == TaskCategoryEnum.DEFECT,
        TaskCard.created_at >= window_start,
        TaskCard.created_at <= window_end,
    )
    repeat_q = db.query(func.count(TaskCard.id)).filter(
        TaskCard.category == TaskCategoryEnum.DEFECT,
        TaskCard.origin_type == TaskOriginTypeEnum.NON_ROUTINE,
        TaskCard.created_at >= window_start,
        TaskCard.created_at <= window_end,
    )
    findings_q = db.query(func.count(QMSAuditFinding.id)).filter(
        QMSAuditFinding.created_at >= window_start,
        QMSAuditFinding.created_at <= window_end,
    )

    if aircraft_serial_number:
        defects_q = defects_q.filter(TaskCard.aircraft_serial_number == aircraft_serial_number)
        repeat_q = repeat_q.filter(TaskCard.aircraft_serial_number == aircraft_serial_number)

    if ata_chapter:
        defects_q = defects_q.filter(TaskCard.ata_chapter == ata_chapter)
        repeat_q = repeat_q.filter(TaskCard.ata_chapter == ata_chapter)

    defects_count = defects_q.scalar() or 0
    repeat_defects = repeat_q.scalar() or 0
    finding_events = findings_q.scalar() or 0

    trend = models.ReliabilityDefectTrend(
        amo_id=amo_id,
        aircraft_serial_number=aircraft_serial_number,
        ata_chapter=ata_chapter,
        window_start=window_start,
        window_end=window_end,
        defects_count=defects_count,
        repeat_defects=repeat_defects,
        finding_events=finding_events,
        utilisation_hours=float(utilisation_hours or 0.0),
        utilisation_cycles=float(utilisation_cycles or 0.0),
    )
    trend.defect_rate_per_100_fh = _calc_defect_rate(trend.defects_count, trend.utilisation_hours)

    db.add(trend)
    db.commit()
    db.refresh(trend)
    return trend


def upsert_recurring_finding(
    db: Session,
    *,
    amo_id: str,
    data: schemas.RecurringFindingCreate,
) -> models.ReliabilityRecurringFinding:
    """
    Increment occurrence count for a recurring finding key.
    """

    query = db.query(models.ReliabilityRecurringFinding).filter(
        models.ReliabilityRecurringFinding.amo_id == amo_id,
    )
    if data.aircraft_serial_number:
        query = query.filter(models.ReliabilityRecurringFinding.aircraft_serial_number == data.aircraft_serial_number)
    if data.program_item_id:
        query = query.filter(models.ReliabilityRecurringFinding.program_item_id == data.program_item_id)
    if data.ata_chapter:
        query = query.filter(models.ReliabilityRecurringFinding.ata_chapter == data.ata_chapter)

    instance = query.first()
    if instance:
        instance.occurrence_count += max(1, data.occurrence_count)
        instance.last_seen_at = func.now()
        if data.recommendation:
            instance.recommendation = data.recommendation
    else:
        instance = models.ReliabilityRecurringFinding(
            amo_id=amo_id,
            **data.model_dump(),
        )
        db.add(instance)

    db.commit()
    db.refresh(instance)
    return instance


def create_recommendation(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ReliabilityRecommendationCreate,
    created_by_user_id: Optional[str] = None,
) -> models.ReliabilityRecommendation:
    rec = models.ReliabilityRecommendation(
        amo_id=amo_id,
        created_by_user_id=created_by_user_id,
        **data.model_dump(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
