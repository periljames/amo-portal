# backend/amodb/apps/reliability/services.py

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, Sequence

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


def create_reliability_event(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ReliabilityEventCreate,
    created_by_user_id: Optional[str] = None,
) -> models.ReliabilityEvent:
    event = models.ReliabilityEvent(
        amo_id=amo_id,
        created_by_user_id=created_by_user_id,
        **data.model_dump(),
    )
    if data.occurred_at is None:
        event.occurred_at = func.now()
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_reliability_events(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ReliabilityEvent]:
    return (
        db.query(models.ReliabilityEvent)
        .filter(models.ReliabilityEvent.amo_id == amo_id)
        .order_by(models.ReliabilityEvent.occurred_at.desc())
        .all()
    )


def create_kpi_snapshot(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ReliabilityKPICreate,
) -> models.ReliabilityKPI:
    kpi = models.ReliabilityKPI(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(kpi)
    db.commit()
    db.refresh(kpi)
    return kpi


def list_kpis(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ReliabilityKPI]:
    return (
        db.query(models.ReliabilityKPI)
        .filter(models.ReliabilityKPI.amo_id == amo_id)
        .order_by(models.ReliabilityKPI.window_end.desc())
        .all()
    )


def create_alert(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ReliabilityAlertCreate,
    created_by_user_id: Optional[str] = None,
) -> models.ReliabilityAlert:
    alert = models.ReliabilityAlert(
        amo_id=amo_id,
        created_by_user_id=created_by_user_id,
        **data.model_dump(),
    )
    if data.triggered_at is None:
        alert.triggered_at = func.now()
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def list_alerts(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ReliabilityAlert]:
    return (
        db.query(models.ReliabilityAlert)
        .filter(models.ReliabilityAlert.amo_id == amo_id)
        .order_by(models.ReliabilityAlert.triggered_at.desc())
        .all()
    )


def create_fracas_case(
    db: Session,
    *,
    amo_id: str,
    data: schemas.FRACASCaseCreate,
    created_by_user_id: Optional[str] = None,
) -> models.FRACASCase:
    case = models.FRACASCase(
        amo_id=amo_id,
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
        **data.model_dump(),
    )
    if data.opened_at is None:
        case.opened_at = func.now()
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_fracas_cases(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.FRACASCase]:
    return (
        db.query(models.FRACASCase)
        .filter(models.FRACASCase.amo_id == amo_id)
        .order_by(models.FRACASCase.opened_at.desc())
        .all()
    )


def create_fracas_action(
    db: Session,
    *,
    data: schemas.FRACASActionCreate,
) -> models.FRACASAction:
    action = models.FRACASAction(
        **data.model_dump(),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def list_fracas_actions(
    db: Session,
    *,
    fracas_case_id: int,
) -> Sequence[models.FRACASAction]:
    return (
        db.query(models.FRACASAction)
        .filter(models.FRACASAction.fracas_case_id == fracas_case_id)
        .order_by(models.FRACASAction.created_at.desc())
        .all()
    )


def create_engine_snapshot(
    db: Session,
    *,
    amo_id: str,
    data: schemas.EngineFlightSnapshotCreate,
) -> models.EngineFlightSnapshot:
    snapshot = models.EngineFlightSnapshot(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_engine_snapshots(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.EngineFlightSnapshot]:
    return (
        db.query(models.EngineFlightSnapshot)
        .filter(models.EngineFlightSnapshot.amo_id == amo_id)
        .order_by(models.EngineFlightSnapshot.flight_date.desc())
        .all()
    )


def create_oil_uplift(
    db: Session,
    *,
    amo_id: str,
    data: schemas.OilUpliftCreate,
) -> models.OilUplift:
    uplift = models.OilUplift(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(uplift)
    db.commit()
    db.refresh(uplift)
    return uplift


def list_oil_uplifts(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.OilUplift]:
    return (
        db.query(models.OilUplift)
        .filter(models.OilUplift.amo_id == amo_id)
        .order_by(models.OilUplift.uplift_date.desc())
        .all()
    )


def create_oil_consumption_rate(
    db: Session,
    *,
    amo_id: str,
    data: schemas.OilConsumptionRateCreate,
) -> models.OilConsumptionRate:
    rate = models.OilConsumptionRate(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(rate)
    db.commit()
    db.refresh(rate)
    return rate


def list_oil_consumption_rates(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.OilConsumptionRate]:
    return (
        db.query(models.OilConsumptionRate)
        .filter(models.OilConsumptionRate.amo_id == amo_id)
        .order_by(models.OilConsumptionRate.window_end.desc())
        .all()
    )


def create_component_instance(
    db: Session,
    *,
    data: schemas.ComponentInstanceCreate,
) -> models.ComponentInstance:
    instance = models.ComponentInstance(
        **data.model_dump(),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def list_component_instances(
    db: Session,
) -> Sequence[models.ComponentInstance]:
    return db.query(models.ComponentInstance).order_by(models.ComponentInstance.part_number.asc()).all()


def create_part_movement(
    db: Session,
    *,
    amo_id: str,
    data: schemas.PartMovementLedgerCreate,
) -> models.PartMovementLedger:
    movement = models.PartMovementLedger(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def list_part_movements(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.PartMovementLedger]:
    return (
        db.query(models.PartMovementLedger)
        .filter(models.PartMovementLedger.amo_id == amo_id)
        .order_by(models.PartMovementLedger.event_date.desc())
        .all()
    )


def create_removal_event(
    db: Session,
    *,
    amo_id: str,
    data: schemas.RemovalEventCreate,
) -> models.RemovalEvent:
    removal = models.RemovalEvent(
        amo_id=amo_id,
        **data.model_dump(),
    )
    if data.removed_at is None:
        removal.removed_at = func.now()
    db.add(removal)
    db.commit()
    db.refresh(removal)
    return removal


def list_removal_events(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.RemovalEvent]:
    return (
        db.query(models.RemovalEvent)
        .filter(models.RemovalEvent.amo_id == amo_id)
        .order_by(models.RemovalEvent.removed_at.desc())
        .all()
    )


def create_aircraft_utilization(
    db: Session,
    *,
    amo_id: str,
    data: schemas.AircraftUtilizationDailyCreate,
) -> models.AircraftUtilizationDaily:
    usage = models.AircraftUtilizationDaily(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def list_aircraft_utilization(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.AircraftUtilizationDaily]:
    return (
        db.query(models.AircraftUtilizationDaily)
        .filter(models.AircraftUtilizationDaily.amo_id == amo_id)
        .order_by(models.AircraftUtilizationDaily.date.desc())
        .all()
    )


def create_engine_utilization(
    db: Session,
    *,
    amo_id: str,
    data: schemas.EngineUtilizationDailyCreate,
) -> models.EngineUtilizationDaily:
    usage = models.EngineUtilizationDaily(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def list_engine_utilization(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.EngineUtilizationDaily]:
    return (
        db.query(models.EngineUtilizationDaily)
        .filter(models.EngineUtilizationDaily.amo_id == amo_id)
        .order_by(models.EngineUtilizationDaily.date.desc())
        .all()
    )


def create_threshold_set(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ThresholdSetCreate,
) -> models.ThresholdSet:
    threshold = models.ThresholdSet(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(threshold)
    db.commit()
    db.refresh(threshold)
    return threshold


def list_threshold_sets(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ThresholdSet]:
    return (
        db.query(models.ThresholdSet)
        .filter(models.ThresholdSet.amo_id == amo_id)
        .order_by(models.ThresholdSet.name.asc())
        .all()
    )


def create_alert_rule(
    db: Session,
    *,
    data: schemas.AlertRuleCreate,
) -> models.AlertRule:
    rule = models.AlertRule(
        **data.model_dump(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def list_alert_rules(
    db: Session,
    *,
    threshold_set_id: int,
) -> Sequence[models.AlertRule]:
    return (
        db.query(models.AlertRule)
        .filter(models.AlertRule.threshold_set_id == threshold_set_id)
        .order_by(models.AlertRule.kpi_code.asc())
        .all()
    )


def create_control_chart_config(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ControlChartConfigCreate,
) -> models.ControlChartConfig:
    config = models.ControlChartConfig(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def list_control_chart_configs(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ControlChartConfig]:
    return (
        db.query(models.ControlChartConfig)
        .filter(models.ControlChartConfig.amo_id == amo_id)
        .order_by(models.ControlChartConfig.kpi_code.asc())
        .all()
    )
