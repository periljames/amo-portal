from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control import workspace_workflow_router as guards
from amodb.apps.doc_control.domain_models import DocumentWorkflowInstance


def _tenant():
    return SimpleNamespace(id="tenant-1", amo_id="amo-1")


def _workflow() -> DocumentWorkflowInstance:
    return DocumentWorkflowInstance(
        id="workflow-1",
        tenant_id="amo-1",
        manual_id="manual-1",
        revision_id="revision-1",
        state="SCHEDULED_FOR_EFFECTIVITY",
        requires_authority=False,
        training_impact_required=True,
        training_readiness_status="NOT_REQUIRED",
        qms_readiness_status="NOT_REQUIRED",
        distribution_readiness_status="NOT_REQUIRED",
        version=1,
    )


def _approver():
    return SimpleNamespace(
        id="user-1",
        role="QUALITY_MANAGER",
        is_superuser=False,
        is_amo_admin=False,
    )


def _payload(**values):
    base = {
        "action": "PUBLISH",
        "expected_version": 1,
        "comments": None,
        "evidence": [],
    }
    base.update(values)
    return schemas.WorkflowTransitionRequest(**base)


def test_distribution_readiness_cannot_be_marked_ready_manually() -> None:
    with pytest.raises(HTTPException) as caught:
        guards._validate_readiness_change(
            None,
            tenant=_tenant(),
            workflow=_workflow(),
            payload=_payload(distribution_readiness_status="READY"),
            current_user=_approver(),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "DISTRIBUTION_READY_IS_SYSTEM_MANAGED"


def test_training_ready_requires_resolved_training_link(monkeypatch) -> None:
    monkeypatch.setattr(guards, "_resolved_integration_exists", lambda *args, **kwargs: False)
    with pytest.raises(HTTPException) as caught:
        guards._validate_readiness_change(
            None,
            tenant=_tenant(),
            workflow=_workflow(),
            payload=_payload(training_readiness_status="READY"),
            current_user=_approver(),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "TRAINING_LINK_NOT_READY"


def test_training_ready_accepts_resolved_training_link(monkeypatch) -> None:
    monkeypatch.setattr(guards, "_resolved_integration_exists", lambda *args, **kwargs: True)
    guards._validate_readiness_change(
        None,
        tenant=_tenant(),
        workflow=_workflow(),
        payload=_payload(training_readiness_status="READY"),
        current_user=_approver(),
    )


def test_waiver_requires_reason_and_evidence() -> None:
    with pytest.raises(HTTPException) as caught:
        guards._validate_readiness_change(
            None,
            tenant=_tenant(),
            workflow=_workflow(),
            payload=_payload(training_readiness_status="WAIVED"),
            current_user=_approver(),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "WAIVER_EVIDENCE_REQUIRED"


def test_waiver_with_reason_and_evidence_is_allowed() -> None:
    guards._validate_readiness_change(
        None,
        tenant=_tenant(),
        workflow=_workflow(),
        payload=_payload(
            training_readiness_status="WAIVED",
            comments="Training manager approved a limited waiver for this controlled release.",
            evidence=[{"asset_id": "evidence-1"}],
        ),
        current_user=_approver(),
    )
