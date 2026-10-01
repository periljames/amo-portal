from __future__ import annotations

import pytest

from amodb.apps.quality.audit_checklist_response_policy import (
    normalise_response_options,
    resolve_response_value,
)
from amodb.apps.quality.audit_preparation_router import _preparation_readiness_blockers
from amodb.apps.quality.audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from amodb.apps.quality.audit_session_router import AuditSetupUpdate
from amodb.apps.quality.audit_evidence_models import QualityAuditEvidenceArtifact
from amodb.apps.quality.audit_evidence_router import _evidence_audit_event
from amodb.apps.quality.audit_checklist_template_router import ChecklistTemplateItem, _normalised_items


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


def test_checklist_revision_assigns_stable_item_and_section_identity() -> None:
    rows = _normalised_items([
        ChecklistTemplateItem(section="Stores", prompt="Verify traceability.", response_type="YES_NO_NA"),
        ChecklistTemplateItem(section="Stores", prompt="Verify quarantine control.", response_type="YES_NO_NA"),
        ChecklistTemplateItem(section="Line", prompt="Verify technical log control.", response_type="YES_NO_NA"),
    ])

    assert len({row["item_id"] for row in rows}) == 3
    assert rows[0]["section_id"] == rows[1]["section_id"]
    assert rows[0]["section_id"] != rows[2]["section_id"]
    assert rows[0]["section_title"] == "Stores"


def test_checklist_revision_rejects_duplicate_item_identity() -> None:
    item_id = "checklist-item-stable-001"
    with pytest.raises(Exception, match="duplicated"):
        _normalised_items([
            ChecklistTemplateItem(item_id=item_id, section="Stores", prompt="Verify traceability."),
            ChecklistTemplateItem(item_id=item_id, section="Stores", prompt="Verify another control."),
        ])



def test_execution_governance_maps_answer_provenance_columns() -> None:
    columns = QualityAuditChecklistExecutionGovernance.__table__.columns
    assert "answered_by_user_id" in columns
    assert "answered_at" in columns


def test_setup_contract_accepts_existing_audit_location_field() -> None:
    payload = AuditSetupUpdate(location="Hangar 1")
    assert payload.location == "Hangar 1"



def test_evidence_upload_event_is_audit_scoped_for_realtime_recovery() -> None:
    artifact = QualityAuditEvidenceArtifact(
        id="evidence-1",
        amo_id="amo-1",
        audit_id="00000000-0000-0000-0000-000000000001",
        checklist_item_id="00000000-0000-0000-0000-000000000002",
        source_type="INTERNAL_USER",
        client_mutation_id="mutation-12345678",
        file_ref="opaque/ref",
        filename="record.pdf",
        size_bytes=10,
        sha256="a" * 64,
        offline_upload_state="SYNCED",
        server_processing_state="AVAILABLE",
    )
    event = _evidence_audit_event(
        amo_id="amo-1",
        audit_id=artifact.audit_id,
        artifact=artifact,
        actor_user_id="user-1",
        actor_participant_id=None,
    )
    assert event.action == "UPLOADED"
    assert event.metadata_json["auditId"] == str(artifact.audit_id)
    assert event.after["sha256"] == "a" * 64
