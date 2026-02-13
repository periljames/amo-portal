"""enforce audit car workflow fields

Revision ID: c3d4e5f6a7b8
Revises: d2c3e4f5a6b7
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'd2c3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('quality_cars', sa.Column('root_cause_text', sa.Text(), nullable=True))
    op.add_column('quality_cars', sa.Column('root_cause_status', sa.String(length=32), nullable=False, server_default='PENDING'))
    op.add_column('quality_cars', sa.Column('root_cause_review_note', sa.Text(), nullable=True))
    op.add_column('quality_cars', sa.Column('capa_text', sa.Text(), nullable=True))
    op.add_column('quality_cars', sa.Column('capa_status', sa.String(length=32), nullable=False, server_default='PENDING'))
    op.add_column('quality_cars', sa.Column('capa_review_note', sa.Text(), nullable=True))
    op.add_column('quality_cars', sa.Column('evidence_required', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('quality_cars', sa.Column('evidence_received_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('quality_cars', sa.Column('evidence_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_quality_cars_root_cause_status', 'quality_cars', ['root_cause_status'])
    op.create_index('ix_quality_cars_capa_status', 'quality_cars', ['capa_status'])
    op.create_index('ix_quality_cars_evidence_received_at', 'quality_cars', ['evidence_received_at'])
    op.create_index('ix_quality_cars_evidence_verified_at', 'quality_cars', ['evidence_verified_at'])


def downgrade() -> None:
    op.drop_index('ix_quality_cars_evidence_verified_at', table_name='quality_cars')
    op.drop_index('ix_quality_cars_evidence_received_at', table_name='quality_cars')
    op.drop_index('ix_quality_cars_capa_status', table_name='quality_cars')
    op.drop_index('ix_quality_cars_root_cause_status', table_name='quality_cars')
    op.drop_column('quality_cars', 'evidence_verified_at')
    op.drop_column('quality_cars', 'evidence_received_at')
    op.drop_column('quality_cars', 'evidence_required')
    op.drop_column('quality_cars', 'capa_review_note')
    op.drop_column('quality_cars', 'capa_status')
    op.drop_column('quality_cars', 'capa_text')
    op.drop_column('quality_cars', 'root_cause_review_note')
    op.drop_column('quality_cars', 'root_cause_status')
    op.drop_column('quality_cars', 'root_cause_text')
