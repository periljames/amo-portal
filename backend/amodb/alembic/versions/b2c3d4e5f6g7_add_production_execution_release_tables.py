"""add production execution release tables

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e9f0
Create Date: 2026-03-03 10:35:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e9f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'technical_production_execution_evidence',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_order_id', sa.Integer(), sa.ForeignKey('work_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_card_id', sa.Integer(), sa.ForeignKey('task_cards.id', ondelete='SET NULL'), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_tr_exec_evidence_amo_wo', 'technical_production_execution_evidence', ['amo_id', 'work_order_id'])

    op.create_table(
        'technical_production_release_gates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_order_id', sa.Integer(), sa.ForeignKey('work_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='Draft'),
        sa.Column('readiness_notes', sa.Text(), nullable=True),
        sa.Column('blockers_json', sa.JSON(), nullable=False),
        sa.Column('evidence_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('signed_off_by_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('signed_off_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('handed_to_records', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('handed_to_records_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('amo_id', 'work_order_id', name='uq_tr_release_gate_amo_wo'),
    )
    op.create_index('ix_tr_release_gate_amo_status', 'technical_production_release_gates', ['amo_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_tr_release_gate_amo_status', table_name='technical_production_release_gates')
    op.drop_table('technical_production_release_gates')
    op.drop_index('ix_tr_exec_evidence_amo_wo', table_name='technical_production_execution_evidence')
    op.drop_table('technical_production_execution_evidence')
