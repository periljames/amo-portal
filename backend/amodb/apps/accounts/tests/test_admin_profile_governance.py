from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from amodb.apps.accounts import admin_profile_router as profile_router
from amodb.apps.accounts import department_home_router as home_router
from amodb.apps.accounts.admin_profile_concurrency import serialized_approval_count
from amodb.apps.accounts.admin_profile_guard import require_active_admin_profile
from amodb.apps.accounts.admin_profile_router import (
    REQUIRED_SCHEMA_TABLES,
    _as_utc,
    _assert_tenant_member,
    _ensure_schema,
    _is_implicit_admin,
    _is_management_approver,
)
from amodb.apps.accounts.router_admin import router as protected_admin_router


def actor(**overrides):
    values = {
        "id": "user-1",
        "amo_id": "amo-a",
        "effective_amo_id": "amo-a",
        "is_superuser": False,
        "is_amo_admin": False,
        "role": "QUALITY_MANAGER",
        "position_title": "Quality Manager",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def request(path: str):
    return SimpleNamespace(url=SimpleNamespace(path=path))


def test_admin_profile_rejects_cross_tenant_actor() -> None:
    with pytest.raises(HTTPException) as exc:
        _assert_tenant_member(actor(amo_id="amo-a", effective_amo_id="amo-a"), SimpleNamespace(id="amo-b"))
    assert exc.value.status_code == 403
    assert "not a member" in str(exc.value.detail).lower()


def test_platform_superuser_cannot_become_tenant_admin_profile() -> None:
    with pytest.raises(HTTPException) as exc:
        _assert_tenant_member(actor(is_superuser=True), SimpleNamespace(id="amo-a"))
    assert exc.value.status_code == 403
    assert "support-session" in str(exc.value.detail).lower()


def test_existing_admin_and_governance_approver_rules() -> None:
    assert _is_implicit_admin(actor(role="AMO_ADMIN", is_amo_admin=True)) is True
    assert _is_implicit_admin(actor(role="QUALITY_MANAGER", is_amo_admin=False)) is False
    assert _is_management_approver(actor(role="QUALITY_MANAGER")) is True
    assert _is_management_approver(actor(role="VIEW_ONLY", position_title="Accountable Manager")) is True
    assert _is_management_approver(actor(role="VIEW_ONLY", position_title="HR Manager")) is True
    assert _is_management_approver(actor(role="TECHNICIAN", position_title="Technician")) is False


def test_naive_and_aware_grant_datetimes_are_normalised_to_utc() -> None:
    naive = datetime(2026, 8, 3, 10, 0, 0)
    aware = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    assert _as_utc(naive).tzinfo == timezone.utc
    assert _as_utc(aware) == aware


def test_accounts_package_preserves_router_modules_for_monkeypatching() -> None:
    assert hasattr(profile_router, "inspect")
    assert hasattr(profile_router, "router")
    assert hasattr(home_router, "_admin_profile_active")
    assert hasattr(home_router, "router")


def test_admin_profile_schema_check_accepts_migrated_tables_without_runtime_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    inspector = SimpleNamespace(get_table_names=lambda: sorted(REQUIRED_SCHEMA_TABLES))
    monkeypatch.setattr(profile_router, "inspect", lambda _bind: inspector)

    _ensure_schema(db)

    db.get_bind.assert_called_once_with()
    db.execute.assert_not_called()


def test_admin_profile_schema_check_fails_closed_when_migration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    inspector = SimpleNamespace(get_table_names=lambda: ["users", "amos"])
    monkeypatch.setattr(profile_router, "inspect", lambda _bind: inspector)

    with pytest.raises(HTTPException) as exc:
        _ensure_schema(db)

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "ADMIN_PROFILE_SCHEMA_NOT_MIGRATED"
    assert sorted(exc.value.detail["missing_tables"]) == sorted(REQUIRED_SCHEMA_TABLES)
    db.execute.assert_not_called()


def test_all_registered_tenant_admin_routes_have_profile_dependency() -> None:
    normal_routes = [
        route
        for route in protected_admin_router.routes
        if isinstance(route, APIRoute) and "/admin-profile/" not in route.path
    ]
    assert normal_routes
    unprotected = [
        route.path
        for route in normal_routes
        if require_active_admin_profile not in {
            dependency.call for dependency in route.dependant.dependencies
        }
    ]
    assert unprotected == []


def test_profile_governance_routes_are_the_only_tenant_admin_exemption() -> None:
    db = MagicMock()
    current = actor(role="AMO_ADMIN", is_amo_admin=True)
    assert require_active_admin_profile(
        request("/accounts/admin/admin-profile/safarilink/state"),
        current,
        db,
    ) is current
    db.execute.assert_not_called()


def test_normal_tenant_admin_api_requires_active_backend_session() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        require_active_admin_profile(
            request("/accounts/admin/users"),
            actor(role="AMO_ADMIN", is_amo_admin=True),
            db,
        )
    assert exc.value.status_code == 403
    assert "activate admin profile" in str(exc.value.detail).lower()


def test_active_backend_session_unlocks_tenant_admin_api() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = ("session-1",)
    current = actor(role="AMO_ADMIN", is_amo_admin=True)
    assert require_active_admin_profile(
        request("/accounts/admin/users"),
        current,
        db,
    ) is current


def test_platform_superuser_stays_on_separate_control_plane() -> None:
    db = MagicMock()
    current = actor(is_superuser=True, amo_id=None, effective_amo_id=None, role="SUPERUSER")
    assert require_active_admin_profile(
        request("/accounts/admin/platform/metrics"),
        current,
        db,
    ) is current
    db.execute.assert_not_called()


def test_postgres_approval_count_locks_grant_before_counting() -> None:
    db = MagicMock()
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    lock_result = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 2
    db.execute.side_effect = [lock_result, count_result]

    assert serialized_approval_count(db, "grant-1") == 2

    lock_sql = str(db.execute.call_args_list[0].args[0]).upper()
    count_sql = str(db.execute.call_args_list[1].args[0]).upper()
    assert "FOR UPDATE" in lock_sql
    assert "COUNT(DISTINCT APPROVER_USER_ID)" in count_sql


def test_sqlite_approval_count_avoids_unsupported_row_lock() -> None:
    db = MagicMock()
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    db.execute.return_value = count_result

    assert serialized_approval_count(db, "grant-1") == 1
    assert db.execute.call_count == 1
    assert "FOR UPDATE" not in str(db.execute.call_args.args[0]).upper()
