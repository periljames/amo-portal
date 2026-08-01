from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import commercial_services

commercial_router = importlib.import_module("amodb.apps.platform.commercial_router")
phase4_router = importlib.import_module("amodb.apps.platform.phase4_router")
phase4_api_key_router = importlib.import_module("amodb.apps.platform.phase4_api_key_router")


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


def test_phase4_routes_expose_security_support_and_webhook_controls():
    paths = {route.path for route in phase4_router.router.routes}
    assert "/phase4/security/alerts" in paths
    assert "/phase4/security/alerts/{alert_id}/resolve" in paths
    assert "/phase4/security/audit" in paths
    assert "/phase4/webhooks/{webhook_id}/deliveries" in paths
    assert "/phase4/infrastructure/capabilities" in paths
    assert "/phase4/tenants/{tenant_id}/support-sessions" in paths


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
    surfaces = [
        repository_root / "frontend" / "src" / "pages" / "platform" / "PlatformTenantsPage.tsx",
        repository_root / "frontend" / "src" / "pages" / "platform" / "PlatformBillingPage.tsx",
        repository_root / "frontend" / "src" / "pages" / "platform" / "PlatformSecurityPage.tsx",
        repository_root / "frontend" / "src" / "pages" / "platform" / "PlatformIntegrationsPage.tsx",
        repository_root / "frontend" / "src" / "services" / "commercialControl.ts",
        repository_root / "frontend" / "src" / "services" / "platformPhase4.ts",
    ]

    for path in surfaces:
        source = path.read_text(encoding="utf-8")
        assert 'value="ALL"' not in source
        assert '"REAL", "DEMO"' in source or "PlatformDataMode" in source


def test_migration_has_database_check_for_data_mode():
    repository_root = Path(__file__).resolve().parents[5]
    migration = repository_root / "backend" / "amodb" / "alembic" / "versions" / "plat_20260801_commercial_control.py"
    source = migration.read_text(encoding="utf-8")
    assert "data_mode IN ('REAL','DEMO')" in source
    assert 'down_revision: Union[str, Sequence[str], None] = "saas_20260731_route_latency_hist"' in source


def test_phase4_infrastructure_disables_unimplemented_failover():
    payload = phase4_router.infrastructure_capabilities(user=SimpleNamespace(id="root"))
    assert payload["database_failover"]["available"] is False
    assert "No safe runtime implementation" in payload["database_failover"]["reason"]


def test_phase4_source_uses_normal_timedelta_and_explicit_environment_scope():
    repository_root = Path(__file__).resolve().parents[5]
    source = (repository_root / "backend" / "amodb" / "apps" / "platform" / "phase4_router.py").read_text(encoding="utf-8")
    assert "from datetime import datetime, timedelta, timezone" in source
    assert '__import__("datetime").timedelta' not in source
    assert "data_mode: str = Query(\"REAL\")" in source
    assert "normalize_data_mode(data_mode)" in source


def test_commercial_integrity_covers_plan_changes_pricing_and_scheduled_cancellation():
    repository_root = Path(__file__).resolve().parents[5]
    source = (repository_root / "backend" / "amodb" / "apps" / "platform" / "commercial_integrity.py").read_text(encoding="utf-8")
    assert "_rebuild_subscription_items" in source
    assert "plan_price" in source
    assert "Scheduled cancellation reached the current period end" in source
    assert '_CURRENT_SUBSCRIPTION_STATUSES = services.ACTIVE_SUBSCRIPTION_STATUSES | {"DRAFT", "PAUSED"}' in source
    assert 'row.price_book_id = book.id if book else None' in source


def test_scheduled_cancellation_runs_on_a_write_session_lifecycle():
    repository_root = Path(__file__).resolve().parents[5]
    source = (repository_root / "backend" / "amodb" / "apps" / "platform" / "commercial_lifecycle.py").read_text(encoding="utf-8")
    assert "WriteSessionLocal" in source
    assert "commercial-subscription-lifecycle" in source
    assert "_apply_due_cancellations(db, commit=True)" in source


def test_canonical_api_key_route_persists_and_validates_expiry():
    source = Path(phase4_api_key_router.__file__).read_text(encoding="utf-8")
    assert '"/integrations/api-keys"' in source
    assert "expires_at=expires_at" in source
    assert "expires_at must be in the future" in source
    assert "install_canonical_api_key_create_route" in source
