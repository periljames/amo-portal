from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import models, schemas, services

router = APIRouter(
    prefix="",
    tags=["inventory"],
    dependencies=[Depends(require_module("inventory"))],
)

INVENTORY_WRITE_ROLES = [
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.STORES,
    account_models.AccountRole.STORES_MANAGER,
    account_models.AccountRole.STOREKEEPER,
    account_models.AccountRole.QUALITY_INSPECTOR,
]


def _amo_id(current_user: account_models.User) -> str:
    return str(getattr(current_user, "effective_amo_id", None) or current_user.amo_id)


@router.post(
    "/inventory/receive",
    response_model=schemas.InventoryLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def receive_inventory(
    payload: schemas.InventoryReceiveRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*INVENTORY_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    if payload.condition is None:
        payload.condition = models.InventoryConditionEnum.QUARANTINE
    entry = services.receive_inventory(
        db,
        amo_id=_amo_id(current_user),
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post(
    "/inventory/inspect",
    response_model=List[schemas.InventoryLedgerRead],
    status_code=status.HTTP_201_CREATED,
)
def inspect_inventory(
    payload: schemas.InventoryInspectRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*INVENTORY_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    entries = services.inspect_inventory(
        db,
        amo_id=_amo_id(current_user),
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    for entry in entries:
        db.refresh(entry)
    return entries


@router.post(
    "/inventory/transfer",
    response_model=schemas.InventoryLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def transfer_inventory(
    payload: schemas.InventoryTransferRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*INVENTORY_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    entry = services.transfer_inventory(
        db,
        amo_id=_amo_id(current_user),
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post(
    "/inventory/issue",
    response_model=schemas.InventoryLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def issue_inventory(
    payload: schemas.InventoryIssueRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*INVENTORY_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    entry = services.issue_inventory(
        db,
        amo_id=_amo_id(current_user),
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post(
    "/inventory/return",
    response_model=schemas.InventoryLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def return_inventory(
    payload: schemas.InventoryReturnRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*INVENTORY_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    entry = services.return_inventory(
        db,
        amo_id=_amo_id(current_user),
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post(
    "/inventory/scrap",
    response_model=schemas.InventoryLedgerRead,
    status_code=status.HTTP_201_CREATED,
)
def scrap_inventory(
    payload: schemas.InventoryScrapRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*INVENTORY_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    entry = services.scrap_inventory(
        db,
        amo_id=_amo_id(current_user),
        payload=payload,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get(
    "/inventory/on-hand",
    response_model=List[schemas.InventoryOnHandItem],
)
def list_on_hand(
    part_number: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_on_hand(db, amo_id=_amo_id(current_user), part_number=part_number)


@router.get(
    "/inventory/ledger",
    response_model=List[schemas.InventoryLedgerRead],
)
def list_ledger(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_ledger(db, amo_id=_amo_id(current_user), skip=skip, limit=limit)
