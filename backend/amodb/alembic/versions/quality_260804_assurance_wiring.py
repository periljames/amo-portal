"""Wire continuous assurance to authoritative QMS records.

Revision ID: quality_260804_assurance_wiring
Revises: quality_260804_assurance_rls
Create Date: 2026-08-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260804_assurance_wiring"
down_revision = "quality_260804_assurance_rls"
branch_labels = None
depends_on = None


_EVENT_SOURCES: tuple[tuple[str, str], ...] = (
    ("qms_audits", "AUDIT"),
    ("qms_audit_schedules", "AUDIT_SCHEDULE"),
    ("qms_audit_findings", "FINDING"),
    ("quality_cars", "CAR"),
    ("qms_documents", "DOCUMENT"),
    ("training_records", "TRAINING"),
    ("qms_suppliers", "SUPPLIER"),
    ("qms_supplier_approvals", "SUPPLIER_APPROVAL"),
    ("qms_calibration_records", "CALIBRATION"),
    ("qms_calibration_certificates", "CALIBRATION_CERTIFICATE"),
    ("qms_equipment", "EQUIPMENT"),
    ("qms_risks", "RISK"),
    ("qms_change_controls", "CHANGE"),
    ("qms_management_review_actions", "MANAGEMENT_REVIEW_ACTION"),
    ("qms_regulator_findings", "REGULATOR_FINDING"),
    ("qms_external_commitments", "EXTERNAL_COMMITMENT"),
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _policy_name(table_name: str) -> str:
    return f"{table_name}_amo_isolation"


def _enable_rls(table_name: str) -> None:
    policy_name = _policy_name(table_name)
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY {policy_name}
            ON "{table_name}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            """
        )
    )


def upgrade() -> None:
    op.add_column(
        "quality_assurance_controls",
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "quality_assurance_controls",
        sa.Column("approval_status", sa.String(length=24), nullable=False, server_default="DRAFT"),
    )
    op.add_column("quality_assurance_controls", sa.Column("control_objective", sa.Text(), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("test_method", sa.Text(), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("approved_by_user_id", sa.String(length=36), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_quality_assurance_controls_approved_by",
        "quality_assurance_controls",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("quality_assurance_evidence_links", sa.Column("source_table", sa.String(length=80), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("source_route", sa.String(length=500), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("source_label", sa.String(length=255), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("source_snapshot", sa.JSON(), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quality_assurance_evidence_links", sa.Column("invalidation_reason", sa.Text(), nullable=True))

    op.create_table(
        "quality_control_tests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("control_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("next_test_due", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["quality_assurance_controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "result IN ('PASS', 'FAIL', 'PARTIAL', 'NOT_TESTED')",
            name="ck_quality_control_test_result",
        ),
    )
    op.create_index(
        "ix_quality_control_tests_control",
        "quality_control_tests",
        ["amo_id", "control_id", "tested_at"],
    )

    op.create_table(
        "quality_assurance_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("source_table", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("previous_snapshot", sa.JSON(), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=True),
        sa.Column("changed_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=80), nullable=True),
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "event_type IN ('INSERT', 'UPDATE', 'DELETE')",
            name="ck_quality_assurance_event_type",
        ),
        sa.CheckConstraint(
            "processing_status IN ('PENDING', 'PROCESSED', 'ERROR')",
            name="ck_quality_assurance_event_status",
        ),
    )
    op.create_index(
        "ix_quality_assurance_events_queue",
        "quality_assurance_events",
        ["amo_id", "processing_status", "occurred_at"],
    )
    op.create_index(
        "ix_quality_assurance_events_source",
        "quality_assurance_events",
        ["amo_id", "source_type", "source_id"],
    )

    if not _is_postgresql():
        return

    op.create_check_constraint(
        "ck_quality_assurance_control_approval_status",
        "quality_assurance_controls",
        "approval_status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'RETIRED')",
    )
    _enable_rls("quality_control_tests")
    _enable_rls("quality_assurance_events")

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION quality_capture_assurance_event()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                current_row jsonb;
                previous_row jsonb;
                tenant_id text;
                record_id text;
                actor_id text;
                invalid_reason text;
                changed jsonb;
            BEGIN
                current_row := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
                previous_row := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
                tenant_id := COALESCE(current_row ->> 'amo_id', previous_row ->> 'amo_id');
                record_id := COALESCE(current_row ->> 'id', previous_row ->> 'id');
                actor_id := COALESCE(
                    current_row ->> 'updated_by_user_id',
                    current_row ->> 'updated_by',
                    current_row ->> 'created_by_user_id',
                    current_row ->> 'created_by',
                    NULLIF(current_setting('app.user_id', true), '')
                );

                IF tenant_id IS NULL OR record_id IS NULL THEN
                    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
                END IF;

                IF TG_OP = 'UPDATE' THEN
                    SELECT COALESCE(jsonb_agg(key), '[]'::jsonb)
                    INTO changed
                    FROM jsonb_each(current_row)
                    WHERE previous_row -> key IS DISTINCT FROM current_row -> key;
                ELSE
                    changed := '[]'::jsonb;
                END IF;

                INSERT INTO quality_assurance_events (
                    id, amo_id, source_table, source_type, source_id, event_type,
                    previous_snapshot, source_snapshot, changed_fields, actor_user_id,
                    correlation_id, processing_status, occurred_at
                ) VALUES (
                    gen_random_uuid()::text,
                    tenant_id,
                    TG_TABLE_NAME,
                    TG_ARGV[0],
                    record_id,
                    TG_OP,
                    previous_row,
                    current_row,
                    changed,
                    NULLIF(actor_id, ''),
                    NULLIF(current_setting('app.correlation_id', true), ''),
                    'PENDING',
                    NOW()
                );

                invalid_reason := CASE
                    WHEN TG_OP = 'DELETE' THEN 'Authoritative source record was deleted.'
                    WHEN NULLIF(current_row ->> 'deleted_at', '') IS NOT NULL THEN 'Authoritative source record was soft-deleted.'
                    WHEN UPPER(COALESCE(current_row ->> 'status', '')) IN ('CANCELLED', 'OBSOLETE', 'REJECTED', 'DELETED')
                        THEN 'Authoritative source record is no longer valid for assurance.'
                    ELSE NULL
                END;

                UPDATE quality_assurance_evidence_links
                SET source_table = TG_TABLE_NAME,
                    source_snapshot = current_row,
                    source_verified_at = NOW(),
                    last_synced_at = NOW(),
                    evidence_status = CASE
                        WHEN invalid_reason IS NOT NULL THEN 'REJECTED'
                        WHEN valid_until IS NOT NULL AND valid_until < CURRENT_DATE THEN 'EXPIRED'
                        ELSE evidence_status
                    END,
                    invalidated_at = CASE WHEN invalid_reason IS NOT NULL THEN NOW() ELSE NULL END,
                    invalidation_reason = invalid_reason,
                    updated_at = NOW()
                WHERE amo_id::text = tenant_id
                  AND source_type = TG_ARGV[0]
                  AND source_id = record_id;

                RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
            END;
            $$
            """
        )
    )

    for table_name, source_type in _EVENT_SOURCES:
        trigger_name = f"trg_{table_name}_assurance_event"
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{table_name}') IS NOT NULL THEN
                        DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
                        CREATE TRIGGER {trigger_name}
                        AFTER INSERT OR UPDATE OR DELETE ON {table_name}
                        FOR EACH ROW EXECUTE FUNCTION quality_capture_assurance_event('{source_type}');
                    END IF;
                END
                $$;
                """
            )
        )


def downgrade() -> None:
    if _is_postgresql():
        for table_name, _source_type in reversed(_EVENT_SOURCES):
            trigger_name = f"trg_{table_name}_assurance_event"
            op.execute(
                sa.text(
                    f"""
                    DO $$
                    BEGIN
                        IF to_regclass('public.{table_name}') IS NOT NULL THEN
                            DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
                        END IF;
                    END
                    $$;
                    """
                )
            )
        op.execute(sa.text("DROP FUNCTION IF EXISTS quality_capture_assurance_event()"))
        for table_name in ("quality_assurance_events", "quality_control_tests"):
            policy_name = _policy_name(table_name)
            op.execute(sa.text(f'DROP POLICY IF EXISTS {policy_name} ON "{table_name}"'))
            op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))
        op.drop_constraint(
            "ck_quality_assurance_control_approval_status",
            "quality_assurance_controls",
            type_="check",
        )

    op.drop_index("ix_quality_assurance_events_source", table_name="quality_assurance_events")
    op.drop_index("ix_quality_assurance_events_queue", table_name="quality_assurance_events")
    op.drop_table("quality_assurance_events")
    op.drop_index("ix_quality_control_tests_control", table_name="quality_control_tests")
    op.drop_table("quality_control_tests")

    for column_name in (
        "invalidation_reason",
        "invalidated_at",
        "last_synced_at",
        "source_verified_at",
        "source_snapshot",
        "source_label",
        "source_route",
        "source_table",
    ):
        op.drop_column("quality_assurance_evidence_links", column_name)

    op.drop_constraint(
        "fk_quality_assurance_controls_approved_by",
        "quality_assurance_controls",
        type_="foreignkey",
    )
    for column_name in (
        "retired_at",
        "approved_at",
        "approved_by_user_id",
        "test_method",
        "control_objective",
        "approval_status",
        "version_no",
    ):
        op.drop_column("quality_assurance_controls", column_name)
