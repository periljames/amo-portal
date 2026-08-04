from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .pdfium_service import (
    MAX_PDF_BYTES,
    MAX_PDF_PAGES,
    PdfEngineError,
    PdfInspection,
    _contains_unsafe_action,
)


CAPABILITY_TIMEOUT_SECONDS = int(os.getenv("PDF_CAPABILITY_TIMEOUT_SECONDS", "25"))
CAPABILITY_WORK_ROOT = Path(os.getenv("PDFIUM_WORK_DIR", "uploads/pdfium-work")).resolve()


def _validate_input(content: bytes) -> None:
    if not content or not content.startswith(b"%PDF"):
        raise PdfEngineError("PDF_INVALID", "A valid PDF source is required")
    if len(content) > MAX_PDF_BYTES:
        raise PdfEngineError(
            "PDF_TOO_LARGE",
            f"PDF input exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB processing limit",
            status_code=413,
        )


def _safe_work_root() -> Path:
    CAPABILITY_WORK_ROOT.mkdir(parents=True, exist_ok=True)
    root = CAPABILITY_WORK_ROOT.resolve()
    if not root.is_dir():
        raise PdfEngineError("PDF_WORK_DIR_INVALID", "The PDF processing work directory is unavailable", status_code=500)
    return root


def _security_profile(content: bytes) -> tuple[bool, bool]:
    """Inspect encryption and executable actions without building page fingerprints."""

    import pymupdf

    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PdfEngineError("PDF_INVALID", "The PDF parser could not open this document") from exc

    try:
        encrypted = bool(document.needs_pass or document.is_encrypted)
        if encrypted:
            return False, True

        catalog = document.xref_object(-1, compressed=False)
        if _contains_unsafe_action(catalog or ""):
            return True, False
        for xref in range(1, document.xref_length()):
            if _contains_unsafe_action(document.xref_object(xref, compressed=False) or ""):
                return True, False
        return False, False
    except PdfEngineError:
        raise
    except Exception as exc:
        raise PdfEngineError(
            "PDF_STRUCTURE_SCAN_FAILED",
            "The PDF action structure could not be inspected safely",
            status_code=422,
        ) from exc
    finally:
        document.close()


def _pdfium_engine_version(pdfium: Any) -> str:
    info = getattr(pdfium, "PDFIUM_INFO", None)
    return "unknown" if info is None else str(info)


def _inspect_worker(source_path: Path) -> dict[str, Any]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    content = source_path.read_bytes()
    _validate_input(content)
    has_actions, encrypted = _security_profile(content)

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
        unsupported_reason = None
        if encrypted:
            unsupported_reason = "Encrypted PDFs require an approved password workflow"
        elif has_actions:
            unsupported_reason = "PDF JavaScript and automatic actions are disabled"
        elif dynamic_xfa:
            unsupported_reason = "Dynamic XFA forms cannot be flattened safely"
        return {
            "engine": "PDFium",
            "engine_version": _pdfium_engine_version(pdfium),
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "page_count": page_count,
            "form_type": form_type,
            "has_acroform": form_type == acro_form,
            "has_javascript": has_actions,
            "is_dynamic_xfa": dynamic_xfa,
            "encrypted": encrypted,
            "can_flatten": not encrypted and not has_actions and not dynamic_xfa,
            "unsupported_reason": unsupported_reason,
            "template_fingerprint": None,
        }
    finally:
        document.close()


def _read_result(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PdfEngineError("PDF_CAPABILITY_FAILED", "PDF capability inspection returned invalid metadata", status_code=500) from exc
    if not isinstance(payload, dict):
        raise PdfEngineError("PDF_CAPABILITY_FAILED", "PDF capability inspection returned invalid metadata", status_code=500)
    if payload.get("error"):
        error = payload["error"] if isinstance(payload["error"], dict) else {}
        raise PdfEngineError(
            str(error.get("code") or "PDF_CAPABILITY_FAILED"),
            str(error.get("message") or "PDF capability inspection failed"),
            status_code=int(error.get("status_code") or 422),
        )
    return payload


def inspect_pdf_capabilities_bytes(content: bytes) -> PdfInspection:
    _validate_input(content)
    root = _safe_work_root()
    with tempfile.TemporaryDirectory(prefix="pdf-capability-", dir=root) as raw_dir:
        work_dir = Path(raw_dir).resolve()
        if work_dir.parent != root:
            raise PdfEngineError("PDF_WORK_DIR_ESCAPE", "Unsafe PDF processing path", status_code=500)
        source_path = work_dir / "input.pdf"
        result_path = work_dir / "result.json"
        source_path.write_bytes(content)
        command = [
            sys.executable,
            "-m",
            "amodb.apps.doc_control.pdf_capability_service",
            "--worker",
            str(source_path),
            str(result_path),
        ]
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=CAPABILITY_TIMEOUT_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfEngineError(
                "PDF_CAPABILITY_TIMEOUT",
                f"PDF capability inspection exceeded {CAPABILITY_TIMEOUT_SECONDS} seconds",
                status_code=504,
            ) from exc
        if result_path.exists():
            return PdfInspection(**_read_result(result_path))
        detail = (completed.stderr or completed.stdout or "PDF capability worker failed").strip()[-1000:]
        raise PdfEngineError("PDF_CAPABILITY_FAILED", detail, status_code=500)


def _worker_main(source: str, result: str) -> int:
    result_path = Path(result).resolve()
    try:
        result_path.write_text(json.dumps(_inspect_worker(Path(source).resolve()), sort_keys=True), encoding="utf-8")
        return 0
    except PdfEngineError as exc:
        result_path.write_text(
            json.dumps({"error": {"code": exc.code, "message": exc.message, "status_code": exc.status_code}}),
            encoding="utf-8",
        )
        return 2
    except Exception as exc:
        result_path.write_text(
            json.dumps({"error": {"code": "PDF_CAPABILITY_FAILED", "message": str(exc)[:1000], "status_code": 500}}),
            encoding="utf-8",
        )
        return 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("source")
    parser.add_argument("result")
    args = parser.parse_args()
    if not args.worker:
        raise SystemExit(2)
    raise SystemExit(_worker_main(args.source, args.result))
