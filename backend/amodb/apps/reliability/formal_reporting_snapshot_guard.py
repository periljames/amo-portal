from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import formal_reporting as core

_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_EXCLUDED_PREFIXES = (
    "reliability_formal_",
    "reliability_regulatory_",
)
_EXCLUDED_TABLES = {
    "reliability_reporting_schedule",
    "reliability_amp_recommendations",
}


def lock_snapshot_sources(db: Session) -> list[str]:
    """Serialize a PostgreSQL formal-report freeze against authoritative writes.

    The report cutoff is assigned *after* these SHARE locks are acquired. Any
    writer already in flight must therefore commit before the cutoff is taken
    and becomes visible to the snapshot; any writer starting afterwards waits
    until the report freeze commits and is necessarily post-cutoff. This keeps
    frozen source identities and the calculation snapshot on one transaction
    boundary without introducing a second copy/calculation service.

    SQLite remains available for isolated unit tests and does not support table
    locks, so no locking statement is issued outside PostgreSQL.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return []

    candidates = list(db.execute(text("""
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = current_schema()
          AND (
            tablename LIKE 'reliability_%'
            OR tablename IN ('aircraft_utilization_daily', 'aircraft')
          )
        ORDER BY tablename
    """)).scalars())
    tables = [
        name
        for name in candidates
        if _SAFE_IDENTIFIER.fullmatch(str(name))
        and str(name) not in _EXCLUDED_TABLES
        and not any(str(name).startswith(prefix) for prefix in _EXCLUDED_PREFIXES)
    ]
    if not tables:
        return []

    quoted = ", ".join(f'"{name}"' for name in tables)
    db.execute(text(f"LOCK TABLE {quoted} IN SHARE MODE"))
    return tables


def freeze_report(db: Session, report, user, payload):
    lock_snapshot_sources(db)
    return _ORIGINAL_FREEZE(db, report, user, payload)


_ORIGINAL_FREEZE = core._freeze_report


def apply() -> None:
    if getattr(core, "_formal_snapshot_guard_applied", False):
        return
    core._freeze_report = freeze_report
    core._formal_snapshot_guard_applied = True
