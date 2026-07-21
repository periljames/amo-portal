"""tenant audit scopes and scope-based QAR references

Revision ID: qual_20260627_scope
Revises: qual_20260627_wf_close
Create Date: 2026-06-27
"""
from __future__ import annotations

import re
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import bindparam, text
from sqlalchemy.dialects import postgresql

revision: str = "qual_20260627_scope"
down_revision: str | tuple[str, ...] | None = "qual_20260627_wf_close"
branch_labels = None
depends_on = None

_DEFAULT_SCOPES = (
    ("AC", "Aircraft audit", "FIRST_PARTY", "INTERNAL", 10, "Aircraft-specific airworthiness, aircraft records, and aircraft condition audit scope."),
    ("MO", "Maintenance facility", "FIRST_PARTY", "INTERNAL", 20, "Maintenance organisation facilities, stores, tooling, production, and quality system audit scope."),
    ("SC", "Subcontractor", "SECOND_PARTY", "EXTERNAL", 30, "Subcontracted maintenance or support organisation audit scope."),
    ("VEN", "Vendor / Supplier", "SECOND_PARTY", "EXTERNAL", 40, "Supplier, vendor, material, service, or procurement audit scope."),
    ("REG", "Regulatory / third-party external", "THIRD_PARTY", "THIRD_PARTY", 50, "Regulator, customer, certification body, or other third-party audit of the tenant."),
)

_EXPECTED_SCOPE_COLUMNS = {
    "id",
    "amo_id",
    "code",
    "name",
    "description",
    "party_level",
    "default_kind",
    "is_active",
    "is_system_default",
    "sort_order",
    "created_at",
    "updated_at",
}


def _has_table(conn, table_name: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:name)"), {"name": table_name}).scalar() is not None


def _column_names(conn, table_name: str) -> set[str]:
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
    )
    return {str(row[0]) for row in rows}


def _has_column(conn, table_name: str, column_name: str) -> bool:
    return column_name in _column_names(conn, table_name)


def _column_udt(conn, table_name: str, column_name: str) -> str | None:
    return conn.execute(
        text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()


def _index_exists(conn, index_name: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:name)"), {"name": index_name}).scalar() is not None


def _ensure_index(conn, index_name: str, table_name: str, columns_sql: str, unique: bool = False) -> None:
    if _index_exists(conn, index_name):
        return
    uniqueness = "UNIQUE " if unique else ""
    conn.execute(text(f"CREATE {uniqueness}INDEX {index_name} ON {table_name} ({columns_sql})"))


def _is_real_scope_definition_table(conn) -> bool:
    if not _has_table(conn, "qms_audit_scopes"):
        return False
    cols = _column_names(conn, "qms_audit_scopes")
    return _EXPECTED_SCOPE_COLUMNS.issubset(cols) and _column_udt(conn, "qms_audit_scopes", "id") == "uuid"


def _legacy_backup_name(conn) -> str:
    base = "qms_audit_scopes_legacy_artifacts_20260628"
    if not _has_table(conn, base):
        return base
    for i in range(2, 100):
        candidate = f"{base}_{i}"
        if not _has_table(conn, candidate):
            return candidate
    raise RuntimeError("Could not choose a legacy backup name for qms_audit_scopes")


def _prepare_scope_definition_table(conn) -> None:
    """Preserve any old non-scope table, then create the real audit-scope table.

    The live database has previously used qms_audit_scopes for a legacy artifact/task
    shape. That table must not be mutated into this new definition table because its
    columns and id type do not match this model. We keep it by renaming it and create
    the real table from a clean shape.
    """
    if _has_table(conn, "qms_audit_scopes") and not _is_real_scope_definition_table(conn):
        backup_name = _legacy_backup_name(conn)
        conn.execute(text(f"ALTER TABLE qms_audit_scopes RENAME TO {backup_name}"))

    if not _has_table(conn, "qms_audit_scopes"):
        op.create_table(
            "qms_audit_scopes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
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
            sa.CheckConstraint("code = upper(code)", name="ck_qms_audit_scope_code_upper"),
        )

    # Ensure old partial attempts or manually-created tables have required columns.
    if not _has_column(conn, "qms_audit_scopes", "created_by_user_id"):
        op.add_column("qms_audit_scopes", sa.Column("created_by_user_id", sa.String(length=36), nullable=True))

    _ensure_index(conn, "ix_qms_audit_scope_amo_active", "qms_audit_scopes", "amo_id, is_active")
    _ensure_index(conn, "ux_qms_audit_scopes_amo_code", "qms_audit_scopes", "amo_id, code", unique=True)


def _ensure_uuid_column(conn, table_name: str, column_name: str) -> None:
    if not _has_table(conn, table_name):
        return
    if not _has_column(conn, table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, postgresql.UUID(as_uuid=True), nullable=True))
        return
    # Do not attempt risky in-place conversion during this migration. If a legacy DB
    # ever has this column with the wrong type, preserve it and add a clean UUID column.
    if _column_udt(conn, table_name, column_name) != "uuid":
        backup = f"{column_name}_legacy_text"
        if not _has_column(conn, table_name, backup):
            conn.execute(text(f"ALTER TABLE {table_name} RENAME COLUMN {column_name} TO {backup}"))
            op.add_column(table_name, sa.Column(column_name, postgresql.UUID(as_uuid=True), nullable=True))


def _ensure_audit_scope_columns(conn) -> None:
    for table_name in ("qms_audits", "qms_audit_schedules"):
        if not _has_table(conn, table_name):
            continue
        _ensure_uuid_column(conn, table_name, "audit_scope_id")
        if not _has_column(conn, table_name, "audit_scope_code"):
            op.add_column(table_name, sa.Column("audit_scope_code", sa.String(length=16), nullable=True))
        _ensure_index(conn, f"ix_{table_name}_audit_scope_id", table_name, "audit_scope_id")
        _ensure_index(conn, f"ix_{table_name}_audit_scope_code", table_name, "audit_scope_code")


def _stable_scope_uuid(amo_id: str, code: str) -> uuid.UUID:
    return uuid.UUID("00000000-0000-4000-8000-" + re.sub(r"[^0-9a-f]", "", uuid.uuid5(uuid.NAMESPACE_DNS, f"{amo_id}:qms_audit_scope:{code}").hex)[:12])


def _seed_default_scopes(conn) -> None:
    insert_stmt = text(
        """
        INSERT INTO qms_audit_scopes
            (id, amo_id, code, name, description, party_level, default_kind, is_active, is_system_default, sort_order, created_at, updated_at)
        VALUES
            (:scope_id, :amo_id, :code, :name, :description, :party_level, :default_kind, true, true, :sort_order, NOW(), NOW())
        ON CONFLICT (amo_id, code)
        DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            party_level = EXCLUDED.party_level,
            default_kind = EXCLUDED.default_kind,
            is_active = true,
            is_system_default = true,
            sort_order = EXCLUDED.sort_order,
            updated_at = NOW()
        """
    ).bindparams(bindparam("scope_id", type_=postgresql.UUID(as_uuid=True)))

    amos = conn.execute(text("SELECT id::text AS id FROM amos ORDER BY id::text")).mappings().all()
    for amo in amos:
        amo_id = str(amo["id"])
        for code, name, party_level, default_kind, sort_order, description in _DEFAULT_SCOPES:
            conn.execute(
                insert_stmt,
                {
                    "scope_id": _stable_scope_uuid(amo_id, code),
                    "amo_id": amo_id,
                    "code": code,
                    "name": name,
                    "description": description,
                    "party_level": party_level,
                    "default_kind": default_kind,
                    "sort_order": sort_order,
                },
            )


def _normalise_schedules(conn) -> None:
    if not _has_table(conn, "qms_audit_schedules"):
        return
    conn.execute(
        text(
            """
            UPDATE qms_audit_schedules s
            SET audit_scope_code = COALESCE(s.audit_scope_code, ds.code, 'MO'),
                audit_scope_id = COALESCE(s.audit_scope_id, ds.id)
            FROM qms_audit_scopes ds
            WHERE ds.amo_id = s.amo_id
              AND ds.code = CASE
                    WHEN s.kind = 'THIRD_PARTY' THEN 'REG'
                    WHEN s.kind = 'EXTERNAL' THEN 'SC'
                    ELSE 'MO'
                  END
              AND (s.audit_scope_code IS NULL OR s.audit_scope_id IS NULL)
            """
        )
    )


def _normalise_audits(conn) -> None:
    if not _has_table(conn, "qms_audits"):
        return
    conn.execute(
        text(
            """
            UPDATE qms_audits
            SET audit_scope_code = COALESCE(audit_scope_code, NULLIF(unit_code, ''), 'MO')
            WHERE audit_scope_code IS NULL
            """
        )
    )
    conn.execute(
        text(
            """
            WITH scoped AS (
                SELECT
                    a.id,
                    COALESCE(existing_scope.id, default_scope.id) AS scope_id,
                    COALESCE(existing_scope.code, default_scope.code, 'MO') AS scope_code,
                    (EXTRACT(YEAR FROM COALESCE(a.planned_start, a.created_at::date, CURRENT_DATE))::int % 100) AS ref_year,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.amo_id,
                                     COALESCE(existing_scope.code, default_scope.code, 'MO'),
                                     (EXTRACT(YEAR FROM COALESCE(a.planned_start, a.created_at::date, CURRENT_DATE))::int % 100)
                        ORDER BY a.created_at NULLS LAST, a.id
                    ) AS seq
                FROM qms_audits a
                LEFT JOIN qms_audit_scopes existing_scope
                    ON existing_scope.amo_id = a.amo_id
                   AND existing_scope.code = UPPER(COALESCE(a.audit_scope_code, a.unit_code, ''))
                LEFT JOIN qms_audit_scopes default_scope
                    ON default_scope.amo_id = a.amo_id
                   AND default_scope.code = CASE
                        WHEN a.kind = 'THIRD_PARTY' THEN 'REG'
                        WHEN a.kind = 'EXTERNAL' THEN 'SC'
                        ELSE 'MO'
                   END
            )
            UPDATE qms_audits a
            SET audit_scope_id = scoped.scope_id,
                audit_scope_code = scoped.scope_code,
                reference_family = 'QAR',
                unit_code = scoped.scope_code,
                ref_year = scoped.ref_year,
                ref_sequence = scoped.seq,
                audit_ref = 'QAR/' || scoped.scope_code || '/' || LPAD(scoped.ref_year::text, 2, '0') || '/' || LPAD(scoped.seq::text, 3, '0')
            FROM scoped
            WHERE a.id = scoped.id
              AND (
                a.audit_scope_id IS NULL
                OR a.audit_scope_code IS NULL
                OR a.unit_code IS DISTINCT FROM scoped.scope_code
                OR a.ref_year IS DISTINCT FROM scoped.ref_year
                OR a.audit_ref !~ ('^QAR/' || scoped.scope_code || '/' || LPAD(scoped.ref_year::text, 2, '0') || '/[0-9]{3,}$')
              )
            """
        )
    )
    if _has_table(conn, "qms_audit_reference_counters"):
        conn.execute(
            text(
                """
                WITH counter_source AS (
                    SELECT amo_id, unit_code, ref_year, MAX(ref_sequence) AS last_value
                    FROM qms_audits
                    WHERE reference_family = 'QAR'
                      AND amo_id IS NOT NULL
                      AND unit_code IS NOT NULL
                      AND ref_year IS NOT NULL
                      AND ref_sequence IS NOT NULL
                    GROUP BY amo_id, unit_code, ref_year
                )
                INSERT INTO qms_audit_reference_counters
                    (id, amo_id, reference_family, unit_code, ref_year, last_value, created_at, updated_at)
                SELECT
                    ('00000000-0000-4000-8000-' || substring(md5(amo_id::text || ':' || unit_code::text || ':' || ref_year::text) for 12))::uuid,
                    amo_id, 'QAR', unit_code, ref_year, last_value, NOW(), NOW()
                FROM counter_source
                ON CONFLICT (amo_id, reference_family, unit_code, ref_year)
                DO UPDATE SET
                    last_value = GREATEST(qms_audit_reference_counters.last_value, EXCLUDED.last_value),
                    updated_at = NOW()
                """
            )
        )


def upgrade() -> None:
    conn = op.get_bind()
    _prepare_scope_definition_table(conn)
    _ensure_audit_scope_columns(conn)
    _seed_default_scopes(conn)
    _normalise_schedules(conn)
    _normalise_audits(conn)


def downgrade() -> None:
    conn = op.get_bind()
    for table_name in ("qms_audits", "qms_audit_schedules"):
        if _has_table(conn, table_name):
            if _index_exists(conn, f"ix_{table_name}_audit_scope_code"):
                op.drop_index(f"ix_{table_name}_audit_scope_code", table_name=table_name)
            if _index_exists(conn, f"ix_{table_name}_audit_scope_id"):
                op.drop_index(f"ix_{table_name}_audit_scope_id", table_name=table_name)
            if _has_column(conn, table_name, "audit_scope_code"):
                op.drop_column(table_name, "audit_scope_code")
            if _has_column(conn, table_name, "audit_scope_id"):
                op.drop_column(table_name, "audit_scope_id")
    if _has_table(conn, "qms_audit_scopes"):
        if _index_exists(conn, "ix_qms_audit_scope_amo_active"):
            op.drop_index("ix_qms_audit_scope_amo_active", table_name="qms_audit_scopes")
        if _index_exists(conn, "ux_qms_audit_scopes_amo_code"):
            op.drop_index("ux_qms_audit_scopes_amo_code", table_name="qms_audit_scopes")
        op.drop_table("qms_audit_scopes")
