from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from amodb.apps.accounts import models, services


def _create_amo(session, *, code: str = "AMO1") -> models.AMO:
    amo = models.AMO(
        amo_code=code,
        name="Test AMO",
        login_slug=f"{code.lower()}-login",
    )
    session.add(amo)
    session.commit()
    return amo


def _create_sku(session, *, code: str, term: models.BillingTerm) -> models.CatalogSKU:
    sku = models.CatalogSKU(
        code=code,
        name=f"{code} Plan",
        term=term,
        trial_days=14,
        amount_cents=2500,
        currency="USD",
    )
    session.add(sku)
    session.commit()
    return sku


def _create_license(
    session,
    *,
    amo_id: str,
    sku: models.CatalogSKU,
    status: models.LicenseStatus,
    term: models.BillingTerm,
    trial_extra_days: int = 0,
) -> models.TenantLicense:
    now = datetime.now(timezone.utc)
    license = models.TenantLicense(
        amo_id=amo_id,
        sku_id=sku.id,
        status=status,
        term=term,
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=30),
        trial_ends_at=now + timedelta(days=trial_extra_days),
    )
    session.add(license)
    session.commit()
    return license


def test_resolve_entitlements_picks_unlimited_first(db_session):
    amo = _create_amo(db_session)
    sku_monthly = _create_sku(db_session, code="BASE-M", term=models.BillingTerm.MONTHLY)
    sku_annual = _create_sku(db_session, code="BASE-A", term=models.BillingTerm.ANNUAL)

    limited_license = _create_license(
        db_session,
        amo_id=amo.id,
        sku=sku_monthly,
        status=models.LicenseStatus.ACTIVE,
        term=models.BillingTerm.MONTHLY,
    )
    unlimited_license = _create_license(
        db_session,
        amo_id=amo.id,
        sku=sku_annual,
        status=models.LicenseStatus.TRIALING,
        term=models.BillingTerm.ANNUAL,
        trial_extra_days=10,
    )

    db_session.add_all(
        [
            models.LicenseEntitlement(
                license_id=limited_license.id,
                key="seats",
                limit=5,
                is_unlimited=False,
            ),
            models.LicenseEntitlement(
                license_id=limited_license.id,
                key="storage_gb",
                limit=50,
            ),
            models.LicenseEntitlement(
                license_id=unlimited_license.id,
                key="seats",
                is_unlimited=True,
            ),
        ]
    )
    db_session.commit()

    resolved = services.resolve_entitlements(db_session, amo_id=amo.id)
    assert resolved["seats"].is_unlimited is True
    assert resolved["seats"].license_term == models.BillingTerm.ANNUAL
    assert resolved["storage_gb"].limit == 50
    assert resolved["storage_gb"].license_status == models.LicenseStatus.ACTIVE


def test_append_ledger_entry_enforces_idempotency(db_session):
    amo = _create_amo(db_session, code="AMO2")
    entry = services.append_ledger_entry(
        db_session,
        amo_id=amo.id,
        amount_cents=1000,
        currency="USD",
        entry_type=models.LedgerEntryType.CHARGE,
        description="Initial charge",
        idempotency_key="charge-001",
    )

    duplicate = services.append_ledger_entry(
        db_session,
        amo_id=amo.id,
        amount_cents=1000,
        currency="USD",
        entry_type=models.LedgerEntryType.CHARGE,
        description="Should reuse existing",
        idempotency_key="charge-001",
    )

    assert entry.id == duplicate.id
    assert db_session.query(models.LedgerEntry).count() == 1

    with pytest.raises(services.IdempotencyError):
        services.append_ledger_entry(
            db_session,
            amo_id=amo.id,
            amount_cents=1500,
            currency="USD",
            entry_type=models.LedgerEntryType.CHARGE,
            description="Conflicting payload",
            idempotency_key="charge-001",
        )
