"""ensure training import columns present for environments that missed the catalog migration

Revision ID: f4a5b6c7d8e9
Revises: c4b7e1d9f0a2
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "c4b7e1d9f0a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE training_courses ADD COLUMN IF NOT EXISTS category_raw VARCHAR(255)"))
    op.execute(sa.text("ALTER TABLE training_courses ADD COLUMN IF NOT EXISTS status VARCHAR(64)"))
    op.execute(sa.text("ALTER TABLE training_courses ADD COLUMN IF NOT EXISTS scope VARCHAR(255)"))
    op.execute(sa.text("UPDATE training_courses SET status = 'One_Off' WHERE status IS NULL OR btrim(status) = ''"))
    op.execute(sa.text("ALTER TABLE training_courses ALTER COLUMN status SET DEFAULT 'One_Off'"))
    op.execute(sa.text("ALTER TABLE training_courses ALTER COLUMN is_mandatory SET DEFAULT false"))


def downgrade() -> None:
    # Safe no-op downgrade: columns may already be in use and were added to repair schema drift.
    pass
