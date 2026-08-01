from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import commercial_router, commercial_services


def test_data_mode_accepts_only_real_or_demo():
    assert commercial_services.normalize_data_mode("REAL") == "REAL"
    assert commercial_services.normalize_data_mode("live") == "REAL"
    assert commercial_services.normalize_data_mode("demo") == "DEMO"
    with pytest.raises(ValueError, match="REAL or DEMO"):
        commercial_services.normalize_data_mode("ALL")
    with pytest.raises(ValueError, match="REAL or DEMO"):
        commercial_services.normalize_data_mode("anything")


def test_commercial_router_exposes_explicit_data_mode_contract():
    paths = {route.path for route in commercial_router.router.routes}
    assert "/commercial/data-modes" in paths
    assert "/commercial/tenants/provision" in paths
    assert "/commercial/subscriptions/{subscription_id}/reconcile" in paths
    assert "/commercial/invoices/{invoice_id}/payments" in paths


def test_period_end_is_term_specific_and_one_time_has_no_renewal():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert (commercial_services.period_end(start, "MONTHLY") - start).days == 30
    assert (commercial_services.period_end(start, "BI_ANNUAL") - start).days == 182
    assert (commercial_services.period_end(start, "ANNUAL") - start).days == 365
    assert commercial_services.period_end(start, "ONE_TIME") is None


def test_force_password_reset_persists_flag_and_revokes_sessions(monkeypatch: pytest.MonkeyPatch):
    user = SimpleNamespace(
        id="user-1",
        amo_id="amo-1",
        email="admin@example.test",
        must_change_password=False,
        token_revoked_at=None,
        password_changed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.get.return_value = user
    monkeypatch.setattr(commercial_services, "audit", MagicMock())

    result = commercial_services.force_password_reset(
        db,
        user_id="user-1",
        actor_user_id="root-1",
        reason="Security reset",
    )

    assert result["must_change_password"] is True
    assert user.must_change_password is True
    assert user.token_revoked_at is not None
    assert user.password_changed_at is None
    db.commit.assert_called_once()


def test_legacy_projection_maps_canonical_states_safely():
    assert commercial_services.legacy_status("ACTIVE") == account_models.LicenseStatus.ACTIVE
    assert commercial_services.legacy_status("TRIALING") == account_models.LicenseStatus.TRIALING
    assert commercial_services.legacy_status("PAST_DUE") == account_models.LicenseStatus.EXPIRED
    assert commercial_services.legacy_term("ANNUAL") == account_models.BillingTerm.ANNUAL
    assert commercial_services.legacy_term("BI_ANNUAL") == account_models.BillingTerm.BI_ANNUAL
    assert commercial_services.legacy_term("ONE_TIME") == account_models.BillingTerm.MONTHLY


def test_platform_console_never_offers_all_data_mode():
    repository_root = Path(__file__).resolve().parents[5]
    tenant_page = repository_root / "frontend" / "src" / "pages" / "platform" / "PlatformTenantsPage.tsx"
    billing_page = repository_root / "frontend" / "src" / "pages" / "platform" / "PlatformBillingPage.tsx"
    commercial_service = repository_root / "frontend" / "src" / "services" / "commercialControl.ts"

    for path in (tenant_page, billing_page, commercial_service):
        source = path.read_text(encoding="utf-8")
        assert 'value="ALL"' not in source
        assert '"REAL", "DEMO"' in source


def test_migration_has_database_check_for_data_mode():
    repository_root = Path(__file__).resolve().parents[5]
    migration = repository_root / "backend" / "amodb" / "alembic" / "versions" / "plat_20260801_commercial_control.py"
    source = migration.read_text(encoding="utf-8")
    assert "data_mode IN ('REAL','DEMO')" in source
    assert 'down_revision: Union[str, Sequence[str], None] = "saas_20260731_route_latency_hist"' in source
