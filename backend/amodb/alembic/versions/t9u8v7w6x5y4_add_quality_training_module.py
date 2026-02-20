"""add quality training module

Revision ID: t9u8v7w6x5y4
Revises: e41af43f2beb
Create Date: 2026-02-20
"""
from alembic import op
import sqlalchemy as sa


revision = 't9u8v7w6x5y4'
down_revision = 'e41af43f2beb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('quality_training_courses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('course_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=128), nullable=True),
        sa.Column('owner_department', sa.String(length=128), nullable=True),
        sa.Column('delivery_mode', sa.String(length=32), nullable=False),
        sa.Column('is_recurrent', sa.Boolean(), nullable=False),
        sa.Column('recurrence_interval_months', sa.Integer(), nullable=True),
        sa.Column('grace_window_days', sa.Integer(), nullable=True),
        sa.Column('prerequisites_text', sa.Text(), nullable=True),
        sa.Column('minimum_outcome_type', sa.String(length=32), nullable=False),
        sa.Column('minimum_score_optional', sa.Integer(), nullable=True),
        sa.Column('active_flag', sa.Boolean(), nullable=False),
        sa.Column('current_syllabus_asset_id', sa.String(length=128), nullable=True),
        sa.Column('certificate_template_asset_id', sa.String(length=128), nullable=True),
        sa.Column('evidence_requirements_json', sa.JSON(), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'course_id', name='uq_quality_training_course_tenant_course_id')
    )
    for name in ['quality_training_sessions','quality_training_session_attendees','quality_training_completion_records','quality_training_role_requirements','quality_training_staff_overrides','quality_training_authorisations','quality_training_audit_events','quality_training_settings']:
        pass
    op.create_table('quality_training_sessions', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('session_id', sa.String(64), nullable=False), sa.Column('course_id', sa.String(64), nullable=False), sa.Column('start_datetime', sa.DateTime(timezone=True), nullable=False), sa.Column('end_datetime', sa.DateTime(timezone=True), nullable=False), sa.Column('location_text', sa.String(255)), sa.Column('instructor_user_id', sa.String(36)), sa.Column('status', sa.String(32), nullable=False), sa.Column('capacity_optional', sa.Integer()), sa.Column('notes_text', sa.Text()))
    op.create_table('quality_training_session_attendees', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('session_id', sa.String(64), nullable=False), sa.Column('staff_id', sa.String(36), nullable=False), sa.Column('attendance_status', sa.String(32), nullable=False), sa.Column('attendance_marked_at', sa.DateTime(timezone=True)), sa.Column('result_outcome', sa.String(32)), sa.Column('score_optional', sa.Integer()), sa.Column('remarks_text', sa.Text()), sa.Column('evidence_asset_ids', sa.JSON()))
    op.create_table('quality_training_completion_records', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('completion_id', sa.String(64), nullable=False), sa.Column('staff_id', sa.String(36), nullable=False), sa.Column('course_id', sa.String(64), nullable=False), sa.Column('completion_date', sa.Date(), nullable=False), sa.Column('outcome', sa.String(32), nullable=False), sa.Column('score_optional', sa.Integer()), sa.Column('source_session_id', sa.String(64)), sa.Column('next_due_date', sa.Date()), sa.Column('evidence_asset_ids', sa.JSON()))
    op.create_table('quality_training_role_requirements', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('role_id', sa.String(64), nullable=False), sa.Column('course_id', sa.String(64), nullable=False), sa.Column('required_flag', sa.Boolean(), nullable=False), sa.Column('interval_override_months', sa.Integer()), sa.Column('initial_only_flag', sa.Boolean(), nullable=False), sa.Column('notes_text', sa.Text()))
    op.create_table('quality_training_staff_overrides', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('staff_id', sa.String(36), nullable=False), sa.Column('course_id', sa.String(64), nullable=False), sa.Column('override_type', sa.String(32), nullable=False), sa.Column('interval_override_months', sa.Integer()), sa.Column('reason_text', sa.Text(), nullable=False), sa.Column('approved_by_user_id', sa.String(36), nullable=False), sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('quality_training_authorisations', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('auth_id', sa.String(64), nullable=False), sa.Column('staff_id', sa.String(36), nullable=False), sa.Column('auth_type', sa.String(128), nullable=False), sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True)), sa.Column('granted_by_user_id', sa.String(36)), sa.Column('evidence_asset_id', sa.String(128)), sa.Column('status', sa.String(32), nullable=False))
    op.create_table('quality_training_audit_events', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False), sa.Column('object_type', sa.String(64), nullable=False), sa.Column('object_id', sa.String(64), nullable=False), sa.Column('action', sa.String(32), nullable=False), sa.Column('actor_user_id', sa.String(36)), sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False), sa.Column('diff_json', sa.JSON(), nullable=False))
    op.create_table('quality_training_settings', sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False, unique=True), sa.Column('default_recurrence_interval_months', sa.Integer(), nullable=False), sa.Column('default_grace_window_days', sa.Integer(), nullable=False), sa.Column('certificate_mandatory_default', sa.Boolean(), nullable=False), sa.Column('attendance_sheet_mandatory_default', sa.Boolean(), nullable=False))


def downgrade() -> None:
    for table in ['quality_training_settings','quality_training_audit_events','quality_training_authorisations','quality_training_staff_overrides','quality_training_role_requirements','quality_training_completion_records','quality_training_session_attendees','quality_training_sessions','quality_training_courses']:
        op.drop_table(table)
