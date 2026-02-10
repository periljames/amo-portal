from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.apps.audit import schemas as audit_schemas

from . import models, schemas


DEFAULT_ACCOUNTS = [
    ("1000", "Cash", models.GLAccountTypeEnum.ASSET),
    ("1100", "Inventory", models.GLAccountTypeEnum.ASSET),
    ("1200", "Accounts Receivable", models.GLAccountTypeEnum.ASSET),
    ("2100", "Accounts Payable", models.GLAccountTypeEnum.LIABILITY),
    ("2200", "Tax Payable", models.GLAccountTypeEnum.LIABILITY),
    ("4000", "Revenue", models.GLAccountTypeEnum.INCOME),
    ("5000", "Cost of Goods Sold", models.GLAccountTypeEnum.EXPENSE),
    ("5100", "Scrap Expense", models.GLAccountTypeEnum.EXPENSE),
]


ACCOUNT_LOOKUP = {
    "cash": "1000",
    "inventory": "1100",
    "ar": "1200",
    "ap": "2100",
    "tax": "2200",
    "revenue": "4000",
    "cogs": "5000",
    "scrap": "5100",
}


def _audit_event(db: Session, *, amo_id: str, entity_type: str, entity_id: str, action: str, actor_user_id: Optional[str], after_json: dict) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            after_json=after_json,
        ),
    )


def ensure_finance_defaults(db: Session, *, amo_id: str) -> None:
    created = False
    existing_accounts = {a.code for a in db.query(models.GLAccount).filter(models.GLAccount.amo_id == amo_id).all()}
    for code, name, acc_type in DEFAULT_ACCOUNTS:
        if code in existing_accounts:
            continue
        # Flush each GL account insert independently to avoid driver-side
        # insertmany VALUES casting regressions on some PostgreSQL enum
        # deployments (`gl_account_type_enum` vs VARCHAR).
        db.add(
            models.GLAccount(
                amo_id=amo_id,
                code=code,
                name=name,
                account_type=acc_type,
                is_active=True,
            )
        )
        db.flush()
        created = True

    existing_tax = {t.code for t in db.query(models.TaxCode).all()}
    if "NONE" not in existing_tax:
        db.add(
            models.TaxCode(
                code="NONE",
                description="No tax",
                tax_type=models.TaxTypeEnum.NONE,
                rate=Decimal("0"),
                is_active=True,
            )
        )
        created = True

    existing_currency = {c.code for c in db.query(models.Currency).all()}
    if "USD" not in existing_currency:
        db.add(models.Currency(code="USD", name="US Dollar", symbol="$", is_active=True))
        created = True

    if created:
        db.flush()


def _get_account(db: Session, *, amo_id: str, code_key: str) -> models.GLAccount:
    code = ACCOUNT_LOOKUP[code_key]
    account = (
        db.query(models.GLAccount)
        .filter(models.GLAccount.amo_id == amo_id, models.GLAccount.code == code)
        .first()
    )
    if not account:
        raise HTTPException(status_code=409, detail=f"GL account {code} missing; run finance seed.")
    return account


def _create_journal_entry(
    db: Session,
    *,
    amo_id: str,
    description: str,
    entry_date: date,
    lines: List[models.JournalLine],
    actor_user_id: Optional[str],
    post: bool = True,
) -> models.JournalEntry:
    total_debit = sum(Decimal(line.debit or 0) for line in lines)
    total_credit = sum(Decimal(line.credit or 0) for line in lines)
    if total_debit != total_credit:
        raise HTTPException(status_code=400, detail="Journal entry is not balanced.")

    entry = models.JournalEntry(
        amo_id=amo_id,
        description=description,
        entry_date=entry_date,
        status=models.JournalStatusEnum.DRAFT,
    )
    db.add(entry)
    db.flush()
    for line in lines:
        line.journal_entry = entry
        db.add(line)

    if post:
        entry.status = models.JournalStatusEnum.POSTED
        entry.posted_at = datetime.utcnow()
        entry.posted_by_user_id = actor_user_id
        db.add(entry)

    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="JournalEntry",
        entity_id=str(entry.id),
        action="post" if post else "create",
        actor_user_id=actor_user_id,
        after_json={"status": entry.status.value, "description": description},
    )
    return entry


def post_inventory_receipt(db: Session, *, amo_id: str, amount: Decimal, actor_user_id: Optional[str], reference: str) -> models.JournalEntry:
    ensure_finance_defaults(db, amo_id=amo_id)
    inventory = _get_account(db, amo_id=amo_id, code_key="inventory")
    ap = _get_account(db, amo_id=amo_id, code_key="ap")
    lines = [
        models.JournalLine(gl_account_id=inventory.id, debit=amount, credit=Decimal("0")),
        models.JournalLine(gl_account_id=ap.id, debit=Decimal("0"), credit=amount),
    ]
    return _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Inventory receipt {reference}",
        entry_date=date.today(),
        lines=lines,
        actor_user_id=actor_user_id,
        post=True,
    )


def post_inventory_issue(db: Session, *, amo_id: str, amount: Decimal, actor_user_id: Optional[str], reference: str) -> models.JournalEntry:
    ensure_finance_defaults(db, amo_id=amo_id)
    inventory = _get_account(db, amo_id=amo_id, code_key="inventory")
    cogs = _get_account(db, amo_id=amo_id, code_key="cogs")
    lines = [
        models.JournalLine(gl_account_id=cogs.id, debit=amount, credit=Decimal("0")),
        models.JournalLine(gl_account_id=inventory.id, debit=Decimal("0"), credit=amount),
    ]
    return _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Inventory issue {reference}",
        entry_date=date.today(),
        lines=lines,
        actor_user_id=actor_user_id,
        post=True,
    )


def post_inventory_scrap(db: Session, *, amo_id: str, amount: Decimal, actor_user_id: Optional[str], reference: str) -> models.JournalEntry:
    ensure_finance_defaults(db, amo_id=amo_id)
    inventory = _get_account(db, amo_id=amo_id, code_key="inventory")
    scrap = _get_account(db, amo_id=amo_id, code_key="scrap")
    lines = [
        models.JournalLine(gl_account_id=scrap.id, debit=amount, credit=Decimal("0")),
        models.JournalLine(gl_account_id=inventory.id, debit=Decimal("0"), credit=amount),
    ]
    return _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Inventory scrap {reference}",
        entry_date=date.today(),
        lines=lines,
        actor_user_id=actor_user_id,
        post=True,
    )


def create_invoice(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InvoiceCreate,
    actor_user_id: Optional[str],
) -> models.Invoice:
    existing = (
        db.query(models.Invoice)
        .filter(models.Invoice.amo_id == amo_id, models.Invoice.idempotency_key == payload.idempotency_key)
        .first()
    )
    if existing:
        return existing

    invoice = models.Invoice(
        amo_id=amo_id,
        invoice_number=payload.invoice_number,
        customer_id=payload.customer_id,
        status=models.InvoiceStatusEnum.DRAFT,
        currency=payload.currency,
        issued_date=payload.issued_date,
        due_date=payload.due_date,
        idempotency_key=payload.idempotency_key,
    )
    db.add(invoice)
    db.flush()

    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for line in payload.lines:
        line_total = line.quantity * line.unit_price
        subtotal += line_total
        tax_rate = Decimal("0")
        if line.tax_code_id:
            tax = db.query(models.TaxCode).filter(models.TaxCode.id == line.tax_code_id).first()
            if tax:
                tax_rate = Decimal(tax.rate)
        tax_amount = (line_total * tax_rate).quantize(Decimal("0.01"))
        tax_total += tax_amount
        db.add(
            models.InvoiceLine(
                invoice_id=invoice.id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_code_id=line.tax_code_id,
                work_order_id=line.work_order_id,
                inventory_movement_id=line.inventory_movement_id,
            )
        )

    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.total = subtotal + tax_total
    db.add(invoice)
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="Invoice",
        entity_id=str(invoice.id),
        action="create",
        actor_user_id=actor_user_id,
        after_json={"invoice_number": invoice.invoice_number, "total": str(invoice.total)},
    )
    return invoice


def finalize_invoice(
    db: Session,
    *,
    amo_id: str,
    invoice_id: int,
    actor_user_id: Optional[str],
) -> models.Invoice:
    invoice = (
        db.query(models.Invoice)
        .filter(models.Invoice.amo_id == amo_id, models.Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status == models.InvoiceStatusEnum.FINALIZED:
        return invoice

    ensure_finance_defaults(db, amo_id=amo_id)
    ar = _get_account(db, amo_id=amo_id, code_key="ar")
    revenue = _get_account(db, amo_id=amo_id, code_key="revenue")
    tax = _get_account(db, amo_id=amo_id, code_key="tax")

    lines = [
        models.JournalLine(gl_account_id=ar.id, debit=invoice.total, credit=Decimal("0")),
        models.JournalLine(gl_account_id=revenue.id, debit=Decimal("0"), credit=invoice.subtotal),
    ]
    if invoice.tax_total and invoice.tax_total > 0:
        lines.append(models.JournalLine(gl_account_id=tax.id, debit=Decimal("0"), credit=invoice.tax_total))

    _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Invoice {invoice.invoice_number}",
        entry_date=invoice.issued_date or date.today(),
        lines=lines,
        actor_user_id=actor_user_id,
        post=True,
    )

    invoice.status = models.InvoiceStatusEnum.FINALIZED
    invoice.finalized_at = datetime.utcnow()
    invoice.finalized_by_user_id = actor_user_id
    db.add(invoice)
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="Invoice",
        entity_id=str(invoice.id),
        action="finalize",
        actor_user_id=actor_user_id,
        after_json={"status": invoice.status.value},
    )
    return invoice


def create_credit_note(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.CreditNoteCreate,
    actor_user_id: Optional[str],
) -> models.CreditNote:
    existing = (
        db.query(models.CreditNote)
        .filter(models.CreditNote.amo_id == amo_id, models.CreditNote.idempotency_key == payload.idempotency_key)
        .first()
    )
    if existing:
        return existing

    credit_note = models.CreditNote(
        amo_id=amo_id,
        credit_note_number=payload.credit_note_number,
        invoice_id=payload.invoice_id,
        customer_id=payload.customer_id,
        status=models.CreditNoteStatusEnum.DRAFT,
        currency=payload.currency,
        subtotal=payload.subtotal,
        tax_total=payload.tax_total,
        total=payload.total,
        idempotency_key=payload.idempotency_key,
    )
    db.add(credit_note)
    db.flush()

    ensure_finance_defaults(db, amo_id=amo_id)
    ar = _get_account(db, amo_id=amo_id, code_key="ar")
    revenue = _get_account(db, amo_id=amo_id, code_key="revenue")
    tax = _get_account(db, amo_id=amo_id, code_key="tax")

    lines = [
        models.JournalLine(gl_account_id=revenue.id, debit=credit_note.subtotal, credit=Decimal("0")),
        models.JournalLine(gl_account_id=ar.id, debit=Decimal("0"), credit=credit_note.total),
    ]
    if credit_note.tax_total and credit_note.tax_total > 0:
        lines.append(models.JournalLine(gl_account_id=tax.id, debit=credit_note.tax_total, credit=Decimal("0")))

    _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Credit note {credit_note.credit_note_number}",
        entry_date=date.today(),
        lines=lines,
        actor_user_id=actor_user_id,
        post=True,
    )

    credit_note.status = models.CreditNoteStatusEnum.FINALIZED
    credit_note.finalized_at = datetime.utcnow()
    credit_note.finalized_by_user_id = actor_user_id
    db.add(credit_note)
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="CreditNote",
        entity_id=str(credit_note.id),
        action="finalize",
        actor_user_id=actor_user_id,
        after_json={"status": credit_note.status.value},
    )
    return credit_note


def create_payment(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.PaymentCreate,
    actor_user_id: Optional[str],
) -> models.Payment:
    existing = (
        db.query(models.Payment)
        .filter(models.Payment.amo_id == amo_id, models.Payment.idempotency_key == payload.idempotency_key)
        .first()
    )
    if existing:
        return existing

    payment = models.Payment(
        amo_id=amo_id,
        customer_id=payload.customer_id,
        amount=payload.amount,
        currency=payload.currency,
        status=models.PaymentStatusEnum.RECEIVED,
        reference=payload.reference,
        idempotency_key=payload.idempotency_key,
        created_by_user_id=actor_user_id,
    )
    db.add(payment)
    db.flush()

    allocated_total = Decimal("0")
    for allocation in payload.allocations:
        allocated_total += allocation.amount
        db.add(
            models.PaymentAllocation(
                payment_id=payment.id,
                invoice_id=allocation.invoice_id,
                amount=allocation.amount,
            )
        )

    if allocated_total > payload.amount:
        raise HTTPException(status_code=400, detail="Allocated amount exceeds payment total.")

    ensure_finance_defaults(db, amo_id=amo_id)
    cash = _get_account(db, amo_id=amo_id, code_key="cash")
    ar = _get_account(db, amo_id=amo_id, code_key="ar")

    lines = [
        models.JournalLine(gl_account_id=cash.id, debit=payload.amount, credit=Decimal("0")),
        models.JournalLine(gl_account_id=ar.id, debit=Decimal("0"), credit=payload.amount),
    ]
    _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Payment {payment.id}",
        entry_date=date.today(),
        lines=lines,
        actor_user_id=actor_user_id,
        post=True,
    )

    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="Payment",
        entity_id=str(payment.id),
        action="create",
        actor_user_id=actor_user_id,
        after_json={"amount": str(payment.amount)},
    )
    return payment


def create_journal(db: Session, *, amo_id: str, payload: schemas.JournalCreate, actor_user_id: Optional[str]) -> models.JournalEntry:
    ensure_finance_defaults(db, amo_id=amo_id)
    lines = []
    for line in payload.lines:
        lines.append(
            models.JournalLine(
                gl_account_id=line.gl_account_id,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
            )
        )
    entry = _create_journal_entry(
        db,
        amo_id=amo_id,
        description=payload.description,
        entry_date=payload.entry_date,
        lines=lines,
        actor_user_id=actor_user_id,
        post=payload.post,
    )
    return entry


def reverse_journal_entry(
    db: Session,
    *,
    amo_id: str,
    journal_entry_id: int,
    actor_user_id: Optional[str],
) -> models.JournalEntry:
    entry = (
        db.query(models.JournalEntry)
        .filter(
            models.JournalEntry.amo_id == amo_id,
            models.JournalEntry.id == journal_entry_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found.")
    if entry.status != models.JournalStatusEnum.POSTED:
        raise HTTPException(status_code=400, detail="Only posted journals can be reversed.")

    reversal_lines = []
    for line in entry.lines:
        reversal_lines.append(
            models.JournalLine(
                gl_account_id=line.gl_account_id,
                description=f"Reversal of {entry.id}",
                debit=line.credit,
                credit=line.debit,
            )
        )

    reversal_entry = _create_journal_entry(
        db,
        amo_id=amo_id,
        description=f"Reversal of journal {entry.id}",
        entry_date=date.today(),
        lines=reversal_lines,
        actor_user_id=actor_user_id,
        post=True,
    )
    reversal_entry.reversal_of_id = entry.id
    entry.status = models.JournalStatusEnum.REVERSED
    db.add(entry)
    db.add(reversal_entry)

    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="JournalEntry",
        entity_id=str(entry.id),
        action="reverse",
        actor_user_id=actor_user_id,
        after_json={"reversal_id": reversal_entry.id},
    )
    return reversal_entry


def trial_balance(db: Session, *, amo_id: str) -> List[schemas.TrialBalanceLine]:
    query = (
        db.query(
            models.GLAccount.id,
            models.GLAccount.code,
            models.GLAccount.name,
            func.coalesce(func.sum(models.JournalLine.debit), 0),
            func.coalesce(func.sum(models.JournalLine.credit), 0),
        )
        .join(models.JournalLine, models.JournalLine.gl_account_id == models.GLAccount.id)
        .join(models.JournalEntry, models.JournalEntry.id == models.JournalLine.journal_entry_id)
        .filter(
            models.GLAccount.amo_id == amo_id,
            models.JournalEntry.status == models.JournalStatusEnum.POSTED,
        )
        .group_by(models.GLAccount.id)
        .order_by(models.GLAccount.code.asc())
    )
    results: List[schemas.TrialBalanceLine] = []
    for row in query.all():
        results.append(
            schemas.TrialBalanceLine(
                gl_account_id=row[0],
                account_code=row[1],
                account_name=row[2],
                debit=Decimal(row[3]),
                credit=Decimal(row[4]),
            )
        )
    return results


def ar_aging(db: Session, *, amo_id: str, currency: str = "USD") -> schemas.ARAgingResponse:
    buckets = {
        "0-30": Decimal("0"),
        "31-60": Decimal("0"),
        "61-90": Decimal("0"),
        "90+": Decimal("0"),
    }

    today = date.today()
    invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.amo_id == amo_id,
            models.Invoice.status == models.InvoiceStatusEnum.FINALIZED,
            models.Invoice.currency == currency,
        )
        .all()
    )
    for invoice in invoices:
        paid = (
            db.query(func.coalesce(func.sum(models.PaymentAllocation.amount), 0))
            .join(models.Payment)
            .filter(models.PaymentAllocation.invoice_id == invoice.id)
            .scalar()
        )
        outstanding = Decimal(invoice.total) - Decimal(paid or 0)
        if outstanding <= 0:
            continue
        due = invoice.due_date or invoice.issued_date or today
        age_days = (today - due).days
        if age_days <= 30:
            buckets["0-30"] += outstanding
        elif age_days <= 60:
            buckets["31-60"] += outstanding
        elif age_days <= 90:
            buckets["61-90"] += outstanding
        else:
            buckets["90+"] += outstanding

    return schemas.ARAgingResponse(
        currency=currency,
        buckets=[schemas.ARAgingBucket(bucket=k, amount=v) for k, v in buckets.items()],
    )


def close_period(
    db: Session,
    *,
    amo_id: str,
    period: str,
    actor_user_id: Optional[str],
) -> models.AccountingPeriod:
    entry = (
        db.query(models.AccountingPeriod)
        .filter(models.AccountingPeriod.amo_id == amo_id, models.AccountingPeriod.period == period)
        .first()
    )
    if not entry:
        entry = models.AccountingPeriod(
            amo_id=amo_id,
            period=period,
            status=models.AccountingPeriodStatusEnum.CLOSED,
            closed_at=datetime.utcnow(),
            closed_by_user_id=actor_user_id,
        )
        db.add(entry)
    else:
        entry.status = models.AccountingPeriodStatusEnum.CLOSED
        entry.closed_at = datetime.utcnow()
        entry.closed_by_user_id = actor_user_id
        db.add(entry)

    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="AccountingPeriod",
        entity_id=str(entry.id or period),
        action="close",
        actor_user_id=actor_user_id,
        after_json={"period": period, "status": entry.status.value},
    )
    return entry
