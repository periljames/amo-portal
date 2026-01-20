# backend/amodb/apps/reliability/router.py

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from ...database import get_write_db
from ..accounts import models as account_models
from . import schemas, services

router = APIRouter(
    prefix="/reliability",
    tags=["reliability"],
    dependencies=[Depends(require_module("reliability"))],
)

PART_MOVEMENT_ROLES = [
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PLANNING_ENGINEER,
    account_models.AccountRole.PRODUCTION_ENGINEER,
    account_models.AccountRole.CERTIFYING_ENGINEER,
    account_models.AccountRole.CERTIFYING_TECHNICIAN,
    account_models.AccountRole.TECHNICIAN,
    account_models.AccountRole.STORES,
    account_models.AccountRole.QUALITY_MANAGER,
]


@router.post(
    "/templates/seed",
    response_model=List[schemas.ReliabilityProgramTemplateRead],
    status_code=status.HTTP_201_CREATED,
)
def seed_templates(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    created = services.seed_default_templates(
        db,
        amo_id=current_user.amo_id,
        created_by_user_id=current_user.id,
    )
    return created


@router.post(
    "/trends",
    response_model=schemas.DefectTrendRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trend(
    payload: schemas.DefectTrendCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    trend = services.compute_defect_trend(
        db,
        amo_id=current_user.amo_id,
        window_start=payload.window_start,
        window_end=payload.window_end,
        aircraft_serial_number=payload.aircraft_serial_number,
        ata_chapter=payload.ata_chapter,
    )
    return trend


@router.post(
    "/recurring",
    response_model=schemas.RecurringFindingRead,
    status_code=status.HTTP_201_CREATED,
)
def upsert_recurring(
    payload: schemas.RecurringFindingCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    instance = services.upsert_recurring_finding(
        db,
        amo_id=current_user.amo_id,
        data=payload,
    )
    return instance


@router.post(
    "/recommendations",
    response_model=schemas.ReliabilityRecommendationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recommendation(
    payload: schemas.ReliabilityRecommendationCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_recommendation(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
    )


@router.post(
    "/events",
    response_model=schemas.ReliabilityEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    payload: schemas.ReliabilityEventCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_reliability_event(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
    )


@router.get(
    "/events",
    response_model=List[schemas.ReliabilityEventRead],
)
def list_events(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_reliability_events(db, amo_id=current_user.amo_id)


@router.get(
    "/pull",
    response_model=schemas.ReliabilityPullRead,
)
def pull_reliability_feed(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 500,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.build_reliability_pull(
        db,
        amo_id=current_user.amo_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get(
    "/events/export",
    response_class=Response,
)
def export_events(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    csv_payload = services.export_reliability_events_csv(db, amo_id=current_user.amo_id)
    return Response(
        content=csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reliability_events.csv"},
    )


@router.post(
    "/ingest/e-logbook-events",
    response_model=schemas.ReliabilityEventIngestBatchResult,
    status_code=status.HTTP_201_CREATED,
)
def ingest_e_logbook_events(
    payload: schemas.ReliabilityEventIngestBatch,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        created = services.create_reliability_events_bulk(
            db,
            amo_id=current_user.amo_id,
            created_by_user_id=current_user.id,
            events=payload.events,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return schemas.ReliabilityEventIngestBatchResult(created=created)


@router.post(
    "/kpis",
    response_model=schemas.ReliabilityKPIRead,
    status_code=status.HTTP_201_CREATED,
)
def create_kpi(
    payload: schemas.ReliabilityKPICreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_kpi_snapshot(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/kpis",
    response_model=List[schemas.ReliabilityKPIRead],
)
def list_kpis(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_kpis(db, amo_id=current_user.amo_id)


@router.post(
    "/alerts",
    response_model=schemas.ReliabilityAlertRead,
    status_code=status.HTTP_201_CREATED,
)
def create_alert(
    payload: schemas.ReliabilityAlertCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_alert(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=schemas.ReliabilityAlertRead,
)
def acknowledge_alert(
    alert_id: int,
    payload: schemas.ReliabilityAlertAcknowledge,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.acknowledge_alert(
            db,
            amo_id=current_user.amo_id,
            alert_id=alert_id,
            message=payload.message,
            acknowledged_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=schemas.ReliabilityAlertRead,
)
def resolve_alert(
    alert_id: int,
    payload: schemas.ReliabilityAlertResolve,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.resolve_alert(
            db,
            amo_id=current_user.amo_id,
            alert_id=alert_id,
            message=payload.message,
            resolved_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/alerts",
    response_model=List[schemas.ReliabilityAlertRead],
)
def list_alerts(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_alerts(db, amo_id=current_user.amo_id)


@router.post(
    "/notifications/rules",
    response_model=schemas.ReliabilityNotificationRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_notification_rule(
    payload: schemas.ReliabilityNotificationRuleCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_notification_rule(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
    )


@router.get(
    "/notifications/rules",
    response_model=List[schemas.ReliabilityNotificationRuleRead],
)
def list_notification_rules(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_notification_rules(db, amo_id=current_user.amo_id)


@router.get(
    "/notifications/me",
    response_model=List[schemas.ReliabilityNotificationRead],
)
def list_my_notifications(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_notifications(db, amo_id=current_user.amo_id, user_id=current_user.id)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=schemas.ReliabilityNotificationRead,
)
def mark_notification_read(
    notification_id: int,
    payload: schemas.ReliabilityNotificationMarkRead,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.mark_notification_read(
            db,
            amo_id=current_user.amo_id,
            user_id=current_user.id,
            notification_id=notification_id,
            read=payload.read,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/alerts/evaluate",
    response_model=schemas.ReliabilityAlertEvaluationResult,
)
def evaluate_alerts(
    payload: schemas.ReliabilityAlertEvaluationRequest,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        created_alerts, evaluated_rules = services.evaluate_alerts_for_kpi(
            db,
            amo_id=current_user.amo_id,
            kpi_id=payload.kpi_id,
            threshold_set_id=payload.threshold_set_id,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return schemas.ReliabilityAlertEvaluationResult(
        created_alerts=created_alerts,
        evaluated_rules=evaluated_rules,
    )


@router.post(
    "/fracas/cases",
    response_model=schemas.FRACASCaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fracas_case(
    payload: schemas.FRACASCaseCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_fracas_case(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
    )


@router.post(
    "/fracas/cases/{case_id}/approve",
    response_model=schemas.FRACASCaseRead,
)
def approve_fracas_case(
    case_id: int,
    payload: schemas.FRACASCaseApprove,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.approve_fracas_case(
            db,
            amo_id=current_user.amo_id,
            case_id=case_id,
            approved_by_user_id=current_user.id,
            approval_notes=payload.approval_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/fracas/cases/{case_id}/verify",
    response_model=schemas.FRACASCaseRead,
)
def verify_fracas_case(
    case_id: int,
    payload: schemas.FRACASCaseVerify,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.verify_fracas_case(
            db,
            amo_id=current_user.amo_id,
            case_id=case_id,
            verified_by_user_id=current_user.id,
            verification_notes=payload.verification_notes,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/fracas/cases",
    response_model=List[schemas.FRACASCaseRead],
)
def list_fracas_cases(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_fracas_cases(db, amo_id=current_user.amo_id)


@router.post(
    "/fracas/actions",
    response_model=schemas.FRACASActionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fracas_action(
    payload: schemas.FRACASActionCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.create_fracas_action(db, amo_id=current_user.amo_id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/fracas/actions/{action_id}/verify",
    response_model=schemas.FRACASActionRead,
)
def verify_fracas_action(
    action_id: int,
    payload: schemas.FRACASActionVerify,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.verify_fracas_action(
            db,
            amo_id=current_user.amo_id,
            action_id=action_id,
            verified_by_user_id=current_user.id,
            effectiveness_notes=payload.effectiveness_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/fracas/{fracas_case_id}/actions",
    response_model=List[schemas.FRACASActionRead],
)
def list_fracas_actions(
    fracas_case_id: int,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.list_fracas_actions(db, amo_id=current_user.amo_id, fracas_case_id=fracas_case_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/engine-snapshots",
    response_model=schemas.EngineFlightSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_engine_snapshot(
    payload: schemas.EngineFlightSnapshotCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.create_engine_snapshot(db, amo_id=current_user.amo_id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/engine-snapshots",
    response_model=List[schemas.EngineFlightSnapshotRead],
)
def list_engine_snapshots(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_engine_snapshots(db, amo_id=current_user.amo_id)


@router.post(
    "/engine-trends/compute",
    response_model=List[schemas.EngineTrendStatusRead],
)
def compute_engine_trend_status(
    aircraft_serial_number: Optional[str] = None,
    engine_position: Optional[str] = None,
    engine_serial_number: Optional[str] = None,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.compute_engine_trend_status(
        db,
        amo_id=current_user.amo_id,
        aircraft_serial_number=aircraft_serial_number,
        engine_position=engine_position,
        engine_serial_number=engine_serial_number,
    )


@router.get(
    "/engine-trends/fleet-status",
    response_model=List[schemas.EngineTrendStatusRead],
)
def list_engine_trend_statuses(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_engine_trend_statuses(db, amo_id=current_user.amo_id)


@router.get(
    "/engine-trends/series",
    response_model=schemas.EngineTrendSeriesRead,
)
def get_engine_trend_series(
    aircraft_serial_number: str,
    engine_position: str,
    metric: str,
    engine_serial_number: Optional[str] = None,
    baseline_window: int = 10,
    shift_threshold: float = 3.0,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.get_engine_trend_series(
        db,
        amo_id=current_user.amo_id,
        aircraft_serial_number=aircraft_serial_number,
        engine_position=engine_position,
        metric=metric,
        engine_serial_number=engine_serial_number,
        baseline_window=baseline_window,
        shift_threshold=shift_threshold,
    )


@router.post(
    "/engine-trends/{status_id}/review",
    response_model=schemas.EngineTrendStatusRead,
)
def review_engine_trend_status(
    status_id: int,
    payload: schemas.EngineTrendStatusReview,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.review_engine_trend_status(
            db,
            amo_id=current_user.amo_id,
            status_id=status_id,
            reviewed_by_user_id=current_user.id,
            last_review_date=payload.last_review_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/ingest/engine-snapshots",
    response_model=schemas.EngineFlightSnapshotIngestBatchResult,
    status_code=status.HTTP_201_CREATED,
)
def ingest_engine_snapshots(
    payload: schemas.EngineFlightSnapshotIngestBatch,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        created = services.create_engine_snapshots_bulk(
            db,
            amo_id=current_user.amo_id,
            snapshots=payload.snapshots,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return schemas.EngineFlightSnapshotIngestBatchResult(created=created)


@router.post(
    "/oil-uplifts",
    response_model=schemas.OilUpliftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_oil_uplift(
    payload: schemas.OilUpliftCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_oil_uplift(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/oil-uplifts",
    response_model=List[schemas.OilUpliftRead],
)
def list_oil_uplifts(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_oil_uplifts(db, amo_id=current_user.amo_id)


@router.post(
    "/oil-consumption",
    response_model=schemas.OilConsumptionRateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_oil_consumption_rate(
    payload: schemas.OilConsumptionRateCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_oil_consumption_rate(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/oil-consumption",
    response_model=List[schemas.OilConsumptionRateRead],
)
def list_oil_consumption_rates(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_oil_consumption_rates(db, amo_id=current_user.amo_id)


@router.post(
    "/component-instances",
    response_model=schemas.ComponentInstanceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_component_instance(
    payload: schemas.ComponentInstanceCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_component_instance(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        actor_user_id=current_user.id,
    )


@router.get(
    "/component-instances",
    response_model=List[schemas.ComponentInstanceRead],
)
def list_component_instances(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_component_instances(db, amo_id=current_user.amo_id)


@router.post(
    "/part-movements",
    response_model=schemas.PartMovementLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_part_movement(
    payload: schemas.PartMovementLedgerCreate,
    current_user: account_models.User = Depends(require_roles(*PART_MOVEMENT_ROLES)),
    db: Session = Depends(get_write_db),
):
    return services.create_part_movement(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        actor_user_id=current_user.id,
    )


@router.get(
    "/part-movements",
    response_model=List[schemas.PartMovementLedgerRead],
)
def list_part_movements(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_part_movements(db, amo_id=current_user.amo_id)


@router.post(
    "/removals",
    response_model=schemas.RemovalEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_removal_event(
    payload: schemas.RemovalEventCreate,
    current_user: account_models.User = Depends(require_roles(*PART_MOVEMENT_ROLES)),
    db: Session = Depends(get_write_db),
):
    return services.create_removal_event(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        actor_user_id=current_user.id,
    )


@router.get(
    "/removals",
    response_model=List[schemas.RemovalEventRead],
)
def list_removal_events(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_removal_events(db, amo_id=current_user.amo_id)


@router.post(
    "/shop-visits",
    response_model=schemas.ShopVisitRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shop_visit(
    payload: schemas.ShopVisitCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_shop_visit(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/shop-visits",
    response_model=List[schemas.ShopVisitRead],
)
def list_shop_visits(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_shop_visits(db, amo_id=current_user.amo_id)


@router.post(
    "/utilization/aircraft",
    response_model=schemas.AircraftUtilizationDailyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_aircraft_utilization(
    payload: schemas.AircraftUtilizationDailyCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_aircraft_utilization(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/utilization/aircraft",
    response_model=List[schemas.AircraftUtilizationDailyRead],
)
def list_aircraft_utilization(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_aircraft_utilization(db, amo_id=current_user.amo_id)


@router.post(
    "/utilization/engine",
    response_model=schemas.EngineUtilizationDailyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_engine_utilization(
    payload: schemas.EngineUtilizationDailyCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_engine_utilization(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/utilization/engine",
    response_model=List[schemas.EngineUtilizationDailyRead],
)
def list_engine_utilization(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_engine_utilization(db, amo_id=current_user.amo_id)


@router.post(
    "/threshold-sets",
    response_model=schemas.ThresholdSetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_threshold_set(
    payload: schemas.ThresholdSetCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_threshold_set(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/threshold-sets",
    response_model=List[schemas.ThresholdSetRead],
)
def list_threshold_sets(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_threshold_sets(db, amo_id=current_user.amo_id)


@router.post(
    "/alert-rules",
    response_model=schemas.AlertRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_alert_rule(
    payload: schemas.AlertRuleCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.create_alert_rule(db, amo_id=current_user.amo_id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/threshold-sets/{threshold_set_id}/alert-rules",
    response_model=List[schemas.AlertRuleRead],
)
def list_alert_rules(
    threshold_set_id: int,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.list_alert_rules(db, amo_id=current_user.amo_id, threshold_set_id=threshold_set_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/control-charts",
    response_model=schemas.ControlChartConfigRead,
    status_code=status.HTTP_201_CREATED,
)
def create_control_chart_config(
    payload: schemas.ControlChartConfigCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_control_chart_config(db, amo_id=current_user.amo_id, data=payload)


@router.get(
    "/control-charts",
    response_model=List[schemas.ControlChartConfigRead],
)
def list_control_chart_configs(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_control_chart_configs(db, amo_id=current_user.amo_id)


@router.post(
    "/reports",
    response_model=schemas.ReliabilityReportRead,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    payload: schemas.ReliabilityReportCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.generate_reliability_report(
        db,
        amo_id=current_user.amo_id,
        created_by_user_id=current_user.id,
        window_start=payload.window_start,
        window_end=payload.window_end,
    )


@router.get(
    "/reports",
    response_model=List[schemas.ReliabilityReportRead],
)
def list_reports(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_reports(db, amo_id=current_user.amo_id)


@router.get(
    "/reports/{report_id}",
    response_model=schemas.ReliabilityReportRead,
)
def get_report(
    report_id: int,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        return services.get_report(db, amo_id=current_user.amo_id, report_id=report_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/reports/{report_id}/download",
    response_class=FileResponse,
)
def download_report(
    report_id: int,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    try:
        report = services.get_report(db, amo_id=current_user.amo_id, report_id=report_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not report.file_ref:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Report is not ready.")
    return FileResponse(report.file_ref, filename=f"reliability_report_{report.id}.pdf")
