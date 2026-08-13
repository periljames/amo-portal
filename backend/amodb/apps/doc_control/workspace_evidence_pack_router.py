from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import evidence_models as em
from .workspace_service import (
    audit,
    get_manual,
    get_profile,
    get_revision,
    require_control_user,
    require_manual_access,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Evidence Packs"])

MAX_PACK_FILE_BYTES = int(os.getenv("DOCUMENT_EVIDENCE_PACK_MAX_BYTES", str(250 * 1024 * 1024)))
MAX_PACK_ATTACHMENTS = int(os.getenv("DOCUMENT_EVIDENCE_PACK_MAX_ATTACHMENTS", "500"))
MAX_PACK_ROWS_PER_DATASET = int(os.getenv("DOCUMENT_EVIDENCE_PACK_MAX_ROWS", "10000"))


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.loads(json.dumps(value, default=str))
    return str(value)


def _serialize_row(row: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = exclude or set()
    output: dict[str, Any] = {}
    mapper = sa_inspect(row.__class__)
    for attr in mapper.column_attrs:
        key = attr.key
        if key in excluded:
            continue
        output[key] = _json_value(getattr(row, key, None))
    return output


def _bounded(rows: list[Any], *, dataset: str) -> list[Any]:
    if len(rows) > MAX_PACK_ROWS_PER_DATASET:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVIDENCE_PACK_DATASET_TOO_LARGE",
                "message": f"Evidence pack dataset {dataset} exceeds the synchronous row ceiling.",
                "dataset": dataset,
                "rows": len(rows),
                "limit": MAX_PACK_ROWS_PER_DATASET,
            },
        )
    return rows


def _write_json(archive: zipfile.ZipFile, path: str, value: Any) -> str:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    archive.writestr(path, payload)
    return hashlib.sha256(payload).hexdigest()


def _write_csv(archive: zipfile.ZipFile, path: str, rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    if rows:
        fields: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            safe: dict[str, Any] = {}
            for key in fields:
                value = row.get(key)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True, default=str)
                text_value = "" if value is None else str(value)
                if text_value.lstrip().startswith(("=", "+", "-", "@")):
                    text_value = "'" + text_value
                safe[key] = text_value
            writer.writerow(safe)
    payload = buffer.getvalue().encode("utf-8-sig")
    archive.writestr(path, payload)
    return hashlib.sha256(payload).hexdigest()


def _attachment_name(prefix: str, asset_id: str, filename: str) -> str:
    safe = Path(filename or "evidence").name.replace("/", "_").replace("\\", "_")
    return f"attachments/{prefix}/{asset_id}_{safe}"


def _read_verified_file(path_value: str, expected_sha256: str, *, label: str) -> bytes:
    path = Path(path_value).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=409,
            detail={"code": "EVIDENCE_PACK_FILE_MISSING", "message": f"Retained file is unavailable: {label}"},
        )
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if not expected_sha256 or actual.lower() != expected_sha256.lower():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVIDENCE_PACK_CHECKSUM_MISMATCH",
                "message": f"Retained file checksum does not match the controlled record: {label}",
                "expected_sha256": expected_sha256,
                "actual_sha256": actual,
            },
        )
    return content


def _manual_audit_rows(db: Session, *, tenant_id: str, manual_id: str) -> list[manual_models.ManualAuditLog]:
    # Audit entity IDs vary by lifecycle object, so retain direct document events
    # plus events whose diff references this manual. The latter is filtered in
    # Python because JSON shapes differ across older controlled event types.
    rows = (
        db.query(manual_models.ManualAuditLog)
        .filter(manual_models.ManualAuditLog.tenant_id == tenant_id)
        .order_by(manual_models.ManualAuditLog.at.asc(), manual_models.ManualAuditLog.id.asc())
        .limit(MAX_PACK_ROWS_PER_DATASET + 1)
        .all()
    )
    selected: list[manual_models.ManualAuditLog] = []
    for row in rows:
        if str(row.entity_id or "") == manual_id:
            selected.append(row)
            continue
        payload = row.diff_json or {}
        if manual_id in json.dumps(payload, default=str):
            selected.append(row)
    return _bounded(selected, dataset="audit_history")


def _datasets(db: Session, *, tenant_id: str, manual_id: str, revision_id: str | None) -> dict[str, list[Any]]:
    def query(model, *, revision_scoped: bool = True):
        q = db.query(model).filter(model.tenant_id == tenant_id, model.manual_id == manual_id)
        if revision_id and revision_scoped and hasattr(model, "revision_id"):
            q = q.filter(model.revision_id == revision_id)
        return _bounded(q.all(), dataset=model.__tablename__)

    campaigns = query(dm.DocumentDistributionCampaign)
    campaign_ids = [row.id for row in campaigns]
    recipients = []
    acknowledgements = []
    if campaign_ids:
        recipients = _bounded(
            db.query(dm.DocumentDistributionRecipient)
            .filter(dm.DocumentDistributionRecipient.tenant_id == tenant_id, dm.DocumentDistributionRecipient.campaign_id.in_(campaign_ids))
            .all(),
            dataset="distribution_recipients",
        )
        recipient_ids = [row.id for row in recipients]
        if recipient_ids:
            acknowledgements = _bounded(
                db.query(dm.DocumentAcknowledgement)
                .filter(dm.DocumentAcknowledgement.tenant_id == tenant_id, dm.DocumentAcknowledgement.recipient_id.in_(recipient_ids))
                .all(),
                dataset="acknowledgements",
            )

    copies = query(dm.DocumentControlledCopy)
    copy_ids = [row.id for row in copies]
    copy_events = []
    if copy_ids:
        copy_events = _bounded(
            db.query(dm.DocumentControlledCopyEvent)
            .filter(dm.DocumentControlledCopyEvent.tenant_id == tenant_id, dm.DocumentControlledCopyEvent.controlled_copy_id.in_(copy_ids))
            .all(),
            dataset="controlled_copy_events",
        )

    external_sources = query(dm.ExternalDocumentSource, revision_scoped=False)
    source_ids = [row.id for row in external_sources]
    external_receipts = []
    if source_ids:
        external_receipts = _bounded(
            db.query(dm.ExternalRevisionReceipt)
            .filter(dm.ExternalRevisionReceipt.tenant_id == tenant_id, dm.ExternalRevisionReceipt.source_id.in_(source_ids))
            .all(),
            dataset="external_revision_receipts",
        )

    result: dict[str, list[Any]] = {
        "change_requests": query(dm.DocumentChangeRequest),
        "workflows": query(dm.DocumentWorkflowInstance),
        "authority_submissions": query(dm.DocumentAuthoritySubmission),
        "temporary_revisions": query(dm.DocumentTemporaryRevision),
        "distribution_campaigns": campaigns,
        "distribution_recipients": recipients,
        "acknowledgements": acknowledgements,
        "controlled_copies": copies,
        "controlled_copy_events": copy_events,
        "periodic_reviews": query(dm.DocumentReviewPlan),
        "external_sources": external_sources,
        "external_revision_receipts": external_receipts,
        "applicability": query(dm.DocumentApplicabilityRule),
        "integration_links": query(dm.DocumentIntegrationLink),
    }
    if hasattr(dm, "DocumentGeneratedRecord"):
        result["generated_records"] = query(dm.DocumentGeneratedRecord)
    return result


@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-pack.zip")
def generate_document_evidence_pack(
    tenant_slug: str,
    manual_id: str,
    request: Request,
    revision_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    selected_revision = get_revision(db, manual, revision_id) if revision_id else None

    revisions_query = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.manual_id == manual.id)
    if selected_revision:
        revisions_query = revisions_query.filter(manual_models.ManualRevision.id == selected_revision.id)
    revisions = _bounded(
        revisions_query.order_by(manual_models.ManualRevision.created_at.asc(), manual_models.ManualRevision.id.asc()).all(),
        dataset="revisions",
    )
    datasets = _datasets(
        db,
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=selected_revision.id if selected_revision else None,
    )
    evidence_query = db.query(em.DocumentEvidenceAsset).filter(
        em.DocumentEvidenceAsset.tenant_id == tenant.amo_id,
        em.DocumentEvidenceAsset.manual_id == manual.id,
    )
    if selected_revision:
        evidence_query = evidence_query.filter(
            (em.DocumentEvidenceAsset.revision_id == selected_revision.id)
            | (em.DocumentEvidenceAsset.revision_id.is_(None))
        )
    evidence_assets = _bounded(
        evidence_query.order_by(em.DocumentEvidenceAsset.created_at.asc(), em.DocumentEvidenceAsset.id.asc()).all(),
        dataset="evidence_assets",
    )
    audit_rows = _manual_audit_rows(db, tenant_id=tenant.id, manual_id=manual.id)

    attachment_count = len(evidence_assets) + sum(1 for row in revisions if row.source_storage_path and row.source_sha256)
    if attachment_count > MAX_PACK_ATTACHMENTS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVIDENCE_PACK_TOO_MANY_ATTACHMENTS",
                "message": "This evidence pack exceeds the synchronous attachment ceiling.",
                "attachments": attachment_count,
                "limit": MAX_PACK_ATTACHMENTS,
            },
        )

    generated_at = datetime.now(timezone.utc)
    buffer = io.BytesIO()
    file_manifest: list[dict[str, Any]] = []
    dataset_manifest: dict[str, dict[str, Any]] = {}
    total_attachment_bytes = 0

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        readme = (
            "AMO Portal Document Control evidence pack\n"
            f"Document: {manual.code} — {manual.title}\n"
            f"Generated: {generated_at.isoformat()}\n"
            "This package is server-generated from authoritative Document Control records.\n"
            "Use manifest.json SHA-256 values to verify retained files and datasets.\n"
        ).encode("utf-8")
        archive.writestr("README.txt", readme)
        file_manifest.append({"path": "README.txt", "sha256": hashlib.sha256(readme).hexdigest(), "size_bytes": len(readme), "kind": "README"})

        document_payload = {
            "document": _serialize_row(manual),
            "profile": _serialize_row(profile) if profile else None,
            "selected_revision_id": selected_revision.id if selected_revision else None,
            "generated_at": generated_at.isoformat(),
            "generated_by_user_id": current_user.id,
            "tenant_id": tenant.amo_id,
            "tenant_slug": tenant.slug,
        }
        digest = _write_json(archive, "data/document.json", document_payload)
        dataset_manifest["document"] = {"path": "data/document.json", "rows": 1, "sha256": digest}

        revision_payload = [_serialize_row(row, exclude={"source_storage_path"}) for row in revisions]
        digest = _write_json(archive, "data/revisions.json", revision_payload)
        dataset_manifest["revisions"] = {"path": "data/revisions.json", "rows": len(revision_payload), "sha256": digest}
        _write_csv(archive, "data/revisions.csv", revision_payload)

        for name, rows in datasets.items():
            payload = [_serialize_row(row) for row in rows]
            json_path = f"data/{name}.json"
            csv_path = f"data/{name}.csv"
            digest = _write_json(archive, json_path, payload)
            csv_digest = _write_csv(archive, csv_path, payload)
            dataset_manifest[name] = {
                "path": json_path,
                "csv_path": csv_path,
                "rows": len(payload),
                "sha256": digest,
                "csv_sha256": csv_digest,
            }

        audit_payload = [_serialize_row(row) for row in audit_rows]
        digest = _write_json(archive, "data/audit_history.json", audit_payload)
        csv_digest = _write_csv(archive, "data/audit_history.csv", audit_payload)
        dataset_manifest["audit_history"] = {
            "path": "data/audit_history.json",
            "csv_path": "data/audit_history.csv",
            "rows": len(audit_payload),
            "sha256": digest,
            "csv_sha256": csv_digest,
        }

        evidence_payload = [_serialize_row(row, exclude={"storage_path", "source_context_json"}) for row in evidence_assets]
        digest = _write_json(archive, "data/evidence_assets.json", evidence_payload)
        dataset_manifest["evidence_assets"] = {"path": "data/evidence_assets.json", "rows": len(evidence_payload), "sha256": digest}

        for row in revisions:
            if not row.source_storage_path or not row.source_sha256:
                continue
            content = _read_verified_file(
                row.source_storage_path,
                row.source_sha256,
                label=f"revision {row.revision_number}",
            )
            total_attachment_bytes += len(content)
            if total_attachment_bytes > MAX_PACK_FILE_BYTES:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "EVIDENCE_PACK_TOO_LARGE", "message": "Evidence pack attachments exceed the synchronous size ceiling.", "limit_bytes": MAX_PACK_FILE_BYTES},
                )
            filename = row.source_filename or f"revision-{row.revision_number}.bin"
            path = _attachment_name("controlled-revisions", row.id, filename)
            archive.writestr(path, content)
            file_manifest.append({
                "path": path,
                "sha256": row.source_sha256,
                "size_bytes": len(content),
                "kind": "CONTROLLED_REVISION_SOURCE",
                "revision_id": row.id,
            })

        for row in evidence_assets:
            content = _read_verified_file(row.storage_path, row.sha256, label=row.filename)
            total_attachment_bytes += len(content)
            if total_attachment_bytes > MAX_PACK_FILE_BYTES:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "EVIDENCE_PACK_TOO_LARGE", "message": "Evidence pack attachments exceed the synchronous size ceiling.", "limit_bytes": MAX_PACK_FILE_BYTES},
                )
            path = _attachment_name(row.category.lower(), row.id, row.filename)
            archive.writestr(path, content)
            file_manifest.append({
                "path": path,
                "sha256": row.sha256,
                "size_bytes": len(content),
                "kind": "DOCUMENT_EVIDENCE_ASSET",
                "asset_id": row.id,
                "category": row.category,
            })

        manifest = {
            "schema": "amo-portal.document-control-evidence-pack.v1",
            "generated_at": generated_at.isoformat(),
            "tenant": {"id": tenant.amo_id, "slug": tenant.slug},
            "document": {"id": manual.id, "code": manual.code, "title": manual.title},
            "revision_scope": selected_revision.id if selected_revision else "ALL",
            "dataset_manifest": dataset_manifest,
            "files": file_manifest,
            "bounds": {
                "max_attachment_bytes": MAX_PACK_FILE_BYTES,
                "max_attachments": MAX_PACK_ATTACHMENTS,
                "max_rows_per_dataset": MAX_PACK_ROWS_PER_DATASET,
            },
        }
        _write_json(archive, "manifest.json", manifest)

    pack_bytes = buffer.getvalue()
    pack_sha256 = hashlib.sha256(pack_bytes).hexdigest()
    audit(
        db,
        tenant,
        request,
        "document.evidence_pack.generated",
        "manual",
        manual.id,
        {
            "revision_id": selected_revision.id if selected_revision else None,
            "pack_sha256": pack_sha256,
            "pack_size_bytes": len(pack_bytes),
            "attachments": attachment_count,
        },
    )
    db.commit()

    filename = f"{manual.code.replace('/', '-')}_evidence_pack{f'_{selected_revision.revision_number}' if selected_revision else ''}.zip"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store",
        "X-Evidence-Pack-SHA256": pack_sha256,
        "X-Evidence-Pack-Attachments": str(attachment_count),
    }
    return StreamingResponse(io.BytesIO(pack_bytes), media_type="application/zip", headers=headers)
