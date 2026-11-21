"""Tenant-isolated Microsoft 365 connection and explicit controlled DOCX import.

Microsoft edits remain drafts in SharePoint. Only a frozen, user-requested import
creates a DMS revision; publication continues through normal Document Control.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from amodb.apps.accounts import models as accounts
from amodb.apps.accounts.tenant_authority import is_tenant_admin
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals import core_router as manual_core
from amodb.apps.manuals.office_layout import precompute_office_layout_assets
from amodb.apps.doc_control.knowledge_indexer import index_revision_background
from amodb.apps.platform.saas_secrets import encrypt_secret
from amodb.database import get_db
from amodb.security import get_current_active_user
from . import microsoft_models as mm
from .microsoft_graph import (
    _configured, authorization_url, configured, connected_identity,
    current_item, download_docx, exchange_code, link_payload, share_item,
    tenant_claim, update_link,
)
from .workspace_service import audit, get_manual, require_control_user, resolve_tenant

workspace_router = APIRouter(prefix="/workspace", tags=["Document Control Microsoft 365"])
callback_router = APIRouter(prefix="/microsoft365", tags=["Microsoft 365 authorization"])


class LinkDocument(BaseModel):
    share_url: str = Field(min_length=20, max_length=2048)


class ImportDocument(BaseModel):
    revision_number: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    issue_number: str = Field(default="", max_length=32)
    expected_etag: str = Field(min_length=1, max_length=255)


def _connection(db: Session, tenant_id: str) -> mm.DocumentMicrosoftConnection | None:
    return db.query(mm.DocumentMicrosoftConnection).filter(mm.DocumentMicrosoftConnection.tenant_id == tenant_id).first()


def _connected(db: Session, tenant_id: str) -> mm.DocumentMicrosoftConnection:
    row = _connection(db, tenant_id)
    if not row or row.status != "CONNECTED" or not row.encrypted_refresh_token:
        raise HTTPException(status_code=409, detail="Connect Microsoft 365 in Document Control Administration first")
    return row


def _link(db: Session, tenant_id: str, manual_id: str) -> mm.DocumentMicrosoftFileLink | None:
    return db.query(mm.DocumentMicrosoftFileLink).filter(
        mm.DocumentMicrosoftFileLink.tenant_id == tenant_id,
        mm.DocumentMicrosoftFileLink.manual_id == manual_id,
    ).first()


def _require_admin(user, tenant) -> None:
    if not is_tenant_admin(user, tenant.amo_id):
        raise HTTPException(status_code=403, detail="Only the tenant administrator may authorize or disconnect Microsoft 365")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@workspace_router.get("/t/{tenant_slug}/microsoft365/connection")
def connection_status(
    tenant_slug: str,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant = resolve_tenant(db, tenant_slug, user)
    row = _connection(db, tenant.amo_id)
    return {
        "configured": configured(),
        "connected": bool(row and row.status == "CONNECTED" and row.encrypted_refresh_token),
        "status": row.status if row else "NOT_CONNECTED",
        "microsoft_user_name": row.microsoft_user_name if row and row.status == "CONNECTED" else None,
        "microsoft_tenant_id": row.microsoft_tenant_id if row and row.status == "CONNECTED" else None,
        "can_configure": is_tenant_admin(user, tenant.amo_id),
        "last_connected_at": row.last_connected_at.isoformat() if row and row.last_connected_at else None,
        "last_error": row.last_error if row else None,
    }


@workspace_router.post("/t/{tenant_slug}/microsoft365/connect")
def start_connection(
    tenant_slug: str, request: Request,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, user)
    _require_admin(user, tenant)
    _configured()
    state = secrets.token_urlsafe(40)
    state_hash = hashlib.sha256(state.encode("ascii")).hexdigest()
    row = _connection(db, tenant.amo_id)
    if row is None:
        row = mm.DocumentMicrosoftConnection(tenant_id=tenant.amo_id)
        db.add(row)
    row.oauth_state_sha256 = state_hash
    row.oauth_state_user_id = str(user.id)
    row.oauth_state_expires_at = _now() + timedelta(minutes=10)
    row.last_error = None
    audit(db, tenant, request, "document.microsoft365.connect_started", "document_microsoft_connection", row.id, {})
    db.commit()
    return {"authorization_url": authorization_url(state), "expires_in_seconds": 600}


@callback_router.get("/oauth/callback", include_in_schema=False)
def microsoft_callback(
    state: str, code: str | None = None, error: str | None = None,
    db: Session = Depends(get_db),
):
    if not (20 <= len(state) <= 256):
        raise HTTPException(status_code=400, detail="Invalid Microsoft authorization state")
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    row = db.query(mm.DocumentMicrosoftConnection).filter(
        mm.DocumentMicrosoftConnection.oauth_state_sha256 == state_hash,
    ).with_for_update().first()
    if not row or not row.oauth_state_expires_at or _aware(row.oauth_state_expires_at) < _now():
        raise HTTPException(status_code=400, detail="Expired or invalid Microsoft authorization state")
    actor = db.query(accounts.User).filter(
        accounts.User.id == row.oauth_state_user_id,
        accounts.User.amo_id == row.tenant_id,
        accounts.User.is_active.is_(True),
    ).first()
    if not actor or not is_tenant_admin(actor, row.tenant_id):
        raise HTTPException(status_code=403, detail="The Microsoft connection administrator is no longer authorized")
    tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.amo_id == row.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Document Control tenant no longer exists")
    # One-time authorization state; never retain a reusable callback token.
    row.oauth_state_sha256 = None
    row.oauth_state_user_id = None
    row.oauth_state_expires_at = None
    db.flush()
    db.commit()
    success = False
    if code and not error:
        result = exchange_code(code)
        refresh = str(result.get("refresh_token") or "")
        if not refresh:
            raise HTTPException(status_code=502, detail="Microsoft did not grant offline document access")
        identity = connected_identity(str(result["access_token"]))
        row.encrypted_refresh_token = encrypt_secret({"refresh_token": refresh})[0]
        row.status = "CONNECTED"
        row.microsoft_user_id = str(identity.get("id") or "")[:128]
        row.microsoft_user_name = str(identity.get("userPrincipalName") or identity.get("displayName") or "")[:255]
        row.microsoft_tenant_id = tenant_claim(str(result.get("id_token") or ""))
        row.granted_scopes = str(result.get("scope") or "")[:1024]
        row.connected_by_user_id = str(actor.id)
        row.last_connected_at = _now()
        row.last_error = None
        success = True
    else:
        row.last_error = "Microsoft authorization was cancelled or rejected"
    db.commit()
    frontend = _configured()["frontend_url"].rstrip("/")
    destination = frontend + "/maintenance/" + quote(tenant.slug, safe="") + "/document-control/administration?microsoft365=" + ("connected" if success else "cancelled")
    return RedirectResponse(destination, status_code=303)


@workspace_router.delete("/t/{tenant_slug}/microsoft365/connection")
def disconnect(
    tenant_slug: str, request: Request,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, user)
    _require_admin(user, tenant)
    row = _connection(db, tenant.amo_id)
    if row:
        row.encrypted_refresh_token = None
        row.status = "DISCONNECTED"
        row.oauth_state_sha256 = None
        row.oauth_state_user_id = None
        row.oauth_state_expires_at = None
        audit(db, tenant, request, "document.microsoft365.disconnected", "document_microsoft_connection", row.id)
        db.commit()
    # Retain linked file and imported-revision provenance for audit.
    return {"status": "DISCONNECTED"}


@workspace_router.get("/t/{tenant_slug}/documents/{manual_id}/microsoft365")
def document_link(
    tenant_slug: str, manual_id: str,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant = resolve_tenant(db, tenant_slug, user)
    get_manual(db, tenant, manual_id)
    row = _link(db, tenant.amo_id, manual_id)
    return {"linked": bool(row), "file": link_payload(row) if row else None}


@workspace_router.post("/t/{tenant_slug}/documents/{manual_id}/microsoft365")
def link_document(
    tenant_slug: str, manual_id: str, payload: LinkDocument,
    request: Request, db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant = resolve_tenant(db, tenant_slug, user)
    get_manual(db, tenant, manual_id)
    conn = _connected(db, tenant.amo_id)
    item = share_item(conn, payload.share_url)
    if not item.get("eTag"):
        raise HTTPException(status_code=409, detail="Microsoft did not return a stable file version")
    drive_id = str((item.get("parentReference") or {}).get("driveId") or "")
    row = _link(db, tenant.amo_id, manual_id)
    if row and row.last_imported_revision_id and (row.drive_id != drive_id or row.item_id != str(item["id"])):
        raise HTTPException(status_code=409, detail="This manual has imported SharePoint history; unlink it with an audited decision before changing source")
    if not row:
        row = mm.DocumentMicrosoftFileLink(
            tenant_id=tenant.amo_id, manual_id=manual_id, drive_id=drive_id,
            item_id=str(item["id"]), item_name=str(item["name"]), web_url=str(item["webUrl"]),
            observed_etag=str(item["eTag"]), linked_by_user_id=str(user.id),
        )
        db.add(row)
    row.drive_id = drive_id
    row.item_id = str(item["id"])
    update_link(row, item)
    audit(db, tenant, request, "document.microsoft365.linked", "manual", manual_id, {
        "drive_id": row.drive_id, "item_id": row.item_id, "etag": row.observed_etag,
    })
    db.commit()
    return {"linked": True, "file": link_payload(row)}


@workspace_router.post("/t/{tenant_slug}/documents/{manual_id}/microsoft365/check-updates")
def check_document(
    tenant_slug: str, manual_id: str,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant = resolve_tenant(db, tenant_slug, user)
    get_manual(db, tenant, manual_id)
    row = _link(db, tenant.amo_id, manual_id)
    if not row:
        raise HTTPException(status_code=404, detail="No SharePoint document is linked to this manual")
    item = current_item(_connected(db, tenant.amo_id), row)
    update_link(row, item)
    db.commit()
    return {"linked": True, "file": link_payload(row)}


@workspace_router.delete("/t/{tenant_slug}/documents/{manual_id}/microsoft365")
def unlink_document(
    tenant_slug: str, manual_id: str, request: Request,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant = resolve_tenant(db, tenant_slug, user)
    get_manual(db, tenant, manual_id)
    row = _link(db, tenant.amo_id, manual_id)
    if row:
        audit(db, tenant, request, "document.microsoft365.unlinked", "manual", manual_id, {
            "drive_id": row.drive_id, "item_id": row.item_id,
            "last_imported_revision_id": row.last_imported_revision_id,
        })
        db.delete(row)
        db.commit()
    return {"linked": False}


@workspace_router.post("/t/{tenant_slug}/documents/{manual_id}/microsoft365/import")
async def import_document(
    tenant_slug: str, manual_id: str, payload: ImportDocument,
    request: Request, background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
):
    require_control_user(user)
    tenant = resolve_tenant(db, tenant_slug, user)
    manual = get_manual(db, tenant, manual_id)
    row = _link(db, tenant.amo_id, manual_id)
    if not row:
        raise HTTPException(status_code=404, detail="Link a SharePoint document before importing a revision")
    conn = _connected(db, tenant.amo_id)
    item = current_item(conn, row)
    etag = str(item.get("eTag") or "")
    if not etag or etag != payload.expected_etag:
        raise HTTPException(status_code=409, detail="The Word document has changed; check for updates and review the latest version before import")
    if row.last_imported_etag == etag:
        raise HTTPException(status_code=409, detail="This exact SharePoint version has already been imported")
    if db.query(manual_models.ManualRevision.id).filter(
        manual_models.ManualRevision.manual_id == manual.id,
        manual_models.ManualRevision.rev_number == payload.revision_number,
    ).first():
        raise HTTPException(status_code=409, detail="The requested controlled revision number already exists")
    content = download_docx(conn, item, drive_id=row.drive_id)
    # Verify the file did not change during the streaming download.
    current_after = current_item(conn, row)
    if str(current_after.get("eTag") or "") != etag:
        raise HTTPException(status_code=409, detail="The SharePoint source changed during download; retry with the new version")
    file_name = str(item["name"])
    preflight_file = UploadFile(
        file=BytesIO(content), filename=file_name,
        headers=Headers({"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    )
    manual_core._validate_docx_upload(preflight_file, content)
    parsed = manual_core._extract_docx_content(content, file_name)
    meta = dict(parsed.get("metadata") or {})
    detected_code = str(meta.get("part_number") or manual.code).strip().upper()
    if detected_code != manual.code.upper():
        raise HTTPException(status_code=409, detail="The selected Word file identifies a different controlled manual")
    detected_revision = str(meta.get("revision_number") or payload.revision_number).strip()
    if detected_revision != payload.revision_number:
        raise HTTPException(status_code=409, detail="Word's revision label conflicts with the requested DMS revision; correct the source before importing")
    # Use the existing guarded canonical upload pipeline after validating document identity.
    upload = UploadFile(
        file=BytesIO(content),
        filename=file_name,
        headers=Headers({"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    )
    result = await manual_core.upload_docx_revision(
        tenant_slug=tenant_slug, request=request, code=manual.code,
        title=manual.title, rev_number=payload.revision_number,
        issue_number=payload.issue_number, manual_type=manual.manual_type,
        owner_role=manual.owner_role, effective_date=None,
        change_log="Imported from linked SharePoint working file",
        control_metadata_json=None, file=upload, db=db, current_user=user,
    )
    if str(result["manual_id"]) != str(manual.id):
        raise HTTPException(status_code=409, detail="Imported source did not match the canonical manual; contact Document Control")
    row.last_imported_etag = etag
    row.last_imported_source_sha256 = hashlib.sha256(content).hexdigest()
    row.last_imported_revision_id = result["revision_id"]
    update_link(row, current_after)
    audit(db, tenant, request, "document.microsoft365.revision_imported", "manual_revision", result["revision_id"], {
        "manual_id": manual.id, "item_id": row.item_id, "drive_id": row.drive_id,
        "source_etag": etag, "source_sha256": row.last_imported_source_sha256,
    })
    db.commit()
    background_tasks.add_task(precompute_office_layout_assets, result["revision_id"])
    background_tasks.add_task(index_revision_background, result["revision_id"])
    return {
        "manual_id": manual.id,
        "revision_id": result["revision_id"],
        "status": result["status"],
        "source_sha256": result["source_sha256"],
        "file": link_payload(row),
    }
