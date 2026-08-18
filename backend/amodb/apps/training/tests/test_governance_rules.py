from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from amodb.apps.training import governance_rules as rules
from amodb.apps.training import governance_service as service


def auth(**overrides):
    payload = {
        "id": "auth-1",
        "privilege_type": "INSTRUCTOR",
        "status": "ACTIVE",
        "issue_date": date(2026, 1, 1),
        "expiry_date": date(2026, 12, 31),
        "course_ids": ["course-a"],
        "aircraft": "DHC8",
        "theoretical_privilege": True,
        "practical_privilege": True,
        "ojt_privilege": False,
    }
    payload.update(overrides)
    return payload


def provider(**overrides):
    payload = {
        "status": "ACTIVE",
        "recognition_status": "RECOGNISED",
        "effective_date": date(2026, 1, 1),
        "expiry_date": date(2026, 12, 31),
        "approved_course_ids": ["course-a"],
        "authority_id": "kcaa",
    }
    payload.update(overrides)
    return payload


def test_out_of_scope_instructor_is_blocked():
    reasons = rules.technical_authorisation_reasons(auth(course_ids=["course-b"]), on_date=date(2026, 8, 18), privilege_type="INSTRUCTOR", course_id="course-a", require_theory=True)
    assert any("outside this course scope" in reason for reason in reasons)


def test_expired_instructor_cannot_conduct_course():
    reasons = rules.technical_authorisation_reasons(auth(expiry_date=date(2026, 8, 17)), on_date=date(2026, 8, 18), privilege_type="INSTRUCTOR", course_id="course-a")
    assert any("expired on 2026-08-17" in reason for reason in reasons)


def test_suspended_instructor_is_blocked_even_if_dates_are_current():
    reasons = rules.technical_authorisation_reasons(auth(status="SUSPENDED"), on_date=date(2026, 8, 18), privilege_type="INSTRUCTOR", course_id="course-a")
    assert any("SUSPENDED" in reason for reason in reasons)


def test_unapproved_location_blocks_course_requiring_approval():
    reasons = rules.facility_reasons({"status": "ACTIVE", "approval_id": None, "classroom_capacity": 30, "practical_capacity": 10}, on_date=date(2026, 8, 18), learners=10, approval_required=True)
    assert any("requires an approved facility" in reason for reason in reasons)


def test_facility_capacity_is_governed_not_silently_overridden():
    reasons = rules.facility_reasons({"status": "ACTIVE", "approval_id": "approval-1", "classroom_capacity": 12, "practical_capacity": 4}, on_date=date(2026, 8, 18), learners=13, practical_learners=5, approval_required=True)
    assert len(reasons) == 2


def test_invalid_external_ato_scope_prevents_credit():
    reasons = rules.provider_credit_reasons(provider(approved_course_ids=["course-b"]), training_date=date(2026, 8, 18), course_id="course-a", authority_id="kcaa")
    assert any("does not cover this course" in reason for reason in reasons)


def test_external_provider_must_be_valid_on_training_date():
    reasons = rules.provider_credit_reasons(provider(expiry_date=date(2026, 7, 31)), training_date=date(2026, 8, 18), course_id="course-a")
    assert any("expired on the training date" in reason for reason in reasons)


def test_conflicting_current_controlled_rules_are_surfaced_not_guessed():
    conflicting = rules.rule_conflicts([
        {"id": "r1", "rule_code": "EXAM.PASS_MARK", "value_json": {"percent": 75}, "condition_json": {}, "severity": "BLOCK", "exception_permitted": False, "source_document_id": "m1", "source_revision_id": "a"},
        {"id": "r2", "rule_code": "EXAM.PASS_MARK", "value_json": {"percent": 80}, "condition_json": {}, "severity": "BLOCK", "exception_permitted": False, "source_document_id": "m2", "source_revision_id": "b"},
    ])
    assert conflicting and conflicting[0]["rule_code"] == "EXAM.PASS_MARK"
    assert set(conflicting[0]["rule_ids"]) == {"r1", "r2"}


def test_identical_rules_from_two_sources_do_not_create_false_conflict():
    assert rules.rule_conflicts([
        {"id": "r1", "rule_code": "CLASS.CAPACITY", "value_json": {"max": 20}, "condition_json": {}, "severity": "BLOCK", "exception_permitted": False},
        {"id": "r2", "rule_code": "CLASS.CAPACITY", "value_json": {"max": 20}, "condition_json": {}, "severity": "BLOCK", "exception_permitted": False},
    ]) == []


def test_effective_rules_honor_dates_and_applicability():
    rows = rules.effective_rules([
        {"id": "r1", "status": "ACTIVE", "rule_code": "RULE.A", "severity": "BLOCK", "effective_from": date(2026, 1, 1), "effective_to": None, "applicability": {"course_id": "course-a"}},
        {"id": "r2", "status": "ACTIVE", "rule_code": "RULE.B", "severity": "BLOCK", "effective_from": date(2027, 1, 1), "effective_to": None, "applicability": {"course_id": "course-a"}},
        {"id": "r3", "status": "ACTIVE", "rule_code": "RULE.C", "severity": "BLOCK", "effective_from": date(2026, 1, 1), "effective_to": None, "applicability": {"course_id": "course-b"}},
    ], on_date=date(2026, 8, 18), context={"course_id": "course-a"})
    assert [row["id"] for row in rows] == ["r1"]


def test_course_module_decimal_hours_must_reconcile():
    result = rules.course_revision_reconciliation(
        revision={"theory_hours": Decimal("2.50"), "practical_hours": Decimal("1.25"), "total_hours": Decimal("3.75")},
        modules=[{"theory_hours": Decimal("1.25"), "practical_hours": Decimal("0.50")}, {"theory_hours": Decimal("1.25"), "practical_hours": Decimal("0.75")}],
    )
    assert result["blockers"] == []
    assert result["total_hours"] == Decimal("3.75")


def test_course_module_hour_mismatch_blocks_activation():
    result = rules.course_revision_reconciliation(
        revision={"theory_hours": 2, "practical_hours": 1, "total_hours": 3},
        modules=[{"theory_hours": 1, "practical_hours": 1}],
    )
    assert len(result["blockers"]) == 2


def test_learner_missing_required_module_cannot_receive_certificate():
    result = rules.learner_completion_decision(required_module_ids=["m1", "m2"], completed_module_ids=["m1"], required_practical_task_ids=[], passed_practical_task_ids=[], required_assessments=[], passed_assessments=[])
    assert result["status"] == "MAKE_UP_REQUIRED"
    assert result["certificate_eligible"] is False


def test_practical_requirement_affects_completion():
    result = rules.learner_completion_decision(required_module_ids=["m1"], completed_module_ids=["m1"], required_practical_task_ids=["p1"], passed_practical_task_ids=[], required_assessments=[], passed_assessments=[])
    assert result["status"] == "PRACTICAL_INCOMPLETE"
    assert result["certificate_eligible"] is False


def test_examination_requirement_affects_completion():
    result = rules.learner_completion_decision(required_module_ids=[], completed_module_ids=[], required_practical_task_ids=[], passed_practical_task_ids=[], required_assessments=["exam"], passed_assessments=[])
    assert result["status"] == "EXAMINATION_INCOMPLETE"


def test_valid_cohort_can_be_batch_certified_safely():
    result = rules.batch_certificate_decisions([
        {"user_id": "u1", "status": "READY_FOR_CERTIFICATE", "certificate_eligible": True, "blockers": []},
        {"user_id": "u2", "status": "READY_FOR_CERTIFICATE", "certificate_eligible": True, "blockers": []},
    ])
    assert result == {"ready_user_ids": ["u1", "u2"], "blocked": [], "ready_count": 2, "blocked_count": 0}


def test_failed_cohort_member_stays_blocked_without_affecting_valid_members():
    result = rules.batch_certificate_decisions([
        {"user_id": "valid", "status": "READY_FOR_CERTIFICATE", "certificate_eligible": True, "blockers": []},
        {"user_id": "blocked", "status": "MAKE_UP_REQUIRED", "certificate_eligible": False, "blockers": ["m2"]},
    ])
    assert result["ready_user_ids"] == ["valid"]
    assert result["blocked"][0]["user_id"] == "blocked"


def test_compromised_question_cannot_enter_new_exam():
    reasons = rules.question_eligibility_reasons(
        {"status": "COMPROMISED"},
        {"status": "ACTIVE", "effective_from": date(2026, 1, 1), "effective_to": None, "source_revision_id": "rev-1"},
        on_date=date(2026, 8, 18),
    )
    assert any("COMPROMISED" in reason for reason in reasons)


def test_superseded_question_revision_cannot_enter_new_exam():
    reasons = rules.question_eligibility_reasons(
        {"status": "ACTIVE"},
        {"status": "ACTIVE", "effective_from": date(2026, 1, 1), "effective_to": date(2026, 8, 17), "source_revision_id": "rev-1"},
        on_date=date(2026, 8, 18),
    )
    assert any("superseded/expired" in reason for reason in reasons)


def test_question_without_controlled_source_revision_is_blocked():
    reasons = rules.question_eligibility_reasons({"status": "ACTIVE"}, {"status": "ACTIVE", "source_revision_id": None}, on_date=date(2026, 8, 18))
    assert any("no controlled source revision" in reason for reason in reasons)


def test_learner_question_projection_never_contains_answer_key():
    row = SimpleNamespace(id="qr-1", prompt="Which statement is correct?", options_json=["A", "B"], marks=Decimal("1"), answer_key_json={"answer": "A"}, explanation="private")
    payload = service.learner_question_projection(row)
    assert payload == {"question_revision_id": "qr-1", "prompt": "Which statement is correct?", "options": ["A", "B"], "marks": Decimal("1")}
    assert "answer_key_json" not in payload
    assert "explanation" not in payload


def test_authorisation_readiness_changes_when_dependency_expires():
    current = rules.technical_authorisation_reasons(auth(), on_date=date(2026, 8, 18), privilege_type="INSTRUCTOR", course_id="course-a", dependencies_satisfied=True)
    expired_dependency = rules.technical_authorisation_reasons(auth(), on_date=date(2026, 8, 18), privilege_type="INSTRUCTOR", course_id="course-a", dependencies_satisfied=False)
    assert current == []
    assert any("dependencies are not current" in reason for reason in expired_dependency)


def test_readiness_blocker_wins_over_warning_and_advisory():
    result = rules.readiness_result([
        {"code": "a", "satisfied": False, "severity": "WARNING"},
        {"code": "b", "satisfied": False, "severity": "BLOCK"},
        {"code": "c", "satisfied": False, "severity": "ADVISORY"},
    ])
    assert result["status"] == "BLOCKED"
    assert [row["code"] for row in result["blockers"]] == ["b"]


def test_ready_requires_no_unsatisfied_block_or_warning():
    result = rules.readiness_result([
        {"code": "a", "satisfied": True, "severity": "BLOCK"},
        {"code": "b", "satisfied": False, "severity": "ADVISORY"},
    ])
    assert result["status"] == "READY"
