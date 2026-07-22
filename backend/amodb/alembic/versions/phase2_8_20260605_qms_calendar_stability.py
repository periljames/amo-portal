"""QMS calendar stability, tenant timezone, and configurable public holidays.

Revision ID: phase2_8_20260605
Revises: phase2_7_20260605
Create Date: 2026-06-05

Calendar support tables remain idempotent. Performance indexes are created only
when every referenced key, predicate, and include column exists.
"""

from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_8_20260605"
down_revision = "phase2_7_20260605"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = current_schema() AND indexname = :index_name
                )
                """
            ),
            {"index_name": index_name},
        ).scalar()
    )


def _execute_if_columns(
    table_name: str,
    columns: Iterable[str],
    sql: str,
    *,
    index_name: str | None = None,
) -> None:
    if not set(columns).issubset(_columns(table_name)):
        return
    if index_name and _index_exists(index_name):
        return
    op.execute(sa.text(sql))


def upgrade() -> None:
    if not _table_exists("qms_calendar_settings"):
        op.create_table(
            "qms_calendar_settings",
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("holidays_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("holiday_provider", sa.String(length=64), nullable=True),
            sa.Column("holiday_country_code", sa.String(length=16), nullable=True),
            sa.Column("holiday_region_code", sa.String(length=64), nullable=True),
            sa.Column("holiday_source_url", sa.Text(), nullable=True),
            sa.Column("cache_ttl_hours", sa.Integer(), nullable=False, server_default="168"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_qms_calendar_settings_enabled ON qms_calendar_settings (holidays_enabled)"))
        op.execute(
            sa.text(
                """
                INSERT INTO qms_calendar_settings (amo_id, holiday_provider, holiday_country_code, created_at, updated_at)
                SELECT id, 'CONFIGURED_ICS_URL', country, NOW(), NOW()
                FROM amos
                ON CONFLICT (amo_id) DO NOTHING
                """
            )
        )

    if not _table_exists("qms_public_holidays"):
        op.create_table(
            "qms_public_holidays",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("holiday_date", sa.Date(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("source_uid", sa.String(length=512), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.UniqueConstraint("amo_id", "holiday_date", "source_uid", name="uq_qms_public_holidays_amo_date_uid"),
        )
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_qms_public_holidays_amo_date ON qms_public_holidays (amo_id, holiday_date)"))

    specs = (
        ("qms_audits", ("amo_id", "planned_start", "created_at"), "ix_qms_audits_amo_planned_start_fast", "CREATE INDEX ix_qms_audits_amo_planned_start_fast ON qms_audits (amo_id, planned_start, created_at DESC) WHERE planned_start IS NOT NULL"),
        ("qms_audits", ("amo_id", "planned_end", "created_at"), "ix_qms_audits_amo_planned_end_fast", "CREATE INDEX ix_qms_audits_amo_planned_end_fast ON qms_audits (amo_id, planned_end, created_at DESC) WHERE planned_end IS NOT NULL"),
        ("qms_audits", ("amo_id", "status", "created_at"), "ix_qms_audits_amo_status_fast", "CREATE INDEX ix_qms_audits_amo_status_fast ON qms_audits (amo_id, status, created_at DESC)"),
        ("quality_cars", ("amo_id", "due_date", "status"), "ix_quality_cars_amo_due_status_fast", "CREATE INDEX ix_quality_cars_amo_due_status_fast ON quality_cars (amo_id, due_date, status) WHERE due_date IS NOT NULL"),
        ("qms_audit_findings", ("amo_id", "closed_at"), "ix_qms_audit_findings_amo_open_fast", "CREATE INDEX ix_qms_audit_findings_amo_open_fast ON qms_audit_findings (amo_id, closed_at) WHERE closed_at IS NULL"),
        ("training_records", ("amo_id", "user_id", "course_id", "completion_date", "valid_until", "created_at"), "ix_training_records_amo_latest_calendar", "CREATE INDEX ix_training_records_amo_latest_calendar ON training_records (amo_id, user_id, course_id, completion_date DESC, valid_until DESC, created_at DESC) WHERE valid_until IS NOT NULL"),
        ("training_events", ("amo_id", "starts_on", "status"), "ix_training_events_amo_start_status_fast", "CREATE INDEX ix_training_events_amo_start_status_fast ON training_events (amo_id, starts_on, status)"),
    )
    for table_name, columns, index_name, sql in specs:
        _execute_if_columns(table_name, columns, sql, index_name=index_name)

    for table_name in ("qms_audits", "quality_cars", "qms_audit_findings", "training_records", "training_events", "qms_public_holidays"):
        if _table_exists(table_name):
            op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for index_name in (
        "ix_training_events_amo_start_status_fast",
        "ix_training_records_amo_latest_calendar",
        "ix_qms_audit_findings_amo_open_fast",
        "ix_quality_cars_amo_due_status_fast",
        "ix_qms_audits_amo_status_fast",
        "ix_qms_audits_amo_planned_end_fast",
        "ix_qms_audits_amo_planned_start_fast",
        "ix_qms_public_holidays_amo_date",
        "ix_qms_calendar_settings_enabled",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    if _table_exists("qms_public_holidays"):
        op.drop_table("qms_public_holidays")
    if _table_exists("qms_calendar_settings"):
        op.drop_table("qms_calendar_settings")
