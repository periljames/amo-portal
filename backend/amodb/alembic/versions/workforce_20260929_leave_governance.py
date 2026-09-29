"""Add governed leave eligibility fields.

Revision ID: workforce_260929_leave_gov
Revises: docctl_260926_record_index
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "workforce_260929_leave_gov"
down_revision = "docctl_260926_record_index"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    personnel_columns = _columns("personnel_profiles")
    if personnel_columns and "gender" not in personnel_columns:
        op.add_column(
            "personnel_profiles",
            sa.Column("gender", sa.String(length=24), nullable=True),
        )

    leave_columns = _columns("leave_types")
    if leave_columns and "eligible_gender" not in leave_columns:
        op.add_column(
            "leave_types",
            sa.Column(
                "eligible_gender",
                sa.String(length=24),
                nullable=False,
                server_default=sa.text("'ALL'"),
            ),
        )

    if _columns("leave_types"):
        op.execute(
            sa.text(
                """
                UPDATE leave_types
                SET eligible_gender = CASE
                        WHEN availability_type = 'MATERNITY_LEAVE' THEN 'FEMALE'
                        WHEN availability_type = 'PATERNITY_LEAVE' THEN 'MALE'
                        ELSE COALESCE(NULLIF(UPPER(eligible_gender), ''), 'ALL')
                    END
                """
            )
        )


def downgrade() -> None:
    # This is a repair migration for columns already required by the parent-version
    # runtime models. The upgrade is deliberately idempotent because either column
    # may pre-exist on some databases, so a revision-only downgrade cannot safely
    # prove ownership of either column. Preserve them to avoid destructive rollback.
    pass
