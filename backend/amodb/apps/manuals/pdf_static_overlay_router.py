from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from typing import Any

import pymupdf
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.knowledge_execution_scope import can_execute_profile
from amodb.apps.doc_control.pdfium_service import PdfEngineError
from amodb.apps.doc_control.workspace_service import is_control_user
from amodb.database import get_db
from amodb.security import get_current_active_user

from .pdf_reader_router import (
    _SIGNATURE_UNAVAILABLE,
    _engine_http_error,
    _inspection,
    _load_direct_context,
    _source_path,
)


router = APIRouter(prefix="/manuals", tags=["Controlled Static PDF Forms"])

_MAX_OVERLAYS = 300
_MAX_TEXT_LENGTH = 4000
_MIN_FONT_SIZE = 6.0
_MAX_FONT_SIZE = 24.0
_OVERLAY_EXECUTION_TYPES = {
    "PDF_ACROFORM",
    "HYBRID",
    "PORTAL_FORM",
    "DOWNLOADABLE_TEMPLATE",
}


@dataclass(frozen=True)
class StaticOverlay:
    identifier: str
    name: str
    page: int
    x: float
    y: float
    width: float
    height: float
    text: str
    font_size: float
    multiline: bool
    align: int


def _number(value: Any, *, minimum: float, maximum: float, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Static PDF field {field} must be numeric") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"Static PDF field {field} must be between {minimum} and {maximum}",
        )
    return parsed


def _integer(value: Any, *, minimum: int, maximum: int, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Static PDF field {field} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"Static PDF field {field} must be between {minimum} and {maximum}",
        )
    return parsed


def _profile_overlay_schema(profile) -> dict[str, Any]:
    schema = dict(getattr(profile, "schema_json", None) or {})
    overlay = schema.get("pdf_overlay")
    return dict(overlay) if isinstance(overlay, dict) else {}


def static_overlay_capabilities(
    user: account_models.User,
    profile,
    *,
    has_javascript: bool,
    is_dynamic_xfa: bool,
    encrypted: bool,
) -> dict[str, Any]:
    control = is_control_user(user)
    execution_allowed = bool(
        profile
        and str(getattr(profile, "execution_type", "") or "").upper() in _OVERLAY_EXECUTION_TYPES
        and can_execute_profile(user, profile)
    )
    signature_required = bool(getattr(profile, "requires_signature", False))
    safe_source = not has_javascript and not is_dynamic_xfa and not encrypted
    allowed = bool((control or execution_allowed) and safe_source and not signature_required)
    return {
        "can_overlay_fill": allowed,
        "can_configure_overlay": bool(control and safe_source and not signature_required),
        "overlay_schema": _profile_overlay_schema(profile),
        "overlay_download_mode": "COMPLETED_PAGES",
        "overlay_reason": (
            None
            if allowed
            else _SIGNATURE_UNAVAILABLE
            if signature_required
            else "Scripted, dynamic-XFA, or encrypted PDFs cannot use the static form editor"
            if not safe_source
            else "Static PDF form execution is outside your current scope"
        ),
    }


def _schema_fields(profile) -> dict[str, dict[str, Any]]:
    raw = _profile_overlay_schema(profile).get("fields", [])
    fields: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, list):
        return fields
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or item.get("name") or f"field-{index}").strip()
        if identifier:
            fields[identifier] = item
    return fields


def _client_items(raw: str) -> tuple[list[dict[str, Any]], bool]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Static PDF entries must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Static PDF entries must be a JSON object")
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail="Static PDF entries must contain an items array")
    if len(items) > _MAX_OVERLAYS:
        raise HTTPException(status_code=413, detail=f"A maximum of {_MAX_OVERLAYS} static PDF fields is allowed")
    if not all(isinstance(item, dict) for item in items):
        raise HTTPException(status_code=422, detail="Every static PDF entry must be an object")
    return items, bool(payload.get("completed_only", True))


def _normalized_overlay(
    item: dict[str, Any],
    *,
    page_count: int,
    schema_item: dict[str, Any] | None,
    allow_free_position: bool,
    index: int,
) -> StaticOverlay | None:
    source = schema_item if schema_item is not None else item
    identifier = str(item.get("id") or item.get("name") or source.get("id") or source.get("name") or f"field-{index}")
    name = str(source.get("name") or identifier)[:128]
    text = str(item.get("text") or "").replace("\x00", "").strip()
    if not text:
        return None
    if len(text) > _MAX_TEXT_LENGTH:
        raise HTTPException(status_code=413, detail=f"Static PDF field {name} exceeds {_MAX_TEXT_LENGTH} characters")
    if schema_item is None and not allow_free_position:
        raise HTTPException(status_code=403, detail=f"Static PDF field {identifier} is not part of the controlled form schema")

    page = _integer(source.get("page"), minimum=1, maximum=page_count, field=f"{name}.page")
    x = _number(source.get("x"), minimum=0.0, maximum=0.995, field=f"{name}.x")
    y = _number(source.get("y"), minimum=0.0, maximum=0.995, field=f"{name}.y")
    width = _number(source.get("width", 0.2), minimum=0.005, maximum=1.0, field=f"{name}.width")
    height = _number(source.get("height", 0.04), minimum=0.005, maximum=1.0, field=f"{name}.height")
    if x + width > 1.001 or y + height > 1.001:
        raise HTTPException(status_code=422, detail=f"Static PDF field {name} extends outside page {page}")
    font_size = _number(
        source.get("font_size", 10),
        minimum=_MIN_FONT_SIZE,
        maximum=_MAX_FONT_SIZE,
        field=f"{name}.font_size",
    )
    alignment = str(source.get("align") or "left").lower()
    align = {"left": 0, "center": 1, "right": 2}.get(alignment, 0)
    return StaticOverlay(
        identifier=identifier[:128],
        name=name,
        page=page,
        x=x,
        y=y,
        width=width,
        height=height,
        text=text,
        font_size=font_size,
        multiline=bool(source.get("multiline", True)),
        align=align,
    )


def _parse_overlays(
    raw: str,
    *,
    page_count: int,
    profile,
    allow_free_position: bool,
) -> tuple[list[StaticOverlay], bool]:
    items, completed_only = _client_items(raw)
    schema = _schema_fields(profile)
    overlays: list[StaticOverlay] = []
    for index, item in enumerate(items):
        identifier = str(item.get("id") or item.get("name") or "")
        schema_item = schema.get(identifier) if identifier else None
        overlay = _normalized_overlay(
            item,
            page_count=page_count,
            schema_item=schema_item,
            allow_free_position=allow_free_position,
            index=index,
        )
        if overlay is not None:
            overlays.append(overlay)
    if not overlays:
        raise HTTPException(status_code=409, detail="Type at least one value onto the PDF before downloading it")
    return overlays, completed_only


def _insert_overlay(page: Any, overlay: StaticOverlay) -> None:
    page_rect = page.rect
    rect = pymupdf.Rect(
        page_rect.x0 + page_rect.width * overlay.x,
        page_rect.y0 + page_rect.height * overlay.y,
        page_rect.x0 + page_rect.width * (overlay.x + overlay.width),
        page_rect.y0 + page_rect.height * (overlay.y + overlay.height),
    )
    font_size = overlay.font_size
    text = overlay.text if overlay.multiline else re.sub(r"\s+", " ", overlay.text)
    while font_size >= _MIN_FONT_SIZE:
        result = page.insert_textbox(
            rect,
            text,
            fontsize=font_size,
            fontname="helv",
            color=(0, 0, 0),
            align=overlay.align,
            overlay=True,
        )
        if result >= 0:
            return
        font_size -= 0.5
    raise HTTPException(
        status_code=422,
        detail=f"The value for {overlay.name} does not fit its configured PDF area",
    )


def _render_static_overlays(
    source_content: bytes,
    overlays: list[StaticOverlay],
    completed_only: bool,
) -> tuple[bytes, list[int]]:
    document = pymupdf.open(stream=source_content, filetype="pdf")
    source_page_count = document.page_count
    completed_pages = sorted({overlay.page for overlay in overlays})
    try:
        for overlay in overlays:
            _insert_overlay(document[overlay.page - 1], overlay)
        if completed_only:
            output = pymupdf.open()
            try:
                for page_number in completed_pages:
                    output.insert_pdf(
                        document,
                        from_page=page_number - 1,
                        to_page=page_number - 1,
                        links=True,
                        annots=True,
                    )
                content = output.tobytes(garbage=4, deflate=True, clean=True)
            finally:
                output.close()
        else:
            content = document.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        document.close()

    verification = pymupdf.open(stream=content, filetype="pdf")
    try:
        expected_pages = len(completed_pages) if completed_only else source_page_count
        if verification.page_count != expected_pages:
            raise HTTPException(status_code=500, detail="The generated static form PDF failed page-count verification")
    finally:
        verification.close()
    return content, completed_pages


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/static-overlay.pdf")
async def create_static_form_pdf(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    overlay_json: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _tenant, manual, revision, execution = _load_direct_context(
        db,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        revision_id=revision_id,
        current_user=current_user,
    )
    try:
        inspection = await run_in_threadpool(_inspection, revision)
    except PdfEngineError as exc:
        raise _engine_http_error(exc) from exc

    capability = static_overlay_capabilities(
        current_user,
        execution,
        has_javascript=inspection.has_javascript,
        is_dynamic_xfa=inspection.is_dynamic_xfa,
        encrypted=inspection.encrypted,
    )
    if not capability["can_overlay_fill"]:
        raise HTTPException(status_code=403, detail=capability["overlay_reason"] or "Static PDF form execution is unavailable")

    overlays, completed_only = _parse_overlays(
        overlay_json,
        page_count=inspection.page_count,
        profile=execution,
        allow_free_position=bool(capability["can_configure_overlay"]),
    )
    source_content = await run_in_threadpool(_source_path(revision).read_bytes)
    content, completed_pages = await run_in_threadpool(
        _render_static_overlays,
        source_content,
        overlays,
        completed_only,
    )
    output_sha256 = hashlib.sha256(content).hexdigest()
    safe_code = re.sub(r"[^A-Za-z0-9._-]+", "_", str(manual.code or "FORM"))
    suffix = "FILLED_PAGES" if completed_only else "FILLED_COPY"
    filename = f"{safe_code}_{suffix}.pdf"
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PDF-Template-SHA256": inspection.source_sha256,
        "X-PDF-Output-SHA256": output_sha256,
        "X-PDF-Page-Count": str(len(completed_pages) if completed_only else inspection.page_count),
        "X-PDF-Selected-Pages": ",".join(str(page) for page in completed_pages),
        "X-PDF-Overlay-Count": str(len(overlays)),
    }
    return StreamingResponse(io.BytesIO(content), media_type="application/pdf", headers=headers)
