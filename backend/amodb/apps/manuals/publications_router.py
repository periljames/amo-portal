from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import textwrap

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models
from .router_legacy import _tenant_by_slug


router = APIRouter(
    prefix="/manuals",
    tags=["Publications Reader"],
    dependencies=[Depends(get_current_active_user)],
)

_A4_WIDTH = 595.0
_A4_HEIGHT = 842.0
_MARGIN_X = 54.0
_TOP_Y = 64.0
_BOTTOM_Y = 790.0


def _load_publication(db: Session, tenant_slug: str, manual_id: str, rev_id: str):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = (
        db.query(models.Manual)
        .filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id)
        .first()
    )
    revision = (
        db.query(models.ManualRevision)
        .filter(
            models.ManualRevision.id == rev_id,
            models.ManualRevision.manual_id == manual_id,
        )
        .first()
    )
    if not manual or not revision:
        raise HTTPException(status_code=404, detail="Publication revision not found")
    return tenant, manual, revision


def _revision_sections(db: Session, revision_id: str):
    return (
        db.query(models.ManualSection)
        .filter(models.ManualSection.revision_id == revision_id)
        .order_by(models.ManualSection.order_index.asc())
        .all()
    )


def _revision_blocks(db: Session, revision_id: str):
    return (
        db.query(models.ManualBlock)
        .join(models.ManualSection, models.ManualSection.id == models.ManualBlock.section_id)
        .filter(models.ManualSection.revision_id == revision_id)
        .order_by(models.ManualSection.order_index.asc(), models.ManualBlock.order_index.asc())
        .all()
    )


def _source_type(revision: models.ManualRevision) -> str:
    source_type = getattr(revision, "source_type_enum", None)
    return getattr(source_type, "value", str(source_type or "")).upper()


def _source_path(revision: models.ManualRevision) -> Path | None:
    raw = str(getattr(revision, "source_storage_path", "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() and path.is_file() else None


def _pdf_safe(value: str | None) -> str:
    text = str(value or "")
    text = text.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2013": "-",
                "\u2014": "-",
                "\u2022": "-",
                "\u00a0": " ",
            }
        )
    )
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.encode("latin-1", "replace").decode("latin-1")


class _PublicationPdfFlow:
    def __init__(self, title: str, revision_label: str):
        try:
            import fitz  # type: ignore
        except Exception as exc:  # pragma: no cover - deployment dependency guard
            raise HTTPException(status_code=500, detail="PDF renderer is unavailable") from exc
        self.fitz = fitz
        self.document = fitz.open()
        self.title = _pdf_safe(title)
        self.revision_label = _pdf_safe(revision_label)
        self.page = None
        self.y = _TOP_Y
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.document.new_page(width=_A4_WIDTH, height=_A4_HEIGHT)
        self.y = _TOP_Y
        self.page.insert_text(
            (_MARGIN_X, 31),
            self.title[:92],
            fontsize=8.5,
            fontname="hebo",
        )
        self.page.insert_text(
            (_A4_WIDTH - 150, 31),
            self.revision_label[:30],
            fontsize=8.5,
            fontname="helv",
        )
        self.page.draw_line(
            (_MARGIN_X, 40),
            (_A4_WIDTH - _MARGIN_X, 40),
            width=0.6,
        )

    def _ensure_space(self, required: float) -> None:
        if self.y + required > _BOTTOM_Y:
            self._new_page()

    def spacer(self, points: float = 8.0) -> None:
        self._ensure_space(points)
        self.y += points

    def write(self, value: str | None, *, size: float = 10.0, bold: bool = False, indent: float = 0.0) -> None:
        text = _pdf_safe(value).strip()
        if not text:
            return
        available_width = max(220.0, _A4_WIDTH - (_MARGIN_X * 2) - indent)
        average_char_width = max(4.5, size * 0.52)
        wrap_width = max(28, int(available_width / average_char_width))
        leading = max(12.0, size * 1.35)
        paragraphs = text.splitlines() or [text]
        for paragraph in paragraphs:
            lines = textwrap.wrap(
                paragraph,
                width=wrap_width,
                replace_whitespace=True,
                drop_whitespace=True,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]
            for line in lines:
                self._ensure_space(leading)
                self.page.insert_text(
                    (_MARGIN_X + indent, self.y),
                    line,
                    fontsize=size,
                    fontname="hebo" if bold else "helv",
                )
                self.y += leading

    def finish(self) -> bytes:
        total = len(self.document)
        for index, page in enumerate(self.document):
            page.draw_line(
                (_MARGIN_X, _A4_HEIGHT - 40),
                (_A4_WIDTH - _MARGIN_X, _A4_HEIGHT - 40),
                width=0.4,
            )
            page.insert_text(
                (_MARGIN_X, _A4_HEIGHT - 24),
                "Controlled publication - verify current revision in the AMO Portal before use.",
                fontsize=7.5,
                fontname="helv",
            )
            page.insert_text(
                (_A4_WIDTH - 102, _A4_HEIGHT - 24),
                f"Page {index + 1} of {total}",
                fontsize=7.5,
                fontname="helv",
            )
        payload = self.document.tobytes(garbage=4, deflate=True)
        self.document.close()
        return payload


def _render_revision_pdf(db: Session, manual: models.Manual, revision: models.ManualRevision) -> bytes:
    flow = _PublicationPdfFlow(
        manual.title or manual.code or "Publication",
        f"Issue {revision.issue_number or '-'} | Rev {revision.rev_number or '-'}",
    )
    flow.write(manual.title or manual.code or "Publication", size=19, bold=True)
    flow.write(manual.code, size=11, bold=True)
    flow.spacer(5)
    flow.write(f"Issue: {revision.issue_number or '-'}", size=9.5)
    flow.write(f"Revision: {revision.rev_number or '-'}", size=9.5)
    if revision.effective_date:
        flow.write(f"Effective date: {revision.effective_date.isoformat()}", size=9.5)
    flow.write(f"Status: {getattr(revision.status_enum, 'value', revision.status_enum)}", size=9.5)
    flow.spacer(14)

    sections = _revision_sections(db, revision.id)
    blocks = _revision_blocks(db, revision.id)
    blocks_by_section: dict[str, list[models.ManualBlock]] = {}
    for block in blocks:
        blocks_by_section.setdefault(block.section_id, []).append(block)

    if not sections:
        flow.write("No rendered publication content is available for this revision.", size=10)
    for section in sections:
        level = max(1, min(3, int(section.level or 1)))
        heading_size = {1: 15.0, 2: 13.0, 3: 11.5}[level]
        flow.spacer(10 if level == 1 else 6)
        flow.write(section.heading or "Untitled section", size=heading_size, bold=True, indent=(level - 1) * 8)
        flow.spacer(3)
        section_blocks = blocks_by_section.get(section.id, [])
        if not section_blocks:
            flow.write("No text was extracted for this section.", size=9.5, indent=8)
        for block in section_blocks:
            flow.write(block.text_plain or "", size=9.5, indent=8)
            flow.spacer(5)

    return flow.finish()


def _download_filename(manual: models.Manual, revision: models.ManualRevision) -> str:
    code = re.sub(r"[^A-Za-z0-9._-]+", "_", manual.code or "publication").strip("_") or "publication"
    revision_label = re.sub(r"[^A-Za-z0-9._-]+", "_", revision.rev_number or "current").strip("_") or "current"
    return f"{code}_Rev_{revision_label}.pdf"


def _is_image_only_pdf(revision: models.ManualRevision, text_char_count: int) -> bool:
    if _source_type(revision) != "PDF":
        return False
    page_count = max(1, int(getattr(revision, "source_page_count", 0) or 1))
    return text_char_count < max(80, page_count * 16)


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/reader-metadata")
def reader_metadata(
    tenant_slug: str,
    manual_id: str,
    rev_id: str,
    db: Session = Depends(get_db),
):
    _tenant, manual, revision = _load_publication(db, tenant_slug, manual_id, rev_id)
    blocks = _revision_blocks(db, revision.id)
    text_char_count = sum(len((block.text_plain or "").strip()) for block in blocks)
    source_path = _source_path(revision)
    source_size = source_path.stat().st_size if source_path else 0
    source_type = _source_type(revision)
    image_only = _is_image_only_pdf(revision, text_char_count)

    if source_type == "PDF" and source_path:
        rendered_size = source_size
    else:
        rendered_size = len(_render_revision_pdf(db, manual, revision))

    effective_date = revision.effective_date.isoformat() if revision.effective_date else None
    published_date = revision.published_at.date().isoformat() if revision.published_at else None
    created_date = revision.created_at.date().isoformat() if revision.created_at else None
    rendered_url = f"/manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/rendered.pdf"

    return {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "title": manual.title,
        "code": manual.code,
        "manual_type": manual.manual_type,
        "owner_role": manual.owner_role,
        "date": effective_date or published_date or created_date,
        "language": "English",
        "issue_number": revision.issue_number,
        "revision_number": revision.rev_number,
        "source_type": source_type or None,
        "source_filename": revision.source_filename,
        "source_size_bytes": source_size,
        "source_page_count": revision.source_page_count,
        "source_url": f"/manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/source" if source_path else None,
        "rendered_pdf_url": rendered_url,
        "rendered_pdf_size_bytes": rendered_size,
        "download_filename": _download_filename(manual, revision),
        "reader_mode": "pdf" if image_only else "html",
        "image_only": image_only,
        "text_char_count": text_char_count,
        "citation_current": 0,
        "citation_total": 0,
        "subsidiary_count": 0,
    }


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/rendered.pdf")
def rendered_publication_pdf(
    tenant_slug: str,
    manual_id: str,
    rev_id: str,
    db: Session = Depends(get_db),
):
    _tenant, manual, revision = _load_publication(db, tenant_slug, manual_id, rev_id)
    filename = _download_filename(manual, revision)
    source_path = _source_path(revision)
    if _source_type(revision) == "PDF" and source_path:
        return FileResponse(
            path=str(source_path),
            media_type="application/pdf",
            filename=filename,
            headers={"Cache-Control": "private, max-age=60"},
        )

    payload = _render_revision_pdf(db, manual, revision)
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
            "Cache-Control": "private, max-age=60",
        },
    )
