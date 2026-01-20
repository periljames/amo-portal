from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from . import models


class CustomerCreate(BaseModel):
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    currency: str = "USD"


class CustomerRead(CustomerCreate):
    id: int
    amo_id: str
    is_active: bool

    class Config:
        from_attributes = True


class VendorCreate(BaseModel):
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    remit_to_address: Optional[str] = None
    currency: str = "USD"


class VendorRead(VendorCreate):
    id: int
    amo_id: str
    is_active: bool

    class Config:
        from_attributes = True


class GLAccountCreate(BaseModel):
    code: str
    name: str
    account_type: models.GLAccountTypeEnum


class GLAccountRead(GLAccountCreate):
    id: int
    amo_id: str
    is_active: bool

    class Config:
        from_attributes = True


class InvoiceLineCreate(BaseModel):
    description: str
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    tax_code_id: Optional[int] = None
    work_order_id: Optional[int] = None
    inventory_movement_id: Optional[int] = None


class InvoiceCreate(BaseModel):
    invoice_number: str
    customer_id: Optional[int] = None
    currency: str = "USD"
    issued_date: Optional[date] = None
    due_date: Optional[date] = None
    lines: List[InvoiceLineCreate] = Field(default_factory=list)
    idempotency_key: str


class InvoiceRead(BaseModel):
    id: int
    amo_id: str
    invoice_number: str
    customer_id: Optional[int] = None
    status: models.InvoiceStatusEnum
    currency: str
    issued_date: Optional[date] = None
    due_date: Optional[date] = None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    idempotency_key: str
    created_at: datetime
    finalized_at: Optional[datetime] = None
    finalized_by_user_id: Optional[str] = None
    lines: List[InvoiceLineCreate] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CreditNoteCreate(BaseModel):
    credit_note_number: str
    invoice_id: Optional[int] = None
    customer_id: Optional[int] = None
    currency: str = "USD"
    subtotal: Decimal = Field(..., ge=0)
    tax_total: Decimal = Field(..., ge=0)
    total: Decimal = Field(..., ge=0)
    idempotency_key: str


class CreditNoteRead(BaseModel):
    id: int
    amo_id: str
    credit_note_number: str
    invoice_id: Optional[int] = None
    customer_id: Optional[int] = None
    status: models.CreditNoteStatusEnum
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    idempotency_key: str
    created_at: datetime
    finalized_at: Optional[datetime] = None
    finalized_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentAllocationCreate(BaseModel):
    invoice_id: Optional[int] = None
    amount: Decimal = Field(..., gt=0)


class PaymentCreate(BaseModel):
    customer_id: Optional[int] = None
    amount: Decimal = Field(..., gt=0)
    currency: str = "USD"
    reference: Optional[str] = None
    allocations: List[PaymentAllocationCreate] = Field(default_factory=list)
    idempotency_key: str


class PaymentRead(BaseModel):
    id: int
    amo_id: str
    customer_id: Optional[int] = None
    amount: Decimal
    currency: str
    received_at: datetime
    status: models.PaymentStatusEnum
    reference: Optional[str] = None
    idempotency_key: str

    class Config:
        from_attributes = True


class JournalLineCreate(BaseModel):
    gl_account_id: int
    description: Optional[str] = None
    debit: Decimal = Field(0, ge=0)
    credit: Decimal = Field(0, ge=0)


class JournalCreate(BaseModel):
    description: str
    entry_date: date
    lines: List[JournalLineCreate]
    post: bool = False


class JournalRead(BaseModel):
    id: int
    amo_id: str
    description: str
    entry_date: date
    status: models.JournalStatusEnum
    posted_at: Optional[datetime] = None
    posted_by_user_id: Optional[str] = None
    reversal_of_id: Optional[int] = None

    class Config:
        from_attributes = True


class TrialBalanceLine(BaseModel):
    gl_account_id: int
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal


class ARAgingBucket(BaseModel):
    bucket: str
    amount: Decimal


class ARAgingResponse(BaseModel):
    currency: str
    buckets: List[ARAgingBucket]


class ClosePeriodResponse(BaseModel):
    period: str
    status: models.AccountingPeriodStatusEnum
    closed_at: Optional[datetime] = None
    closed_by_user_id: Optional[str] = None
