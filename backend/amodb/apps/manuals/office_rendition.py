"""Exact-source Office PDF rendition ledger and bounded visual-integrity hints."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from sqlalchemy.orm import Session

from . import models


def now() -> datetime:
    return datetime.now(timezone.utc)


def _row(db: Session, revision_id: str) -> models.ManualRendition | None:
    return db.query(models.ManualRendition).filter(
        models.ManualRendition.revision_id == revision_id,
        models.ManualRendition.rendition_type == "PDF",
    ).first()


def begin_rendition(db: Session, revision: models.ManualRevision) -> models.ManualRendition:
    manual = db.query(models.Manual).filter(models.Manual.id == revision.manual_id).one()
    tenant = db.query(models.Tenant).filter(models.Tenant.id == manual.tenant_id).one()
    existing = _row(db, revision.id)
    if existing and existing.source_sha256 != str(revision.source_sha256 or ""):
        raise ValueError("The retained Office revision checksum changed unexpectedly")
    row = existing or models.ManualRendition(
        amo_id=tenant.amo_id, manual_id=manual.id, revision_id=revision.id,
        source_sha256=str(revision.source_sha256 or ""), rendition_type="PDF",
    )
    row.status = "PROCESSING"
    row.attempts = int(row.attempts or 0) + 1
    row.started_at = now()
    row.finished_at = None
    row.error = None
    if not existing:
        db.add(row)
    db.flush()
    return row


def _embedded_media_count(source: Path) -> int:
    if source.suffix.lower() != ".docx":
        return 0
    try:
        with ZipFile(source) as pkg:
            return sum(1 for name in pkg.namelist()
                       if name.startswith("word/media/") and not name.endswith("/"))
    except (OSError, ValueError):
        return 0


def complete_rendition(db: Session, row: models.ManualRendition, revision, derivative) -> None:
    import fitz
    with fitz.open(str(derivative.path)) as pdf:
        images = sum(len(pdf.load_page(page).get_images(full=True))
                     for page in range(pdf.page_count))
        pages = pdf.page_count
    source_images = _embedded_media_count(Path(revision.source_storage_path))
    warning = (
        "Word contains embedded media but the PDF has no raster image objects. "
        "Inspect the pages; some artwork may legitimately be vector graphics."
        if source_images and images == 0 else None
    )
    previous_pdf_sha = row.pdf_sha256
    row.status = "REVIEW_REQUIRED" if warning else "READY"
    row.storage_path = str(derivative.path)
    row.source_sha256 = derivative.source_sha256
    row.pdf_sha256 = derivative.pdf_sha256
    row.converter = "LibreOffice Writer PDF"
    row.page_count = pages
    row.source_media_count = source_images
    row.rendered_image_count = images
    row.warning = warning
    row.error = None
    row.finished_at = now()
    # A regenerated artifact must be re-verified, even when its filename is unchanged.
    if not previous_pdf_sha or previous_pdf_sha != derivative.pdf_sha256:
        row.verified_at = None
        row.verified_by = None
        row.verification_note = None
    db.add(row)


def fail_rendition(db: Session, row: models.ManualRendition, exc: Exception) -> None:
    row.status = "FAILED"
    row.error = str(exc)[:500] or "Office PDF conversion failed"
    row.finished_at = now()
    db.add(row)


def rendition_payload(db: Session, revision: models.ManualRevision) -> dict:
    row = _row(db, revision.id)
    if not row:
        return {}
    from .office_layout import office_layout_pdf_path, office_layout_pdf_checksum, OfficeLayoutError
    path = office_layout_pdf_path(revision)
    valid = bool(path and path.is_file())
    if valid and row.pdf_sha256:
        try:
            valid = office_layout_pdf_checksum(path) == row.pdf_sha256
        except (OfficeLayoutError, OSError):
            valid = False
    status = row.status
    if status in {"READY", "REVIEW_REQUIRED"} and not valid:
        status = "FAILED"
    return {
        "status": status,
        "error": row.error if status == "FAILED" else None,
        "warning": row.warning,
        "source_sha256": row.source_sha256,
        "pdf_sha256": row.pdf_sha256 if valid else None,
        "page_count": row.page_count if valid else None,
        "source_media_count": row.source_media_count,
        "rendered_image_count": row.rendered_image_count,
        "attempts": row.attempts,
        "verified_at": row.verified_at.isoformat() if valid and row.verified_at else None,
        "verified_by": row.verified_by if valid else None,
    }
