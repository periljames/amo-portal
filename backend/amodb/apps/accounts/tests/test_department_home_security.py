from __future__ import annotations

from datetime import datetime, timedelta, timezone
from inspect import signature
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from amodb.apps.accounts.admin_profile_access import active_admin_profile_session
from amodb.apps.accounts.department_home_router import (
    QUICK_ACTIONS,
    _allowed_departments,
    _assert_tenant,
    _is_overdue,
    _normalise_department,
    _safe_task_route,
    router as department_home_router,
)
from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user, get_current_user


def user(**overrides):
    values = {
        "id": "user-a",
        "amo_id": "amo-a",
        "effective_amo_id": "amo-a",
        "auth_session_id": "browser-a",
        "department_id": None,
        "is_superuser": False,
        "is_amo_admin": False,
        "role": "PLANNING_ENGINEER",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_department_home_rejects_cross_tenant_user() -> None:
    with pytest.raises(HTTPException) as exc:
        _assert_tenant(user(), SimpleNamespace(id="amo-b"))
    assert exc.value.status_code == 403
    assert "not a member" in str(exc.value.detail).lower()


def test_platform_superuser_cannot_enter_tenant_home_without_support_session() -> None:
    with pytest.raises(HTTPException) as exc:
        _assert_tenant(user(is_superuser=True), SimpleNamespace(id="amo-a"))
    assert exc.value.status_code == 403
    assert "support session" in str(exc.value.detail).lower()


def test_department_aliases_are_canonicalised() -> None:
    assert _normalise_department("DOC_CONTROL") == "document-control"
    assert _normalise_department("procurement") == "stores"
    assert _normalise_department("QUALITY_ASSURANCE") == "quality"


def test_task_routes_cannot_escape_the_current_tenant_namespace() -> None:
    safe = SimpleNamespace(metadata_json={"route": "/maintenance/tenant-a/planning/work-orders"})
    foreign = SimpleNamespace(metadata_json={"route": "/maintenance/tenant-b/admin/users"})
    external = SimpleNamespace(metadata_json={"route": "https://example.com"})

    assert _safe_task_route(safe, "tenant-a", "planning") == "/maintenance/tenant-a/planning/work-orders"
    assert _safe_task_route(foreign, "tenant-a", "planning") == "/maintenance/tenant-a/planning"
    assert _safe_task_route(external, "tenant-a", "planning") == "/maintenance/tenant-a/planning"


def test_overdue_detection_accepts_naive_and_aware_database_datetimes() -> None:
    now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    assert _is_overdue(datetime(2026, 8, 3, 9, 0), now) is True
    assert _is_overdue(now - timedelta(minutes=1), now) is True
    assert _is_overdue(now + timedelta(minutes=1), now) is False
    assert _is_overdue(None, now) is False


def test_simple_department_actions_stay_inside_their_own_route_namespace() -> None:
    for department in ("safety", "stores", "workshops"):
        assert QUICK_ACTIONS[department]
        assert all(suffix.startswith(f"/{department}/") for _label, _description, suffix in QUICK_ACTIONS[department])


def test_security_identity_and_role_dependencies_use_the_writer_database() -> None:
    assert signature(get_current_user).parameters["db"].default.dependency is get_db
    assert signature(get_current_active_user).parameters["db"].default.dependency is get_db


def test_department_home_uses_writer_for_authorization_and_replica_for_payload() -> None:
    routes = [
        route
        for route in department_home_router.routes
        if isinstance(route, APIRoute) and route.path == "/home/{amo_code}/{department}"
    ]
    assert len(routes) == 1
    direct_dependencies = {dependency.call for dependency in routes[0].dependant.dependencies}
    assert get_current_active_user in direct_dependencies
    assert get_db in direct_dependencies
    assert get_read_db in direct_dependencies


def test_role_driven_access_does_not_open_unrelated_departments(monkeypatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(
        "amodb.apps.accounts.department_home_router._admin_profile_active",
        lambda *_args, **_kwargs: False,
    )

    allowed = _allowed_departments(db, user(role="PLANNING_ENGINEER"), SimpleNamespace(id="amo-a"))

    assert allowed == {"planning"}
    assert "quality" not in allowed
    assert "admin" not in allowed


def test_active_admin_profile_opens_only_supported_tenant_departments(monkeypatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(
        "amodb.apps.accounts.department_home_router._admin_profile_active",
        lambda *_args, **_kwargs: True,
    )

    allowed = _allowed_departments(
        db,
        user(role="AMO_ADMIN", is_amo_admin=True),
        SimpleNamespace(id="amo-a"),
    )

    assert "planning" in allowed
    assert "quality" in allowed
    assert "document-control" in allowed
    assert "admin" not in allowed


def test_active_approved_grantee_opens_supported_department_homes(monkeypatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(
        "amodb.apps.accounts.department_home_router._admin_profile_active",
        lambda *_args, **_kwargs: True,
    )

    allowed = _allowed_departments(
        db,
        user(role="TECHNICIAN", is_amo_admin=False),
        SimpleNamespace(id="amo-a"),
    )

    assert "maintenance" in allowed
    assert "planning" in allowed
    assert "quality" in allowed
    assert "document-control" in allowed
    assert "admin" not in allowed


def test_grantee_session_lookup_does_not_require_legacy_admin_role() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = (1,)

    assert active_admin_profile_session(
        db,
        user(role="TECHNICIAN", is_amo_admin=False),
        SimpleNamespace(id="amo-a"),
    ) is True

    sql = str(db.execute.call_args.args[0]).upper()
    params = db.execute.call_args.args[1]
    assert "ADMIN_PROFILE_SESSIONS" in sql
    assert "ADMIN_ACCESS_GRANTS" in sql
    assert "S.AUTH_SESSION_ID = :AUTH_SESSION_ID" in sql
    assert ":IMPLICIT_ADMIN = TRUE" in sql
    assert params["auth_session_id"] == "browser-a"
    assert params["implicit_admin"] is False


def test_downgraded_admin_grantless_session_does_not_open_department_homes() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = None

    assert active_admin_profile_session(
        db,
        user(role="TECHNICIAN", is_amo_admin=False),
        SimpleNamespace(id="amo-a"),
    ) is False
    assert db.execute.call_args.args[1]["implicit_admin"] is False


def test_other_browser_session_cannot_inherit_department_elevation() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = None

    assert active_admin_profile_session(
        db,
        user(role="AMO_ADMIN", is_amo_admin=True, auth_session_id="browser-b"),
        SimpleNamespace(id="amo-a"),
    ) is False
    assert db.execute.call_args.args[1]["auth_session_id"] == "browser-b"
