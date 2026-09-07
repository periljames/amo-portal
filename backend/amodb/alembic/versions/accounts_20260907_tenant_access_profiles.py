"""Tenant access profiles and governed position links.

Revision ID: accounts_260907_access_profiles
Revises: backend_260906_certified
Create Date: 2026-09-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "accounts_260907_access_profiles"
down_revision = "backend_260906_certified"
branch_labels = None
depends_on = None


_ACCOUNT_ROLE_VALUES = (
    "DOCUMENT_CONTROL_OFFICER",
    "QUALITY_SUPPORT_OFFICER",
    "SAFETY_OFFICER",
    "MAINTENANCE_SUPERVISOR",
    "TECHNICAL_RECORDS_SUPERVISOR",
    "TECHNICAL_RECORDS_OFFICER",
    "MAINTENANCE_SUPPORT",
    "HUMAN_RESOURCES_MANAGER",
    "HUMAN_RESOURCES_OFFICER",
)


def upgrade() -> None:
    for value in _ACCOUNT_ROLE_VALUES:
        op.execute(sa.text(f"ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS '{value}'"))

    # Normalize legacy platform identities. Superuser authority is ROOT-scoped;
    # it must not also be represented as a tenant-administrator appointment.
    op.execute(sa.text(
        "UPDATE users SET is_amo_admin = false "
        "WHERE is_superuser = true OR role = 'SUPERUSER'"
    ))

    # Capture the regulated capacity used for every administrator-grant
    # decision. Two identities in the same role must never satisfy the
    # independent AE + Quality Manager approval rule.
    op.add_column(
        "admin_access_grant_approvals",
        sa.Column("approver_role", sa.String(length=64), nullable=True),
    )
    op.execute(sa.text(
        "UPDATE admin_access_grant_approvals a "
        "SET approver_role = CAST(u.role AS VARCHAR) "
        "FROM users u WHERE u.id = a.approver_user_id"
    ))

    op.alter_column(
        "auth_role_definitions",
        "code",
        existing_type=sa.String(length=80),
        type_=sa.String(length=160),
        existing_nullable=False,
    )
    op.add_column("auth_role_definitions", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.add_column("auth_role_definitions", sa.Column("tenant_code", sa.String(length=64), nullable=True))
    op.add_column("auth_role_definitions", sa.Column("display_name", sa.String(length=160), nullable=True))
    op.add_column("auth_role_definitions", sa.Column("base_role_key", sa.String(length=64), nullable=True))
    op.add_column("auth_role_definitions", sa.Column("category", sa.String(length=64), nullable=True))
    op.add_column("auth_role_definitions", sa.Column("reports_to_role_code", sa.String(length=64), nullable=True))
    op.add_column("auth_role_definitions", sa.Column("is_regulated", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("auth_role_definitions", sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("auth_role_definitions", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("auth_role_definitions", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("auth_role_definitions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("auth_role_definitions", sa.Column("updated_by_user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_auth_role_definition_amo",
        "auth_role_definitions",
        "amos",
        ["amo_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_auth_role_definition_updated_by",
        "auth_role_definitions",
        "users",
        ["updated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_auth_role_definition_amo", "auth_role_definitions", ["amo_id"])
    op.create_index(
        "ix_auth_role_tenant_active",
        "auth_role_definitions",
        ["amo_id", "is_active", "display_name"],
    )
    op.create_index(
        "uq_auth_role_tenant_code",
        "auth_role_definitions",
        ["amo_id", "tenant_code"],
        unique=True,
        postgresql_where=sa.text("amo_id IS NOT NULL"),
    )
    op.execute(sa.text(
        "UPDATE auth_role_definitions "
        "SET tenant_code = COALESCE(tenant_code, code), "
        "display_name = COALESCE(display_name, replace(initcap(replace(code, '_', ' ')), '  ', ' ')), "
        "category = COALESCE(category, 'SYSTEM')"
    ))

    op.add_column(
        "auth_user_role_assignments",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_auth_user_role_primary",
        "auth_user_role_assignments",
        ["amo_id", "user_id", "is_primary"],
    )
    op.create_index(
        "uq_auth_user_primary_profile",
        "auth_user_role_assignments",
        ["amo_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true AND valid_to IS NULL"),
    )

    op.add_column("workforce_positions", sa.Column("access_profile_id", sa.String(length=36), nullable=True))
    op.add_column("workforce_positions", sa.Column("reports_to_position_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_workforce_position_access_profile",
        "workforce_positions",
        "auth_role_definitions",
        ["access_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_workforce_position_reports_to",
        "workforce_positions",
        "workforce_positions",
        ["reports_to_position_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_workforce_position_access_profile", "workforce_positions", ["access_profile_id"])
    op.create_index("ix_workforce_position_reports_to", "workforce_positions", ["reports_to_position_id"])

    # Training applicability must survive tenant terminology changes. Keep the
    # human-readable role label as a historical snapshot, but target the stable
    # tenant access-profile identity for every new JOB_ROLE requirement.
    op.add_column(
        "training_requirements",
        sa.Column("access_profile_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_training_requirement_access_profile",
        "training_requirements",
        "auth_role_definitions",
        ["access_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_training_requirements_access_profile",
        "training_requirements",
        ["amo_id", "access_profile_id"],
    )
    op.create_index(
        "uq_training_requirements_profile_identity",
        "training_requirements",
        ["amo_id", "course_id", "scope", "access_profile_id"],
        unique=True,
        postgresql_where=sa.text("access_profile_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_training_requirements_profile_identity", table_name="training_requirements")
    op.drop_index("ix_training_requirements_access_profile", table_name="training_requirements")
    op.drop_constraint("fk_training_requirement_access_profile", "training_requirements", type_="foreignkey")
    op.drop_column("training_requirements", "access_profile_id")

    op.drop_index("ix_workforce_position_reports_to", table_name="workforce_positions")
    op.drop_index("ix_workforce_position_access_profile", table_name="workforce_positions")
    op.drop_constraint("fk_workforce_position_reports_to", "workforce_positions", type_="foreignkey")
    op.drop_constraint("fk_workforce_position_access_profile", "workforce_positions", type_="foreignkey")
    op.drop_column("workforce_positions", "reports_to_position_id")
    op.drop_column("workforce_positions", "access_profile_id")

    op.drop_index("uq_auth_user_primary_profile", table_name="auth_user_role_assignments")
    op.drop_index("ix_auth_user_role_primary", table_name="auth_user_role_assignments")
    op.drop_column("auth_user_role_assignments", "is_primary")

    op.drop_index("uq_auth_role_tenant_code", table_name="auth_role_definitions")
    op.drop_index("ix_auth_role_tenant_active", table_name="auth_role_definitions")
    op.drop_index("ix_auth_role_definition_amo", table_name="auth_role_definitions")
    op.drop_constraint("fk_auth_role_definition_updated_by", "auth_role_definitions", type_="foreignkey")
    op.drop_constraint("fk_auth_role_definition_amo", "auth_role_definitions", type_="foreignkey")
    for column in (
        "updated_by_user_id", "updated_at", "version", "is_active", "is_editable",
        "is_regulated", "reports_to_role_code", "category", "base_role_key",
        "display_name", "tenant_code", "amo_id",
    ):
        op.drop_column("auth_role_definitions", column)
    op.alter_column(
        "auth_role_definitions",
        "code",
        existing_type=sa.String(length=160),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
    op.drop_column("admin_access_grant_approvals", "approver_role")
    # PostgreSQL enum values are intentionally retained on downgrade. Removing
    # them is unsafe while any historical rows or audit payloads may reference
    # the value.
