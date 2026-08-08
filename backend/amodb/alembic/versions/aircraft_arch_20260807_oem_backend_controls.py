"""add governed OEM source intake and immutable backend controls

Revision ID: aircraft_arch_20260807_oem_backend
Revises: aircraft_arch_20260807_oem_mpd
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aircraft_arch_20260807_oem_backend"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260807_oem_mpd"
branch_labels = None
depends_on = None

UUID = sa.String(36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")
EMPTY_LIST = sa.text("'[]'::json")

CONTENT_CHILD_TABLES = (
    "aircraft_content_pack_sources",
    "aircraft_content_pack_positions",
    "aircraft_content_pack_components",
    "aircraft_content_pack_tasks",
    "aircraft_content_pack_resources",
)


def upgrade() -> None:
    # An AMO-submitted Temporary Revision is a candidate until independently
    # verified by the platform authority. Reclassify any pre-existing unverified
    # ACTIVE rows before expanding the lifecycle constraint.
    op.drop_constraint(
        "ck_aircraft_oem_temporary_revision_status",
        "aircraft_oem_temporary_revisions",
        type_="check",
    )
    op.execute(
        """
        UPDATE aircraft_oem_temporary_revisions
           SET status = 'CANDIDATE'
         WHERE status = 'ACTIVE'
           AND verified_at IS NULL
        """
    )
    op.create_check_constraint(
        "ck_aircraft_oem_temporary_revision_status",
        "aircraft_oem_temporary_revisions",
        "status IN ('CANDIDATE','ACTIVE','INCORPORATED','SUPERSEDED','WITHDRAWN','REPLACED','REJECTED')",
    )

    op.create_table(
        "aircraft_oem_source_intakes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "publication_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "publication_revision_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publication_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "temporary_revision_id",
            UUID,
            sa.ForeignKey("aircraft_oem_temporary_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "pack_id",
            UUID,
            sa.ForeignKey("aircraft_content_packs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_amo_id",
            UUID,
            sa.ForeignKey("amos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("storage_locator", sa.Text(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("detected_profile", sa.String(80), nullable=False),
        sa.Column("profile_confidence", sa.String(16), nullable=False),
        sa.Column("workbook_kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="STAGED"),
        sa.Column("source_manifest_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("validation_summary_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("normalization_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "materialized_revision_id",
            UUID,
            sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "publication_id",
            "checksum_sha256",
            name="uq_aircraft_oem_source_intake_publication_checksum",
        ),
        sa.CheckConstraint(
            "status IN ('STAGED','VALIDATED','APPROVED','MATERIALIZED','REJECTED','FAILED')",
            name="ck_aircraft_oem_source_intake_status",
        ),
    )
    op.create_index(
        "ix_aircraft_oem_source_intake_status",
        "aircraft_oem_source_intakes",
        ["publication_id", "status", "created_at"],
    )
    op.create_index(
        "ix_aircraft_oem_source_intake_pack",
        "aircraft_oem_source_intakes",
        ["pack_id", "status", "created_at"],
    )

    op.create_table(
        "aircraft_oem_source_intake_rows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "intake_id",
            UUID,
            sa.ForeignKey("aircraft_oem_source_intakes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sheet_name", sa.String(120), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("row_kind", sa.String(16), nullable=False),
        sa.Column("identity_key", sa.String(180), nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("normalized_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("issues_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("review_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column(
            "reviewed_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "intake_id",
            "sheet_name",
            "row_number",
            name="uq_aircraft_oem_source_intake_row_position",
        ),
        sa.UniqueConstraint(
            "intake_id",
            "row_hash",
            name="uq_aircraft_oem_source_intake_row_hash",
        ),
        sa.CheckConstraint(
            "row_kind IN ('TASK','RESOURCE','UNMAPPED','IGNORED')",
            name="ck_aircraft_oem_source_intake_row_kind",
        ),
        sa.CheckConstraint(
            "status IN ('VALID','REVIEW_REQUIRED','INVALID','IGNORED')",
            name="ck_aircraft_oem_source_intake_row_status",
        ),
    )
    op.create_index(
        "ix_aircraft_oem_source_intake_row_status",
        "aircraft_oem_source_intake_rows",
        ["intake_id", "status", "row_kind"],
    )
    op.create_index(
        "ix_aircraft_oem_source_intake_row_identity",
        "aircraft_oem_source_intake_rows",
        ["intake_id", "identity_key"],
    )

    # U6 already owns published content-pack protections. These additional
    # triggers use unique names and narrow draft writes further without
    # replacing or colliding with the prior controls.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_backend_content_pack_child()
        RETURNS trigger AS $$
        DECLARE revision_status text;
        BEGIN
            SELECT status INTO revision_status
              FROM aircraft_content_pack_revisions
             WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.revision_id ELSE NEW.revision_id END;
            IF revision_status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION 'controlled content may only be changed on a DRAFT revision';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in CONTENT_CHILD_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_oem_backend_controlled
            BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION aircraft_guard_oem_backend_content_pack_child();
            """
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_backend_content_pack_revision()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IS DISTINCT FROM 'DRAFT' THEN
                    RAISE EXCEPTION 'published/superseded content revisions cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            IF NEW.pack_id IS DISTINCT FROM OLD.pack_id
               OR NEW.revision_code IS DISTINCT FROM OLD.revision_code
               OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
               OR NEW.change_summary IS DISTINCT FROM OLD.change_summary
               OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'content revision identity and reviewed hash are immutable';
            END IF;
            IF OLD.status = 'WITHDRAWN' AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'withdrawn content revisions are terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_content_pack_revision_oem_backend_controlled
        BEFORE UPDATE OR DELETE ON aircraft_content_pack_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_oem_backend_content_pack_revision();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_publication_revision()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'OEM publication revisions cannot be deleted';
            END IF;
            IF NEW.publication_id IS DISTINCT FROM OLD.publication_id
               OR NEW.revision_code IS DISTINCT FROM OLD.revision_code
               OR NEW.issue_date IS DISTINCT FROM OLD.issue_date
               OR NEW.effective_date IS DISTINCT FROM OLD.effective_date
               OR NEW.checksum_sha256 IS DISTINCT FROM OLD.checksum_sha256
               OR NEW.source_filename IS DISTINCT FROM OLD.source_filename
               OR NEW.storage_locator IS DISTINCT FROM OLD.storage_locator
               OR NEW.source_url IS DISTINCT FROM OLD.source_url
               OR NEW.change_summary IS DISTINCT FROM OLD.change_summary
               OR NEW.supersedes_revision_id IS DISTINCT FROM OLD.supersedes_revision_id
               OR NEW.submitted_by_user_id IS DISTINCT FROM OLD.submitted_by_user_id
               OR NEW.submitted_by_amo_id IS DISTINCT FROM OLD.submitted_by_amo_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'OEM publication source identity is immutable';
            END IF;
            IF OLD.status IN ('WITHDRAWN','REJECTED')
               AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'closed OEM publication revisions are terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_oem_publication_revision_controlled
        BEFORE UPDATE OR DELETE ON aircraft_oem_publication_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_oem_publication_revision();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_temporary_revision()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'OEM Temporary Revisions cannot be deleted';
            END IF;
            IF NEW.publication_revision_id IS DISTINCT FROM OLD.publication_revision_id
               OR NEW.temporary_revision_code IS DISTINCT FROM OLD.temporary_revision_code
               OR NEW.issue_date IS DISTINCT FROM OLD.issue_date
               OR NEW.effective_date IS DISTINCT FROM OLD.effective_date
               OR NEW.checksum_sha256 IS DISTINCT FROM OLD.checksum_sha256
               OR NEW.source_filename IS DISTINCT FROM OLD.source_filename
               OR NEW.storage_locator IS DISTINCT FROM OLD.storage_locator
               OR NEW.source_url IS DISTINCT FROM OLD.source_url
               OR NEW.replaces_temporary_revision_code IS DISTINCT FROM OLD.replaces_temporary_revision_code
               OR NEW.filing_instructions IS DISTINCT FROM OLD.filing_instructions
               OR NEW.change_summary IS DISTINCT FROM OLD.change_summary
               OR NEW.submitted_by_user_id IS DISTINCT FROM OLD.submitted_by_user_id
               OR NEW.submitted_by_amo_id IS DISTINCT FROM OLD.submitted_by_amo_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'OEM Temporary Revision source identity is immutable';
            END IF;
            IF OLD.status IN ('INCORPORATED','SUPERSEDED','WITHDRAWN','REPLACED','REJECTED')
               AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'closed OEM Temporary Revisions are terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_oem_temporary_revision_controlled
        BEFORE UPDATE OR DELETE ON aircraft_oem_temporary_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_oem_temporary_revision();
        """
    )

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

        CREATE TRIGGER trg_aircraft_oem_source_intake_controlled
        BEFORE UPDATE OR DELETE ON aircraft_oem_source_intakes
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_oem_source_intake();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_oem_source_intake_row()
        RETURNS trigger AS $$
        DECLARE intake_status text;
        BEGIN
            SELECT status INTO intake_status
              FROM aircraft_oem_source_intakes
             WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.intake_id ELSE NEW.intake_id END;
            IF intake_status IN ('APPROVED','MATERIALIZED') THEN
                RAISE EXCEPTION 'rows of approved/materialized OEM source intake are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_aircraft_oem_source_intake_row_controlled
        BEFORE INSERT OR UPDATE OR DELETE ON aircraft_oem_source_intake_rows
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_oem_source_intake_row();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_source_intake_row_controlled ON aircraft_oem_source_intake_rows"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_oem_source_intake_row()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_source_intake_controlled ON aircraft_oem_source_intakes"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_oem_source_intake()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_temporary_revision_controlled ON aircraft_oem_temporary_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_oem_temporary_revision()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_oem_publication_revision_controlled ON aircraft_oem_publication_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_oem_publication_revision()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_content_pack_revision_oem_backend_controlled ON aircraft_content_pack_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_oem_backend_content_pack_revision()")
    for table in CONTENT_CHILD_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_oem_backend_controlled ON {table}")
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_oem_backend_content_pack_child()")

    op.drop_index(
        "ix_aircraft_oem_source_intake_row_identity",
        table_name="aircraft_oem_source_intake_rows",
    )
    op.drop_index(
        "ix_aircraft_oem_source_intake_row_status",
        table_name="aircraft_oem_source_intake_rows",
    )
    op.drop_table("aircraft_oem_source_intake_rows")
    op.drop_index(
        "ix_aircraft_oem_source_intake_pack",
        table_name="aircraft_oem_source_intakes",
    )
    op.drop_index(
        "ix_aircraft_oem_source_intake_status",
        table_name="aircraft_oem_source_intakes",
    )
    op.drop_table("aircraft_oem_source_intakes")

    op.drop_constraint(
        "ck_aircraft_oem_temporary_revision_status",
        "aircraft_oem_temporary_revisions",
        type_="check",
    )
    op.execute(
        """
        UPDATE aircraft_oem_temporary_revisions
           SET status = 'WITHDRAWN'
         WHERE status IN ('CANDIDATE','REJECTED')
        """
    )
    op.create_check_constraint(
        "ck_aircraft_oem_temporary_revision_status",
        "aircraft_oem_temporary_revisions",
        "status IN ('ACTIVE','INCORPORATED','SUPERSEDED','WITHDRAWN','REPLACED')",
    )
