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
from amodb.apps.reliability import models as reliability_models  # noqa: E402
from amodb.apps.reliability import services as reliability_services  # noqa: E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.crs import models as crs_models  # noqa: E402
from amodb.apps.maintenance_program import models as maintenance_models  # noqa: E402
from amodb.apps.fleet import models as fleet_models  # noqa: E402
from amodb.apps.quality import models as quality_models  # noqa: E402
from amodb.apps.work import models as work_models  # noqa: E402
from amodb.apps.reliability.schemas import DefectTrendCreate  # noqa: E402


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
            fleet_models.AircraftDocument.__table__,
            fleet_models.AircraftUsage.__table__,
            fleet_models.AircraftConfigurationEvent.__table__,
            fleet_models.DefectReport.__table__,
            fleet_models.MaintenanceProgramItem.__table__,
            fleet_models.MaintenanceStatus.__table__,
            work_models.WorkOrder.__table__,
            work_models.TaskCard.__table__,
            quality_models.QMSAuditFinding.__table__,
            reliability_models.ReliabilityDefectTrend.__table__,
            reliability_models.ReliabilityRecurringFinding.__table__,
            reliability_models.ReliabilityRecommendation.__table__,
        ],
    )
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
    amo = account_models.AMO(
        amo_code="AMO-TREND",
        name="Trend AMO",
        login_slug="trend",
    )
    db_session.add(amo)
    db_session.flush()
    aircraft = fleet_models.Aircraft(
        serial_number="AC-1",
        registration="5Y-AC1",
        amo_id=amo.id,
    )
    db_session.add(aircraft)
    wo = work_models.WorkOrder(
        wo_number="WO-1",
        aircraft_serial_number="AC-1",
        description="Test WO",
        amo_id=amo.id,
    )
    db_session.add(wo)
    db_session.flush()
    task = work_models.TaskCard(
        work_order_id=wo.id,
        aircraft_serial_number="AC-1",
        title="Defect card",
        ata_chapter="27-10",
        task_code="DEF-1",
        category=work_models.TaskCategoryEnum.DEFECT,
        origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
        created_at=date(2024, 1, 15),
        amo_id=amo.id,
    )
    db_session.add(task)
    wo_repeat = work_models.WorkOrder(
        wo_number="WO-2",
        aircraft_serial_number="AC-1",
        description="Repeat WO",
        amo_id=amo.id,
    )
    db_session.add(wo_repeat)
    db_session.flush()
    db_session.add(
        work_models.TaskCard(
            work_order_id=wo_repeat.id,
            aircraft_serial_number="AC-1",
            title="Defect repeat",
            ata_chapter="27-10",
            task_code="DEF-1",
            category=work_models.TaskCategoryEnum.DEFECT,
            origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
            created_at=date(2024, 1, 20),
            amo_id=amo.id,
        )
    )
    usage = fleet_models.AircraftUsage(
        aircraft_serial_number="AC-1",
        date=date(2024, 1, 15),
        techlog_no="TL1",
        block_hours=5.0,
        cycles=2,
        amo_id=amo.id,
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
    assert trend.defects_count == 2
    assert trend.repeat_defects == 1  # same defect categorised as non-routine counts as repeat
    assert trend.utilisation_hours == 5.0
