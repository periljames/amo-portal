from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from amodb.apps.doc_control import workspace_service as service
from amodb.apps.doc_control.domain_models import DocumentWorkflowInstance
from amodb.apps.doc_control.workspace_access import enforce_workspace_access
from amodb.apps.manuals import models as manual_models


def _user(role: str, *, superuser: bool = False, amo_admin: bool = False):
    return SimpleNamespace(
        id="user-1",
        role=role,
        is_superuser=superuser,
        is_amo_admin=amo_admin,
        is_active=True,
        is_system_account=False,
    )


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "scheme": "https",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        }
    )


def _workflow(state: str, *, requires_authority: bool = False) -> DocumentWorkflowInstance:
    return DocumentWorkflowInstance(
        id="workflow-1",
        tenant_id="amo-1",
        manual_id="manual-1",
        revision_id="revision-1",
        state=state,
        requires_authority=requires_authority,
        training_impact_required=False,
        training_readiness_status="NOT_REQUIRED",
        qms_readiness_status="NOT_REQUIRED",
        distribution_readiness_status="NOT_REQUIRED",
        version=1,
    )


def test_document_control_roles_are_explicit_and_fail_closed() -> None:
    assert service.is_control_user(_user("QUALITY_MANAGER")) is True
    assert service.is_control_user(_user("QUALITY_INSPECTOR")) is True
    assert service.is_control_user(_user("AUDITOR")) is False
    assert service.is_control_user(_user("DOCUMENT_CONTROL_OFFICER")) is False
    assert service.is_control_user(_user("TECHNICIAN")) is False
    assert service.is_control_user(_user("VIEW_ONLY")) is False
    assert service.is_control_user(_user("TECHNICIAN", superuser=True)) is True


def test_document_approval_roles_are_narrower_than_general_control_roles() -> None:
    assert service.is_approver(_user("QUALITY_MANAGER")) is True
    assert service.is_approver(_user("ACCOUNTABLE_EXECUTIVE")) is True
    assert service.is_approver(_user("QUALITY_INSPECTOR")) is False
    assert service.is_approver(_user("AUDITOR")) is False
    assert service.is_approver(_user("TECHNICIAN", amo_admin=True)) is True


def test_normal_user_can_use_library_and_reader_originated_change_request() -> None:
    normal_user = _user("TECHNICIAN")
    enforce_workspace_access(
        _request("GET", "/doc-control/workspace/t/safarilink/documents"),
        normal_user,
    )
    enforce_workspace_access(
        _request(
            "GET",
            "/doc-control/workspace/t/safarilink/documents/manual-1/read-target",
        ),
        normal_user,
    )
    enforce_workspace_access(
        _request("POST", "/doc-control/workspace/t/safarilink/change-requests"),
        normal_user,
    )
    enforce_workspace_access(
        _request(
            "POST",
            "/doc-control/workspace/t/safarilink/distribution-campaigns/campaign-1/acknowledge",
        ),
        normal_user,
    )


def test_normal_user_cannot_enumerate_controller_worklists() -> None:
    normal_user = _user("TECHNICIAN")
    for path in (
        "/doc-control/workspace/t/safarilink/workflows",
        "/doc-control/workspace/t/safarilink/authority-submissions",
        "/doc-control/workspace/t/safarilink/temporary-revisions",
        "/doc-control/workspace/t/safarilink/distribution-campaigns",
        "/doc-control/workspace/t/safarilink/controlled-copies",
        "/doc-control/workspace/t/safarilink/reports/master-register",
    ):
        with pytest.raises(HTTPException) as caught:
            enforce_workspace_access(_request("GET", path), normal_user)
        assert caught.value.status_code == 403


def test_controller_can_enter_governance_worklists() -> None:
    enforce_workspace_access(
        _request("GET", "/doc-control/workspace/t/safarilink/workflows"),
        _user("QUALITY_MANAGER"),
    )


def test_workflow_rejects_invalid_transition_and_lists_allowed_actions() -> None:
    workflow = _workflow("DRAFT")

    with pytest.raises(HTTPException) as caught:
        service.next_workflow_state(workflow, "PUBLISH")

    assert caught.value.status_code == 409
    assert caught.value.detail["state"] == "DRAFT"
    assert caught.value.detail["allowed_actions"] == ["SUBMIT_TECHNICAL_REVIEW"]


def test_regulated_revision_cannot_bypass_authority_submission() -> None:
    workflow = _workflow("ACCOUNTABLE_MANAGER_APPROVAL", requires_authority=True)

    with pytest.raises(HTTPException) as caught:
        service.next_workflow_state(workflow, "APPROVE_ACCOUNTABLE_MANAGER")

    assert caught.value.status_code == 409
    assert "Authority submission" in str(caught.value.detail)
    assert service.next_workflow_state(workflow, "MARK_AUTHORITY_SUBMITTED") == "AUTHORITY_SUBMITTED"


def test_non_regulated_revision_cannot_enter_authority_path() -> None:
    workflow = _workflow("ACCOUNTABLE_MANAGER_APPROVAL", requires_authority=False)

    with pytest.raises(HTTPException) as caught:
        service.next_workflow_state(workflow, "MARK_AUTHORITY_SUBMITTED")

    assert caught.value.status_code == 409
    assert service.next_workflow_state(workflow, "APPROVE_ACCOUNTABLE_MANAGER") == "SCHEDULED_FOR_EFFECTIVITY"


def test_published_revision_is_locked_and_timestamped() -> None:
    revision = manual_models.ManualRevision(
        id="revision-1",
        manual_id="manual-1",
        rev_number="1",
        issue_number="1",
        status_enum=manual_models.ManualRevisionStatus.DRAFT,
        immutable_locked=False,
    )

    service.sync_revision_status(revision, "PUBLISHED")

    assert revision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED
    assert revision.immutable_locked is True
    assert revision.published_at is not None


def test_corrections_reopen_revision_without_marking_it_published() -> None:
    revision = manual_models.ManualRevision(
        id="revision-1",
        manual_id="manual-1",
        rev_number="1",
        issue_number="1",
        status_enum=manual_models.ManualRevisionStatus.DEPARTMENT_REVIEW,
        immutable_locked=True,
    )

    service.sync_revision_status(revision, "CORRECTIONS_REQUIRED")

    assert revision.status_enum == manual_models.ManualRevisionStatus.DRAFT
    assert revision.immutable_locked is False
