"""repair audit scope columns after legacy scope migration

Revision ID: qual_20260628_scope_fix
Revises: qual_20260627_scope
Create Date: 2026-06-28
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = "qual_20260628_scope_fix"
down_revision: str | tuple[str, ...] | None = "qual_20260627_scope"
branch_labels = None
depends_on = None

_DEFAULT_SCOPES = (
    ("AC", "Aircraft audit", "FIRST_PARTY", "INTERNAL", 10, "Aircraft-specific airworthiness, aircraft records, and aircraft condition audit scope."),
    ("MO", "Maintenance facility", "FIRST_PARTY", "INTERNAL", 20, "Maintenance organisation facilities, stores, tooling, production, and quality system audit scope."),
    ("SC", "Subcontractor", "SECOND_PARTY", "EXTERNAL", 30, "Subcontracted maintenance or support organisation audit scope."),
    ("VEN", "Vendor / Supplier", "SECOND_PARTY", "EXTERNAL", 40, "Supplier, vendor, material, service, or procurement audit scope."),
    ("REG", "Regulatory / third-party external", "THIRD_PARTY", "THIRD_PARTY", 50, "Regulator, customer, certification body, or other third-party audit of the tenant."),
)


def _has_table(conn, table_name: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:name)"), {"name": table_name}).scalar() is not None


def _column_names(conn, table_name: str) -> set[str]:
    if not _has_table(conn, table_name):
        return set()
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalars()
    return {str(row) for row in rows}


def _create_or_repair_scope_table(conn) -> None:
    required = {"id", "amo_id", "code", "name"}
    if _has_table(conn, "qms_audit_scopes"):
        existing = _column_names(conn, "qms_audit_scopes")
        if required.issubset(existing):
            # Ensure newer optional columns exist even if an older clean table was created.
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS description TEXT"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS party_level VARCHAR(32) DEFAULT 'FIRST_PARTY'"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS default_kind VARCHAR(32) DEFAULT 'INTERNAL'"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS is_system_default BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 100"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS created_by_user_id VARCHAR(36)"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"))
            conn.execute(text("ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_qms_audit_scope_code_per_amo ON qms_audit_scopes (amo_id, code)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audit_scope_amo_active ON qms_audit_scopes (amo_id, is_active)"))
            return

        # Legacy artifact table with same name. Preserve it; do not mutate it.
        suffix = "legacy_artifacts_20260628"
        target = f"qms_audit_scopes_{suffix}"
        n = 1
        while _has_table(conn, target):
            n += 1
            target = f"qms_audit_scopes_{suffix}_{n}"
        conn.execute(text(f'ALTER TABLE qms_audit_scopes RENAME TO {target}'))

    op.create_table(
        "qms_audit_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("party_level", sa.String(length=32), nullable=False, server_default="FIRST_PARTY"),
        sa.Column("default_kind", sa.String(length=32), nullable=False, server_default="INTERNAL"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "code", name="uq_qms_audit_scope_code_per_amo"),
    )
    op.create_index("ix_qms_audit_scope_amo_active", "qms_audit_scopes", ["amo_id", "is_active"])


def _ensure_audit_columns(conn) -> None:
    if _has_table(conn, "qms_audits"):
        conn.execute(text("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS audit_scope_id UUID"))
        conn.execute(text("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS audit_scope_code VARCHAR(16)"))
        conn.execute(text("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS reference_family VARCHAR(16)"))
        conn.execute(text("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS unit_code VARCHAR(16)"))
        conn.execute(text("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS ref_year INTEGER"))
        conn.execute(text("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS ref_sequence INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audits_audit_scope_id ON qms_audits (audit_scope_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audits_audit_scope_code ON qms_audits (audit_scope_code)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audits_ref_scope ON qms_audits (amo_id, domain, reference_family, unit_code, ref_year, ref_sequence)"))

    if _has_table(conn, "qms_audit_schedules"):
        conn.execute(text("ALTER TABLE qms_audit_schedules ADD COLUMN IF NOT EXISTS audit_scope_id UUID"))
        conn.execute(text("ALTER TABLE qms_audit_schedules ADD COLUMN IF NOT EXISTS audit_scope_code VARCHAR(16)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_audit_scope_id ON qms_audit_schedules (audit_scope_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_audit_scope_code ON qms_audit_schedules (audit_scope_code)"))


def _ensure_counter_table(conn) -> None:
    if not _has_table(conn, "qms_audit_reference_counters"):
        op.create_table(
            "qms_audit_reference_counters",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("reference_family", sa.String(length=16), nullable=False),
            sa.Column("unit_code", sa.String(length=16), nullable=False),
            sa.Column("ref_year", sa.Integer(), nullable=False),
            sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS id UUID"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS amo_id VARCHAR(36)"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS reference_family VARCHAR(16)"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS unit_code VARCHAR(16)"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS ref_year INTEGER"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS last_value INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE qms_audit_reference_counters ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"))
        conn.execute(text("UPDATE qms_audit_reference_counters SET id = ('00000000-0000-4000-8000-' || substring(md5(COALESCE(amo_id, '') || COALESCE(reference_family, '') || COALESCE(unit_code, '') || COALESCE(ref_year::text, '')) for 12))::uuid WHERE id IS NULL AND amo_id IS NOT NULL AND unit_code IS NOT NULL AND ref_year IS NOT NULL"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_qms_audit_ref_counter_scope ON qms_audit_reference_counters (amo_id, reference_family, unit_code, ref_year)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_audit_ref_counter_scope ON qms_audit_reference_counters (amo_id, reference_family, unit_code, ref_year)"))


def _scope_seed_tenants(conn) -> list[str]:
    tenant_ids: set[str] = set()
    for sql in (
        "SELECT id FROM amos WHERE id IS NOT NULL",
        "SELECT DISTINCT amo_id AS id FROM qms_audits WHERE amo_id IS NOT NULL" if _has_table(conn, "qms_audits") else None,
        "SELECT DISTINCT amo_id AS id FROM qms_audit_schedules WHERE amo_id IS NOT NULL" if _has_table(conn, "qms_audit_schedules") else None,
    ):
        if not sql:
            continue
        for row in conn.execute(text(sql)).mappings().all():
            if row.get("id"):
                tenant_ids.add(str(row["id"]))
    return sorted(tenant_ids)


def _seed_default_scopes(conn) -> None:
    for amo_id in _scope_seed_tenants(conn):
        for code, name, party_level, default_kind, sort_order, description in _DEFAULT_SCOPES:
            conn.execute(
                text(
                    """
                    INSERT INTO qms_audit_scopes
                        (id, amo_id, code, name, description, party_level, default_kind, is_active, is_system_default, sort_order, created_at, updated_at)
                    SELECT
                        :id, :amo_id, :code, :name, :description, :party_level, :default_kind, TRUE, TRUE, :sort_order, NOW(), NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM qms_audit_scopes WHERE amo_id = :amo_id AND code = :code
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "amo_id": amo_id,
                    "code": code,
                    "name": name,
                    "description": description,
                    "party_level": party_level,
                    "default_kind": default_kind,
                    "sort_order": sort_order,
                },
            )


def _normalise_audit_rows(conn) -> None:
    if _has_table(conn, "qms_audit_schedules"):
        conn.execute(text("""
            UPDATE qms_audit_schedules s
            SET audit_scope_code = COALESCE(NULLIF(s.audit_scope_code, ''), ds.code, 'MO'),
                audit_scope_id = COALESCE(s.audit_scope_id, ds.id)
            FROM qms_audit_scopes ds
            WHERE ds.amo_id = s.amo_id
              AND ds.code = CASE WHEN s.kind = 'THIRD_PARTY' THEN 'REG' WHEN s.kind = 'EXTERNAL' THEN 'SC' ELSE 'MO' END
              AND (s.audit_scope_code IS NULL OR s.audit_scope_code = '' OR s.audit_scope_id IS NULL)
        """))
        conn.execute(text("""
            UPDATE qms_audit_schedules
            SET audit_scope_code = COALESCE(NULLIF(audit_scope_code, ''), CASE WHEN kind = 'THIRD_PARTY' THEN 'REG' WHEN kind = 'EXTERNAL' THEN 'SC' ELSE 'MO' END)
            WHERE audit_scope_code IS NULL OR audit_scope_code = ''
        """))

    if _has_table(conn, "qms_audits"):
        conn.execute(text("""
            WITH scoped AS (
                SELECT
                    a.id,
                    COALESCE(existing_scope.id, default_scope.id) AS scope_id,
                    COALESCE(existing_scope.code, default_scope.code, CASE WHEN a.kind = 'THIRD_PARTY' THEN 'REG' WHEN a.kind = 'EXTERNAL' THEN 'SC' ELSE 'MO' END) AS scope_code,
                    (EXTRACT(YEAR FROM COALESCE(a.planned_start, a.created_at::date, CURRENT_DATE))::int % 100) AS ref_year,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.amo_id,
                                     COALESCE(existing_scope.code, default_scope.code, CASE WHEN a.kind = 'THIRD_PARTY' THEN 'REG' WHEN a.kind = 'EXTERNAL' THEN 'SC' ELSE 'MO' END),
                                     (EXTRACT(YEAR FROM COALESCE(a.planned_start, a.created_at::date, CURRENT_DATE))::int % 100)
                        ORDER BY a.created_at NULLS LAST, a.id
                    ) AS seq
                FROM qms_audits a
                LEFT JOIN qms_audit_scopes existing_scope
                    ON existing_scope.amo_id = a.amo_id
                   AND existing_scope.code = UPPER(COALESCE(NULLIF(a.audit_scope_code, ''), NULLIF(a.unit_code, ''), ''))
                LEFT JOIN qms_audit_scopes default_scope
                    ON default_scope.amo_id = a.amo_id
                   AND default_scope.code = CASE WHEN a.kind = 'THIRD_PARTY' THEN 'REG' WHEN a.kind = 'EXTERNAL' THEN 'SC' ELSE 'MO' END
            )
            UPDATE qms_audits a
            SET audit_scope_id = COALESCE(a.audit_scope_id, scoped.scope_id),
                audit_scope_code = COALESCE(NULLIF(a.audit_scope_code, ''), scoped.scope_code),
                reference_family = COALESCE(NULLIF(a.reference_family, ''), 'QAR'),
                unit_code = COALESCE(NULLIF(a.unit_code, ''), scoped.scope_code),
                ref_year = COALESCE(a.ref_year, scoped.ref_year),
                ref_sequence = COALESCE(a.ref_sequence, scoped.seq),
                audit_ref = COALESCE(NULLIF(a.audit_ref, ''), 'QAR/' || scoped.scope_code || '/' || LPAD(scoped.ref_year::text, 2, '0') || '/' || LPAD(scoped.seq::text, 3, '0'))
            FROM scoped
            WHERE a.id = scoped.id
        """))
        conn.execute(text("""
            INSERT INTO qms_audit_reference_counters
                (id, amo_id, reference_family, unit_code, ref_year, last_value, created_at, updated_at)
            SELECT
                ('00000000-0000-4000-8000-' || substring(md5(amo_id || reference_family || unit_code || ref_year::text) for 12))::uuid,
                amo_id,
                reference_family,
                unit_code,
                ref_year,
                MAX(ref_sequence) AS last_value,
                NOW(),
                NOW()
            FROM qms_audits
            WHERE amo_id IS NOT NULL
              AND reference_family IS NOT NULL
              AND unit_code IS NOT NULL
              AND ref_year IS NOT NULL
              AND ref_sequence IS NOT NULL
            GROUP BY amo_id, reference_family, unit_code, ref_year
            ON CONFLICT (amo_id, reference_family, unit_code, ref_year)
            DO UPDATE SET
                last_value = GREATEST(qms_audit_reference_counters.last_value, EXCLUDED.last_value),
                updated_at = NOW()
        """))


def upgrade() -> None:
    conn = op.get_bind()
    _create_or_repair_scope_table(conn)
    _ensure_audit_columns(conn)
    _ensure_counter_table(conn)
    _seed_default_scopes(conn)
    _normalise_audit_rows(conn)


def downgrade() -> None:
    # Intentionally non-destructive. This repair migration only adds compatibility columns/indexes.
    pass
