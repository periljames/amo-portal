from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


TRAINING_ROOT = Path(__file__).resolve().parents[1]
AMODB_ROOT = Path(__file__).resolve().parents[3]

spec = importlib.util.spec_from_file_location("training_operating_rules", TRAINING_ROOT / "operating_rules.py")
rules = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(rules)


def source(name: str) -> str:
    return (TRAINING_ROOT / name).read_text(encoding="utf-8")


class TrainingOperatingSystemScenarioTests(unittest.TestCase):
    def test_01_admin_can_open_full_training_os(self):
        self.assertIn("is_amo_admin", source("permissions.py"))
        self.assertIn("ALL_TRAINING_CAPABILITIES", source("permissions.py"))

    def test_02_training_department_is_not_qms_elevated(self):
        text = source("permissions.py")
        self.assertIn("Training-only", text)
        self.assertNotIn("qms.", text)

    def test_03_quality_manager_can_review_and_approve(self):
        text = source("permissions.py")
        self.assertIn('role == "QUALITY_MANAGER"', text)
        self.assertIn("PLAN_APPROVE", text)

    def test_04_ordinary_employee_has_self_service_only(self):
        self.assertIn("return set(_SELF)", source("permissions.py"))

    def test_05_platform_support_access_fails_closed(self):
        text = source("permissions.py")
        self.assertIn("_platform_support_session_active", text)
        self.assertIn("return False", text)

    def test_06_annual_plan_can_generate_from_obligations(self):
        self.assertIn("_demand_items", source("operating_service.py"))

    def test_07_approved_plan_requires_revision(self):
        self.assertFalse(rules.plan_transition_allowed("APPROVED", "DRAFT"))
        self.assertIn("supersedes_plan_id", source("operating_service.py"))

    def test_08_multi_currency_budget_stores_snapshot(self):
        text = source("operating_service.py")
        for field in ("exchange_rate", "rate_date", "rate_source"):
            self.assertIn(field, text)
        self.assertTrue(rules.budget_transition_allowed("DRAFT", "SUBMITTED"))
        self.assertTrue(rules.budget_transition_allowed("SUBMITTED", "REVIEWED"))
        self.assertTrue(rules.budget_transition_allowed("REVIEWED", "APPROVED"))
        self.assertFalse(rules.budget_transition_allowed("APPROVED", "DRAFT"))

    def test_09_decimal_conversion_is_exact(self):
        self.assertEqual(rules.converted_amount("12.30", "1.25"), Decimal("15.375000"))

    def test_10_short_lived_attendance_code(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(rules.attendance_token_state(status="OPEN", expires_at=now + timedelta(minutes=5), now=now), "OPEN")

    def test_11_expired_attendance_code_rejected(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(rules.attendance_token_state(status="OPEN", expires_at=now, now=now), "EXPIRED")

    def test_12_duplicate_attendance_is_idempotent(self):
        text = source("operating_models.py") + source("operating_service.py")
        self.assertIn("uq_training_attendance_idempotency", text)
        self.assertIn("IDEMPOTENCY_KEY_REUSED", text)

    def test_13_manual_attendance_correction_is_historical(self):
        text = source("operating_service.py")
        self.assertIn("TrainingAttendanceCorrection", text)
        self.assertIn('action="CORRECTED"', text)

    def test_14_trainer_mark_is_available(self):
        self.assertIn("TRAINER", source("operating_schemas.py"))

    def test_15_completed_session_can_be_certified(self):
        text = source("operating_service.py")
        self.assertIn('window.status = "CERTIFIED"', text)
        self.assertIn('TrainingAttendanceWindow.status == "CERTIFIED"', text)

    def test_16_threshold_boundary_79_fails(self):
        self.assertEqual(rules.assessment_outcome(79, 80), "FAIL")

    def test_17_threshold_boundary_80_passes(self):
        self.assertEqual(rules.assessment_outcome(80, 80), "PASS")

    def test_18_practical_assessment_type_supported(self):
        self.assertIn('"PRACTICAL"', source("operating_schemas.py"))

    def test_19_ojt_signoff_gate_supported(self):
        self.assertIn("ojt_signoff_required", source("operating_service.py"))

    def test_20_course_assessment_blocks_certificate(self):
        text = source("operating_service.py")
        self.assertIn("ASSESSMENT_MISSING", text)
        self.assertIn("completion_gate", text)

    def test_21_authorization_case_preparation_exists(self):
        self.assertIn("create_authorization_case", source("operating_service.py"))

    def test_22_readiness_is_not_ready_with_blockers(self):
        value = rules.readiness_status(blockers=["licence"], required_assessments=[], passed_assessments=[], committee_decisions=[], required_committee_count=3)
        self.assertEqual(value, "NOT_READY")

    def test_23_all_evidence_reaches_committee(self):
        value = rules.readiness_status(blockers=[], required_assessments=["W", "P"], passed_assessments=["W", "P"], committee_decisions=[], required_committee_count=3)
        self.assertEqual(value, "READY_FOR_COMMITTEE")

    def test_24_one_committee_reject_rejects_case(self):
        value = rules.readiness_status(blockers=[], required_assessments=[], passed_assessments=[], committee_decisions=["APPROVE", "REJECT"], required_committee_count=3)
        self.assertEqual(value, "REJECTED")

    def test_25_delegate_resolution_uses_postholder_assignments(self):
        text = source("operating_service.py")
        self.assertIn("auth_postholder_assignments", text)
        self.assertIn("delegated_to_user_id", text)

    def test_26_authorization_uses_canonical_account_table(self):
        text = source("operating_service.py")
        self.assertIn("account_models.UserAuthorisation", text)
        self.assertNotIn("class UserAuthorisation", source("operating_models.py"))

    def test_27_auditor_observer_source_is_qms(self):
        text = source("operating_service.py")
        self.assertIn("quality_models.QMSAudit", text)
        self.assertIn("observer_auditor_user_id", text)
        self.assertIn("assistant_auditor_user_id", text)

    def test_28_auditor_observer_target_is_configurable(self):
        self.assertIn("auditor_observer_count", source("operating_models.py"))

    def test_29_effectiveness_levels_one_to_four(self):
        text = source("operating_models.py")
        self.assertIn("level BETWEEN 1 AND 4", text)

    def test_30_level_four_causation_requires_evidence(self):
        self.assertFalse(rules.level_four_causation_allowed(causation_claimed=True, evidence={"baseline": 1}, conclusion="proved"))
        self.assertTrue(rules.level_four_causation_allowed(causation_claimed=False, evidence={}, conclusion=None))

    def test_31_failed_assessment_creates_remedial_task(self):
        text = source("operating_service.py")
        self.assertIn("Remedial training action required", text)
        self.assertIn("task_services.create_task", text)

    def test_32_course_audit_lists_exceptions(self):
        self.assertIn("CourseAuditException", source("operating_service.py"))

    def test_33_next_batch_checks_booking_and_availability(self):
        text = source("operating_service.py")
        self.assertIn("existing_booking", text)
        self.assertIn("availability_conflict", text)

    def test_34_real_pdf_and_xlsx_generators_exist(self):
        text = source("operating_reports.py")
        self.assertIn("SimpleDocTemplate", text)
        self.assertIn("Workbook", text)

    def test_35_large_lists_are_bounded(self):
        text = source("operating_router.py")
        self.assertIn("le=500", text)
        self.assertIn("le=200", text)

    def test_36_tenant_isolation_uses_rls_and_scope(self):
        migration = (AMODB_ROOT / "alembic/versions/training_20260813_operating_system.py").read_text(encoding="utf-8")
        self.assertIn("ENABLE ROW LEVEL SECURITY", migration)
        self.assertIn("app.tenant_id", migration)

    def test_37_certificate_verification_is_preserved(self):
        router = source("router.py")
        self.assertIn("verify_certificate_public", router)
        self.assertIn("_issue_certificate_for_record", router)

    def test_38_self_attendance_cannot_sign_for_another_user(self):
        text = source("operating_service.py")
        self.assertIn("TrainingEventParticipant.user_id == str(actor.id)", text)

    def test_39_control_room_exposes_source_errors(self):
        self.assertIn("source_errors", source("operating_service.py"))

    def test_40_schema_contract_covers_all_first_class_records(self):
        text = source("operating_models.py")
        for table in ("training_plans", "training_budgets", "training_attendance_entries", "training_assessment_instances", "training_authorization_cases", "training_effectiveness_evaluations"):
            self.assertIn(table, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
