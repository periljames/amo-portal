"""complete canonical qms tenant-scoped tables and RLS

Revision ID: qms_p2_20260426
Revises: qms_p1_rls_20260426
Create Date: 2026-04-26

This migration completes the canonical QMS storage layer used by
/api/maintenance/{amo_code}/qms. It is intentionally additive and production-safe:
existing tables are not dropped; missing tenant/common columns are added; RLS is enabled
where an amo_id column is present.
"""
from __future__ import annotations

from alembic import op


revision = "qms_p2_20260426"
down_revision = "qms_p1_rls_20260426"
branch_labels = None
depends_on = None


TENANT_TABLES = ['qms_processes', 'qms_process_owners', 'qms_quality_policy', 'qms_quality_objectives', 'qms_context_items', 'qms_interested_parties', 'qms_risks', 'qms_risk_controls', 'qms_risk_actions', 'qms_opportunities', 'qms_document_versions', 'qms_document_sections', 'qms_document_change_requests', 'qms_document_approvals', 'qms_document_approval_letters', 'qms_document_distribution', 'qms_document_acknowledgements', 'qms_document_templates', 'qms_document_obsolete_records', 'qms_audit_programs', 'qms_audit_team_members', 'qms_audit_notices', 'qms_audit_scopes', 'qms_audit_war_room_files', 'qms_audit_checklists', 'qms_audit_checklist_items', 'qms_audit_evidence', 'qms_audit_reports', 'qms_audit_post_briefs', 'qms_audit_archives', 'qms_findings', 'qms_finding_sources', 'qms_finding_evidence', 'qms_finding_classifications', 'qms_finding_links', 'qms_car_root_causes', 'qms_car_containment_actions', 'qms_car_corrective_action_plans', 'qms_car_action_items', 'qms_car_evidence', 'qms_car_reviews', 'qms_car_effectiveness_reviews', 'qms_car_closure_records', 'qms_car_rejections', 'qms_training_courses', 'qms_training_requirements', 'qms_training_records', 'qms_competence_matrix', 'qms_competence_gaps', 'qms_training_evaluations', 'qms_suppliers', 'qms_supplier_approvals', 'qms_supplier_scopes', 'qms_supplier_evaluations', 'qms_supplier_audits', 'qms_supplier_findings', 'qms_supplier_documents', 'qms_supplier_performance_scores', 'qms_equipment', 'qms_calibration_records', 'qms_calibration_certificates', 'qms_equipment_status_history', 'qms_out_of_tolerance_events', 'qms_management_reviews', 'qms_management_review_inputs', 'qms_management_review_minutes', 'qms_management_review_decisions', 'qms_management_review_actions', 'qms_management_review_approvals', 'qms_tasks', 'qms_task_assignments', 'qms_task_comments', 'qms_notifications', 'qms_activity_logs', 'qms_evidence_files', 'qms_archive_packages', 'qms_archive_package_items', 'qms_retention_rules', 'qms_file_hashes', 'qms_file_access_logs', 'qms_settings', 'qms_numbering_rules', 'qms_workflow_rules', 'qms_approval_matrix', 'qms_notification_rules', 'qms_templates', 'qms_form_definitions', 'qms_metric_definitions', 'qms_dashboard_widgets', 'qms_report_definitions', 'qms_report_exports', 'qms_change_controls', 'qms_external_items', 'qms_regulator_findings', 'qms_customer_complaints', 'qms_customer_feedback', 'qms_authority_correspondence', 'qms_external_responses', 'qms_external_commitments', 'qms_external_audits']


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _create_or_harden_table(table: str) -> None:
    quoted = _q(table)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {quoted} (
            id varchar(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            amo_id varchar(36) NOT NULL REFERENCES amos(id) ON DELETE CASCADE,
            title varchar(255),
            name varchar(255),
            status varchar(64) NOT NULL DEFAULT 'OPEN',
            owner_user_id varchar(36),
            due_date date,
            description text,
            source_type varchar(96),
            file_name varchar(255),
            file_path text,
            storage_path text,
            sha256 varchar(128),
            mime_type varchar(128),
            size_bytes bigint,
            payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            created_by varchar(36),
            updated_at timestamptz,
            updated_by varchar(36),
            deleted_at timestamptz
        )
    """)
    for column_sql in (
        "amo_id varchar(36)",
        "title varchar(255)",
        "name varchar(255)",
        "status varchar(64) DEFAULT 'OPEN'",
        "owner_user_id varchar(36)",
        "due_date date",
        "description text",
        "source_type varchar(96)",
        "file_name varchar(255)",
        "file_path text",
        "storage_path text",
        "sha256 varchar(128)",
        "mime_type varchar(128)",
        "size_bytes bigint",
        "payload jsonb DEFAULT '{}'::jsonb",
        "created_at timestamptz DEFAULT now()",
        "created_by varchar(36)",
        "updated_at timestamptz",
        "updated_by varchar(36)",
        "deleted_at timestamptz",
    ):
        op.execute(f"ALTER TABLE {quoted} ADD COLUMN IF NOT EXISTS {column_sql}")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_amo_id ON {quoted} (amo_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_amo_status ON {quoted} (amo_id, status)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_amo_due ON {quoted} (amo_id, due_date)")
    op.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {quoted}")
    op.execute(f"""
        CREATE POLICY {table}_tenant_isolation
        ON {quoted}
        USING (amo_id = current_setting('app.tenant_id', true))
        WITH CHECK (amo_id = current_setting('app.tenant_id', true))
    """)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for table in TENANT_TABLES:
        _create_or_harden_table(table)


def downgrade() -> None:
    # Do not drop production QMS data automatically.
    for table in TENANT_TABLES:
        quoted = _q(table)
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {quoted}")
        op.execute(f"ALTER TABLE {quoted} DISABLE ROW LEVEL SECURITY")
