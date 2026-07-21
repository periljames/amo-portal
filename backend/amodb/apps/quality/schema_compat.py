from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

_AUDIT_REF_PATTERN = re.compile(r"^(?P<family>[A-Z0-9]+)/(?P<unit>[A-Z0-9]+)/(?P<year>\d{2})/(?P<seq>\d+)$")
_AUDIT_REFERENCE_COLUMNS = ("reference_family", "unit_code", "ref_year", "ref_sequence")
_DEFAULT_AUDIT_SCOPES = (
    ("AC", "Aircraft audit", "FIRST_PARTY", "INTERNAL", 10, "Aircraft-specific airworthiness, aircraft records, and aircraft condition audit scope."),
    ("MO", "Maintenance facility", "FIRST_PARTY", "INTERNAL", 20, "Maintenance organisation facilities, stores, tooling, production, and quality system audit scope."),
    ("SC", "Subcontractor", "SECOND_PARTY", "EXTERNAL", 30, "Subcontracted maintenance or support organisation audit scope."),
    ("VEN", "Vendor / Supplier", "SECOND_PARTY", "EXTERNAL", 40, "Supplier, vendor, material, service, or procurement audit scope."),
    ("REG", "Regulatory / third-party external", "THIRD_PARTY", "THIRD_PARTY", 50, "Regulator, customer, certification body, or other third-party audit of the tenant."),
)
_LEGACY_SCOPE_ARTIFACT_COLUMNS = {
    "title", "status", "owner_user_id", "due_date", "source_type", "file_name", "file_path",
    "storage_path", "sha256", "mime_type", "size_bytes", "payload",
}


def _derive_reference_parts(audit_ref: str | None, *, planned_start: date | None, created_at: datetime | None) -> tuple[str, str, int, int]:
    if audit_ref:
        match = _AUDIT_REF_PATTERN.match(audit_ref.strip().upper())
        if match:
            return (match.group("family"), match.group("unit"), int(match.group("year")), int(match.group("seq")))
    basis = planned_start or (created_at.date() if created_at else date.today())
    return ("QAR", "MO", basis.year % 100, 1)


def _table_exists(db: Session, table_name: str) -> bool:
    return db.execute(text("SELECT to_regclass(:name)"), {"name": table_name}).scalar() is not None


def _table_columns(db: Session, table_name: str) -> dict[str, str]:
    rows = db.execute(
        text(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).mappings()
    return {str(row["column_name"]): str(row["udt_name"]) for row in rows}


def _next_available_legacy_name(db: Session) -> str:
    base = "qms_audit_scopes_legacy_artifacts_20260628"
    if not _table_exists(db, base):
        return base
    for index in range(2, 100):
        candidate = f"{base}_{index}"
        if not _table_exists(db, candidate):
            return candidate
    raise RuntimeError("No available qms_audit_scopes legacy quarantine name")


def _rename_constraint_if_exists(db: Session, table_name: str, old_name: str, new_name: str) -> None:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = current_schema()
              AND t.relname = :table_name
              AND c.conname = :old_name
            """
        ),
        {"table_name": table_name, "old_name": old_name},
    ).first()
    if row:
        db.execute(text(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'))


def _rename_index_if_exists(db: Session, old_name: str, new_name: str) -> None:
    if db.execute(text("SELECT to_regclass(:name)"), {"name": old_name}).scalar() is None:
        return
    if db.execute(text("SELECT to_regclass(:name)"), {"name": new_name}).scalar() is not None:
        return
    db.execute(text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def _quarantine_legacy_scope_artifact_table(db: Session) -> None:
    if not _table_exists(db, "qms_audit_scopes"):
        return
    cols = set(_table_columns(db, "qms_audit_scopes"))
    if "code" in cols and {"party_level", "default_kind"}.issubset(cols):
        return
    if not cols.intersection(_LEGACY_SCOPE_ARTIFACT_COLUMNS):
        return

    legacy_name = _next_available_legacy_name(db)
    db.execute(text(f'ALTER TABLE qms_audit_scopes RENAME TO "{legacy_name}"'))
    _rename_constraint_if_exists(db, legacy_name, "qms_audit_scopes_pkey", f"{legacy_name}_pkey")
    _rename_constraint_if_exists(db, legacy_name, "qms_audit_scopes_amo_id_fkey", f"{legacy_name}_amo_id_fkey")
    _rename_index_if_exists(db, "ix_qms_audit_scopes_amo_id", f"ix_{legacy_name}_amo_id")
    _rename_index_if_exists(db, "ix_qms_audit_scopes_amo_due", f"ix_{legacy_name}_amo_due")
    _rename_index_if_exists(db, "ix_qms_audit_scopes_amo_status", f"ix_{legacy_name}_amo_status")


def _create_scope_table_if_missing(db: Session) -> None:
    if _table_exists(db, "qms_audit_scopes"):
        return
    db.execute(text("""
        CREATE TABLE qms_audit_scopes (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            amo_id VARCHAR(36) NOT NULL,
            code VARCHAR(16) NOT NULL,
            name VARCHAR(120) NOT NULL,
            description TEXT,
            party_level VARCHAR(32) NOT NULL DEFAULT 'FIRST_PARTY',
            default_kind VARCHAR(32) NOT NULL DEFAULT 'INTERNAL',
            is_active BOOLEAN NOT NULL DEFAULT true,
            is_system_default BOOLEAN NOT NULL DEFAULT false,
            sort_order INTEGER NOT NULL DEFAULT 100,
            created_by_user_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_qms_audit_scopes PRIMARY KEY (id),
            CONSTRAINT fk_qms_audit_scopes_amo_id FOREIGN KEY (amo_id) REFERENCES amos(id) ON DELETE CASCADE,
            CONSTRAINT ck_qms_audit_scope_code_upper CHECK (code = upper(code))
        )
    """))


def _ensure_uuid_column(db: Session, table_name: str, column_name: str) -> None:
    if _table_columns(db, table_name).get(column_name) == "uuid":
        return
    db.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'))
    db.execute(text(f"""
        ALTER TABLE "{table_name}"
        ALTER COLUMN "{column_name}" TYPE uuid
        USING (
            CASE
                WHEN "{column_name}"::text ~* '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
                    THEN "{column_name}"::uuid
                WHEN NULLIF("{column_name}"::text, '') IS NULL
                    THEN gen_random_uuid()
                ELSE ('00000000-0000-4000-8000-' || substring(md5("{column_name}"::text) for 12))::uuid
            END
        )
    """))
    if table_name == "qms_audit_scopes" and column_name == "id":
        db.execute(text('ALTER TABLE qms_audit_scopes ALTER COLUMN id SET DEFAULT gen_random_uuid()'))


def _ensure_scope_table_columns(db: Session) -> None:
    _quarantine_legacy_scope_artifact_table(db)
    _create_scope_table_if_missing(db)

    statements = (
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS code VARCHAR(16)",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS name VARCHAR(120)",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS party_level VARCHAR(32) DEFAULT 'FIRST_PARTY'",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS default_kind VARCHAR(32) DEFAULT 'INTERNAL'",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS is_system_default BOOLEAN DEFAULT false",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 100",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS created_by_user_id VARCHAR(36)",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE qms_audit_scopes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_qms_audit_scope_code_per_amo ON qms_audit_scopes (amo_id, code)",
        "CREATE INDEX IF NOT EXISTS ix_qms_audit_scope_amo_active ON qms_audit_scopes (amo_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_qms_audit_scopes_amo_id ON qms_audit_scopes (amo_id)",
    )
    for statement in statements:
        db.execute(text(statement))

    _ensure_uuid_column(db, "qms_audit_scopes", "id")
    db.execute(text("""
        UPDATE qms_audit_scopes
        SET code = upper(COALESCE(NULLIF(code, ''), 'MO')),
            name = COALESCE(NULLIF(name, ''), 'Maintenance facility'),
            party_level = COALESCE(NULLIF(party_level, ''), 'FIRST_PARTY'),
            default_kind = COALESCE(NULLIF(default_kind, ''), 'INTERNAL'),
            is_active = COALESCE(is_active, true),
            is_system_default = COALESCE(is_system_default, false),
            sort_order = COALESCE(sort_order, 100),
            created_at = COALESCE(created_at, NOW()),
            updated_at = COALESCE(updated_at, NOW())
        WHERE code IS NULL OR name IS NULL OR party_level IS NULL OR default_kind IS NULL
           OR is_active IS NULL OR is_system_default IS NULL OR sort_order IS NULL
           OR created_at IS NULL OR updated_at IS NULL
    """))


def _seed_default_audit_scopes(db: Session) -> None:
    _ensure_scope_table_columns(db)
    amo_rows = db.execute(text("SELECT id FROM amos")).mappings().all()
    for amo in amo_rows:
        for code, name, party_level, default_kind, sort_order, description in _DEFAULT_AUDIT_SCOPES:
            db.execute(
                text(
                    """
                    INSERT INTO qms_audit_scopes
                        (id, amo_id, code, name, description, party_level, default_kind, is_active, is_system_default, sort_order, created_at, updated_at)
                    SELECT
                        CAST(:id AS uuid), :amo_id, :code, :name, :description, :party_level, :default_kind, true, true, :sort_order, NOW(), NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM qms_audit_scopes WHERE amo_id = :amo_id AND code = :code
                    )
                    """
                ),
                {"id": str(uuid.uuid4()), "amo_id": amo["id"], "code": code, "name": name, "description": description, "party_level": party_level, "default_kind": default_kind, "sort_order": sort_order},
            )


def ensure_qms_audit_scope_schema(db: Session) -> bool:
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False

    changed = False
    inspector = inspect(db.get_bind())
    table_names = set(inspector.get_table_names())

    # Some tenant databases already contain data migrated by earlier patches but
    # still have legacy SQLAlchemy-emulated enum columns.  BI_ANNUAL is longer
    # than the historical VARCHAR(7) frequency column, which caused schedule
    # creation to fail after deleting and recreating an audit.  Keep this guard
    # here so every Quality audit endpoint heals the table shape before writes.
    if "qms_audit_schedules" in table_names:
        frequency_width = db.execute(
            text(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'qms_audit_schedules'
                  AND column_name = 'frequency'
                """
            )
        ).scalar()
        if frequency_width is not None and int(frequency_width) < 16:
            db.execute(text("ALTER TABLE qms_audit_schedules ALTER COLUMN frequency TYPE VARCHAR(32)"))
            changed = True

    _ensure_scope_table_columns(db)
    changed = True

    for table_name in ("qms_audits", "qms_audit_schedules"):
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "audit_scope_id" not in columns:
            db.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN audit_scope_id UUID'))
            changed = True
        elif _table_columns(db, table_name).get("audit_scope_id") != "uuid":
            _ensure_uuid_column(db, table_name, "audit_scope_id")
            changed = True
        if "audit_scope_code" not in columns:
            db.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN audit_scope_code VARCHAR(16)'))
            changed = True

    _seed_default_audit_scopes(db)
    if _table_exists(db, "qms_audits"):
        db.execute(text("""
            UPDATE qms_audits
            SET audit_scope_code = upper(COALESCE(NULLIF(audit_scope_code, ''), NULLIF(unit_code, ''), 'MO'))
            WHERE audit_scope_code IS NULL OR audit_scope_code = ''
        """))
    if _table_exists(db, "qms_audit_schedules"):
        db.execute(text("""
            UPDATE qms_audit_schedules
            SET audit_scope_code = COALESCE(audit_scope_code, 'MO')
            WHERE audit_scope_code IS NULL
        """))
    db.commit()
    return changed


def ensure_qms_audit_reference_schema(db: Session) -> bool:
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False

    bind = get_bind()
    inspector = inspect(bind)
    audit_columns = {column["name"] for column in inspector.get_columns("qms_audits")}
    missing_columns = [column for column in _AUDIT_REFERENCE_COLUMNS if column not in audit_columns]

    if not missing_columns and "qms_audit_reference_counters" in inspector.get_table_names():
        return False

    for column in missing_columns:
        if column in {"reference_family", "unit_code"}:
            db.execute(text(f"ALTER TABLE qms_audits ADD COLUMN {column} VARCHAR(16)"))
        else:
            db.execute(text(f"ALTER TABLE qms_audits ADD COLUMN {column} INTEGER"))

    if "qms_audit_reference_counters" not in inspector.get_table_names():
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS qms_audit_reference_counters (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                amo_id VARCHAR(36) NOT NULL REFERENCES amos(id) ON DELETE CASCADE,
                reference_family VARCHAR(16) NOT NULL,
                unit_code VARCHAR(16) NOT NULL,
                ref_year INTEGER NOT NULL,
                last_value INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_qms_audit_ref_counter_scope
            ON qms_audit_reference_counters (amo_id, reference_family, unit_code, ref_year)
        """))

    legacy_rows = db.execute(
        text(
            """
            SELECT id, audit_ref, planned_start, created_at, reference_family, unit_code, ref_year, ref_sequence
            FROM qms_audits
            """
        )
    ).mappings()

    for row in legacy_rows:
        reference_family, unit_code, ref_year, ref_sequence = _derive_reference_parts(
            row.get("audit_ref"), planned_start=row.get("planned_start"), created_at=row.get("created_at")
        )
        db.execute(
            text(
                """
                UPDATE qms_audits
                SET reference_family = COALESCE(reference_family, :reference_family),
                    unit_code = COALESCE(unit_code, :unit_code),
                    ref_year = COALESCE(ref_year, :ref_year),
                    ref_sequence = COALESCE(ref_sequence, :ref_sequence)
                WHERE id = :audit_id
                """
            ),
            {"audit_id": row["id"], "reference_family": reference_family, "unit_code": unit_code, "ref_year": ref_year, "ref_sequence": ref_sequence},
        )

    db.commit()
    return True


def audit_reference_columns_present(db: Session) -> bool:
    columns = {column["name"] for column in inspect(db.get_bind()).get_columns("qms_audits")}
    return all(column in columns for column in _AUDIT_REFERENCE_COLUMNS)
