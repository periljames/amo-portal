"""add manual audit log and ocr fields

Revision ID: m3a4n5u6l7s8
Revises: d7e6f5a4b3c2
Create Date: 2026-04-08 08:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'm3a4n5u6l7s8'
down_revision = 'd7e6f5a4b3c2'
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return any(col['name'] == column_name for col in inspect(bind).get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, 'manual_audit_log'):
        op.create_table(
            'manual_audit_log',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('tenant_id', sa.String(length=36), sa.ForeignKey('manual_tenants.id', ondelete='CASCADE'), nullable=False),
            sa.Column('actor_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('action', sa.String(length=128), nullable=False),
            sa.Column('entity_type', sa.String(length=64), nullable=False),
            sa.Column('entity_id', sa.String(length=36), nullable=False),
            sa.Column('at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('ip_device', sa.String(length=255), nullable=True),
            sa.Column('diff_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        )
        op.create_index('ix_manual_audit_log_tenant_id', 'manual_audit_log', ['tenant_id'])

    for column in [
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('manual_uuid', sa.String(length=64), nullable=True),
        sa.Column('ocr_detected_ref', sa.String(length=255), nullable=True),
        sa.Column('ocr_detected_date', sa.Date(), nullable=True),
        sa.Column('ocr_verified_bool', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('ocr_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stamped_export_uri', sa.Text(), nullable=True),
    ]:
        if not _has_column(bind, 'manual_revisions', column.name):
            op.add_column('manual_revisions', column)

    existing_indexes = {idx['name'] for idx in inspect(bind).get_indexes('manual_revisions')}
    if 'ix_manual_revisions_manual_uuid' not in existing_indexes:
        op.create_index('ix_manual_revisions_manual_uuid', 'manual_revisions', ['manual_uuid'])


def downgrade() -> None:
    bind = op.get_bind()
    existing_indexes = {idx['name'] for idx in inspect(bind).get_indexes('manual_revisions')}
    if 'ix_manual_revisions_manual_uuid' in existing_indexes:
        op.drop_index('ix_manual_revisions_manual_uuid', table_name='manual_revisions')

    for column_name in ['stamped_export_uri', 'ocr_verified_at', 'ocr_verified_bool', 'ocr_detected_date', 'ocr_detected_ref', 'manual_uuid', 'source_filename']:
        if _has_column(bind, 'manual_revisions', column_name):
            op.drop_column('manual_revisions', column_name)

    if _has_table(bind, 'manual_audit_log'):
        op.drop_index('ix_manual_audit_log_tenant_id', table_name='manual_audit_log')
        op.drop_table('manual_audit_log')
