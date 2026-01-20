from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.crs import models as crs_models
from amodb.apps.maintenance_program import models as maintenance_models
from amodb.entitlements import require_module


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
            account_models.ModuleSubscription.__table__,
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
        amo_code="AMO-MOD",
        name="Module AMO",
        login_slug="mod",
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _create_user(db, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="admin@example.com",
        staff_code="ADM-1",
        first_name="Admin",
        last_name="User",
        full_name="Admin User",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_module_subscription_blocks_access(db_session):
    amo = _create_amo(db_session)
    user = _create_user(db_session, amo.id)

    subscription = account_models.ModuleSubscription(
        amo_id=amo.id,
        module_code="finance_inventory",
        status=account_models.ModuleSubscriptionStatus.DISABLED,
    )
    db_session.add(subscription)
    db_session.commit()

    dependency = require_module("finance_inventory")
    with pytest.raises(HTTPException):
        dependency(current_user=user, db=db_session)

    subscription.status = account_models.ModuleSubscriptionStatus.ENABLED
    db_session.add(subscription)
    db_session.commit()

    assert dependency(current_user=user, db=db_session) == user
