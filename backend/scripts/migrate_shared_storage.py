from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# The migration imports tenant models but must not install HTTP route overrides.
os.environ.setdefault("AMO_INSTALL_SHARED_STORAGE_ROUTE_HARDENING", "false")

from sqlalchemy.orm import Session

from amodb import storage
from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.procurement import document_models as procurement_models
from amodb.apps.reliability import models as reliability_models
from amodb.apps.training import models as training_models
from amodb.database import WriteSessionLocal


@dataclass(frozen=True)
class Candidate:
    kind: str
    row: Any
    uri_attr: str
    source: Path
    key: str
    content_type: str | None
    expected_sha256: str | None


def _legacy_root() -> Path:
    return Path(os.getenv("AMO_LEGACY_UPLOAD_ROOT", os.getenv("AMO_STORAGE_LOCAL_ROOT", "/srv/amo/uploads"))).resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str | None, fallback: str) -> str:
    name = Path(str(value or fallback)).name.strip()
    return storage.normalise_key(name or fallback)


def _candidate(
    *,
    kind: str,
    row: Any,
    uri_attr: str,
    key: str,
    content_type: str | None = None,
    expected_sha256: str | None = None,
) -> Candidate | None:
    raw = str(getattr(row, uri_attr, "") or "").strip()
    if not raw or raw.startswith("s3://"):
        return None
    source = Path(raw).resolve()
    return Candidate(
        kind=kind,
        row=row,
        uri_attr=uri_attr,
        source=source,
        key=storage.normalise_key(key),
        content_type=content_type,
        expected_sha256=(str(expected_sha256).strip().lower() if expected_sha256 else None),
    )


def _collect(db: Session) -> list[Candidate]:
    candidates: list[Candidate] = []

    for row in db.query(account_models.AMOAsset).filter(account_models.AMOAsset.storage_path.isnot(None)).yield_per(200):
        item = _candidate(
            kind="amo_asset",
            row=row,
            uri_attr="storage_path",
            key=f"amo-assets/{row.amo_id}/{row.id}/{_safe_name(row.original_filename, str(row.id))}",
            content_type=row.content_type,
            expected_sha256=row.sha256,
        )
        if item:
            candidates.append(item)

    for row in db.query(training_models.TrainingFile).filter(training_models.TrainingFile.storage_path.isnot(None)).yield_per(200):
        suffix = "".join(Path(row.original_filename or "evidence.bin").suffixes)[-20:]
        item = _candidate(
            kind="training",
            row=row,
            uri_attr="storage_path",
            key=f"training/{row.amo_id}/{row.owner_user_id}/{row.id}{suffix}",
            content_type=row.content_type,
            expected_sha256=row.sha256,
        )
        if item:
            candidates.append(item)

    for row in db.query(procurement_models.ProcurementDocument).filter(procurement_models.ProcurementDocument.stored_path.isnot(None)).yield_per(200):
        entity_type = str(getattr(getattr(row, "entity_type", None), "value", row.entity_type or "record")).lower()
        item = _candidate(
            kind="procurement",
            row=row,
            uri_attr="stored_path",
            key=f"procurement-documents/{row.amo_id}/{entity_type}/{row.entity_id}/{row.id}_{_safe_name(row.original_filename, str(row.id))}",
            content_type=row.mime_type,
            expected_sha256=row.sha256,
        )
        if item:
            candidates.append(item)

    for row in db.query(fleet_models.AircraftDocument).filter(fleet_models.AircraftDocument.file_storage_path.isnot(None)).yield_per(200):
        aircraft = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.serial_number == row.aircraft_serial_number).first()
        if aircraft is None:
            continue
        item = _candidate(
            kind="aircraft_document",
            row=row,
            uri_attr="file_storage_path",
            key=f"aircraft-documents/{aircraft.amo_id}/{row.aircraft_serial_number}/{row.id}/{_safe_name(row.file_original_name, str(row.id))}",
            content_type=row.file_content_type,
        )
        if item:
            candidates.append(item)

    for row in db.query(reliability_models.EhmRawLog).filter(reliability_models.EhmRawLog.storage_path.isnot(None)).yield_per(200):
        suffix = Path(row.original_filename or "ehm.log").suffix or ".log"
        item = _candidate(
            kind="ehm",
            row=row,
            uri_attr="storage_path",
            key=f"ehm/{row.amo_id}/{row.aircraft_serial_number}/{row.engine_position}/{row.id}{suffix}",
            content_type=row.content_type,
            expected_sha256=row.sha256_hash,
        )
        if item:
            candidates.append(item)

    return candidates


def migrate(*, dry_run: bool, strict: bool, delete_source: bool, limit: int | None) -> int:
    storage.validate_storage_configuration(require_shared=True)
    root = _legacy_root()
    db = WriteSessionLocal()
    migrated = 0
    skipped = 0
    failed = 0
    try:
        candidates = _collect(db)
        if limit is not None:
            candidates = candidates[: max(0, limit)]
        print(f"legacy_root={root}")
        print(f"candidates={len(candidates)} dry_run={dry_run} strict={strict} delete_source={delete_source}")

        for item in candidates:
            if not _inside(item.source, root):
                failed += 1
                print(f"FAIL {item.kind} {getattr(item.row, 'id', '?')}: path outside legacy root: {item.source}")
                if strict:
                    raise RuntimeError("Legacy upload path is outside configured migration root")
                continue
            if not item.source.is_file():
                failed += 1
                print(f"FAIL {item.kind} {getattr(item.row, 'id', '?')}: file missing: {item.source}")
                if strict:
                    raise FileNotFoundError(str(item.source))
                continue
            if item.expected_sha256:
                actual = _sha256(item.source)
                if actual.lower() != item.expected_sha256:
                    failed += 1
                    print(f"FAIL {item.kind} {getattr(item.row, 'id', '?')}: checksum mismatch")
                    if strict:
                        raise RuntimeError(f"Checksum mismatch for {item.source}")
                    continue

            if dry_run:
                skipped += 1
                print(f"DRY {item.kind} {getattr(item.row, 'id', '?')}: {item.source} -> {item.key}")
                continue

            stored = storage.put_file(item.source, key=item.key, content_type=item.content_type)
            setattr(item.row, item.uri_attr, stored.uri)
            db.add(item.row)
            try:
                db.commit()
            except Exception:
                db.rollback()
                try:
                    storage.delete(stored.uri)
                except Exception:
                    pass
                failed += 1
                print(f"FAIL {item.kind} {getattr(item.row, 'id', '?')}: database update failed")
                if strict:
                    raise
                continue

            migrated += 1
            print(f"OK   {item.kind} {getattr(item.row, 'id', '?')}: {stored.uri}")
            if delete_source:
                item.source.unlink(missing_ok=True)

        print(f"summary migrated={migrated} dry_run_only={skipped} failed={failed}")
        return 1 if failed and strict else 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Move legacy node-local portal files into configured shared S3-compatible storage and rewrite authoritative DB pointers.")
    parser.add_argument("--apply", action="store_true", help="Perform uploads and database pointer updates. Default is dry-run.")
    parser.add_argument("--strict", action="store_true", help="Stop on missing, unsafe, checksum-mismatched or failed records.")
    parser.add_argument("--delete-source", action="store_true", help="Delete a legacy local file only after its database pointer is committed to shared storage.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of candidate records to inspect/migrate.")
    args = parser.parse_args()
    if args.delete_source and not args.apply:
        parser.error("--delete-source requires --apply")
    return migrate(dry_run=not args.apply, strict=args.strict, delete_source=args.delete_source, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
