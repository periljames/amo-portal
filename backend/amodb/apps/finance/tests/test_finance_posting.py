from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.crs import models as crs_models
from amodb.apps.maintenance_program import models as maintenance_models
from amodb.apps.finance import models as finance_models
from amodb.apps.finance import services as finance_services
from amodb.apps.finance import schemas as finance_schemas
from amodb.apps.audit import models as audit_models


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.AMOAsset.__table__,
            account_models.Department.__table__,
            account_models.User.__table__,
            account_models.AuthorisationType.__table__,
            account_models.UserAuthorisation.__table__,
            account_models.AccountSecurityEvent.__table__,
            account_models.IdempotencyKey.__table__,
            crs_models.CRS.__table__,
            crs_models.CRSSignoff.__table__,
            maintenance_models.AmpProgramItem.__table__,
            maintenance_models.AmpAircraftProgramItem.__table__,
            audit_models.AuditEvent.__table__,
            finance_models.Currency.__table__,
            finance_models.TaxCode.__table__,
            finance_models.Customer.__table__,
            finance_models.Vendor.__table__,
            finance_models.GLAccount.__table__,
            finance_models.Invoice.__table__,
            finance_models.InvoiceLine.__table__,
            finance_models.CreditNote.__table__,
            finance_models.Payment.__table__,
            finance_models.PaymentAllocation.__table__,
            finance_models.JournalEntry.__table__,
            finance_models.JournalLine.__table__,
            finance_models.AccountingPeriod.__table__,
        ],
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _create_amo(db):
    amo = account_models.AMO(
        amo_code="AMO-FIN",
        name="Finance AMO",
        login_slug="fin",
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _create_user(db, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="finance@example.com",
        staff_code="FIN-1",
        first_name="Fin",
        last_name="User",
        full_name="Fin User",
        hashed_password="hash",
        role=account_models.AccountRole.FINANCE_MANAGER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_invoice_finalize_posts_balanced_journal(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)

    finance_services.ensure_finance_defaults(db_session, amo_id=amo.id)
    customer = finance_models.Customer(
        amo_id=amo.id,
        code="CUST-1",
        name="Customer",
        currency="USD",
        is_active=True,
    )
    db_session.add(customer)
    db_session.commit()

    payload = finance_schemas.InvoiceCreate(
        invoice_number="INV-1",
        customer_id=customer.id,
        currency="USD",
        issued_date=date.today(),
        due_date=date.today(),
        lines=[
            finance_schemas.InvoiceLineCreate(
                description="Labour",
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
            )
        ],
        idempotency_key="inv-1",
    )
    invoice = finance_services.create_invoice(
        db_session,
        amo_id=amo.id,
        payload=payload,
        actor_user_id=user.id,
    )
    finance_services.finalize_invoice(
        db_session,
        amo_id=amo.id,
        invoice_id=invoice.id,
        actor_user_id=user.id,
    )
    db_session.commit()

    entry = db_session.query(finance_models.JournalEntry).first()
    assert entry is not None
    debit = sum(Decimal(line.debit) for line in entry.lines)
    credit = sum(Decimal(line.credit) for line in entry.lines)
    assert debit == credit


def test_journal_reversal_creates_offsetting_entry(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)
    finance_services.ensure_finance_defaults(db_session, amo_id=amo.id)

    cash = db_session.query(finance_models.GLAccount).filter_by(amo_id=amo.id, code="1000").first()
    revenue = db_session.query(finance_models.GLAccount).filter_by(amo_id=amo.id, code="4000").first()

    entry = finance_services.create_journal(
        db_session,
        amo_id=amo.id,
        payload=finance_schemas.JournalCreate(
            description="Manual",
            entry_date=date.today(),
            lines=[
                finance_schemas.JournalLineCreate(gl_account_id=cash.id, debit=Decimal("50"), credit=Decimal("0")),
                finance_schemas.JournalLineCreate(gl_account_id=revenue.id, debit=Decimal("0"), credit=Decimal("50")),
            ],
            post=True,
        ),
        actor_user_id=user.id,
    )
    db_session.commit()

    reversal = finance_services.reverse_journal_entry(
        db_session,
        amo_id=amo.id,
        journal_entry_id=entry.id,
        actor_user_id=user.id,
    )
    db_session.commit()

    debit = sum(Decimal(line.debit) for line in reversal.lines)
    credit = sum(Decimal(line.credit) for line in reversal.lines)
    assert debit == credit
    assert reversal.reversal_of_id == entry.id
    assert entry.status == finance_models.JournalStatusEnum.REVERSED
