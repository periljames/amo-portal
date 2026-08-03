from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.accounts.department_home_router import (
    _allowed_departments,
    _assert_tenant,
    _normalise_department,
    _safe_task_route,
)


def user(**overrides):
    values = {
        "id": "user-a",
        "amo_id": "amo-a",
        "effective_amo_id": "amo-a",
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
