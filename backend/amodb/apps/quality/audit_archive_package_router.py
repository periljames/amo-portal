from __future__ import annotations

import json
import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from amodb.apps.audit import models as audit_models
from amodb.database import get_read_db, get_write_db
from amodb.user_id import generate_user_id

from .audit_archive_governance_models import (
    QualityAuditArchiveManifest,
    QualityAuditArchiveManifestItem,
    QualityAuditDispositionEvent,
)
from .audit_archive_governance_router import (
    DispositionExecute,
    _active_holds,
    _audit,
    _build_inventory,
    _canonical_hash,
    _inventory_hash,
    _latest_manifest,
    _latest_policy,
    _manifest_dict,
    _policy_dict,
    _retention_start,
    _utcnow,
)
from .audit_closure_models import QualityAuditClosureState
from .router import AUDIT_REPORT_DIR
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)


router = APIRouter(tags=["Quality audit archive package"])
ARCHIVE_PACKAGE_DIR = AUDIT_REPORT_DIR.parent / "audit_archives"
ARCHIVE_TRANSFER_DIR = AUDIT_REPORT_DIR.parent / "audit_archive_transfers"
ARCHIVE_DISPOSITION_DIR = AUDIT_REPORT_DIR.parent / "audit_archive_disposed"


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned[:96] or "audit"


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path(root: Path, value: str | Path) -> Path:
    base = root.resolve()
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Audit archive package path escaped controlled Quality storage.") from exc
    return candidate


def _zip_json(handle: zipfile.ZipFile, name: str, value: Any) -> None:
    payload = json.dumps(jsonable_encoder(value), sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    handle.writestr(info, payload)


def _timeline(db: Session, *, amo_id: str, audit_id: uuid.UUID, inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entity_ids = {str(audit_id), *(str(item["authoritative_record_id"]) for item in inventory)}
    rows = db.query(audit_models.AuditEvent).filter(
        audit_models.AuditEvent.amo_id == amo_id,
        audit_models.AuditEvent.entity_id.in_(entity_ids),
    ).order_by(audit_models.AuditEvent.occurred_at.asc(), audit_models.AuditEvent.created_at.asc()).limit(10000).all()
    return [
        {
            "id": str(row.id),
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "action": row.action,
            "actor_user_id": row.actor_user_id,
            "correlation_id": row.correlation_id,
            "occurred_at": row.occurred_at or row.created_at,
            "metadata": row.metadata_json or {},
        }
        for row in rows
    ]


def _package_indexes(inventory: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "scope-criteria.json": [],
        "preparation/index.json": [],
        "checklist/index.json": [],
        "findings/index.json": [],
        "report/index.json": [],
        "signatures/index.json": [],
        "closing-meeting/index.json": [],
        "cars/index.json": [],
    }
    for item in inventory:
        item_type = str(item.get("item_type") or "")
        if item_type == "AUDIT":
            buckets["scope-criteria.json"].append(item)
        elif item_type.startswith("PREPARATION_"):
            buckets["preparation/index.json"].append(item)
        elif item_type == "CHECKLIST_EXECUTION":
            buckets["checklist/index.json"].append(item)
        elif item_type == "FINDING":
            buckets["findings/index.json"].append(item)
        elif item_type == "REPORT_REVISION":
            buckets["report/index.json"].append(item)
        elif item_type == "SIGNATURE_EVIDENCE":
            buckets["signatures/index.json"].append(item)
        elif item_type == "ASSURANCE_ARTIFACT":
            buckets["closing-meeting/index.json"].append(item)
        elif item_type == "CAR":
            buckets["cars/index.json"].append(item)
    return buckets


def _render_package(
    path: Path,
    *,
    manifest_payload: dict[str, Any],
    manifest_sha256: str,
    inventory: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    indexes = _package_indexes(inventory)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        _zip_json(archive, "manifest.json", {**manifest_payload, "manifest_sha256": manifest_sha256})
        for name, items in sorted(indexes.items()):
            _zip_json(archive, name, {"items": items, "item_count": len(items)})
        _zip_json(archive, "timeline.json", {"items": timeline, "event_count": len(timeline)})
    return path.stat().st_size, _sha256(path)


def _latest_execution(db: Session, *, amo_id: str, audit_id: uuid.UUID, manifest_id: str | None = None) -> QualityAuditDispositionEvent | None:
    query = db.query(QualityAuditDispositionEvent).filter(
        QualityAuditDispositionEvent.amo_id == amo_id,
        QualityAuditDispositionEvent.audit_id == audit_id,
        QualityAuditDispositionEvent.event_type == "EXECUTED",
    )
    if manifest_id:
        query = query.filter(QualityAuditDispositionEvent.manifest_id == manifest_id)
    return query.order_by(QualityAuditDispositionEvent.created_at.desc()).first()


def _package_manifest_dict(db: Session, row: QualityAuditArchiveManifest) -> dict[str, Any]:
    result = _manifest_dict(row)
    executed = _latest_execution(db, amo_id=row.amo_id, audit_id=row.audit_id, manifest_id=row.id)
    available = False
    if row.package_file_ref and row.package_sha256 and executed is None:
        try:
            package_path = _safe_path(ARCHIVE_PACKAGE_DIR, row.package_file_ref)
            available = package_path.is_file() and _sha256(package_path) == row.package_sha256
        except HTTPException:
            available = False
    result.update({
        "package_filename": row.package_filename,
        "package_content_type": row.package_content_type,
        "package_size_bytes": row.package_size_bytes,
        "package_sha256": row.package_sha256,
        "package_available": available,
    })
    return result


@router.get("/audits/{audit_id}/archive-governance")
def get_archive_governance_with_package(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    manifest = _latest_manifest(db, amo_id=ctx.amo_id, audit_id=audit_id)
    holds = _active_holds(db, amo_id=ctx.amo_id, audit_id=audit_id)
    disposition = db.query(QualityAuditDispositionEvent).filter(
        QualityAuditDispositionEvent.amo_id == ctx.amo_id,
        QualityAuditDispositionEvent.audit_id == audit_id,
    ).order_by(QualityAuditDispositionEvent.created_at.desc()).first()
    now = _utcnow()
    return {
        "policy": _policy_dict(_latest_policy(db, ctx.amo_id)),
        "manifest": _package_manifest_dict(db, manifest) if manifest else None,
        "active_holds": [
            {
                "hold_key": hold.hold_key,
                "reason": hold.reason,
                "governing_basis": hold.governing_basis,
                "created_at": hold.created_at,
            }
            for hold in holds
        ],
        "disposition": {
            "event_type": disposition.event_type,
            "disposition_mode": disposition.disposition_mode,
            "inventory_sha256": disposition.inventory_sha256,
            "package_sha256": disposition.package_sha256,
            "action_ref": disposition.action_ref,
            "reason": disposition.reason,
            "created_at": disposition.created_at,
        } if disposition else None,
        "retention_due": bool(manifest and manifest.retention_due_at and manifest.retention_due_at <= now),
    }


@router.post("/audits/{audit_id}/archive-manifests/generate", status_code=status.HTTP_201_CREATED)
def generate_archive_manifest_with_package(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    policy = _latest_policy(db, ctx.amo_id)
    if policy is None:
        raise HTTPException(status_code=409, detail="Audit retention policy is not configured for this tenant.")
    closure = db.query(QualityAuditClosureState).filter(
        QualityAuditClosureState.amo_id == ctx.amo_id,
        QualityAuditClosureState.audit_id == audit_id,
    ).first()
    if closure is None:
        raise HTTPException(status_code=409, detail="Audit closure state is required before archive generation.")
    if closure.follow_up_status != "COMPLETE":
        raise HTTPException(status_code=409, detail="Assurance follow-up must be complete before the audit package can be archived.")

    retention_start = _retention_start(closure, policy)
    retention_due = None if policy.indefinite else retention_start + __import__("datetime").timedelta(days=int(policy.duration_days or 0))
    latest = db.query(QualityAuditArchiveManifest).filter(
        QualityAuditArchiveManifest.amo_id == ctx.amo_id,
        QualityAuditArchiveManifest.audit_id == audit_id,
    ).order_by(QualityAuditArchiveManifest.manifest_version.desc()).with_for_update().first()
    version = (latest.manifest_version + 1) if latest else 1
    inventory = _build_inventory(db, amo_id=ctx.amo_id, audit=audit)
    manifest_id = generate_user_id()
    manifest_payload = {
        "manifest_id": manifest_id,
        "tenant_id": ctx.amo_id,
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
        "manifest_version": version,
        "retention_policy_revision_id": policy.id,
        "retention_class": policy.retention_class,
        "retention_start_at": retention_start,
        "retention_due_at": retention_due,
        "items": inventory,
    }
    manifest_digest = _canonical_hash(manifest_payload)
    filename = f"{_safe_name(audit.audit_ref or str(audit.id))}-archive-v{version}.zip"
    path = (ARCHIVE_PACKAGE_DIR / ctx.amo_id / str(audit.id) / filename).resolve()
    _safe_path(ARCHIVE_PACKAGE_DIR, path)
    package_size = 0
    package_digest = ""
    try:
        package_size, package_digest = _render_package(
            path,
            manifest_payload=manifest_payload,
            manifest_sha256=manifest_digest,
            inventory=inventory,
            timeline=_timeline(db, amo_id=ctx.amo_id, audit_id=audit.id, inventory=inventory),
        )
        manifest = QualityAuditArchiveManifest(
            id=manifest_id,
            amo_id=ctx.amo_id,
            audit_id=audit.id,
            manifest_version=version,
            retention_policy_revision_id=policy.id,
            retention_class=policy.retention_class,
            retention_start_at=retention_start,
            retention_due_at=retention_due,
            manifest_json=jsonable_encoder(manifest_payload),
            manifest_sha256=manifest_digest,
            item_count=len(inventory),
            package_file_ref=str(path),
            package_filename=filename,
            package_content_type="application/zip",
            package_size_bytes=package_size,
            package_sha256=package_digest,
            created_by_user_id=ctx.user_id,
        )
        db.add(manifest)
        for item in inventory:
            db.add(QualityAuditArchiveManifestItem(
                amo_id=ctx.amo_id,
                audit_id=audit.id,
                manifest_id=manifest_id,
                item_type=item["item_type"],
                authoritative_record_id=item["authoritative_record_id"],
                revision_ref=item["revision_ref"],
                source_system=item["source_system"],
                content_hash=item["content_hash"],
                retention_role=item["retention_role"],
                metadata_json=item["metadata"],
            ))
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    loaded = db.query(QualityAuditArchiveManifest).options(selectinload(QualityAuditArchiveManifest.items)).filter(
        QualityAuditArchiveManifest.id == manifest_id,
    ).one()
    return _package_manifest_dict(db, loaded)


@router.get("/audits/{audit_id}/archive-manifests/{manifest_id}/download")
def download_archive_package(
    audit_id: uuid.UUID,
    manifest_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> Response:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    manifest = db.query(QualityAuditArchiveManifest).filter(
        QualityAuditArchiveManifest.amo_id == ctx.amo_id,
        QualityAuditArchiveManifest.audit_id == audit_id,
        QualityAuditArchiveManifest.id == manifest_id,
    ).first()
    if manifest is None:
        raise HTTPException(status_code=404, detail="Archive manifest not found.")
    if _latest_execution(db, amo_id=ctx.amo_id, audit_id=audit_id, manifest_id=manifest.id) is not None:
        raise HTTPException(status_code=410, detail="This archive package has completed controlled disposition and is no longer available from the active Quality store.")
    if not manifest.package_file_ref or not manifest.package_sha256:
        raise HTTPException(status_code=409, detail="This manifest predates controlled archive-package generation. Generate a new manifest version.")
    path = _safe_path(ARCHIVE_PACKAGE_DIR, manifest.package_file_ref)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Archive package file is missing from controlled storage.")
    if _sha256(path) != manifest.package_sha256:
        raise HTTPException(status_code=409, detail="Archive package no longer matches its governed SHA-256 checksum.")
    return FileResponse(path, media_type=manifest.package_content_type or "application/zip", filename=manifest.package_filename or path.name)


@router.post("/audits/{audit_id}/archive-manifests/{manifest_id}/dispose")
def execute_package_disposition(
    audit_id: uuid.UUID,
    manifest_id: str,
    payload: DispositionExecute,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    policy = _latest_policy(db, ctx.amo_id)
    if policy is None:
        raise HTTPException(status_code=409, detail="Audit retention policy is not configured.")
    assert_quality_permission(db, ctx, policy.approving_capability)
    if policy.indefinite or policy.disposition_mode == "NO_DISPOSITION":
        raise HTTPException(status_code=409, detail="Current retention policy does not permit disposition.")
    manifest = db.query(QualityAuditArchiveManifest).options(selectinload(QualityAuditArchiveManifest.items)).filter(
        QualityAuditArchiveManifest.amo_id == ctx.amo_id,
        QualityAuditArchiveManifest.audit_id == audit_id,
        QualityAuditArchiveManifest.id == manifest_id,
    ).first()
    if manifest is None:
        raise HTTPException(status_code=404, detail="Archive manifest not found.")
    if manifest.retention_due_at is None or manifest.retention_due_at > _utcnow():
        raise HTTPException(status_code=409, detail="Archive retention is not yet due.")
    holds = _active_holds(db, amo_id=ctx.amo_id, audit_id=audit_id)
    if holds:
        raise HTTPException(status_code=409, detail={"message": "Active legal hold blocks disposition.", "holds": [hold.hold_key for hold in holds]})
    if policy.review_before_disposition:
        latest_review = db.query(QualityAuditDispositionEvent).filter(
            QualityAuditDispositionEvent.amo_id == ctx.amo_id,
            QualityAuditDispositionEvent.audit_id == audit_id,
            QualityAuditDispositionEvent.manifest_id == manifest.id,
            QualityAuditDispositionEvent.event_type.in_(["APPROVED", "REJECTED"]),
        ).order_by(QualityAuditDispositionEvent.created_at.desc()).first()
        if latest_review is None or latest_review.event_type != "APPROVED":
            raise HTTPException(status_code=409, detail="Approved disposition review is required by policy before execution.")
    if _latest_execution(db, amo_id=ctx.amo_id, audit_id=audit_id, manifest_id=manifest.id) is not None:
        raise HTTPException(status_code=409, detail="Disposition has already been executed for this manifest.")
    if not manifest.package_file_ref or not manifest.package_sha256:
        raise HTTPException(status_code=409, detail="Controlled disposition requires a generated archive package with a governed checksum.")

    source = _safe_path(ARCHIVE_PACKAGE_DIR, manifest.package_file_ref)
    if not source.is_file() or _sha256(source) != manifest.package_sha256:
        raise HTTPException(status_code=409, detail="Archive package is missing or no longer matches its governed checksum.")

    action_ref: str
    moved_path: Path
    if policy.disposition_mode == "TRANSFER_PACKAGE":
        moved_path = (ARCHIVE_TRANSFER_DIR / ctx.amo_id / str(audit_id) / (manifest.package_filename or source.name)).resolve()
        _safe_path(ARCHIVE_TRANSFER_DIR, moved_path)
        moved_path.parent.mkdir(parents=True, exist_ok=True)
        if moved_path.exists():
            raise HTTPException(status_code=409, detail="Controlled transfer destination already contains this archive package.")
        shutil.move(str(source), str(moved_path))
        if _sha256(moved_path) != manifest.package_sha256:
            shutil.move(str(moved_path), str(source))
            raise HTTPException(status_code=409, detail="Transferred archive package failed checksum verification.")
        action_ref = str(moved_path)
    else:
        moved_path = (ARCHIVE_DISPOSITION_DIR / ctx.amo_id / str(audit_id) / f"{manifest.id}-{manifest.package_filename or source.name}").resolve()
        _safe_path(ARCHIVE_DISPOSITION_DIR, moved_path)
        moved_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, moved_path)
        action_ref = f"disposed:{moved_path.name}"

    row = QualityAuditDispositionEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        manifest_id=manifest.id,
        event_type="EXECUTED",
        disposition_mode=policy.disposition_mode,
        inventory_sha256=_inventory_hash(manifest),
        package_sha256=manifest.package_sha256,
        action_ref=action_ref,
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        if moved_path.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(moved_path), str(source))
        raise

    if policy.disposition_mode == "PRESERVE_METADATA_DELETE_PACKAGE":
        moved_path.unlink(missing_ok=True)
    return {
        "event_type": row.event_type,
        "disposition_mode": row.disposition_mode,
        "inventory_sha256": row.inventory_sha256,
        "package_sha256": row.package_sha256,
        "action_ref": row.action_ref,
        "created_at": row.created_at,
        "authoritative_records_deleted": False,
        "metadata_preserved": True,
    }
