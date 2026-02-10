from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configure a disposable database URL before importing the application Base.
# We do not connect to this engine in tests; it only satisfies module import.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DATABASE_WRITE_URL"] = "sqlite+pysqlite:///:memory:"

from amodb.database import Base  # noqa: E402
from amodb.apps.accounts import models  # noqa: E402
from amodb.apps.audit import models as audit_models  # noqa: E402
from amodb.apps.tasks import models as task_models  # noqa: E402
from amodb.apps.notifications import models as notification_models  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            models.AMO.__table__,
            models.AMOAsset.__table__,
            models.Department.__table__,
            models.User.__table__,
            models.UserActiveContext.__table__,
            models.AuthorisationType.__table__,
            models.UserAuthorisation.__table__,
            models.AccountSecurityEvent.__table__,
            models.CatalogSKU.__table__,
            models.TenantLicense.__table__,
            models.LicenseEntitlement.__table__,
            models.UsageMeter.__table__,
            models.LedgerEntry.__table__,
            models.PaymentMethod.__table__,
            models.IdempotencyKey.__table__,
            models.BillingInvoice.__table__,
            models.BillingAuditLog.__table__,
            models.WebhookEvent.__table__,
            audit_models.AuditEvent.__table__,
            task_models.Task.__table__,
            notification_models.EmailLog.__table__,
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
