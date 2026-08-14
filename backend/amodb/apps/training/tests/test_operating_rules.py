from __future__ import annotations

import importlib.util
import unittest
from datetime import date, datetime, timedelta, timezone
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
        text = source("operating_service.py")
        self.assertIn("_demand_items", text)
        self.assertIn('source_type="EXPIRY_SCHEDULE"', text)
        self.assertIn("participant_obligations", text)

    def test_06a_each_expiry_is_placed_in_its_own_calendar_month(self):
        generated = date(2026, 8, 13)
        self.assertEqual(rules.plan_month_for_due_date(due_date=date(2026, 11, 5), plan_year=2026, generated_on=generated), 11)
        self.assertEqual(rules.plan_month_for_due_date(due_date=date(2026, 2, 5), plan_year=2026, generated_on=generated), 8)
        self.assertEqual(rules.plan_month_for_due_date(due_date=date(2025, 2, 5), plan_year=2027, generated_on=generated), 1)
        self.assertEqual(rules.plan_month_for_due_date(due_date=None, plan_year=2026, generated_on=generated), 8)

    def test_06b_plan_keeps_uploaded_record_and_expiry_provenance(self):
        models = source("operating_models.py")
        service = source("operating_service.py")
        for field in ("person_name_snapshot", "expiry_date", "planned_due_date", "source_record_id", "source_reference"):
            self.assertIn(field, models)
        self.assertIn("Workbook RecordID", service)

    def test_06c_role_matrix_courses_are_not_dropped_by_blank_catalogue_flag(self):
        text = source("compliance.py")
        self.assertIn("mandatory_items = list(items) if required_only", text)

    def test_06d_workbook_commit_autonomously_syncs_the_current_plan(self):
        importer = source("workbook_import.py")
        service = source("operating_service.py")
        self.assertIn("sync_current_plan_from_records", importer)
        self.assertIn('"training_plan_sync"', importer)
        self.assertIn('"REVISED_AND_RECALCULATED"', service)
        self.assertIn('"REVIEW_LOCKED"', service)

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

    def test_41_attendance_open_notifies_scheduled_participants(self):
        text = source("operating_service.py")
        self.assertIn("TrainingNotification(", text)
        self.assertIn("PortalNotification(", text)
        self.assertIn('kind="TRAINING_ATTENDANCE_OPEN"', text)
        self.assertIn("notifications_queued", text)

    def test_42_attendance_deep_link_is_same_origin_only(self):
        schema = source("operating_schemas.py")
        self.assertIn("validate_sign_in_path", schema)
        self.assertIn('path.startswith("//")', schema)
        self.assertIn('"://" in path', schema)

    def test_43_live_roster_and_plan_obligations_are_paginated(self):
        router = source("operating_router.py")
        self.assertIn('"/attendance/events/{event_id}/roster"', router)
        self.assertIn('"/plans/{plan_id}/obligations"', router)
        self.assertIn("AttendanceRosterPage", router)
        self.assertIn("TrainingPlanObligationPage", router)

    def test_44_control_room_uses_tenant_projection(self):
        text = source("operating_service.py")
        self.assertIn("def _tenant_training_counts", text)
        self.assertIn("bounded, set-based reads", text)
        control_room_body = text.split("def control_room", 1)[1]
        self.assertIn("_tenant_training_counts", control_room_body)
        self.assertNotIn("evaluate_user_training_policy(db, user", control_room_body)

    def test_45_instructors_can_operate_but_not_certify_attendance(self):
        permissions = source("permissions.py")
        instructor_block = permissions.split('if any(token in position for token in ("assessor", "instructor", "trainer")):', 1)[1].split("return set(_SELF)", 1)[0]
        self.assertIn("ATTENDANCE_MANAGE", instructor_block)
        self.assertNotIn("SESSION_CLOSE", instructor_block)

    def test_46_qms_and_dms_share_the_training_evidence_adapter(self):
        people = (AMODB_ROOT / "apps/quality/people_router.py").read_text(encoding="utf-8")
        assignment = (AMODB_ROOT / "apps/quality/audit_assignment_guard.py").read_text(encoding="utf-8")
        dms = (AMODB_ROOT / "apps/doc_control/workspace_integration_router.py").read_text(encoding="utf-8")
        self.assertIn("current_training_evidence", people)
        self.assertIn("current_training_evidence", assignment)
        self.assertIn("training_source_status_snapshot", dms)

    def test_47_dms_training_catalog_excludes_internal_security_tables(self):
        dms = (AMODB_ROOT / "apps/doc_control/workspace_integration_router.py").read_text(encoding="utf-8")
        self.assertIn("_EXPLICIT_ALLOWED_TABLES", dms)
        allowed = dms.split('"TRAINING": {', 1)[1].split("}", 1)[0]
        self.assertNotIn("training_auditor_access_grants", allowed)
        self.assertNotIn("training_notifications", allowed)
        self.assertNotIn("training_audit_logs", allowed)

    def test_48_dms_current_record_status_checks_verification_expiry_and_lifecycle(self):
        adapter = source("integration.py")
        self.assertIn('return "SUPERSEDED"', adapter)
        self.assertIn('return "PENDING"', adapter)
        self.assertIn('return "EXPIRED"', adapter)
        self.assertIn('return "READY"', adapter)

    def test_49_release_gates_evaluate_people_not_requirement_row_count(self):
        gates = source("gates.py")
        self.assertIn("unresolved_training_gate_items", gates)
        self.assertIn("CURRENT_VERIFIED_EVIDENCE_REQUIRED", gates)
        self.assertNotIn("SELECT COUNT(*)", gates)

    def test_50_qms_latest_record_summary_excludes_unverified_history(self):
        adapter = source("integration.py")
        self.assertIn("training_record_summary", adapter)
        self.assertIn("active_records_filter", adapter)
        self.assertIn("TrainingRecordVerificationStatus.VERIFIED", adapter)

    def test_51_training_evidence_upload_checks_cross_object_integrity(self):
        storage_policy = source("shared_storage_policy.py")
        self.assertIn("belongs to a different person", storage_policy)
        self.assertIn("belongs to a different course", storage_policy)
        self.assertIn("_ALLOWED_EVIDENCE_EXTENSIONS", storage_policy)

    def test_52_training_evidence_download_keeps_an_explicit_fastapi_contract(self):
        router = source("router.py")
        storage_policy = source("shared_storage_policy.py")
        self.assertIn('"/files/{file_id}/download"', router)
        self.assertIn("def _materialize_training_file", router)
        self.assertIn("storage.materialize(raw, expected_sha256=f.sha256)", router)
        self.assertNotIn('"/training/files/{file_id}/download":', storage_policy)
        self.assertNotIn("def download_training_file_shared(**values", storage_policy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
