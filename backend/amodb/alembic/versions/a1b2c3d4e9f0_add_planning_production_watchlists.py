"""add planning production watchlists

Revision ID: a1b2c3d4e9f0
Revises: t9r8e7c6h5n4
Create Date: 2026-03-03 10:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e9f0'
down_revision = 't9r8e7c6h5n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'technical_airworthiness_watchlists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='Active'),
        sa.Column('criteria_json', sa.JSON(), nullable=False),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_tr_watchlists_amo_status', 'technical_airworthiness_watchlists', ['amo_id', 'status'])

    op.create_table(
        'technical_airworthiness_publications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('authority', sa.String(length=32), nullable=False),
        sa.Column('document_type', sa.String(length=32), nullable=False),
        sa.Column('doc_number', sa.String(length=96), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('ata_chapter', sa.String(length=16), nullable=True),
        sa.Column('effectivity_summary', sa.Text(), nullable=True),
        sa.Column('keywords', sa.JSON(), nullable=False),
        sa.Column('raw_metadata_json', sa.JSON(), nullable=False),
        sa.Column('source_link', sa.String(length=512), nullable=True),
        sa.Column('published_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('amo_id', 'source', 'doc_number', name='uq_tr_publication_source_doc'),
    )
    op.create_index('ix_tr_publications_amo_date', 'technical_airworthiness_publications', ['amo_id', 'published_date'])

    op.create_table(
        'technical_airworthiness_publication_matches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('watchlist_id', sa.Integer(), sa.ForeignKey('technical_airworthiness_watchlists.id', ondelete='CASCADE'), nullable=False),
        sa.Column('publication_id', sa.Integer(), sa.ForeignKey('technical_airworthiness_publications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('classification', sa.String(length=32), nullable=False, server_default='Potentially Applicable'),
        sa.Column('matched_fleet_json', sa.JSON(), nullable=False),
        sa.Column('matched_components_json', sa.JSON(), nullable=False),
        sa.Column('review_status', sa.String(length=32), nullable=False, server_default='Matched'),
        sa.Column('assigned_reviewer_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('amo_id', 'watchlist_id', 'publication_id', name='uq_tr_watchlist_publication_match'),
    )
    op.create_index('ix_tr_pub_match_amo_status', 'technical_airworthiness_publication_matches', ['amo_id', 'review_status'])

    op.create_table(
        'technical_compliance_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('publication_match_id', sa.Integer(), sa.ForeignKey('technical_airworthiness_publication_matches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('decision', sa.String(length=48), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='Under Review'),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('due_hours', sa.Float(), nullable=True),
        sa.Column('due_cycles', sa.Float(), nullable=True),
        sa.Column('recurring_interval_days', sa.Integer(), nullable=True),
        sa.Column('owner_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('package_ref', sa.String(length=64), nullable=True),
        sa.Column('work_order_ref', sa.String(length=64), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('decision_notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_tr_comp_actions_amo_status', 'technical_compliance_actions', ['amo_id', 'status'])

    op.create_table(
        'technical_compliance_action_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('amo_id', sa.String(length=36), sa.ForeignKey('amos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('compliance_action_id', sa.Integer(), sa.ForeignKey('technical_compliance_actions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_status', sa.String(length=32), nullable=True),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('event_notes', sa.Text(), nullable=True),
        sa.Column('actor_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_tr_comp_hist_amo_action', 'technical_compliance_action_history', ['amo_id', 'compliance_action_id'])


def downgrade() -> None:
    op.drop_index('ix_tr_comp_hist_amo_action', table_name='technical_compliance_action_history')
    op.drop_table('technical_compliance_action_history')
    op.drop_index('ix_tr_comp_actions_amo_status', table_name='technical_compliance_actions')
    op.drop_table('technical_compliance_actions')
    op.drop_index('ix_tr_pub_match_amo_status', table_name='technical_airworthiness_publication_matches')
    op.drop_table('technical_airworthiness_publication_matches')
    op.drop_index('ix_tr_publications_amo_date', table_name='technical_airworthiness_publications')
    op.drop_table('technical_airworthiness_publications')
    op.drop_index('ix_tr_watchlists_amo_status', table_name='technical_airworthiness_watchlists')
    op.drop_table('technical_airworthiness_watchlists')
