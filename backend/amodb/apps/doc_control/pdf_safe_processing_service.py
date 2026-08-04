from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import pdfium_service as base
from .pdfium_service import PdfEngineError, PdfFlattenResult, PdfInspection


SAFE_PROCESS_TIMEOUT_SECONDS = int(os.getenv("PDF_SAFE_PROCESS_TIMEOUT_SECONDS", "90"))
SAFE_WORK_ROOT = Path(os.getenv("PDFIUM_WORK_DIR", "uploads/pdfium-work")).resolve()
_JS_KEY_PATTERN = re.compile(r"/(?:JavaScript|JS)(?=[\s/<>{}\[\]()])", re.IGNORECASE)
_INERT_JS_PATTERN = re.compile(r"/(?:JavaScript|JS)\s*(?:null|\(\s*\)|<\s*>)", re.IGNORECASE)
_ACTION_SUBTYPE_PATTERN = re.compile(r"/S\s*/([A-Za-z0-9#]+)", re.IGNORECASE)
_JAVASCRIPT_SUBTYPE_PATTERN = re.compile(r"/S\s*/(?:JavaScript|JS)\b", re.IGNORECASE)
_ACTION_OBJECT_PATTERN = re.compile(r"/Type\s*/Action\b", re.IGNORECASE)
_PDF_REF_PATTERN = re.compile(r"(\d+)\s+\d+\s+R")
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
_INSPECTION_FIELDS = {
    "engine",
    "engine_version",
    "source_sha256",
    "page_count",
    "form_type",
    "has_acroform",
    "has_javascript",
    "is_dynamic_xfa",
    "encrypted",
    "can_flatten",
    "unsupported_reason",
    "template_fingerprint",
}
_FLATTEN_FIELDS = {
    "engine",
    "engine_version",
    "source_sha256",
    "output_sha256",
    "page_count",
    "form_type",
    "flattened_pages",
    "unchanged_pages",
}


def contains_unsafe_action(source: str) -> bool:
    """Detect executable actions without confusing font glyph names with `/A` actions."""

    normalized = base._decode_pdf_name_escapes(source or "")
    inert_javascript = bool(_INERT_JS_PATTERN.search(normalized))
    executable = _INERT_JS_PATTERN.sub("", normalized)
    if _JS_KEY_PATTERN.search(executable):
        return True
    subtypes = {match.group(1).casefold() for match in _ACTION_SUBTYPE_PATTERN.finditer(executable)}
    if inert_javascript and _JAVASCRIPT_SUBTYPE_PATTERN.search(executable):
        subtypes -= {"javascript", "js"}
    if subtypes & _DANGEROUS_ACTION_SUBTYPES:
        return True
    if _ACTION_OBJECT_PATTERN.search(executable):
        if not subtypes or any(subtype not in _SAFE_ACTION_SUBTYPES for subtype in subtypes):
            return True
    return False


def _safe_work_root() -> Path:
    SAFE_WORK_ROOT.mkdir(parents=True, exist_ok=True)
    root = SAFE_WORK_ROOT.resolve()
    if not root.is_dir():
        raise PdfEngineError("PDF_WORK_DIR_INVALID", "The PDF processing work directory is unavailable", status_code=500)
    return root


def _count_widgets(document: Any) -> int:
    return sum(len(list(page.widgets() or [])) for page in document)


def _javascript_object_xrefs(document: Any) -> set[int]:
    scripted: set[int] = set()
    for xref in range(1, document.xref_length()):
        source = document.xref_object(xref, compressed=False) or ""
        executable = _INERT_JS_PATTERN.sub("", source)
        if _JS_KEY_PATTERN.search(executable) or _JAVASCRIPT_SUBTYPE_PATTERN.search(executable):
            scripted.add(xref)
    return scripted


def _remove_script_references(document: Any) -> None:
    """Remove only executable PDF actions; keep pages, links, fields and images intact."""

    catalog = int(document.pdf_catalog())
    names_kind, names_value = document.xref_get_key(catalog, "Names")
    if names_kind == "xref":
        match = _PDF_REF_PATTERN.search(str(names_value or ""))
        if match:
            names_xref = int(match.group(1))
            if document.xref_get_key(names_xref, "JavaScript")[0] != "null":
                document.xref_set_key(names_xref, "JavaScript", "null")
    for key in ("AA", "OpenAction"):
        if document.xref_get_key(catalog, key)[0] != "null":
            document.xref_set_key(catalog, key, "null")

    scripted_xrefs = _javascript_object_xrefs(document)
    for xref in range(1, document.xref_length()):
        if document.xref_get_key(xref, "AA")[0] != "null":
            document.xref_set_key(xref, "AA", "null")
        action_kind, action_value = document.xref_get_key(xref, "A")
        if action_kind == "xref":
            match = _PDF_REF_PATTERN.search(str(action_value or ""))
            if match and int(match.group(1)) in scripted_xrefs:
                document.xref_set_key(xref, "A", "null")
    for xref in scripted_xrefs:
        document.update_object(xref, "<< >>")


def _sanitize_in_process(content: bytes) -> bytes:
    import pymupdf

    base._validate_input(content)
    try:
        source = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PdfEngineError("PDF_INVALID", "The PDF parser could not open this document") from exc

    try:
        if source.needs_pass or source.is_encrypted:
            raise PdfEngineError(
                "PDF_ENCRYPTED",
                "Encrypted PDFs require an approved password workflow and cannot be processed here",
                status_code=409,
            )
        page_count = source.page_count
        widget_count = _count_widgets(source)
        link_count = sum(len(page.get_links()) for page in source)
        image_count = sum(len(page.get_images(full=True)) for page in source)
        _remove_script_references(source)
        # Garbage level 1 removes newly orphaned action objects without rebuilding
        # or recompressing every page stream. Large manuals therefore sanitize in
        # roughly the same order of time as opening the file, not full re-rendering.
        sanitized = source.tobytes(garbage=1, deflate=False, clean=False)
    finally:
        source.close()

    try:
        verified = pymupdf.open(stream=sanitized, filetype="pdf")
    except Exception as exc:
        raise PdfEngineError("PDF_SANITIZE_INVALID", "The script-disabled PDF could not be reopened", status_code=500) from exc
    try:
        if verified.page_count != page_count:
            raise PdfEngineError("PDF_SANITIZE_PAGE_MISMATCH", "PDF script removal changed the page count", status_code=500)
        if _count_widgets(verified) != widget_count:
            raise PdfEngineError("PDF_SANITIZE_WIDGET_MISMATCH", "PDF script removal changed the AcroForm field count", status_code=500)
        if sum(len(page.get_links()) for page in verified) != link_count:
            raise PdfEngineError("PDF_SANITIZE_LINK_MISMATCH", "PDF script removal changed document links", status_code=500)
        if sum(len(page.get_images(full=True)) for page in verified) != image_count:
            raise PdfEngineError("PDF_SANITIZE_IMAGE_MISMATCH", "PDF script removal changed embedded images", status_code=500)
        sources = [verified.xref_object(-1, compressed=False)]
        sources.extend(verified.xref_object(xref, compressed=False) for xref in range(1, verified.xref_length()))
        if any(contains_unsafe_action(value or "") for value in sources):
            raise PdfEngineError(
                "PDF_UNSAFE_ACTION_REMAINS",
                "The PDF contains an executable action that could not be removed safely",
                status_code=409,
            )
    finally:
        verified.close()
    return sanitized


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PdfEngineError("PDF_SAFE_WORKER_FAILED", "Safe PDF processing returned invalid metadata", status_code=500) from exc
    if not isinstance(payload, dict):
        raise PdfEngineError("PDF_SAFE_WORKER_FAILED", "Safe PDF processing returned invalid metadata", status_code=500)
    if payload.get("error"):
        error = payload["error"] if isinstance(payload["error"], dict) else {}
        raise PdfEngineError(
            str(error.get("code") or "PDF_SAFE_PROCESSING_FAILED"),
            str(error.get("message") or "Safe PDF processing failed"),
            status_code=int(error.get("status_code") or 422),
        )
    return payload


def _run_worker(action: str, content: bytes) -> tuple[dict[str, Any], bytes | None]:
    base._validate_input(content)
    root = _safe_work_root()
    with tempfile.TemporaryDirectory(prefix="pdf-safe-", dir=root) as raw_dir:
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
            "amodb.apps.doc_control.pdf_safe_processing_service",
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
                timeout=SAFE_PROCESS_TIMEOUT_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfEngineError(
                "PDF_SAFE_PROCESS_TIMEOUT",
                f"Safe PDF processing exceeded {SAFE_PROCESS_TIMEOUT_SECONDS} seconds",
                status_code=504,
            ) from exc
        if metadata_path.exists():
            metadata = _read_metadata(metadata_path)
        elif completed.returncode:
            detail = (completed.stderr or completed.stdout or "Safe PDF worker failed").strip()[-1000:]
            raise PdfEngineError("PDF_SAFE_WORKER_FAILED", detail, status_code=500)
        else:
            raise PdfEngineError("PDF_SAFE_WORKER_FAILED", "Safe PDF processing produced no metadata", status_code=500)
        output = output_path.read_bytes() if output_path.exists() else None
        return metadata, output


def sanitize_pdf_javascript_bytes(content: bytes) -> bytes:
    metadata, output = _run_worker("sanitize", content)
    if not output or not output.startswith(b"%PDF"):
        raise PdfEngineError("PDF_SANITIZE_OUTPUT_INVALID", "PDF script removal produced an invalid document", status_code=500)
    if hashlib.sha256(output).hexdigest() != str(metadata.get("output_sha256") or ""):
        raise PdfEngineError("PDF_SANITIZE_CHECKSUM_MISMATCH", "The script-disabled PDF checksum could not be verified", status_code=500)
    return output


def inspect_script_disabled_pdf_bytes(content: bytes) -> PdfInspection:
    metadata, _ = _run_worker("inspect", content)
    return PdfInspection(**{key: metadata[key] for key in _INSPECTION_FIELDS})


def flatten_script_disabled_pdf_bytes(content: bytes) -> PdfFlattenResult:
    metadata, output = _run_worker("flatten", content)
    if not output or not output.startswith(b"%PDF"):
        raise PdfEngineError("PDF_FLATTEN_OUTPUT_INVALID", "PDFium did not produce a valid flattened PDF")
    if hashlib.sha256(output).hexdigest() != str(metadata.get("output_sha256") or ""):
        raise PdfEngineError("PDF_FLATTEN_CHECKSUM_MISMATCH", "The flattened PDF checksum could not be verified", status_code=500)
    return PdfFlattenResult(content=output, **{key: metadata[key] for key in _FLATTEN_FIELDS})


def _worker_process(action: str, source_path: Path, output_path: Path) -> dict[str, Any]:
    content = source_path.read_bytes()
    sanitized = _sanitize_in_process(content)
    sanitized_path = source_path.with_name("sanitized.pdf")
    sanitized_path.write_bytes(sanitized)
    if action == "sanitize":
        import pymupdf

        with pymupdf.open(stream=sanitized, filetype="pdf") as verified:
            page_count = verified.page_count
        output_path.write_bytes(sanitized)
        return {
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "output_sha256": hashlib.sha256(sanitized).hexdigest(),
            "page_count": page_count,
        }

    base._contains_unsafe_action = contains_unsafe_action
    metadata = base._worker_process(action, sanitized_path, output_path)
    metadata["script_policy"] = "DISABLED_AND_STRIPPED"
    metadata["original_source_sha256"] = hashlib.sha256(content).hexdigest()
    return metadata


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
            json.dumps({"error": {"code": "PDF_SAFE_WORKER_FAILED", "message": str(exc)[:1000], "status_code": 500}}),
            encoding="utf-8",
        )
        return 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("action", choices=("sanitize", "inspect", "flatten"))
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("metadata")
    args = parser.parse_args()
    if not args.worker:
        raise SystemExit(2)
    raise SystemExit(_worker_main(args.action, args.source, args.output, args.metadata))
