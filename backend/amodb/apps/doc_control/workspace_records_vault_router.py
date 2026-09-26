from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from calendar import monthrange
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, true
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.tenant_authority import is_tenant_admin
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import records_vault_models as rm
from . import warehouse_service as warehouse
from .document_text_extractor import extract_document_text
from .workspace_evidence_router import _safe_filename, _validate_file_signature
from .workspace_library_router import _scope_match
from .workspace_service import audit, is_control_user, resolve_tenant, role_value, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Records Vault"])

RECORD_ROOT = Path(os.getenv("DOCUMENT_RECORD_VAULT_DIR", "uploads/document-record-vault")).resolve()
MAX_RECORD_BYTES = int(os.getenv("DOCUMENT_RECORD_VAULT_MAX_BYTES", str(100 * 1024 * 1024)))
DISPOSITIONS = {"REVIEW_AT_EXPIRY", "ARCHIVE", "TRANSFER", "DESTROY"}
SERIES_STATUSES = {"ACTIVE", "INACTIVE"}
RECORD_STATUSES = {"ACTIVE", "ARCHIVED", "TRANSFERRED", "DISPOSED"}


class RecordSeriesCreate(BaseModel):
    code: str = Field(min_length=2, max_length=128)
    title: str = Field(min_length=2, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    owner_department: str = Field(min_length=2, max_length=128)
    retention_years: int = Field(default=7, ge=1, le=100)
    disposition_method: Literal["REVIEW_AT_EXPIRY", "ARCHIVE", "TRANSFER", "DESTROY"] = "REVIEW_AT_EXPIRY"
    restricted: bool = True
    controllers_can_read: bool = True
    access_scope: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegalHoldRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=2, max_length=4000)


class RecordDispositionRequest(BaseModel):
    disposition_status: Literal["ARCHIVED", "TRANSFERRED", "DISPOSED"]
    reason: str = Field(min_length=2, max_length=4000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


def _add_years(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def _scope_allows(user: account_models.User, scope: dict[str, Any]) -> bool:
    if str(user.id) in {str(value) for value in scope.get("user_ids", [])}:
        return True
    role = role_value(user)
    if role and role in {str(value).upper() for value in scope.get("roles", [])}:
        return True
    department = getattr(user, "department", None)
    department_tokens = {
        str(value).upper()
        for value in [
            getattr(user, "department_id", None),
            getattr(department, "id", None),
            getattr(department, "code", None),
            getattr(department, "name", None),
        ]
        if value
    }
    return bool(department_tokens.intersection({str(value).upper() for value in scope.get("departments", [])}))


def _scope_sql_conditions(user: account_models.User, scope_column) -> list:
    conditions = [_scope_match(scope_column, "user_ids", str(user.id))]
    role = role_value(user)
    if role:
        conditions.append(_scope_match(scope_column, "roles", role, case_insensitive=True))
    department = getattr(user, "department", None)
    department_tokens = {
        str(value)
        for value in [
            getattr(user, "department_id", None),
            getattr(department, "id", None),
            getattr(department, "code", None),
            getattr(department, "name", None),
        ]
        if value
    }
    for token in department_tokens:
        conditions.append(_scope_match(scope_column, "departments", token, case_insensitive=True))
    return conditions


def _record_access_predicate(user: account_models.User):
    """Filter before count/offset so restricted records never distort pagination."""
    if is_tenant_admin(user):
        return true()
    series_conditions = [
        rm.TenantRecordSeries.restricted_flag.is_(False),
        *_scope_sql_conditions(user, rm.TenantRecordSeries.access_scope_json),
    ]
    if is_control_user(user):
        series_conditions.append(rm.TenantRecordSeries.controllers_can_read.is_(True))

    record_scope_empty = func.coalesce(func.jsonb_object_length(rm.TenantRecordAsset.access_scope_json), 0) == 0
    record_conditions = [
        record_scope_empty,
        *_scope_sql_conditions(user, rm.TenantRecordAsset.access_scope_json),
    ]
    return and_(or_(*series_conditions), or_(*record_conditions))


def _can_read_series(user: account_models.User, series: rm.TenantRecordSeries) -> bool:
    if is_tenant_admin(user):
        return True
    if is_control_user(user) and series.controllers_can_read:
        return True
    if not series.restricted_flag:
        return True
    return _scope_allows(user, dict(series.access_scope_json or {}))


def _can_read_record(user: account_models.User, series: rm.TenantRecordSeries, row: rm.TenantRecordAsset) -> bool:
    if not _can_read_series(user, series):
        return False
    scope = dict(row.access_scope_json or {})
    return not scope or is_tenant_admin(user) or _scope_allows(user, scope)


def _series(db: Session, tenant_id: str, series_id: str) -> rm.TenantRecordSeries:
    row = db.query(rm.TenantRecordSeries).filter(
        rm.TenantRecordSeries.tenant_id == tenant_id,
        rm.TenantRecordSeries.id == series_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Record series not found")
    return row


def _record(db: Session, tenant_id: str, record_id: str) -> rm.TenantRecordAsset:
    row = db.query(rm.TenantRecordAsset).filter(
        rm.TenantRecordAsset.tenant_id == tenant_id,
        rm.TenantRecordAsset.id == record_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Retained record not found")
    return row


def _series_payload(row: rm.TenantRecordSeries, user: account_models.User) -> dict[str, Any]:
    can_read = _can_read_series(user, row)
    return {
        "id": row.id,
        "code": row.code,
        "title": row.title if can_read or is_control_user(user) else "Restricted record series",
        "description": row.description if can_read else None,
        "owner_department": row.owner_department,
        "retention_years": row.retention_years,
        "disposition_method": row.disposition_method,
        "restricted": bool(row.restricted_flag),
        "controllers_can_read": bool(row.controllers_can_read) if is_control_user(user) else None,
        "status": row.status,
        "content_access": can_read,
    }


def _record_payload(row: rm.TenantRecordAsset, series: rm.TenantRecordSeries, user: account_models.User) -> dict[str, Any]:
    can_read = _can_read_record(user, series, row)
    controller = is_control_user(user)
    return {
        "id": row.id,
        "series_id": row.series_id,
        "series_code": series.code,
        "record_number": row.record_number,
        "title": row.title if can_read else "Restricted retained record",
        "source_module": row.source_module if can_read or controller else None,
        "source_entity_type": row.source_entity_type if can_read or controller else None,
        "source_entity_id": row.source_entity_id if can_read or controller else None,
        "filename": row.filename if can_read else None,
        "mime_type": row.mime_type if can_read else None,
        "size_bytes": row.size_bytes if can_read else None,
        "sha256": row.sha256 if can_read and controller else None,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        "retention_due_at": row.retention_due_at.isoformat() if row.retention_due_at else None,
        "legal_hold": bool(row.legal_hold),
        "legal_hold_reason": row.legal_hold_reason if controller else None,
        "disposition_status": row.disposition_status,
        "content_access": can_read,
    }


def _write_event(
    db: Session,
    *,
    tenant_id: str,
    record_id: str,
    user_id: str | None,
    event_type: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(rm.TenantRecordEvent(
        tenant_id=tenant_id,
        record_asset_id=record_id,
        event_type=event_type,
        actor_user_id=user_id,
        reason=reason,
        metadata_json=dict(metadata or {}),
    ))


@router.get("/t/{tenant_slug}/records/series")
def list_record_series(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    rows = db.query(rm.TenantRecordSeries).filter(
        rm.TenantRecordSeries.tenant_id == tenant.amo_id,
        rm.TenantRecordSeries.status == "ACTIVE",
    ).order_by(rm.TenantRecordSeries.code.asc()).all()
    if not is_control_user(current_user):
        rows = [row for row in rows if _can_read_series(current_user, row)]
    return {"items": [_series_payload(row, current_user) for row in rows]}


@router.post("/t/{tenant_slug}/records/series", status_code=201)
def create_record_series(
    tenant_slug: str,
    payload: RecordSeriesCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Document Control privileges are required to create a record series")
    tenant = resolve_tenant(db, tenant_slug, current_user)
    code = payload.code.strip().upper()
    if db.query(rm.TenantRecordSeries.id).filter(
        rm.TenantRecordSeries.tenant_id == tenant.amo_id,
        rm.TenantRecordSeries.code == code,
    ).first():
        raise HTTPException(status_code=409, detail="Record series code already exists")
    row = rm.TenantRecordSeries(
        tenant_id=tenant.amo_id,
        code=code,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        owner_department=payload.owner_department.strip().upper(),
        retention_years=payload.retention_years,
        disposition_method=payload.disposition_method,
        restricted_flag=payload.restricted,
        controllers_can_read=payload.controllers_can_read,
        access_scope_json=dict(payload.access_scope),
        metadata_json=dict(payload.metadata),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.records.series_created", "record_series", row.id, {
        "code": row.code,
        "retention_years": row.retention_years,
        "restricted": row.restricted_flag,
    })
    db.commit()
    return _series_payload(row, current_user)


@router.get("/t/{tenant_slug}/records")
def list_records(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    series_id: str | None = None,
    source_module: str | None = Query(default=None, max_length=64),
    legal_hold: bool | None = None,
    disposition_status: str | None = Query(default=None, max_length=40),
    retention_due: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(rm.TenantRecordAsset, rm.TenantRecordSeries).join(
        rm.TenantRecordSeries,
        rm.TenantRecordSeries.id == rm.TenantRecordAsset.series_id,
    ).filter(
        rm.TenantRecordAsset.tenant_id == tenant.amo_id,
        rm.TenantRecordSeries.tenant_id == tenant.amo_id,
    )
    query = query.filter(_record_access_predicate(current_user))
    if series_id:
        query = query.filter(rm.TenantRecordAsset.series_id == series_id)
    if source_module:
        query = query.filter(rm.TenantRecordAsset.source_module == source_module.strip().upper())
    if legal_hold is not None:
        query = query.filter(rm.TenantRecordAsset.legal_hold.is_(legal_hold))
    if disposition_status:
        query = query.filter(rm.TenantRecordAsset.disposition_status == disposition_status.strip().upper())
    if retention_due:
        query = query.filter(
            rm.TenantRecordAsset.retention_due_at.isnot(None),
            rm.TenantRecordAsset.retention_due_at <= utcnow(),
            rm.TenantRecordAsset.disposition_status == "ACTIVE",
        )
    if q and q.strip():
        search = q.strip()
        if db.get_bind().dialect.name == "postgresql":
            language = "simple"
            tsquery = func.websearch_to_tsquery(language, search)
            vector = func.to_tsvector(language, rm.TenantRecordAsset.search_text)
            query = query.filter(vector.op("@@")(tsquery)).order_by(func.ts_rank_cd(vector, tsquery).desc())
        else:
            needle = f"%{search}%"
            query = query.filter(or_(
                rm.TenantRecordAsset.record_number.ilike(needle),
                rm.TenantRecordAsset.title.ilike(needle),
                rm.TenantRecordAsset.filename.ilike(needle),
                rm.TenantRecordAsset.search_text.ilike(needle),
            ))
    total = int(query.order_by(None).count())
    rows = query.order_by(
        rm.TenantRecordAsset.captured_at.desc(),
        rm.TenantRecordAsset.id.desc(),
    ).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [
            {
                **_record_payload(row, series, current_user),
                "download_url": f"/doc-control/workspace/t/{tenant_slug}/records/{row.id}/download"
                if _can_read_record(current_user, series, row) else None,
            }
            for row, series in rows
        ],
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(rows)},
    }


@router.post("/t/{tenant_slug}/records", status_code=201)
async def upload_record(
    tenant_slug: str,
    request: Request,
    artifact: UploadFile = File(...),
    series_id: str = Form(...),
    record_number: str = Form(...),
    title: str = Form(...),
    source_module: str = Form("DOCUMENT_CONTROL"),
    source_entity_type: str | None = Form(None),
    source_entity_id: str | None = Form(None),
    captured_at: str | None = Form(None),
    access_scope_json: str | None = Form(None),
    metadata_json: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Document Control privileges are required to deposit a retained record")
    tenant = resolve_tenant(db, tenant_slug, current_user)
    series = _series(db, tenant.amo_id, series_id)
    if series.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="This record series is not active")
    number = record_number.strip()
    if db.query(rm.TenantRecordAsset.id).filter(
        rm.TenantRecordAsset.tenant_id == tenant.amo_id,
        rm.TenantRecordAsset.record_number == number,
    ).first():
        raise HTTPException(status_code=409, detail="Record number already exists")

    content = await artifact.read(MAX_RECORD_BYTES + 1)
    if len(content) > MAX_RECORD_BYTES:
        raise HTTPException(status_code=413, detail="Retained record exceeds the configured maximum file size")
    filename = _safe_filename(artifact.filename)
    mime_type = _validate_file_signature(filename, content)
    checksum = hashlib.sha256(content).hexdigest()
    if captured_at:
        try:
            captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="captured_at must be an ISO-8601 date/time") from exc
    else:
        captured = utcnow()
    try:
        scope = json.loads(access_scope_json) if access_scope_json else {}
        metadata = json.loads(metadata_json) if metadata_json else {}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Record access scope and metadata must be valid JSON objects") from exc
    if not isinstance(scope, dict) or not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="Record access scope and metadata must be JSON objects")

    record_id = str(uuid.uuid4())
    directory = (RECORD_ROOT / str(tenant.amo_id) / series.code / record_id).resolve()
    expected_root = RECORD_ROOT.resolve()
    if expected_root not in directory.parents:
        raise HTTPException(status_code=400, detail="Invalid record storage path")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    destination.write_bytes(content)

    extracted = extract_document_text(filename, content, mime_type)
    metadata = {
        **metadata,
        "text_index": {
            "engine": extracted.engine,
            "truncated": extracted.truncated,
            "warning": extracted.warning,
        },
    }
    search_text = " ".join(filter(None, [
        number,
        title.strip(),
        filename,
        source_module,
        source_entity_type or "",
        source_entity_id or "",
        " ".join(str(value) for value in metadata.values() if isinstance(value, (str, int, float))),
        extracted.text,
    ]))[:2_000_000]
    row = rm.TenantRecordAsset(
        id=record_id,
        tenant_id=tenant.amo_id,
        series_id=series.id,
        record_number=number,
        title=title.strip(),
        source_module=source_module.strip().upper(),
        source_entity_type=(source_entity_type or "").strip() or None,
        source_entity_id=(source_entity_id or "").strip() or None,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=checksum,
        storage_path=str(destination),
        captured_at=captured,
        retention_due_at=_add_years(captured, series.retention_years),
        search_text=search_text,
        access_scope_json=scope,
        metadata_json=metadata,
        uploaded_by_user_id=current_user.id,
    )
    db.add(row)
    _write_event(
        db,
        tenant_id=tenant.amo_id,
        record_id=row.id,
        user_id=current_user.id,
        event_type="DEPOSITED",
        metadata={"source_module": row.source_module, "sha256": row.sha256},
    )
    warehouse_record, warehouse_version = warehouse.sync_retained_record(
        db,
        tenant_id=str(tenant.amo_id),
        record_asset=row,
        series=series,
        actor_user_id=str(current_user.id),
    )
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=warehouse_record.id,
        content_version_id=warehouse_version.id,
        event_type="record.deposited",
        actor_user_id=str(current_user.id),
        metadata={"record_asset_id": row.id, "record_number": row.record_number},
    )
    audit(db, tenant, request, "document.records.deposited", "record_asset", row.id, {
        "series_id": series.id,
        "record_number": row.record_number,
        "source_module": row.source_module,
        "source_entity_type": row.source_entity_type,
        "source_entity_id": row.source_entity_id,
        "sha256": row.sha256,
        "text_index_engine": extracted.engine,
        "text_index_warning": extracted.warning,
        "retention_due_at": row.retention_due_at.isoformat() if row.retention_due_at else None,
    })
    db.commit()
    return {
        **_record_payload(row, series, current_user),
        "download_url": f"/doc-control/workspace/t/{tenant_slug}/records/{row.id}/download",
    }


@router.get("/t/{tenant_slug}/records/{record_id}")
def get_record(
    tenant_slug: str,
    record_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _record(db, tenant.amo_id, record_id)
    series = _series(db, tenant.amo_id, row.series_id)
    if not _can_read_record(current_user, series, row):
        raise HTTPException(status_code=403, detail="This retained record is outside your authorized scope")
    return {
        **_record_payload(row, series, current_user),
        "download_url": f"/doc-control/workspace/t/{tenant_slug}/records/{row.id}/download",
    }


@router.get("/t/{tenant_slug}/records/{record_id}/download")
def download_record(
    tenant_slug: str,
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _record(db, tenant.amo_id, record_id)
    series = _series(db, tenant.amo_id, row.series_id)
    if not _can_read_record(current_user, series, row):
        raise HTTPException(status_code=403, detail="This retained record is outside your authorized scope")
    path = Path(row.storage_path).resolve()
    if not path.is_file() or RECORD_ROOT.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="Retained record file is unavailable")
    audit(db, tenant, request, "document.records.downloaded", "record_asset", row.id, {
        "record_number": row.record_number,
        "series_id": row.series_id,
    })
    _write_event(db, tenant_id=tenant.amo_id, record_id=row.id, user_id=current_user.id, event_type="ACCESSED")
    warehouse_record, warehouse_version = warehouse.sync_retained_record(
        db,
        tenant_id=str(tenant.amo_id),
        record_asset=row,
        series=series,
        actor_user_id=str(current_user.id),
    )
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=warehouse_record.id,
        content_version_id=warehouse_version.id,
        event_type="record.downloaded",
        actor_user_id=str(current_user.id),
        metadata={"record_asset_id": row.id},
    )
    db.commit()
    return FileResponse(
        path,
        media_type=row.mime_type,
        filename=row.filename,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/t/{tenant_slug}/records/{record_id}/legal-hold")
def set_legal_hold(
    tenant_slug: str,
    record_id: str,
    payload: LegalHoldRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Document Control privileges are required to manage record holds")
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _record(db, tenant.amo_id, record_id)
    row.legal_hold = payload.enabled
    row.legal_hold_reason = payload.reason.strip() if payload.enabled else None
    row.legal_hold_set_by_user_id = current_user.id if payload.enabled else None
    row.legal_hold_set_at = utcnow() if payload.enabled else None
    _write_event(
        db,
        tenant_id=tenant.amo_id,
        record_id=row.id,
        user_id=current_user.id,
        event_type="LEGAL_HOLD_SET" if payload.enabled else "LEGAL_HOLD_RELEASED",
        reason=payload.reason.strip(),
    )
    warehouse_record, warehouse_version = warehouse.sync_retained_record(
        db,
        tenant_id=str(tenant.amo_id),
        record_asset=row,
        series=_series(db, tenant.amo_id, row.series_id),
        actor_user_id=str(current_user.id),
    )
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=warehouse_record.id,
        content_version_id=warehouse_version.id,
        event_type="retention_hold.applied" if payload.enabled else "retention_hold.released",
        actor_user_id=str(current_user.id),
        metadata={"reason": payload.reason.strip()},
    )
    audit(db, tenant, request, "document.records.legal_hold_changed", "record_asset", row.id, {
        "enabled": payload.enabled,
        "reason": payload.reason.strip(),
    })
    db.commit()
    return {"id": row.id, "legal_hold": row.legal_hold, "legal_hold_reason": row.legal_hold_reason}


@router.post("/t/{tenant_slug}/records/{record_id}/disposition")
def dispose_record(
    tenant_slug: str,
    record_id: str,
    payload: RecordDispositionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Document Control privileges are required to govern record disposition")
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _record(db, tenant.amo_id, record_id)
    if row.legal_hold:
        raise HTTPException(status_code=409, detail="This record is under legal/administrative hold and cannot be disposed")
    if payload.disposition_status not in RECORD_STATUSES - {"ACTIVE"}:
        raise HTTPException(status_code=422, detail="Unsupported disposition status")
    row.disposition_status = payload.disposition_status
    row.disposed_at = utcnow()
    row.disposed_by_user_id = current_user.id
    row.disposition_reason = payload.reason.strip()
    _write_event(
        db,
        tenant_id=tenant.amo_id,
        record_id=row.id,
        user_id=current_user.id,
        event_type=f"DISPOSITION_{payload.disposition_status}",
        reason=payload.reason.strip(),
        metadata={"evidence": list(payload.evidence)},
    )
    warehouse_record, warehouse_version = warehouse.sync_retained_record(
        db,
        tenant_id=str(tenant.amo_id),
        record_asset=row,
        series=_series(db, tenant.amo_id, row.series_id),
        actor_user_id=str(current_user.id),
    )
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=warehouse_record.id,
        content_version_id=warehouse_version.id,
        event_type="record.disposition_recorded",
        actor_user_id=str(current_user.id),
        metadata={"status": row.disposition_status, "reason": row.disposition_reason},
    )
    audit(db, tenant, request, "document.records.disposition_recorded", "record_asset", row.id, {
        "status": row.disposition_status,
        "reason": row.disposition_reason,
        "evidence": list(payload.evidence),
    })
    # The binary is intentionally retained here. A separate purge authority is
    # required before physical destruction; this transition only records the
    # governed disposition decision and prevents silent deletion.
    db.commit()
    return {"id": row.id, "disposition_status": row.disposition_status, "disposed_at": row.disposed_at.isoformat()}


@router.get("/t/{tenant_slug}/records/{record_id}/history")
def record_history(
    tenant_slug: str,
    record_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _record(db, tenant.amo_id, record_id)
    series = _series(db, tenant.amo_id, row.series_id)
    if not (_can_read_record(current_user, series, row) or is_control_user(current_user)):
        raise HTTPException(status_code=403, detail="This retained record is outside your authorized scope")
    events = db.query(rm.TenantRecordEvent).filter(
        rm.TenantRecordEvent.tenant_id == tenant.amo_id,
        rm.TenantRecordEvent.record_asset_id == row.id,
    ).order_by(rm.TenantRecordEvent.created_at.desc()).limit(250).all()
    return {"items": [{
        "id": event.id,
        "event_type": event.event_type,
        "actor_user_id": event.actor_user_id if is_control_user(current_user) else None,
        "reason": event.reason if is_control_user(current_user) else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    } for event in events]}
