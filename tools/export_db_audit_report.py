"""
AMO Portal DB audit export using SQLAlchemy/psycopg2.
Run from repo root or backend folder after setting DATABASE_WRITE_URL or DATABASE_URL.
Exports schema/statistics only, not table row data.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

QUERIES: dict[str, str] = {
    "database_identity": """
        SELECT current_database() AS database_name,
               current_user AS current_user,
               inet_server_addr()::text AS server_addr,
               inet_server_port() AS server_port,
               version() AS postgres_version,
               now()::text AS captured_at
    """,
    "alembic_versions": "SELECT version_num FROM alembic_version ORDER BY version_num",
    "table_inventory": """
        SELECT n.nspname AS schema_name,
               c.relname AS table_name,
               c.relkind AS relkind,
               pg_total_relation_size(c.oid) AS total_bytes,
               pg_relation_size(c.oid) AS table_bytes,
               pg_indexes_size(c.oid) AS index_bytes,
               COALESCE(s.n_live_tup, c.reltuples)::bigint AS estimated_rows,
               COALESCE(s.n_dead_tup, 0)::bigint AS estimated_dead_rows,
               s.seq_scan,
               s.seq_tup_read,
               s.idx_scan,
               s.n_tup_ins,
               s.n_tup_upd,
               s.n_tup_del,
               s.last_vacuum::text AS last_vacuum,
               s.last_autovacuum::text AS last_autovacuum,
               s.last_analyze::text AS last_analyze,
               s.last_autoanalyze::text AS last_autoanalyze
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
          AND c.relkind IN ('r','p','m')
        ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname
    """,
    "columns": """
        SELECT table_schema, table_name, ordinal_position, column_name, data_type, udt_name,
               character_maximum_length, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY table_schema, table_name, ordinal_position
    """,
    "constraints": """
        SELECT tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type,
               string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema NOT IN ('pg_catalog','information_schema')
          AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE')
        GROUP BY tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type
        ORDER BY tc.table_schema, tc.table_name, tc.constraint_type, tc.constraint_name
    """,
    "foreign_keys": """
        SELECT tc.table_schema, tc.table_name, tc.constraint_name,
               string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns,
               ccu.table_schema AS foreign_table_schema,
               ccu.table_name AS foreign_table_name,
               string_agg(ccu.column_name, ', ' ORDER BY kcu.ordinal_position) AS foreign_columns
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema NOT IN ('pg_catalog','information_schema')
        GROUP BY tc.table_schema, tc.table_name, tc.constraint_name, ccu.table_schema, ccu.table_name
        ORDER BY tc.table_schema, tc.table_name, tc.constraint_name
    """,
    "indexes": """
        SELECT schemaname, tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname NOT IN ('pg_catalog','information_schema')
        ORDER BY schemaname, tablename, indexname
    """,
    "index_usage": """
        SELECT s.schemaname, s.relname AS table_name, s.indexrelname AS index_name,
               s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
               pg_relation_size(s.indexrelid) AS index_bytes
        FROM pg_stat_user_indexes s
        ORDER BY s.idx_scan ASC, pg_relation_size(s.indexrelid) DESC
    """,
    "sequential_scan_hotspots": """
        SELECT relname AS table_name, seq_scan, seq_tup_read, idx_scan, n_live_tup, n_dead_tup,
               pg_total_relation_size(relid) AS total_bytes
        FROM pg_stat_user_tables
        ORDER BY seq_tup_read DESC, seq_scan DESC
    """,
    "missing_fk_indexes": """
        WITH fk_cols AS (
          SELECT conrelid, conname, unnest(conkey) AS attnum
          FROM pg_constraint
          WHERE contype = 'f'
        ),
        fk_groups AS (
          SELECT conrelid, conname, array_agg(attnum ORDER BY attnum) AS attnums
          FROM fk_cols
          GROUP BY conrelid, conname
        ),
        idx_cols AS (
          SELECT indrelid, indkey::int[] AS indkeys FROM pg_index
        )
        SELECT n.nspname AS schema_name, c.relname AS table_name, fg.conname AS fk_name,
               string_agg(a.attname, ', ' ORDER BY a.attnum) AS fk_columns
        FROM fk_groups fg
        JOIN pg_class c ON c.oid = fg.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = fg.conrelid AND a.attnum = ANY(fg.attnums)
        WHERE NOT EXISTS (
          SELECT 1 FROM idx_cols i
          WHERE i.indrelid = fg.conrelid
            AND i.indkeys[0:cardinality(fg.attnums)-1] = fg.attnums
        )
        GROUP BY n.nspname, c.relname, fg.conname
        ORDER BY n.nspname, c.relname, fg.conname
    """,
    "duplicate_index_candidates": """
        WITH idx AS (
          SELECT n.nspname AS schema_name,
                 c.relname AS table_name,
                 i.indexrelid::regclass::text AS index_name,
                 i.indrelid,
                 i.indkey,
                 i.indisunique,
                 i.indisprimary,
                 pg_get_indexdef(i.indexrelid) AS indexdef,
                 pg_relation_size(i.indexrelid) AS index_bytes
          FROM pg_index i
          JOIN pg_class c ON c.oid = i.indrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          WHERE n.nspname NOT IN ('pg_catalog','information_schema')
        )
        SELECT a.schema_name, a.table_name,
               a.index_name AS possible_redundant_index,
               b.index_name AS covering_index,
               a.index_bytes AS redundant_index_bytes,
               a.indexdef AS redundant_indexdef,
               b.indexdef AS covering_indexdef
        FROM idx a
        JOIN idx b
          ON a.indrelid = b.indrelid
         AND a.index_name <> b.index_name
         AND b.indkey::text LIKE a.indkey::text || '%'
         AND (b.indisunique = a.indisunique OR b.indisunique = true)
        WHERE a.indisprimary = false
        ORDER BY a.index_bytes DESC, a.schema_name, a.table_name
    """,
    "extensions": "SELECT extname, extversion FROM pg_extension ORDER BY extname",
}


def sanitize_url(url: str) -> str:
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", url)


def rows_to_dicts(result) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result]


def run_optional(cmd: list[str], cwd: Path, out_file: Path) -> None:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        out_file.write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    except Exception as exc:
        out_file.write_text(str(exc), encoding="utf-8")


def main() -> int:
    url = os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_WRITE_URL or DATABASE_URL is required.", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_dir = Path.cwd()
    out_dir = start_dir / f"db_audit_report_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, pool_pre_ping=True)
    report: dict[str, Any] = {
        "metadata": {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "database_url_sanitized": sanitize_url(url),
            "exports_table_data": False,
        },
        "sections": {},
        "errors": {},
    }

    with engine.connect() as conn:
        for name, query in QUERIES.items():
            try:
                report["sections"][name] = rows_to_dicts(conn.execute(text(query)))
            except SQLAlchemyError as exc:
                report["errors"][name] = str(exc)

    (out_dir / "db_audit_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    for section, rows in report["sections"].items():
        csv_path = out_dir / f"{section}.csv"
        if not rows:
            csv_path.write_text("", encoding="utf-8")
            continue
        headers = list(rows[0].keys())
        lines = [",".join(headers)]
        for row in rows:
            values = []
            for h in headers:
                value = "" if row.get(h) is None else str(row.get(h))
                values.append('"' + value.replace('"', '""').replace("\n", " ") + '"')
            lines.append(",".join(values))
        csv_path.write_text("\n".join(lines), encoding="utf-8")

    # SQLAlchemy model inventory if import works from this location.
    try:
        from amodb.core.database import Base  # type: ignore
        lines = []
        for mapper in sorted(Base.registry.mappers, key=lambda m: getattr(m.class_, "__name__", "")):
            cls = mapper.class_
            table = getattr(cls, "__table__", None)
            if table is None:
                continue
            lines.append(f"{cls.__module__}.{cls.__name__} -> {table.name}")
            for col in table.columns:
                lines.append(f"  - {col.name}: {col.type} nullable={col.nullable} pk={col.primary_key} index={col.index} unique={col.unique}")
        (out_dir / "sqlalchemy_model_inventory.txt").write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        (out_dir / "sqlalchemy_model_inventory_error.txt").write_text(str(exc), encoding="utf-8")

    # Alembic state if run from repo root or backend.
    candidates = [start_dir / "backend" / "amodb" / "alembic.ini", start_dir / "amodb" / "alembic.ini"]
    ini = next((p for p in candidates if p.exists()), None)
    if ini:
        cwd = ini.parent.parent if ini.parent.name == "amodb" else start_dir
        run_optional(["alembic", "-c", str(ini), "heads"], cwd, out_dir / "alembic_heads.txt")
        run_optional(["alembic", "-c", str(ini), "current"], cwd, out_dir / "alembic_current.txt")
        run_optional(["alembic", "-c", str(ini), "history", "--verbose"], cwd, out_dir / "alembic_history_verbose.txt")

    zip_path = out_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in out_dir.rglob("*"):
            zf.write(path, path.relative_to(out_dir.parent))

    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
