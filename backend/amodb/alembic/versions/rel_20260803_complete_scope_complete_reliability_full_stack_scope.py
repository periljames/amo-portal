"""complete Reliability full stack scope

Revision ID: rel_20260803_complete_scope
Revises: rel_20260803_merge_heads_diag
Create Date: 2026-08-03 14:35:49.735252

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'rel_20260803_complete_scope'
down_revision: Union[str, Sequence[str], None] = 'rel_20260803_merge_heads_diag'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RELIABILITY_CAPABILITY_CODES = ['reliability.read', 'reliability.source.manage', 'reliability.ingest', 'reliability.data_quality.resolve', 'reliability.fracas.triage', 'reliability.fracas.investigate', 'reliability.fracas.action', 'reliability.fracas.verify', 'reliability.programme.manage', 'reliability.programme.approve', 'reliability.metric.manage', 'reliability.metric.execute', 'reliability.meeting.manage', 'reliability.change.manage', 'reliability.change.approve', 'reliability.handoff.manage', 'reliability.authority.prepare', 'reliability.authority.submit', 'reliability.ai.use', 'reliability.ai.review', 'reliability.audit.read']
_RELIABILITY_ROLE_IDS = ['rel-role-viewer', 'rel-role-engineer', 'rel-role-manager', 'rel-role-authority']

def _seed_reliability_authorization() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
    INSERT INTO auth_capability_definitions (id, code, module, description)
    VALUES
        ('rel-cap-001', 'reliability.read', 'reliability', 'Reliability Read'),
        ('rel-cap-002', 'reliability.source.manage', 'reliability', 'Reliability Source Manage'),
        ('rel-cap-003', 'reliability.ingest', 'reliability', 'Reliability Ingest'),
        ('rel-cap-004', 'reliability.data_quality.resolve', 'reliability', 'Reliability Data_Quality Resolve'),
        ('rel-cap-005', 'reliability.fracas.triage', 'reliability', 'Reliability Fracas Triage'),
        ('rel-cap-006', 'reliability.fracas.investigate', 'reliability', 'Reliability Fracas Investigate'),
        ('rel-cap-007', 'reliability.fracas.action', 'reliability', 'Reliability Fracas Action'),
        ('rel-cap-008', 'reliability.fracas.verify', 'reliability', 'Reliability Fracas Verify'),
        ('rel-cap-009', 'reliability.programme.manage', 'reliability', 'Reliability Programme Manage'),
        ('rel-cap-010', 'reliability.programme.approve', 'reliability', 'Reliability Programme Approve'),
        ('rel-cap-011', 'reliability.metric.manage', 'reliability', 'Reliability Metric Manage'),
        ('rel-cap-012', 'reliability.metric.execute', 'reliability', 'Reliability Metric Execute'),
        ('rel-cap-013', 'reliability.meeting.manage', 'reliability', 'Reliability Meeting Manage'),
        ('rel-cap-014', 'reliability.change.manage', 'reliability', 'Reliability Change Manage'),
        ('rel-cap-015', 'reliability.change.approve', 'reliability', 'Reliability Change Approve'),
        ('rel-cap-016', 'reliability.handoff.manage', 'reliability', 'Reliability Handoff Manage'),
        ('rel-cap-017', 'reliability.authority.prepare', 'reliability', 'Reliability Authority Prepare'),
        ('rel-cap-018', 'reliability.authority.submit', 'reliability', 'Reliability Authority Submit'),
        ('rel-cap-019', 'reliability.ai.use', 'reliability', 'Reliability Ai Use'),
        ('rel-cap-020', 'reliability.ai.review', 'reliability', 'Reliability Ai Review'),
        ('rel-cap-021', 'reliability.audit.read', 'reliability', 'Reliability Audit Read')
    ON CONFLICT (code) DO UPDATE SET
        module = EXCLUDED.module,
        description = EXCLUDED.description
    """)
    op.execute("""
    INSERT INTO auth_role_definitions (id, code, scope_type, description, is_system)
    VALUES
        ('rel-role-viewer', 'RELIABILITY_VIEWER', 'AMO', 'Read-only Reliability evidence and controlled outputs.', true),
        ('rel-role-engineer', 'RELIABILITY_ENGINEER', 'AMO', 'Reliability ingestion, technical investigation, calculations and implementation handoffs.', true),
        ('rel-role-manager', 'RELIABILITY_MANAGER', 'AMO', 'Reliability programme manager with governance and approval authority inside the AMO tenant.', true),
        ('rel-role-authority', 'RELIABILITY_AUTHORITY_SUBMITTER', 'AMO', 'Controlled preparation and submission of accepted Reliability authority packages.', true)
    ON CONFLICT (code) DO UPDATE SET
        scope_type = EXCLUDED.scope_type,
        description = EXCLUDED.description,
        is_system = true
    """)
    op.execute("""
    INSERT INTO auth_role_capability_bindings (id, role_id, capability_id, constraints_json)
    VALUES
        ('rel-bind-0001', 'rel-role-viewer', 'rel-cap-001', '{}'::json),
        ('rel-bind-0002', 'rel-role-engineer', 'rel-cap-001', '{}'::json),
        ('rel-bind-0003', 'rel-role-engineer', 'rel-cap-003', '{}'::json),
        ('rel-bind-0004', 'rel-role-engineer', 'rel-cap-005', '{}'::json),
        ('rel-bind-0005', 'rel-role-engineer', 'rel-cap-006', '{}'::json),
        ('rel-bind-0006', 'rel-role-engineer', 'rel-cap-007', '{}'::json),
        ('rel-bind-0007', 'rel-role-engineer', 'rel-cap-012', '{}'::json),
        ('rel-bind-0008', 'rel-role-engineer', 'rel-cap-016', '{}'::json),
        ('rel-bind-0009', 'rel-role-engineer', 'rel-cap-019', '{}'::json),
        ('rel-bind-0010', 'rel-role-manager', 'rel-cap-001', '{}'::json),
        ('rel-bind-0011', 'rel-role-manager', 'rel-cap-002', '{}'::json),
        ('rel-bind-0012', 'rel-role-manager', 'rel-cap-003', '{}'::json),
        ('rel-bind-0013', 'rel-role-manager', 'rel-cap-004', '{}'::json),
        ('rel-bind-0014', 'rel-role-manager', 'rel-cap-005', '{}'::json),
        ('rel-bind-0015', 'rel-role-manager', 'rel-cap-006', '{}'::json),
        ('rel-bind-0016', 'rel-role-manager', 'rel-cap-007', '{}'::json),
        ('rel-bind-0017', 'rel-role-manager', 'rel-cap-008', '{}'::json),
        ('rel-bind-0018', 'rel-role-manager', 'rel-cap-009', '{}'::json),
        ('rel-bind-0019', 'rel-role-manager', 'rel-cap-010', '{}'::json),
        ('rel-bind-0020', 'rel-role-manager', 'rel-cap-011', '{}'::json),
        ('rel-bind-0021', 'rel-role-manager', 'rel-cap-012', '{}'::json),
        ('rel-bind-0022', 'rel-role-manager', 'rel-cap-013', '{}'::json),
        ('rel-bind-0023', 'rel-role-manager', 'rel-cap-014', '{}'::json),
        ('rel-bind-0024', 'rel-role-manager', 'rel-cap-015', '{}'::json),
        ('rel-bind-0025', 'rel-role-manager', 'rel-cap-016', '{}'::json),
        ('rel-bind-0026', 'rel-role-manager', 'rel-cap-017', '{}'::json),
        ('rel-bind-0027', 'rel-role-manager', 'rel-cap-019', '{}'::json),
        ('rel-bind-0028', 'rel-role-manager', 'rel-cap-020', '{}'::json),
        ('rel-bind-0029', 'rel-role-manager', 'rel-cap-021', '{}'::json),
        ('rel-bind-0030', 'rel-role-authority', 'rel-cap-001', '{}'::json),
        ('rel-bind-0031', 'rel-role-authority', 'rel-cap-017', '{}'::json),
        ('rel-bind-0032', 'rel-role-authority', 'rel-cap-018', '{}'::json),
        ('rel-bind-0033', 'rel-role-authority', 'rel-cap-021', '{}'::json)
    ON CONFLICT (role_id, capability_id) DO NOTHING
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || '|' || u.id || '|rel-role-viewer'), u.amo_id, u.id, 'rel-role-viewer', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-viewer'
      )
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || '|' || u.id || '|rel-role-engineer'), u.amo_id, u.id, 'rel-role-engineer', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND CAST(u.role AS TEXT) IN ('PLANNING_ENGINEER', 'PRODUCTION_ENGINEER', 'QUALITY_INSPECTOR', 'AUDITOR')
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-engineer'
      )
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || '|' || u.id || '|rel-role-manager'), u.amo_id, u.id, 'rel-role-manager', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND (u.is_amo_admin = true OR CAST(u.role AS TEXT) IN ('AMO_ADMIN', 'QUALITY_MANAGER', 'SAFETY_MANAGER'))
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-manager'
      )
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || '|' || u.id || '|rel-role-authority'), u.amo_id, u.id, 'rel-role-authority', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND (u.is_amo_admin = true OR CAST(u.role AS TEXT) IN ('AMO_ADMIN', 'QUALITY_MANAGER'))
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-authority'
      )
    """)

def _remove_reliability_authorization() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("DELETE FROM auth_user_role_assignments WHERE role_id = ANY(:role_ids)").bindparams(role_ids=_RELIABILITY_ROLE_IDS))
    op.execute(sa.text("DELETE FROM auth_role_capability_bindings WHERE role_id = ANY(:role_ids)").bindparams(role_ids=_RELIABILITY_ROLE_IDS))
    op.execute(sa.text("DELETE FROM auth_role_definitions WHERE id = ANY(:role_ids)").bindparams(role_ids=_RELIABILITY_ROLE_IDS))
    op.execute(sa.text("DELETE FROM auth_capability_definitions WHERE code = ANY(:codes)").bindparams(codes=_RELIABILITY_CAPABILITY_CODES))

def _install_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_reliability_append_only_mutation()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'Reliability evidence table % is append-only', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    DROP TRIGGER IF EXISTS trg_reliability_audit_events_append_only ON reliability_audit_events;
    CREATE TRIGGER trg_reliability_audit_events_append_only
    BEFORE UPDATE OR DELETE ON reliability_audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_reliability_append_only_mutation();
    """)
    op.execute("""
    DROP TRIGGER IF EXISTS trg_reliability_fracas_evidence_append_only ON reliability_fracas_evidence;
    CREATE TRIGGER trg_reliability_fracas_evidence_append_only
    BEFORE UPDATE OR DELETE ON reliability_fracas_evidence
    FOR EACH ROW EXECUTE FUNCTION prevent_reliability_append_only_mutation();
    """)
    op.execute("""
    DROP TRIGGER IF EXISTS trg_reliability_fracas_stage_events_append_only ON reliability_fracas_stage_events;
    CREATE TRIGGER trg_reliability_fracas_stage_events_append_only
    BEFORE UPDATE OR DELETE ON reliability_fracas_stage_events
    FOR EACH ROW EXECUTE FUNCTION prevent_reliability_append_only_mutation();
    """)
    op.execute("""
    DROP TRIGGER IF EXISTS trg_reliability_calculation_runs_append_only ON reliability_calculation_runs;
    CREATE TRIGGER trg_reliability_calculation_runs_append_only
    BEFORE UPDATE OR DELETE ON reliability_calculation_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_reliability_append_only_mutation();
    """)

def _drop_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_reliability_audit_events_append_only ON reliability_audit_events")
    op.execute("DROP TRIGGER IF EXISTS trg_reliability_fracas_evidence_append_only ON reliability_fracas_evidence")
    op.execute("DROP TRIGGER IF EXISTS trg_reliability_fracas_stage_events_append_only ON reliability_fracas_stage_events")
    op.execute("DROP TRIGGER IF EXISTS trg_reliability_calculation_runs_append_only ON reliability_calculation_runs")
    op.execute("DROP FUNCTION IF EXISTS prevent_reliability_append_only_mutation()")

def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('reliability_ai_reviews',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('review_type', sa.String(length=60), nullable=False),
    sa.Column('entity_type', sa.String(length=60), nullable=False),
    sa.Column('entity_id', sa.String(length=128), nullable=False),
    sa.Column('model_id', sa.String(length=80), nullable=False),
    sa.Column('model_version', sa.String(length=80), nullable=False),
    sa.Column('prompt_hash', sa.String(length=64), nullable=False),
    sa.Column('input_snapshot_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('citations_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('output_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=7, scale=6), nullable=True),
    sa.Column('advisory_only', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('reviewed_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_ai_reviews_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_ai_reviews_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], name=op.f('fk_reliability_ai_reviews_reviewed_by_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_ai_reviews'))
    )
    op.create_index('ix_reliability_ai_entity', 'reliability_ai_reviews', ['amo_id', 'entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_reliability_ai_reviews_amo_id'), 'reliability_ai_reviews', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_ai_reviews_status'), 'reliability_ai_reviews', ['status'], unique=False)
    op.create_index('ix_reliability_ai_status', 'reliability_ai_reviews', ['amo_id', 'status'], unique=False)
    op.create_table('reliability_audit_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('entity_type', sa.String(length=60), nullable=False),
    sa.Column('entity_id', sa.String(length=128), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('previous_hash', sa.String(length=64), nullable=True),
    sa.Column('event_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_reliability_audit_events_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_audit_events_amo_id_amos'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_audit_events')),
    sa.UniqueConstraint('amo_id', 'event_hash', name='uq_reliability_audit_hash')
    )
    op.create_index('ix_reliability_audit_entity', 'reliability_audit_events', ['amo_id', 'entity_type', 'entity_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_reliability_audit_events_amo_id'), 'reliability_audit_events', ['amo_id'], unique=False)
    op.create_table('reliability_programmes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_programmes_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_reliability_programmes_owner_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_programmes')),
    sa.UniqueConstraint('amo_id', 'code', name='uq_reliability_programme_amo_code')
    )
    op.create_index('ix_reliability_programme_status', 'reliability_programmes', ['amo_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_programmes_amo_id'), 'reliability_programmes', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_programmes_status'), 'reliability_programmes', ['status'], unique=False)
    op.create_table('reliability_sources',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('source_type', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('transport', sa.String(length=24), nullable=False),
    sa.Column('mapping_version', sa.String(length=40), nullable=False),
    sa.Column('configuration_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('poll_interval_minutes', sa.Integer(), nullable=True),
    sa.Column('next_poll_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_cursor', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_sources_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_sources_created_by_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_sources')),
    sa.UniqueConstraint('amo_id', 'code', name='uq_reliability_sources_amo_code')
    )
    op.create_index(op.f('ix_reliability_sources_amo_id'), 'reliability_sources', ['amo_id'], unique=False)
    op.create_index('ix_reliability_sources_amo_type', 'reliability_sources', ['amo_id', 'source_type'], unique=False)
    op.create_index('ix_reliability_sources_due', 'reliability_sources', ['amo_id', 'status', 'next_poll_at'], unique=False)
    op.create_index(op.f('ix_reliability_sources_source_type'), 'reliability_sources', ['source_type'], unique=False)
    op.create_index(op.f('ix_reliability_sources_status'), 'reliability_sources', ['status'], unique=False)
    op.create_table('reliability_handoffs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('source_type', sa.String(length=60), nullable=False),
    sa.Column('source_id', sa.String(length=128), nullable=False),
    sa.Column('target_module', sa.String(length=40), nullable=False),
    sa.Column('target_route', sa.String(length=255), nullable=True),
    sa.Column('target_record_type', sa.String(length=80), nullable=True),
    sa.Column('target_record_id', sa.String(length=128), nullable=True),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_handoffs_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_handoffs_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_reliability_handoffs_owner_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_reliability_handoffs_task_id_tasks'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_handoffs'))
    )
    op.create_index('ix_reliability_handoff_source', 'reliability_handoffs', ['amo_id', 'source_type', 'source_id'], unique=False)
    op.create_index('ix_reliability_handoff_target_status', 'reliability_handoffs', ['amo_id', 'target_module', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_handoffs_amo_id'), 'reliability_handoffs', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_handoffs_status'), 'reliability_handoffs', ['status'], unique=False)
    op.create_index(op.f('ix_reliability_handoffs_target_module'), 'reliability_handoffs', ['target_module'], unique=False)
    op.create_index(op.f('ix_reliability_handoffs_task_id'), 'reliability_handoffs', ['task_id'], unique=False)
    op.create_table('reliability_ingestion_batches',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('record_count', sa.Integer(), nullable=False),
    sa.Column('valid_count', sa.Integer(), nullable=False),
    sa.Column('duplicate_count', sa.Integer(), nullable=False),
    sa.Column('invalid_count', sa.Integer(), nullable=False),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_by_user_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_ingestion_batches_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['received_by_user_id'], ['users.id'], name=op.f('fk_reliability_ingestion_batches_received_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['reliability_sources.id'], name=op.f('fk_reliability_ingestion_batches_source_id_reliability_sources'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_ingestion_batches'))
    )
    op.create_index('ix_reliability_batches_amo_received', 'reliability_ingestion_batches', ['amo_id', 'received_at'], unique=False)
    op.create_index('ix_reliability_batches_source_status', 'reliability_ingestion_batches', ['source_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_batches_amo_id'), 'reliability_ingestion_batches', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_batches_content_hash'), 'reliability_ingestion_batches', ['content_hash'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_batches_source_id'), 'reliability_ingestion_batches', ['source_id'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_batches_status'), 'reliability_ingestion_batches', ['status'], unique=False)
    op.create_table('reliability_programme_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('programme_id', sa.String(length=36), nullable=False),
    sa.Column('revision', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=True),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('change_summary', sa.Text(), nullable=False),
    sa.Column('regulatory_profiles', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('scope_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('data_sources_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('reporting_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('responsibility_matrix_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('approval_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('authority_required', sa.Boolean(), nullable=False),
    sa.Column('approved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_programme_versions_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], name=op.f('fk_reliability_programme_versions_approved_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_programme_versions_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['programme_id'], ['reliability_programmes.id'], name=op.f('fk_reliability_programme_versions_programme_id_reliability_programmes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_programme_versions')),
    sa.UniqueConstraint('programme_id', 'revision', name='uq_reliability_programme_revision')
    )
    op.create_index('ix_reliability_programme_version_status', 'reliability_programme_versions', ['amo_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_programme_versions_amo_id'), 'reliability_programme_versions', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_programme_versions_programme_id'), 'reliability_programme_versions', ['programme_id'], unique=False)
    op.create_index(op.f('ix_reliability_programme_versions_status'), 'reliability_programme_versions', ['status'], unique=False)
    op.create_table('reliability_change_proposals',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('programme_version_id', sa.String(length=36), nullable=True),
    sa.Column('source_type', sa.String(length=60), nullable=False),
    sa.Column('source_id', sa.String(length=128), nullable=False),
    sa.Column('proposal_type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('problem_statement', sa.Text(), nullable=False),
    sa.Column('proposed_change_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('impact_assessment_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('simulation_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('approval_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=True),
    sa.Column('effectiveness_due_date', sa.Date(), nullable=True),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_change_proposals_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_change_proposals_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_reliability_change_proposals_owner_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['programme_version_id'], ['reliability_programme_versions.id'], name=op.f('fk_reliability_change_proposals_programme_version_id_reliability_programme_versions'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_change_proposals'))
    )
    op.create_index(op.f('ix_reliability_change_proposals_amo_id'), 'reliability_change_proposals', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_change_proposals_proposal_type'), 'reliability_change_proposals', ['proposal_type'], unique=False)
    op.create_index(op.f('ix_reliability_change_proposals_status'), 'reliability_change_proposals', ['status'], unique=False)
    op.create_index('ix_reliability_change_source', 'reliability_change_proposals', ['source_type', 'source_id'], unique=False)
    op.create_index('ix_reliability_change_status', 'reliability_change_proposals', ['amo_id', 'status'], unique=False)
    op.create_table('reliability_metric_definitions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('programme_version_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('scope_type', sa.String(length=24), nullable=False),
    sa.Column('method', sa.String(length=32), nullable=False),
    sa.Column('numerator_event_types', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('denominator_type', sa.String(length=24), nullable=False),
    sa.Column('multiplier', sa.Numeric(precision=20, scale=8), nullable=False),
    sa.Column('window_days', sa.Integer(), nullable=False),
    sa.Column('schedule_interval_minutes', sa.Integer(), nullable=False),
    sa.Column('minimum_exposure', sa.Numeric(precision=20, scale=8), nullable=False),
    sa.Column('direction', sa.String(length=24), nullable=False),
    sa.Column('formula_version', sa.String(length=40), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_metric_definitions_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['programme_version_id'], ['reliability_programme_versions.id'], name=op.f('fk_reliability_metric_definitions_programme_version_id_reliability_programme_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_metric_definitions')),
    sa.UniqueConstraint('programme_version_id', 'code', name='uq_reliability_metric_version_code')
    )
    op.create_index(op.f('ix_reliability_metric_definitions_amo_id'), 'reliability_metric_definitions', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_metric_definitions_programme_version_id'), 'reliability_metric_definitions', ['programme_version_id'], unique=False)
    op.create_index('ix_reliability_metric_due', 'reliability_metric_definitions', ['amo_id', 'active', 'next_run_at'], unique=False)
    op.create_table('reliability_review_meetings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('programme_version_id', sa.String(length=36), nullable=True),
    sa.Column('meeting_type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('data_cutoff_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('agenda_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('attendees_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('quorum_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('minutes', sa.Text(), nullable=True),
    sa.Column('chaired_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_review_meetings_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], name=op.f('fk_reliability_review_meetings_approved_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['chaired_by_user_id'], ['users.id'], name=op.f('fk_reliability_review_meetings_chaired_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['programme_version_id'], ['reliability_programme_versions.id'], name=op.f('fk_reliability_review_meetings_programme_version_id_reliability_programme_versions'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_review_meetings'))
    )
    op.create_index('ix_reliability_meeting_schedule', 'reliability_review_meetings', ['amo_id', 'scheduled_at'], unique=False)
    op.create_index('ix_reliability_meeting_status', 'reliability_review_meetings', ['amo_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_review_meetings_amo_id'), 'reliability_review_meetings', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_review_meetings_status'), 'reliability_review_meetings', ['status'], unique=False)
    op.create_table('reliability_authority_submissions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('programme_version_id', sa.String(length=36), nullable=True),
    sa.Column('change_proposal_id', sa.String(length=36), nullable=True),
    sa.Column('meeting_id', sa.String(length=36), nullable=True),
    sa.Column('authority_profile', sa.String(length=40), nullable=False),
    sa.Column('submission_type', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('external_reference', sa.String(length=128), nullable=True),
    sa.Column('package_manifest_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('response_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('submitted_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_authority_submissions_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['change_proposal_id'], ['reliability_change_proposals.id'], name=op.f('fk_reliability_authority_submissions_change_proposal_id_reliability_change_proposals'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_authority_submissions_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['meeting_id'], ['reliability_review_meetings.id'], name=op.f('fk_reliability_authority_submissions_meeting_id_reliability_review_meetings'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['programme_version_id'], ['reliability_programme_versions.id'], name=op.f('fk_reliability_authority_submissions_programme_version_id_reliability_programme_versions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submitted_by_user_id'], ['users.id'], name=op.f('fk_reliability_authority_submissions_submitted_by_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_authority_submissions')),
    sa.UniqueConstraint('amo_id', 'authority_profile', 'external_reference', name='uq_reliability_authority_reference')
    )
    op.create_index('ix_reliability_authority_status', 'reliability_authority_submissions', ['amo_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_authority_submissions_amo_id'), 'reliability_authority_submissions', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_authority_submissions_authority_profile'), 'reliability_authority_submissions', ['authority_profile'], unique=False)
    op.create_index(op.f('ix_reliability_authority_submissions_status'), 'reliability_authority_submissions', ['status'], unique=False)
    op.create_table('reliability_calculation_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('metric_definition_id', sa.String(length=36), nullable=False),
    sa.Column('scope_type', sa.String(length=24), nullable=False),
    sa.Column('scope_id', sa.String(length=128), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('numerator', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('denominator', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('confidence_lower', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('confidence_upper', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('sample_size', sa.Integer(), nullable=False),
    sa.Column('small_fleet', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('formula_version', sa.String(length=40), nullable=False),
    sa.Column('source_cutoff_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source_lineage_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('result_hash', sa.String(length=64), nullable=False),
    sa.Column('scheduled', sa.Boolean(), nullable=False),
    sa.Column('run_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('denominator IS NULL OR denominator >= 0', name=op.f('ck_reliability_calculation_runs_ck_reliability_calculation_denominator_nonnegative')),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_calculation_runs_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['metric_definition_id'], ['reliability_metric_definitions.id'], name=op.f('fk_reliability_calculation_runs_metric_definition_id_reliability_metric_definitions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_by_user_id'], ['users.id'], name=op.f('fk_reliability_calculation_runs_run_by_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_calculation_runs')),
    sa.UniqueConstraint('amo_id', 'metric_definition_id', 'scope_type', 'scope_id', 'period_start', 'period_end', 'formula_version', name='uq_reliability_calculation_identity'),
    sa.UniqueConstraint('result_hash')
    )
    op.create_index('ix_reliability_calculation_metric_period', 'reliability_calculation_runs', ['metric_definition_id', 'period_end'], unique=False)
    op.create_index(op.f('ix_reliability_calculation_runs_amo_id'), 'reliability_calculation_runs', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_calculation_runs_metric_definition_id'), 'reliability_calculation_runs', ['metric_definition_id'], unique=False)
    op.create_index(op.f('ix_reliability_calculation_runs_status'), 'reliability_calculation_runs', ['status'], unique=False)
    op.create_index('ix_reliability_calculation_scope', 'reliability_calculation_runs', ['amo_id', 'scope_type', 'scope_id'], unique=False)
    op.create_table('reliability_ingestion_records',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('batch_id', sa.String(length=36), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('validation_status', sa.String(length=24), nullable=False),
    sa.Column('validation_errors', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('normalized_event_id', sa.Integer(), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_ingestion_records_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['batch_id'], ['reliability_ingestion_batches.id'], name=op.f('fk_reliability_ingestion_records_batch_id_reliability_ingestion_batches'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['normalized_event_id'], ['reliability_events.id'], name=op.f('fk_reliability_ingestion_records_normalized_event_id_reliability_events'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['reliability_sources.id'], name=op.f('fk_reliability_ingestion_records_source_id_reliability_sources'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_ingestion_records')),
    sa.UniqueConstraint('amo_id', 'source_id', 'external_id', name='uq_reliability_ingestion_external'),
    sa.UniqueConstraint('amo_id', 'source_id', 'payload_hash', name='uq_reliability_ingestion_payload')
    )
    op.create_index('ix_reliability_ingestion_batch_status', 'reliability_ingestion_records', ['batch_id', 'validation_status'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_records_amo_id'), 'reliability_ingestion_records', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_records_batch_id'), 'reliability_ingestion_records', ['batch_id'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_records_normalized_event_id'), 'reliability_ingestion_records', ['normalized_event_id'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_records_source_id'), 'reliability_ingestion_records', ['source_id'], unique=False)
    op.create_index(op.f('ix_reliability_ingestion_records_validation_status'), 'reliability_ingestion_records', ['validation_status'], unique=False)
    op.create_table('reliability_meeting_decisions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('meeting_id', sa.String(length=36), nullable=False),
    sa.Column('decision_type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('decision', sa.Text(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('dissent', sa.Text(), nullable=True),
    sa.Column('linked_entity_type', sa.String(length=60), nullable=True),
    sa.Column('linked_entity_id', sa.String(length=128), nullable=True),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_meeting_decisions_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['meeting_id'], ['reliability_review_meetings.id'], name=op.f('fk_reliability_meeting_decisions_meeting_id_reliability_review_meetings'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_reliability_meeting_decisions_owner_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_meeting_decisions'))
    )
    op.create_index('ix_reliability_decision_meeting_status', 'reliability_meeting_decisions', ['meeting_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_meeting_decisions_amo_id'), 'reliability_meeting_decisions', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_meeting_decisions_meeting_id'), 'reliability_meeting_decisions', ['meeting_id'], unique=False)
    op.create_index(op.f('ix_reliability_meeting_decisions_status'), 'reliability_meeting_decisions', ['status'], unique=False)
    op.create_table('reliability_operational_interruptions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('reliability_event_id', sa.Integer(), nullable=False),
    sa.Column('interruption_type', sa.String(length=40), nullable=False),
    sa.Column('flight_number', sa.String(length=24), nullable=True),
    sa.Column('origin', sa.String(length=8), nullable=True),
    sa.Column('destination', sa.String(length=8), nullable=True),
    sa.Column('scheduled_departure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_departure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delay_minutes', sa.Integer(), nullable=True),
    sa.Column('cancelled', sa.Boolean(), nullable=False),
    sa.Column('return_to_gate', sa.Boolean(), nullable=False),
    sa.Column('air_turnback', sa.Boolean(), nullable=False),
    sa.Column('diversion', sa.Boolean(), nullable=False),
    sa.Column('engine_shutdown', sa.Boolean(), nullable=False),
    sa.Column('dispatch_impact', sa.String(length=40), nullable=True),
    sa.Column('mel_reference', sa.String(length=80), nullable=True),
    sa.Column('cdl_reference', sa.String(length=80), nullable=True),
    sa.Column('deferral_category', sa.String(length=16), nullable=True),
    sa.Column('deferred_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('delay_minutes IS NULL OR delay_minutes >= 0', name=op.f('ck_reliability_operational_interruptions_ck_reliability_delay_nonnegative')),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_operational_interruptions_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reliability_event_id'], ['reliability_events.id'], name=op.f('fk_reliability_operational_interruptions_reliability_event_id_reliability_events'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_operational_interruptions')),
    sa.UniqueConstraint('amo_id', 'reliability_event_id', name='uq_reliability_interruption_event')
    )
    op.create_index('ix_reliability_interruptions_amo_type', 'reliability_operational_interruptions', ['amo_id', 'interruption_type'], unique=False)
    op.create_index('ix_reliability_interruptions_flight', 'reliability_operational_interruptions', ['amo_id', 'flight_number', 'scheduled_departure_at'], unique=False)
    op.create_index(op.f('ix_reliability_operational_interruptions_amo_id'), 'reliability_operational_interruptions', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_operational_interruptions_cdl_reference'), 'reliability_operational_interruptions', ['cdl_reference'], unique=False)
    op.create_index(op.f('ix_reliability_operational_interruptions_flight_number'), 'reliability_operational_interruptions', ['flight_number'], unique=False)
    op.create_index(op.f('ix_reliability_operational_interruptions_interruption_type'), 'reliability_operational_interruptions', ['interruption_type'], unique=False)
    op.create_index(op.f('ix_reliability_operational_interruptions_mel_reference'), 'reliability_operational_interruptions', ['mel_reference'], unique=False)
    op.create_index(op.f('ix_reliability_operational_interruptions_reliability_event_id'), 'reliability_operational_interruptions', ['reliability_event_id'], unique=False)
    op.create_table('reliability_threshold_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('metric_definition_id', sa.String(length=36), nullable=False),
    sa.Column('version', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('caution_value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('alert_value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('lower_caution_value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('lower_alert_value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('minimum_exposure', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=True),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_threshold_versions_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], name=op.f('fk_reliability_threshold_versions_approved_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_reliability_threshold_versions_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['metric_definition_id'], ['reliability_metric_definitions.id'], name=op.f('fk_reliability_threshold_versions_metric_definition_id_reliability_metric_definitions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_threshold_versions')),
    sa.UniqueConstraint('metric_definition_id', 'version', name='uq_reliability_threshold_metric_version')
    )
    op.create_index('ix_reliability_threshold_status', 'reliability_threshold_versions', ['amo_id', 'status'], unique=False)
    op.create_index(op.f('ix_reliability_threshold_versions_amo_id'), 'reliability_threshold_versions', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_threshold_versions_metric_definition_id'), 'reliability_threshold_versions', ['metric_definition_id'], unique=False)
    op.create_index(op.f('ix_reliability_threshold_versions_status'), 'reliability_threshold_versions', ['status'], unique=False)
    op.create_table('reliability_data_quality_issues',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=True),
    sa.Column('batch_id', sa.String(length=36), nullable=True),
    sa.Column('record_id', sa.String(length=36), nullable=True),
    sa.Column('issue_code', sa.String(length=80), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('details_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_data_quality_issues_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['batch_id'], ['reliability_ingestion_batches.id'], name=op.f('fk_reliability_data_quality_issues_batch_id_reliability_ingestion_batches'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['record_id'], ['reliability_ingestion_records.id'], name=op.f('fk_reliability_data_quality_issues_record_id_reliability_ingestion_records'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], name=op.f('fk_reliability_data_quality_issues_resolved_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['reliability_sources.id'], name=op.f('fk_reliability_data_quality_issues_source_id_reliability_sources'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_data_quality_issues'))
    )
    op.create_index(op.f('ix_reliability_data_quality_issues_amo_id'), 'reliability_data_quality_issues', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_data_quality_issues_batch_id'), 'reliability_data_quality_issues', ['batch_id'], unique=False)
    op.create_index(op.f('ix_reliability_data_quality_issues_issue_code'), 'reliability_data_quality_issues', ['issue_code'], unique=False)
    op.create_index(op.f('ix_reliability_data_quality_issues_record_id'), 'reliability_data_quality_issues', ['record_id'], unique=False)
    op.create_index(op.f('ix_reliability_data_quality_issues_severity'), 'reliability_data_quality_issues', ['severity'], unique=False)
    op.create_index(op.f('ix_reliability_data_quality_issues_source_id'), 'reliability_data_quality_issues', ['source_id'], unique=False)
    op.create_index(op.f('ix_reliability_data_quality_issues_status'), 'reliability_data_quality_issues', ['status'], unique=False)
    op.create_index('ix_reliability_dq_amo_status', 'reliability_data_quality_issues', ['amo_id', 'status'], unique=False)
    op.create_index('ix_reliability_dq_source', 'reliability_data_quality_issues', ['source_id', 'created_at'], unique=False)
    op.create_table('reliability_fracas_lifecycles',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('fracas_case_id', sa.Integer(), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=False),
    sa.Column('triage_disposition', sa.String(length=40), nullable=True),
    sa.Column('containment_required', sa.Boolean(), nullable=False),
    sa.Column('containment_complete', sa.Boolean(), nullable=False),
    sa.Column('problem_statement', sa.Text(), nullable=True),
    sa.Column('root_cause_method', sa.String(length=80), nullable=True),
    sa.Column('root_cause_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('risk_assessment_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('effectiveness_due_date', sa.Date(), nullable=True),
    sa.Column('reopened_count', sa.Integer(), nullable=False),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('stage_entered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_fracas_lifecycles_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['fracas_case_id'], ['fracas_cases.id'], name=op.f('fk_reliability_fracas_lifecycles_fracas_case_id_fracas_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_reliability_fracas_lifecycles_owner_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_fracas_lifecycles')),
    sa.UniqueConstraint('amo_id', 'fracas_case_id', name='uq_reliability_fracas_lifecycle_case')
    )
    op.create_index(op.f('ix_reliability_fracas_lifecycles_amo_id'), 'reliability_fracas_lifecycles', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_fracas_lifecycles_fracas_case_id'), 'reliability_fracas_lifecycles', ['fracas_case_id'], unique=False)
    op.create_index(op.f('ix_reliability_fracas_lifecycles_stage'), 'reliability_fracas_lifecycles', ['stage'], unique=False)
    op.create_index('ix_reliability_fracas_stage', 'reliability_fracas_lifecycles', ['amo_id', 'stage'], unique=False)
    op.create_table('reliability_effectiveness_reviews',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('lifecycle_id', sa.String(length=36), nullable=False),
    sa.Column('review_date', sa.Date(), nullable=False),
    sa.Column('metric_code', sa.String(length=80), nullable=True),
    sa.Column('baseline_value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('current_value', sa.Numeric(precision=20, scale=8), nullable=True),
    sa.Column('acceptance_criteria', sa.Text(), nullable=False),
    sa.Column('outcome', sa.String(length=32), nullable=False),
    sa.Column('evidence_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('reviewer_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_effectiveness_reviews_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], name=op.f('fk_reliability_effectiveness_reviews_approved_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lifecycle_id'], ['reliability_fracas_lifecycles.id'], name=op.f('fk_reliability_effectiveness_reviews_lifecycle_id_reliability_fracas_lifecycles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], name=op.f('fk_reliability_effectiveness_reviews_reviewer_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_effectiveness_reviews'))
    )
    op.create_index('ix_reliability_effectiveness_lifecycle_date', 'reliability_effectiveness_reviews', ['lifecycle_id', 'review_date'], unique=False)
    op.create_index(op.f('ix_reliability_effectiveness_reviews_amo_id'), 'reliability_effectiveness_reviews', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_effectiveness_reviews_lifecycle_id'), 'reliability_effectiveness_reviews', ['lifecycle_id'], unique=False)
    op.create_index(op.f('ix_reliability_effectiveness_reviews_outcome'), 'reliability_effectiveness_reviews', ['outcome'], unique=False)
    op.create_table('reliability_fracas_evidence',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('lifecycle_id', sa.String(length=36), nullable=False),
    sa.Column('evidence_type', sa.String(length=40), nullable=False),
    sa.Column('reference_type', sa.String(length=60), nullable=True),
    sa.Column('reference_id', sa.String(length=128), nullable=True),
    sa.Column('reference_url', sa.Text(), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('captured_by_user_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_fracas_evidence_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['captured_by_user_id'], ['users.id'], name=op.f('fk_reliability_fracas_evidence_captured_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lifecycle_id'], ['reliability_fracas_lifecycles.id'], name=op.f('fk_reliability_fracas_evidence_lifecycle_id_reliability_fracas_lifecycles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_fracas_evidence'))
    )
    op.create_index(op.f('ix_reliability_fracas_evidence_amo_id'), 'reliability_fracas_evidence', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_fracas_evidence_evidence_type'), 'reliability_fracas_evidence', ['evidence_type'], unique=False)
    op.create_index('ix_reliability_fracas_evidence_lifecycle', 'reliability_fracas_evidence', ['lifecycle_id', 'captured_at'], unique=False)
    op.create_index(op.f('ix_reliability_fracas_evidence_lifecycle_id'), 'reliability_fracas_evidence', ['lifecycle_id'], unique=False)
    op.create_table('reliability_fracas_stage_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('lifecycle_id', sa.String(length=36), nullable=False),
    sa.Column('from_stage', sa.String(length=40), nullable=True),
    sa.Column('to_stage', sa.String(length=40), nullable=False),
    sa.Column('decision', sa.String(length=40), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('previous_hash', sa.String(length=64), nullable=True),
    sa.Column('event_hash', sa.String(length=64), nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_reliability_fracas_stage_events_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], name=op.f('fk_reliability_fracas_stage_events_amo_id_amos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lifecycle_id'], ['reliability_fracas_lifecycles.id'], name=op.f('fk_reliability_fracas_stage_events_lifecycle_id_reliability_fracas_lifecycles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reliability_fracas_stage_events')),
    sa.UniqueConstraint('event_hash')
    )
    op.create_index('ix_reliability_fracas_stage_event_chain', 'reliability_fracas_stage_events', ['lifecycle_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_reliability_fracas_stage_events_amo_id'), 'reliability_fracas_stage_events', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_fracas_stage_events_lifecycle_id'), 'reliability_fracas_stage_events', ['lifecycle_id'], unique=False)
    op.add_column('reliability_events', sa.Column('source_record_id', sa.String(length=255), nullable=True))
    op.add_column('reliability_events', sa.Column('source_payload_hash', sa.String(length=64), nullable=True))
    op.add_column('reliability_events', sa.Column('validation_status', sa.String(length=24), server_default=sa.text("'VALID'"), nullable=False))
    op.add_column('reliability_events', sa.Column('validation_errors', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column('reliability_events', sa.Column('provenance_json', sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column('reliability_events', sa.Column('operation_stage', sa.String(length=40), nullable=True))
    op.add_column('reliability_events', sa.Column('flight_number', sa.String(length=24), nullable=True))
    op.add_column('reliability_events', sa.Column('origin_station', sa.String(length=8), nullable=True))
    op.add_column('reliability_events', sa.Column('destination_station', sa.String(length=8), nullable=True))
    op.add_column('reliability_events', sa.Column('delay_minutes', sa.Integer(), nullable=True))
    op.add_column('reliability_events', sa.Column('mel_reference', sa.String(length=80), nullable=True))
    op.add_column('reliability_events', sa.Column('cdl_reference', sa.String(length=80), nullable=True))
    op.add_column('reliability_events', sa.Column('deferral_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('reliability_events', sa.Column('part_number', sa.String(length=80), nullable=True))
    op.add_column('reliability_events', sa.Column('component_serial_number', sa.String(length=80), nullable=True))
    op.add_column('reliability_events', sa.Column('confirmed_failure', sa.Boolean(), nullable=True))
    op.add_column('reliability_events', sa.Column('repeat_key', sa.String(length=255), nullable=True))
    op.alter_column('reliability_events', 'event_type',
               existing_type=sa.VARCHAR(length=12),
               type_=sa.Enum('DEFECT', 'REPEAT_DEFECT', 'PILOT_REPORT', 'CABIN_REPORT', 'TECHNICAL_DELAY', 'TECHNICAL_CANCELLATION', 'RETURN_TO_GATE', 'AIR_TURNBACK', 'DIVERSION', 'IN_FLIGHT_SHUTDOWN', 'ABORTED_TAKEOFF', 'MEL_DEFERRAL', 'CDL_DEFERRAL', 'UNSCHEDULED_REMOVAL', 'SCHEDULED_REMOVAL', 'REMOVAL', 'INSTALLATION', 'SHOP_FINDING', 'NO_FAULT_FOUND', 'OCTM', 'ECTM', 'EHM_ALERT', 'FRACAS', 'MAINTENANCE_ERROR', 'SUPPLIER_ESCAPE', 'SAFETY_EVENT', 'OTHER', name='reliability_event_type_enum', native_enum=False),
               existing_nullable=False)
    op.create_index(op.f('ix_reliability_events_amo_id'), 'reliability_events', ['amo_id'], unique=False)
    op.create_index(op.f('ix_reliability_events_ata_chapter'), 'reliability_events', ['ata_chapter'], unique=False)
    op.create_index(op.f('ix_reliability_events_cdl_reference'), 'reliability_events', ['cdl_reference'], unique=False)
    op.create_index('ix_reliability_events_component_identity', 'reliability_events', ['amo_id', 'part_number', 'component_serial_number'], unique=False)
    op.create_index(op.f('ix_reliability_events_component_serial_number'), 'reliability_events', ['component_serial_number'], unique=False)
    op.create_index(op.f('ix_reliability_events_deferral_expires_at'), 'reliability_events', ['deferral_expires_at'], unique=False)
    op.create_index(op.f('ix_reliability_events_flight_number'), 'reliability_events', ['flight_number'], unique=False)
    op.create_index(op.f('ix_reliability_events_id'), 'reliability_events', ['id'], unique=False)
    op.create_index(op.f('ix_reliability_events_mel_reference'), 'reliability_events', ['mel_reference'], unique=False)
    op.create_index(op.f('ix_reliability_events_operation_stage'), 'reliability_events', ['operation_stage'], unique=False)
    op.create_index(op.f('ix_reliability_events_operator_event_id'), 'reliability_events', ['operator_event_id'], unique=False)
    op.create_index(op.f('ix_reliability_events_part_number'), 'reliability_events', ['part_number'], unique=False)
    op.create_index('ix_reliability_events_repeat_key', 'reliability_events', ['amo_id', 'repeat_key'], unique=False)
    op.create_index(op.f('ix_reliability_events_severity'), 'reliability_events', ['severity'], unique=False)
    op.create_index(op.f('ix_reliability_events_source_payload_hash'), 'reliability_events', ['source_payload_hash'], unique=False)
    op.create_index(op.f('ix_reliability_events_source_record_id'), 'reliability_events', ['source_record_id'], unique=False)
    op.create_index(op.f('ix_reliability_events_source_system'), 'reliability_events', ['source_system'], unique=False)
    op.create_index(op.f('ix_reliability_events_validation_status'), 'reliability_events', ['validation_status'], unique=False)
    op.create_unique_constraint('uq_reliability_event_source_record', 'reliability_events', ['amo_id', 'source_system', 'source_record_id'])
    # ### end Alembic commands ###

    _seed_reliability_authorization()
    _install_append_only_guards()

def downgrade() -> None:
    _drop_append_only_guards()
    _remove_reliability_authorization()
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('uq_reliability_event_source_record', 'reliability_events', type_='unique')
    op.drop_index(op.f('ix_reliability_events_validation_status'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_source_system'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_source_record_id'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_source_payload_hash'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_severity'), table_name='reliability_events')
    op.drop_index('ix_reliability_events_repeat_key', table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_part_number'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_operator_event_id'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_operation_stage'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_mel_reference'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_id'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_flight_number'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_deferral_expires_at'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_component_serial_number'), table_name='reliability_events')
    op.drop_index('ix_reliability_events_component_identity', table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_cdl_reference'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_ata_chapter'), table_name='reliability_events')
    op.drop_index(op.f('ix_reliability_events_amo_id'), table_name='reliability_events')
    op.alter_column('reliability_events', 'event_type',
               existing_type=sa.Enum('DEFECT', 'REPEAT_DEFECT', 'PILOT_REPORT', 'CABIN_REPORT', 'TECHNICAL_DELAY', 'TECHNICAL_CANCELLATION', 'RETURN_TO_GATE', 'AIR_TURNBACK', 'DIVERSION', 'IN_FLIGHT_SHUTDOWN', 'ABORTED_TAKEOFF', 'MEL_DEFERRAL', 'CDL_DEFERRAL', 'UNSCHEDULED_REMOVAL', 'SCHEDULED_REMOVAL', 'REMOVAL', 'INSTALLATION', 'SHOP_FINDING', 'NO_FAULT_FOUND', 'OCTM', 'ECTM', 'EHM_ALERT', 'FRACAS', 'MAINTENANCE_ERROR', 'SUPPLIER_ESCAPE', 'SAFETY_EVENT', 'OTHER', name='reliability_event_type_enum', native_enum=False),
               type_=sa.VARCHAR(length=12),
               existing_nullable=False)
    op.drop_column('reliability_events', 'repeat_key')
    op.drop_column('reliability_events', 'confirmed_failure')
    op.drop_column('reliability_events', 'component_serial_number')
    op.drop_column('reliability_events', 'part_number')
    op.drop_column('reliability_events', 'deferral_expires_at')
    op.drop_column('reliability_events', 'cdl_reference')
    op.drop_column('reliability_events', 'mel_reference')
    op.drop_column('reliability_events', 'delay_minutes')
    op.drop_column('reliability_events', 'destination_station')
    op.drop_column('reliability_events', 'origin_station')
    op.drop_column('reliability_events', 'flight_number')
    op.drop_column('reliability_events', 'operation_stage')
    op.drop_column('reliability_events', 'provenance_json')
    op.drop_column('reliability_events', 'validation_errors')
    op.drop_column('reliability_events', 'validation_status')
    op.drop_column('reliability_events', 'source_payload_hash')
    op.drop_column('reliability_events', 'source_record_id')
    op.drop_index(op.f('ix_reliability_fracas_stage_events_lifecycle_id'), table_name='reliability_fracas_stage_events')
    op.drop_index(op.f('ix_reliability_fracas_stage_events_amo_id'), table_name='reliability_fracas_stage_events')
    op.drop_index('ix_reliability_fracas_stage_event_chain', table_name='reliability_fracas_stage_events')
    op.drop_table('reliability_fracas_stage_events')
    op.drop_index(op.f('ix_reliability_fracas_evidence_lifecycle_id'), table_name='reliability_fracas_evidence')
    op.drop_index('ix_reliability_fracas_evidence_lifecycle', table_name='reliability_fracas_evidence')
    op.drop_index(op.f('ix_reliability_fracas_evidence_evidence_type'), table_name='reliability_fracas_evidence')
    op.drop_index(op.f('ix_reliability_fracas_evidence_amo_id'), table_name='reliability_fracas_evidence')
    op.drop_table('reliability_fracas_evidence')
    op.drop_index(op.f('ix_reliability_effectiveness_reviews_outcome'), table_name='reliability_effectiveness_reviews')
    op.drop_index(op.f('ix_reliability_effectiveness_reviews_lifecycle_id'), table_name='reliability_effectiveness_reviews')
    op.drop_index(op.f('ix_reliability_effectiveness_reviews_amo_id'), table_name='reliability_effectiveness_reviews')
    op.drop_index('ix_reliability_effectiveness_lifecycle_date', table_name='reliability_effectiveness_reviews')
    op.drop_table('reliability_effectiveness_reviews')
    op.drop_index('ix_reliability_fracas_stage', table_name='reliability_fracas_lifecycles')
    op.drop_index(op.f('ix_reliability_fracas_lifecycles_stage'), table_name='reliability_fracas_lifecycles')
    op.drop_index(op.f('ix_reliability_fracas_lifecycles_fracas_case_id'), table_name='reliability_fracas_lifecycles')
    op.drop_index(op.f('ix_reliability_fracas_lifecycles_amo_id'), table_name='reliability_fracas_lifecycles')
    op.drop_table('reliability_fracas_lifecycles')
    op.drop_index('ix_reliability_dq_source', table_name='reliability_data_quality_issues')
    op.drop_index('ix_reliability_dq_amo_status', table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_status'), table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_source_id'), table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_severity'), table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_record_id'), table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_issue_code'), table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_batch_id'), table_name='reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_data_quality_issues_amo_id'), table_name='reliability_data_quality_issues')
    op.drop_table('reliability_data_quality_issues')
    op.drop_index(op.f('ix_reliability_threshold_versions_status'), table_name='reliability_threshold_versions')
    op.drop_index(op.f('ix_reliability_threshold_versions_metric_definition_id'), table_name='reliability_threshold_versions')
    op.drop_index(op.f('ix_reliability_threshold_versions_amo_id'), table_name='reliability_threshold_versions')
    op.drop_index('ix_reliability_threshold_status', table_name='reliability_threshold_versions')
    op.drop_table('reliability_threshold_versions')
    op.drop_index(op.f('ix_reliability_operational_interruptions_reliability_event_id'), table_name='reliability_operational_interruptions')
    op.drop_index(op.f('ix_reliability_operational_interruptions_mel_reference'), table_name='reliability_operational_interruptions')
    op.drop_index(op.f('ix_reliability_operational_interruptions_interruption_type'), table_name='reliability_operational_interruptions')
    op.drop_index(op.f('ix_reliability_operational_interruptions_flight_number'), table_name='reliability_operational_interruptions')
    op.drop_index(op.f('ix_reliability_operational_interruptions_cdl_reference'), table_name='reliability_operational_interruptions')
    op.drop_index(op.f('ix_reliability_operational_interruptions_amo_id'), table_name='reliability_operational_interruptions')
    op.drop_index('ix_reliability_interruptions_flight', table_name='reliability_operational_interruptions')
    op.drop_index('ix_reliability_interruptions_amo_type', table_name='reliability_operational_interruptions')
    op.drop_table('reliability_operational_interruptions')
    op.drop_index(op.f('ix_reliability_meeting_decisions_status'), table_name='reliability_meeting_decisions')
    op.drop_index(op.f('ix_reliability_meeting_decisions_meeting_id'), table_name='reliability_meeting_decisions')
    op.drop_index(op.f('ix_reliability_meeting_decisions_amo_id'), table_name='reliability_meeting_decisions')
    op.drop_index('ix_reliability_decision_meeting_status', table_name='reliability_meeting_decisions')
    op.drop_table('reliability_meeting_decisions')
    op.drop_index(op.f('ix_reliability_ingestion_records_validation_status'), table_name='reliability_ingestion_records')
    op.drop_index(op.f('ix_reliability_ingestion_records_source_id'), table_name='reliability_ingestion_records')
    op.drop_index(op.f('ix_reliability_ingestion_records_normalized_event_id'), table_name='reliability_ingestion_records')
    op.drop_index(op.f('ix_reliability_ingestion_records_batch_id'), table_name='reliability_ingestion_records')
    op.drop_index(op.f('ix_reliability_ingestion_records_amo_id'), table_name='reliability_ingestion_records')
    op.drop_index('ix_reliability_ingestion_batch_status', table_name='reliability_ingestion_records')
    op.drop_table('reliability_ingestion_records')
    op.drop_index('ix_reliability_calculation_scope', table_name='reliability_calculation_runs')
    op.drop_index(op.f('ix_reliability_calculation_runs_status'), table_name='reliability_calculation_runs')
    op.drop_index(op.f('ix_reliability_calculation_runs_metric_definition_id'), table_name='reliability_calculation_runs')
    op.drop_index(op.f('ix_reliability_calculation_runs_amo_id'), table_name='reliability_calculation_runs')
    op.drop_index('ix_reliability_calculation_metric_period', table_name='reliability_calculation_runs')
    op.drop_table('reliability_calculation_runs')
    op.drop_index(op.f('ix_reliability_authority_submissions_status'), table_name='reliability_authority_submissions')
    op.drop_index(op.f('ix_reliability_authority_submissions_authority_profile'), table_name='reliability_authority_submissions')
    op.drop_index(op.f('ix_reliability_authority_submissions_amo_id'), table_name='reliability_authority_submissions')
    op.drop_index('ix_reliability_authority_status', table_name='reliability_authority_submissions')
    op.drop_table('reliability_authority_submissions')
    op.drop_index(op.f('ix_reliability_review_meetings_status'), table_name='reliability_review_meetings')
    op.drop_index(op.f('ix_reliability_review_meetings_amo_id'), table_name='reliability_review_meetings')
    op.drop_index('ix_reliability_meeting_status', table_name='reliability_review_meetings')
    op.drop_index('ix_reliability_meeting_schedule', table_name='reliability_review_meetings')
    op.drop_table('reliability_review_meetings')
    op.drop_index('ix_reliability_metric_due', table_name='reliability_metric_definitions')
    op.drop_index(op.f('ix_reliability_metric_definitions_programme_version_id'), table_name='reliability_metric_definitions')
    op.drop_index(op.f('ix_reliability_metric_definitions_amo_id'), table_name='reliability_metric_definitions')
    op.drop_table('reliability_metric_definitions')
    op.drop_index('ix_reliability_change_status', table_name='reliability_change_proposals')
    op.drop_index('ix_reliability_change_source', table_name='reliability_change_proposals')
    op.drop_index(op.f('ix_reliability_change_proposals_status'), table_name='reliability_change_proposals')
    op.drop_index(op.f('ix_reliability_change_proposals_proposal_type'), table_name='reliability_change_proposals')
    op.drop_index(op.f('ix_reliability_change_proposals_amo_id'), table_name='reliability_change_proposals')
    op.drop_table('reliability_change_proposals')
    op.drop_index(op.f('ix_reliability_programme_versions_status'), table_name='reliability_programme_versions')
    op.drop_index(op.f('ix_reliability_programme_versions_programme_id'), table_name='reliability_programme_versions')
    op.drop_index(op.f('ix_reliability_programme_versions_amo_id'), table_name='reliability_programme_versions')
    op.drop_index('ix_reliability_programme_version_status', table_name='reliability_programme_versions')
    op.drop_table('reliability_programme_versions')
    op.drop_index(op.f('ix_reliability_ingestion_batches_status'), table_name='reliability_ingestion_batches')
    op.drop_index(op.f('ix_reliability_ingestion_batches_source_id'), table_name='reliability_ingestion_batches')
    op.drop_index(op.f('ix_reliability_ingestion_batches_content_hash'), table_name='reliability_ingestion_batches')
    op.drop_index(op.f('ix_reliability_ingestion_batches_amo_id'), table_name='reliability_ingestion_batches')
    op.drop_index('ix_reliability_batches_source_status', table_name='reliability_ingestion_batches')
    op.drop_index('ix_reliability_batches_amo_received', table_name='reliability_ingestion_batches')
    op.drop_table('reliability_ingestion_batches')
    op.drop_index(op.f('ix_reliability_handoffs_task_id'), table_name='reliability_handoffs')
    op.drop_index(op.f('ix_reliability_handoffs_target_module'), table_name='reliability_handoffs')
    op.drop_index(op.f('ix_reliability_handoffs_status'), table_name='reliability_handoffs')
    op.drop_index(op.f('ix_reliability_handoffs_amo_id'), table_name='reliability_handoffs')
    op.drop_index('ix_reliability_handoff_target_status', table_name='reliability_handoffs')
    op.drop_index('ix_reliability_handoff_source', table_name='reliability_handoffs')
    op.drop_table('reliability_handoffs')
    op.drop_index(op.f('ix_reliability_sources_status'), table_name='reliability_sources')
    op.drop_index(op.f('ix_reliability_sources_source_type'), table_name='reliability_sources')
    op.drop_index('ix_reliability_sources_due', table_name='reliability_sources')
    op.drop_index('ix_reliability_sources_amo_type', table_name='reliability_sources')
    op.drop_index(op.f('ix_reliability_sources_amo_id'), table_name='reliability_sources')
    op.drop_table('reliability_sources')
    op.drop_index(op.f('ix_reliability_programmes_status'), table_name='reliability_programmes')
    op.drop_index(op.f('ix_reliability_programmes_amo_id'), table_name='reliability_programmes')
    op.drop_index('ix_reliability_programme_status', table_name='reliability_programmes')
    op.drop_table('reliability_programmes')
    op.drop_index(op.f('ix_reliability_audit_events_amo_id'), table_name='reliability_audit_events')
    op.drop_index('ix_reliability_audit_entity', table_name='reliability_audit_events')
    op.drop_table('reliability_audit_events')
    op.drop_index('ix_reliability_ai_status', table_name='reliability_ai_reviews')
    op.drop_index(op.f('ix_reliability_ai_reviews_status'), table_name='reliability_ai_reviews')
    op.drop_index(op.f('ix_reliability_ai_reviews_amo_id'), table_name='reliability_ai_reviews')
    op.drop_index('ix_reliability_ai_entity', table_name='reliability_ai_reviews')
    op.drop_table('reliability_ai_reviews')
    # ### end Alembic commands ###
