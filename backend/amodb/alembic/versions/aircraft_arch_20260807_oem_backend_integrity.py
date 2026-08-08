"""enforce OEM backend lifecycle integrity

Revision ID: aircraft_arch_20260807_oem_backend_integrity
Revises: aircraft_arch_20260807_oem_backend_guard
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "aircraft_arch_20260807_oem_backend_integrity"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260807_oem_backend_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_enforce_oem_publication_revision_lifecycle()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status NOT IN ('CANDIDATE','VERIFIED','CURRENT') THEN
                    RAISE EXCEPTION 'new OEM publication revision must enter as CANDIDATE, VERIFIED, or CURRENT';
                END IF;
            ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
                IF NOT (
                    (OLD.status = 'CANDIDATE' AND NEW.status IN ('VERIFIED','REJECTED','WITHDRAWN'))
                    OR (OLD.status = 'VERIFIED' AND NEW.status IN ('CURRENT','REJECTED','WITHDRAWN'))
                    OR (OLD.status = 'CURRENT' AND NEW.status = 'SUPERSEDED')
                    OR (OLD.status = 'SUPERSEDED' AND NEW.status = 'WITHDRAWN')
                ) THEN
                    RAISE EXCEPTION 'illegal OEM publication revision lifecycle transition: % -> %', OLD.status, NEW.status;
                END IF;
            END IF;

            IF NEW.status IN ('VERIFIED','CURRENT')
               AND (NEW.verified_by_user_id IS NULL OR NEW.verified_at IS NULL) THEN
                RAISE EXCEPTION 'verified/current OEM publication revision requires verifier and verification timestamp';
            END IF;
            IF NEW.status = 'CURRENT'
               AND NEW.checksum_sha256 IS NULL THEN
                RAISE EXCEPTION 'current OEM publication revision requires source checksum';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_oem_publication_revision_lifecycle
        BEFORE INSERT OR UPDATE ON aircraft_oem_publication_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_enforce_oem_publication_revision_lifecycle();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_enforce_oem_temporary_revision_lifecycle()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status NOT IN ('CANDIDATE','ACTIVE') THEN
                    RAISE EXCEPTION 'new OEM Temporary Revision must enter as CANDIDATE or ACTIVE';
                END IF;
            ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
                IF NOT (
                    (OLD.status = 'CANDIDATE' AND NEW.status IN ('ACTIVE','REJECTED'))
                    OR (OLD.status = 'ACTIVE' AND NEW.status IN ('INCORPORATED','SUPERSEDED','WITHDRAWN','REPLACED'))
                ) THEN
                    RAISE EXCEPTION 'illegal OEM Temporary Revision lifecycle transition: % -> %', OLD.status, NEW.status;
                END IF;
            END IF;

            IF NEW.status = 'ACTIVE'
               AND (NEW.verified_by_user_id IS NULL OR NEW.verified_at IS NULL) THEN
                RAISE EXCEPTION 'active OEM Temporary Revision requires verifier and verification timestamp';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_oem_temporary_revision_lifecycle
        BEFORE INSERT OR UPDATE ON aircraft_oem_temporary_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_enforce_oem_temporary_revision_lifecycle();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_enforce_content_pack_revision_lifecycle()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status IS DISTINCT FROM 'DRAFT' THEN
                    RAISE EXCEPTION 'new content-pack revision must enter as DRAFT';
                END IF;
            ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
                IF NOT (
                    (OLD.status = 'DRAFT' AND NEW.status IN ('PUBLISHED','WITHDRAWN'))
                    OR (OLD.status = 'PUBLISHED' AND NEW.status IN ('SUPERSEDED','WITHDRAWN'))
                    OR (OLD.status = 'SUPERSEDED' AND NEW.status = 'WITHDRAWN')
                ) THEN
                    RAISE EXCEPTION 'illegal content-pack revision lifecycle transition: % -> %', OLD.status, NEW.status;
                END IF;
            END IF;

            IF NEW.status = 'PUBLISHED'
               AND (NEW.published_by_user_id IS NULL OR NEW.published_at IS NULL OR NEW.content_hash IS NULL) THEN
                RAISE EXCEPTION 'published content-pack revision requires publisher, publication timestamp, and content hash';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_content_pack_revision_lifecycle
        BEFORE INSERT OR UPDATE ON aircraft_content_pack_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_enforce_content_pack_revision_lifecycle();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_enforce_oem_source_intake_lifecycle()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status IS DISTINCT FROM 'STAGED' THEN
                    RAISE EXCEPTION 'new OEM source intake must enter as STAGED';
                END IF;
            ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
                IF NOT (
                    (OLD.status = 'STAGED' AND NEW.status IN ('VALIDATED','REJECTED','FAILED'))
                    OR (OLD.status = 'VALIDATED' AND NEW.status IN ('STAGED','APPROVED','REJECTED','FAILED'))
                    OR (OLD.status = 'APPROVED' AND NEW.status IN ('MATERIALIZED','REJECTED'))
                ) THEN
                    RAISE EXCEPTION 'illegal OEM source intake lifecycle transition: % -> %', OLD.status, NEW.status;
                END IF;
            END IF;

            IF NEW.status IN ('VALIDATED','APPROVED','MATERIALIZED')
               AND NEW.normalization_hash IS NULL THEN
                RAISE EXCEPTION 'validated/approved/materialized OEM source intake requires normalization hash';
            END IF;
            IF NEW.status IN ('APPROVED','MATERIALIZED')
               AND (NEW.approved_by_user_id IS NULL OR NEW.approved_at IS NULL) THEN
                RAISE EXCEPTION 'approved/materialized OEM source intake requires approval authority and timestamp';
            END IF;
            IF NEW.status = 'MATERIALIZED'
               AND (NEW.materialized_revision_id IS NULL OR NEW.materialized_at IS NULL) THEN
                RAISE EXCEPTION 'materialized OEM source intake requires materialized revision and timestamp';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_oem_source_intake_lifecycle
        BEFORE INSERT OR UPDATE ON aircraft_oem_source_intakes
        FOR EACH ROW EXECUTE FUNCTION aircraft_enforce_oem_source_intake_lifecycle();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_source_intake_lifecycle ON aircraft_oem_source_intakes"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_enforce_oem_source_intake_lifecycle()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_content_pack_revision_lifecycle ON aircraft_content_pack_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_enforce_content_pack_revision_lifecycle()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_temporary_revision_lifecycle ON aircraft_oem_temporary_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_enforce_oem_temporary_revision_lifecycle()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_publication_revision_lifecycle ON aircraft_oem_publication_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_enforce_oem_publication_revision_lifecycle()")
