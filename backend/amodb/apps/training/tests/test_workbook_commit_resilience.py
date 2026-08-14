from __future__ import annotations

import unittest
from pathlib import Path


TRAINING_DIR = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (TRAINING_DIR / name).read_text(encoding="utf-8")


class WorkbookCommitResilienceTests(unittest.TestCase):
    def test_people_row_failure_exits_atomic_context_before_more_sql(self) -> None:
        importer = source("workbook_import.py")
        people_block = importer.split("# Personnel + explicit access decisions", 1)[1].split("# Applicability groups", 1)[0]
        self.assertIn("with work_db.begin_nested():", people_block)
        self.assertIn("raise WorkbookRowCommitError", people_block)
        self.assertNotIn('item.issue_code = "PERSON_COMMIT_FAILED"', people_block)

    def test_identity_integrity_race_returns_to_review(self) -> None:
        importer = source("workbook_import.py")
        self.assertIn("except IntegrityError as exc:", importer)
        self.assertIn("raise PersonnelIdentityChanged", importer)
        self.assertIn('row.status = "REVIEW"', importer)
        self.assertIn('row.decision = None', importer)
        self.assertIn("_refresh_identity_review_options", importer)

    def test_commit_hot_path_uses_preloaded_indexes_and_one_inactive_hash(self) -> None:
        importer = source("workbook_import.py")
        self.assertIn("_build_personnel_commit_indexes", importer)
        self.assertIn("courses_by_code=courses", importer)
        self.assertIn("assignments = {", importer)
        self.assertIn("rules = {", importer)
        self.assertIn("inactive_password_hash = get_password_hash", importer)
        self.assertIn("inactive_password_hash=inactive_password_hash", importer)

    def test_training_lifecycle_reuses_preloaded_records(self) -> None:
        records = source("records_import.py")
        self.assertIn("preloaded_rows", records)
        self.assertIn("records_by_pair", records)
        self.assertIn("preloaded_rows=records_by_pair.get", records)

    def test_training_rows_are_staged_historical_before_latest_is_promoted(self) -> None:
        records = source("records_import.py")
        create_block = records.split("record = models.TrainingRecord(", 1)[1].split("db.add(record)", 1)[0]
        self.assertIn('record_status="RENEWED"', create_block)
        self.assertIn("_stage_record_lifecycle", records)
        self.assertIn("_activate_latest_records", records)
        self.assertLess(records.index("db.flush()\n        _activate_latest_records"), records.index("_activate_latest_records(db, latest_records)\n        db.flush()"))

    def test_training_lifecycle_updates_database_fields_not_only_remarks(self) -> None:
        records = source("records_import.py")
        lifecycle = records.split("def _stage_record_lifecycle", 1)[1].split("def _activate_latest_records", 1)[0]
        self.assertIn('row.record_status = "RENEWED"', lifecycle)
        self.assertIn("row.superseded_by_record_id = latest.id", lifecycle)
        self.assertIn("row.superseded_at = now", lifecycle)
        activation = records.split("def _activate_latest_records", 1)[1].split("def import_training_records_rows", 1)[0]
        self.assertIn('latest.record_status = "ACTIVE"', activation)
        self.assertIn("latest.superseded_by_record_id = None", activation)

    def test_training_import_batches_new_row_flushes(self) -> None:
        records = source("records_import.py")
        create_path = records.split("if existing is None:", 1)[1].split("else:\n            action = \"UNCHANGED\"", 1)[0]
        self.assertIn("id=generate_user_id()", create_path)
        self.assertNotIn("db.flush()", create_path)

    def test_progress_is_batched_and_summary_reports_created_accounts(self) -> None:
        importer = source("workbook_import.py")
        self.assertIn("COMMIT_PROGRESS_BATCH", importer)
        self.assertIn('"portal_accounts_created": accounts_created', importer)
        self.assertIn('"elapsed_ms"', importer)

    def test_commit_workers_are_fenced_by_a_durable_attempt_token(self) -> None:
        importer = source("workbook_import.py")
        self.assertIn("new_commit_attempt_token", importer)
        self.assertIn("WorkbookCommitLeaseLost", importer)
        self.assertIn("_require_commit_lease", importer)
        self.assertIn("TrainingWorkbookImportJob.status == \"QUEUED_COMMIT\"", importer)
        self.assertIn("_commit_attempt_token(job) != attempt_token", importer)

    def test_stale_commit_is_requeued_after_database_or_process_restart(self) -> None:
        router = source("workbook_router.py")
        self.assertIn("_recover_stale_commit", router)
        self.assertIn("TRAINING_WORKBOOK_STALE_COMMIT_SECONDS", router)
        self.assertIn('TrainingWorkbookImportJob.stage: "RECOVERING_COMMIT"', router)
        self.assertIn("automatic_recovery_attempts", router)
        self.assertIn("background_tasks.add_task", router)

    def test_final_row_reconciliation_is_bulk_written(self) -> None:
        importer = source("workbook_import.py")
        finalization = importer.split("# Persist all row outcomes", 1)[1].split("# Keep the current-year", 1)[0]
        self.assertIn("bulk_update_mappings", finalization)
        self.assertNotIn("progress_db.get(TrainingWorkbookImportRow", finalization)

    def test_database_restart_is_reported_as_retryable_service_unavailable(self) -> None:
        main = (TRAINING_DIR.parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn("except OperationalError:", main)
        self.assertIn('"error_code": "DB_TEMPORARILY_UNAVAILABLE"', main)
        self.assertIn('headers={"Retry-After": "3"}', main)

    def test_licence_category_scope_is_not_limited_to_255_characters(self) -> None:
        models = source("workbook_models.py")
        importer = source("workbook_import.py")
        self.assertIn("category_code = Column(Text, nullable=True)", models)
        self.assertIn("LICENCE_CATEGORY_MAX_CHARS", importer)
        self.assertIn('_licence_category(raw.get("Category (Reg. 2013)")', importer)
        self.assertIn('_licence_category(raw.get("Category (Reg. 2018)")', importer)

    def test_licence_category_migration_extends_the_current_training_head(self) -> None:
        migration = (
            TRAINING_DIR.parents[1]
            / "alembic"
            / "versions"
            / "training_20260814_licence_category_text.py"
        ).read_text(encoding="utf-8")
        self.assertIn('revision = "training_20260814_licence_text"', migration)
        self.assertIn('down_revision = "training_20260813_readiness_audit"', migration)
        self.assertIn("type_=sa.Text()", migration)
        self.assertIn("char_length(category_code) > 255", migration)


if __name__ == "__main__":
    unittest.main()
