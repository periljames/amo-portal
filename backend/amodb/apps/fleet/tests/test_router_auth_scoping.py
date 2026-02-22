from __future__ import annotations

from datetime import date, timedelta
import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.fleet import router as fleet_router
from amodb.apps.work import models as work_models


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
            fleet_models.Aircraft.__table__,
            work_models.WorkOrder.__table__,
            fleet_models.AircraftDocument.__table__,
        ],
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()


def _create_amo(db, code: str, slug: str) -> account_models.AMO:
    amo = account_models.AMO(amo_code=code, name=code, login_slug=slug)
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _create_aircraft(db, *, amo_id: str, serial: str, reg: str) -> fleet_models.Aircraft:
    aircraft = fleet_models.Aircraft(amo_id=amo_id, serial_number=serial, registration=reg)
    db.add(aircraft)
    db.commit()
    db.refresh(aircraft)
    return aircraft


def _create_doc(db, *, serial: str) -> fleet_models.AircraftDocument:
    doc = fleet_models.AircraftDocument(
        aircraft_serial_number=serial,
        document_type=fleet_models.AircraftDocumentType.CERTIFICATE_OF_AIRWORTHINESS,
        authority=account_models.RegulatoryAuthority.KCAA,
        issued_on=date.today() - timedelta(days=300),
        expires_on=date.today() + timedelta(days=10),
        alert_window_days=30,
        status=fleet_models.AircraftDocumentStatus.CURRENT,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_list_aircraft_uses_effective_amo_id_scope():
    src = inspect.getsource(fleet_router.list_aircraft)
    assert "current_user.effective_amo_id" in src


def test_document_alerts_impl_filters_by_amo_in_query_source():
    src = inspect.getsource(fleet_router._list_document_alerts_impl)
    assert ".join(models.Aircraft)" in src
    assert "models.Aircraft.amo_id == amo_id" in src


def test_router_registers_static_document_alerts_and_slash_safe_collection_routes():
    route_defs = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in fleet_router.router.routes
    }

    assert ("/aircraft/document-alerts", ("GET",)) in route_defs
    assert ("/aircraft/document-alerts/", ("GET",)) in route_defs
    assert ("/aircraft", ("GET",)) in route_defs
    assert ("/aircraft/", ("GET",)) in route_defs
    assert ("/aircraft", ("POST",)) in route_defs
    assert ("/aircraft/", ("POST",)) in route_defs
