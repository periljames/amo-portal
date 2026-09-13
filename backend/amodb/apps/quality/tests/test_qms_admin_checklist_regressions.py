from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.manuals import core_router as manual_core
from amodb.apps.quality.audit_file_controls import _require_checklist_editor


def _user(role: str, *, amo_id: str = "amo-1", is_amo_admin: bool = False):
    return SimpleNamespace(
        id=f"user-{role.lower()}",
        role=role,
        amo_id=amo_id,
        effective_amo_id=amo_id,
        is_active=True,
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=is_amo_admin,
    )


def _unassigned_audit():
    return SimpleNamespace(
        lead_auditor_user_id=None,
        observer_auditor_user_id=None,
        assistant_auditor_user_id=None,
        supporting_auditor_user_ids=[],
    )


def test_amo_admin_can_replace_controlled_audit_checklist() -> None:
    _require_checklist_editor(
        _user("AMO_ADMIN", is_amo_admin=True),
        _unassigned_audit(),
    )


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
