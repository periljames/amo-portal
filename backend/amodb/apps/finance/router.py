from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from amodb.database import get_db
from amodb.apps.accounts import models as account_models

from . import schemas, services

router = APIRouter(
    prefix="",
    tags=["finance", "accounting"],
    dependencies=[Depends(require_module("finance_inventory"))],
)

FINANCE_WRITE_ROLES = [
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.FINANCE_MANAGER,
    account_models.AccountRole.ACCOUNTS_OFFICER,
]


@router.post(
    "/finance/invoices",
    response_model=schemas.InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice(
    payload: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    invoice = services.create_invoice(db, amo_id=current_user.amo_id, payload=payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post(
    "/finance/invoices/{invoice_id}/finalize",
    response_model=schemas.InvoiceRead,
)
def finalize_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_WRITE_ROLES)),
):
    invoice = services.finalize_invoice(db, amo_id=current_user.amo_id, invoice_id=invoice_id, actor_user_id=current_user.id)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post(
    "/finance/credit-notes",
    response_model=schemas.CreditNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_credit_note(
    payload: schemas.CreditNoteCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    credit_note = services.create_credit_note(db, amo_id=current_user.amo_id, payload=payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(credit_note)
    return credit_note


@router.post(
    "/finance/payments",
    response_model=schemas.PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    payload: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_WRITE_ROLES)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not payload.idempotency_key and idempotency_key:
        payload.idempotency_key = idempotency_key
    payment = services.create_payment(db, amo_id=current_user.amo_id, payload=payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(payment)
    return payment


@router.get(
    "/finance/ar-aging",
    response_model=schemas.ARAgingResponse,
)
def ar_aging(
    currency: str = "USD",
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.ar_aging(db, amo_id=current_user.amo_id, currency=currency)


@router.post(
    "/accounting/journals",
    response_model=schemas.JournalRead,
    status_code=status.HTTP_201_CREATED,
)
def create_journal(
    payload: schemas.JournalCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_WRITE_ROLES)),
):
    entry = services.create_journal(db, amo_id=current_user.amo_id, payload=payload, actor_user_id=current_user.id)
    db.commit()
    db.refresh(entry)
    return entry


@router.get(
    "/accounting/trial-balance",
    response_model=List[schemas.TrialBalanceLine],
)
def trial_balance(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.trial_balance(db, amo_id=current_user.amo_id)


@router.post(
    "/accounting/periods/{period}/close",
    response_model=schemas.ClosePeriodResponse,
)
def close_period(
    period: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_WRITE_ROLES)),
):
    entry = services.close_period(db, amo_id=current_user.amo_id, period=period, actor_user_id=current_user.id)
    db.commit()
    db.refresh(entry)
    return schemas.ClosePeriodResponse(
        period=entry.period,
        status=entry.status,
        closed_at=entry.closed_at,
        closed_by_user_id=entry.closed_by_user_id,
    )
