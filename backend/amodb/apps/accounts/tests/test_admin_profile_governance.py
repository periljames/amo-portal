from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.accounts.admin_profile_guard import require_active_admin_profile
from amodb.apps.accounts.admin_profile_router import (
    _as_utc,
    _assert_tenant_member,
    _is_implicit_admin,
    _is_management_approver,
)


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


def test_existing_amo_admin_is_eligible_but_quality_manager_is_only_an_approver() -> None:
    assert _is_implicit_admin(actor(role="AMO_ADMIN", is_amo_admin=True)) is True
    assert _is_implicit_admin(actor(role="QUALITY_MANAGER", is_amo_admin=False)) is False
    assert _is_management_approver(actor(role="QUALITY_MANAGER")) is True
    assert _is_management_approver(actor(role="TECHNICIAN", position_title="Technician")) is False


def test_accountable_and_hr_managers_are_governance_approvers() -> None:
    assert _is_management_approver(actor(role="VIEW_ONLY", position_title="Accountable Manager")) is True
    assert _is_management_approver(actor(role="VIEW_ONLY", position_title="HR Manager")) is True


def test_naive_and_aware_grant_datetimes_are_normalised_to_utc() -> None:
    naive = datetime(2026, 8, 3, 10, 0, 0)
    aware = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    assert _as_utc(naive).tzinfo == timezone.utc
    assert _as_utc(aware) == aware


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
