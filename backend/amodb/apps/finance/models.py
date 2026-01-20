from __future__ import annotations

import enum
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class TaxTypeEnum(str, enum.Enum):
    VAT = "VAT"
    GST = "GST"
    SALES = "SALES"
    NONE = "NONE"


class InvoiceStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"
    VOID = "VOID"


class CreditNoteStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"
    VOID = "VOID"


class PaymentStatusEnum(str, enum.Enum):
    RECEIVED = "RECEIVED"
    VOID = "VOID"


class JournalStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class AccountingPeriodStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class GLAccountTypeEnum(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (UniqueConstraint("code", name="uq_currency_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(8), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    symbol = Column(String(8), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class TaxCode(Base):
    __tablename__ = "tax_codes"
    __table_args__ = (UniqueConstraint("code", name="uq_tax_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), nullable=False, unique=True, index=True)
    description = Column(String(128), nullable=True)
    tax_type = Column(SAEnum(TaxTypeEnum, name="tax_type_enum", native_enum=False), nullable=False)
    rate = Column(Numeric(6, 4), nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_customer_code"),
        Index("ix_customers_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    billing_address = Column(Text, nullable=True)
    currency = Column(String(8), nullable=False, default="USD")
    is_active = Column(Boolean, nullable=False, default=True)


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_vendor_code"),
        Index("ix_vendors_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    remit_to_address = Column(Text, nullable=True)
    currency = Column(String(8), nullable=False, default="USD")
    is_active = Column(Boolean, nullable=False, default=True)


class GLAccount(Base):
    __tablename__ = "gl_accounts"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_gl_account_code"),
        Index("ix_gl_accounts_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    account_type = Column(SAEnum(GLAccountTypeEnum, name="gl_account_type_enum", native_enum=False), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class Invoice(Base):
    __tablename__ = "finance_invoices"
    __table_args__ = (
        UniqueConstraint("amo_id", "invoice_number", name="uq_invoice_number"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_finance_invoice_idempotency"),
        Index("ix_finance_invoices_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number = Column(String(64), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    status = Column(SAEnum(InvoiceStatusEnum, name="invoice_status_enum", native_enum=False), nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    issued_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_total = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    lines = relationship("InvoiceLine", back_populates="invoice", lazy="selectin")
    customer = relationship("Customer", lazy="joined")


class InvoiceLine(Base):
    __tablename__ = "finance_invoice_lines"
    __table_args__ = (Index("ix_invoice_lines_invoice", "invoice_id"),)

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("finance_invoices.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id", ondelete="SET NULL"), nullable=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    inventory_movement_id = Column(Integer, ForeignKey("inventory_movement_ledger.id", ondelete="SET NULL"), nullable=True)

    invoice = relationship("Invoice", back_populates="lines", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")


class CreditNote(Base):
    __tablename__ = "finance_credit_notes"
    __table_args__ = (
        UniqueConstraint("amo_id", "credit_note_number", name="uq_credit_note_number"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_credit_note_idempotency"),
        Index("ix_credit_notes_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    credit_note_number = Column(String(64), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        SAEnum(CreditNoteStatusEnum, name="credit_note_status_enum", native_enum=False),
        nullable=False,
    )
    currency = Column(String(8), nullable=False, default="USD")
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_total = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    invoice = relationship("Invoice", lazy="joined")
    customer = relationship("Customer", lazy="joined")


class Payment(Base):
    __tablename__ = "finance_payments"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_payment_idempotency"),
        Index("ix_payments_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status = Column(SAEnum(PaymentStatusEnum, name="payment_status_enum", native_enum=False), nullable=False)
    reference = Column(String(128), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    allocations = relationship("PaymentAllocation", back_populates="payment", lazy="selectin")


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (Index("ix_payment_allocations_payment", "payment_id"),)

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("finance_payments.id", ondelete="CASCADE"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)

    payment = relationship("Payment", back_populates="allocations", lazy="joined")
    invoice = relationship("Invoice", lazy="joined")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    entry_date = Column(Date, nullable=False, default=date.today)
    status = Column(SAEnum(JournalStatusEnum, name="journal_status_enum", native_enum=False), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    posted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reversal_of_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    lines = relationship("JournalLine", back_populates="journal_entry", lazy="selectin")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (Index("ix_journal_lines_entry", "journal_entry_id"),)

    id = Column(Integer, primary_key=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False)
    gl_account_id = Column(Integer, ForeignKey("gl_accounts.id", ondelete="RESTRICT"), nullable=False)
    description = Column(String(255), nullable=True)
    debit = Column(Numeric(12, 2), nullable=False, default=0)
    credit = Column(Numeric(12, 2), nullable=False, default=0)

    journal_entry = relationship("JournalEntry", back_populates="lines", lazy="joined")
    gl_account = relationship("GLAccount", lazy="joined")


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"
    __table_args__ = (
        UniqueConstraint("amo_id", "period", name="uq_accounting_period"),
        Index("ix_accounting_periods_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    period = Column(String(16), nullable=False, index=True)
    status = Column(
        SAEnum(AccountingPeriodStatusEnum, name="accounting_period_status_enum", native_enum=False),
        nullable=False,
        default=AccountingPeriodStatusEnum.OPEN,
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
