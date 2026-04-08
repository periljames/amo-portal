from __future__ import annotations

from datetime import datetime, timedelta, date
import hashlib
from uuid import uuid4
from html import escape
import json
import os
import re
import tempfile
import zipfile
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from amodb.database import get_db
from amodb.security import get_current_actor_id, get_current_active_user
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.models import AMO

from . import models
from .schemas import (
    AcknowledgeRequest,
    DiffSummaryOut,
    DocxPreviewOut,
    ExportCreate,
    LifecycleTransitionOut,
    LifecycleTransitionRequest,
    ManualCreate,
    ManualFeaturedEntry,
    ManualOut,
    MasterListEntry,
    OCRVerifyOut,
    PrintLogCreate,
    RevisionCreate,
    RevisionOut,
    StampOverlayOut,
    StampOverlayRequest,
    TransitionRequest,
    WorkflowOut,
)

router = APIRouter(prefix="/manuals", tags=["Manuals"], dependencies=[Depends(get_current_active_user)])

MAX_DOCX_UPLOAD_BYTES = 10 * 1024 * 1024


def _role_value(current_user: account_models.User) -> str:
    role = getattr(current_user, "role", None)
    return getattr(role, "value", str(role))


def _is_manual_control_user(current_user: account_models.User) -> bool:
    role_value = _role_value(current_user)
    return bool(
        getattr(current_user, "is_superuser", False)
        or role_value in {
            "AMO_ADMIN",
            "QUALITY_MANAGER",
            "QUALITY_INSPECTOR",
            "DOCUMENT_CONTROL_OFFICER",
        }
    )


def _require_manual_control_user(current_user: account_models.User) -> None:
    if not _is_manual_control_user(current_user):
        raise HTTPException(status_code=403, detail="Manual control privileges required")


def _apply_lifecycle_transition(
    *,
    rev: models.ManualRevision,
    manual: models.Manual | None,
    tenant: models.Tenant,
    action: str,
    actor_id: str | None,
    db: Session,
) -> tuple[models.ManualRevisionStatus, bool]:
    previous = rev.status_enum
    approval_chain_reset = False

    if action == "save_draft":
        rev.status_enum = models.ManualRevisionStatus.DRAFT
    elif action == "submit_for_review":
        if rev.status_enum != models.ManualRevisionStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Only draft revisions can be staged")
        rev.status_enum = models.ManualRevisionStatus.DEPARTMENT_REVIEW
    elif action == "verify_compliance":
        if rev.status_enum != models.ManualRevisionStatus.DEPARTMENT_REVIEW:
            raise HTTPException(status_code=400, detail="Revision must be staged before compliance review")
        rev.status_enum = models.ManualRevisionStatus.QUALITY_APPROVAL
    elif action == "sign_approval":
        if rev.status_enum != models.ManualRevisionStatus.QUALITY_APPROVAL:
            raise HTTPException(status_code=400, detail="Revision must be in-review before approval")
        rev.status_enum = models.ManualRevisionStatus.REGULATOR_SIGNOFF
        rev.authority_approval_ref = f"e-sign:{actor_id or 'system'}:{datetime.utcnow().isoformat()}"
    elif action == "publish":
        if rev.status_enum != models.ManualRevisionStatus.REGULATOR_SIGNOFF:
            raise HTTPException(status_code=400, detail="Revision must be approved before publication")
        if rev.requires_authority_approval_bool and not rev.ocr_verified_bool:
            raise HTTPException(status_code=400, detail="KCAA approval letter must be OCR-verified before publication")
        rev.status_enum = models.ManualRevisionStatus.PUBLISHED
        rev.published_at = datetime.utcnow()
        rev.immutable_locked = True
        previous_published = None
        if manual and manual.current_published_rev_id:
            previous_published = db.query(models.ManualRevision).filter(models.ManualRevision.id == manual.current_published_rev_id).first()
        if previous_published:
            previous_published.status_enum = models.ManualRevisionStatus.SUPERSEDED
            previous_published.superseded_by_rev_id = rev.id
        if manual:
            manual.current_published_rev_id = rev.id
        due_days = int((tenant.settings_json or {}).get("ack_due_days", 10))
        db.add(models.Acknowledgement(revision_id=rev.id, holder_user_id=rev.created_by, due_at=datetime.utcnow() + timedelta(days=due_days)))
        db.add(models.ManualAIHookEvent(tenant_id=tenant.id, revision_id=rev.id, event_name="revision.published", payload_json={"manual_id": rev.manual_id}))
    elif action == "reject_to_draft":
        if rev.status_enum not in {
            models.ManualRevisionStatus.DEPARTMENT_REVIEW,
            models.ManualRevisionStatus.QUALITY_APPROVAL,
            models.ManualRevisionStatus.REGULATOR_SIGNOFF,
        }:
            raise HTTPException(status_code=400, detail="Only staged/in-review/approved revisions can be rejected")
        rev.status_enum = models.ManualRevisionStatus.DRAFT
        rev.authority_approval_ref = None
        rev.published_at = None
        rev.immutable_locked = False
        approval_chain_reset = True
    else:
        raise HTTPException(status_code=400, detail="Unsupported lifecycle action")

    return previous, approval_chain_reset


def _validate_docx_upload(file: UploadFile, content: bytes) -> None:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX uploads are supported")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded DOCX is empty")
    if len(content) > MAX_DOCX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"DOCX file is too large (max {MAX_DOCX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            if "word/document.xml" not in set(zf.namelist()):
                raise HTTPException(status_code=400, detail="Invalid DOCX structure: word/document.xml missing")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid DOCX file") from exc


def _slugify_heading(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _clean_docx_text(value: str) -> str:
    text = (value or "").replace("\xa0", " ")
    text = re.sub(r"PAGEREF\s+_Toc\d+.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\\[huz]", " ", text)
    text = re.sub(r"_Toc\d+", " ", text)
    text = re.sub(r"TOC\s+\\o.*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _heading_level(style_name: str, text: str) -> int | None:
    style = (style_name or "").strip().lower()
    match = re.search(r"heading\s*(\d)", style)
    if match:
        return max(1, min(3, int(match.group(1))))
    if re.match(r"^\d+(?:\.\d+)*\s+.+", text) and len(text) <= 180:
        depth = min(3, text.split(" ", 1)[0].count(".") + 1)
        return depth
    if text.isupper() and 4 <= len(text) <= 120:
        return 1
    return None


def _normalize_manual_type(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper()
    for token in ["OMA", "CAME", "MEL", "MOE", "MTM", "MCM", "MPM", "CLM", "QMSM", "SMS", "AMP", "MM"]:
        if token in upper:
            return token
    return None


def _parse_date_string(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _extract_docx_content(content: bytes, filename: str | None = None) -> dict[str, object]:
    try:
        from docx import Document  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="DOCX parsing library unavailable") from exc

    doc = Document(BytesIO(content))
    paragraphs: list[dict[str, object]] = []
    headings: list[dict[str, object]] = []

    for paragraph in doc.paragraphs:
        raw = " ".join(run.text for run in paragraph.runs) or paragraph.text
        text = _clean_docx_text(raw)
        if not text:
            continue
        style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
        level = _heading_level(style_name, text)
        entry = {"text": text, "style": style_name, "level": level}
        paragraphs.append(entry)
        if level is not None:
            headings.append({"heading": text, "level": level})

    doc_title = _clean_docx_text(getattr(getattr(doc, "core_properties", None), "title", "") or "")
    joined = "\n".join(str(item["text"]) for item in paragraphs[:400])
    search_source = "\n".join(filter(None, [filename or "", doc_title, joined]))

    part_match = re.search(r"\b([A-Z]{1,4}/[A-Z0-9]{1,8}/\d{1,4}(?:/\d{1,4})?)\b", search_source, flags=re.IGNORECASE)
    rev_match = re.search(r"(?:\brev(?:ision)?\s*(?:no\.?|number)?\s*[:#-]?\s*)([A-Z0-9._-]+)", search_source, flags=re.IGNORECASE)
    issue_match = re.search(r"(?:\bissue\s*(?:no\.?|number)?\s*[:#-]?\s*)([A-Z0-9._-]+)", search_source, flags=re.IGNORECASE)
    date_match = re.search(r"(?:effective(?:\s+date)?|effectivity)\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})", search_source, flags=re.IGNORECASE)

    title = doc_title or (headings[0]["heading"] if headings else (paragraphs[0]["text"] if paragraphs else (filename or "Untitled manual")))
    manual_type = _normalize_manual_type(search_source) or "GENERAL"
    excerpt = "\n\n".join(str(item["text"]) for item in paragraphs[:12])

    return {
        "paragraphs": paragraphs,
        "headings": headings[:40],
        "metadata": {
            "part_number": (part_match.group(1).upper() if part_match else None),
            "manual_type": manual_type,
            "title": str(title)[:255],
            "revision_number": (rev_match.group(1).strip() if rev_match else None),
            "issue_number": (issue_match.group(1).strip() if issue_match else None),
            "effective_date": (date_match.group(1).strip() if date_match else None),
        },
        "excerpt": excerpt,
    }


def _build_manual_sections(docx_payload: dict[str, object]) -> list[dict[str, object]]:
    paragraphs = list(docx_payload.get("paragraphs", []))
    metadata = dict(docx_payload.get("metadata", {}))
    section_specs: list[dict[str, object]] = []
    current = {
        "heading": str(metadata.get("title") or "Overview"),
        "level": 1,
        "paragraphs": [],
    }

    for item in paragraphs:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        level = item.get("level")
        if level is not None:
            if current["paragraphs"] or section_specs == []:
                section_specs.append(current)
            current = {
                "heading": text[:255],
                "level": int(level),
                "paragraphs": [],
            }
            continue
        current["paragraphs"].append(text)

    if current["paragraphs"] or not section_specs:
        section_specs.append(current)

    normalized: list[dict[str, object]] = []
    for index, spec in enumerate(section_specs, start=1):
        heading = str(spec.get("heading") or f"Section {index}")[:255]
        normalized.append({
            "heading": heading,
            "level": max(1, min(3, int(spec.get("level") or 1))),
            "anchor_slug": _slugify_heading(heading, f"section-{index}"),
            "paragraphs": list(spec.get("paragraphs") or []),
        })
    return normalized


def _build_prosemirror_json(section_specs: list[dict[str, object]]) -> dict:
    content: list[dict[str, object]] = []
    for index, spec in enumerate(section_specs, start=1):
        heading = str(spec.get("heading") or f"Section {index}")
        level = max(1, min(3, int(spec.get("level") or 1)))
        section_id = str(spec.get("anchor_slug") or f"sec-{index:03d}")
        content.append({
            "type": "heading",
            "attrs": {"level": level, "section_id": section_id},
            "content": [{"type": "text", "text": heading}],
        })
        for para in list(spec.get("paragraphs") or []):
            text = str(para).strip()
            if not text:
                continue
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            })
    return {"type": "doc", "content": content}


def _extract_docx_paragraphs(content: bytes) -> list[str]:
    payload = _extract_docx_content(content)
    return [str(item.get("text") or "") for item in list(payload.get("paragraphs", []))]


def _request_ip_device(request: Request) -> str:
    return f"{request.client.host if request.client else 'unknown'}::{request.headers.get('user-agent', 'n/a')}"


_TABLE_EXISTS_CACHE: dict[str, bool] = {}


def _table_exists(db: Session, table_name: str) -> bool:
    bind = db.get_bind()
    cache_key = f"{id(bind)}::{table_name}"
    if cache_key in _TABLE_EXISTS_CACHE:
        return _TABLE_EXISTS_CACHE[cache_key]
    exists = inspect(bind).has_table(table_name)
    _TABLE_EXISTS_CACHE[cache_key] = exists
    return exists


def _query_audit_rows(db: Session, *criterion, limit: int | None = None):
    if not _table_exists(db, "manual_audit_log"):
        return []
    query = db.query(models.ManualAuditLog).filter(*criterion).order_by(models.ManualAuditLog.at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def _extract_text_from_pdf_bytes(content: bytes) -> str:
    try:
        import fitz  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="OCR libraries unavailable") from exc

    doc = fitz.open(stream=content, filetype="pdf")
    text_parts: list[str] = []
    for page in doc:
        text_parts.append(page.get_text("text"))
    text = "\n".join(text_parts).strip()
    if len(text) >= 80:
        return text

    ocr_parts: list[str] = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        ocr_parts.append(pytesseract.image_to_string(image))
    return "\n".join(ocr_parts).strip()


def _extract_kcaa_reference(text: str) -> str | None:
    patterns = [
        r"(?:\bref(?:erence)?\b|\bfile\s*ref\b)\s*[:#-]?\s*([A-Z0-9/.-]{4,})",
        r"\b(KCAA/[A-Z0-9/.-]{3,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_first_date(text: str) -> date | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})", text)
    return _parse_date_string(match.group(1)) if match else None


def _normalize_ref(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _render_revision_pdf(revision: models.ManualRevision, sections: list[models.ManualSection], section_blocks: dict[str, list[models.ManualBlock]], *, signer_name: str, signer_role: str, stamp_label: str, tenant_slug: str, manual_id: str) -> tuple[str, str]:
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.units import mm  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="PDF render library unavailable") from exc

    output_dir = os.path.join(tempfile.gettempdir(), "amo_manual_stamps", tenant_slug, manual_id, revision.id)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"stamped-{uuid4().hex}.pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    left = 18 * mm
    top = height - 18 * mm
    bottom = 22 * mm
    line_height = 5 * mm

    def new_page(page_heading: str) -> tuple[float, int]:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, height - 14 * mm, page_heading)
        c.setFont("Helvetica", 9)
        c.drawRightString(width - 18 * mm, height - 14 * mm, f"Rev {revision.rev_number}")
        return top, 1

    y, page_no = new_page("Controlled Manual")
    c.setFont("Helvetica", 9)

    for section in sections:
        blocks = section_blocks.get(section.id, [])
        if y < bottom + 25 * mm:
            c.showPage()
            page_no += 1
            y, _ = new_page(section.heading)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, section.heading)
        y -= line_height
        c.setFont("Helvetica", 9)
        for block in blocks:
            for line in re.findall(r".{1,100}(?:\s+|$)", block.text_plain or ""):
                chunk = line.strip()
                if not chunk:
                    continue
                if y < bottom + 20 * mm:
                    c.showPage()
                    page_no += 1
                    y, _ = new_page(section.heading)
                    c.setFont("Helvetica", 9)
                c.drawString(left + 4 * mm, y, chunk[:120])
                y -= line_height
            y -= 1.5 * mm

    stamp_x = width - 76 * mm
    stamp_y = bottom + 8 * mm
    c.setStrokeColorRGB(0.72, 0.13, 0.13)
    c.setLineWidth(1.4)
    c.roundRect(stamp_x, stamp_y, 58 * mm, 24 * mm, 4 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(stamp_x + 29 * mm, stamp_y + 17 * mm, stamp_label[:40])
    c.setFont("Helvetica", 8)
    c.drawCentredString(stamp_x + 29 * mm, stamp_y + 11 * mm, signer_name[:36])
    c.drawCentredString(stamp_x + 29 * mm, stamp_y + 7 * mm, signer_role[:36])
    c.drawCentredString(stamp_x + 29 * mm, stamp_y + 3 * mm, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    c.save()

    with open(output_path, "rb") as handle:
        sha256 = hashlib.sha256(handle.read()).hexdigest()
    return output_path, sha256

def _tenant_by_slug(db: Session, tenant_slug: str) -> models.Tenant:
    tenant = db.query(models.Tenant).filter(models.Tenant.slug == tenant_slug).first()
    if tenant:
        return tenant

    amo = db.query(AMO).filter(AMO.login_slug == tenant_slug).first()
    if not amo:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant = db.query(models.Tenant).filter(models.Tenant.amo_id == amo.id).first()
    if tenant:
        if tenant.slug != tenant_slug:
            tenant.slug = tenant_slug
        if tenant.name != amo.name:
            tenant.name = amo.name
        return tenant

    tenant = models.Tenant(amo_id=amo.id, slug=tenant_slug, name=amo.name, settings_json={"ack_due_days": 10})
    db.add(tenant)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        tenant = db.query(models.Tenant).filter(models.Tenant.amo_id == amo.id).first()
        if tenant:
            if tenant.slug != tenant_slug:
                tenant.slug = tenant_slug
            if tenant.name != amo.name:
                tenant.name = amo.name
            return tenant
        raise
    return tenant


def _audit(db: Session, tenant_id: str, actor_id: str | None, action: str, entity_type: str, entity_id: str, request: Request, diff: dict | None = None) -> None:
    if not _table_exists(db, "manual_audit_log"):
        return
    db.add(models.ManualAuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_device=_request_ip_device(request),
        diff_json=diff or {},
    ))


@router.get("/t/{tenant_slug}", response_model=list[ManualOut])
def list_manuals(tenant_slug: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    return db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id).all()


@router.post("/t/{tenant_slug}", response_model=ManualOut)
def create_manual(tenant_slug: str, payload: ManualCreate, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = models.Manual(tenant_id=tenant.id, code=payload.code, title=payload.title, manual_type=payload.manual_type, owner_role=payload.owner_role)
    db.add(manual)
    db.flush()
    _audit(db, tenant.id, get_current_actor_id(), "manual.created", "manual", manual.id, request)
    db.commit()
    db.refresh(manual)
    return manual









@router.post("/t/{tenant_slug}/upload-docx/preview", response_model=DocxPreviewOut)
async def preview_docx_upload(
    tenant_slug: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _ = _tenant_by_slug(db, tenant_slug)
    if str(current_user.role) == "AccountRole.VIEW_ONLY" or getattr(current_user, "role", None) == account_models.AccountRole.VIEW_ONLY:
        raise HTTPException(status_code=403, detail="Insufficient privileges to upload manuals")
    content = await file.read()
    _validate_docx_upload(file, content)
    parsed = _extract_docx_content(content, file.filename)
    paragraphs = [str(item.get("text") or "") for item in list(parsed.get("paragraphs", []))]
    headings = [str(item.get("heading") or "") for item in list(parsed.get("headings", []))]
    metadata = dict(parsed.get("metadata", {}))
    heading = str(metadata.get("title") or (headings[0] if headings else (paragraphs[0] if paragraphs else file.filename or "Untitled manual")))
    return DocxPreviewOut(
        filename=file.filename or "manual.docx",
        heading=heading[:255],
        paragraph_count=len(paragraphs),
        sample=paragraphs[:20],
        outline=headings[:20],
        metadata=metadata,
        excerpt=str(parsed.get("excerpt") or ""),
    )


@router.post("/t/{tenant_slug}/upload-docx")
async def upload_docx_revision(
    tenant_slug: str,
    request: Request,
    code: str = Form(...),
    title: str = Form(...),
    rev_number: str = Form(...),
    manual_type: str = Form("GENERAL"),
    owner_role: str = Form("Library"),
    issue_number: str = Form(""),
    effective_date: str | None = Form(None),
    change_log: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    if str(current_user.role) == "AccountRole.VIEW_ONLY" or getattr(current_user, "role", None) == account_models.AccountRole.VIEW_ONLY:
        raise HTTPException(status_code=403, detail="Insufficient privileges to upload manuals")
    content = await file.read()
    _validate_docx_upload(file, content)

    parsed = _extract_docx_content(content, file.filename)
    metadata = dict(parsed.get("metadata", {}))
    section_specs = _build_manual_sections(parsed)
    paragraph_count = sum(len(list(spec.get("paragraphs") or [])) for spec in section_specs)

    manual_code = (str(metadata.get("part_number") or code) or "").strip().upper()
    manual_title = (str(metadata.get("title") or title) or file.filename or "Untitled manual").strip()
    manual_type_value = (str(metadata.get("manual_type") or manual_type) or "GENERAL").strip().upper()
    issue_value = (str(metadata.get("issue_number") or issue_number) or "00").strip()
    rev_value = (str(metadata.get("revision_number") or rev_number) or "00").strip()
    effective_value = _parse_date_string(str(metadata.get("effective_date") or effective_date or "").strip())

    manual = db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id, models.Manual.code == manual_code).first()
    if not manual:
        manual = models.Manual(
            tenant_id=tenant.id,
            code=manual_code,
            title=manual_title,
            manual_type=manual_type_value,
            owner_role=(owner_role.strip() or "Library"),
        )
        db.add(manual)
        db.flush()
    else:
        manual.title = manual_title or manual.title
        manual.manual_type = manual_type_value or manual.manual_type
        if owner_role.strip():
            manual.owner_role = owner_role.strip()

    rev = models.ManualRevision(
        manual_id=manual.id,
        rev_number=rev_value,
        issue_number=issue_value,
        effective_date=effective_value,
        created_by=get_current_actor_id(),
        status_enum=models.ManualRevisionStatus.DRAFT,
        source_filename=file.filename,
        manual_uuid=f"manual::{manual.id}::rev::{uuid4().hex[:12]}",
        notes=(f"Uploaded source: {file.filename}" + (f"\nChange log: {change_log.strip()}" if change_log and change_log.strip() else "")),
    )
    db.add(rev)
    db.flush()

    created_sections: list[models.ManualSection] = []
    all_blocks = 0
    for section_index, spec in enumerate(section_specs, start=1):
        section = models.ManualSection(
            revision_id=rev.id,
            order_index=section_index,
            heading=str(spec.get("heading") or f"Section {section_index}")[:255],
            anchor_slug=str(spec.get("anchor_slug") or f"section-{section_index}"),
            level=int(spec.get("level") or 1),
            metadata_json={"source": "docx-upload", "filename": file.filename, "paragraphs": len(list(spec.get("paragraphs") or []))},
        )
        db.add(section)
        db.flush()
        created_sections.append(section)
        for block_index, para in enumerate(list(spec.get("paragraphs") or []), start=1):
            safe_text = str(para).strip()
            if not safe_text:
                continue
            all_blocks += 1
            html_text = f"<p>{escape(safe_text)}</p>"
            hash_source = f"{rev.id}:{section.id}:{block_index}:{safe_text}".encode("utf-8")
            db.add(models.ManualBlock(
                section_id=section.id,
                order_index=block_index,
                block_type="paragraph",
                html_sanitized=html_text,
                text_plain=safe_text,
                change_hash=hashlib.sha256(hash_source).hexdigest(),
            ))

    prose_json = _build_prosemirror_json(section_specs)
    checksum = hashlib.sha256(json.dumps(prose_json, sort_keys=True).encode("utf-8")).hexdigest()
    previous_version = (
        db.query(models.DocumentVersion)
        .filter(models.DocumentVersion.document_id == manual.id)
        .order_by(models.DocumentVersion.created_at.desc())
        .first()
    )
    if previous_version:
        previous_version.is_active = False

    current_version = models.DocumentVersion(
        document_id=manual.id,
        revision_id=rev.id,
        version_label=f"Rev {rev.rev_number}",
        content_json=prose_json,
        delta_patch={
            "from_version_id": previous_version.id if previous_version else None,
            "changed_nodes": len(prose_json.get("content", [])),
        },
        checksum_sha256=checksum,
        state="Draft",
        is_active=True,
    )
    db.add(current_version)
    db.flush()

    for section in created_sections:
        words = max(1, len(section.heading.split()))
        db.add(models.DocumentSection(
            document_version_id=current_version.id,
            section_id=section.anchor_slug,
            heading=section.heading[:255],
            word_count=words,
            min_reading_time=max(1, words // 180),
        ))

    _audit(db, tenant.id, get_current_actor_id(), "revision.docx_uploaded", "manual_revision", rev.id, request, {
        "filename": file.filename,
        "paragraphs": paragraph_count,
        "sections": len(created_sections),
        "metadata": metadata,
    })
    db.commit()
    return {"manual_id": manual.id, "revision_id": rev.id, "status": rev.status_enum.value, "paragraphs": paragraph_count}


@router.get("/t/{tenant_slug}/{manual_id}/revisions", response_model=list[RevisionOut])
def list_revisions(tenant_slug: str, manual_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    revisions = (
        db.query(models.ManualRevision)
        .join(models.Manual, models.Manual.id == models.ManualRevision.manual_id)
        .filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id)
        .order_by(models.ManualRevision.created_at.desc())
        .all()
    )
    return [RevisionOut(**rev.__dict__, status_enum=rev.status_enum.value) for rev in revisions]

@router.post("/t/{tenant_slug}/{manual_id}/revisions", response_model=RevisionOut)
def create_revision(tenant_slug: str, manual_id: str, payload: RevisionCreate, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")
    rev = models.ManualRevision(
        manual_id=manual.id,
        rev_number=payload.rev_number,
        issue_number=payload.issue_number,
        effective_date=payload.effective_date,
        notes=payload.notes,
        requires_authority_approval_bool=payload.requires_authority_approval_bool,
        created_by=get_current_actor_id(),
    )
    db.add(rev)
    db.flush()
    _audit(db, tenant.id, get_current_actor_id(), "revision.created", "manual_revision", rev.id, request, {"rev_number": payload.rev_number})
    db.commit()
    db.refresh(rev)
    return RevisionOut(**rev.__dict__, status_enum=rev.status_enum.value)


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/workflow", response_model=WorkflowOut)
def transition_revision(tenant_slug: str, manual_id: str, rev_id: str, payload: TransitionRequest, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")

    transitions = {
        "submit_department_review": models.ManualRevisionStatus.DEPARTMENT_REVIEW,
        "approve_quality": models.ManualRevisionStatus.QUALITY_APPROVAL,
        "approve_regulator": models.ManualRevisionStatus.REGULATOR_SIGNOFF,
        "archive": models.ManualRevisionStatus.ARCHIVED,
    }
    if payload.action == "publish":
        if rev.requires_authority_approval_bool and rev.status_enum != models.ManualRevisionStatus.REGULATOR_SIGNOFF:
            raise HTTPException(status_code=400, detail="Regulator sign-off required before publishing")
        rev.status_enum = models.ManualRevisionStatus.PUBLISHED
        rev.published_at = datetime.utcnow()
        rev.immutable_locked = True
        manual = db.query(models.Manual).filter(models.Manual.id == manual_id).first()
        previous = None
        if manual and manual.current_published_rev_id:
            previous = db.query(models.ManualRevision).filter(models.ManualRevision.id == manual.current_published_rev_id).first()
        if previous:
            previous.status_enum = models.ManualRevisionStatus.SUPERSEDED
            previous.superseded_by_rev_id = rev.id
        if manual:
            manual.current_published_rev_id = rev.id
        due_days = int((tenant.settings_json or {}).get("ack_due_days", 10))
        db.add(models.Acknowledgement(revision_id=rev.id, holder_user_id=rev.created_by, due_at=datetime.utcnow() + timedelta(days=due_days)))
        db.add(models.ManualAIHookEvent(tenant_id=tenant.id, revision_id=rev.id, event_name="revision.published", payload_json={"manual_id": manual_id}))
    else:
        new_status = transitions.get(payload.action)
        if not new_status:
            raise HTTPException(status_code=400, detail="Unsupported action")
        rev.status_enum = new_status

    _audit(db, tenant.id, get_current_actor_id(), f"revision.workflow.{payload.action}", "manual_revision", rev.id, request, {"comment": payload.comment})
    db.commit()

    history = _query_audit_rows(db, models.ManualAuditLog.entity_id == rev.id, limit=20)
    return WorkflowOut(revision_id=rev.id, status=rev.status_enum.value, requires_authority_approval=rev.requires_authority_approval_bool, history=[{"action": item.action, "at": item.at.isoformat(), "actor_id": item.actor_id} for item in history])




@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/lifecycle/transition", response_model=LifecycleTransitionOut)
def transition_revision_lifecycle(
    tenant_slug: str,
    manual_id: str,
    rev_id: str,
    payload: LifecycleTransitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manual_control_user(current_user)
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    manual = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()

    previous, reset = _apply_lifecycle_transition(
        rev=rev,
        manual=manual,
        tenant=tenant,
        action=payload.action,
        actor_id=get_current_actor_id(),
        db=db,
    )
    _audit(db, tenant.id, get_current_actor_id(), f"revision.lifecycle.{payload.action}", "manual_revision", rev.id, request, {"comment": payload.comment})
    db.commit()
    return LifecycleTransitionOut(
        revision_id=rev.id,
        state=rev.status_enum.value,
        previous_state=previous.value,
        approval_chain_reset=reset,
    )


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/read")
def read_revision(tenant_slug: str, manual_id: str, rev_id: str, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev or not manual:
        raise HTTPException(status_code=404, detail="Revision not found")
    sections = db.query(models.ManualSection).filter(models.ManualSection.revision_id == rev_id).order_by(models.ManualSection.order_index.asc()).all()
    blocks = db.query(models.ManualBlock).join(models.ManualSection, models.ManualSection.id == models.ManualBlock.section_id).filter(models.ManualSection.revision_id == rev_id).order_by(models.ManualBlock.order_index.asc()).all()
    _audit(db, tenant.id, get_current_actor_id(), "revision.read", "manual_revision", rev.id, request, {"manual_id": manual.id, "section_count": len(sections)})
    db.commit()
    return {
        "revision_id": rev.id,
        "status": rev.status_enum.value,
        "not_published": rev.status_enum != models.ManualRevisionStatus.PUBLISHED,
        "manual": {"id": manual.id, "code": manual.code, "title": manual.title, "manual_type": manual.manual_type},
        "sections": [{"id": s.id, "heading": s.heading, "anchor_slug": s.anchor_slug, "level": s.level} for s in sections],
        "blocks": [{"section_id": b.section_id, "html": b.html_sanitized, "text": b.text_plain, "change_hash": b.change_hash} for b in blocks],
    }


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/diff", response_model=DiffSummaryOut)
def revision_diff(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    _ = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    diff = db.query(models.RevisionDiffIndex).filter(models.RevisionDiffIndex.revision_id == rev_id).first()
    if not diff:
        diff = models.RevisionDiffIndex(revision_id=rev_id, baseline_revision_id=None, summary_json={"changed_sections": 0, "changed_blocks": 0, "added": 0, "removed": 0})
        db.add(diff)
        db.commit()
        db.refresh(diff)
    return DiffSummaryOut(revision_id=diff.revision_id, baseline_revision_id=diff.baseline_revision_id, summary_json=diff.summary_json)


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/workflow", response_model=WorkflowOut)
def get_workflow(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    history = _query_audit_rows(db, models.ManualAuditLog.entity_id == rev.id, limit=20)
    return WorkflowOut(revision_id=rev.id, status=rev.status_enum.value, requires_authority_approval=rev.requires_authority_approval_bool, history=[{"action": item.action, "at": item.at.isoformat(), "actor_id": item.actor_id} for item in history])


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/acknowledge")
def acknowledge_revision(tenant_slug: str, manual_id: str, rev_id: str, payload: AcknowledgeRequest, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    ack = db.query(models.Acknowledgement).filter(models.Acknowledgement.revision_id == rev_id, models.Acknowledgement.holder_user_id == actor_id).first()
    if not ack:
        ack = models.Acknowledgement(revision_id=rev_id, holder_user_id=actor_id, due_at=datetime.utcnow() + timedelta(days=10))
        db.add(ack)
    ack.acknowledged_at = datetime.utcnow()
    ack.acknowledgement_text = payload.acknowledgement_text
    ack.status_enum = "ACKNOWLEDGED"
    _audit(db, tenant.id, actor_id, "revision.acknowledged", "acknowledgement", ack.id, request)
    db.commit()
    return {"status": "ok", "acknowledged_at": ack.acknowledged_at}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/exports")
def create_export(tenant_slug: str, manual_id: str, rev_id: str, payload: ExportCreate, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    source = f"{tenant_slug}:{manual_id}:{rev_id}:{payload.version_label}:{payload.controlled_bool}:{payload.watermark_uncontrolled_bool}:{datetime.utcnow().isoformat()}"
    sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    exp = models.PrintExport(
        revision_id=rev_id,
        controlled_bool=payload.controlled_bool,
        watermark_uncontrolled_bool=payload.watermark_uncontrolled_bool,
        generated_by=actor_id,
        storage_uri=f"s3://manuals/{tenant_slug}/{manual_id}/{rev_id}/{sha}.pdf",
        sha256=sha,
        render_profile_json={"change_bars": True, "watermark_uncontrolled": payload.watermark_uncontrolled_bool},
        version_label=payload.version_label,
    )
    db.add(exp)
    db.flush()
    _audit(db, tenant.id, actor_id, "revision.exported", "print_export", exp.id, request)
    db.commit()
    return {"id": exp.id, "sha256": exp.sha256, "storage_uri": exp.storage_uri}


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/exports")
def list_exports(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    _ = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    rows = db.query(models.PrintExport).filter(models.PrintExport.revision_id == rev_id).order_by(models.PrintExport.generated_at.desc()).all()
    return [{"id": r.id, "controlled": r.controlled_bool, "watermark_uncontrolled": r.watermark_uncontrolled_bool, "generated_at": r.generated_at, "sha256": r.sha256} for r in rows]


@router.post("/exports/{export_id}/print-log")
def create_print_log(export_id: str, payload: PrintLogCreate, db: Session = Depends(get_db)):
    exp = db.query(models.PrintExport).filter(models.PrintExport.id == export_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Export not found")
    log = models.PrintLog(export_id=export_id, printed_by=get_current_actor_id(), controlled_copy_no=payload.controlled_copy_no, recipient=payload.recipient, purpose=payload.purpose)
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id, "status": log.status_enum}


@router.post("/exports/{export_id}/recall")
def recall_print(export_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.PrintLog).filter(models.PrintLog.export_id == export_id).all()
    for row in rows:
        row.status_enum = "RECALLED"
    db.commit()
    return {"updated": len(rows)}


@router.get("/t/{tenant_slug}/master-list", response_model=list[MasterListEntry])
def master_list(tenant_slug: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manuals = db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id).all()
    result = []
    for manual in manuals:
        current_rev = None
        pending = 0
        if manual.current_published_rev_id:
            current_rev = db.query(models.ManualRevision).filter(models.ManualRevision.id == manual.current_published_rev_id).first()
            pending = db.query(models.Acknowledgement).filter(models.Acknowledgement.revision_id == manual.current_published_rev_id, models.Acknowledgement.status_enum != "ACKNOWLEDGED").count()
        result.append(MasterListEntry(manual_id=manual.id, code=manual.code, title=manual.title, current_revision=current_rev.rev_number if current_rev else None, current_status=current_rev.status_enum.value if current_rev else "NO_PUBLISHED_REV", pending_ack_count=pending))
    return result

@router.get("/t/{tenant_slug}/featured", response_model=list[ManualFeaturedEntry])
def featured_manuals(tenant_slug: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manuals = db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id).all()
    usage: dict[str, int] = {manual.id: 0 for manual in manuals}
    if _table_exists(db, "manual_audit_log"):
        rows = db.query(models.ManualAuditLog).filter(models.ManualAuditLog.tenant_id == tenant.id, models.ManualAuditLog.action == "revision.read").all()
        revision_to_manual: dict[str, str] = {}
        revisions = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.tenant_id == tenant.id).all()
        for rev in revisions:
            revision_to_manual[rev.id] = rev.manual_id
        for row in rows:
            manual_id = None
            if isinstance(row.diff_json, dict):
                manual_id = row.diff_json.get("manual_id")
            manual_id = manual_id or revision_to_manual.get(row.entity_id)
            if manual_id:
                usage[manual_id] = usage.get(manual_id, 0) + 1
    ranked = sorted(manuals, key=lambda item: (-usage.get(item.id, 0), item.code))[:3]
    out: list[ManualFeaturedEntry] = []
    for manual in ranked:
        current_rev = None
        if manual.current_published_rev_id:
            current_rev = db.query(models.ManualRevision).filter(models.ManualRevision.id == manual.current_published_rev_id).first()
        out.append(ManualFeaturedEntry(
            manual_id=manual.id,
            code=manual.code,
            title=manual.title,
            manual_type=manual.manual_type,
            current_revision=current_rev.rev_number if current_rev else None,
            open_count=usage.get(manual.id, 0),
        ))
    return out


@router.get("/t/{tenant_slug}/{manual_id}", response_model=ManualOut)
def get_manual(tenant_slug: str, manual_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")
    return manual


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/processing/run")
def run_processor(tenant_slug: str, manual_id: str, rev_id: str, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    _audit(db, tenant.id, actor_id, "revision.processing.run", "manual_revision", rev_id, request, {"stage": "queued"})
    db.commit()
    return {"status": "queued", "job_id": str(uuid4())}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/ocr/run")
def run_ocr(tenant_slug: str, manual_id: str, rev_id: str, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    _audit(db, tenant.id, actor_id, "revision.ocr.run", "manual_revision", rev_id, request, {"stage": "queued"})
    db.commit()
    return {"status": "queued", "job_id": str(uuid4())}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/ocr/verify", response_model=OCRVerifyOut)
async def verify_ocr_letter(
    tenant_slug: str,
    manual_id: str,
    rev_id: str,
    request: Request,
    file: UploadFile = File(...),
    typed_ref: str | None = Form(None),
    typed_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload the KCAA approval letter as PDF")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Approval letter PDF is empty")
    extracted = _extract_text_from_pdf_bytes(content)
    detected_ref = _extract_kcaa_reference(extracted)
    detected_date = _extract_first_date(extracted)
    typed_date_obj = _parse_date_string(typed_date)
    ref_match = bool(detected_ref and typed_ref and _normalize_ref(detected_ref) == _normalize_ref(typed_ref))
    date_match = bool(detected_date and typed_date_obj and detected_date == typed_date_obj)
    verified = ref_match and date_match

    rev.ocr_detected_ref = detected_ref
    rev.ocr_detected_date = detected_date
    rev.ocr_verified_bool = verified
    rev.ocr_verified_at = datetime.utcnow() if verified else None
    if verified and detected_ref:
        rev.authority_approval_ref = detected_ref

    _audit(db, tenant.id, get_current_actor_id(), "revision.ocr.verified", "manual_revision", rev.id, request, {
        "filename": file.filename,
        "detected_ref": detected_ref,
        "detected_date": detected_date.isoformat() if detected_date else None,
        "typed_ref": typed_ref,
        "typed_date": typed_date,
        "verified": verified,
    })
    db.commit()
    return OCRVerifyOut(
        revision_id=rev.id,
        detected_ref=detected_ref,
        detected_date=detected_date,
        typed_ref=typed_ref,
        typed_date=typed_date_obj,
        ref_match=ref_match,
        date_match=date_match,
        verified=verified,
        text_excerpt=extracted[:1200],
    )


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/stamp-overlay", response_model=StampOverlayOut)
def create_stamped_overlay(
    tenant_slug: str,
    manual_id: str,
    rev_id: str,
    payload: StampOverlayRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    sections = db.query(models.ManualSection).filter(models.ManualSection.revision_id == rev_id).order_by(models.ManualSection.order_index.asc()).all()
    blocks = db.query(models.ManualBlock).join(models.ManualSection, models.ManualSection.id == models.ManualBlock.section_id).filter(models.ManualSection.revision_id == rev_id).order_by(models.ManualBlock.order_index.asc()).all()
    block_map: dict[str, list[models.ManualBlock]] = {}
    for block in blocks:
        block_map.setdefault(block.section_id, []).append(block)
    output_path, sha256 = _render_revision_pdf(
        rev,
        sections,
        block_map,
        signer_name=payload.signer_name,
        signer_role=payload.signer_role,
        stamp_label=payload.stamp_label,
        tenant_slug=tenant_slug,
        manual_id=manual_id,
    )
    exp = models.PrintExport(
        revision_id=rev.id,
        controlled_bool=payload.controlled_bool,
        watermark_uncontrolled_bool=not payload.controlled_bool,
        generated_by=get_current_actor_id(),
        generated_at=datetime.utcnow(),
        storage_uri=output_path,
        sha256=sha256,
        render_profile_json={"stamped": True, "signer_name": payload.signer_name, "signer_role": payload.signer_role, "stamp_label": payload.stamp_label},
        version_label=f"stamped-rev-{rev.rev_number}",
    )
    db.add(exp)
    rev.stamped_export_uri = output_path
    _audit(db, tenant.id, get_current_actor_id(), "revision.stamp_overlay.created", "manual_revision", rev.id, request, {"export_sha256": sha256, "storage_uri": output_path})
    db.commit()
    db.refresh(exp)
    return StampOverlayOut(revision_id=rev.id, export_id=exp.id, storage_uri=output_path, sha256=sha256)


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/processing/status")
def processing_status(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    _ = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    rows = _query_audit_rows(db, models.ManualAuditLog.entity_id == rev_id, models.ManualAuditLog.action.in_(["revision.processing.run", "revision.ocr.run"]), limit=1)
    row = rows[0] if rows else None
    if not row:
        return {"revision_id": rev_id, "stage": "idle", "actor_id": None, "at": None}
    return {"revision_id": rev_id, "stage": row.diff_json.get("stage", "queued"), "actor_id": row.actor_id, "at": row.at}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/outline/generate")
def generate_outline(tenant_slug: str, manual_id: str, rev_id: str, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    count = db.query(models.ManualSection).filter(models.ManualSection.revision_id == rev_id).count()
    _audit(db, tenant.id, actor_id, "revision.outline.generated", "manual_revision", rev_id, request, {"generated": count})
    db.commit()
    return {"status": "ok", "generated": count}
