"""Backfill approved tenant-local QMS/DMS/Manuals binaries into S3.

Dry-run by default. Requires explicit --apply and tenant ID, an approved
byte allocation, a backup, and AMO_STORAGE_BACKEND=s3. Copies are checked
against the regulatory checksum before any retained reference is changed;
the original file is never deleted. Run separately on each historical volume.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session
from amodb import storage as shared_storage
from amodb.database import WriteSessionLocal
from amodb.apps.doc_control.evidence_models import DocumentEvidenceAsset
from amodb.apps.doc_control.records_vault_models import TenantRecordAsset
from amodb.apps.doc_control.knowledge_models import DocumentationRecord
from amodb.apps.quality.audit_evidence_models import QualityAuditEvidenceArtifact
from amodb.apps.quality.audit_guest_document_models import QualityAuditDocumentSubmission
from amodb.apps.quality.audit_report_composition_models import QualityAuditReportArtifact
from amodb.apps.manuals import models as manuals_models
from amodb.apps.platform import storage_quota_upload, storage_quota_service


@dataclass(frozen=True)
class Source:
    kind: str
    model: type
    column: str
    tenant_column: str
    root: Path
    mime_column: str


SOURCES = (
    Source("dms-evidence", DocumentEvidenceAsset, "storage_path", "tenant_id",
           Path(os.getenv("DOCUMENT_EVIDENCE_DIR", "uploads/document-control-evidence")).resolve(), "mime_type"),
    Source("dms-record-vault", TenantRecordAsset, "storage_path", "tenant_id",
           Path(os.getenv("DOCUMENT_RECORD_VAULT_DIR", "uploads/document-record-vault")).resolve(), "mime_type"),
    Source("documentation-generated-records", DocumentationRecord, "artifact_storage_path", "tenant_id",
           Path(os.getenv("DOCUMENT_RECORD_DIR", "uploads/documentation-records")).resolve(), "artifact_mime_type"),
    Source("qms-checklist-evidence", QualityAuditEvidenceArtifact, "file_ref", "amo_id",
           Path(os.getenv("QMS_AUDIT_EVIDENCE_DIR", "uploads/qms-audit-evidence")).resolve(), "content_type"),
    Source("qms-guest-documents", QualityAuditDocumentSubmission, "storage_ref", "amo_id",
           Path(os.getenv("QMS_AUDIT_GUEST_DOCUMENT_DIR", "uploads/qms-audit-guest-documents")).resolve(), "content_type"),
    Source("qms-generated-reports", QualityAuditReportArtifact, "storage_ref", "amo_id",
           Path(os.getenv("QMS_GENERATED_AUDIT_REPORT_DIR", "uploads/qms-generated-audit-reports")).resolve(), "content_type"),
    Source("manuals-originals", manuals_models.ManualRevision, "source_storage_path", "",
           Path(os.getenv("MANUAL_UPLOAD_DIR", "uploads/manuals")).resolve(), "source_mime_type"),
)


def resolve_local(source: Source, value: str) -> Path:
    if not value or value.startswith("s3://"):
        raise ValueError("Already migrated or missing")
    raw = Path(value)
    path = (raw if raw.is_absolute() else source.root / raw).resolve()
    if source.root not in path.parents or not path.is_file():
        raise ValueError("Legacy file not found within its approved tenant storage root")
    return path


def digest_file(path: Path) -> tuple[int, str]:
    hash_value = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while part := source.read(1024 * 1024):
            hash_value.update(part)
            size += len(part)
    return size, hash_value.hexdigest()


def scan_source(db: Session, source: Source, tenant_id: str, *, limit: int):
    model = source.model
    column = getattr(model, source.column)
    q = db.query(model).filter(column.isnot(None), ~column.like("s3://%"))
    if source.kind == "manuals-originals":
        q = q.join(manuals_models.Manual, model.manual_id == manuals_models.Manual.id).join(
            manuals_models.Tenant, manuals_models.Manual.tenant_id == manuals_models.Tenant.id,
        ).filter(manuals_models.Tenant.amo_id == tenant_id)
    else:
        q = q.filter(getattr(model, source.tenant_column) == tenant_id)
    return q.order_by(model.id).limit(limit).all()


def migrate_one(db: Session, *, source: Source, tenant_id: str, row, apply: bool) -> dict:
    reference = str(getattr(row, source.column))
    try:
        source_file = resolve_local(source, reference)
        size, digest = digest_file(source_file)
        expected = str(getattr(row, "sha256", None) or getattr(row, "source_sha256", None) or getattr(row, "artifact_sha256", None) or "").lower()
        if expected and digest != expected:
            raise ValueError("Stored source SHA-256 differs from the authoritative database checksum")
        declared = getattr(row, "size_bytes", None)
        if declared is not None and int(declared) != size:
            raise ValueError("Stored source size differs from the authoritative record")
    except (OSError, ValueError) as error:
        return {"kind": source.kind, "record_id": str(row.id), "status": "BLOCKED", "reason": str(error)}

    key = f"legacy-backfill/{tenant_id}/{source.kind}/{row.id}/{re.sub(r'[^A-Za-z0-9._-]', '_', source_file.name)}"
    result = {"kind": source.kind, "record_id": str(row.id), "status": "VERIFIED_LOCAL",
              "size_bytes": size, "sha256": digest}
    if not apply:
        return result
    operation_id = f"legacy-backfill:{source.kind}:{row.id}"
    from amodb.apps.platform.storage_quota_models import TenantStorageReservation
    earlier = db.query(TenantStorageReservation).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.idempotency_key == operation_id,
    ).one_or_none()
    # An interrupted backfill may return an already-finalized, immutable S3
    # receipt. Never delete that established object if this run's verification
    # fails; it can still be referenced by another committed record.
    was_committed = earlier is not None and earlier.state == "FINALIZED"
    persisted = storage_quota_upload.put_local_file(
        db, tenant_id=tenant_id, key=key, path=source_file,
        content_type=getattr(row, source.mime_column, None),
        operation_id=operation_id,
    )
    # Read independently via the public adapter before changing legal references.
    try:
        remote_copy = shared_storage.materialize(persisted.uri)
        remote_size, remote_hash = digest_file(remote_copy)
        if remote_size != size or remote_hash != digest:
            raise IOError("Restored object checksum failed; original reference remains unchanged")
        setattr(row, source.column, persisted.uri)
        db.flush()
    except Exception:
        if not was_committed:
            try:
                shared_storage.delete(persisted.uri)
            except Exception:
                pass
        raise
    result["status"] = "MIGRATED_AND_VERIFIED"
    result["object_uri"] = persisted.uri
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", args.tenant_id):
        parser.error("Valid tenant UUID/ID required")
    if not 1 <= args.limit <= 10000:
        parser.error("--limit must be between 1 and 10000")
    if args.apply and not shared_storage.shared_storage_enabled():
        parser.error("Shared S3 storage must be configured before applying a backfill")
    failures = 0
    inspected = 0
    migrated = 0
    with WriteSessionLocal() as db:
        if args.apply:
            account = storage_quota_service.read_quota(db, args.tenant_id)
            if not account["quota_bytes"] or account["integrity_state"] != "OK":
                parser.error("An approved, reconciled byte quota is required before backfill")
        for source in SOURCES:
            rows = scan_source(db, source, args.tenant_id, limit=args.limit)
            for row in rows:
                inspected += 1
                try:
                    result = migrate_one(db, source=source, tenant_id=args.tenant_id,
                                         row=row, apply=args.apply)
                    if args.apply and result["status"] == "MIGRATED_AND_VERIFIED":
                        db.commit()
                        migrated += 1
                    elif result["status"] == "BLOCKED":
                        db.rollback()
                        failures += 1
                except Exception as exc:
                    db.rollback()
                    failures += 1
                    result = {"kind": source.kind, "record_id": str(row.id),
                              "status": "FAILED", "reason": type(exc).__name__}
                print(json.dumps(result, sort_keys=True))
        print(json.dumps({"tenant_id": args.tenant_id, "inspected": inspected,
                          "migrated": migrated, "blocked_or_failed": failures,
                          "dry_run": not args.apply}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
