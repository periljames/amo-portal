"""Add roster rule-set, approval authority and departmental approval governance.

Revision ID: rostering_20260724_governance
Revises: saas_20260722_side_effect_safe
Create Date: 2026-07-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_20260724_governance"
down_revision = "saas_20260722_side_effect_safe"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_names(table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _foreign_key_signatures(
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(str(column) for column in (foreign_key.get("constrained_columns") or ())),
            str(foreign_key.get("referred_table") or ""),
            tuple(str(column) for column in (foreign_key.get("referred_columns") or ())),
        )
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    }


def upgrade() -> None:
    op.create_table(
        "roster_rule_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version_label", sa.String(length=128), nullable=True),
        sa.Column("regulatory_basis", sa.Text(), nullable=True),
        sa.Column("manual_reference", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_roster_rule_set_dates",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_roster_rule_set_amo_code"),
    )
    op.create_index(
        "ix_roster_rule_sets_amo_active",
        "roster_rule_sets",
        ["amo_id", "is_active"],
        unique=False,
    )

    # The historical Workforce precreate migration reads current ORM metadata to
    # repair incomplete installations. On a clean replay it can therefore create
    # this future column before this owning migration runs. Reuse that column and
    # add only the relationship/index that could not exist before roster_rule_sets.
    if "rule_set_id" not in _column_names("roster_rules"):
        op.add_column(
            "roster_rules",
            sa.Column("rule_set_id", sa.String(length=36), nullable=True),
        )

    rule_set_fk = (("rule_set_id",), "roster_rule_sets", ("id",))
    if rule_set_fk not in _foreign_key_signatures("roster_rules"):
        op.create_foreign_key(
            "fk_roster_rules_rule_set",
            "roster_rules",
            "roster_rule_sets",
            ["rule_set_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_roster_rules_rule_set" not in _index_names("roster_rules"):
        op.create_index(
            "ix_roster_rules_rule_set",
            "roster_rules",
            ["rule_set_id"],
            unique=False,
        )

    op.create_table(
        "roster_approval_authorities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("authority_level", sa.String(length=32), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("base_station_id", sa.String(length=36), nullable=True),
        sa.Column("can_approve", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_roster_approval_authority_dates",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "amo_id",
            "user_id",
            "authority_level",
            "department_id",
            "base_station_id",
            name="uq_roster_approval_authority_scope",
        ),
    )
    op.create_index(
        "ix_roster_approval_authority_scope",
        "roster_approval_authorities",
        ["amo_id", "base_station_id", "department_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_roster_approval_authority_user",
        "roster_approval_authorities",
        ["amo_id", "user_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "roster_department_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("base_station_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_approver_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["roster_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_approver_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "department_id",
            "base_station_id",
            name="uq_roster_department_approval_scope",
        ),
    )
    op.create_index(
        "ix_roster_department_approval_version_status",
        "roster_department_approvals",
        ["version_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_roster_department_approval_assignee",
        "roster_department_approvals",
        ["amo_id", "assigned_approver_user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_roster_department_approval_assignee", table_name="roster_department_approvals")
    op.drop_index("ix_roster_department_approval_version_status", table_name="roster_department_approvals")
    op.drop_table("roster_department_approvals")
    op.drop_index("ix_roster_approval_authority_user", table_name="roster_approval_authorities")
    op.drop_index("ix_roster_approval_authority_scope", table_name="roster_approval_authorities")
    op.drop_table("roster_approval_authorities")
    op.drop_index("ix_roster_rules_rule_set", table_name="roster_rules")
    op.drop_constraint("fk_roster_rules_rule_set", "roster_rules", type_="foreignkey")
    op.drop_column("roster_rules", "rule_set_id")
    op.drop_index("ix_roster_rule_sets_amo_active", table_name="roster_rule_sets")
    op.drop_table("roster_rule_sets")
