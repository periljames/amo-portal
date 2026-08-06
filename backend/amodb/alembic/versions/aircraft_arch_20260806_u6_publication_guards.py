"""protect published aircraft content-pack revisions

Revision ID: aircraft_arch_20260806_u6_guards
Revises: merge_20260806_aircraft_workforce
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "aircraft_arch_20260806_u6_guards"
down_revision: Union[str, Sequence[str], None] = "merge_20260806_aircraft_workforce"
branch_labels = None
depends_on = None


CONTENT_TABLES = (
    "aircraft_content_pack_sources",
    "aircraft_content_pack_positions",
    "aircraft_content_pack_components",
    "aircraft_content_pack_tasks",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_aircraft_content_pack_revision()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'published content-pack revisions are immutable';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status = 'DRAFT'
               AND NEW.status = 'PUBLISHED'
               AND ROW(
                    NEW.pack_id, NEW.revision_code, NEW.content_hash,
                    NEW.change_summary, NEW.created_by_user_id, NEW.created_at
               ) IS NOT DISTINCT FROM ROW(
                    OLD.pack_id, OLD.revision_code, OLD.content_hash,
                    OLD.change_summary, OLD.created_by_user_id, OLD.created_at
               )
               AND NEW.published_by_user_id IS NOT NULL
               AND NEW.published_at IS NOT NULL THEN
                RETURN NEW;
            END IF;

            IF OLD.status = 'PUBLISHED'
               AND NEW.status = 'SUPERSEDED'
               AND ROW(
                    NEW.pack_id, NEW.revision_code, NEW.content_hash,
                    NEW.change_summary, NEW.created_by_user_id, NEW.created_at,
                    NEW.published_by_user_id, NEW.published_at
               ) IS NOT DISTINCT FROM ROW(
                    OLD.pack_id, OLD.revision_code, OLD.content_hash,
                    OLD.change_summary, OLD.created_by_user_id, OLD.created_at,
                    OLD.published_by_user_id, OLD.published_at
               ) THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'content-pack revisions require a new controlled revision';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_aircraft_content_pack_revisions_controlled
        BEFORE UPDATE OR DELETE ON aircraft_content_pack_revisions
        FOR EACH ROW EXECUTE FUNCTION protect_aircraft_content_pack_revision();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_aircraft_content_pack_child()
        RETURNS trigger AS $$
        DECLARE
            old_status text;
            new_status text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                SELECT status INTO old_status
                FROM aircraft_content_pack_revisions
                WHERE id = OLD.revision_id;
                IF old_status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'published content-pack child rows are immutable';
                END IF;
            END IF;

            IF TG_OP <> 'DELETE' THEN
                SELECT status INTO new_status
                FROM aircraft_content_pack_revisions
                WHERE id = NEW.revision_id;
                IF new_status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'published content-pack child rows are immutable';
                END IF;
                RETURN NEW;
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in CONTENT_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_controlled
            BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_aircraft_content_pack_child();
            """
        )


def downgrade() -> None:
    for table in CONTENT_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_controlled ON {table}")
    op.execute("DROP FUNCTION IF EXISTS protect_aircraft_content_pack_child()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_aircraft_content_pack_revisions_controlled "
        "ON aircraft_content_pack_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS protect_aircraft_content_pack_revision()")
