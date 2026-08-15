"""Controlled Workforce bulk-operation endpoints."""
from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import bulk_governance, bulk_schemas, bulk_service, permissions, services

router = APIRouter(prefix="/workforce/hr", tags=["workforce-hr-bulk"])

_OPERATION_PATTERN = (
    "^(CREATE_CONTRACTS|ASSIGN_DEFAULT_DAY_PATTERN|ASSIGN_WORK_PATTERN|ASSIGN_ORGANIZATION|ASSIGN_POSITION|"
    "ASSIGN_BASES|ASSIGN_SUPERVISOR|UPDATE_GROUPS|UPDATE_CONTRACT_SETTINGS|SCHEDULE_OFFBOARDING)$"
)


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _error(detail: str, *, code: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "error_code": code,
            "field_errors": {},
            "conflicts": [],
            "retryable": False,
        },
    )


def _require_contract_management(db: Session, user: account_models.User) -> None:
    permissions.require_permission(
        db,
        user=user,
        permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
    )


def _require_default_pattern_management(db: Session, user: account_models.User) -> None:
    for permission in (
        permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
        permissions.PermissionCode.ROSTER_MANAGE_PATTERNS,
        permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,
    ):
        permissions.require_permission(db, user=user, permission=permission)


def _require_pattern_batch_access(db: Session, user: account_models.User) -> None:
    if permissions.any_permission(
        db,
        user=user,
        permissions=(
            permissions.PermissionCode.ROSTER_MANAGE_PATTERNS,
            permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
            permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
        ),
    ):
        return
    permissions.require_permission(
        db,
        user=user,
        permission=permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
    )


def _require_bulk_read_access(db: Session, user: account_models.User) -> None:
    if permissions.any_permission(
        db,
        user=user,
        permissions=(
            permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
            permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
            permissions.PermissionCode.ROSTER_MANAGE_PATTERNS,
        ),
    ):
        return
    permissions.require_permission(
        db,
        user=user,
        permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE,
    )


def _require_operation_management(db: Session, user: account_models.User, operation_id: str) -> None:
    operation = bulk_service.get_operation(db, amo_id=_amo(user), operation_id=operation_id)
    if operation is not None and operation.operation_type == "ASSIGN_WORK_PATTERN":
        _require_pattern_batch_access(db, user)
        return
    _require_contract_management(db, user)


def _queue(background_tasks: BackgroundTasks, operation: bulk_schemas.BulkOperationRead, created: bool) -> None:
    """Production leaves work queued for the standalone worker.

    Inline execution is an explicit development/test escape hatch only.
    """
    if (
        created
        and operation.status == "QUEUED"
        and os.getenv("WORKFORCE_BULK_INLINE_DISPATCH", "0") == "1"
    ):
        background_tasks.add_task(bulk_service.process_operation, operation.id)


@router.post(
    "/people/contracts/preview",
    response_model=bulk_schemas.ContractBatchPreview,
)
def preview_contract_batch(
    payload: bulk_schemas.ContractBatchPreviewRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_contract_management(db, current_user)
    try:
        return bulk_service.preview_contract_batch(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            payload=payload,
        )
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_CONTRACT_BATCH_PREVIEW_INVALID") from exc


@router.post(
    "/people/work-patterns/preview",
    response_model=bulk_schemas.WorkPatternBatchPreview,
)
def preview_work_pattern_batch(
    payload: bulk_schemas.WorkPatternBatchPreviewRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_pattern_batch_access(db, current_user)
    try:
        return bulk_service.preview_work_pattern_batch(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            payload=payload,
        )
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_PATTERN_BATCH_PREVIEW_INVALID") from exc


@router.post(
    "/bulk-operations/contracts",
    response_model=bulk_schemas.BulkOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_contract_batch(
    payload: bulk_schemas.ContractBatchSubmitRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_contract_management(db, current_user)
    try:
        operation, created = bulk_service.submit_contract_batch(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        db.commit()
        _queue(background_tasks, operation, created)
        return operation
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_CONTRACT_BATCH_INVALID") from exc


@router.post(
    "/bulk-operations/default-day-pattern",
    response_model=bulk_schemas.BulkOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_default_pattern_batch(
    payload: bulk_schemas.DefaultPatternBatchSubmitRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_default_pattern_management(db, current_user)
    try:
        operation, created = bulk_service.submit_default_pattern_batch(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        db.commit()
        _queue(background_tasks, operation, created)
        return operation
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_DEFAULT_PATTERN_BATCH_INVALID") from exc


@router.post(
    "/bulk-operations/work-patterns",
    response_model=bulk_schemas.BulkOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_work_pattern_batch(
    payload: bulk_schemas.WorkPatternBatchSubmitRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_pattern_batch_access(db, current_user)
    try:
        operation, created = bulk_service.submit_work_pattern_batch(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        db.commit()
        _queue(background_tasks, operation, created)
        return operation
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_PATTERN_BATCH_INVALID") from exc


@router.post(
    "/bulk-operations/personnel",
    response_model=bulk_schemas.BulkOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_personnel_mutation(
    payload: bulk_schemas.PersonnelMutationRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_contract_management(db, current_user)
    try:
        operation, created = bulk_governance.submit_personnel_mutation(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        db.commit()
        _queue(background_tasks, operation, created)
        return operation
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_PERSONNEL_MUTATION_INVALID") from exc


@router.get(
    "/bulk-operations",
    response_model=bulk_schemas.BulkOperationsPage,
)
def get_bulk_operations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    operation_status: str | None = Query(default=None, alias="status", pattern="^(QUEUED|RUNNING|COMPLETED|COMPLETED_WITH_ERRORS|FAILED)$"),
    operation_type: str | None = Query(default=None, pattern=_OPERATION_PATTERN),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_bulk_read_access(db, current_user)
    return bulk_service.list_operations(
        db,
        amo_id=_amo(current_user),
        page=page,
        page_size=page_size,
        status=operation_status,
        operation_type=operation_type,
    )


@router.get(
    "/bulk-operations/{operation_id}",
    response_model=bulk_schemas.BulkOperationRead,
)
def get_bulk_operation(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_bulk_read_access(db, current_user)
    try:
        return bulk_service.read_operation(db, amo_id=_amo(current_user), operation_id=operation_id)
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_BULK_OPERATION_NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND) from exc


@router.get(
    "/bulk-operations/{operation_id}/items",
    response_model=bulk_schemas.BulkOperationItemsPage,
)
def get_bulk_operation_items(
    operation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    item_status: str | None = Query(default=None, alias="status", pattern="^(PENDING|RUNNING|SUCCEEDED|SKIPPED|FAILED)$"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_bulk_read_access(db, current_user)
    try:
        return bulk_service.list_items(
            db,
            amo_id=_amo(current_user),
            operation_id=operation_id,
            page=page,
            page_size=page_size,
            status=item_status,
        )
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_BULK_OPERATION_NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND) from exc


@router.get("/bulk-operations/{operation_id}/failures.csv")
def download_bulk_failure_report(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_bulk_read_access(db, current_user)
    try:
        content = bulk_service.failure_report_csv(
            db,
            amo_id=_amo(current_user),
            operation_id=operation_id,
        )
    except ValueError as exc:
        raise _error(str(exc), code="WORKFORCE_BULK_OPERATION_NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND) from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="workforce-bulk-{operation_id}-failures.csv"'},
    )


@router.post(
    "/bulk-operations/{operation_id}/retry",
    response_model=bulk_schemas.BulkOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_bulk_operation(
    operation_id: str,
    payload: bulk_schemas.BulkOperationRetryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_operation_management(db, current_user, operation_id)
    try:
        operation, created = bulk_service.retry_failed_operation(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            operation_id=operation_id,
            idempotency_key=payload.idempotency_key,
        )
        db.commit()
        _queue(background_tasks, operation, created)
        return operation
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_BULK_OPERATION_RETRY_INVALID") from exc


@router.post(
    "/bulk-operations/{operation_id}/resume",
    response_model=bulk_schemas.BulkOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_bulk_operation(
    operation_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_operation_management(db, current_user, operation_id)
    try:
        operation = bulk_service.resume_operation(
            db,
            amo_id=_amo(current_user),
            actor=current_user,
            operation_id=operation_id,
        )
        db.commit()
        _queue(background_tasks, operation, True)
        return operation
    except ValueError as exc:
        db.rollback()
        raise _error(str(exc), code="WORKFORCE_BULK_OPERATION_RESUME_INVALID", status_code=status.HTTP_409_CONFLICT) from exc
