"""Add CHECK constraint for training course status domain.

Revision ID: c4b7e1d9f0a2
Revises: a3c9e7f1b2d4
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4b7e1d9f0a2"
down_revision: Union[str, Sequence[str], None] = "a3c9e7f1b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALLOWED = ("Initial", "Recurrent", "One_Off")


def upgrade() -> None:
    bind = op.get_bind()

    # Normalize known legacy values before constraining.
    bind.execute(
        sa.text(
            """
            UPDATE training_courses
            SET status = 'One_Off'
            WHERE status IS NULL
               OR btrim(status) = ''
               OR lower(btrim(status)) IN ('active', 'inactive', 'one-off', 'one off')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE training_courses
            SET status = CASE lower(btrim(status))
                WHEN 'initial' THEN 'Initial'
                WHEN 'recurrent' THEN 'Recurrent'
                WHEN 'one_off' THEN 'One_Off'
                ELSE status
            END
            """
        )
    )

    invalid_rows = bind.execute(
        sa.text(
            """
            SELECT id, status
            FROM training_courses
            WHERE status NOT IN ('Initial', 'Recurrent', 'One_Off')
            ORDER BY id
            LIMIT 20
            """
        )
    ).fetchall()
    if invalid_rows:
        preview = ", ".join(f"{row.id}:{row.status}" for row in invalid_rows)
        raise RuntimeError(
            "Cannot enforce training course status constraint; "
            f"found invalid statuses in training_courses (sample): {preview}"
        )

    op.create_check_constraint(
        "ck_training_courses_status_domain",
        "training_courses",
        "status IN ('Initial', 'Recurrent', 'One_Off')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_training_courses_status_domain", "training_courses", type_="check")
