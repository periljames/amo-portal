from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.crs import models as crs_models
from amodb.apps.maintenance_program import models as maintenance_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.reliability import models as reliability_models
from amodb.apps.reliability import schemas as reliability_schemas
from amodb.apps.reliability import services as reliability_services


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
            crs_models.CRS.__table__,
            crs_models.CRSSignoff.__table__,
            maintenance_models.AmpProgramItem.__table__,
            maintenance_models.AmpAircraftProgramItem.__table__,
            fleet_models.Aircraft.__table__,
            fleet_models.AircraftComponent.__table__,
            reliability_models.PartMovementLedger.__table__,
            reliability_models.RemovalEvent.__table__,
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
        amo_code="AMO-REL",
        name="Reliability AMO",
        login_slug="rel",
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _create_user(db, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="eng@example.com",
        staff_code="ENG-1",
        first_name="Eng",
        last_name="User",
        full_name="Eng User",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_removal_requires_tracking_id(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)

    aircraft = fleet_models.Aircraft(
        serial_number="SN-100",
        registration="REG-100",
        amo_id=amo.id,
    )
    component = fleet_models.AircraftComponent(
        amo_id=amo.id,
        aircraft_serial_number=aircraft.serial_number,
        position="L ENG",
        part_number="PN-1",
        serial_number="SN-1",
        is_installed=True,
    )
    db_session.add_all([aircraft, component])
    db_session.commit()

    payload = reliability_schemas.PartMovementLedgerCreate(
        aircraft_serial_number=aircraft.serial_number,
        component_id=component.id,
        event_type=reliability_schemas.PartMovementTypeEnum.REMOVE,
        event_date=date.today(),
        notes="Removal",
    )

    with pytest.raises(HTTPException):
        reliability_services.create_part_movement(
            db_session,
            amo_id=amo.id,
            data=payload,
            removal_tracking_id=None,
            actor_user_id=user.id,
        )
