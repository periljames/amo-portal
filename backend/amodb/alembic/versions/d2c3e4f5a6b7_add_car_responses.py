"""add car responses

Revision ID: d2c3e4f5a6b7
Revises: c9f1b2a3d4e5
Create Date: 2025-02-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d2c3e4f5a6b7"
down_revision = "c9f1b2a3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().dialect.has_table(op.get_bind(), "quality_cars"):
        return
    op.create_table(
        "quality_car_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("car_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("containment_action", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("corrective_action", sa.Text(), nullable=True),
        sa.Column("preventive_action", sa.Text(), nullable=True),
        sa.Column("evidence_ref", sa.String(length=512), nullable=True),
        sa.Column("submitted_by_name", sa.String(length=255), nullable=True),
        sa.Column("submitted_by_email", sa.String(length=255), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SUBMITTED",
                "ROOT_CAUSE_ACCEPTED",
                "ROOT_CAUSE_REJECTED",
                "CAP_REJECTED",
                "CAP_ACCEPTED",
                name="quality_car_response_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_car_responses_car_id",
        "quality_car_responses",
        ["car_id"],
        unique=False,
    )
    op.create_index(
        "ix_quality_car_responses_status",
        "quality_car_responses",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    if not op.get_bind().dialect.has_table(op.get_bind(), "quality_car_responses"):
        return
    op.drop_index("ix_quality_car_responses_status", table_name="quality_car_responses")
    op.drop_index("ix_quality_car_responses_car_id", table_name="quality_car_responses")
    op.drop_table("quality_car_responses")
