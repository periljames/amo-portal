from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import migration_services
from .migration_schemas import (
    MigrationApprovalRequest,
    MigrationBatchCreate,
    MigrationBatchRead,
    MigrationCheckpointRead,
    MigrationCheckpointUpdate,
    MigrationCommitRequest,
    MigrationPresetCreate,
    MigrationReconciliationDecision,
    MigrationReconciliationRead,
    MigrationRollbackRequest,
    MigrationStageRequest,
    MigrationSummaryRead,
)


router = APIRouter(
    prefix="/migration",
    tags=["migration_control"],
    dependencies=[Depends(require_module("work"))],
)

MIGRATION_EDITOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
)
MIGRATION_APPROVER_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
)


@router.get("/summary", response_model=MigrationSummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return migration_services.summary(db, amo_id=current_user.effective_amo_id)


@router.get("/batches", response_model=list[MigrationBatchRead])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return migration_services.list_batches(db, amo_id=current_user.effective_amo_id)


@router.get("/batches/{batch_id}", response_model=MigrationBatchRead)
def get_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    return migration_services.batch_read(batch)


@router.post("/batches", response_model=MigrationBatchRead, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: MigrationBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_EDITOR_ROLES)),
):
    batch = migration_services.create_batch(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/presets/5y-sls", response_model=MigrationBatchRead, status_code=status.HTTP_201_CREATED)
def create_5y_sls_pilot(
    payload: MigrationPresetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_EDITOR_ROLES)),
):
    batch = migration_services.create_5y_sls_preset(
        db,
        amo_id=current_user.effective_amo_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/batches/{batch_id}/stage", response_model=MigrationBatchRead)
def stage_rows(
    batch_id: str,
    payload: MigrationStageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_EDITOR_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    migration_services.stage_rows(db, batch=batch, payload=payload, actor=current_user)
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/batches/{batch_id}/validate", response_model=MigrationBatchRead)
def validate_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_EDITOR_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    migration_services.validate_batch(db, batch=batch, actor=current_user)
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/batches/{batch_id}/reconcile", response_model=MigrationBatchRead)
def reconcile_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_EDITOR_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    migration_services.reconcile_batch(db, batch=batch, actor=current_user)
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/batches/{batch_id}/reconciliation/{item_id}/decision", response_model=MigrationReconciliationRead)
def decide_reconciliation(
    batch_id: str,
    item_id: str,
    payload: MigrationReconciliationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_APPROVER_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    item = migration_services.decide_reconciliation(
        db,
        batch=batch,
        item_id=item_id,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(item)
    return item


@router.put("/batches/{batch_id}/checkpoints/{checkpoint_key}", response_model=MigrationCheckpointRead)
def update_checkpoint(
    batch_id: str,
    checkpoint_key: str,
    payload: MigrationCheckpointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_APPROVER_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    checkpoint = migration_services.update_checkpoint(
        db,
        batch=batch,
        checkpoint_key=checkpoint_key,
        payload=payload,
        actor=current_user,
    )
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


@router.post("/batches/{batch_id}/approve", response_model=MigrationBatchRead)
def approve_batch(
    batch_id: str,
    payload: MigrationApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_APPROVER_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    migration_services.approve_batch(db, batch=batch, payload=payload, actor=current_user)
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/batches/{batch_id}/commit", response_model=MigrationBatchRead)
def commit_batch(
    batch_id: str,
    payload: MigrationCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MIGRATION_APPROVER_ROLES)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    migration_services.commit_batch(db, batch=batch, payload=payload, actor=current_user)
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)


@router.post("/batches/{batch_id}/rollback", response_model=MigrationBatchRead)
def rollback_batch(
    batch_id: str,
    payload: MigrationRollbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AccountRole.SUPERUSER, AccountRole.AMO_ADMIN)),
):
    batch = migration_services._get_batch(db, amo_id=current_user.effective_amo_id, batch_id=batch_id)
    migration_services.rollback_batch(db, batch=batch, payload=payload, actor=current_user)
    db.commit()
    db.refresh(batch)
    return migration_services.batch_read(batch)
