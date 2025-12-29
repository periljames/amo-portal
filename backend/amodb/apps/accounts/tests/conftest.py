from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configure a disposable database URL before importing the application Base.
# We do not connect to this engine in tests; it only satisfies module import.
os.environ["DATABASE_URL"] = "postgresql+psycopg2://test:test@localhost:5432/testdb"

from amodb.database import Base  # noqa: E402
from amodb.apps.accounts import models  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            models.AMO.__table__,
            models.CatalogSKU.__table__,
            models.TenantLicense.__table__,
            models.LicenseEntitlement.__table__,
            models.UsageMeter.__table__,
            models.LedgerEntry.__table__,
            models.PaymentMethod.__table__,
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
