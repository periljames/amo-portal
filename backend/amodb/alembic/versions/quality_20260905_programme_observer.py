"""Store programme observers separately from supporting auditors.

Revision ID: quality_260905_prog_observer
Revises: quality_260905_programme_team
"""

from alembic import op
import sqlalchemy as sa


revision = "quality_260905_prog_observer"
down_revision = "quality_260905_programme_team"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("observer_auditor_user_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_quality_audit_programme_items_observer_user",
        "quality_audit_programme_items",
        "users",
        ["observer_auditor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quality_audit_programme_items_observer_user",
        "quality_audit_programme_items",
        type_="foreignkey",
    )
    op.drop_column("quality_audit_programme_items", "observer_auditor_user_id")
