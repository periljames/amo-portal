from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "postgresql+psycopg2://test:test@localhost:5432/testdb"
sys.path.append(str(Path(__file__).resolve().parents[3]))

from amodb.database import Base  # noqa: E402
from amodb.apps.reliability.router import router as reliability_router  # noqa: E402
from amodb.apps.reliability import services as reliability_services  # noqa: E402
from amodb.apps.fleet import models as fleet_models  # noqa: E402
from amodb.apps.work import models as work_models  # noqa: E402
from amodb.apps.reliability.schemas import DefectTrendCreate  # noqa: E402


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_router_has_expected_routes():
    def _has_post(path: str) -> bool:
        return any(route.path == path and "POST" in (route.methods or []) for route in reliability_router.routes)

    assert _has_post("/reliability/templates/seed")
    assert _has_post("/reliability/trends")
    assert _has_post("/reliability/recurring")
    assert _has_post("/reliability/recommendations")


def test_compute_trend_basic(db_session):
    # Seed basic utilisation and a defect card
    aircraft = fleet_models.Aircraft(serial_number="AC-1", registration="5Y-AC1")
    db_session.add(aircraft)
    wo = work_models.WorkOrder(wo_number="WO-1", aircraft_serial_number="AC-1", description="Test WO")
    db_session.add(wo)
    db_session.flush()
    task = work_models.TaskCard(
        work_order_id=wo.id,
        aircraft_serial_number="AC-1",
        title="Defect card",
        category=work_models.TaskCategoryEnum.DEFECT,
        origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
        created_at=date(2024, 1, 15),
    )
    db_session.add(task)
    usage = fleet_models.AircraftUsage(
        aircraft_serial_number="AC-1",
        date=date(2024, 1, 15),
        techlog_no="TL1",
        block_hours=5.0,
        cycles=2,
    )
    db_session.add(usage)
    db_session.commit()

    payload = DefectTrendCreate(window_start=date(2024, 1, 1), window_end=date(2024, 1, 31))
    trend = reliability_services.compute_defect_trend(
        db_session,
        amo_id="amo-1",
        window_start=payload.window_start,
        window_end=payload.window_end,
        aircraft_serial_number=payload.aircraft_serial_number,
        ata_chapter=payload.ata_chapter,
    )
    assert trend.defects_count == 1
    assert trend.repeat_defects == 1  # same defect categorised as non-routine counts as repeat
    assert trend.utilisation_hours == 5.0
