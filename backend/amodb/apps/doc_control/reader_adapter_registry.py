"""Declarative format negotiation for the governed Publications reader.

The registry describes the bounded rendering path that actually exists in the
portal. It does not imply native Office editing. Non-PDF office/image sources use
controlled derivatives plus semantic/OCR aids where ingestion produced them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class ReaderAdapter:
    name: str
    source_types: tuple[str, ...]
    mime_types: tuple[str, ...]
    extensions: tuple[str, ...]
    renderer: str
    location_adapter: str
    selection_support: str
    source_exact: bool
    derivative: bool
    search: str
    compare: str
    ocr_mode: str
    supports_layout: bool

    def payload(self) -> dict:
        return asdict(self)


PDF = ReaderAdapter(
    name="PDF_CANONICAL",
    source_types=("PDF",),
    mime_types=("application/pdf",),
    extensions=("pdf",),
    renderer="PDF_V3",
    location_adapter="PDF_CANONICAL_PAGE",
    selection_support="NATIVE_TEXT_IF_PRESENT",
    source_exact=True,
    derivative=False,
    search="PDF_TEXT_OR_OCR_AID",
    compare="SEMANTIC_STRUCTURE_AND_CHECKSUM",
    ocr_mode="AID_WHEN_IMAGE_ONLY",
    supports_layout=True,
)

OFFICE_DOCUMENT = ReaderAdapter(
    name="OFFICE_DOCUMENT_DERIVATIVE",
    source_types=("DOCX", "ODT", "DOC", "RTF"),
    mime_types=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "application/msword",
        "application/rtf",
    ),
    extensions=("docx", "odt", "doc", "rtf"),
    renderer="DERIVATIVE_PDF_OR_SEMANTIC_HTML",
    location_adapter="SEMANTIC_SECTION_BLOCK",
    selection_support="SEMANTIC_TEXT",
    source_exact=False,
    derivative=True,
    search="SEMANTIC_TEXT",
    compare="SEMANTIC_STRUCTURE",
    ocr_mode="NONE",
    supports_layout=True,
)

SPREADSHEET = ReaderAdapter(
    name="SPREADSHEET_DERIVATIVE",
    source_types=("XLSX", "ODS", "XLS", "CSV"),
    mime_types=(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.ms-excel",
        "text/csv",
    ),
    extensions=("xlsx", "ods", "xls", "csv"),
    renderer="DERIVATIVE_PDF_OR_DOWNLOAD",
    location_adapter="SPREADSHEET_SHEET_CELL",
    selection_support="CELL_RANGE_WHEN_INDEXED",
    source_exact=False,
    derivative=True,
    search="INDEXED_CELL_TEXT",
    compare="INDEXED_STRUCTURE",
    ocr_mode="NONE",
    supports_layout=True,
)

PRESENTATION = ReaderAdapter(
    name="PRESENTATION_DERIVATIVE",
    source_types=("PPTX", "ODP", "PPT"),
    mime_types=(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.presentation",
        "application/vnd.ms-powerpoint",
    ),
    extensions=("pptx", "odp", "ppt"),
    renderer="DERIVATIVE_PDF_OR_DOWNLOAD",
    location_adapter="PRESENTATION_SLIDE_OBJECT",
    selection_support="SLIDE_OBJECT_WHEN_INDEXED",
    source_exact=False,
    derivative=True,
    search="INDEXED_SLIDE_TEXT",
    compare="INDEXED_STRUCTURE",
    ocr_mode="AID_FOR_RASTER_SLIDES",
    supports_layout=True,
)

MARKUP_TEXT = ReaderAdapter(
    name="MARKUP_TEXT_SEMANTIC",
    source_types=("HTML", "HTM", "MARKDOWN", "MD", "TXT", "TEXT"),
    mime_types=("text/html", "text/markdown", "text/plain"),
    extensions=("html", "htm", "md", "markdown", "txt"),
    renderer="SEMANTIC_HTML",
    location_adapter="SEMANTIC_SECTION_BLOCK",
    selection_support="SEMANTIC_TEXT",
    source_exact=False,
    derivative=False,
    search="SEMANTIC_TEXT",
    compare="SEMANTIC_STRUCTURE",
    ocr_mode="NONE",
    supports_layout=False,
)

IMAGE = ReaderAdapter(
    name="IMAGE_DERIVATIVE",
    source_types=("TIFF", "TIF", "PNG", "JPEG", "JPG"),
    mime_types=("image/tiff", "image/png", "image/jpeg"),
    extensions=("tiff", "tif", "png", "jpeg", "jpg"),
    renderer="DERIVATIVE_PDF_IMAGE",
    location_adapter="IMAGE_REGION",
    selection_support="IMAGE_REGION",
    source_exact=False,
    derivative=True,
    search="OCR_AID_ONLY",
    compare="IMAGE_CHECKSUM_AND_OCR_AID",
    ocr_mode="AID_REQUIRED_FOR_TEXT",
    supports_layout=True,
)

FALLBACK = ReaderAdapter(
    name="UNSUPPORTED_SAFE_FALLBACK",
    source_types=(),
    mime_types=(),
    extensions=(),
    renderer="DOWNLOAD_ONLY",
    location_adapter="FILE_IDENTITY_ONLY",
    selection_support="NONE",
    source_exact=False,
    derivative=False,
    search="NONE",
    compare="CHECKSUM_ONLY",
    ocr_mode="NONE",
    supports_layout=False,
)

ADAPTERS: tuple[ReaderAdapter, ...] = (PDF, OFFICE_DOCUMENT, SPREADSHEET, PRESENTATION, MARKUP_TEXT, IMAGE)


def _normalise(values: Iterable[str | None]) -> set[str]:
    return {str(value or "").strip().lower() for value in values if str(value or "").strip()}


def resolve_adapter(*, source_type: str | None, mime_type: str | None, filename: str | None) -> ReaderAdapter:
    source = str(source_type or "").strip().upper()
    mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    extension = str(filename or "").rsplit(".", 1)[-1].lower() if "." in str(filename or "") else ""
    for adapter in ADAPTERS:
        if source and source in adapter.source_types:
            return adapter
        if mime and mime in _normalise(adapter.mime_types):
            return adapter
        if extension and extension in _normalise(adapter.extensions):
            return adapter
    return FALLBACK


def supported_format_catalogue() -> list[dict]:
    return [adapter.payload() for adapter in ADAPTERS] + [FALLBACK.payload()]
