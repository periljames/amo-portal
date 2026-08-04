from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import readiness_services
from .readiness_schemas import (
    ForecastScenarioCreate,
    ForecastScenarioRead,
    ForecastScenarioUpdate,
    PackageFreezeCreate,
    PackageFreezeRead,
    ReadinessAssessmentRead,
    ReadinessDashboardRead,
    ReadinessRequirementCreate,
    ReadinessRequirementRead,
    ReadinessRequirementUpdate,
)

router = APIRouter(
    prefix="/planning-control",
    tags=["forecast_readiness"],
    dependencies=[Depends(require_module("work"))],
)

PLANNING_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
)
READINESS_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
)


@router.get("/dashboard", response_model=ReadinessDashboardRead)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return readiness_services.dashboard(db, amo_id=current_user.effective_amo_id)


@router.get("/scenarios", response_model=list[ForecastScenarioRead])
def list_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return readiness_services.list_scenarios(db, amo_id=current_user.effective_amo_id)


@router.post("/scenarios", response_model=ForecastScenarioRead, status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: ForecastScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PLANNING_ROLES)),
):
    row = readiness_services.create_scenario(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/scenarios/{scenario_id}", response_model=ForecastScenarioRead)
def update_scenario(
    scenario_id: str,
    payload: ForecastScenarioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PLANNING_ROLES)),
):
    scenario = readiness_services._get_scenario(
        db,
        amo_id=current_user.effective_amo_id,
        scenario_id=scenario_id,
    )
    readiness_services.update_scenario(db, scenario=scenario, payload=payload, actor=current_user)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.post("/scenarios/{scenario_id}/run", response_model=ForecastScenarioRead)
def run_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PLANNING_ROLES)),
):
    scenario = readiness_services._get_scenario(
        db,
        amo_id=current_user.effective_amo_id,
        scenario_id=scenario_id,
    )
    readiness_services.run_scenario(db, scenario=scenario, actor=current_user)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.get("/packages/{package_id}/requirements", response_model=list[ReadinessRequirementRead])
def list_requirements(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return readiness_services.list_requirements(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )


@router.post(
    "/packages/{package_id}/requirements",
    response_model=ReadinessRequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_requirement(
    package_id: int,
    payload: ReadinessRequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*READINESS_ROLES)),
):
    row = readiness_services.create_requirement(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/requirements/{requirement_id}", response_model=ReadinessRequirementRead)
def update_requirement(
    requirement_id: str,
    payload: ReadinessRequirementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*READINESS_ROLES)),
):
    row = readiness_services.update_requirement(
        db,
        amo_id=current_user.effective_amo_id,
        requirement_id=requirement_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/packages/{package_id}/assess", response_model=ReadinessAssessmentRead)
def assess_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*READINESS_ROLES)),
):
    row = readiness_services.assess_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/packages/{package_id}/assessments", response_model=list[ReadinessAssessmentRead])
def list_assessments(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return readiness_services.list_assessments(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )


@router.post("/packages/{package_id}/freeze", response_model=PackageFreezeRead)
def freeze_package(
    package_id: int,
    payload: PackageFreezeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PLANNING_ROLES)),
):
    row = readiness_services.freeze_package(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/packages/{package_id}/freezes", response_model=list[PackageFreezeRead])
def list_freezes(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return readiness_services.list_freezes(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )
