from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.aircraft_architecture.content_packs import backend_assembly


def _row(
    *,
    row_id: str,
    intake_id: str,
    identity: str,
    value: str,
    temporary_revision_id: str | None,
):
    intake = SimpleNamespace(
        id=intake_id,
        temporary_revision_id=temporary_revision_id,
    )
    return SimpleNamespace(
        id=row_id,
        intake_id=intake_id,
        intake=intake,
        row_kind="TASK",
        identity_key=identity,
        normalized_json={
            "task_code": identity,
            "title": "Controlled task",
            "intervals_json": {"hours": value},
        },
    )


def test_different_base_and_temporary_revision_task_requires_explicit_resolution():
    base = _row(
        row_id="base-row",
        intake_id="base-intake",
        identity="TASK-100",
        value="8000",
        temporary_revision_id=None,
    )
    temporary = _row(
        row_id="tr-row",
        intake_id="tr-intake",
        identity="TASK-100",
        value="6000",
        temporary_revision_id="tr-1",
    )
    groups = {("TASK", "TASK-100"): [base, temporary]}

    conflicts, selected = backend_assembly._conflicts_and_selected(groups, [])

    assert selected == []
    assert conflicts == [
        {
            "row_kind": "TASK",
            "identity_key": "TASK-100",
            "candidate_intake_ids": ["base-intake", "tr-intake"],
            "candidate_row_ids": ["base-row", "tr-row"],
            "reason": "controlled content differs across base/TR sources",
        }
    ]


def test_conflict_resolution_selects_exact_reviewed_intake():
    base = _row(
        row_id="base-row",
        intake_id="base-intake",
        identity="TASK-100",
        value="8000",
        temporary_revision_id=None,
    )
    temporary = _row(
        row_id="tr-row",
        intake_id="tr-intake",
        identity="TASK-100",
        value="6000",
        temporary_revision_id="tr-1",
    )
    resolution = backend_assembly.OemBaselineConflictResolution(
        row_kind="TASK",
        identity_key="TASK-100",
        selected_intake_id="tr-intake",
        rationale="Temporary Revision changes the controlled interval to 6000 FH",
    )

    conflicts, selected = backend_assembly._conflicts_and_selected(
        {("TASK", "TASK-100"): [base, temporary]},
        [resolution],
    )

    assert conflicts == []
    assert selected == [temporary]


def test_resolution_cannot_select_an_unrelated_intake():
    base = _row(
        row_id="base-row",
        intake_id="base-intake",
        identity="TASK-100",
        value="8000",
        temporary_revision_id=None,
    )
    temporary = _row(
        row_id="tr-row",
        intake_id="tr-intake",
        identity="TASK-100",
        value="6000",
        temporary_revision_id="tr-1",
    )
    resolution = backend_assembly.OemBaselineConflictResolution(
        row_kind="TASK",
        identity_key="TASK-100",
        selected_intake_id="other-intake",
        rationale="Invalid test selection",
    )

    with pytest.raises(HTTPException, match="does not select exactly one candidate"):
        backend_assembly._conflicts_and_selected(
            {("TASK", "TASK-100"): [base, temporary]},
            [resolution],
        )


def test_unused_conflict_resolution_is_rejected():
    base = _row(
        row_id="base-row",
        intake_id="base-intake",
        identity="TASK-100",
        value="8000",
        temporary_revision_id=None,
    )
    resolution = backend_assembly.OemBaselineConflictResolution(
        row_kind="TASK",
        identity_key="TASK-NOT-PRESENT",
        selected_intake_id="base-intake",
        rationale="No corresponding conflict",
    )

    with pytest.raises(HTTPException, match="non-conflicting identities"):
        backend_assembly._conflicts_and_selected(
            {("TASK", "TASK-100"): [base]},
            [resolution],
        )


def test_identical_duplicate_prefers_temporary_revision_authority_deterministically():
    base = _row(
        row_id="base-row",
        intake_id="base-intake",
        identity="TASK-100",
        value="8000",
        temporary_revision_id=None,
    )
    temporary = _row(
        row_id="tr-row",
        intake_id="tr-intake",
        identity="TASK-100",
        value="8000",
        temporary_revision_id="tr-1",
    )

    conflicts, selected = backend_assembly._conflicts_and_selected(
        {("TASK", "TASK-100"): [base, temporary]},
        [],
    )

    assert conflicts == []
    assert selected == [temporary]
