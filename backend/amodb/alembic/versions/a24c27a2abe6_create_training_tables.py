"""create training tables

Revision ID: a24c27a2abe6
Revises: b9a8860cf4f2
Create Date: 2025-12-18 16:45:19.636432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a24c27a2abe6'
down_revision: Union[str, Sequence[str], None] = 'b9a8860cf4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

    # AUTO-FIX: enum precreate (checkfirst)
    bind = op.get_bind()
    postgresql.ENUM('PLANNED', 'DUE_SOON', 'OVERDUE', 'COMPLETED', 'SUSPENDED', name='aircraft_program_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('AIRFRAME', 'ENGINE', 'PROP', 'AD', 'SB', 'HT', 'OTHER', name='maintenance_program_category').create(bind, checkfirst=True)
    postgresql.ENUM('ACTIVE', 'SUSPENDED', 'DELETED', name='program_item_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('LEAD', 'SUPPORT', 'INSPECTOR', name='task_assignment_role').create(bind, checkfirst=True)
    postgresql.ENUM('ASSIGNED', 'ACCEPTED', 'REJECTED', 'COMPLETED', name='task_assignment_status').create(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'UNSCHEDULED', 'DEFECT', 'MODIFICATION', name='task_category').create(bind, checkfirst=True)
    postgresql.ENUM('INDEPENDENT_INSPECTION', 'FUNCTIONAL_TEST', 'OPERATIONAL_CHECK', 'DUPLICATE_INSPECTION', 'OTHER', name='task_error_capturing_method').create(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'NON_ROUTINE', name='task_origin_type').create(bind, checkfirst=True)
    postgresql.ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', name='task_priority').create(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'PAUSED', 'COMPLETED', 'DEFERRED', 'CANCELLED', name='task_status').create(bind, checkfirst=True)
    postgresql.ENUM('HF', 'FTS', 'EWIS', 'SMS', 'TYPE', 'INTERNAL_TECHNICAL', 'QUALITY_SYSTEMS', 'REGULATORY', 'OTHER', name='training_course_category_enum').create(bind, checkfirst=True)
    postgresql.ENUM('ILLNESS', 'OPERATIONAL_REQUIREMENTS', 'PERSONAL_EMERGENCY', 'PROVIDER_CANCELLATION', 'SYSTEM_FAILURE', 'OTHER', name='training_deferral_reason_enum').create(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='training_deferral_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('CLASSROOM', 'ONLINE', 'OJT', 'MIXED', 'OTHER', name='training_delivery_method_enum').create(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='training_event_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('CERTIFICATE', 'AMEL', 'LICENSE', 'EVIDENCE', 'OTHER', name='training_file_kind_enum').create(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', name='training_file_review_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('INITIAL', 'CONTINUATION', 'RECURRENT', 'REFRESHER', 'OTHER', name='training_kind_enum').create(bind, checkfirst=True)
    postgresql.ENUM('INFO', 'ACTION_REQUIRED', 'WARNING', name='training_notification_severity_enum').create(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'INVITED', 'CONFIRMED', 'ATTENDED', 'NO_SHOW', 'CANCELLED', 'DEFERRED', name='training_participant_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'VERIFIED', 'REJECTED', name='training_record_verification_status_enum').create(bind, checkfirst=True)
    postgresql.ENUM('ALL', 'DEPARTMENT', 'JOB_ROLE', 'USER', name='training_requirement_scope_enum').create(bind, checkfirst=True)
    postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'CLOSED', 'CANCELLED', name='work_order_status').create(bind, checkfirst=True)
    postgresql.ENUM('LINE', 'BASE', 'PERIODIC', 'UNSCHEDULED', 'MODIFICATION', 'DEFECT', 'OTHER', name='work_order_type').create(bind, checkfirst=True)


def upgrade() -> None:
    # AUTO-FIX: enum precreate (PostgreSQL requires CREATE TYPE before ALTER TABLE ADD COLUMN)
    bind = op.get_bind()
    postgresql.ENUM('AIRFRAME', 'ENGINE', 'PROP', 'AD', 'SB', 'HT', 'OTHER', name='maintenance_program_category', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('ACTIVE', 'SUSPENDED', 'DELETED', name='program_item_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'DUE_SOON', 'OVERDUE', 'COMPLETED', 'SUSPENDED', name='aircraft_program_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('HF', 'FTS', 'EWIS', 'SMS', 'TYPE', 'INTERNAL_TECHNICAL', 'QUALITY_SYSTEMS', 'REGULATORY', 'OTHER', name='training_course_category_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('INITIAL', 'CONTINUATION', 'RECURRENT', 'REFRESHER', 'OTHER', name='training_kind_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('CLASSROOM', 'ONLINE', 'OJT', 'MIXED', 'OTHER', name='training_delivery_method_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('INFO', 'ACTION_REQUIRED', 'WARNING', name='training_notification_severity_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'UNSCHEDULED', 'DEFECT', 'MODIFICATION', name='task_category', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'NON_ROUTINE', name='task_origin_type', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', name='task_priority', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'PAUSED', 'COMPLETED', 'DEFERRED', 'CANCELLED', name='task_status', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('INDEPENDENT_INSPECTION', 'FUNCTIONAL_TEST', 'OPERATIONAL_CHECK', 'DUPLICATE_INSPECTION', 'OTHER', name='task_error_capturing_method', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('ILLNESS', 'OPERATIONAL_REQUIREMENTS', 'PERSONAL_EMERGENCY', 'PROVIDER_CANCELLATION', 'SYSTEM_FAILURE', 'OTHER', name='training_deferral_reason_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='training_deferral_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='training_event_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('ALL', 'DEPARTMENT', 'JOB_ROLE', 'USER', name='training_requirement_scope_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('LEAD', 'SUPPORT', 'INSPECTOR', name='task_assignment_role', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('ASSIGNED', 'ACCEPTED', 'REJECTED', 'COMPLETED', name='task_assignment_status', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'INVITED', 'CONFIRMED', 'ATTENDED', 'NO_SHOW', 'CANCELLED', 'DEFERRED', name='training_participant_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'VERIFIED', 'REJECTED', name='training_record_verification_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('CERTIFICATE', 'AMEL', 'LICENSE', 'EVIDENCE', 'OTHER', name='training_file_kind_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', name='training_file_review_status_enum', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('LINE', 'BASE', 'PERIODIC', 'UNSCHEDULED', 'MODIFICATION', 'DEFECT', 'OTHER', name='work_order_type', create_type=False).create(bind, checkfirst=True)
    postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'CLOSED', 'CANCELLED', name='work_order_status', create_type=False).create(bind, checkfirst=True)

    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('maintenance_program_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aircraft_template', sa.String(length=50), nullable=False),
    sa.Column('ata_chapter', sa.String(length=20), nullable=True),
    sa.Column('task_code', sa.String(length=64), nullable=True),
    sa.Column('category', postgresql.ENUM('AIRFRAME', 'ENGINE', 'PROP', 'AD', 'SB', 'HT', 'OTHER', name='maintenance_program_category', create_type=False), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('interval_hours', sa.Float(), nullable=True),
    sa.Column('interval_cycles', sa.Float(), nullable=True),
    sa.Column('interval_days', sa.Integer(), nullable=True),
    sa.Column('is_mandatory', sa.Boolean(), nullable=False),
    sa.Column('template_code', sa.String(length=50), nullable=False),
    sa.Column('task_number', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('threshold_hours', sa.Float(), nullable=True),
    sa.Column('threshold_cycles', sa.Float(), nullable=True),
    sa.Column('threshold_days', sa.Integer(), nullable=True),
    sa.Column('default_zone', sa.String(length=32), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'SUSPENDED', 'DELETED', name='program_item_status_enum', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_maintenance_program_items_aircraft_template'), 'maintenance_program_items', ['aircraft_template'], unique=False)
    op.create_index(op.f('ix_maintenance_program_items_ata_chapter'), 'maintenance_program_items', ['ata_chapter'], unique=False)
    op.create_index(op.f('ix_maintenance_program_items_id'), 'maintenance_program_items', ['id'], unique=False)
    op.create_index(op.f('ix_maintenance_program_items_task_code'), 'maintenance_program_items', ['task_code'], unique=False)
    op.create_index(op.f('ix_maintenance_program_items_task_number'), 'maintenance_program_items', ['task_number'], unique=False)
    op.create_index(op.f('ix_maintenance_program_items_template_code'), 'maintenance_program_items', ['template_code'], unique=False)
    op.create_table('maintenance_statuses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aircraft_serial_number', sa.String(length=50), nullable=False),
    sa.Column('program_item_id', sa.Integer(), nullable=False),
    sa.Column('last_done_date', sa.Date(), nullable=True),
    sa.Column('last_done_hours', sa.Float(), nullable=True),
    sa.Column('last_done_cycles', sa.Float(), nullable=True),
    sa.Column('next_due_date', sa.Date(), nullable=True),
    sa.Column('next_due_hours', sa.Float(), nullable=True),
    sa.Column('next_due_cycles', sa.Float(), nullable=True),
    sa.Column('remaining_days', sa.Integer(), nullable=True),
    sa.Column('remaining_hours', sa.Float(), nullable=True),
    sa.Column('remaining_cycles', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['aircraft_serial_number'], ['aircraft.serial_number'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['program_item_id'], ['maintenance_program_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('aircraft_serial_number', 'program_item_id', name='uq_maintenance_status_aircraft_program_item')
    )
    op.create_index(op.f('ix_maintenance_statuses_aircraft_serial_number'), 'maintenance_statuses', ['aircraft_serial_number'], unique=False)
    op.create_index(op.f('ix_maintenance_statuses_id'), 'maintenance_statuses', ['id'], unique=False)
    op.create_index(op.f('ix_maintenance_statuses_program_item_id'), 'maintenance_statuses', ['program_item_id'], unique=False)
    op.create_table('aircraft_program_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aircraft_serial_number', sa.String(length=50), nullable=False),
    sa.Column('program_item_id', sa.Integer(), nullable=False),
    sa.Column('aircraft_component_id', sa.Integer(), nullable=True),
    sa.Column('override_title', sa.String(length=255), nullable=True),
    sa.Column('override_task_code', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('last_done_hours', sa.Float(), nullable=True),
    sa.Column('last_done_cycles', sa.Float(), nullable=True),
    sa.Column('last_done_date', sa.Date(), nullable=True),
    sa.Column('next_due_hours', sa.Float(), nullable=True),
    sa.Column('next_due_cycles', sa.Float(), nullable=True),
    sa.Column('next_due_date', sa.Date(), nullable=True),
    sa.Column('remaining_hours', sa.Float(), nullable=True),
    sa.Column('remaining_cycles', sa.Float(), nullable=True),
    sa.Column('remaining_days', sa.Integer(), nullable=True),
    sa.Column('status', postgresql.ENUM('PLANNED', 'DUE_SOON', 'OVERDUE', 'COMPLETED', 'SUSPENDED', name='aircraft_program_status_enum', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['aircraft_component_id'], ['aircraft_components.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['aircraft_serial_number'], ['aircraft.serial_number'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['program_item_id'], ['maintenance_program_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aircraft_program_items_aircraft_component_id'), 'aircraft_program_items', ['aircraft_component_id'], unique=False)
    op.create_index(op.f('ix_aircraft_program_items_aircraft_serial_number'), 'aircraft_program_items', ['aircraft_serial_number'], unique=False)
    op.create_index(op.f('ix_aircraft_program_items_id'), 'aircraft_program_items', ['id'], unique=False)
    op.create_index(op.f('ix_aircraft_program_items_program_item_id'), 'aircraft_program_items', ['program_item_id'], unique=False)
    op.create_table('aircraft_usage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aircraft_serial_number', sa.String(length=50), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('techlog_no', sa.String(length=64), nullable=False),
    sa.Column('station', sa.String(length=16), nullable=True),
    sa.Column('block_hours', sa.Float(), nullable=False),
    sa.Column('cycles', sa.Float(), nullable=False),
    sa.Column('ttaf_after', sa.Float(), nullable=True),
    sa.Column('tca_after', sa.Float(), nullable=True),
    sa.Column('ttesn_after', sa.Float(), nullable=True),
    sa.Column('tcesn_after', sa.Float(), nullable=True),
    sa.Column('ttsoh_after', sa.Float(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('updated_by_user_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['aircraft_serial_number'], ['aircraft.serial_number'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('aircraft_serial_number', 'date', 'techlog_no', name='uq_aircraft_usage_aircraft_date_techlog')
    )
    op.create_index(op.f('ix_aircraft_usage_aircraft_serial_number'), 'aircraft_usage', ['aircraft_serial_number'], unique=False)
    op.create_index(op.f('ix_aircraft_usage_date'), 'aircraft_usage', ['date'], unique=False)
    op.create_index(op.f('ix_aircraft_usage_id'), 'aircraft_usage', ['id'], unique=False)
    op.create_table('training_audit_logs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_training_audit_actor', 'training_audit_logs', ['amo_id', 'actor_user_id', 'created_at'], unique=False)
    op.create_index('idx_training_audit_amo_created', 'training_audit_logs', ['amo_id', 'created_at'], unique=False)
    op.create_index('idx_training_audit_entity', 'training_audit_logs', ['amo_id', 'entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_training_audit_logs_action'), 'training_audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_training_audit_logs_actor_user_id'), 'training_audit_logs', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_training_audit_logs_amo_id'), 'training_audit_logs', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_audit_logs_entity_id'), 'training_audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_training_audit_logs_entity_type'), 'training_audit_logs', ['entity_type'], unique=False)
    op.create_table('training_courses',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('course_id', sa.String(length=64), nullable=False),
    sa.Column('course_name', sa.String(length=255), nullable=False),
    sa.Column('frequency_months', sa.Integer(), nullable=True),
    sa.Column('category', postgresql.ENUM('HF', 'FTS', 'EWIS', 'SMS', 'TYPE', 'INTERNAL_TECHNICAL', 'QUALITY_SYSTEMS', 'REGULATORY', 'OTHER', name='training_course_category_enum', create_type=False), nullable=False),
    sa.Column('kind', postgresql.ENUM('INITIAL', 'CONTINUATION', 'RECURRENT', 'REFRESHER', 'OTHER', name='training_kind_enum', create_type=False), nullable=False),
    sa.Column('delivery_method', postgresql.ENUM('CLASSROOM', 'ONLINE', 'OJT', 'MIXED', 'OTHER', name='training_delivery_method_enum', create_type=False), nullable=False),
    sa.Column('regulatory_reference', sa.String(length=255), nullable=True),
    sa.Column('default_provider', sa.String(length=255), nullable=True),
    sa.Column('default_duration_days', sa.Integer(), nullable=True),
    sa.Column('is_mandatory', sa.Boolean(), nullable=False),
    sa.Column('mandatory_for_all', sa.Boolean(), nullable=False),
    sa.Column('prerequisite_course_id', sa.String(length=64), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('updated_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('amo_id', 'course_id', name='uq_training_courses_amo_courseid')
    )
    op.create_index('idx_training_courses_amo_active', 'training_courses', ['amo_id', 'is_active'], unique=False)
    op.create_index('idx_training_courses_amo_category', 'training_courses', ['amo_id', 'category'], unique=False)
    op.create_index(op.f('ix_training_courses_amo_id'), 'training_courses', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_courses_category'), 'training_courses', ['category'], unique=False)
    op.create_index(op.f('ix_training_courses_is_active'), 'training_courses', ['is_active'], unique=False)
    op.create_index(op.f('ix_training_courses_kind'), 'training_courses', ['kind'], unique=False)
    op.create_table('training_notifications',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('severity', postgresql.ENUM('INFO', 'ACTION_REQUIRED', 'WARNING', name='training_notification_severity_enum', create_type=False), nullable=False),
    sa.Column('link_path', sa.String(length=255), nullable=True),
    sa.Column('dedupe_key', sa.String(length=255), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('amo_id', 'user_id', 'dedupe_key', name='uq_training_notifications_dedupe')
    )
    op.create_index('idx_training_notifications_amo_user_created', 'training_notifications', ['amo_id', 'user_id', 'created_at'], unique=False)
    op.create_index('idx_training_notifications_amo_user_unread', 'training_notifications', ['amo_id', 'user_id', 'read_at'], unique=False)
    op.create_index(op.f('ix_training_notifications_amo_id'), 'training_notifications', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_notifications_severity'), 'training_notifications', ['severity'], unique=False)
    op.create_index(op.f('ix_training_notifications_user_id'), 'training_notifications', ['user_id'], unique=False)
    op.create_table('task_cards',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('work_order_id', sa.Integer(), nullable=False),
    sa.Column('aircraft_serial_number', sa.String(length=50), nullable=False),
    sa.Column('aircraft_component_id', sa.Integer(), nullable=True),
    sa.Column('program_item_id', sa.Integer(), nullable=True),
    sa.Column('parent_task_id', sa.Integer(), nullable=True),
    sa.Column('ata_chapter', sa.String(length=20), nullable=True),
    sa.Column('task_code', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', postgresql.ENUM('SCHEDULED', 'UNSCHEDULED', 'DEFECT', 'MODIFICATION', name='task_category', create_type=False), nullable=False),
    sa.Column('origin_type', postgresql.ENUM('SCHEDULED', 'NON_ROUTINE', name='task_origin_type', create_type=False), nullable=False),
    sa.Column('priority', postgresql.ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', name='task_priority', create_type=False), nullable=False),
    sa.Column('zone', sa.String(length=32), nullable=True),
    sa.Column('access_panel', sa.String(length=64), nullable=True),
    sa.Column('planned_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('planned_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('estimated_manhours', sa.Float(), nullable=True),
    sa.Column('status', postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'PAUSED', 'COMPLETED', 'DEFERRED', 'CANCELLED', name='task_status', create_type=False), nullable=False),
    sa.Column('actual_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_capturing_method', postgresql.ENUM('INDEPENDENT_INSPECTION', 'FUNCTIONAL_TEST', 'OPERATIONAL_CHECK', 'DUPLICATE_INSPECTION', 'OTHER', name='task_error_capturing_method', create_type=False), nullable=True),
    sa.Column('requires_duplicate_inspection', sa.Boolean(), nullable=False),
    sa.Column('hf_notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('updated_by_user_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['aircraft_component_id'], ['aircraft_components.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['aircraft_serial_number'], ['aircraft.serial_number'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_task_id'], ['task_cards.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['program_item_id'], ['maintenance_program_items.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('work_order_id', 'task_code', name='uq_taskcard_workorder_taskcode')
    )
    op.create_index(op.f('ix_task_cards_aircraft_component_id'), 'task_cards', ['aircraft_component_id'], unique=False)
    op.create_index(op.f('ix_task_cards_aircraft_serial_number'), 'task_cards', ['aircraft_serial_number'], unique=False)
    op.create_index(op.f('ix_task_cards_ata_chapter'), 'task_cards', ['ata_chapter'], unique=False)
    op.create_index(op.f('ix_task_cards_id'), 'task_cards', ['id'], unique=False)
    op.create_index(op.f('ix_task_cards_parent_task_id'), 'task_cards', ['parent_task_id'], unique=False)
    op.create_index(op.f('ix_task_cards_program_item_id'), 'task_cards', ['program_item_id'], unique=False)
    op.create_index(op.f('ix_task_cards_task_code'), 'task_cards', ['task_code'], unique=False)
    op.create_index(op.f('ix_task_cards_work_order_id'), 'task_cards', ['work_order_id'], unique=False)
    op.create_table('training_deferral_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('requested_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('course_id', sa.String(length=36), nullable=False),
    sa.Column('original_due_date', sa.Date(), nullable=False),
    sa.Column('requested_new_due_date', sa.Date(), nullable=False),
    sa.Column('reason_category', postgresql.ENUM('ILLNESS', 'OPERATIONAL_REQUIREMENTS', 'PERSONAL_EMERGENCY', 'PROVIDER_CANCELLATION', 'SYSTEM_FAILURE', 'OTHER', name='training_deferral_reason_enum', create_type=False), nullable=False),
    sa.Column('reason_text', sa.Text(), nullable=True),
    sa.Column('status', postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='training_deferral_status_enum', create_type=False), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('decision_comment', sa.Text(), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['training_courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_training_deferrals_amo_status', 'training_deferral_requests', ['amo_id', 'status'], unique=False)
    op.create_index('idx_training_deferrals_user_course_status', 'training_deferral_requests', ['user_id', 'course_id', 'status'], unique=False)
    op.create_index(op.f('ix_training_deferral_requests_amo_id'), 'training_deferral_requests', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_deferral_requests_course_id'), 'training_deferral_requests', ['course_id'], unique=False)
    op.create_index(op.f('ix_training_deferral_requests_decided_by_user_id'), 'training_deferral_requests', ['decided_by_user_id'], unique=False)
    op.create_index(op.f('ix_training_deferral_requests_requested_by_user_id'), 'training_deferral_requests', ['requested_by_user_id'], unique=False)
    op.create_index(op.f('ix_training_deferral_requests_status'), 'training_deferral_requests', ['status'], unique=False)
    op.create_index(op.f('ix_training_deferral_requests_user_id'), 'training_deferral_requests', ['user_id'], unique=False)
    op.create_table('training_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('course_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('provider', sa.String(length=255), nullable=True),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=True),
    sa.Column('status', postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='training_event_status_enum', create_type=False), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['training_courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_training_events_amo_course_date', 'training_events', ['amo_id', 'course_id', 'starts_on'], unique=False)
    op.create_index('idx_training_events_amo_status', 'training_events', ['amo_id', 'status'], unique=False)
    op.create_index(op.f('ix_training_events_amo_id'), 'training_events', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_events_course_id'), 'training_events', ['course_id'], unique=False)
    op.create_index(op.f('ix_training_events_status'), 'training_events', ['status'], unique=False)
    op.create_table('training_requirements',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('course_id', sa.String(length=36), nullable=False),
    sa.Column('scope', postgresql.ENUM('ALL', 'DEPARTMENT', 'JOB_ROLE', 'USER', name='training_requirement_scope_enum', create_type=False), nullable=False),
    sa.Column('department_code', sa.String(length=64), nullable=True),
    sa.Column('job_role', sa.String(length=128), nullable=True),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('is_mandatory', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=True),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['training_courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_training_requirements_amo_active', 'training_requirements', ['amo_id', 'is_active'], unique=False)
    op.create_index('idx_training_requirements_amo_scope', 'training_requirements', ['amo_id', 'scope'], unique=False)
    op.create_index('idx_training_requirements_dept', 'training_requirements', ['amo_id', 'department_code'], unique=False)
    op.create_index('idx_training_requirements_role', 'training_requirements', ['amo_id', 'job_role'], unique=False)
    op.create_index('idx_training_requirements_user', 'training_requirements', ['amo_id', 'user_id'], unique=False)
    op.create_index(op.f('ix_training_requirements_amo_id'), 'training_requirements', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_requirements_course_id'), 'training_requirements', ['course_id'], unique=False)
    op.create_index(op.f('ix_training_requirements_department_code'), 'training_requirements', ['department_code'], unique=False)
    op.create_index(op.f('ix_training_requirements_is_active'), 'training_requirements', ['is_active'], unique=False)
    op.create_index(op.f('ix_training_requirements_job_role'), 'training_requirements', ['job_role'], unique=False)
    op.create_index(op.f('ix_training_requirements_scope'), 'training_requirements', ['scope'], unique=False)
    op.create_index(op.f('ix_training_requirements_user_id'), 'training_requirements', ['user_id'], unique=False)
    op.create_table('task_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('role_on_task', postgresql.ENUM('LEAD', 'SUPPORT', 'INSPECTOR', name='task_assignment_role', create_type=False), nullable=False),
    sa.Column('allocated_hours', sa.Float(), nullable=True),
    sa.Column('status', postgresql.ENUM('ASSIGNED', 'ACCEPTED', 'REJECTED', 'COMPLETED', name='task_assignment_status', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['task_cards.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_task_assignments_id'), 'task_assignments', ['id'], unique=False)
    op.create_index(op.f('ix_task_assignments_task_id'), 'task_assignments', ['task_id'], unique=False)
    op.create_index(op.f('ix_task_assignments_user_id'), 'task_assignments', ['user_id'], unique=False)
    op.create_table('training_event_participants',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('status', postgresql.ENUM('SCHEDULED', 'INVITED', 'CONFIRMED', 'ATTENDED', 'NO_SHOW', 'CANCELLED', 'DEFERRED', name='training_participant_status_enum', create_type=False), nullable=False),
    sa.Column('attendance_note', sa.Text(), nullable=True),
    sa.Column('attendance_marked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attendance_marked_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('attended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('deferral_request_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['attendance_marked_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deferral_request_id'], ['training_deferral_requests.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['event_id'], ['training_events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'user_id', name='uq_training_event_participants_event_user')
    )
    op.create_index('idx_training_participants_amo_user', 'training_event_participants', ['amo_id', 'user_id'], unique=False)
    op.create_index('idx_training_participants_event', 'training_event_participants', ['event_id'], unique=False)
    op.create_index('idx_training_participants_user', 'training_event_participants', ['user_id'], unique=False)
    op.create_index(op.f('ix_training_event_participants_amo_id'), 'training_event_participants', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_event_participants_attendance_marked_by_user_id'), 'training_event_participants', ['attendance_marked_by_user_id'], unique=False)
    op.create_index(op.f('ix_training_event_participants_deferral_request_id'), 'training_event_participants', ['deferral_request_id'], unique=False)
    op.create_index(op.f('ix_training_event_participants_event_id'), 'training_event_participants', ['event_id'], unique=False)
    op.create_index(op.f('ix_training_event_participants_status'), 'training_event_participants', ['status'], unique=False)
    op.create_index(op.f('ix_training_event_participants_user_id'), 'training_event_participants', ['user_id'], unique=False)
    op.create_table('training_records',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('course_id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=True),
    sa.Column('completion_date', sa.Date(), nullable=False),
    sa.Column('valid_until', sa.Date(), nullable=True),
    sa.Column('hours_completed', sa.Integer(), nullable=True),
    sa.Column('exam_score', sa.Integer(), nullable=True),
    sa.Column('certificate_reference', sa.String(length=255), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('verification_status', postgresql.ENUM('PENDING', 'VERIFIED', 'REJECTED', name='training_record_verification_status_enum', create_type=False), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('verification_comment', sa.Text(), nullable=True),
    sa.Column('is_manual_entry', sa.Boolean(), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['training_courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['event_id'], ['training_events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['verified_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_training_records_amo_user', 'training_records', ['amo_id', 'user_id'], unique=False)
    op.create_index('idx_training_records_user_course', 'training_records', ['user_id', 'course_id'], unique=False)
    op.create_index('idx_training_records_validity', 'training_records', ['valid_until'], unique=False)
    op.create_index(op.f('ix_training_records_amo_id'), 'training_records', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_records_course_id'), 'training_records', ['course_id'], unique=False)
    op.create_index(op.f('ix_training_records_event_id'), 'training_records', ['event_id'], unique=False)
    op.create_index(op.f('ix_training_records_user_id'), 'training_records', ['user_id'], unique=False)
    op.create_index(op.f('ix_training_records_verification_status'), 'training_records', ['verification_status'], unique=False)
    op.create_index(op.f('ix_training_records_verified_by_user_id'), 'training_records', ['verified_by_user_id'], unique=False)
    op.create_table('work_log_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actual_hours', sa.Float(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('station', sa.String(length=16), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['task_cards.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_log_entries_id'), 'work_log_entries', ['id'], unique=False)
    op.create_index(op.f('ix_work_log_entries_task_id'), 'work_log_entries', ['task_id'], unique=False)
    op.create_index(op.f('ix_work_log_entries_user_id'), 'work_log_entries', ['user_id'], unique=False)
    op.create_table('training_files',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('amo_id', sa.String(length=36), nullable=False),
    sa.Column('owner_user_id', sa.String(length=36), nullable=False),
    sa.Column('kind', postgresql.ENUM('CERTIFICATE', 'AMEL', 'LICENSE', 'EVIDENCE', 'OTHER', name='training_file_kind_enum', create_type=False), nullable=False),
    sa.Column('course_id', sa.String(length=36), nullable=True),
    sa.Column('event_id', sa.String(length=36), nullable=True),
    sa.Column('record_id', sa.String(length=36), nullable=True),
    sa.Column('deferral_request_id', sa.String(length=36), nullable=True),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False),
    sa.Column('content_type', sa.String(length=128), nullable=True),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('review_status', postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', name='training_file_review_status_enum', create_type=False), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('review_comment', sa.Text(), nullable=True),
    sa.Column('uploaded_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['amo_id'], ['amos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['training_courses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deferral_request_id'], ['training_deferral_requests.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['event_id'], ['training_events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['record_id'], ['training_records.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_training_files_amo_owner', 'training_files', ['amo_id', 'owner_user_id'], unique=False)
    op.create_index('idx_training_files_course', 'training_files', ['amo_id', 'course_id'], unique=False)
    op.create_index('idx_training_files_deferral', 'training_files', ['amo_id', 'deferral_request_id'], unique=False)
    op.create_index('idx_training_files_event', 'training_files', ['amo_id', 'event_id'], unique=False)
    op.create_index('idx_training_files_record', 'training_files', ['amo_id', 'record_id'], unique=False)
    op.create_index(op.f('ix_training_files_amo_id'), 'training_files', ['amo_id'], unique=False)
    op.create_index(op.f('ix_training_files_course_id'), 'training_files', ['course_id'], unique=False)
    op.create_index(op.f('ix_training_files_deferral_request_id'), 'training_files', ['deferral_request_id'], unique=False)
    op.create_index(op.f('ix_training_files_event_id'), 'training_files', ['event_id'], unique=False)
    op.create_index(op.f('ix_training_files_kind'), 'training_files', ['kind'], unique=False)
    op.create_index(op.f('ix_training_files_owner_user_id'), 'training_files', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_training_files_record_id'), 'training_files', ['record_id'], unique=False)
    op.create_index(op.f('ix_training_files_review_status'), 'training_files', ['review_status'], unique=False)
    op.create_index(op.f('ix_training_files_reviewed_by_user_id'), 'training_files', ['reviewed_by_user_id'], unique=False)
    op.create_index(op.f('ix_training_files_sha256'), 'training_files', ['sha256'], unique=False)
    op.create_index(op.f('ix_training_files_uploaded_by_user_id'), 'training_files', ['uploaded_by_user_id'], unique=False)
    op.drop_index(op.f('ix_work_order_tasks_id'), table_name='work_order_tasks')
    op.drop_table('work_order_tasks')
    op.add_column('aircraft', sa.Column('aircraft_model_code', sa.String(length=32), nullable=True))
    op.add_column('aircraft', sa.Column('operator_code', sa.String(length=5), nullable=True))
    op.add_column('aircraft', sa.Column('supplier_code', sa.String(length=5), nullable=True))
    op.add_column('aircraft', sa.Column('company_name', sa.String(length=255), nullable=True))
    op.add_column('aircraft', sa.Column('internal_aircraft_identifier', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_aircraft_aircraft_model_code'), 'aircraft', ['aircraft_model_code'], unique=False)
    op.create_index(op.f('ix_aircraft_operator_code'), 'aircraft', ['operator_code'], unique=False)
    op.add_column('aircraft_components', sa.Column('tbo_hours', sa.Float(), nullable=True))
    op.add_column('aircraft_components', sa.Column('tbo_cycles', sa.Float(), nullable=True))
    op.add_column('aircraft_components', sa.Column('tbo_calendar_months', sa.Integer(), nullable=True))
    op.add_column('aircraft_components', sa.Column('hsi_hours', sa.Float(), nullable=True))
    op.add_column('aircraft_components', sa.Column('hsi_cycles', sa.Float(), nullable=True))
    op.add_column('aircraft_components', sa.Column('hsi_calendar_months', sa.Integer(), nullable=True))
    op.add_column('aircraft_components', sa.Column('last_overhaul_date', sa.Date(), nullable=True))
    op.add_column('aircraft_components', sa.Column('last_overhaul_hours', sa.Float(), nullable=True))
    op.add_column('aircraft_components', sa.Column('last_overhaul_cycles', sa.Float(), nullable=True))
    op.add_column('aircraft_components', sa.Column('manufacturer_code', sa.String(length=32), nullable=True))
    op.add_column('aircraft_components', sa.Column('operator_code', sa.String(length=32), nullable=True))
    op.add_column('aircraft_components', sa.Column('unit_of_measure_hours', sa.String(length=8), server_default='', nullable=False))
    op.add_column('aircraft_components', sa.Column('unit_of_measure_cycles', sa.String(length=8), server_default='', nullable=False))
    op.add_column('work_orders', sa.Column('originating_org', sa.String(length=64), nullable=True))
    op.add_column('work_orders', sa.Column('work_package_ref', sa.String(length=64), nullable=True))
    op.add_column('work_orders', sa.Column('wo_type', postgresql.ENUM('LINE', 'BASE', 'PERIODIC', 'UNSCHEDULED', 'MODIFICATION', 'DEFECT', 'OTHER', name='work_order_type', create_type=False), server_default='OTHER', nullable=False))
    # --- AUTO-FIX: safe server_default for NOT NULL add_column ---
    op.alter_column('work_orders', 'wo_type', server_default=None)

    op.add_column('work_orders', sa.Column('closed_date', sa.Date(), nullable=True))
    op.add_column('work_orders', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    # --- AUTO-FIX: safe server_default for NOT NULL add_column ---
    op.alter_column('work_orders', 'created_at', server_default=None)

    op.add_column('work_orders', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    # --- AUTO-FIX: safe server_default for NOT NULL add_column ---
    op.alter_column('work_orders', 'updated_at', server_default=None)

    op.add_column('work_orders', sa.Column('created_by_user_id', sa.String(length=36), nullable=True))
    op.add_column('work_orders', sa.Column('updated_by_user_id', sa.String(length=36), nullable=True))
    op.alter_column('work_orders', 'wo_number',
               existing_type=sa.VARCHAR(length=10),
               type_=sa.String(length=32),
               existing_nullable=False)
    op.alter_column('work_orders', 'check_type',
               existing_type=sa.VARCHAR(length=20),
               type_=sa.String(length=32),
               existing_nullable=True)
    op.alter_column('work_orders', 'status',
               existing_type=sa.VARCHAR(length=20),
               type_=postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'CLOSED', 'CANCELLED', name='work_order_status', create_type=False),
               existing_nullable=False)
    op.drop_constraint(op.f('work_orders_wo_number_key'), 'work_orders', type_='unique')
    op.create_index(op.f('ix_work_orders_aircraft_serial_number'), 'work_orders', ['aircraft_serial_number'], unique=False)
    op.create_index(op.f('ix_work_orders_wo_number'), 'work_orders', ['wo_number'], unique=True)
    op.create_foreign_key(None, 'work_orders', 'users', ['created_by_user_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'work_orders', 'users', ['updated_by_user_id'], ['id'], ondelete='SET NULL')
    # ### end Alembic commands ###

    # AUTO-FIX: drop temporary defaults for NOT NULL add_column
    op.alter_column('aircraft_components', 'unit_of_measure_cycles', server_default=None)
    op.alter_column('aircraft_components', 'unit_of_measure_hours', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'work_orders', type_='foreignkey')
    op.drop_constraint(None, 'work_orders', type_='foreignkey')
    op.drop_index(op.f('ix_work_orders_wo_number'), table_name='work_orders')
    op.drop_index(op.f('ix_work_orders_aircraft_serial_number'), table_name='work_orders')
    op.create_unique_constraint(op.f('work_orders_wo_number_key'), 'work_orders', ['wo_number'], postgresql_nulls_not_distinct=False)
    op.alter_column('work_orders', 'status',
               existing_type=postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'CLOSED', 'CANCELLED', name='work_order_status', create_type=False),
               type_=sa.VARCHAR(length=20),
               existing_nullable=False)
    op.alter_column('work_orders', 'check_type',
               existing_type=sa.String(length=32),
               type_=sa.VARCHAR(length=20),
               existing_nullable=True)
    op.alter_column('work_orders', 'wo_number',
               existing_type=sa.String(length=32),
               type_=sa.VARCHAR(length=10),
               existing_nullable=False)
    op.drop_column('work_orders', 'updated_by_user_id')
    op.drop_column('work_orders', 'created_by_user_id')
    op.drop_column('work_orders', 'updated_at')
    op.drop_column('work_orders', 'created_at')
    op.drop_column('work_orders', 'closed_date')
    op.drop_column('work_orders', 'wo_type')
    op.drop_column('work_orders', 'work_package_ref')
    op.drop_column('work_orders', 'originating_org')
    op.drop_column('aircraft_components', 'unit_of_measure_cycles')
    op.drop_column('aircraft_components', 'unit_of_measure_hours')
    op.drop_column('aircraft_components', 'operator_code')
    op.drop_column('aircraft_components', 'manufacturer_code')
    op.drop_column('aircraft_components', 'last_overhaul_cycles')
    op.drop_column('aircraft_components', 'last_overhaul_hours')
    op.drop_column('aircraft_components', 'last_overhaul_date')
    op.drop_column('aircraft_components', 'hsi_calendar_months')
    op.drop_column('aircraft_components', 'hsi_cycles')
    op.drop_column('aircraft_components', 'hsi_hours')
    op.drop_column('aircraft_components', 'tbo_calendar_months')
    op.drop_column('aircraft_components', 'tbo_cycles')
    op.drop_column('aircraft_components', 'tbo_hours')
    op.drop_index(op.f('ix_aircraft_operator_code'), table_name='aircraft')
    op.drop_index(op.f('ix_aircraft_aircraft_model_code'), table_name='aircraft')
    op.drop_column('aircraft', 'internal_aircraft_identifier')
    op.drop_column('aircraft', 'company_name')
    op.drop_column('aircraft', 'supplier_code')
    op.drop_column('aircraft', 'operator_code')
    op.drop_column('aircraft', 'aircraft_model_code')
    op.create_table('work_order_tasks',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('work_order_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('task_code', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('is_non_routine', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('status', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], name=op.f('work_order_tasks_work_order_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('work_order_tasks_pkey'))
    )
    op.create_index(op.f('ix_work_order_tasks_id'), 'work_order_tasks', ['id'], unique=False)
    op.drop_index(op.f('ix_training_files_uploaded_by_user_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_sha256'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_reviewed_by_user_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_review_status'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_record_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_owner_user_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_kind'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_event_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_deferral_request_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_course_id'), table_name='training_files')
    op.drop_index(op.f('ix_training_files_amo_id'), table_name='training_files')
    op.drop_index('idx_training_files_record', table_name='training_files')
    op.drop_index('idx_training_files_event', table_name='training_files')
    op.drop_index('idx_training_files_deferral', table_name='training_files')
    op.drop_index('idx_training_files_course', table_name='training_files')
    op.drop_index('idx_training_files_amo_owner', table_name='training_files')
    op.drop_table('training_files')
    op.drop_index(op.f('ix_work_log_entries_user_id'), table_name='work_log_entries')
    op.drop_index(op.f('ix_work_log_entries_task_id'), table_name='work_log_entries')
    op.drop_index(op.f('ix_work_log_entries_id'), table_name='work_log_entries')
    op.drop_table('work_log_entries')
    op.drop_index(op.f('ix_training_records_verified_by_user_id'), table_name='training_records')
    op.drop_index(op.f('ix_training_records_verification_status'), table_name='training_records')
    op.drop_index(op.f('ix_training_records_user_id'), table_name='training_records')
    op.drop_index(op.f('ix_training_records_event_id'), table_name='training_records')
    op.drop_index(op.f('ix_training_records_course_id'), table_name='training_records')
    op.drop_index(op.f('ix_training_records_amo_id'), table_name='training_records')
    op.drop_index('idx_training_records_validity', table_name='training_records')
    op.drop_index('idx_training_records_user_course', table_name='training_records')
    op.drop_index('idx_training_records_amo_user', table_name='training_records')
    op.drop_table('training_records')
    op.drop_index(op.f('ix_training_event_participants_user_id'), table_name='training_event_participants')
    op.drop_index(op.f('ix_training_event_participants_status'), table_name='training_event_participants')
    op.drop_index(op.f('ix_training_event_participants_event_id'), table_name='training_event_participants')
    op.drop_index(op.f('ix_training_event_participants_deferral_request_id'), table_name='training_event_participants')
    op.drop_index(op.f('ix_training_event_participants_attendance_marked_by_user_id'), table_name='training_event_participants')
    op.drop_index(op.f('ix_training_event_participants_amo_id'), table_name='training_event_participants')
    op.drop_index('idx_training_participants_user', table_name='training_event_participants')
    op.drop_index('idx_training_participants_event', table_name='training_event_participants')
    op.drop_index('idx_training_participants_amo_user', table_name='training_event_participants')
    op.drop_table('training_event_participants')
    op.drop_index(op.f('ix_task_assignments_user_id'), table_name='task_assignments')
    op.drop_index(op.f('ix_task_assignments_task_id'), table_name='task_assignments')
    op.drop_index(op.f('ix_task_assignments_id'), table_name='task_assignments')
    op.drop_table('task_assignments')
    op.drop_index(op.f('ix_training_requirements_user_id'), table_name='training_requirements')
    op.drop_index(op.f('ix_training_requirements_scope'), table_name='training_requirements')
    op.drop_index(op.f('ix_training_requirements_job_role'), table_name='training_requirements')
    op.drop_index(op.f('ix_training_requirements_is_active'), table_name='training_requirements')
    op.drop_index(op.f('ix_training_requirements_department_code'), table_name='training_requirements')
    op.drop_index(op.f('ix_training_requirements_course_id'), table_name='training_requirements')
    op.drop_index(op.f('ix_training_requirements_amo_id'), table_name='training_requirements')
    op.drop_index('idx_training_requirements_user', table_name='training_requirements')
    op.drop_index('idx_training_requirements_role', table_name='training_requirements')
    op.drop_index('idx_training_requirements_dept', table_name='training_requirements')
    op.drop_index('idx_training_requirements_amo_scope', table_name='training_requirements')
    op.drop_index('idx_training_requirements_amo_active', table_name='training_requirements')
    op.drop_table('training_requirements')
    op.drop_index(op.f('ix_training_events_status'), table_name='training_events')
    op.drop_index(op.f('ix_training_events_course_id'), table_name='training_events')
    op.drop_index(op.f('ix_training_events_amo_id'), table_name='training_events')
    op.drop_index('idx_training_events_amo_status', table_name='training_events')
    op.drop_index('idx_training_events_amo_course_date', table_name='training_events')
    op.drop_table('training_events')
    op.drop_index(op.f('ix_training_deferral_requests_user_id'), table_name='training_deferral_requests')
    op.drop_index(op.f('ix_training_deferral_requests_status'), table_name='training_deferral_requests')
    op.drop_index(op.f('ix_training_deferral_requests_requested_by_user_id'), table_name='training_deferral_requests')
    op.drop_index(op.f('ix_training_deferral_requests_decided_by_user_id'), table_name='training_deferral_requests')
    op.drop_index(op.f('ix_training_deferral_requests_course_id'), table_name='training_deferral_requests')
    op.drop_index(op.f('ix_training_deferral_requests_amo_id'), table_name='training_deferral_requests')
    op.drop_index('idx_training_deferrals_user_course_status', table_name='training_deferral_requests')
    op.drop_index('idx_training_deferrals_amo_status', table_name='training_deferral_requests')
    op.drop_table('training_deferral_requests')
    op.drop_index(op.f('ix_task_cards_work_order_id'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_task_code'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_program_item_id'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_parent_task_id'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_id'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_ata_chapter'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_aircraft_serial_number'), table_name='task_cards')
    op.drop_index(op.f('ix_task_cards_aircraft_component_id'), table_name='task_cards')
    op.drop_table('task_cards')
    op.drop_index(op.f('ix_training_notifications_user_id'), table_name='training_notifications')
    op.drop_index(op.f('ix_training_notifications_severity'), table_name='training_notifications')
    op.drop_index(op.f('ix_training_notifications_amo_id'), table_name='training_notifications')
    op.drop_index('idx_training_notifications_amo_user_unread', table_name='training_notifications')
    op.drop_index('idx_training_notifications_amo_user_created', table_name='training_notifications')
    op.drop_table('training_notifications')
    op.drop_index(op.f('ix_training_courses_kind'), table_name='training_courses')
    op.drop_index(op.f('ix_training_courses_is_active'), table_name='training_courses')
    op.drop_index(op.f('ix_training_courses_category'), table_name='training_courses')
    op.drop_index(op.f('ix_training_courses_amo_id'), table_name='training_courses')
    op.drop_index('idx_training_courses_amo_category', table_name='training_courses')
    op.drop_index('idx_training_courses_amo_active', table_name='training_courses')
    op.drop_table('training_courses')
    op.drop_index(op.f('ix_training_audit_logs_entity_type'), table_name='training_audit_logs')
    op.drop_index(op.f('ix_training_audit_logs_entity_id'), table_name='training_audit_logs')
    op.drop_index(op.f('ix_training_audit_logs_amo_id'), table_name='training_audit_logs')
    op.drop_index(op.f('ix_training_audit_logs_actor_user_id'), table_name='training_audit_logs')
    op.drop_index(op.f('ix_training_audit_logs_action'), table_name='training_audit_logs')
    op.drop_index('idx_training_audit_entity', table_name='training_audit_logs')
    op.drop_index('idx_training_audit_amo_created', table_name='training_audit_logs')
    op.drop_index('idx_training_audit_actor', table_name='training_audit_logs')
    op.drop_table('training_audit_logs')
    op.drop_index(op.f('ix_aircraft_usage_id'), table_name='aircraft_usage')
    op.drop_index(op.f('ix_aircraft_usage_date'), table_name='aircraft_usage')
    op.drop_index(op.f('ix_aircraft_usage_aircraft_serial_number'), table_name='aircraft_usage')
    op.drop_table('aircraft_usage')
    op.drop_index(op.f('ix_aircraft_program_items_program_item_id'), table_name='aircraft_program_items')
    op.drop_index(op.f('ix_aircraft_program_items_id'), table_name='aircraft_program_items')
    op.drop_index(op.f('ix_aircraft_program_items_aircraft_serial_number'), table_name='aircraft_program_items')
    op.drop_index(op.f('ix_aircraft_program_items_aircraft_component_id'), table_name='aircraft_program_items')
    op.drop_table('aircraft_program_items')
    op.drop_index(op.f('ix_maintenance_statuses_program_item_id'), table_name='maintenance_statuses')
    op.drop_index(op.f('ix_maintenance_statuses_id'), table_name='maintenance_statuses')
    op.drop_index(op.f('ix_maintenance_statuses_aircraft_serial_number'), table_name='maintenance_statuses')
    op.drop_table('maintenance_statuses')
    op.drop_index(op.f('ix_maintenance_program_items_template_code'), table_name='maintenance_program_items')
    op.drop_index(op.f('ix_maintenance_program_items_task_number'), table_name='maintenance_program_items')
    op.drop_index(op.f('ix_maintenance_program_items_task_code'), table_name='maintenance_program_items')
    op.drop_index(op.f('ix_maintenance_program_items_id'), table_name='maintenance_program_items')
    op.drop_index(op.f('ix_maintenance_program_items_ata_chapter'), table_name='maintenance_program_items')
    op.drop_index(op.f('ix_maintenance_program_items_aircraft_template'), table_name='maintenance_program_items')
    op.drop_table('maintenance_program_items')
    # ### end Alembic commands ###

    # AUTO-FIX: enum drop (best-effort on downgrade)
    bind = op.get_bind()
    postgresql.ENUM('AIRFRAME', 'ENGINE', 'PROP', 'AD', 'SB', 'HT', 'OTHER', name='maintenance_program_category', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('ACTIVE', 'SUSPENDED', 'DELETED', name='program_item_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'DUE_SOON', 'OVERDUE', 'COMPLETED', 'SUSPENDED', name='aircraft_program_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('HF', 'FTS', 'EWIS', 'SMS', 'TYPE', 'INTERNAL_TECHNICAL', 'QUALITY_SYSTEMS', 'REGULATORY', 'OTHER', name='training_course_category_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('INITIAL', 'CONTINUATION', 'RECURRENT', 'REFRESHER', 'OTHER', name='training_kind_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('CLASSROOM', 'ONLINE', 'OJT', 'MIXED', 'OTHER', name='training_delivery_method_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('INFO', 'ACTION_REQUIRED', 'WARNING', name='training_notification_severity_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'UNSCHEDULED', 'DEFECT', 'MODIFICATION', name='task_category', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'NON_ROUTINE', name='task_origin_type', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', name='task_priority', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'PAUSED', 'COMPLETED', 'DEFERRED', 'CANCELLED', name='task_status', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('INDEPENDENT_INSPECTION', 'FUNCTIONAL_TEST', 'OPERATIONAL_CHECK', 'DUPLICATE_INSPECTION', 'OTHER', name='task_error_capturing_method', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('ILLNESS', 'OPERATIONAL_REQUIREMENTS', 'PERSONAL_EMERGENCY', 'PROVIDER_CANCELLATION', 'SYSTEM_FAILURE', 'OTHER', name='training_deferral_reason_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='training_deferral_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='training_event_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('ALL', 'DEPARTMENT', 'JOB_ROLE', 'USER', name='training_requirement_scope_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('LEAD', 'SUPPORT', 'INSPECTOR', name='task_assignment_role', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('ASSIGNED', 'ACCEPTED', 'REJECTED', 'COMPLETED', name='task_assignment_status', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('SCHEDULED', 'INVITED', 'CONFIRMED', 'ATTENDED', 'NO_SHOW', 'CANCELLED', 'DEFERRED', name='training_participant_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'VERIFIED', 'REJECTED', name='training_record_verification_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('CERTIFICATE', 'AMEL', 'LICENSE', 'EVIDENCE', 'OTHER', name='training_file_kind_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', name='training_file_review_status_enum', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('LINE', 'BASE', 'PERIODIC', 'UNSCHEDULED', 'MODIFICATION', 'DEFECT', 'OTHER', name='work_order_type', create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'CLOSED', 'CANCELLED', name='work_order_status', create_type=False).drop(bind, checkfirst=True)
