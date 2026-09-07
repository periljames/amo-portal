from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import MetaData, Table, delete, inspect, select, text, tuple_, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb import storage
from amodb.database import Base

from . import models


logger = logging.getLogger(__name__)

RECYCLE_BIN_RETENTION_DAYS = 30

_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_LEGACY_QUALITY_STORAGE_ROOT = Path(__file__).resolve().parents[2] / "generated" / "quality"
_DELETE_BATCH_SIZE = 500
_SCHEMA_CACHE_KEY = "quality.audit_deletion.schema"

_PUBLIC_DELETE_FAILURE = (
    "The audit could not be deleted. No database records were changed. "
    "Try again; if the problem continues, contact an administrator."
)


class AuditDeletionError(RuntimeError):
    """Safe boundary error for a failed governed audit purge."""

    code = "AUDIT_DELETE_FAILED"
    public_message = _PUBLIC_DELETE_FAILURE


def recycle_bin_purge_at(deleted_at: datetime | None) -> datetime | None:
    """Return the governed purge deadline for a recycle-bin tombstone."""

    if deleted_at is None:
        return None
    value = deleted_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value + timedelta(days=RECYCLE_BIN_RETENTION_DAYS)


def recycle_bin_days_remaining(
    deleted_at: datetime | None,
    *,
    now: datetime | None = None,
) -> int | None:
    purge_at = recycle_bin_purge_at(deleted_at)
    if purge_at is None:
        return None
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (purge_at - clock).total_seconds())
    return int((seconds + 86_399) // 86_400)

_FILE_COLUMNS = {
    "file_ref",
    "storage_ref",
    "package_file_ref",
    "pack_storage_ref",
    "evidence_ref",
}
_CATEGORY_LABELS = {
    "findings": "Findings",
    "corrective_actions": "Corrective actions and CAR responses",
    "checklists": "Checklist records and execution history",
    "documents": "Uploaded documents and evidence",
    "meetings": "Meetings and participants",
    "notices": "Audit notices and delivery history",
    "reports": "Reports, signatures and assurance records",
    "access": "Auditee access grants and activity",
    "packages": "Archive packages and manifests",
    "workflow": "Preparation, closing and workflow records",
}


@dataclass(frozen=True)
class _ForeignKeyEdge:
    child_name: str
    local_columns: tuple[str, ...]
    remote_columns: tuple[str, ...]


@dataclass(frozen=True)
class _AuditSchema:
    """Request-local map of the modelled audit ownership graph.

    SQLAlchemy's Inspector issues a catalogue query for every
    ``get_foreign_keys`` call. The portal has hundreds of tables, so rebuilding
    the graph from the live catalogue made both deletion preview and purge
    unnecessarily slow. Application metadata is the authoritative schema map;
    only unmodelled legacy Quality tables need reflection.
    """

    available: frozenset[str]
    tables: dict[str, Any]
    cascade_children: dict[str, tuple[_ForeignKeyEdge, ...]]
    children: dict[str, frozenset[str]]


def _target_column(target_fullname: str) -> tuple[str, str] | None:
    parts = target_fullname.split(".")
    if len(parts) < 2:
        return None
    return parts[-2], parts[-1]


def _build_audit_schema(db: Session) -> _AuditSchema:
    bind = db.get_bind()
    available = frozenset(inspect(bind).get_table_names())
    tables: dict[str, Any] = {
        name: table
        for name in available
        if (table := Base.metadata.tables.get(name)) is not None
    }

    # Compatibility for a deployed legacy Quality table that predates its ORM
    # model. Do not reflect unrelated application tables during an audit purge.
    for table_name in sorted(available.difference(tables)):
        if table_name.startswith(("qms_", "quality_")):
            tables[table_name] = Table(table_name, MetaData(), autoload_with=bind)

    cascade_children: dict[str, list[_ForeignKeyEdge]] = defaultdict(list)
    children: dict[str, set[str]] = defaultdict(set)
    for child_name, table in tables.items():
        for constraint in table.foreign_key_constraints:
            targets = [_target_column(element.target_fullname) for element in constraint.elements]
            if not targets or any(target is None for target in targets):
                continue
            resolved_targets = [target for target in targets if target is not None]
            parent_names = {target[0] for target in resolved_targets}
            if len(parent_names) != 1:
                continue
            parent_name = next(iter(parent_names))
            if parent_name not in available or parent_name == child_name:
                continue
            local_columns = tuple(element.parent.name for element in constraint.elements)
            remote_columns = tuple(target[1] for target in resolved_targets)
            children[parent_name].add(child_name)
            if str(constraint.ondelete or "").upper() == "CASCADE":
                cascade_children[parent_name].append(
                    _ForeignKeyEdge(child_name, local_columns, remote_columns)
                )

    return _AuditSchema(
        available=available,
        tables=tables,
        cascade_children={
            parent: tuple(sorted(edges, key=lambda edge: (edge.child_name, edge.local_columns)))
            for parent, edges in cascade_children.items()
        },
        children={parent: frozenset(child_names) for parent, child_names in children.items()},
    )


def _audit_schema(db: Session) -> _AuditSchema:
    session_info = getattr(db, "info", None)
    if isinstance(session_info, dict):
        cached = session_info.get(_SCHEMA_CACHE_KEY)
        if isinstance(cached, _AuditSchema):
            return cached
    schema = _build_audit_schema(db)
    if isinstance(session_info, dict):
        session_info[_SCHEMA_CACHE_KEY] = schema
    return schema


def _category(table_name: str) -> str:
    name = table_name.lower()
    if "attachment" in name or "document" in name or "evidence" in name:
        return "documents"
    if "car" in name or "corrective" in name:
        return "corrective_actions"
    if "checklist" in name:
        return "checklists"
    if "finding" in name:
        return "findings"
    if "meeting" in name or "participant" in name or "presence" in name:
        return "meetings"
    if "notice" in name:
        return "notices"
    if "report" in name or "signature" in name or "assurance" in name or "webauthn" in name:
        return "reports"
    if "access" in name or "verification_token" in name:
        return "access"
    if "archive" in name or "authority_submission" in name:
        return "packages"
    return "workflow"


def _available_tables(db: Session) -> set[str]:
    return set(_audit_schema(db).available)


def _table(db: Session, table_name: str, *, schema: _AuditSchema | None = None) -> Any | None:
    return (schema or _audit_schema(db)).tables.get(table_name)


def _candidate_storage_refs(row: Any) -> set[str]:
    refs: set[str] = set()
    for key, value in dict(row).items():
        if key in _FILE_COLUMNS and isinstance(value, str) and value.strip():
            candidate = value.strip()
            if (
                candidate.startswith("s3://")
                or Path(candidate).is_absolute()
                or _WINDOWS_ABSOLUTE_PATH.match(candidate)
                or candidate.replace("\\", "/").startswith(("backend/amodb/generated/quality/", "amodb/generated/quality/"))
            ):
                refs.add(candidate)
    return refs


def _delete_owned_file(ref: str) -> None:
    if ref.startswith("s3://"):
        storage.delete(ref)
        return
    path = Path(ref).resolve()
    approved_roots = (storage.local_root(), _LEGACY_QUALITY_STORAGE_ROOT.resolve())
    if not any(path == root or root in path.parents for root in approved_roots):
        raise ValueError("Audit file is outside approved Quality storage roots")
    path.unlink(missing_ok=True)


def _row_key(table: Any, row: Any) -> tuple[Any, ...]:
    primary_key = list(table.primary_key.columns)
    if primary_key:
        return tuple(row[column.name] for column in primary_key)
    return tuple(sorted((str(key), repr(value)) for key, value in dict(row).items()))


def _inventory_delete_order(
    db: Session,
    inventory: dict[str, list[Any]],
    *,
    schema: _AuditSchema | None = None,
) -> list[str]:
    """Order owned tables child-first, including non-cascading cross-links.

    PostgreSQL implements foreign-key actions with triggers. Explicit ordering
    prevents a RESTRICT link between two audit-owned child tables from racing
    the parent audit's other cascade triggers.
    """
    nodes = set(inventory).difference({"qms_audits"})
    if not nodes:
        return []

    schema = schema or _audit_schema(db)
    children: dict[str, set[str]] = defaultdict(set)
    indegree = {table_name: 0 for table_name in nodes}
    for parent_name in nodes:
        for child_name in schema.children.get(parent_name, ()):
            if child_name not in nodes:
                continue
            if child_name not in children[parent_name]:
                children[parent_name].add(child_name)
                indegree[child_name] += 1

    ready = deque(sorted(table_name for table_name, degree in indegree.items() if degree == 0))
    parent_first: list[str] = []
    while ready:
        parent_name = ready.popleft()
        parent_first.append(parent_name)
        for child_name in sorted(children.get(parent_name, ())):
            indegree[child_name] -= 1
            if indegree[child_name] == 0:
                ready.append(child_name)

    if len(parent_first) != len(nodes):
        cycle = sorted(nodes.difference(parent_first))
        raise RuntimeError(
            "The audit was not deleted because its record dependency graph contains a cycle: "
            + ", ".join(cycle)
        )
    return list(reversed(parent_first))


def _delete_inventory_rows(
    db: Session,
    inventory: dict[str, list[Any]],
    *,
    schema: _AuditSchema | None = None,
) -> None:
    schema = schema or _audit_schema(db)
    for table_name in _inventory_delete_order(db, inventory, schema=schema):
        table = _table(db, table_name, schema=schema)
        rows = inventory.get(table_name, [])
        if table is None or not rows:
            continue
        primary_key = list(table.primary_key.columns)
        if not primary_key:
            raise RuntimeError(f"Audit-owned table {table_name} has no primary key")
        keys = [tuple(row[column.name] for column in primary_key) for row in rows]
        for offset in range(0, len(keys), _DELETE_BATCH_SIZE):
            batch = keys[offset:offset + _DELETE_BATCH_SIZE]
            if len(primary_key) == 1:
                condition = primary_key[0].in_([key[0] for key in batch])
            else:
                condition = tuple_(*primary_key).in_(batch)
            db.execute(delete(table).where(condition))


def _inventory_select_columns(schema: _AuditSchema, table_name: str) -> list[Any]:
    table = schema.tables[table_name]
    primary_key = list(table.primary_key.columns)
    if not primary_key:
        return list(table.columns)
    names = {column.name for column in primary_key}
    names.update(name for name in _FILE_COLUMNS if name in table.c)
    for edge in schema.cascade_children.get(table_name, ()):
        names.update(edge.remote_columns)
    return [column for column in table.columns if column.name in names]


def _audit_inventory(
    db: Session,
    *,
    audit: models.QMSAudit,
    schema: _AuditSchema | None = None,
) -> dict[str, list[Any]]:
    """Return every row removed by the audit's FK cascades plus owned CARs.

    Shared DMS source documents and checklist-memory rows use SET NULL/RESTRICT
    relationships and are intentionally not walked or deleted.
    """
    schema = schema or _audit_schema(db)
    available = schema.available

    inventory: dict[str, list[Any]] = defaultdict(list)
    seen: dict[str, set[tuple[Any, ...]]] = defaultdict(set)
    queue: deque[tuple[str, list[Any]]] = deque()

    def add_rows(table_name: str, rows: list[Any]) -> None:
        table = _table(db, table_name, schema=schema)
        if table is None:
            return
        fresh: list[Any] = []
        for row in rows:
            key = _row_key(table, row)
            if key in seen[table_name]:
                continue
            seen[table_name].add(key)
            inventory[table_name].append(row)
            fresh.append(row)
        if fresh:
            queue.append((table_name, fresh))

    audit_table = _table(db, "qms_audits", schema=schema)
    if audit_table is None:
        return {}
    root_row = db.execute(
        select(*_inventory_select_columns(schema, "qms_audits")).where(audit_table.c.id == audit.id)
    ).mappings().first()
    if root_row is None:
        return {}
    add_rows("qms_audits", [root_row])

    while queue:
        parent_name, parent_rows = queue.popleft()
        for edge in schema.cascade_children.get(parent_name, ()):
            child_name = edge.child_name
            local_columns = edge.local_columns
            remote_columns = edge.remote_columns
            child = _table(db, child_name, schema=schema)
            if child is None:
                continue
            values = [tuple(row[column] for column in remote_columns) for row in parent_rows]
            values = [value for value in values if all(part is not None for part in value)]
            if not values:
                continue
            if len(local_columns) == 1:
                condition = child.c[local_columns[0]].in_([value[0] for value in values])
            else:
                condition = tuple_(*(child.c[column] for column in local_columns)).in_(values)
            rows = list(db.execute(
                select(*_inventory_select_columns(schema, child_name)).where(condition)
            ).mappings())
            add_rows(child_name, rows)

        # quality_cars uses SET NULL so that findings may ordinarily be retained,
        # but a permanent audit purge owns and removes CARs originating from it.
        if parent_name == "qms_audit_findings" and "quality_cars" in available:
            quality_cars = _table(db, "quality_cars", schema=schema)
            if quality_cars is not None:
                finding_ids = [row["id"] for row in parent_rows]
                rows = list(db.execute(
                    select(*_inventory_select_columns(schema, "quality_cars")).where(
                        quality_cars.c.amo_id == audit.amo_id,
                        quality_cars.c.finding_id.in_(finding_ids),
                    )
                ).mappings())
                add_rows("quality_cars", rows)

    return dict(inventory)


def _impact_from_inventory(*, audit: models.QMSAudit, inventory: dict[str, list[Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    storage_refs: set[str] = set()
    for table_name, rows in inventory.items():
        if table_name != "qms_audits":
            counts[_category(table_name)] += len(rows)
        for row in rows:
            storage_refs.update(_candidate_storage_refs(row))

    storage_refs.update(value for value in (audit.report_file_ref, audit.checklist_file_ref) if value)
    groups = [
        {"key": key, "label": _CATEGORY_LABELS[key], "count": int(counts.get(key, 0))}
        for key in _CATEGORY_LABELS
        if counts.get(key, 0)
    ]
    record_count = 1 + sum(item["count"] for item in groups)
    return {
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "status": str(getattr(audit.status, "value", audit.status)),
        "groups": groups,
        "database_record_count": record_count,
        "managed_file_count": len(storage_refs),
        "controlled_dms_sources_preserved": True,
        "storage_refs": sorted(storage_refs),
    }


def build_audit_deletion_impact(db: Session, *, audit: models.QMSAudit) -> dict[str, Any]:
    started_at = perf_counter()
    schema = _audit_schema(db)
    impact = _impact_from_inventory(
        audit=audit,
        inventory=_audit_inventory(db, audit=audit, schema=schema),
    )
    logger.info(
        "Quality audit deletion impact prepared",
        extra={
            "audit_id": str(audit.id),
            "amo_id": str(audit.amo_id),
            "database_record_count": impact.get("database_record_count", 0),
            "managed_file_count": impact.get("managed_file_count", 0),
            "duration_ms": round((perf_counter() - started_at) * 1000, 1),
        },
    )
    return impact


def permanently_delete_audit(
    db: Session,
    *,
    audit: models.QMSAudit,
    actor_user_id: str,
) -> dict[str, Any]:
    started_at = perf_counter()
    audit_id = str(audit.id)
    amo_id = str(audit.amo_id)

    try:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("""
                    SELECT
                        set_config('app.tenant_id', :amo_id, true),
                        set_config('app.user_id', :actor_user_id, true),
                        set_config('app.qms_audit_purge_id', :audit_id, true),
                        set_config('app.qms_audit_purge_amo_id', :amo_id, true)
                """),
                {
                    "audit_id": audit_id,
                    "amo_id": amo_id,
                    "actor_user_id": str(actor_user_id),
                },
            )

        schema = _audit_schema(db)
        inventory = _audit_inventory(db, audit=audit, schema=schema)
        impact = _impact_from_inventory(audit=audit, inventory=inventory)
        refs = list(impact.pop("storage_refs", []))

        checklist_memory = _table(db, "quality_audit_checklist_memory", schema=schema)
        if checklist_memory is not None:
            db.execute(update(checklist_memory).where(
                checklist_memory.c.amo_id == audit.amo_id,
                checklist_memory.c.last_audit_id == audit.id,
            ).values(last_audit_id=None))

        _delete_inventory_rows(db, inventory, schema=schema)
        db.delete(audit)
        db.flush()
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Governed Quality audit database purge failed",
            extra={"audit_id": audit_id, "amo_id": amo_id},
        )
        raise AuditDeletionError(_PUBLIC_DELETE_FAILURE) from exc

    failed_refs: list[str] = []
    for ref in refs:
        try:
            _delete_owned_file(ref)
        except Exception:
            logger.exception("Unable to remove managed Quality audit object", extra={"audit_id": audit_id})
            failed_refs.append(ref)
    if failed_refs:
        db.rollback()
        raise AuditDeletionError(_PUBLIC_DELETE_FAILURE)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "Governed Quality audit purge commit failed",
            extra={"audit_id": audit_id, "amo_id": amo_id},
        )
        raise AuditDeletionError(_PUBLIC_DELETE_FAILURE) from exc
    impact["managed_files_deleted"] = len(refs)
    logger.info(
        "Governed Quality audit purge completed",
        extra={
            "audit_id": audit_id,
            "amo_id": amo_id,
            "database_record_count": impact.get("database_record_count", 0),
            "managed_file_count": len(refs),
            "duration_ms": round((perf_counter() - started_at) * 1000, 1),
        },
    )
    return impact
