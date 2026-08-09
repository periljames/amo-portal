"""make OEM single-current guards transaction-safe

Revision ID: aircraft_arch_20260807_oem_backend_guard
Revises: aircraft_arch_20260807_oem_backend
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "aircraft_arch_20260807_oem_backend_guard"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260807_oem_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The authoritative uniqueness invariants are transaction-deferred so one
    # atomic service operation can supersede the old authority and publish/make
    # current the new authority regardless of ORM UPDATE ordering.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_assert_one_current_oem_revision()
        RETURNS trigger AS $$
        DECLARE target_publication text;
        DECLARE current_count integer;
        BEGIN
            target_publication := CASE
                WHEN TG_OP = 'DELETE' THEN OLD.publication_id
                ELSE NEW.publication_id
            END;
            SELECT count(*) INTO current_count
              FROM aircraft_oem_publication_revisions
             WHERE publication_id = target_publication
               AND status = 'CURRENT';
            IF current_count > 1 THEN
                RAISE EXCEPTION 'OEM publication may have only one CURRENT revision';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER trg_aircraft_oem_one_current_deferred
        AFTER INSERT OR UPDATE OR DELETE ON aircraft_oem_publication_revisions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION aircraft_assert_one_current_oem_revision();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_assert_one_published_content_revision()
        RETURNS trigger AS $$
        DECLARE target_pack text;
        DECLARE published_count integer;
        BEGIN
            target_pack := CASE
                WHEN TG_OP = 'DELETE' THEN OLD.pack_id
                ELSE NEW.pack_id
            END;
            SELECT count(*) INTO published_count
              FROM aircraft_content_pack_revisions
             WHERE pack_id = target_pack
               AND status = 'PUBLISHED';
            IF published_count > 1 THEN
                RAISE EXCEPTION 'content pack may have only one PUBLISHED revision';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER trg_aircraft_content_one_published_deferred
        AFTER INSERT OR UPDATE OR DELETE ON aircraft_content_pack_revisions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION aircraft_assert_one_published_content_revision();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_content_one_published_deferred ON aircraft_content_pack_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_assert_one_published_content_revision()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_one_current_deferred ON aircraft_oem_publication_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_assert_one_current_oem_revision()")
