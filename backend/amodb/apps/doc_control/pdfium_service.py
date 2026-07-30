from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


MAX_PDF_BYTES = int(os.getenv("PDFIUM_MAX_INPUT_BYTES", str(100 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.getenv("PDFIUM_MAX_PAGES", "5000"))
PROCESS_TIMEOUT_SECONDS = int(os.getenv("PDFIUM_PROCESS_TIMEOUT_SECONDS", "90"))
WORK_ROOT = Path(os.getenv("PDFIUM_WORK_DIR", "uploads/pdfium-work")).resolve()

_PDF_NAME_ESCAPE = re.compile(r"#([0-9A-Fa-f]{2})")
_ACTION_NAME_PATTERN = re.compile(r"/(?:JavaScript|JS|OpenAction|AA)(?=[\s/<>{}\[\]()])", re.IGNORECASE)
_ACTION_CONTAINER_PATTERN = re.compile(r"/(?:A|Next)(?=[\s/<>{}\[\]()])|/Type\s*/Action\b", re.IGNORECASE)
_ACTION_SUBTYPE_PATTERN = re.compile(r"/S\s*/([A-Za-z0-9#]+)", re.IGNORECASE)
_SAFE_ACTION_SUBTYPES = {"goto", "uri"}
_DANGEROUS_ACTION_SUBTYPES = {
    "javascript",
    "js",
    "launch",
    "submitform",
    "importdata",
    "gotor",
    "gotoe",
    "named",
    "rendition",
    "richmediaexecute",
    "setocgstate",
    "sound",
    "movie",
    "hide",
    "resetform",
    "trans",
}


class PdfEngineError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class PdfInspection:
    engine: str
    engine_version: str
    source_sha256: str
    page_count: int
    form_type: int
    has_acroform: bool
    has_javascript: bool
    is_dynamic_xfa: bool
    encrypted: bool
    can_flatten: bool
    unsupported_reason: str | None = None
    template_fingerprint: dict[str, Any] | None = None


@dataclass(frozen=True)
class PdfFlattenResult:
    content: bytes
    engine: str
    engine_version: str
    source_sha256: str
    output_sha256: str
    page_count: int
    form_type: int
    flattened_pages: int
    unchanged_pages: int

    def metadata(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("content", None)
        return payload


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_input(content: bytes) -> None:
    if not content or not content.startswith(b"%PDF"):
        raise PdfEngineError("PDF_INVALID", "A valid PDF working copy is required")
    if len(content) > MAX_PDF_BYTES:
        raise PdfEngineError(
            "PDF_TOO_LARGE",
            f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
            status_code=413,
        )


def _safe_work_root() -> Path:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    root = WORK_ROOT.resolve()
    if not root.is_dir():
        raise PdfEngineError("PDF_WORK_DIR_INVALID", "The PDF processing work directory is unavailable", status_code=500)
    return root


def _decode_pdf_name_escapes(value: str) -> str:
    return _PDF_NAME_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), value)


def _normalize_text_token(value: Any) -> str:
    """Preserve all semantic glyphs while normalizing Unicode and whitespace."""

    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(normalized.split())


def _rect_payload(value: Any) -> list[float]:
    return [
        round(float(value.x0), 1),
        round(float(value.y0), 1),
        round(float(value.x1), 1),
        round(float(value.y1), 1),
    ]


def _bbox_payload(value: Any) -> list[float]:
    values = list(value or (0, 0, 0, 0))
    return [round(float(component), 1) for component in values[:4]]


def _rects_intersect(left: list[float], right: list[float], tolerance: float = 1.0) -> bool:
    if len(left) != 4 or len(right) != 4:
        return False
    return not (
        left[2] <= right[0] - tolerance
        or left[0] >= right[2] + tolerance
        or left[3] <= right[1] - tolerance
        or left[1] >= right[3] + tolerance
    )


def _rounded_color(value: Any) -> list[float] | None:
    if value is None:
        return None
    return [round(float(component), 3) for component in value]


def _geometry_payload(value: Any) -> Any:
    """Return a stable JSON-safe representation of PyMuPDF path geometry."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {str(key): _geometry_payload(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_geometry_payload(item) for item in value]
    if all(hasattr(value, attr) for attr in ("x0", "y0", "x1", "y1")):
        return {
            "rect": [
                round(float(value.x0), 3),
                round(float(value.y0), 3),
                round(float(value.x1), 3),
                round(float(value.y1), 3),
            ]
        }
    if all(hasattr(value, attr) for attr in ("x", "y")):
        return {"point": [round(float(value.x), 3), round(float(value.y), 3)]}
    try:
        return [_geometry_payload(item) for item in value]
    except TypeError:
        return str(value)


def _drawing_signature(drawing: dict[str, Any]) -> str:
    payload = {
        "type": str(drawing.get("type") or ""),
        "rect": _rect_payload(drawing["rect"]),
        "items": _geometry_payload(drawing.get("items") or []),
        "fill": _rounded_color(drawing.get("fill")),
        "color": _rounded_color(drawing.get("color")),
        "width": round(float(drawing.get("width") or 0), 2),
        "close_path": bool(drawing.get("closePath")),
        "dashes": str(drawing.get("dashes") or ""),
        "line_cap": _geometry_payload(drawing.get("lineCap")),
        "line_join": _geometry_payload(drawing.get("lineJoin")),
        "fill_opacity": round(float(drawing.get("fill_opacity") or 0), 3),
        "stroke_opacity": round(float(drawing.get("stroke_opacity") or 0), 3),
        "layer": str(drawing.get("layer") or ""),
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _text_appearance_signature(span: dict[str, Any]) -> str:
    payload = {
        "font": str(span.get("font") or ""),
        "size": round(float(span.get("size") or 0), 2),
        "color": int(span.get("color") or 0),
        "alpha": int(span.get("alpha") if span.get("alpha") is not None else 255),
        "flags": int(span.get("flags") or 0),
        "char_flags": int(span.get("char_flags") or 0),
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _page_text_spans(page: Any) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    text = page.get_text("dict", sort=True)
    for block in list(text.get("blocks") or []):
        if int(block.get("type") or 0) != 0:
            continue
        for line in list(block.get("lines") or []):
            for span in list(line.get("spans") or []):
                bbox = _bbox_payload(span.get("bbox"))
                normalized_text = _normalize_text_token(span.get("text"))
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1] or not normalized_text:
                    continue
                spans.append({
                    "text": normalized_text,
                    "bbox": bbox,
                    "appearance": _text_appearance_signature(span),
                })
    return spans


def _contains_unsafe_action(source: str) -> bool:
    normalized = _decode_pdf_name_escapes(source or "")
    if _ACTION_NAME_PATTERN.search(normalized):
        return True
    subtypes = {match.group(1).casefold() for match in _ACTION_SUBTYPE_PATTERN.finditer(normalized)}
    if subtypes & _DANGEROUS_ACTION_SUBTYPES:
        return True
    if _ACTION_CONTAINER_PATTERN.search(normalized):
        if not subtypes:
            return True
        if any(subtype not in _SAFE_ACTION_SUBTYPES for subtype in subtypes):
            return True
    return False


def _parsed_pdf_profile(content: bytes) -> tuple[bool, bool, dict[str, Any]]:
    """Inspect decoded PDF objects and build immutable page anchors.

    PyMuPDF expands compressed object streams and normalizes escaped PDF names,
    so action dictionaries cannot hide behind byte encoding. Form rectangles are
    exclusion zones: field values may change, while all static text—including
    punctuation, operators, and appearance—images, and vector path geometry outside
    those zones must remain exactly attributable to the controlled template.
    """
    import pymupdf

    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PdfEngineError("PDF_INVALID", "The PDF parser could not open this document") from exc

    try:
        encrypted = bool(document.needs_pass or document.is_encrypted)
        if encrypted:
            raise PdfEngineError(
                "PDF_ENCRYPTED",
                "Encrypted PDFs require an approved password workflow and cannot be processed here",
                status_code=409,
            )

        has_actions = False
        object_sources = [document.xref_object(-1, compressed=False)]
        object_sources.extend(
            document.xref_object(xref, compressed=False)
            for xref in range(1, document.xref_length())
        )
        for source in object_sources:
            if _contains_unsafe_action(source or ""):
                has_actions = True
                break

        pages: list[dict[str, Any]] = []
        total_anchors = 0
        for page in document:
            excluded_rects = [_rect_payload(widget.rect) for widget in list(page.widgets() or [])]

            words = [
                span
                for span in _page_text_spans(page)
                if not any(_rects_intersect(list(span.get("bbox") or []), excluded) for excluded in excluded_rects)
            ]

            images: list[dict[str, Any]] = []
            for image in page.get_image_info(hashes=True, xrefs=True):
                bbox = [round(float(value), 1) for value in image.get("bbox", (0, 0, 0, 0))]
                if any(_rects_intersect(bbox, excluded) for excluded in excluded_rects):
                    continue
                digest = image.get("digest")
                images.append({
                    "digest": digest.hex() if isinstance(digest, bytes) else str(digest or ""),
                    "bbox": bbox,
                })

            drawings: list[dict[str, Any]] = []
            for drawing in page.get_drawings():
                bbox = _rect_payload(drawing["rect"])
                if any(_rects_intersect(bbox, excluded) for excluded in excluded_rects):
                    continue
                drawings.append({"signature": _drawing_signature(drawing), "bbox": bbox})

            total_anchors += len(words) + len(images) + len(drawings)
            pages.append({
                "width": round(float(page.rect.width), 1),
                "height": round(float(page.rect.height), 1),
                "excluded_rects": excluded_rects,
                "words": words,
                "images": images,
                "drawings": drawings,
            })

        return has_actions, encrypted, {"version": 4, "total_anchors": total_anchors, "pages": pages}
    except PdfEngineError:
        raise
    except Exception as exc:
        raise PdfEngineError(
            "PDF_STRUCTURE_SCAN_FAILED",
            "The PDF object structure could not be inspected safely",
            status_code=422,
        ) from exc
    finally:
        document.close()


def _near_bbox(left: list[float], right: list[float], tolerance: float = 3.0) -> bool:
    return len(left) == len(right) == 4 and all(abs(left[index] - right[index]) <= tolerance for index in range(4))


def _filtered_anchors(page: dict[str, Any], excluded_rects: list[list[float]], key: str) -> list[dict[str, Any]]:
    return [
        anchor
        for anchor in list(page.get(key) or [])
        if not any(_rects_intersect(list(anchor.get("bbox") or []), excluded) for excluded in excluded_rects)
    ]


def _consume_matching_anchor(
    candidates: list[dict[str, Any]],
    used_indexes: set[int],
    predicate: Callable[[dict[str, Any]], bool],
) -> bool:
    for index, candidate in enumerate(candidates):
        if index in used_indexes or not predicate(candidate):
            continue
        used_indexes.add(index)
        return True
    return False


def validate_template_provenance(expected: PdfInspection, candidate: PdfInspection) -> dict[str, Any]:
    expected_fingerprint = dict(expected.template_fingerprint or {})
    candidate_fingerprint = dict(candidate.template_fingerprint or {})
    expected_pages = list(expected_fingerprint.get("pages") or [])
    candidate_pages = list(candidate_fingerprint.get("pages") or [])

    if expected.page_count != candidate.page_count or len(expected_pages) != len(candidate_pages):
        raise PdfEngineError(
            "PDF_TEMPLATE_MISMATCH",
            "The completed PDF page count does not match the controlled template",
            status_code=409,
        )
    if int(expected_fingerprint.get("total_anchors") or 0) < 1:
        raise PdfEngineError(
            "PDF_TEMPLATE_PROVENANCE_UNAVAILABLE",
            "This template has no stable content anchors; provenance cannot be established safely",
            status_code=409,
        )

    verified_anchors = 0
    for page_number, (source_page, completed_page) in enumerate(zip(expected_pages, candidate_pages), start=1):
        if (
            abs(float(source_page.get("width") or 0) - float(completed_page.get("width") or 0)) > 1.0
            or abs(float(source_page.get("height") or 0) - float(completed_page.get("height") or 0)) > 1.0
        ):
            raise PdfEngineError(
                "PDF_TEMPLATE_MISMATCH",
                f"Completed PDF page {page_number} has different page geometry from the controlled template",
                status_code=409,
            )

        exclusions = list(source_page.get("excluded_rects") or [])
        completed_words = _filtered_anchors(completed_page, exclusions, "words")
        completed_images = _filtered_anchors(completed_page, exclusions, "images")
        completed_drawings = _filtered_anchors(completed_page, exclusions, "drawings")
        used_words: set[int] = set()
        used_images: set[int] = set()
        used_drawings: set[int] = set()

        for source_word in list(source_page.get("words") or []):
            if not _consume_matching_anchor(
                completed_words,
                used_words,
                lambda completed: (
                    completed.get("text") == source_word.get("text")
                    and completed.get("appearance") == source_word.get("appearance")
                    and _near_bbox(list(completed.get("bbox") or []), list(source_word.get("bbox") or []))
                ),
            ):
                raise PdfEngineError(
                    "PDF_TEMPLATE_MISMATCH",
                    f"Completed PDF page {page_number} is missing or changes controlled template text",
                    status_code=409,
                )
            verified_anchors += 1

        for source_image in list(source_page.get("images") or []):
            if not _consume_matching_anchor(
                completed_images,
                used_images,
                lambda completed: (
                    completed.get("digest") == source_image.get("digest")
                    and _near_bbox(list(completed.get("bbox") or []), list(source_image.get("bbox") or []))
                ),
            ):
                raise PdfEngineError(
                    "PDF_TEMPLATE_MISMATCH",
                    f"Completed PDF page {page_number} is missing a controlled template image",
                    status_code=409,
                )
            verified_anchors += 1

        for source_drawing in list(source_page.get("drawings") or []):
            if not _consume_matching_anchor(
                completed_drawings,
                used_drawings,
                lambda completed: (
                    completed.get("signature") == source_drawing.get("signature")
                    and _near_bbox(list(completed.get("bbox") or []), list(source_drawing.get("bbox") or []))
                ),
            ):
                raise PdfEngineError(
                    "PDF_TEMPLATE_MISMATCH",
                    f"Completed PDF page {page_number} is missing controlled template geometry",
                    status_code=409,
                )
            verified_anchors += 1

        if (
            len(used_words) != len(completed_words)
            or len(used_images) != len(completed_images)
            or len(used_drawings) != len(completed_drawings)
        ):
            raise PdfEngineError(
                "PDF_TEMPLATE_MISMATCH",
                f"Completed PDF page {page_number} adds unauthorized static content outside form fields",
                status_code=409,
            )

    return {
        "verified": True,
        "template_source_sha256": expected.source_sha256,
        "completed_source_sha256": candidate.source_sha256,
        "page_count": expected.page_count,
        "verified_anchors": verified_anchors,
        "fingerprint_version": int(expected_fingerprint.get("version") or 4),
    }


def _read_worker_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PdfEngineError("PDF_WORKER_FAILED", "PDFium did not return a valid processing result", status_code=500) from exc
    if not isinstance(payload, dict):
        raise PdfEngineError("PDF_WORKER_FAILED", "PDFium returned an invalid processing result", status_code=500)
    if payload.get("error"):
        error = payload["error"] if isinstance(payload["error"], dict) else {}
        raise PdfEngineError(
            str(error.get("code") or "PDF_PROCESSING_FAILED"),
            str(error.get("message") or "PDFium could not process this document"),
            status_code=int(error.get("status_code") or 422),
        )
    return payload


def _run_worker(action: str, content: bytes) -> tuple[dict[str, Any], bytes | None]:
    _validate_input(content)
    root = _safe_work_root()
    with tempfile.TemporaryDirectory(prefix="pdfium-", dir=root) as raw_dir:
        work_dir = Path(raw_dir).resolve()
        if work_dir.parent != root:
            raise PdfEngineError("PDF_WORK_DIR_ESCAPE", "Unsafe PDF processing path", status_code=500)
        source_path = work_dir / "input.pdf"
        output_path = work_dir / "output.pdf"
        metadata_path = work_dir / "result.json"
        source_path.write_bytes(content)
        command = [
            sys.executable,
            "-m",
            "amodb.apps.doc_control.pdfium_service",
            "--worker",
            action,
            str(source_path),
            str(output_path),
            str(metadata_path),
        ]
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=PROCESS_TIMEOUT_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfEngineError(
                "PDF_PROCESS_TIMEOUT",
                f"PDF processing exceeded {PROCESS_TIMEOUT_SECONDS} seconds",
                status_code=504,
            ) from exc
        if metadata_path.exists():
            metadata = _read_worker_metadata(metadata_path)
        elif completed.returncode:
            detail = (completed.stderr or completed.stdout or "PDFium worker failed").strip()[-1000:]
            raise PdfEngineError("PDF_WORKER_FAILED", detail, status_code=500)
        else:
            raise PdfEngineError("PDF_WORKER_FAILED", "PDFium did not produce processing metadata", status_code=500)
        output = output_path.read_bytes() if action == "flatten" and output_path.exists() else None
        return metadata, output


def inspect_pdf_bytes(content: bytes) -> PdfInspection:
    metadata, _ = _run_worker("inspect", content)
    return PdfInspection(**metadata)


def flatten_pdf_bytes(content: bytes) -> PdfFlattenResult:
    metadata, output = _run_worker("flatten", content)
    if not output or not output.startswith(b"%PDF"):
        raise PdfEngineError("PDF_FLATTEN_OUTPUT_INVALID", "PDFium did not produce a valid flattened PDF")
    if _sha256(output) != metadata.get("output_sha256"):
        raise PdfEngineError("PDF_FLATTEN_CHECKSUM_MISMATCH", "The flattened PDF checksum could not be verified", status_code=500)
    return PdfFlattenResult(content=output, **metadata)


def _pdfium_engine_version(pdfium: Any) -> str:
    info = getattr(pdfium, "PDFIUM_INFO", None)
    return "unknown" if info is None else str(info)


def _worker_process(action: str, source_path: Path, output_path: Path) -> dict[str, Any]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    content = source_path.read_bytes()
    _validate_input(content)
    has_actions, encrypted, template_fingerprint = _parsed_pdf_profile(content)
    source_sha256 = _sha256(content)
    if has_actions:
        raise PdfEngineError(
            "PDF_SCRIPTED",
            "PDF JavaScript and automatic actions are disabled for controlled documents",
            status_code=409,
        )

    try:
        document = pdfium.PdfDocument(source_path)
    except Exception as exc:
        raise PdfEngineError("PDF_INVALID", "PDFium could not open this PDF") from exc

    try:
        page_count = len(document)
        if page_count < 1:
            raise PdfEngineError("PDF_EMPTY", "The PDF contains no pages")
        if page_count > MAX_PDF_PAGES:
            raise PdfEngineError(
                "PDF_PAGE_LIMIT",
                f"PDF contains {page_count} pages; the processing limit is {MAX_PDF_PAGES}",
                status_code=413,
            )
        form_type = int(document.get_formtype())
        acro_form = int(getattr(pdfium_c, "FORMTYPE_ACRO_FORM", 1))
        xfa_full = int(getattr(pdfium_c, "FORMTYPE_XFA_FULL", 2))
        xfa_foreground = int(getattr(pdfium_c, "FORMTYPE_XFA_FOREGROUND", 3))
        dynamic_xfa = form_type in {xfa_full, xfa_foreground}
        has_acroform = form_type == acro_form
        engine_version = _pdfium_engine_version(pdfium)
        unsupported_reason = "Dynamic XFA forms cannot be flattened safely" if dynamic_xfa else None
        base = {
            "engine": "PDFium",
            "engine_version": engine_version,
            "source_sha256": source_sha256,
            "page_count": page_count,
            "form_type": form_type,
        }
        if action == "inspect":
            return {
                **base,
                "has_acroform": has_acroform,
                "has_javascript": has_actions,
                "is_dynamic_xfa": dynamic_xfa,
                "encrypted": encrypted,
                "can_flatten": not dynamic_xfa and not has_actions,
                "unsupported_reason": unsupported_reason,
                "template_fingerprint": template_fingerprint,
            }
        if dynamic_xfa:
            raise PdfEngineError("PDF_DYNAMIC_XFA", unsupported_reason or "Dynamic XFA is unsupported", status_code=409)
        if form_type:
            document.init_forms()
        flattened_pages = 0
        unchanged_pages = 0
        for page_index in range(page_count):
            page = document.get_page(page_index)
            try:
                result = int(pdfium_c.FPDFPage_Flatten(page.raw, pdfium_c.FLAT_NORMALDISPLAY))
            finally:
                page.close()
            if result == int(pdfium_c.FLATTEN_FAIL):
                raise PdfEngineError("PDF_FLATTEN_FAILED", f"PDFium failed to flatten page {page_index + 1}")
            if result == int(pdfium_c.FLATTEN_SUCCESS):
                flattened_pages += 1
            else:
                unchanged_pages += 1
        document.save(output_path)
    finally:
        document.close()

    output = output_path.read_bytes()
    if not output.startswith(b"%PDF"):
        raise PdfEngineError("PDF_FLATTEN_OUTPUT_INVALID", "PDFium produced an invalid flattened PDF")
    try:
        with pdfium.PdfDocument(output_path) as reopened:
            output_pages = len(reopened)
    except Exception as exc:
        raise PdfEngineError("PDF_FLATTEN_REOPEN_FAILED", "The flattened PDF could not be reopened") from exc
    if output_pages != page_count:
        raise PdfEngineError(
            "PDF_FLATTEN_PAGE_MISMATCH",
            f"Flattened output contains {output_pages} pages; expected {page_count}",
        )
    return {
        **base,
        "output_sha256": _sha256(output),
        "flattened_pages": flattened_pages,
        "unchanged_pages": unchanged_pages,
    }


def _worker_main(action: str, source: str, output: str, metadata: str) -> int:
    metadata_path = Path(metadata).resolve()
    try:
        payload = _worker_process(action, Path(source).resolve(), Path(output).resolve())
        metadata_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return 0
    except PdfEngineError as exc:
        metadata_path.write_text(
            json.dumps({"error": {"code": exc.code, "message": exc.message, "status_code": exc.status_code}}),
            encoding="utf-8",
        )
        return 2
    except Exception as exc:
        metadata_path.write_text(
            json.dumps({"error": {"code": "PDF_WORKER_FAILED", "message": str(exc)[:1000], "status_code": 500}}),
            encoding="utf-8",
        )
        return 3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("action", choices=("inspect", "flatten"))
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("metadata")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if not args.worker:
        raise SystemExit(64)
    raise SystemExit(_worker_main(args.action, args.source, args.output, args.metadata))
