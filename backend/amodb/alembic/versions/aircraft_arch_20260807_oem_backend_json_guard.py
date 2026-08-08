"""fix OEM intake JSON immutability comparison

Revision ID: aircraft_arch_20260807_oem_backend_json
Revises: aircraft_arch_20260807_oem_backend_indexes
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "aircraft_arch_20260807_oem_backend_json"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260807_oem_backend_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL json (unlike jsonb) has no equality operator, so IS DISTINCT
    # FROM on JSON raises UndefinedFunction at runtime. Compare canonical jsonb
    # casts while preserving the existing JSON column contract.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_source_intake()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('APPROVED','MATERIALIZED') THEN
                    RAISE EXCEPTION 'approved/materialized OEM source intake cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.status IN ('APPROVED','MATERIALIZED') THEN
                IF NEW.publication_id IS DISTINCT FROM OLD.publication_id
                   OR NEW.publication_revision_id IS DISTINCT FROM OLD.publication_revision_id
                   OR NEW.temporary_revision_id IS DISTINCT FROM OLD.temporary_revision_id
                   OR NEW.pack_id IS DISTINCT FROM OLD.pack_id
                   OR NEW.source_filename IS DISTINCT FROM OLD.source_filename
                   OR NEW.storage_locator IS DISTINCT FROM OLD.storage_locator
                   OR NEW.checksum_sha256 IS DISTINCT FROM OLD.checksum_sha256
                   OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
                   OR NEW.detected_profile IS DISTINCT FROM OLD.detected_profile
                   OR NEW.profile_confidence IS DISTINCT FROM OLD.profile_confidence
                   OR NEW.workbook_kind IS DISTINCT FROM OLD.workbook_kind
                   OR NEW.source_manifest_json::jsonb IS DISTINCT FROM OLD.source_manifest_json::jsonb
                   OR NEW.normalization_hash IS DISTINCT FROM OLD.normalization_hash
                   OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'approved OEM source intake identity is immutable';
                END IF;
            END IF;
            IF OLD.status = 'MATERIALIZED' AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'materialized OEM source intake is terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    # Downgrade restores the function as introduced by the parent migration.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_source_intake()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('APPROVED','MATERIALIZED') THEN
                    RAISE EXCEPTION 'approved/materialized OEM source intake cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.status IN ('APPROVED','MATERIALIZED') THEN
                IF NEW.publication_id IS DISTINCT FROM OLD.publication_id
                   OR NEW.publication_revision_id IS DISTINCT FROM OLD.publication_revision_id
                   OR NEW.temporary_revision_id IS DISTINCT FROM OLD.temporary_revision_id
                   OR NEW.pack_id IS DISTINCT FROM OLD.pack_id
                   OR NEW.source_filename IS DISTINCT FROM OLD.source_filename
                   OR NEW.storage_locator IS DISTINCT FROM OLD.storage_locator
                   OR NEW.checksum_sha256 IS DISTINCT FROM OLD.checksum_sha256
                   OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
                   OR NEW.detected_profile IS DISTINCT FROM OLD.detected_profile
                   OR NEW.profile_confidence IS DISTINCT FROM OLD.profile_confidence
                   OR NEW.workbook_kind IS DISTINCT FROM OLD.workbook_kind
                   OR NEW.source_manifest_json IS DISTINCT FROM OLD.source_manifest_json
                   OR NEW.normalization_hash IS DISTINCT FROM OLD.normalization_hash
                   OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'approved OEM source intake identity is immutable';
                END IF;
            END IF;
            IF OLD.status = 'MATERIALIZED' AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'materialized OEM source intake is terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
