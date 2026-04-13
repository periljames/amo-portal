"""add manual source storage fields and reader progress

Revision ID: m4a5n6u7a8l9
Revises: m3a4n5u6l7s8
Create Date: 2026-04-09 10:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'm4a5n6u7a8l9'
down_revision = 'm3a4n5u6l7s8'
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return any(col['name'] == column_name for col in inspect(bind).get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    return any(idx['name'] == index_name for idx in inspect(bind).get_indexes(table_name))


def _enum_exists(bind, enum_name: str) -> bool:
    row = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": enum_name}).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    if not _enum_exists(bind, 'manual_source_type_enum'):
        op.execute("CREATE TYPE manual_source_type_enum AS ENUM ('DOCX', 'PDF')")

    for column in [
        sa.Column('source_type_enum', sa.Enum('DOCX', 'PDF', name='manual_source_type_enum'), nullable=True),
        sa.Column('source_storage_path', sa.Text(), nullable=True),
        sa.Column('source_mime_type', sa.String(length=128), nullable=True),
        sa.Column('source_sha256', sa.String(length=64), nullable=True),
        sa.Column('source_page_count', sa.Integer(), nullable=True),
    ]:
        if not _has_column(bind, 'manual_revisions', column.name):
            op.add_column('manual_revisions', column)

    if not _has_index(bind, 'manual_revisions', 'ix_manual_revisions_source_sha256'):
        op.create_index('ix_manual_revisions_source_sha256', 'manual_revisions', ['source_sha256'])

    if not _has_table(bind, 'manual_reader_progress'):
        op.create_table(
            'manual_reader_progress',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('tenant_id', sa.String(length=36), sa.ForeignKey('manual_tenants.id', ondelete='CASCADE'), nullable=False),
            sa.Column('manual_id', sa.String(length=36), sa.ForeignKey('manuals.id', ondelete='CASCADE'), nullable=False),
            sa.Column('revision_id', sa.String(length=36), sa.ForeignKey('manual_revisions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('last_section_id', sa.String(length=36), sa.ForeignKey('manual_sections.id', ondelete='SET NULL'), nullable=True),
            sa.Column('last_anchor_slug', sa.String(length=255), nullable=True),
            sa.Column('last_page_number', sa.Integer(), nullable=True),
            sa.Column('scroll_percent', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('zoom_percent', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('bookmark_label', sa.String(length=255), nullable=True),
            sa.Column('bookmarks_json', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column('last_opened_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('revision_id', 'user_id', name='uq_manual_reader_progress_revision_user'),
        )
        op.create_index('ix_manual_reader_progress_tenant_id', 'manual_reader_progress', ['tenant_id'])
        op.create_index('ix_manual_reader_progress_manual_id', 'manual_reader_progress', ['manual_id'])
        op.create_index('ix_manual_reader_progress_revision_id', 'manual_reader_progress', ['revision_id'])
        op.create_index('ix_manual_reader_progress_user_id', 'manual_reader_progress', ['user_id'])


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, 'manual_reader_progress'):
        for index_name in [
            'ix_manual_reader_progress_user_id',
            'ix_manual_reader_progress_revision_id',
            'ix_manual_reader_progress_manual_id',
            'ix_manual_reader_progress_tenant_id',
        ]:
            if _has_index(bind, 'manual_reader_progress', index_name):
                op.drop_index(index_name, table_name='manual_reader_progress')
        op.drop_table('manual_reader_progress')

    if _has_index(bind, 'manual_revisions', 'ix_manual_revisions_source_sha256'):
        op.drop_index('ix_manual_revisions_source_sha256', table_name='manual_revisions')

    for column_name in ['source_page_count', 'source_sha256', 'source_mime_type', 'source_storage_path', 'source_type_enum']:
        if _has_column(bind, 'manual_revisions', column_name):
            op.drop_column('manual_revisions', column_name)

    if _enum_exists(bind, 'manual_source_type_enum'):
        op.execute('DROP TYPE manual_source_type_enum')
