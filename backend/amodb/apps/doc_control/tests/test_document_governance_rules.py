from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.doc_control.governance_schemas import ResponsibilityCreate
from amodb.apps.doc_control.governance_service import (
    active_on,
    effective_assignments,
    incoming_would_replace_confirmed,
    validate_assignment_target,
)


def assignment(**overrides):
    values = {
        "responsibility_type": "DOCUMENT_OWNER",
        "confirmation_status": "CONFIRMED",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "assignment_source": "MANUAL",
        "confidence_percent": 100,
        "updated_at": datetime(2026, 8, 6),
        "created_at": datetime(2026, 8, 6),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_effective_assignment_excludes_rejected_expired_and_future_rows() -> None:
    rows = [
        assignment(),
        assignment(confirmation_status="REJECTED"),
        assignment(effective_to=date(2026, 6, 1)),
        assignment(effective_from=date(2027, 1, 1)),
    ]
    grouped = effective_assignments(rows, on_date=date(2026, 8, 6))
    assert grouped["DOCUMENT_OWNER"] == [rows[0]]
    assert active_on(rows[0], date(2026, 8, 6))


def test_manual_confirmed_assignment_outranks_inferred_suggestion() -> None:
    inferred = assignment(
        confirmation_status="MATCH_PROPOSED",
        assignment_source="INFERRED",
        confidence_percent=98,
    )
    manual = assignment(confidence_percent=80)
    grouped = effective_assignments([inferred, manual], on_date=date(2026, 8, 6))
    assert grouped["DOCUMENT_OWNER"][0] is manual


def test_inference_cannot_replace_confirmed_governance() -> None:
    assert incoming_would_replace_confirmed(
        [assignment(confidence_percent=80)],
        responsibility_type="DOCUMENT_OWNER",
        assignment_source="INFERRED",
        confidence_percent=70,
    )
    assert not incoming_would_replace_confirmed(
        [assignment(confidence_percent=80)],
        responsibility_type="DOCUMENT_OWNER",
        assignment_source="MANUAL",
        confidence_percent=70,
    )


def test_assignment_requires_exactly_one_matching_target() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_assignment_target(
            assignee_type="USER",
            assignee_user_id="user-1",
            assignee_department_id="department-1",
            assignee_org_unit_id=None,
            assignee_role=None,
        )
    assert caught.value.status_code == 422


def test_effective_date_range_is_validated_before_persistence() -> None:
    with pytest.raises(ValidationError):
        ResponsibilityCreate(
            responsibility_type="DOCUMENT_OWNER",
            assignee_type="ROLE",
            assignee_role="HEAD_OF_QUALITY",
            effective_from=date(2026, 8, 6),
            effective_to=date(2026, 8, 5),
        )
