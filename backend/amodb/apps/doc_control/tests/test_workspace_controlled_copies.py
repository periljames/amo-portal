from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control.workspace_copy_router import _ALLOWED_EVENTS, validate_copy_event


def _copy(status: str = "ISSUED"):
    return SimpleNamespace(
        status=status,
        copy_number="COPY-001",
        holder_user_id="holder-1",
        location_text="Nairobi Base Library",
    )


def _event(event_type: str, **values):
    payload = {
        "event_type": event_type,
        "to_holder_user_id": None,
        "to_location": None,
        "reason": None,
        "evidence": [],
    }
    payload.update(values)
    return schemas.ControlledCopyEventCreate(**payload)


def test_destroyed_copy_is_terminal() -> None:
    assert _ALLOWED_EVENTS["DESTROYED"] == set()
    with pytest.raises(HTTPException) as caught:
        validate_copy_event(
            _copy("DESTROYED"),
            _event("LOCATION_CHANGE", to_location="Archive Store"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "CONTROLLED_COPY_EVENT_INVALID"


def test_destruction_requires_reason_and_evidence() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_copy_event(_copy(), _event("DESTROY", reason="Obsolete copy"))
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "COPY_DISPOSITION_EVIDENCE_REQUIRED"


def test_destruction_with_reason_and_evidence_is_allowed() -> None:
    validate_copy_event(
        _copy(),
        _event(
            "DESTROY",
            reason="Superseded copy destroyed under controller supervision",
            evidence=[{"asset_id": "destruction-certificate-1"}],
        ),
    )


def test_unchanged_transfer_is_rejected() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_copy_event(
            _copy(),
            _event(
                "TRANSFER",
                to_holder_user_id="holder-1",
                to_location="Nairobi Base Library",
            ),
        )
    assert caught.value.status_code == 409


def test_recall_requires_reason() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_copy_event(_copy(), _event("RECALL"))
    assert caught.value.status_code == 409


def test_location_change_requires_a_new_location() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_copy_event(
            _copy(),
            _event("LOCATION_CHANGE", to_location="Nairobi Base Library"),
        )
    assert caught.value.status_code == 409
