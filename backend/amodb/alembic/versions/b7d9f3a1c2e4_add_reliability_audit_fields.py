"""add reliability audit fields

Revision ID: b7d9f3a1c2e4
Revises: 9c6a7d2e8f10
Create Date: 2025-02-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7d9f3a1c2e4"
down_revision: Union[str, Sequence[str], None] = "9c6a7d2e8f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reliability_alerts", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reliability_alerts", sa.Column("acknowledged_by_user_id", sa.String(length=36), nullable=True))
    op.create_index(
        op.f("ix_reliability_alerts_acknowledged_by_user_id"),
        "reliability_alerts",
        ["acknowledged_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_reliability_alerts_acknowledged_by_user_id_users"),
        "reliability_alerts",
        "users",
        ["acknowledged_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("fracas_cases", sa.Column("verification_notes", sa.Text(), nullable=True))
    op.add_column("fracas_cases", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fracas_cases", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fracas_cases", sa.Column("verified_by_user_id", sa.String(length=36), nullable=True))
    op.add_column("fracas_cases", sa.Column("approved_by_user_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_fracas_cases_verified_by_user_id"), "fracas_cases", ["verified_by_user_id"], unique=False)
    op.create_index(op.f("ix_fracas_cases_approved_by_user_id"), "fracas_cases", ["approved_by_user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_fracas_cases_verified_by_user_id_users"),
        "fracas_cases",
        "users",
        ["verified_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_fracas_cases_approved_by_user_id_users"),
        "fracas_cases",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("fracas_actions", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fracas_actions", sa.Column("verified_by_user_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_fracas_actions_verified_by_user_id"), "fracas_actions", ["verified_by_user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_fracas_actions_verified_by_user_id_users"),
        "fracas_actions",
        "users",
        ["verified_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_fracas_actions_verified_by_user_id_users"), "fracas_actions", type_="foreignkey")
    op.drop_index(op.f("ix_fracas_actions_verified_by_user_id"), table_name="fracas_actions")
    op.drop_column("fracas_actions", "verified_by_user_id")
    op.drop_column("fracas_actions", "verified_at")

    op.drop_constraint(op.f("fk_fracas_cases_approved_by_user_id_users"), "fracas_cases", type_="foreignkey")
    op.drop_constraint(op.f("fk_fracas_cases_verified_by_user_id_users"), "fracas_cases", type_="foreignkey")
    op.drop_index(op.f("ix_fracas_cases_approved_by_user_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_verified_by_user_id"), table_name="fracas_cases")
    op.drop_column("fracas_cases", "approved_by_user_id")
    op.drop_column("fracas_cases", "verified_by_user_id")
    op.drop_column("fracas_cases", "approved_at")
    op.drop_column("fracas_cases", "verified_at")
    op.drop_column("fracas_cases", "verification_notes")

    op.drop_constraint(op.f("fk_reliability_alerts_acknowledged_by_user_id_users"), "reliability_alerts", type_="foreignkey")
    op.drop_index(op.f("ix_reliability_alerts_acknowledged_by_user_id"), table_name="reliability_alerts")
    op.drop_column("reliability_alerts", "acknowledged_by_user_id")
    op.drop_column("reliability_alerts", "acknowledged_at")
