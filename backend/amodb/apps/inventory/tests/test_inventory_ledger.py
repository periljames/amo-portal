from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.inventory import models as inventory_models
from amodb.apps.crs import models as crs_models
from amodb.apps.maintenance_program import models as maintenance_models
from amodb.apps.inventory import services as inventory_services
from amodb.apps.inventory import schemas as inventory_schemas
from amodb.apps.finance import models as finance_models
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
            inventory_models.InventoryPart.__table__,
            inventory_models.InventoryLocation.__table__,
            inventory_models.InventoryLot.__table__,
            inventory_models.InventorySerial.__table__,
            inventory_models.InventoryMovementLedger.__table__,
            finance_models.GLAccount.__table__,
            finance_models.TaxCode.__table__,
            finance_models.Currency.__table__,
            finance_models.JournalEntry.__table__,
            finance_models.JournalLine.__table__,
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
        amo_code="AMO-INV",
        name="Inventory AMO",
        login_slug="inv",
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _create_user(db, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="store@example.com",
        staff_code="ST-1",
        first_name="Store",
        last_name="Keeper",
        full_name="Store Keeper",
        hashed_password="hash",
        role=account_models.AccountRole.STOREKEEPER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_on_hand_derived_from_ledger(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)
    part = inventory_models.InventoryPart(
        amo_id=amo.id,
        part_number="PN-100",
        description="Test Part",
        uom="EA",
        is_serialized=False,
        is_lot_controlled=False,
    )
    location = inventory_models.InventoryLocation(
        amo_id=amo.id,
        code="MAIN",
        name="Main Store",
        is_active=True,
    )
    db_session.add_all([part, location])
    db_session.commit()

    receive_payload = inventory_schemas.InventoryReceiveRequest(
        part_number="PN-100",
        quantity=5,
        uom="EA",
        to_location_id=location.id,
        idempotency_key="recv-1",
        is_serialized=False,
        is_lot_controlled=False,
    )
    inventory_services.receive_inventory(
        db_session,
        amo_id=amo.id,
        payload=receive_payload,
        actor_user_id=user.id,
    )

    issue_payload = inventory_schemas.InventoryIssueRequest(
        part_number="PN-100",
        quantity=2,
        uom="EA",
        from_location_id=location.id,
        idempotency_key="issue-1",
    )
    inventory_services.issue_inventory(
        db_session,
        amo_id=amo.id,
        payload=issue_payload,
        actor_user_id=user.id,
    )

    db_session.commit()

    on_hand = inventory_services.list_on_hand(db_session, amo_id=amo.id, part_number="PN-100")
    assert len(on_hand) == 1
    assert on_hand[0].quantity == 3
