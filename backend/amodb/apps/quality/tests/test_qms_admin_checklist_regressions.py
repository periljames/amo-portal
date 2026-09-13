from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from amodb.apps.manuals import core_router as manual_core
from amodb.apps.quality.audit_file_controls import _require_checklist_editor


def _user(role: str, *, user_id: str | None = None, amo_id: str = "amo-1", is_amo_admin: bool = False):
    return SimpleNamespace(
        id=user_id or f"user-{role.lower()}",
        role=role,
        amo_id=amo_id,
        effective_amo_id=amo_id,
        is_active=True,
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=is_amo_admin,
        _admin_profile_elevated=False,
    )


def _unassigned_audit():
    return SimpleNamespace(
        lead_auditor_user_id=None,
        observer_auditor_user_id=None,
        assistant_auditor_user_id=None,
        supporting_auditor_user_ids=[],
    )


def _assigned_audit():
    return SimpleNamespace(
        lead_auditor_user_id="lead-1",
        observer_auditor_user_id="observer-1",
        assistant_auditor_user_id="assistant-1",
        supporting_auditor_user_ids=["support-1"],
    )


def test_amo_admin_can_replace_controlled_audit_checklist() -> None:
    _require_checklist_editor(
        _user("AMO_ADMIN", is_amo_admin=True),
        _unassigned_audit(),
    )


def test_executing_audit_team_can_replace_controlled_audit_checklist_but_observer_cannot() -> None:
    audit = _assigned_audit()
    for user_id in ("lead-1", "assistant-1", "support-1"):
        _require_checklist_editor(_user("AUDITOR", user_id=user_id), audit)

    with pytest.raises(HTTPException) as caught:
        _require_checklist_editor(_user("AUDITOR", user_id="observer-1"), audit)
    assert caught.value.status_code == 403
    assert "read-only" in str(caught.value.detail).lower()


def test_unassigned_non_admin_still_cannot_replace_controlled_audit_checklist() -> None:
    with pytest.raises(HTTPException) as caught:
        _require_checklist_editor(_user("TECHNICIAN"), _unassigned_audit())
    assert caught.value.status_code == 403


def test_manual_intake_uses_canonical_document_control_authority() -> None:
    # Importing the composed router installs the compatibility bridge used by
    # guarded preview/upload routes and QMS audit-preparation intake.
    importlib.import_module("amodb.apps.manuals.router")

    manual_core._require_manual_control_user(
        _user("AMO_ADMIN", is_amo_admin=True),
    )
    with pytest.raises(HTTPException) as caught:
        manual_core._require_manual_control_user(_user("TECHNICIAN"))
    assert caught.value.status_code == 403


def test_quality_router_export_exposes_fieldwork_helper_contract() -> None:
    quality_package = importlib.import_module("amodb.apps.quality")
    for helper_name in (
        "_is_quality_admin",
        "_audit_allows_user_by_audit",
        "_require_audit_fieldwork_write_access",
        "_next_audit_finding_ref",
        "_date_to_datetime",
        "_ensure_car_for_finding",
        "task_services",
    ):
        assert hasattr(quality_package.router, helper_name), helper_name


def test_observer_read_only_guard_is_installed_on_legacy_audit_content_mutations() -> None:
    quality_package = importlib.import_module("amodb.apps.quality")
    guarded = {
        ("POST", "/quality/audits/{audit_id}/document-requests"),
        ("PATCH", "/quality/audits/{audit_id}/document-requests/{request_id}"),
        ("POST", "/quality/audits/{audit_id}/checklist-items"),
        ("PATCH", "/quality/audits/{audit_id}/checklist-items/{item_id}"),
        ("POST", "/quality/audits/{audit_id}/findings"),
        ("PATCH", "/quality/audits/{audit_id}/findings/{finding_id}"),
        ("POST", "/quality/audits/{audit_id}/post-brief"),
        ("POST", "/quality/audits/{audit_id}/archive-package"),
        ("POST", "/quality/audits/{audit_id}/report"),
        ("POST", "/quality/audits/{audit_id}/report/share"),
    }
    seen: set[tuple[str, str]] = set()
    for route in quality_package.router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (method, str(route.path))
            if key not in guarded:
                continue
            seen.add(key)
            dependency_names = {
                getattr(dependency.call, "__name__", "")
                for dependency in route.dependant.dependencies
            }
            assert "_deny_observer_audit_mutation" in dependency_names, key
    assert seen == guarded


def test_observer_guard_does_not_turn_read_routes_into_write_routes() -> None:
    quality_package = importlib.import_module("amodb.apps.quality")
    checklist_get = next(
        route
        for route in quality_package.router.routes
        if isinstance(route, APIRoute)
        and str(route.path) == "/quality/audits/{audit_id}/checklist-items"
        and "GET" in (route.methods or set())
    )
    dependency_names = {
        getattr(dependency.call, "__name__", "")
        for dependency in checklist_get.dependant.dependencies
    }
    assert "_deny_observer_audit_mutation" not in dependency_names
