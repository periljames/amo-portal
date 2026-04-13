"""P0 training course planning fields

Revision ID: p0a5_train_plan
Revises: p0a4_training_gate_fields
Create Date: 2026-04-09 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p0a5_train_plan"
down_revision = "p0a4_training_gate_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("training_courses", sa.Column("nominal_hours", sa.Integer(), nullable=True))
    op.add_column("training_courses", sa.Column("planning_lead_days", sa.Integer(), nullable=True, server_default=sa.text("45")))
    op.add_column("training_courses", sa.Column("candidate_requirement_text", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_training_course_nominal_hours_nonneg",
        "training_courses",
        "nominal_hours IS NULL OR nominal_hours >= 0",
    )
    op.create_check_constraint(
        "ck_training_course_planning_lead_nonneg",
        "training_courses",
        "planning_lead_days IS NULL OR planning_lead_days >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_training_course_planning_lead_nonneg", "training_courses", type_="check")
    op.drop_constraint("ck_training_course_nominal_hours_nonneg", "training_courses", type_="check")
    op.drop_column("training_courses", "candidate_requirement_text")
    op.drop_column("training_courses", "planning_lead_days")
    op.drop_column("training_courses", "nominal_hours")
