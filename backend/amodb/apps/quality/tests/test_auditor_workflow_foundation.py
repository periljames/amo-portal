from __future__ import annotations

import pytest

from amodb.apps.quality.audit_checklist_response_policy import (
    normalise_response_options,
    resolve_response_value,
)
from amodb.apps.quality.audit_preparation_router import _preparation_readiness_blockers


def _captured_request(*, stage: str, status: str = "REQUESTED", is_required: bool = True) -> dict:
    return {
        "checklist_snapshot": [{"id": "check-1"}],
        "document_request_snapshot": [
            {
                "id": "request-1",
                "is_required": is_required,
                "requirement_stage": stage,
                "status": status,
            }
        ],
    }


def test_document_request_stage_separates_issue_from_fieldwork_gate() -> None:
    captured = _captured_request(stage="REQUIRED_BEFORE_FIELDWORK")

    assert _preparation_readiness_blockers(captured, phase="ISSUE") == []
    blockers = _preparation_readiness_blockers(captured, phase="FIELDWORK")

    assert len(blockers) == 1
    assert blockers[0]["type"] == "DOCUMENT_REQUEST"
    assert blockers[0]["request_ids"] == ["request-1"]


@pytest.mark.parametrize("stage", ["REQUIRED_DURING_FIELDWORK", "REQUESTED_NOT_BLOCKING"])
def test_later_or_nonblocking_requests_do_not_prevent_fieldwork_start(stage: str) -> None:
    captured = _captured_request(stage=stage)

    assert _preparation_readiness_blockers(captured, phase="ISSUE") == []
    assert _preparation_readiness_blockers(captured, phase="FIELDWORK") == []


@pytest.mark.parametrize("status", ["ACCEPTED", "WAIVED"])
def test_resolved_pre_fieldwork_request_does_not_block(status: str) -> None:
    captured = _captured_request(stage="REQUIRED_BEFORE_FIELDWORK", status=status)

    assert _preparation_readiness_blockers(captured, phase="FIELDWORK") == []


def test_yes_no_na_scheme_preserves_source_vocabulary_and_semantics() -> None:
    options = normalise_response_options("YES_NO_NA", None)

    assert [row["value"] for row in options] == ["YES", "NO", "N/A"]
    assert [row["canonical_status"] for row in options] == [
        "COMPLIANT",
        "NONCOMPLIANT",
        "NOT_APPLICABLE",
    ]
    assert resolve_response_value(
        response_type="YES_NO_NA",
        response_options=options,
        response_value="NO",
        canonical_status="NONCOMPLIANT",
    ) == "NO"


def test_ambiguous_custom_scheme_requires_explicit_mapping() -> None:
    with pytest.raises(ValueError, match="no explicit response_options"):
        normalise_response_options("YES_NO_NA_U_S", None)

    options = normalise_response_options(
        "YES_NO_NA_U_S",
        [
            {"value": "YES", "label": "Yes", "canonical_status": "COMPLIANT"},
            {"value": "NO", "label": "No", "canonical_status": "NONCOMPLIANT"},
            {"value": "N/A", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
            # These mappings are intentionally test data only. The application
            # must receive them from the governed source/template and never infer
            # the meaning of U or S.
            {"value": "U", "label": "U", "canonical_status": "NOT_VERIFIED"},
            {"value": "S", "label": "S", "canonical_status": "OBSERVATION"},
        ],
    )

    assert [row["value"] for row in options] == ["YES", "NO", "N/A", "U", "S"]


def test_source_response_cannot_claim_a_different_canonical_outcome() -> None:
    with pytest.raises(ValueError, match="maps to COMPLIANT, not NONCOMPLIANT"):
        resolve_response_value(
            response_type="YES_NO_NA",
            response_options=None,
            response_value="YES",
            canonical_status="NONCOMPLIANT",
        )
