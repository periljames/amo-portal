"""Upgrade the disposable DMS browser fixture to a real 2,000-page PDF.

This runs only after the normal governed fixture has been seeded. It preserves
all document/workflow/custody metadata and replaces the immutable revision's
CI-only source bytes so the production reader is exercised at large-manual
scale without shipping synthetic documents into application code.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdf_canvas

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.manuals import models as manual_models  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402
from amodb.scripts.seed_document_governance_e2e import REVISION_ID  # noqa: E402


SCALE_PDF_PATH = Path("/tmp/amo-document-governance-reader-2000-pages.pdf")
SCALE_PDF_PAGES = 2_000
CHECKPOINTS = {100, 500, 1_000, 1_999}


def _build_scale_pdf() -> tuple[Path, str]:
    SCALE_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = pdf_canvas.Canvas(
        str(SCALE_PDF_PATH),
        pagesize=A4,
        invariant=1,
        pageCompression=1,
    )
    width, height = A4
    document.setTitle("AMO Portal 2000-page controlled reader scale fixture")

    for page_number in range(1, SCALE_PDF_PAGES + 1):
        document.setFont("Helvetica-Bold", 14)
        document.drawString(54, height - 68, "Document Governance Large Manual Scale Fixture")
        document.setFont("Helvetica", 10)
        document.drawString(54, height - 92, f"Controlled page {page_number} of {SCALE_PDF_PAGES}")
        document.drawString(
            54,
            height - 116,
            "This synthetic page exists only in disposable CI to prove bounded PDF rendering.",
        )
        if page_number in CHECKPOINTS:
            key = f"scale-checkpoint-{page_number}"
            document.bookmarkPage(key)
            document.addOutlineEntry(f"Scale checkpoint page {page_number}", key, level=0, closed=False)
            document.setFont("Helvetica-Bold", 12)
            document.drawString(54, height - 152, f"Scale checkpoint {page_number}")
        document.setFont("Helvetica", 8)
        document.drawRightString(width - 54, 38, f"DMS-CI-MOM · Rev 1 · Page {page_number}")
        document.showPage()

    document.save()
    content = SCALE_PDF_PATH.read_bytes()
    return SCALE_PDF_PATH.resolve(), hashlib.sha256(content).hexdigest()


def main() -> None:
    path, checksum = _build_scale_pdf()
    db = WriteSessionLocal()
    try:
        revision = (
            db.query(manual_models.ManualRevision)
            .filter(manual_models.ManualRevision.id == REVISION_ID)
            .one()
        )
        revision.source_type_enum = manual_models.ManualSourceType.PDF
        revision.source_filename = "document-governance-reader-2000-pages.pdf"
        revision.source_mime_type = "application/pdf"
        revision.source_storage_path = str(path)
        revision.source_sha256 = checksum
        revision.source_page_count = SCALE_PDF_PAGES
        # The row remains a published/immutable controlled revision; only the
        # disposable CI source fixture is replaced before the server starts.
        revision.published_at = revision.published_at or datetime.now(timezone.utc)
        db.commit()
        print(
            f"Reader scale fixture ready: revision={REVISION_ID} "
            f"pages={SCALE_PDF_PAGES} bytes={path.stat().st_size} sha256={checksum}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
