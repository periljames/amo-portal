"""Restore regulatory mapping tables used by the Document Control workspace.

Revision ID: docctl_20260808_regmap
Revises: docgov_rel_20260807_merge
Create Date: 2026-08-08

The ORM and Document Control regulation-links endpoint have long treated these
three tables as authoritative, but the migration graph did not create them on a
clean database.  This migration is intentionally idempotent so environments
that were repaired manually are not broken when they receive the canonical
schema migration.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "docctl_20260808_regmap"
down_revision = "docgov_rel_20260807_merge"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    return {
        str(index.get("name"))
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _ensure_index(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=False)


def upgrade() -> None:
    tables = _table_names()

    if "regulation_catalog" not in tables:
        op.create_table(
            "regulation_catalog",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=True),
            sa.Column("authority", sa.String(length=64), nullable=False),
            sa.Column("instrument_name", sa.String(length=255), nullable=False),
            sa.Column("instrument_version", sa.String(length=64), nullable=False),
            sa.Column("citation_text", sa.Text(), nullable=False),
            sa.Column("url_reference", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["manual_tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        tables.add("regulation_catalog")
    _ensure_index("ix_regulation_catalog_tenant_id", "regulation_catalog", ["tenant_id"])

    if "regulation_requirements" not in tables:
        op.create_table(
            "regulation_requirements",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("catalog_id", sa.String(length=36), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("requirement_text", sa.Text(), nullable=False),
            sa.Column("applicability_tags", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["catalog_id"], ["regulation_catalog.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        tables.add("regulation_requirements")
    _ensure_index("ix_regulation_requirements_catalog_id", "regulation_requirements", ["catalog_id"])

    if "manual_requirement_links" not in tables:
        op.create_table(
            "manual_requirement_links",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("revision_id", sa.String(length=36), nullable=False),
            sa.Column("section_id", sa.String(length=36), nullable=True),
            sa.Column("block_id", sa.String(length=36), nullable=True),
            sa.Column("requirement_id", sa.String(length=36), nullable=False),
            sa.Column("compliance_note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["section_id"], ["manual_sections.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["block_id"], ["manual_blocks.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["requirement_id"], ["regulation_requirements.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        tables.add("manual_requirement_links")
    _ensure_index("ix_manual_requirement_links_revision_id", "manual_requirement_links", ["revision_id"])


def downgrade() -> None:
    # Regulatory mapping is controlled evidence.  Do not destructively remove
    # tables that may pre-date this repair in installations where the missing
    # migration was previously remediated manually.  Downgrading only removes
    # the Alembic revision marker; a subsequent upgrade remains idempotent.
    pass
