from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import execution_services
from .execution_schemas import (
    ExecutionDashboardRead,
    ExecutionEventCreate,
    ExecutionEventRead,
    ExecutionSessionClose,
    ExecutionSessionCreate,
    ExecutionSessionRead,
    HandbackBuildRequest,
    HandbackFindingCreate,
    HandbackFindingRead,
    HandbackFindingResolve,
    HandbackRead,
    HandbackReviewRequest,
    HandbackSubmitRequest,
    TaskIssueCreate,
    TaskIssueRead,
    TaskIssueResolve,
)

router = APIRouter(
    prefix="/execution-control",
    tags=["production_execution_control"],
    dependencies=[Depends(require_module("work"))],
)

EXECUTION_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
    AccountRole.TECHNICIAN,
)
SUPERVISOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
)
RECORDS_REVIEW_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
)


@router.get("/dashboard", response_model=ExecutionDashboardRead)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return execution_services.dashboard(db, amo_id=current_user.effective_amo_id)


@router.get("/sessions", response_model=list[ExecutionSessionRead])
def list_sessions(
    package_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return execution_services.list_sessions(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )


@router.post("/sessions", response_model=ExecutionSessionRead, status_code=status.HTTP_201_CREATED)
def start_session(
    payload: ExecutionSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*EXECUTION_ROLES)),
):
    row = execution_services.start_session(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/sessions/{session_id}/events", response_model=ExecutionEventRead)
def record_event(
    session_id: str,
    payload: ExecutionEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*EXECUTION_ROLES)),
):
    session = execution_services._get_session(db, amo_id=current_user.effective_amo_id, session_id=session_id)
    row = execution_services.record_event(db, session=session, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/sessions/{session_id}/issues", response_model=TaskIssueRead, status_code=status.HTTP_201_CREATED)
def raise_issue(
    session_id: str,
    payload: TaskIssueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*EXECUTION_ROLES)),
):
    session = execution_services._get_session(db, amo_id=current_user.effective_amo_id, session_id=session_id)
    row = execution_services.raise_issue(db, session=session, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/issues/{issue_id}/resolve", response_model=TaskIssueRead)
def resolve_issue(
    issue_id: str,
    payload: TaskIssueResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SUPERVISOR_ROLES)),
):
    row = execution_services.resolve_issue(
        db,
        amo_id=current_user.effective_amo_id,
        issue_id=issue_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/sessions/{session_id}/close", response_model=ExecutionSessionRead)
def close_session(
    session_id: str,
    payload: ExecutionSessionClose,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SUPERVISOR_ROLES)),
):
    session = execution_services._get_session(db, amo_id=current_user.effective_amo_id, session_id=session_id)
    execution_services.close_session(db, session=session, payload=payload, actor=current_user)
    db.commit()
    db.refresh(session)
    return session


@router.get("/handbacks", response_model=list[HandbackRead])
def list_handbacks(
    package_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return execution_services.list_handbacks(
        db,
        amo_id=current_user.effective_amo_id,
        package_id=package_id,
    )


@router.post("/handbacks/build", response_model=HandbackRead, status_code=status.HTTP_201_CREATED)
def build_handback(
    payload: HandbackBuildRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SUPERVISOR_ROLES)),
):
    row = execution_services.build_handback(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/handbacks/{handback_id}/submit", response_model=HandbackRead)
def submit_handback(
    handback_id: str,
    payload: HandbackSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SUPERVISOR_ROLES)),
):
    row = execution_services._get_handback(db, amo_id=current_user.effective_amo_id, handback_id=handback_id)
    execution_services.submit_handback(db, handback=row, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/handbacks/{handback_id}/findings", response_model=HandbackFindingRead, status_code=status.HTTP_201_CREATED)
def add_finding(
    handback_id: str,
    payload: HandbackFindingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*RECORDS_REVIEW_ROLES)),
):
    handback = execution_services._get_handback(db, amo_id=current_user.effective_amo_id, handback_id=handback_id)
    row = execution_services.add_finding(db, handback=handback, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/findings/{finding_id}/resolve", response_model=HandbackFindingRead)
def resolve_finding(
    finding_id: str,
    payload: HandbackFindingResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SUPERVISOR_ROLES)),
):
    row = execution_services.resolve_finding(
        db,
        amo_id=current_user.effective_amo_id,
        finding_id=finding_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/handbacks/{handback_id}/review", response_model=HandbackRead)
def review_handback(
    handback_id: str,
    payload: HandbackReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*RECORDS_REVIEW_ROLES)),
):
    row = execution_services._get_handback(db, amo_id=current_user.effective_amo_id, handback_id=handback_id)
    execution_services.review_handback(db, handback=row, payload=payload, actor=current_user)
    db.commit()
    db.refresh(row)
    return row
