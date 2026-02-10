"""add car attachment sha256

Revision ID: b1c2d3e4f5a6
Revises: f8a1b2c3d4e6
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = 'f8a1b2c3d4e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('quality_car_attachments', sa.Column('sha256', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_quality_car_attachments_sha256'), 'quality_car_attachments', ['sha256'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quality_car_attachments_sha256'), table_name='quality_car_attachments')
    op.drop_column('quality_car_attachments', 'sha256')
