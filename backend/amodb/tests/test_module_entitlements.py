import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Tuple

import pytest
from fastapi import HTTPException, status

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/testdb")
sys.path.append(str(Path(__file__).resolve().parents[2]))

from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.accounts import schemas as account_schemas  # noqa: E402
from amodb.apps.accounts import services as account_services  # noqa: E402
from amodb import entitlements as entitlement_service  # noqa: E402
from amodb import security as security_service  # noqa: E402
from amodb.apps.fleet.router import router as fleet_router  # noqa: E402
from amodb.apps.maintenance_program.api import router as maintenance_router  # noqa: E402
from amodb.apps.quality.router import router as quality_router  # noqa: E402
from amodb.apps.reliability.router import router as reliability_router  # noqa: E402
from amodb.apps.training.router import router as training_router  # noqa: E402
from amodb.apps.work.router import router as work_router  # noqa: E402


def _make_entitlement(key: str) -> account_schemas.ResolvedEntitlement:
    return account_schemas.ResolvedEntitlement(
        key=key,
        is_unlimited=True,
        limit=None,
        source_license_id="license-1",
        license_term=account_models.BillingTerm.MONTHLY,
        license_status=account_models.LicenseStatus.ACTIVE,
    )


def _module_guards() -> Tuple[Tuple[str, object], ...]:
    return (
        ("quality", quality_router.dependencies[0].dependency),
        ("maintenance_program", maintenance_router.dependencies[0].dependency),
        ("fleet", fleet_router.dependencies[0].dependency),
        ("work", work_router.dependencies[0].dependency),
        ("training", training_router.dependencies[0].dependency),
        ("reliability", reliability_router.dependencies[0].dependency),
    )


def _allow_billing_and_defer_subscription_to_entitlements(monkeypatch) -> None:
    monkeypatch.setattr(
        account_services,
        "get_billing_access_status",
        lambda db, amo_id: SimpleNamespace(has_access=True, lock_reason=None),
    )
    monkeypatch.setattr(
        entitlement_service,
        "_has_module_subscription",
        lambda db, amo_id, module_key: None,
    )


def test_module_guard_blocks_without_entitlement(monkeypatch):
    _allow_billing_and_defer_subscription_to_entitlements(monkeypatch)
    monkeypatch.setattr(
        account_services,
        "resolve_entitlements",
        lambda db, amo_id, as_of=None: {},
    )
    stub_user = SimpleNamespace(amo_id="amo-1", is_superuser=False, is_active=True)

    for module_key, dependency in _module_guards():
        with pytest.raises(HTTPException) as exc:
            dependency(current_user=stub_user, db=SimpleNamespace(get=lambda *_: SimpleNamespace(is_active=True)))
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert module_key in str(exc.value.detail)


def test_module_guard_allows_with_entitlement(monkeypatch):
    _allow_billing_and_defer_subscription_to_entitlements(monkeypatch)
    entitlements: Dict[str, account_schemas.ResolvedEntitlement] = {
        key: _make_entitlement(key)
        for key, _ in _module_guards()
    }
    monkeypatch.setattr(
        account_services,
        "resolve_entitlements",
        lambda db, amo_id, as_of=None: entitlements,
    )
    stub_user = SimpleNamespace(amo_id="amo-1", is_superuser=False, is_active=True)

    for _, dependency in _module_guards():
        assert dependency(current_user=stub_user, db=SimpleNamespace(get=lambda *_: SimpleNamespace(is_active=True))) is stub_user



def test_standing_tenant_admin_cannot_bypass_commercial_license(monkeypatch):
    user = SimpleNamespace(amo_id="amo-1", is_superuser=False, is_active=True)
    monkeypatch.setattr(security_service, "is_tenant_admin", lambda u: True)

    def deny(*args, **kwargs):
        raise HTTPException(status_code=403, detail="No effective paid entitlement")

    monkeypatch.setattr(entitlement_service, "enforce_tenant_module", deny)
    with pytest.raises(HTTPException) as blocked:
        security_service.require_module_access("quality")(current_user=user, db=None)
    assert blocked.value.status_code == 403

    monkeypatch.setattr(entitlement_service, "enforce_tenant_module", lambda *args, **kwargs: None)
    assert security_service.require_module_access("quality")(current_user=user, db=None) is user


def test_shared_module_router_requires_at_least_one_licensed_module(monkeypatch):
    user = SimpleNamespace(amo_id="amo-1", is_superuser=False, is_active=True)
    monkeypatch.setattr(security_service, "is_tenant_admin", lambda u: True)

    def only_documents(db, *, amo_id, module_key):
        if module_key != "documents":
            raise HTTPException(status_code=403, detail="Unlicensed")

    monkeypatch.setattr(entitlement_service, "enforce_tenant_module", only_documents)
    guard = security_service.require_any_module_access("documents", "quality", level="manage")
    assert guard(current_user=user, db=None) is user
    monkeypatch.setattr(entitlement_service, "enforce_tenant_module", lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(403, "Unlicensed")))
    with pytest.raises(HTTPException):
        guard(current_user=user, db=None)
