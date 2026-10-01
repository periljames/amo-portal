"""Harden auditor workflow foundation and add immutable audit work packages.

Revision ID: quality_260930_auditor_foundation
Revises: workforce_260929_leave_gov
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_260930_auditor_foundation"
down_revision = "workforce_260929_leave_gov"
branch_labels = None
depends_on = None

DOC_META = "quality_audit_document_request_metadata"
EXECUTION = "quality_audit_checklist_execution_governance"
PARTICIPANT_EXECUTION = "quality_audit_fieldwork_participant_contributions"
WORK_PACKAGE = "quality_audit_work_packages"
AUDIT = "qms_audits"
EVIDENCE = "quality_audit_evidence_artifacts"
FINDING = "qms_audit_findings"
MEETING = "quality_audit_meetings"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy} ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql() or not _has_table(table_name):
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    audit_columns = _columns(AUDIT)
    if audit_columns and "objectives" not in audit_columns:
        op.add_column(AUDIT, sa.Column("objectives", sa.Text(), nullable=True))
    audit_columns = _columns(AUDIT)
    if audit_columns and "entity_version" not in audit_columns:
        op.add_column(AUDIT, sa.Column("entity_version", sa.Integer(), nullable=False, server_default="1"))
        op.create_check_constraint("ck_qms_audits_entity_version", AUDIT, "entity_version >= 1")

    finding_columns = _columns(FINDING)
    if finding_columns and "entity_version" not in finding_columns:
        op.add_column(FINDING, sa.Column("entity_version", sa.Integer(), nullable=False, server_default="1"))
        op.create_check_constraint("ck_qms_audit_findings_entity_version", FINDING, "entity_version >= 1")
    if finding_columns and "updated_at" not in finding_columns:
        op.add_column(FINDING, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(sa.text("UPDATE qms_audit_findings SET updated_at = created_at WHERE updated_at IS NULL"))
        op.alter_column(FINDING, "updated_at", nullable=False)

    columns = _columns(DOC_META)
    if columns and "responsible_party" not in columns:
        op.add_column(DOC_META, sa.Column("responsible_party", sa.String(length=255), nullable=True))
    if columns and "checklist_item_ids" not in columns:
        op.add_column(DOC_META, sa.Column("checklist_item_ids", sa.JSON(), nullable=False, server_default="[]"))
    if columns and "requirement_stage" not in columns:
        op.add_column(
            DOC_META,
            sa.Column(
                "requirement_stage",
                sa.String(length=32),
                nullable=False,
                server_default="REQUIRED_BEFORE_ISSUE",
            ),
        )
        op.create_check_constraint(
            "ck_quality_audit_doc_meta_requirement_stage",
            DOC_META,
            "requirement_stage IN ('REQUIRED_BEFORE_ISSUE','REQUIRED_BEFORE_FIELDWORK','REQUIRED_DURING_FIELDWORK','REQUESTED_NOT_BLOCKING')",
        )

    meeting_columns = _columns(MEETING)
    if meeting_columns and "auditee_department" not in meeting_columns:
        op.add_column(MEETING, sa.Column("auditee_department", sa.String(length=255), nullable=True))
    if meeting_columns and "auditor_user_id" not in meeting_columns:
        op.add_column(MEETING, sa.Column("auditor_user_id", sa.String(length=36), nullable=True))
        op.create_foreign_key("fk_quality_audit_meeting_auditor", MEETING, "users", ["auditor_user_id"], ["id"], ondelete="SET NULL")

    execution_columns = _columns(EXECUTION)
    if execution_columns and "response_value" not in execution_columns:
        op.add_column(EXECUTION, sa.Column("response_value", sa.String(length=64), nullable=True))
    execution_columns = _columns(EXECUTION)
    if execution_columns and "auditee_comments" not in execution_columns:
        op.add_column(EXECUTION, sa.Column("auditee_comments", sa.Text(), nullable=True))
    if execution_columns and "sampled_item_information" not in execution_columns:
        op.add_column(EXECUTION, sa.Column("sampled_item_information", sa.Text(), nullable=True))
    if execution_columns and "applicability" not in execution_columns:
        op.add_column(EXECUTION, sa.Column("applicability", sa.String(length=128), nullable=False, server_default="APPLICABLE"))

    evidence_columns = _columns(EVIDENCE)
    if evidence_columns and "evidence_request_id" not in evidence_columns:
        op.add_column(EVIDENCE, sa.Column("evidence_request_id", sa.Uuid(), nullable=True))
        op.create_foreign_key("fk_quality_audit_evidence_request", EVIDENCE, "quality_audit_document_requests", ["evidence_request_id"], ["id"], ondelete="SET NULL")
    if evidence_columns and "source_device_id" not in evidence_columns:
        op.add_column(EVIDENCE, sa.Column("source_device_id", sa.String(length=128), nullable=True))
    if evidence_columns and "captured_at" not in evidence_columns:
        op.add_column(EVIDENCE, sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True))
    if evidence_columns and "offline_upload_state" not in evidence_columns:
        op.add_column(EVIDENCE, sa.Column("offline_upload_state", sa.String(length=16), nullable=False, server_default="SYNCED"))
        op.create_check_constraint("ck_quality_audit_evidence_upload_state", EVIDENCE, "offline_upload_state IN ('SYNCED','PENDING','FAILED','CONFLICT')")
    if evidence_columns and "server_processing_state" not in evidence_columns:
        op.add_column(EVIDENCE, sa.Column("server_processing_state", sa.String(length=16), nullable=False, server_default="AVAILABLE"))
        op.create_check_constraint("ck_quality_audit_evidence_processing_state", EVIDENCE, "server_processing_state IN ('AVAILABLE','PROCESSING','FAILED')")

    participant_columns = _columns(PARTICIPANT_EXECUTION)
    if participant_columns and "response_value" not in participant_columns:
        op.add_column(PARTICIPANT_EXECUTION, sa.Column("response_value", sa.String(length=64), nullable=True))

    if not _has_table(WORK_PACKAGE):
        op.create_table(
            WORK_PACKAGE,
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("audit_id", sa.Uuid(), nullable=False),
            sa.Column("preparation_revision_id", sa.String(length=36), nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("package_snapshot", sa.JSON(), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("offline_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("supersedes_work_package_id", sa.String(length=36), nullable=True),
            sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_work_package_revision_no"),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["preparation_revision_id"],
                ["quality_audit_preparation_revisions.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["supersedes_work_package_id"],
                [f"{WORK_PACKAGE}.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "amo_id",
                "audit_id",
                "revision_no",
                name="uq_quality_audit_work_package_revision",
            ),
            sa.UniqueConstraint(
                "amo_id",
                "preparation_revision_id",
                name="uq_quality_audit_work_package_preparation",
            ),
        )
        op.create_index(
            "ix_quality_audit_work_package_audit",
            WORK_PACKAGE,
            ["amo_id", "audit_id", "revision_no"],
        )
        op.create_index(
            "ix_quality_audit_work_package_sha",
            WORK_PACKAGE,
            ["amo_id", "content_sha256"],
        )
        _enable_rls(WORK_PACKAGE)

        if _is_postgresql():
            op.execute(sa.text("""
                CREATE OR REPLACE FUNCTION prevent_quality_audit_work_package_mutation()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'issued audit work packages are immutable';
                END;
                $$ LANGUAGE plpgsql;
            """))
            op.execute(sa.text(f"""
                CREATE TRIGGER trg_quality_audit_work_package_immutable
                BEFORE UPDATE OR DELETE ON {WORK_PACKAGE}
                FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_work_package_mutation();
            """))


def downgrade() -> None:
    audit_columns = _columns(AUDIT)
    if audit_columns and "entity_version" in audit_columns:
        op.drop_constraint("ck_qms_audits_entity_version", AUDIT, type_="check")
        op.drop_column(AUDIT, "entity_version")
    audit_columns = _columns(AUDIT)
    if audit_columns and "objectives" in audit_columns:
        op.drop_column(AUDIT, "objectives")

    if _has_table(WORK_PACKAGE):
        if _is_postgresql():
            op.execute(sa.text(
                f"DROP TRIGGER IF EXISTS trg_quality_audit_work_package_immutable ON {WORK_PACKAGE}"
            ))
            op.execute(sa.text(
                "DROP FUNCTION IF EXISTS prevent_quality_audit_work_package_mutation()"
            ))
        _disable_rls(WORK_PACKAGE)
        op.drop_index("ix_quality_audit_work_package_sha", table_name=WORK_PACKAGE)
        op.drop_index("ix_quality_audit_work_package_audit", table_name=WORK_PACKAGE)
        op.drop_table(WORK_PACKAGE)

    evidence_columns = _columns(EVIDENCE)
    if evidence_columns and "server_processing_state" in evidence_columns:
        op.drop_constraint("ck_quality_audit_evidence_processing_state", EVIDENCE, type_="check")
        op.drop_column(EVIDENCE, "server_processing_state")
    if evidence_columns and "offline_upload_state" in evidence_columns:
        op.drop_constraint("ck_quality_audit_evidence_upload_state", EVIDENCE, type_="check")
        op.drop_column(EVIDENCE, "offline_upload_state")
    if evidence_columns and "captured_at" in evidence_columns:
        op.drop_column(EVIDENCE, "captured_at")
    if evidence_columns and "source_device_id" in evidence_columns:
        op.drop_column(EVIDENCE, "source_device_id")
    if evidence_columns and "evidence_request_id" in evidence_columns:
        op.drop_constraint("fk_quality_audit_evidence_request", EVIDENCE, type_="foreignkey")
        op.drop_column(EVIDENCE, "evidence_request_id")

    participant_columns = _columns(PARTICIPANT_EXECUTION)
    if participant_columns and "response_value" in participant_columns:
        op.drop_column(PARTICIPANT_EXECUTION, "response_value")

    meeting_columns = _columns(MEETING)
    if meeting_columns and "auditor_user_id" in meeting_columns:
        op.drop_constraint("fk_quality_audit_meeting_auditor", MEETING, type_="foreignkey")
        op.drop_column(MEETING, "auditor_user_id")
    if meeting_columns and "auditee_department" in meeting_columns:
        op.drop_column(MEETING, "auditee_department")

    execution_columns = _columns(EXECUTION)
    if execution_columns and "applicability" in execution_columns:
        op.drop_column(EXECUTION, "applicability")
    if execution_columns and "sampled_item_information" in execution_columns:
        op.drop_column(EXECUTION, "sampled_item_information")
    if execution_columns and "auditee_comments" in execution_columns:
        op.drop_column(EXECUTION, "auditee_comments")
    if execution_columns and "response_value" in execution_columns:
        op.drop_column(EXECUTION, "response_value")

    finding_columns = _columns(FINDING)
    if finding_columns and "updated_at" in finding_columns:
        op.drop_column(FINDING, "updated_at")
    if finding_columns and "entity_version" in finding_columns:
        op.drop_constraint("ck_qms_audit_findings_entity_version", FINDING, type_="check")
        op.drop_column(FINDING, "entity_version")

    columns = _columns(DOC_META)
    if columns and "checklist_item_ids" in columns:
        op.drop_column(DOC_META, "checklist_item_ids")
    if columns and "responsible_party" in columns:
        op.drop_column(DOC_META, "responsible_party")
    if columns and "requirement_stage" in columns:
        op.drop_constraint(
            "ck_quality_audit_doc_meta_requirement_stage",
            DOC_META,
            type_="check",
        )
        op.drop_column(DOC_META, "requirement_stage")
