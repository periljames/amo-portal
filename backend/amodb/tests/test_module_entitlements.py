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


def test_module_guard_blocks_without_entitlement(monkeypatch):
    monkeypatch.setattr(
        account_services,
        "resolve_entitlements",
        lambda db, amo_id, as_of=None: {},
    )
    stub_user = SimpleNamespace(amo_id="amo-1", is_superuser=False, is_active=True)

    for module_key, dependency in _module_guards():
        with pytest.raises(HTTPException) as exc:
            dependency(current_user=stub_user, db=None)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert module_key in str(exc.value.detail)


def test_module_guard_allows_with_entitlement(monkeypatch):
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
        assert dependency(current_user=stub_user, db=None) is stub_user
