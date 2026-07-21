"""allow level 4 observation findings

Revision ID: qual_20260628_lvl4
Revises: qual_20260628_scope_fix
Create Date: 2026-06-28
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "qual_20260628_lvl4"
down_revision = "qual_20260628_scope_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DO $$
        DECLARE constraint_name text;
        BEGIN
            FOR constraint_name IN
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = current_schema()
                  AND rel.relname = 'qms_audit_findings'
                  AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) ILIKE '%LEVEL_3%'
                  AND pg_get_constraintdef(con.oid) NOT ILIKE '%LEVEL_4%'
            LOOP
                EXECUTE format('ALTER TABLE qms_audit_findings DROP CONSTRAINT IF EXISTS %I', constraint_name);
            END LOOP;
        END $$;
    """))
    conn.execute(text("""
        ALTER TABLE qms_audit_findings
        ADD CONSTRAINT ck_qms_audit_findings_level_v4
        CHECK (level IN ('LEVEL_1', 'LEVEL_2', 'LEVEL_3', 'LEVEL_4'))
        NOT VALID
    """))
    conn.execute(text("""
        ALTER TABLE qms_audit_findings
        VALIDATE CONSTRAINT ck_qms_audit_findings_level_v4
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE qms_audit_findings DROP CONSTRAINT IF EXISTS ck_qms_audit_findings_level_v4"))
