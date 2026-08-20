from __future__ import annotations

from datetime import date
from decimal import Decimal

from amodb.apps.training import exam_governance


def candidate(code: str, revision_id: str, *, question_status: str = "ACTIVE", revision_status: str = "ACTIVE", exposure: int = 0):
    return {
        "question": {
            "id": f"q-{code}",
            "question_code": code,
            "status": question_status,
            "module_id": "m1",
            "learning_objective_id": "lo1",
            "exposure_count": exposure,
        },
        "revision": {
            "id": revision_id,
            "status": revision_status,
            "effective_from": date(2026, 1, 1),
            "effective_to": None,
            "source_revision_id": "manual-rev-1",
        },
    }


def test_exam_generation_excludes_compromised_and_superseded_questions():
    result = exam_governance.select_question_revisions(
        [
            candidate("A", "r-a"),
            candidate("B", "r-b", question_status="COMPROMISED"),
            candidate("C", "r-c", revision_status="RETIRED"),
        ],
        on_date=date(2026, 8, 18),
        selection_rules={"question_count": 1},
    )
    assert result["ready"] is True
    assert result["selected_revision_ids"] == ["r-a"]
    excluded = {row["question_revision_id"] for row in result["excluded"]}
    assert excluded == {"r-b", "r-c"}


def test_exam_generation_blocks_when_blueprint_cannot_be_satisfied():
    result = exam_governance.select_question_revisions(
        [candidate("A", "r-a")],
        on_date=date(2026, 8, 18),
        selection_rules={"question_count": 2},
    )
    assert result["ready"] is False
    assert result["required_count"] == 2
    assert result["eligible_count"] == 1


def test_exam_generation_respects_blueprint_exposure_limit_without_magic_constant():
    result = exam_governance.select_question_revisions(
        [candidate("A", "r-a", exposure=4), candidate("B", "r-b", exposure=1)],
        on_date=date(2026, 8, 18),
        selection_rules={"question_count": 1, "max_exposure_count": 4},
    )
    assert result["selected_revision_ids"] == ["r-b"]
    assert any(row["question_revision_id"] == "r-a" for row in result["excluded"])


def test_item_analysis_uses_supplied_policy_thresholds():
    responses = [
        {"selected_option": "A", "correct": True, "total_score": 90},
        {"selected_option": "A", "correct": True, "total_score": 80},
        {"selected_option": "B", "correct": False, "total_score": 50},
        {"selected_option": "B", "correct": False, "total_score": 40},
    ]
    result = exam_governance.item_analysis(
        responses,
        policy={
            "minimum_sample_size": 4,
            "minimum_difficulty_index": "0.30",
            "maximum_difficulty_index": "0.90",
            "minimum_discrimination_index": "0.20",
            "discrimination_group_fraction": "0.25",
            "complaint_review_threshold": 2,
        },
        complaint_count=0,
    )
    assert result["sample_size"] == 4
    assert result["percent_correct"] == Decimal("50")
    assert result["difficulty_index"] == Decimal("0.5")
    assert result["discrimination_index"] == Decimal("1")
    assert result["review_status"] == "CLEAR"


def test_item_analysis_flags_superseded_source_for_human_review_without_editing_question():
    result = exam_governance.item_analysis(
        [{"selected_option": "A", "correct": True, "total_score": 90}],
        policy={"minimum_sample_size": 1},
        source_superseded=True,
    )
    assert result["review_status"] == "REVIEW_REQUIRED"
    assert any("superseded" in reason for reason in result["review_reasons"])


def test_item_analysis_does_not_invent_quality_conclusion_below_controlled_sample_size():
    result = exam_governance.item_analysis(
        [{"selected_option": "A", "correct": False, "total_score": 20}],
        policy={"minimum_sample_size": 10, "minimum_difficulty_index": "0.30"},
    )
    assert result["review_status"] == "INSUFFICIENT_DATA"
    assert result["review_reasons"] == []
