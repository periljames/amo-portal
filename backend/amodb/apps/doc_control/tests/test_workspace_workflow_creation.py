from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control import workspace_workflow_create_router as creation


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class _DB:
    def __init__(self, query_rows):
        self.query_rows = list(query_rows)

    def query(self, *args, **kwargs):
        return _Query(self.query_rows.pop(0))


def _tenant():
    return SimpleNamespace(id="tenant-1", amo_id="amo-1")


def _manual():
    return SimpleNamespace(id="manual-1")


def _revision():
    return SimpleNamespace(id="revision-1")


def _user(role: str = "QUALITY_INSPECTOR"):
    return SimpleNamespace(
        id="user-1",
        role=role,
        is_superuser=False,
        is_amo_admin=False,
    )


def test_profile_and_open_changes_cannot_be_bypassed(monkeypatch) -> None:
    monkeypatch.setattr(
        creation,
        "get_profile",
        lambda *args, **kwargs: SimpleNamespace(
            requires_authority_approval=True,
            regulated_flag=True,
            acknowledgement_required=True,
        ),
    )
    changes = [
        SimpleNamespace(training_impact_required=True, qms_blocking=True),
    ]
    payload = schemas.WorkflowCreate(
        manual_id="manual-1",
        revision_id="revision-1",
        requires_authority=False,
        training_impact_required=False,
        training_readiness_status="READY",
        qms_readiness_status="WAIVED",
        distribution_readiness_status="READY",
    )

    derived = creation.derive_initial_workflow_payload(
        _DB([changes, []]),
        tenant=_tenant(),
        manual=_manual(),
        revision=_revision(),
        payload=payload,
        current_user=_user(),
    )

    assert derived.requires_authority is True
    assert derived.training_impact_required is True
    assert derived.training_readiness_status == "PENDING"
    assert derived.qms_readiness_status == "PENDING"
    assert derived.distribution_readiness_status == "PENDING"


def test_linked_training_and_qms_records_start_pending(monkeypatch) -> None:
    monkeypatch.setattr(
        creation,
        "get_profile",
        lambda *args, **kwargs: SimpleNamespace(
            requires_authority_approval=False,
            regulated_flag=False,
            acknowledgement_required=False,
        ),
    )
    links = [
        SimpleNamespace(source_module="TRAINING"),
        SimpleNamespace(source_module="QMS"),
    ]
    payload = schemas.WorkflowCreate(
        manual_id="manual-1",
        revision_id="revision-1",
    )

    derived = creation.derive_initial_workflow_payload(
        _DB([[], links]),
        tenant=_tenant(),
        manual=_manual(),
        revision=_revision(),
        payload=payload,
        current_user=_user(),
    )

    assert derived.training_impact_required is True
    assert derived.training_readiness_status == "PENDING"
    assert derived.qms_readiness_status == "PENDING"
    assert derived.distribution_readiness_status == "NOT_REQUIRED"


def test_non_approver_cannot_schedule_effectivity_at_workflow_creation(monkeypatch) -> None:
    monkeypatch.setattr(creation, "get_profile", lambda *args, **kwargs: None)
    payload = schemas.WorkflowCreate(
        manual_id="manual-1",
        revision_id="revision-1",
        effective_at=datetime.utcnow(),
    )

    with pytest.raises(HTTPException) as caught:
        creation.derive_initial_workflow_payload(
            _DB([[], []]),
            tenant=_tenant(),
            manual=_manual(),
            revision=_revision(),
            payload=payload,
            current_user=_user("TECHNICIAN"),
        )

    assert caught.value.status_code == 403
