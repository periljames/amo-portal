# backend/amodb/apps/reliability/router.py

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user
from ...database import get_write_db
from ..accounts import models as account_models
from . import schemas, services

router = APIRouter(
    prefix="/reliability",
    tags=["reliability"],
    dependencies=[Depends(require_module("reliability"))],
)


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
    return services.create_fracas_action(db, data=payload)


@router.get(
    "/fracas/{fracas_case_id}/actions",
    response_model=List[schemas.FRACASActionRead],
)
def list_fracas_actions(
    fracas_case_id: int,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_fracas_actions(db, fracas_case_id=fracas_case_id)


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
    return services.create_engine_snapshot(db, amo_id=current_user.amo_id, data=payload)


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
    return services.create_component_instance(db, data=payload)


@router.get(
    "/component-instances",
    response_model=List[schemas.ComponentInstanceRead],
)
def list_component_instances(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_component_instances(db)


@router.post(
    "/part-movements",
    response_model=schemas.PartMovementLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_part_movement(
    payload: schemas.PartMovementLedgerCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_part_movement(db, amo_id=current_user.amo_id, data=payload)


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
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_removal_event(db, amo_id=current_user.amo_id, data=payload)


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
    return services.create_alert_rule(db, data=payload)


@router.get(
    "/threshold-sets/{threshold_set_id}/alert-rules",
    response_model=List[schemas.AlertRuleRead],
)
def list_alert_rules(
    threshold_set_id: int,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.list_alert_rules(db, threshold_set_id=threshold_set_id)


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
