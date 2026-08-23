from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import domain_models as dc_models
from amodb.apps.doc_control.workspace_service import can_read_manual, get_profile
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .core_router import _audit, _tenant_by_slug


router = APIRouter(
    prefix="/manuals",
    tags=["Publications Reader Performance"],
    dependencies=[Depends(get_current_active_user)],
)

_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
_STREAM_CHUNK_BYTES = 1024 * 1024


class ReaderPositionUpdate(BaseModel):
    page_number: int | None = Field(default=None, ge=1)
    anchor_slug: str | None = Field(default=None, max_length=255)
    section_id: str | None = Field(default=None, max_length=36)
    scroll_percent: int = Field(default=0, ge=0, le=100)
    zoom_percent: int = Field(default=100, ge=50, le=250)


def _status_value(revision: models.ManualRevision) -> str:
    raw = getattr(revision, "status_enum", None)
    return str(getattr(raw, "value", raw or "")).upper()


def _source_type(revision: models.ManualRevision) -> str:
    raw = getattr(revision, "source_type_enum", None)
    return str(getattr(raw, "value", raw or "")).upper()


def _source_path(revision: models.ManualRevision) -> Path | None:
    raw = str(getattr(revision, "source_storage_path", "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() and path.is_file() else None


def _cache_key(revision: models.ManualRevision, source_path: Path | None) -> str:
    checksum = str(getattr(revision, "source_sha256", "") or "").strip().lower()
    if checksum:
        return checksum
    if source_path:
        stat = source_path.stat()
        return f"{revision.id}-{stat.st_size}-{stat.st_mtime_ns}"
    return f"{revision.id}-{getattr(revision, 'created_at', '')}"


def _etag(cache_key: str) -> str:
    return f'"{cache_key}"'


def _load_publication(
    db: Session,
    *,
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    current_user: account_models.User,
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if not getattr(current_user, "is_superuser", False) and str(getattr(current_user, "amo_id", "")) != str(tenant.amo_id):
        raise HTTPException(status_code=403, detail="The requested publication is outside the active AMO context")
    manual = (
        db.query(models.Manual)
        .filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id)
        .first()
    )
    revision = (
        db.query(models.ManualRevision)
        .filter(
            models.ManualRevision.id == revision_id,
            models.ManualRevision.manual_id == manual_id,
        )
        .first()
    )
    if not manual or not revision:
        raise HTTPException(status_code=404, detail="Publication revision not found")
    profile = get_profile(db, tenant, manual.id)
    if not can_read_manual(current_user, profile):
        raise HTTPException(status_code=403, detail="The current user is not permitted to read this publication")
    return tenant, manual, revision, profile


def _acknowledgement_payload(db: Session, revision_id: str, user_id: str | None) -> dict:
    if not user_id:
        return {"required": False, "pending": False}
    row = (
        db.query(models.Acknowledgement)
        .filter(
            models.Acknowledgement.revision_id == revision_id,
            models.Acknowledgement.holder_user_id == user_id,
        )
        .first()
    )
    if not row:
        return {
            "required": False,
            "pending": False,
            "status": None,
            "due_at": None,
            "acknowledged_at": None,
            "acknowledgement_text": None,
        }
    raw_status = getattr(row, "status_enum", None)
    status = str(getattr(raw_status, "value", raw_status or "")).upper()
    return {
        "required": True,
        "pending": status != "ACKNOWLEDGED",
        "status": status,
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
        "acknowledgement_text": row.acknowledgement_text,
    }


def _progress_payload(db: Session, revision_id: str, user_id: str | None) -> dict:
    if not user_id:
        return {}
    row = (
        db.query(models.ManualReaderProgress)
        .filter(
            models.ManualReaderProgress.revision_id == revision_id,
            models.ManualReaderProgress.user_id == user_id,
        )
        .first()
    )
    if not row:
        return {}
    return {
        "last_section_id": row.last_section_id,
        "last_anchor_slug": row.last_anchor_slug,
        "last_page_number": row.last_page_number,
        "scroll_percent": row.scroll_percent,
        "zoom_percent": row.zoom_percent,
        "last_opened_at": row.last_opened_at.isoformat() if row.last_opened_at else None,
    }


def _reader_metadata(
    db: Session,
    *,
    tenant_slug: str,
    manual: models.Manual,
    revision: models.ManualRevision,
    profile,
    sections: list[models.ManualSection],
) -> dict:
    source_path = _source_path(revision)
    source_size = source_path.stat().st_size if source_path else 0
    source_type = _source_type(revision)
    cache_key = _cache_key(revision, source_path)
    text_char_count = int(
        db.query(func.coalesce(func.sum(func.length(models.ManualBlock.text_plain)), 0))
        .join(models.ManualSection, models.ManualSection.id == models.ManualBlock.section_id)
        .filter(models.ManualSection.revision_id == revision.id)
        .scalar()
        or 0
    )
    page_count = max(1, int(getattr(revision, "source_page_count", 0) or 1))
    image_only = source_type == "PDF" and text_char_count < max(80, page_count * 16)
    is_published = _status_value(revision) == "PUBLISHED"
    if source_type == "PDF" and source_path:
        rendered_url = (
            f"/manuals/t/{tenant_slug}/{manual.id}/rev/{revision.id}/stream.pdf"
            f"?v={cache_key}"
        )
        rendered_size = source_size
        source_exact = True
    else:
        rendered_url = f"/manuals/t/{tenant_slug}/{manual.id}/rev/{revision.id}/rendered.pdf?v={cache_key}"
        rendered_size = 0
        source_exact = False
    effective_date = revision.effective_date.isoformat() if revision.effective_date else None
    published_date = revision.published_at.date().isoformat() if revision.published_at else None
    created_date = revision.created_at.date().isoformat() if revision.created_at else None
    return {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "title": manual.title,
        "code": manual.code,
        "manual_type": manual.manual_type,
        "owner_role": manual.owner_role,
        "date": effective_date or published_date or created_date,
        "language": str(getattr(profile, "language", None) or "English"),
        "issue_number": revision.issue_number,
        "revision_number": revision.rev_number,
        "status": _status_value(revision),
        "is_published": is_published,
        "control_label": "Controlled publication" if is_published else "Uncontrolled draft",
        "source_type": source_type or None,
        "source_filename": revision.source_filename,
        "source_size_bytes": source_size,
        "source_page_count": revision.source_page_count,
        "source_url": rendered_url if source_exact else None,
        "rendered_pdf_url": rendered_url,
        "rendered_pdf_size_bytes": rendered_size,
        "download_filename": f"{manual.code}_Rev_{revision.rev_number or 'current'}.pdf",
        "reader_mode": "pdf" if source_type == "PDF" else "html",
        "image_only": image_only,
        "text_char_count": text_char_count,
        "citation_current": 0,
        "citation_total": 0,
        "subsidiary_count": 0,
        "cache_key": cache_key,
        "source_exact": source_exact,
        "form_policy": "READ_ONLY_PRESERVED",
        "section_count": len(sections),
    }


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-bootstrap")
def reader_bootstrap(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant, manual, revision, profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    sections = (
        db.query(models.ManualSection)
        .filter(models.ManualSection.revision_id == revision.id)
        .order_by(models.ManualSection.order_index.asc())
        .all()
    )
    source_path = _source_path(revision)
    cache_key = _cache_key(revision, source_path)
    etag = _etag(cache_key)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, max-age=30, stale-while-revalidate=300"},
        )
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=300"
    metadata = _reader_metadata(
        db,
        tenant_slug=tenant_slug,
        manual=manual,
        revision=revision,
        profile=profile,
        sections=sections,
    )
    return {
        "cache_key": cache_key,
        "metadata": metadata,
        "read": {
            "revision_id": revision.id,
            "status": _status_value(revision),
            "not_published": _status_value(revision) != "PUBLISHED",
            "manual": {
                "id": manual.id,
                "code": manual.code,
                "title": manual.title,
                "manual_type": manual.manual_type,
                "owner_role": manual.owner_role,
            },
            "revision": {
                "id": revision.id,
                "rev_number": revision.rev_number,
                "issue_number": revision.issue_number,
                "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
                "published_at": revision.published_at.isoformat() if revision.published_at else None,
                "source_filename": revision.source_filename,
                "source_type": _source_type(revision) or None,
                "source_mime_type": revision.source_mime_type,
                "source_page_count": revision.source_page_count,
                "source_available": bool(source_path),
                "source_url": metadata["source_url"],
            },
            "sections": [
                {
                    "id": section.id,
                    "heading": section.heading,
                    "anchor_slug": section.anchor_slug,
                    "level": section.level,
                    "page_start": int((section.metadata_json or {}).get("page_start") or 0) or None,
                    "page_end": int((section.metadata_json or {}).get("page_end") or 0) or None,
                }
                for section in sections
            ],
            "blocks": [],
            "progress": _progress_payload(db, revision.id, str(current_user.id)),
        },
        "acknowledgement": _acknowledgement_payload(db, revision.id, str(current_user.id)),
    }


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-metadata", include_in_schema=False)
def fast_reader_metadata(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, manual, revision, profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    sections = (
        db.query(models.ManualSection)
        .filter(models.ManualSection.revision_id == revision.id)
        .order_by(models.ManualSection.order_index.asc())
        .all()
    )
    return _reader_metadata(
        db,
        tenant_slug=tenant_slug,
        manual=manual,
        revision=revision,
        profile=profile,
        sections=sections,
    )


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-content")
def reader_content(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    section_id: list[str] = Query(default=[]),
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, _manual, revision, _profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    section_query = (
        db.query(models.ManualSection)
        .filter(models.ManualSection.revision_id == revision.id)
        .order_by(models.ManualSection.order_index.asc())
    )
    requested = list(dict.fromkeys(value for value in section_id if value))
    if requested:
        sections = section_query.filter(models.ManualSection.id.in_(requested)).all()
    else:
        sections = section_query.offset(start).limit(limit).all()
    section_ids = [section.id for section in sections]
    blocks = (
        db.query(models.ManualBlock)
        .filter(models.ManualBlock.section_id.in_(section_ids or ["-"]))
        .order_by(models.ManualBlock.section_id.asc(), models.ManualBlock.order_index.asc())
        .all()
    )
    return {
        "sections": [
            {
                "id": section.id,
                "heading": section.heading,
                "anchor_slug": section.anchor_slug,
                "level": section.level,
            }
            for section in sections
        ],
        "blocks": [
            {
                "section_id": block.section_id,
                "html": block.html_sanitized,
                "text": block.text_plain,
                "change_hash": block.change_hash,
            }
            for block in blocks
        ],
        "start": start,
        "limit": limit,
        "returned_sections": len(sections),
    }


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-search")
def reader_search(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=80, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, _manual, revision, _profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    needle = f"%{q.strip()}%"
    rows = (
        db.query(models.ManualSection, models.ManualBlock)
        .outerjoin(models.ManualBlock, models.ManualBlock.section_id == models.ManualSection.id)
        .filter(
            models.ManualSection.revision_id == revision.id,
            or_(
                models.ManualSection.heading.ilike(needle),
                models.ManualBlock.text_plain.ilike(needle),
            ),
        )
        .order_by(models.ManualSection.order_index.asc(), models.ManualBlock.order_index.asc())
        .limit(limit * 4)
        .all()
    )
    results: list[dict] = []
    seen: set[str] = set()
    for section, block in rows:
        if section.id in seen:
            continue
        seen.add(section.id)
        text = str(getattr(block, "text_plain", "") or "").strip()
        results.append(
            {
                "section_id": section.id,
                "anchor_slug": section.anchor_slug,
                "heading": section.heading,
                "level": section.level,
                "page_start": int((section.metadata_json or {}).get("page_start") or 0) or None,
                "snippet": text[:260] if text else "Section heading match",
            }
        )
        if len(results) >= limit:
            break
    return {"query": q.strip(), "items": results, "total": len(results)}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/reader-position")
def update_reader_position(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    payload: ReaderPositionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant, manual, revision, _profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    row = (
        db.query(models.ManualReaderProgress)
        .filter(
            models.ManualReaderProgress.revision_id == revision.id,
            models.ManualReaderProgress.user_id == current_user.id,
        )
        .first()
    )
    created = row is None
    if row is None:
        row = models.ManualReaderProgress(
            tenant_id=tenant.id,
            manual_id=manual.id,
            revision_id=revision.id,
            user_id=current_user.id,
        )
        db.add(row)
    if payload.section_id:
        row.last_section_id = payload.section_id
    if payload.anchor_slug:
        row.last_anchor_slug = payload.anchor_slug
    if payload.page_number:
        row.last_page_number = payload.page_number
    row.scroll_percent = payload.scroll_percent
    row.zoom_percent = payload.zoom_percent
    row.last_opened_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    if created:
        _audit(
            db,
            tenant.id,
            current_user.id,
            "revision.read",
            "manual_revision",
            revision.id,
            request,
            {"manual_id": manual.id, "source": "progressive-reader"},
        )
    db.commit()
    return {"status": "saved", "revision_id": revision.id}


def _iter_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(_STREAM_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _stream_source(path: Path, request: Request, *, filename: str, cache_key: str):
    size = path.stat().st_size
    etag = _etag(cache_key)
    common_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=31536000, immutable",
        "ETag": etag,
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Publication-Source": "exact-original",
        "X-AcroForm-Policy": "read-only",
    }
    if request.headers.get("if-none-match") == etag and not request.headers.get("range"):
        return Response(status_code=304, headers=common_headers)
    range_header = str(request.headers.get("range") or "").strip()
    if range_header:
        match = _RANGE_PATTERN.match(range_header)
        if not match:
            raise HTTPException(status_code=416, detail="Only one byte range is supported")
        first, last = match.groups()
        if not first and not last:
            raise HTTPException(status_code=416, detail="Invalid byte range")
        if not first:
            suffix = min(size, int(last))
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(first)
            end = min(size - 1, int(last) if last else size - 1)
        if start < 0 or start >= size or end < start:
            return Response(status_code=416, headers={**common_headers, "Content-Range": f"bytes */{size}"})
        headers = {
            **common_headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        }
        return StreamingResponse(
            _iter_file(path, start, end),
            status_code=206,
            media_type="application/pdf",
            headers=headers,
        )
    return StreamingResponse(
        _iter_file(path, 0, max(0, size - 1)),
        media_type="application/pdf",
        headers={**common_headers, "Content-Length": str(size)},
    )


@router.get("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/stream.pdf")
def stream_publication_pdf(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, manual, revision, _profile = _load_publication(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    if _source_type(revision) != "PDF":
        raise HTTPException(status_code=409, detail="The exact-source stream is available only for PDF revisions")
    path = _source_path(revision)
    if not path:
        raise HTTPException(status_code=404, detail="The publication source file is unavailable")
    cache_key = _cache_key(revision, path)
    safe_code = re.sub(r"[^A-Za-z0-9._-]+", "_", manual.code or "publication")
    safe_revision = re.sub(r"[^A-Za-z0-9._-]+", "_", revision.rev_number or "current")
    return _stream_source(
        path,
        request,
        filename=f"{safe_code}_Rev_{safe_revision}.pdf",
        cache_key=cache_key,
    )
