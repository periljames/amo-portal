# backend/amodb/apps/reliability/services.py

from __future__ import annotations

import csv
import io
import importlib.util
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from ..work.models import TaskCategoryEnum, TaskCard
from ..fleet.models import AircraftUsage
from ..accounts import models as account_models
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

    start_dt = datetime.combine(window_start, time.min)
    end_dt_exclusive = datetime.combine(window_end + timedelta(days=1), time.min)

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
        TaskCard.created_at >= start_dt,
        TaskCard.created_at < end_dt_exclusive,
    )
    findings_q = db.query(func.count(QMSAuditFinding.id)).filter(
        QMSAuditFinding.created_at >= start_dt,
        QMSAuditFinding.created_at < end_dt_exclusive,
    )

    if aircraft_serial_number:
        defects_q = defects_q.filter(TaskCard.aircraft_serial_number == aircraft_serial_number)

    if ata_chapter:
        defects_q = defects_q.filter(TaskCard.ata_chapter == ata_chapter)

    defects_count = defects_q.scalar() or 0

    repeat_subq = db.query(
        TaskCard.aircraft_serial_number.label("aircraft_serial_number"),
        TaskCard.ata_chapter.label("ata_chapter"),
        TaskCard.task_code.label("task_code"),
        func.count(TaskCard.id).label("defect_count"),
    ).filter(
        TaskCard.category == TaskCategoryEnum.DEFECT,
        TaskCard.created_at >= start_dt,
        TaskCard.created_at < end_dt_exclusive,
    )
    if aircraft_serial_number:
        repeat_subq = repeat_subq.filter(TaskCard.aircraft_serial_number == aircraft_serial_number)
    if ata_chapter:
        repeat_subq = repeat_subq.filter(TaskCard.ata_chapter == ata_chapter)

    repeat_subq = repeat_subq.group_by(
        TaskCard.aircraft_serial_number,
        TaskCard.ata_chapter,
        TaskCard.task_code,
    ).subquery()
    repeat_defects = (
        db.query(func.coalesce(func.sum(repeat_subq.c.defect_count - 1), 0))
        .filter(repeat_subq.c.defect_count > 1)
        .scalar()
        or 0
    )
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


def create_reliability_events_bulk(
    db: Session,
    *,
    amo_id: str,
    created_by_user_id: str,
    events: Sequence[schemas.ReliabilityEventIngestCreate],
) -> Sequence[models.ReliabilityEvent]:
    created = []
    for event_data in events:
        event = models.ReliabilityEvent(
            amo_id=amo_id,
            created_by_user_id=created_by_user_id,
            **event_data.model_dump(),
        )
        created.append(event)
    db.add_all(created)
    db.commit()
    for event in created:
        db.refresh(event)
    return created


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


def export_reliability_events_csv(
    db: Session,
    *,
    amo_id: str,
) -> str:
    events = list_reliability_events(db, amo_id=amo_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "event_type",
            "severity",
            "occurred_at",
            "aircraft_serial_number",
            "engine_position",
            "component_id",
            "work_order_id",
            "task_card_id",
            "ata_chapter",
            "reference_code",
            "source_system",
            "description",
        ]
    )
    for event in events:
        writer.writerow(
            [
                event.id,
                event.event_type.value,
                event.severity.value if event.severity else None,
                event.occurred_at.isoformat() if event.occurred_at else None,
                event.aircraft_serial_number,
                event.engine_position,
                event.component_id,
                event.work_order_id,
                event.task_card_id,
                event.ata_chapter,
                event.reference_code,
                event.source_system,
                event.description,
            ]
        )
    return output.getvalue()


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
    dispatch_alert_notifications(
        db,
        amo_id=amo_id,
        alert=alert,
        created_by_user_id=created_by_user_id,
    )
    return alert


def acknowledge_alert(
    db: Session,
    *,
    amo_id: str,
    alert_id: int,
    message: Optional[str],
    acknowledged_by_user_id: str,
) -> models.ReliabilityAlert:
    alert = (
        db.query(models.ReliabilityAlert)
        .filter(models.ReliabilityAlert.amo_id == amo_id, models.ReliabilityAlert.id == alert_id)
        .first()
    )
    if not alert:
        raise ValueError("Alert not found.")
    if message:
        alert.message = message
    alert.status = models.ReliabilityAlertStatusEnum.ACKNOWLEDGED
    alert.acknowledged_at = func.now()
    alert.acknowledged_by_user_id = acknowledged_by_user_id
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(
    db: Session,
    *,
    amo_id: str,
    alert_id: int,
    message: Optional[str],
    resolved_by_user_id: str,
) -> models.ReliabilityAlert:
    alert = (
        db.query(models.ReliabilityAlert)
        .filter(models.ReliabilityAlert.amo_id == amo_id, models.ReliabilityAlert.id == alert_id)
        .first()
    )
    if not alert:
        raise ValueError("Alert not found.")
    if message:
        alert.message = message
    alert.status = models.ReliabilityAlertStatusEnum.CLOSED
    alert.resolved_at = func.now()
    alert.resolved_by_user_id = resolved_by_user_id
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


def approve_fracas_case(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    approved_by_user_id: str,
    approval_notes: Optional[str],
) -> models.FRACASCase:
    case = (
        db.query(models.FRACASCase)
        .filter(models.FRACASCase.amo_id == amo_id, models.FRACASCase.id == case_id)
        .first()
    )
    if not case:
        raise ValueError("FRACAS case not found.")
    case.approved_at = func.now()
    case.approved_by_user_id = approved_by_user_id
    if approval_notes:
        case.corrective_action_summary = approval_notes
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def verify_fracas_case(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    verified_by_user_id: str,
    verification_notes: Optional[str],
    status: Optional[models.FRACASStatusEnum],
) -> models.FRACASCase:
    case = (
        db.query(models.FRACASCase)
        .filter(models.FRACASCase.amo_id == amo_id, models.FRACASCase.id == case_id)
        .first()
    )
    if not case:
        raise ValueError("FRACAS case not found.")
    case.verified_at = func.now()
    case.verified_by_user_id = verified_by_user_id
    if verification_notes:
        case.verification_notes = verification_notes
    if status:
        case.status = status
        if status == models.FRACASStatusEnum.CLOSED:
            case.closed_at = func.now()
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
    amo_id: str,
    data: schemas.FRACASActionCreate,
) -> models.FRACASAction:
    case = (
        db.query(models.FRACASCase)
        .filter(models.FRACASCase.amo_id == amo_id, models.FRACASCase.id == data.fracas_case_id)
        .first()
    )
    if not case:
        raise ValueError("FRACAS case not found.")
    action = models.FRACASAction(
        **data.model_dump(),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def verify_fracas_action(
    db: Session,
    *,
    amo_id: str,
    action_id: int,
    verified_by_user_id: str,
    effectiveness_notes: Optional[str],
) -> models.FRACASAction:
    action = (
        db.query(models.FRACASAction)
        .join(models.FRACASCase, models.FRACASAction.fracas_case_id == models.FRACASCase.id)
        .filter(models.FRACASAction.id == action_id, models.FRACASCase.amo_id == amo_id)
        .first()
    )
    if not action:
        raise ValueError("FRACAS action not found.")
    action.verified_at = func.now()
    action.verified_by_user_id = verified_by_user_id
    if effectiveness_notes:
        action.effectiveness_notes = effectiveness_notes
    action.status = models.FRACASActionStatusEnum.VERIFIED
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def list_fracas_actions(
    db: Session,
    *,
    amo_id: str,
    fracas_case_id: int,
) -> Sequence[models.FRACASAction]:
    case = (
        db.query(models.FRACASCase)
        .filter(models.FRACASCase.amo_id == amo_id, models.FRACASCase.id == fracas_case_id)
        .first()
    )
    if not case:
        raise ValueError("FRACAS case not found.")
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
    if data.flight_hours is not None and data.flight_hours < 0:
        raise ValueError("flight_hours must be non-negative.")
    if data.cycles is not None and data.cycles < 0:
        raise ValueError("cycles must be non-negative.")
    snapshot = models.EngineFlightSnapshot(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def create_engine_snapshots_bulk(
    db: Session,
    *,
    amo_id: str,
    snapshots: Sequence[schemas.EngineFlightSnapshotIngestCreate],
) -> Sequence[models.EngineFlightSnapshot]:
    created = []
    for snapshot_data in snapshots:
        if snapshot_data.flight_hours is not None and snapshot_data.flight_hours < 0:
            raise ValueError("flight_hours must be non-negative.")
        if snapshot_data.cycles is not None and snapshot_data.cycles < 0:
            raise ValueError("cycles must be non-negative.")
        snapshot = models.EngineFlightSnapshot(
            amo_id=amo_id,
            **snapshot_data.model_dump(),
        )
        created.append(snapshot)
    db.add_all(created)
    db.commit()
    for snapshot in created:
        db.refresh(snapshot)
    return created


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


def _get_control_chart_config(
    db: Session,
    *,
    amo_id: str,
    kpi_code: str,
) -> Optional[models.ControlChartConfig]:
    return (
        db.query(models.ControlChartConfig)
        .filter(models.ControlChartConfig.amo_id == amo_id, models.ControlChartConfig.kpi_code == kpi_code)
        .first()
    )


def _average(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _calculate_baseline(values: Sequence[float], window: int) -> Optional[float]:
    window = max(window, 1)
    if not values:
        return None
    baseline_slice = values[:window]
    return _average(baseline_slice)


def _apply_correction(snapshot: models.EngineFlightSnapshot, metric: str, raw_value: Optional[float]) -> Optional[float]:
    if raw_value is None:
        return None
    if metric.endswith("_C") and snapshot.isa_dev_c is not None:
        return raw_value - snapshot.isa_dev_c
    return raw_value


def _classify_delta(delta: Optional[float], threshold: float) -> Optional[models.EngineTrendStatusEnum]:
    if delta is None:
        return None
    if abs(delta) > threshold:
        return models.EngineTrendStatusEnum.SHIFT
    return models.EngineTrendStatusEnum.NORMAL


def _calculate_ewma(values: Sequence[float], alpha: float) -> Optional[float]:
    if not values:
        return None
    alpha = max(min(alpha, 1.0), 0.0)
    ewma = values[0]
    for value in values[1:]:
        ewma = alpha * value + (1 - alpha) * ewma
    return ewma


def _calculate_cusum(values: Sequence[float], k: float) -> Optional[float]:
    if not values:
        return None
    pos = 0.0
    neg = 0.0
    for value in values:
        pos = max(0.0, pos + value - k)
        neg = min(0.0, neg + value + k)
    return pos if abs(pos) >= abs(neg) else neg


def _calculate_slope(values: Sequence[float], window: int) -> Optional[float]:
    if len(values) < 2:
        return None
    window = max(window, 2)
    window_values = values[-window:]
    n = len(window_values)
    x_vals = list(range(n))
    x_mean = sum(x_vals) / n
    y_mean = sum(window_values) / n
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, window_values))
    denominator = sum((x - x_mean) ** 2 for x in x_vals)
    if denominator == 0:
        return None
    return numerator / denominator


def _build_engine_trend_series(
    snapshots: Sequence[models.EngineFlightSnapshot],
    *,
    metric: str,
    baseline_window: int,
    shift_threshold: float,
    method: Optional[models.ControlChartMethodEnum],
    parameters: Optional[dict],
) -> schemas.EngineTrendSeriesRead:
    values: list[float] = []
    deltas: list[float] = []
    points: list[schemas.EngineTrendPoint] = []

    for snapshot in snapshots:
        raw_value = None
        if snapshot.metrics:
            raw_value = snapshot.metrics.get(metric)
        if isinstance(raw_value, (int, float)):
            corrected_value = _apply_correction(snapshot, metric, float(raw_value))
            if corrected_value is not None:
                values.append(corrected_value)
        else:
            corrected_value = None
        baseline = _calculate_baseline(values, baseline_window)
        delta = corrected_value - baseline if corrected_value is not None and baseline is not None else None
        if delta is not None:
            deltas.append(delta)

        status = _classify_delta(delta, shift_threshold)
        if method == models.ControlChartMethodEnum.EWMA and deltas:
            alpha = float(parameters.get("alpha", 0.2)) if parameters else 0.2
            ewma_value = _calculate_ewma(deltas, alpha)
            status = _classify_delta(ewma_value, shift_threshold)
        elif method == models.ControlChartMethodEnum.CUSUM and deltas:
            k = float(parameters.get("k", 0.5)) if parameters else 0.5
            cusum_value = _calculate_cusum(deltas, k)
            status = _classify_delta(cusum_value, shift_threshold)
        elif method == models.ControlChartMethodEnum.SLOPE and values:
            window = int(parameters.get("window", 5)) if parameters else 5
            slope_value = _calculate_slope(values, window)
            status = _classify_delta(slope_value, shift_threshold)

        points.append(
            schemas.EngineTrendPoint(
                date=snapshot.flight_date,
                raw=float(raw_value) if isinstance(raw_value, (int, float)) else None,
                corrected=corrected_value,
                delta=delta,
                status=status,
            )
        )

    baseline = _calculate_baseline(values, baseline_window)
    return schemas.EngineTrendSeriesRead(
        metric=metric,
        baseline=baseline,
        control_limit=shift_threshold,
        method=method,
        parameters=parameters,
        points=points,
    )


def compute_engine_trend_status(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: Optional[str] = None,
    engine_position: Optional[str] = None,
    engine_serial_number: Optional[str] = None,
) -> list[models.EngineTrendStatus]:
    query = db.query(models.EngineFlightSnapshot).filter(models.EngineFlightSnapshot.amo_id == amo_id)
    if aircraft_serial_number:
        query = query.filter(models.EngineFlightSnapshot.aircraft_serial_number == aircraft_serial_number)
    if engine_position:
        query = query.filter(models.EngineFlightSnapshot.engine_position == engine_position)
    if engine_serial_number:
        query = query.filter(models.EngineFlightSnapshot.engine_serial_number == engine_serial_number)

    snapshots = query.order_by(models.EngineFlightSnapshot.flight_date.asc()).all()
    if not snapshots:
        return []

    grouped: dict[tuple[str, str, Optional[str]], list[models.EngineFlightSnapshot]] = {}
    for snapshot in snapshots:
        key = (
            snapshot.aircraft_serial_number,
            snapshot.engine_position,
            snapshot.engine_serial_number,
        )
        grouped.setdefault(key, []).append(snapshot)

    statuses: list[models.EngineTrendStatus] = []
    required_metrics = schemas._required_engine_metric_keys()
    for (aircraft_sn, engine_pos, engine_sn), engine_snapshots in grouped.items():
        latest_snapshot = engine_snapshots[-1]
        has_metrics = latest_snapshot.metrics is not None
        current_status = models.EngineTrendStatusEnum.NORMAL

        if has_metrics:
            for metric in required_metrics:
                config = _get_control_chart_config(db, amo_id=amo_id, kpi_code=metric)
                method = config.method if config else models.ControlChartMethodEnum.SLOPE
                parameters = config.parameters if config else {}
                baseline_window = int(parameters.get("baseline_window", 10))
                shift_threshold = float(parameters.get("shift_threshold", 3.0))
                series = _build_engine_trend_series(
                    engine_snapshots,
                    metric=metric,
                    baseline_window=baseline_window,
                    shift_threshold=shift_threshold,
                    method=method,
                    parameters=parameters,
                )
                latest_point = series.points[-1] if series.points else None
                if latest_point and latest_point.status == models.EngineTrendStatusEnum.SHIFT:
                    current_status = models.EngineTrendStatusEnum.SHIFT
                    break
        else:
            current_status = models.EngineTrendStatusEnum.SHIFT

        status = (
            db.query(models.EngineTrendStatus)
            .filter(
                models.EngineTrendStatus.amo_id == amo_id,
                models.EngineTrendStatus.aircraft_serial_number == aircraft_sn,
                models.EngineTrendStatus.engine_position == engine_pos,
                models.EngineTrendStatus.engine_serial_number == engine_sn,
            )
            .first()
        )

        if status:
            if status.current_status != current_status:
                status.previous_status = status.current_status
                status.current_status = current_status
            status.last_upload_date = latest_snapshot.flight_date
            status.last_trend_date = latest_snapshot.flight_date
        else:
            status = models.EngineTrendStatus(
                amo_id=amo_id,
                aircraft_serial_number=aircraft_sn,
                engine_position=engine_pos,
                engine_serial_number=engine_sn,
                last_upload_date=latest_snapshot.flight_date,
                last_trend_date=latest_snapshot.flight_date,
                previous_status=None,
                current_status=current_status,
            )
        db.add(status)
        statuses.append(status)

    db.commit()
    for status in statuses:
        db.refresh(status)
    return statuses


def get_engine_trend_series(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    engine_position: str,
    metric: str,
    engine_serial_number: Optional[str] = None,
    baseline_window: int = 10,
    shift_threshold: float = 3.0,
) -> schemas.EngineTrendSeriesRead:
    query = db.query(models.EngineFlightSnapshot).filter(
        models.EngineFlightSnapshot.amo_id == amo_id,
        models.EngineFlightSnapshot.aircraft_serial_number == aircraft_serial_number,
        models.EngineFlightSnapshot.engine_position == engine_position,
    )
    if engine_serial_number:
        query = query.filter(models.EngineFlightSnapshot.engine_serial_number == engine_serial_number)

    snapshots = query.order_by(models.EngineFlightSnapshot.flight_date.asc()).all()
    if not snapshots:
        return schemas.EngineTrendSeriesRead(metric=metric, points=[])

    config = _get_control_chart_config(db, amo_id=amo_id, kpi_code=metric)
    if config and config.parameters:
        baseline_window = int(config.parameters.get("baseline_window", baseline_window))
        shift_threshold = float(config.parameters.get("shift_threshold", shift_threshold))
    method = config.method if config else models.ControlChartMethodEnum.SLOPE
    parameters = config.parameters if config else {}

    series = _build_engine_trend_series(
        snapshots,
        metric=metric,
        baseline_window=baseline_window,
        shift_threshold=shift_threshold,
        method=method,
        parameters=parameters,
    )
    event_query = db.query(models.ReliabilityEvent).filter(
        models.ReliabilityEvent.amo_id == amo_id,
        models.ReliabilityEvent.aircraft_serial_number == aircraft_serial_number,
    )
    if engine_position:
        event_query = event_query.filter(models.ReliabilityEvent.engine_position == engine_position)
    date_range = [snapshots[0].flight_date, snapshots[-1].flight_date]
    events = (
        event_query.filter(
            models.ReliabilityEvent.occurred_at >= datetime.combine(date_range[0], time.min),
            models.ReliabilityEvent.occurred_at <= datetime.combine(date_range[1], time.max),
        )
        .order_by(models.ReliabilityEvent.occurred_at.asc())
        .all()
    )
    event_payloads = [
        schemas.EngineTrendEvent(
            date=event.occurred_at.date(),
            event_type=event.event_type,
            reference_code=event.reference_code,
            severity=event.severity,
            description=event.description,
        )
        for event in events
    ]
    return schemas.EngineTrendSeriesRead(
        metric=series.metric,
        baseline=series.baseline,
        control_limit=series.control_limit,
        method=series.method,
        parameters=series.parameters,
        points=series.points,
        events=event_payloads,
    )


def list_engine_trend_statuses(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.EngineTrendStatus]:
    return (
        db.query(models.EngineTrendStatus)
        .filter(models.EngineTrendStatus.amo_id == amo_id)
        .order_by(models.EngineTrendStatus.aircraft_serial_number.asc())
        .all()
    )


def review_engine_trend_status(
    db: Session,
    *,
    amo_id: str,
    status_id: int,
    reviewed_by_user_id: str,
    last_review_date: date,
) -> models.EngineTrendStatus:
    status = (
        db.query(models.EngineTrendStatus)
        .filter(models.EngineTrendStatus.amo_id == amo_id, models.EngineTrendStatus.id == status_id)
        .first()
    )
    if not status:
        raise ValueError("Engine trend status not found.")
    status.last_review_date = last_review_date
    status.reviewed_by_user_id = reviewed_by_user_id
    db.add(status)
    db.commit()
    db.refresh(status)
    return status


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
    amo_id: str,
    data: schemas.ComponentInstanceCreate,
) -> models.ComponentInstance:
    instance = models.ComponentInstance(
        amo_id=amo_id,
        **data.model_dump(),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def list_component_instances(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ComponentInstance]:
    return (
        db.query(models.ComponentInstance)
        .filter(models.ComponentInstance.amo_id == amo_id)
        .order_by(models.ComponentInstance.part_number.asc())
        .all()
    )


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
    amo_id: str,
    data: schemas.AlertRuleCreate,
) -> models.AlertRule:
    threshold = (
        db.query(models.ThresholdSet)
        .filter(models.ThresholdSet.amo_id == amo_id, models.ThresholdSet.id == data.threshold_set_id)
        .first()
    )
    if not threshold:
        raise ValueError("Threshold set not found.")
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
    amo_id: str,
    threshold_set_id: int,
) -> Sequence[models.AlertRule]:
    threshold = (
        db.query(models.ThresholdSet)
        .filter(models.ThresholdSet.amo_id == amo_id, models.ThresholdSet.id == threshold_set_id)
        .first()
    )
    if not threshold:
        raise ValueError("Threshold set not found.")
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


def _scope_value_for_kpi(kpi: models.ReliabilityKPI) -> Optional[str]:
    if kpi.scope_type == models.KPIBaseScopeEnum.AIRCRAFT:
        return kpi.aircraft_serial_number
    if kpi.scope_type == models.KPIBaseScopeEnum.ENGINE:
        return kpi.engine_position
    if kpi.scope_type == models.KPIBaseScopeEnum.COMPONENT:
        return str(kpi.component_id) if kpi.component_id is not None else None
    if kpi.scope_type == models.KPIBaseScopeEnum.ATA:
        return kpi.ata_chapter
    return None


def _compare_value(value: float, comparator: models.AlertComparatorEnum, threshold: float) -> bool:
    if comparator == models.AlertComparatorEnum.GT:
        return value > threshold
    if comparator == models.AlertComparatorEnum.GTE:
        return value >= threshold
    if comparator == models.AlertComparatorEnum.LT:
        return value < threshold
    if comparator == models.AlertComparatorEnum.LTE:
        return value <= threshold
    if comparator == models.AlertComparatorEnum.EQ:
        return value == threshold
    return False


def evaluate_alerts_for_kpi(
    db: Session,
    *,
    amo_id: str,
    kpi_id: int,
    threshold_set_id: Optional[int],
    created_by_user_id: str,
) -> tuple[list[models.ReliabilityAlert], int]:
    kpi = (
        db.query(models.ReliabilityKPI)
        .filter(models.ReliabilityKPI.amo_id == amo_id, models.ReliabilityKPI.id == kpi_id)
        .first()
    )
    if not kpi:
        raise ValueError("KPI not found.")

    scope_value = _scope_value_for_kpi(kpi)
    threshold_query = db.query(models.ThresholdSet).filter(models.ThresholdSet.amo_id == amo_id)
    if threshold_set_id:
        threshold_query = threshold_query.filter(models.ThresholdSet.id == threshold_set_id)
    else:
        threshold_query = threshold_query.filter(
            models.ThresholdSet.scope_type == kpi.scope_type,
            models.ThresholdSet.scope_value == scope_value,
        )
    thresholds = threshold_query.all()
    if not thresholds:
        return [], 0

    threshold_ids = [threshold.id for threshold in thresholds]
    rules = (
        db.query(models.AlertRule)
        .filter(
            models.AlertRule.threshold_set_id.in_(threshold_ids),
            models.AlertRule.kpi_code == kpi.kpi_code,
            models.AlertRule.enabled.is_(True),
        )
        .all()
    )

    created_alerts = []
    evaluated_rules = 0
    for rule in rules:
        evaluated_rules += 1
        if _compare_value(kpi.value, rule.comparator, rule.threshold_value):
            alert = models.ReliabilityAlert(
                amo_id=amo_id,
                created_by_user_id=created_by_user_id,
                kpi_id=kpi.id,
                threshold_set_id=rule.threshold_set_id,
                alert_code=f"{kpi.kpi_code}:{rule.comparator}:{rule.threshold_value}",
                severity=rule.severity,
                message=f"KPI {kpi.kpi_code} breached {rule.comparator} {rule.threshold_value}",
                triggered_at=func.now(),
            )
            db.add(alert)
            created_alerts.append(alert)

    if created_alerts:
        db.commit()
        for alert in created_alerts:
            db.refresh(alert)
            dispatch_alert_notifications(
                db,
                amo_id=amo_id,
                alert=alert,
                created_by_user_id=created_by_user_id,
            )
    return created_alerts, evaluated_rules


def _severity_rank(severity: models.ReliabilitySeverityEnum) -> int:
    ordering = {
        models.ReliabilitySeverityEnum.LOW: 1,
        models.ReliabilitySeverityEnum.MEDIUM: 2,
        models.ReliabilitySeverityEnum.HIGH: 3,
        models.ReliabilitySeverityEnum.CRITICAL: 4,
    }
    return ordering.get(severity, 1)


def create_notification_rule(
    db: Session,
    *,
    amo_id: str,
    data: schemas.ReliabilityNotificationRuleCreate,
    created_by_user_id: Optional[str] = None,
) -> models.ReliabilityNotificationRule:
    rule = models.ReliabilityNotificationRule(
        amo_id=amo_id,
        created_by_user_id=created_by_user_id,
        **data.model_dump(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def list_notification_rules(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ReliabilityNotificationRule]:
    return (
        db.query(models.ReliabilityNotificationRule)
        .filter(models.ReliabilityNotificationRule.amo_id == amo_id)
        .order_by(models.ReliabilityNotificationRule.created_at.desc())
        .all()
    )


def dispatch_alert_notifications(
    db: Session,
    *,
    amo_id: str,
    alert: models.ReliabilityAlert,
    created_by_user_id: Optional[str],
) -> Sequence[models.ReliabilityNotification]:
    rules = (
        db.query(models.ReliabilityNotificationRule)
        .filter(
            models.ReliabilityNotificationRule.amo_id == amo_id,
            models.ReliabilityNotificationRule.is_active.is_(True),
        )
        .all()
    )
    if not rules:
        return []

    created = []
    for rule in rules:
        if _severity_rank(alert.severity) < _severity_rank(rule.severity):
            continue
        user_q = db.query(account_models.User).filter(account_models.User.amo_id == amo_id)
        if rule.department_id:
            user_q = user_q.filter(account_models.User.department_id == rule.department_id)
        if rule.role:
            user_q = user_q.filter(account_models.User.role == rule.role)
        users = user_q.all()
        for user in users:
            dedupe_key = f"alert:{alert.id}:user:{user.id}"
            existing = (
                db.query(models.ReliabilityNotification)
                .filter(
                    models.ReliabilityNotification.amo_id == amo_id,
                    models.ReliabilityNotification.user_id == user.id,
                    models.ReliabilityNotification.dedupe_key == dedupe_key,
                )
                .first()
            )
            if existing:
                continue
            notification = models.ReliabilityNotification(
                amo_id=amo_id,
                user_id=user.id,
                department_id=user.department_id,
                alert_id=alert.id,
                title=f"Reliability alert: {alert.alert_code}",
                message=alert.message,
                severity=alert.severity,
                dedupe_key=dedupe_key,
                created_by_user_id=created_by_user_id,
            )
            db.add(notification)
            created.append(notification)
    if created:
        db.commit()
        for notification in created:
            db.refresh(notification)
    return created


def list_notifications(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
) -> Sequence[models.ReliabilityNotification]:
    return (
        db.query(models.ReliabilityNotification)
        .filter(
            models.ReliabilityNotification.amo_id == amo_id,
            models.ReliabilityNotification.user_id == user_id,
        )
        .order_by(models.ReliabilityNotification.created_at.desc())
        .all()
    )


def mark_notification_read(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    notification_id: int,
    read: bool,
) -> models.ReliabilityNotification:
    notification = (
        db.query(models.ReliabilityNotification)
        .filter(
            models.ReliabilityNotification.amo_id == amo_id,
            models.ReliabilityNotification.user_id == user_id,
            models.ReliabilityNotification.id == notification_id,
        )
        .first()
    )
    if not notification:
        raise ValueError("Notification not found.")
    notification.read_at = func.now() if read else None
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def _reports_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    output_dir = base_dir / "generated" / "reliability"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def generate_reliability_report(
    db: Session,
    *,
    amo_id: str,
    created_by_user_id: str,
    window_start: date,
    window_end: date,
) -> models.ReliabilityReport:
    report = models.ReliabilityReport(
        amo_id=amo_id,
        window_start=window_start,
        window_end=window_end,
        status=models.ReliabilityReportStatusEnum.PENDING,
        created_by_user_id=created_by_user_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    if importlib.util.find_spec("reportlab") is None:
        report.status = models.ReliabilityReportStatusEnum.FAILED
        db.add(report)
        db.commit()
        return report

    from reportlab.lib.pagesizes import letter  # type: ignore[import-not-found]
    from reportlab.pdfgen import canvas  # type: ignore[import-not-found]
    from reportlab.lib.utils import ImageReader  # type: ignore[import-not-found]

    file_path = _reports_dir() / f"reliability_report_{report.id}.pdf"
    canvas_obj = canvas.Canvas(str(file_path), pagesize=letter)
    width, height = letter

    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    logo_asset = (
        db.query(account_models.AMOAsset)
        .filter(
            account_models.AMOAsset.amo_id == amo_id,
            account_models.AMOAsset.kind == account_models.AMOAssetKind.CRS_LOGO,
            account_models.AMOAsset.is_active.is_(True),
        )
        .order_by(account_models.AMOAsset.created_at.desc())
        .first()
    )
    if logo_asset:
        try:
            canvas_obj.drawImage(
                ImageReader(logo_asset.storage_path),
                40,
                height - 80,
                width=120,
                height=40,
                preserveAspectRatio=True,
                mask="auto",
            )
        except FileNotFoundError:
            pass

    canvas_obj.setFont("Helvetica-Bold", 14)
    canvas_obj.drawString(200, height - 50, "Reliability Report")
    canvas_obj.setFont("Helvetica", 10)
    canvas_obj.drawString(200, height - 65, f"AMO: {amo.name if amo else amo_id}")
    canvas_obj.drawString(200, height - 80, f"Window: {window_start} to {window_end}")

    kpis = (
        db.query(models.ReliabilityKPI)
        .filter(
            models.ReliabilityKPI.amo_id == amo_id,
            models.ReliabilityKPI.window_start >= window_start,
            models.ReliabilityKPI.window_end <= window_end,
        )
        .order_by(models.ReliabilityKPI.kpi_code.asc())
        .all()
    )
    alerts = (
        db.query(models.ReliabilityAlert)
        .filter(
            models.ReliabilityAlert.amo_id == amo_id,
            models.ReliabilityAlert.triggered_at >= datetime.combine(window_start, time.min),
            models.ReliabilityAlert.triggered_at < datetime.combine(window_end + timedelta(days=1), time.min),
        )
        .order_by(models.ReliabilityAlert.triggered_at.desc())
        .all()
    )

    y = height - 120
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(40, y, "KPI Summary")
    y -= 15
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawString(40, y, "KPI Code")
    canvas_obj.drawString(200, y, "Value")
    canvas_obj.drawString(260, y, "Unit")
    canvas_obj.drawString(320, y, "Scope")
    y -= 12

    for kpi in kpis[:30]:
        canvas_obj.drawString(40, y, kpi.kpi_code)
        canvas_obj.drawString(200, y, f"{kpi.value:.3f}")
        canvas_obj.drawString(260, y, kpi.unit or "-")
        canvas_obj.drawString(320, y, kpi.scope_type.value)
        y -= 12
        if y < 120:
            canvas_obj.showPage()
            y = height - 60

    if y < 140:
        canvas_obj.showPage()
        y = height - 60

    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(40, y, "Alerts Summary")
    y -= 15
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawString(40, y, "Alert Code")
    canvas_obj.drawString(200, y, "Severity")
    canvas_obj.drawString(260, y, "Triggered At")
    y -= 12
    for alert in alerts[:30]:
        canvas_obj.drawString(40, y, alert.alert_code)
        canvas_obj.drawString(200, y, alert.severity.value)
        canvas_obj.drawString(260, y, alert.triggered_at.strftime("%Y-%m-%d"))
        y -= 12
        if y < 80:
            canvas_obj.showPage()
            y = height - 60

    canvas_obj.save()

    report.status = models.ReliabilityReportStatusEnum.READY
    report.file_ref = str(file_path)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports(
    db: Session,
    *,
    amo_id: str,
) -> Sequence[models.ReliabilityReport]:
    return (
        db.query(models.ReliabilityReport)
        .filter(models.ReliabilityReport.amo_id == amo_id)
        .order_by(models.ReliabilityReport.created_at.desc())
        .all()
    )


def get_report(
    db: Session,
    *,
    amo_id: str,
    report_id: int,
) -> models.ReliabilityReport:
    report = (
        db.query(models.ReliabilityReport)
        .filter(models.ReliabilityReport.amo_id == amo_id, models.ReliabilityReport.id == report_id)
        .first()
    )
    if not report:
        raise ValueError("Report not found.")
    return report
