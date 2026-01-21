from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from amodb.database import Base
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.accounts import router_admin
from amodb.apps.audit import models as audit_models
from amodb.apps.audit import router as audit_router


def _setup_db():
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
            account_models.UserActiveContext.__table__,
            audit_models.AuditEvent.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return SessionLocal


def _create_user(db, *, amo_id: str, email: str, is_superuser: bool) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email=email,
        staff_code=email.split("@")[0].upper(),
        first_name="User",
        last_name="Test",
        full_name="User Test",
        hashed_password="hash",
        role=account_models.AccountRole.SUPERUSER if is_superuser else account_models.AccountRole.AMO_ADMIN,
        is_active=True,
        is_superuser=is_superuser,
        is_amo_admin=not is_superuser,
    )
    db.add(user)
    db.commit()
    return user


def _create_audit_event(db, *, amo_id: str, entity_id: str):
    event = audit_models.AuditEvent(
        amo_id=amo_id,
        entity_type="Test",
        entity_id=entity_id,
        action="create",
    )
    db.add(event)
    db.commit()
    return event


def test_context_superuser_only():
    SessionLocal = _setup_db()
    db = SessionLocal()

    amo = account_models.AMO(
        amo_code="AMO-REAL",
        name="Real AMO",
        login_slug="real",
    )
    db.add(amo)
    db.commit()

    user = _create_user(db, amo_id=amo.id, email="admin@example.com", is_superuser=False)

    with pytest.raises(HTTPException):
        router_admin.get_admin_context(db=db, current_user=user)

    with pytest.raises(HTTPException):
        router_admin.set_admin_context(
            payload=account_schemas.UserActiveContextUpdate(data_mode=account_models.DataMode.REAL),
            db=db,
            current_user=user,
        )

    db.close()


def test_demo_real_isolation_by_tenant():
    SessionLocal = _setup_db()
    db = SessionLocal()

    real_amo = account_models.AMO(
        amo_code="AMO-REAL",
        name="Real AMO",
        login_slug="real",
        is_demo=False,
    )
    demo_amo = account_models.AMO(
        amo_code="AMO-DEMO",
        name="Demo AMO",
        login_slug="demo",
        is_demo=True,
    )
    db.add_all([real_amo, demo_amo])
    db.commit()

    superuser = _create_user(db, amo_id=real_amo.id, email="root@example.com", is_superuser=True)

    _create_audit_event(db, amo_id=real_amo.id, entity_id="REAL-1")
    _create_audit_event(db, amo_id=demo_amo.id, entity_id="DEMO-1")

    account_services.set_user_active_context(
        db,
        user=superuser,
        data_mode=account_models.DataMode.DEMO,
        active_amo_id=demo_amo.id,
    )
    db.commit()

    effective_user = get_current_active_user(current_user=superuser, db=db)
    demo_list = audit_router.list_audit_events(db=db, current_user=effective_user)
    assert {item.entity_id for item in demo_list} == {"DEMO-1"}

    account_services.set_user_active_context(
        db,
        user=superuser,
        data_mode=account_models.DataMode.REAL,
        active_amo_id=real_amo.id,
    )
    db.commit()

    effective_user = get_current_active_user(current_user=superuser, db=db)
    real_list = audit_router.list_audit_events(db=db, current_user=effective_user)
    assert {item.entity_id for item in real_list} == {"REAL-1"}

    db.close()


def test_context_persists():
    SessionLocal = _setup_db()
    db = SessionLocal()

    real_amo = account_models.AMO(
        amo_code="AMO-REAL",
        name="Real AMO",
        login_slug="real",
        is_demo=False,
    )
    demo_amo = account_models.AMO(
        amo_code="AMO-DEMO",
        name="Demo AMO",
        login_slug="demo",
        is_demo=True,
    )
    db.add_all([real_amo, demo_amo])
    db.commit()

    superuser = _create_user(db, amo_id=real_amo.id, email="root@example.com", is_superuser=True)

    account_services.set_user_active_context(
        db,
        user=superuser,
        data_mode=account_models.DataMode.DEMO,
        active_amo_id=demo_amo.id,
    )
    db.commit()

    superuser = db.query(account_models.User).filter_by(id=superuser.id).first()
    effective_user = get_current_active_user(current_user=superuser, db=db)
    assert effective_user.amo_id == demo_amo.id

    db.close()
