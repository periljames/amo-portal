from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.doc_control.knowledge_assistant_router import _cosine_similarity, _hybrid_merge, _pgvector_available
from amodb.apps.quality.audit_checklist_execution_route_order import _is_execution_route
from amodb.apps.quality.compliance_intelligence_service import (
    detect_requirement_conflicts,
    evaluate_applicability,
    evidence_priority,
    precedence_policy,
)
from amodb.apps.quality.audit_checklist_execution_router import (
    ChecklistAssessmentState,
    StructuredAIAnalysis,
)
from amodb.apps.quality.audit_evidence_router import _evidence_context, _with_assessment_context


def test_not_applicable_requires_reason_and_preserved_basis() -> None:
    with pytest.raises(ValidationError, match="NOT_APPLICABLE"):
        ChecklistAssessmentState(
            applicability="NOT_APPLICABLE",
            applicability_reason="Battery workshop capability is outside the current approval.",
        )

    assessment = ChecklistAssessmentState(
        applicability="NOT_APPLICABLE",
        applicability_reason="Battery workshop capability is outside the current approval.",
        applicability_basis=[{"source_type": "APPROVAL_SCOPE", "source_id": "scope-1"}],
        field_verification_status="NOT_APPLICABLE",
    )
    assert assessment.applicability == "NOT_APPLICABLE"


def test_document_conflict_requires_preserved_competing_references() -> None:
    with pytest.raises(ValidationError, match="CONFLICT"):
        ChecklistAssessmentState(documentary_status="CONFLICT")


def test_field_verification_required_requires_explicit_fieldwork_plan() -> None:
    with pytest.raises(ValidationError, match="FIELD_VERIFICATION_REQUIRED"):
        ChecklistAssessmentState(field_verification_status="FIELD_VERIFICATION_REQUIRED")


def test_structured_ai_analysis_rejects_private_reasoning_payloads() -> None:
    with pytest.raises(ValidationError, match="chain_of_thought"):
        StructuredAIAnalysis.model_validate(
            {
                "conclusion": "Documented procedure found; field verification remains outstanding.",
                "evidence_ids": ["section:rev-1:sec-1"],
                "confidence_basis": "Exact controlled-source reference.",
                "chain_of_thought": "must not be persisted",
            }
        )


def test_assessment_accepts_separate_documentary_implementation_and_field_states() -> None:
    assessment = ChecklistAssessmentState(
        applicability="APPLICABLE",
        documentary_status="DOCUMENTED",
        implementation_status="OBJECTIVE_EVIDENCE_AVAILABLE",
        field_verification_status="FIELD_VERIFICATION_REQUIRED",
        evidence_ids=["section:rev-1:sec-1"],
        document_revision_ids=["rev-1"],
        procedure_refs=["MPM 2.5.8"],
        fieldwork_requirements=["Inspect a sample tool calibration sticker."],
        ai_analysis=StructuredAIAnalysis(
            conclusion="Documented basis found; implementation is not yet physically verified.",
            evidence_ids=["section:rev-1:sec-1"],
            verification_required=["Inspect a sample tool calibration sticker."],
            confidence_basis="Exact controlled-source reference.",
        ),
    )

    assert assessment.documentary_status == "DOCUMENTED"
    assert assessment.implementation_status == "OBJECTIVE_EVIDENCE_AVAILABLE"
    assert assessment.field_verification_status == "FIELD_VERIFICATION_REQUIRED"


@pytest.mark.parametrize(
    "path",
    [
        "/api/maintenance/AMO/quality/audits/a/checklist-execution-governance",
        "/api/maintenance/AMO/quality/audits/a/checklist-items/i/execution-governance",
        "/api/maintenance/AMO/quality/audits/a/checklist-items/i/fieldwork-mutations",
        "/api/maintenance/AMO/quality/audits/a/checklist-items/i/fieldwork-findings",
        "/api/maintenance/AMO/quality/audits/a/checklist-items/i/evidence-candidates",
        "/api/maintenance/AMO/quality/audits/a/applicability-context",
    ],
)
def test_all_checklist_execution_route_families_are_promoted(path: str) -> None:
    assert _is_execution_route(SimpleNamespace(path=path))


def test_pgvector_acceleration_is_optional_outside_postgresql() -> None:
    class _Dialect:
        name = "sqlite"

    class _Bind:
        dialect = _Dialect()

    class _Db:
        def get_bind(self):
            return _Bind()

        def execute(self, *_args, **_kwargs):
            raise AssertionError("SQLite fallback must not query pg_extension.")

    assert _pgvector_available(_Db()) is False


def test_cosine_similarity_rejects_dimension_mismatch_and_ranks_exact_vector() -> None:
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert _cosine_similarity([1.0], [1.0, 0.0]) == 0.0


def test_hybrid_merge_boosts_same_controlled_section_without_losing_provenance() -> None:
    merged = _hybrid_merge(
        [
            {
                "id": "section:rev-1:sec-1",
                "kind": "SECTION",
                "revision_id": "rev-1",
                "section_id": "sec-1",
                "page_number": 7,
                "code": "MPM",
                "heading": "Tool calibration",
                "score": 52.0,
                "lexical_score": 52.0,
                "retrieval_channels": ["LEXICAL"],
                "reader_url": "/reader?page=7",
            },
            {
                "id": "section:rev-1:sec-1",
                "kind": "SECTION",
                "revision_id": "rev-1",
                "section_id": "sec-1",
                "page_number": 7,
                "code": "MPM",
                "heading": "Tool calibration",
                "score": 58.5,
                "semantic_similarity": 0.9,
                "retrieval_channels": ["SEMANTIC"],
                "reader_url": "/reader?page=7",
            },
        ],
        10,
    )

    assert len(merged) == 1
    assert merged[0]["id"] == "section:rev-1:sec-1"
    assert set(merged[0]["retrieval_channels"]) == {"LEXICAL", "SEMANTIC"}
    assert merged[0]["semantic_similarity"] == pytest.approx(0.9)
    assert merged[0]["score"] == pytest.approx(83.5)
    assert merged[0]["reader_url"] == "/reader?page=7"




def test_hybrid_merge_treats_pgvector_channel_as_semantic() -> None:
    merged = _hybrid_merge(
        [
            {
                "id": "section:rev-1:sec-1",
                "kind": "SECTION",
                "revision_id": "rev-1",
                "section_id": "sec-1",
                "page_number": 7,
                "code": "MPM",
                "heading": "Tool calibration",
                "score": 52.0,
                "lexical_score": 52.0,
                "retrieval_channels": ["LEXICAL"],
            },
            {
                "id": "section:rev-1:sec-1",
                "kind": "SECTION",
                "revision_id": "rev-1",
                "section_id": "sec-1",
                "page_number": 7,
                "code": "MPM",
                "heading": "Tool calibration",
                "score": 58.5,
                "semantic_similarity": 0.9,
                "retrieval_channels": ["SEMANTIC_PGVECTOR"],
            },
        ],
        10,
    )

    assert len(merged) == 1
    assert set(merged[0]["retrieval_channels"]) == {"LEXICAL", "SEMANTIC_PGVECTOR"}
    assert merged[0]["score"] == pytest.approx(83.5)
    assert "hybrid" in merged[0]["reason"].lower()

def test_capability_scope_precedence_is_context_specific_not_universal() -> None:
    policy = precedence_policy("CAPABILITY_SCOPE")
    assert policy["APPROVAL_CERTIFICATE"] > policy["CONTROLLED_MANUAL"]
    assert policy["SOP"] > policy["QWI"]
    assert evidence_priority("CAPABILITY_SCOPE", "APPROVAL_CERTIFICATE") == 100
    assert evidence_priority("GENERAL", "APPROVAL_CERTIFICATE") is None


def test_applicability_uses_governed_include_and_exclude_context() -> None:
    rules = [
        {
            "id": "inc-c208",
            "rule_type": "INCLUDE",
            "target_type": "AIRCRAFT_TYPE",
            "target_id": "C208B",
            "target_value": "Cessna 208B",
            "status": "ACTIVE",
        },
        {
            "id": "exc-base",
            "rule_type": "EXCLUDE",
            "target_type": "BASE",
            "target_id": "MBA",
            "target_value": "Mombasa",
            "status": "ACTIVE",
        },
    ]
    applicable = evaluate_applicability(
        rules,
        [{"id": "fact-1", "target_type": "AIRCRAFT_TYPE", "target_id": "C208B"}],
        as_of=date(2026, 10, 2),
    )
    assert applicable["status"] == "APPLICABLE"
    assert applicable["basis"][0]["rule_id"] == "inc-c208"

    excluded = evaluate_applicability(
        rules,
        [
            {"id": "fact-1", "target_type": "AIRCRAFT_TYPE", "target_id": "C208B"},
            {"id": "fact-2", "target_type": "BASE", "target_id": "MBA"},
        ],
        as_of=date(2026, 10, 2),
    )
    assert excluded["status"] == "NOT_APPLICABLE"
    assert excluded["basis"][0]["rule_id"] == "exc-base"


def test_applicability_fails_closed_when_required_context_is_missing() -> None:
    result = evaluate_applicability(
        [
            {
                "id": "cap-1",
                "rule_type": "INCLUDE",
                "target_type": "AUTHORIZATION_GROUP",
                "target_id": "DHC8-CERTIFYING",
                "status": "ACTIVE",
            }
        ],
        [],
        as_of=date(2026, 10, 2),
    )
    assert result["status"] == "UNVERIFIED"
    assert result["missing_context"] == ["AUTHORIZATION_GROUP"]


def test_applicability_respects_effectivity_window() -> None:
    result = evaluate_applicability(
        [
            {
                "id": "future",
                "rule_type": "EXCLUDE",
                "target_type": "AIRCRAFT_TYPE",
                "target_id": "C208B",
                "status": "ACTIVE",
                "effective_from": date(2027, 1, 1),
            }
        ],
        [{"id": "fact-1", "target_type": "AIRCRAFT_TYPE", "target_id": "C208B"}],
        as_of=date(2026, 10, 2),
    )
    assert result["status"] == "UNVERIFIED"


def test_retention_duration_conflict_preserves_both_controlled_sources() -> None:
    conflicts = detect_requirement_conflicts(
        [
            {
                "evidence_id": "section:rev-a:sec-a",
                "reference": "MPM 3.5.2",
                "source_text": "Quality records must be retained for 1 year after closure.",
            },
            {
                "evidence_id": "section:rev-b:sec-b",
                "reference": "QWI-REC-04",
                "source_text": "Quality records must be retained for 2 years after closure.",
            },
        ]
    )
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "DOCUMENT_CONFLICT"
    assert conflicts[0]["detector"] == "RETENTION_DURATION"
    assert {
        source["evidence_id"] for source in conflicts[0]["sources"]
    } == {"section:rev-a:sec-a", "section:rev-b:sec-b"}
    assert conflicts[0]["resolution"] == "AUDITOR_REVIEW_REQUIRED"


def test_matching_retention_periods_do_not_create_false_conflict() -> None:
    conflicts = detect_requirement_conflicts(
        [
            {
                "evidence_id": "section:rev-a:sec-a",
                "reference": "MPM 3.5.2",
                "source_text": "Quality records must be retained for 2 years after closure.",
            },
            {
                "evidence_id": "section:rev-b:sec-b",
                "reference": "QWI-REC-04",
                "source_text": "Quality records must be retained for 24 months after closure.",
            },
        ]
    )
    assert conflicts == []



def test_field_evidence_context_is_structured_and_inherits_assessment_links() -> None:
    context = _evidence_context(
        location_ref="NBO Base",
        person_ref="user-42",
        facility_ref="Battery Shop",
        asset_ref="5Y-SLK",
        tool_ref="SL-ENG-488",
        component_ref="PN-1234 SN-A17",
        regulation_refs_json='["KCAR 2025 Reg. 36"]',
        procedure_refs_json='["MPM 2.5.8"]',
        document_revision_ids_json='["rev-current"]',
    )
    governance = SimpleNamespace(
        regulation_refs=["KCAR 2025 Reg. 36", "KCAR 2025 Reg. 27"],
        procedure_refs=["MPM 2.5.8", "QWI-003 Rev A 4.2"],
        document_revision_ids=["rev-current", "qwi-rev-a"],
    )
    merged = _with_assessment_context(context, governance)
    assert merged["location_ref"] == "NBO Base"
    assert merged["tool_ref"] == "SL-ENG-488"
    assert merged["regulation_refs"] == ["KCAR 2025 Reg. 36", "KCAR 2025 Reg. 27"]
    assert merged["procedure_refs"] == ["MPM 2.5.8", "QWI-003 Rev A 4.2"]
    assert merged["document_revision_ids"] == ["rev-current", "qwi-rev-a"]


def test_field_evidence_context_rejects_non_string_reference_values() -> None:
    with pytest.raises(HTTPException, match="string references only"):
        _evidence_context(regulation_refs_json='[{"ref":"KCAR 36"}]')
