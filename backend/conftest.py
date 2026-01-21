from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DATABASE_WRITE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["AMODB_SKIP_MODEL_IMPORTS"] = "1"

from amodb.database import Base  # noqa: E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.crs import models as crs_models  # noqa: E402
from amodb.apps.fleet import models as fleet_models  # noqa: E402
from amodb.apps.work import models as work_models  # noqa: E402
from amodb.apps.reliability import models as reliability_models  # noqa: E402
from amodb.apps.audit import models as audit_models  # noqa: E402
from amodb.apps.integrations import models as integration_models  # noqa: E402
from amodb.apps.maintenance_program import models as maintenance_program_models  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.User.__table__,
            account_models.IdempotencyKey.__table__,
            account_models.UserActiveContext.__table__,
            fleet_models.Aircraft.__table__,
            fleet_models.AircraftComponent.__table__,
            fleet_models.AircraftUsage.__table__,
            fleet_models.AircraftConfigurationEvent.__table__,
            fleet_models.DefectReport.__table__,
            work_models.WorkOrder.__table__,
            work_models.TaskCard.__table__,
            work_models.TaskAssignment.__table__,
            work_models.WorkLogEntry.__table__,
            work_models.TaskStep.__table__,
            work_models.TaskStepExecution.__table__,
            work_models.InspectorSignOff.__table__,
            maintenance_program_models.AmpProgramItem.__table__,
            maintenance_program_models.AmpAircraftProgramItem.__table__,
            reliability_models.PartMovementLedger.__table__,
            reliability_models.RemovalEvent.__table__,
            audit_models.AuditEvent.__table__,
            integration_models.IntegrationConfig.__table__,
            integration_models.IntegrationOutboundEvent.__table__,
            integration_models.IntegrationInboundEvent.__table__,
        ],
    )
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
