"""index OEM lineage and source-currentness queries

Revision ID: aircraft_arch_20260807_oem_backend_indexes
Revises: aircraft_arch_20260807_oem_backend_integrity
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "aircraft_arch_20260807_oem_backend_indexes"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260807_oem_backend_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_aircraft_content_pack_source_publication_revision",
        "aircraft_content_pack_sources",
        ["publication_revision_id", "revision_id"],
    )
    op.create_index(
        "ix_aircraft_content_pack_source_temporary_revision",
        "aircraft_content_pack_sources",
        ["temporary_revision_id", "revision_id"],
    )
    op.create_index(
        "ix_aircraft_oem_publication_revision_supersedes",
        "aircraft_oem_publication_revisions",
        ["supersedes_revision_id"],
    )
    op.create_index(
        "ix_aircraft_oem_source_watch_due",
        "aircraft_oem_source_watches",
        ["is_active", "last_checked_at", "publication_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_aircraft_oem_source_watch_due",
        table_name="aircraft_oem_source_watches",
    )
    op.drop_index(
        "ix_aircraft_oem_publication_revision_supersedes",
        table_name="aircraft_oem_publication_revisions",
    )
    op.drop_index(
        "ix_aircraft_content_pack_source_temporary_revision",
        table_name="aircraft_content_pack_sources",
    )
    op.drop_index(
        "ix_aircraft_content_pack_source_publication_revision",
        table_name="aircraft_content_pack_sources",
    )
