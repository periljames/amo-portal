from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MAX_PDF_BYTES = int(os.getenv("PDFIUM_MAX_INPUT_BYTES", str(100 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.getenv("PDFIUM_MAX_PAGES", "5000"))
PROCESS_TIMEOUT_SECONDS = int(os.getenv("PDFIUM_PROCESS_TIMEOUT_SECONDS", "90"))
WORK_ROOT = Path(os.getenv("PDFIUM_WORK_DIR", "uploads/pdfium-work")).resolve()

_SCRIPT_PATTERN = re.compile(rb"/(?:JavaScript|JS|OpenAction|AA)(?:\s|\[|<|/)", re.IGNORECASE)


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
    if b"/Encrypt" in content:
        raise PdfEngineError(
            "PDF_ENCRYPTED",
            "Encrypted PDFs require an approved password workflow and cannot be processed here",
            status_code=409,
        )


def _safe_work_root() -> Path:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    root = WORK_ROOT.resolve()
    if not root.is_dir():
        raise PdfEngineError("PDF_WORK_DIR_INVALID", "The PDF processing work directory is unavailable", status_code=500)
    return root


def _read_worker_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive worker boundary
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
    if info is None:
        return "unknown"
    return str(info)


def _worker_process(action: str, source_path: Path, output_path: Path) -> dict[str, Any]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    content = source_path.read_bytes()
    _validate_input(content)
    has_javascript = bool(_SCRIPT_PATTERN.search(content))
    source_sha256 = _sha256(content)
    if has_javascript:
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
                "has_javascript": False,
                "is_dynamic_xfa": dynamic_xfa,
                "encrypted": False,
                "can_flatten": not dynamic_xfa,
                "unsupported_reason": unsupported_reason,
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
    except Exception as exc:  # pragma: no cover - worker crash boundary
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


if __name__ == "__main__":  # pragma: no cover - exercised through bounded subprocess tests
    args = _parse_args()
    if not args.worker:
        raise SystemExit(64)
    raise SystemExit(_worker_main(args.action, args.source, args.output, args.metadata))
