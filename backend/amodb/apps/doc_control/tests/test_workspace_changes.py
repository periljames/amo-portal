from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_change_router as changes
from amodb.apps.doc_control import workspace_schemas as schemas


def _tenant():
    return SimpleNamespace(amo_id="amo-1")


def _change(
    status: str = "OPEN",
    *,
    resolution: str | None = None,
    training_required: bool = False,
    qms_blocking: bool = False,
):
    return SimpleNamespace(
        id="change-1",
        status=status,
        resolution=resolution,
        training_impact_required=training_required,
        qms_blocking=qms_blocking,
    )


def _update(**values):
    return schemas.ChangeRequestUpdate(**values)


def test_open_change_cannot_skip_assessment_and_close_directly() -> None:
    with pytest.raises(HTTPException) as caught:
        changes.validate_change_update(
            None,
            tenant=_tenant(),
            row=_change("OPEN"),
            payload=_update(status="CLOSED", resolution="Implemented"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "CHANGE_TRANSITION_INVALID"


def test_normal_assessment_transition_is_allowed() -> None:
    changes.validate_change_update(
        None,
        tenant=_tenant(),
        row=_change("OPEN"),
        payload=_update(status="ASSESSING"),
    )


def test_closed_change_requires_resolution() -> None:
    with pytest.raises(HTTPException) as caught:
        changes.validate_change_update(
            None,
            tenant=_tenant(),
            row=_change("IMPLEMENTING"),
            payload=_update(status="CLOSED"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "CHANGE_RESOLUTION_REQUIRED"


def test_training_impacted_change_requires_resolved_training_link(monkeypatch) -> None:
    monkeypatch.setattr(changes, "_live_change_links", lambda *args, **kwargs: [])
    with pytest.raises(HTTPException) as caught:
        changes.validate_change_update(
            None,
            tenant=_tenant(),
            row=_change("IMPLEMENTING", training_required=True),
            payload=_update(status="CLOSED", resolution="Amendment incorporated"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "CHANGE_TRAINING_NOT_RESOLVED"


def test_qms_blocking_change_requires_resolved_qms_link(monkeypatch) -> None:
    monkeypatch.setattr(changes, "_live_change_links", lambda *args, **kwargs: [])
    with pytest.raises(HTTPException) as caught:
        changes.validate_change_update(
            None,
            tenant=_tenant(),
            row=_change("IMPLEMENTING", qms_blocking=True),
            payload=_update(status="CLOSED", resolution="Corrective action implemented"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "CHANGE_QMS_NOT_RESOLVED"


def test_resolved_training_and_qms_links_allow_closure(monkeypatch) -> None:
    links = [
        SimpleNamespace(
            id="training-link",
            source_module="TRAINING",
            status_snapshot="COMPLETED",
            blocking=True,
        ),
        SimpleNamespace(
            id="qms-link",
            source_module="QMS",
            status_snapshot="RESOLVED",
            blocking=True,
        ),
    ]
    monkeypatch.setattr(changes, "_live_change_links", lambda *args, **kwargs: links)
    changes.validate_change_update(
        None,
        tenant=_tenant(),
        row=_change("IMPLEMENTING", training_required=True, qms_blocking=True),
        payload=_update(status="CLOSED", resolution="All linked actions verified"),
    )
