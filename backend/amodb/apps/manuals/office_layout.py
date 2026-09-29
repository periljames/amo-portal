"""Stable Office-to-PDF layout derivative generation for the Publications reader.

Office sources stay authoritative and downloadable. This module only creates a
checksum-keyed PDF layout proof once during revision processing so the browser
can reuse the existing client-side PDF reader without re-rendering Word files
on every open.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


LOGGER = logging.getLogger(__name__)

SUPPORTED_OFFICE_EXTENSIONS = {".docx", ".doc", ".odt", ".rtf"}
OFFICE_MIME_BY_EXTENSION = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
}


class OfficeLayoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfficeLayoutDerivative:
    path: Path
    page_count: int
    size_bytes: int
    source_sha256: str
    pdf_sha256: str
    created: bool


def _source_path(revision) -> Path:
    raw = str(getattr(revision, "source_storage_path", "") or "").strip()
    path = Path(raw).resolve() if raw else None
    if not path or not path.exists() or not path.is_file():
        raise OfficeLayoutError("The Office source file is unavailable")
    if path.suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS:
        raise OfficeLayoutError(f"Unsupported Office source type: {path.suffix or 'unknown'}")
    return path


def _normalized_docx_cache_root() -> Path:
    configured = str(os.getenv("OFFICE_NORMALIZED_CACHE_DIR", "") or "").strip()
    root = Path(configured) if configured else Path("uploads/manuals/normalized-office")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _source_checksum(revision, source: Path) -> str:
    """Hash the retained Office bytes and enforce the governed upload checksum."""

    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()

    stored = str(getattr(revision, "source_sha256", "") or "").strip().lower()
    if stored and actual != stored:
        raise OfficeLayoutError(
            "The retained Office source no longer matches the uploaded controlled-file checksum"
        )
    return actual


def office_layout_pdf_path(revision) -> Path | None:
    raw = str(getattr(revision, "source_storage_path", "") or "").strip()
    if not raw:
        return None
    source = Path(raw).resolve()
    if source.suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS:
        return None
    checksum = _source_checksum(revision, source) if source.exists() and source.is_file() else str(getattr(revision, "source_sha256", "") or "")
    token = (checksum or str(getattr(revision, "id", "") or "layout")).lower()[:16]
    return source.with_name(f"{source.stem}.layout-{token}.pdf")


def _pdf_page_count(path: Path) -> int:
    try:
        import fitz  # type: ignore
        with fitz.open(str(path)) as document:
            return max(1, int(document.page_count or 1))
    except Exception:
        return 1


def _validate_pdf(path: Path) -> None:
    if not path.exists() or not path.is_file() or path.stat().st_size < 8:
        raise OfficeLayoutError("Office layout conversion did not produce a PDF")
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise OfficeLayoutError("Office layout conversion produced an invalid PDF")


def _pdf_checksum(path: Path) -> str:
    """Return a stable checksum for the immutable Office PDF proof.

    A size/mtime keyed sidecar avoids re-hashing large manuals on every range
    request while still detecting an unexpected replacement of the derivative.
    """

    stat = path.stat()
    sidecar = path.with_suffix(f"{path.suffix}.sha256.json")
    if sidecar.exists() and sidecar.is_file():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            checksum = str(payload.get("sha256") or "").strip().lower()
            if (
                len(checksum) == 64
                and int(payload.get("size_bytes") or 0) == stat.st_size
                and int(payload.get("mtime_ns") or 0) == stat.st_mtime_ns
            ):
                return checksum
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = digest.hexdigest()
    payload = {
        "sha256": checksum,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    with tempfile.NamedTemporaryFile(
        prefix=f"{path.stem}-sha256-",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as handle:
        temporary = Path(handle.name).resolve()
        json.dump(payload, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, sidecar)
    finally:
        temporary.unlink(missing_ok=True)
    return checksum


def office_layout_pdf_checksum(path: Path) -> str:
    """Return the immutable browser-reader fingerprint for an Office PDF proof."""
    _validate_pdf(path)
    return _pdf_checksum(path)


def _office_binary() -> str:
    configured = str(os.getenv("OFFICE_LAYOUT_CONVERTER", "") or "").strip()
    if configured:
        resolved = shutil.which(configured) or (configured if Path(configured).exists() else "")
        if resolved:
            return str(resolved)

    resolved = shutil.which("soffice") or shutil.which("libreoffice")
    if resolved:
        return resolved

    # Local Windows/macOS development often has LibreOffice installed without
    # adding its program directory to PATH. Production Linux images already
    # install libreoffice-writer, so these probes are only compatibility aids.
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "LibreOffice" / "program" / "soffice.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "LibreOffice" / "program" / "soffice.exe",
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    ]
    for candidate in candidates:
        if str(candidate) and candidate.exists() and candidate.is_file():
            return str(candidate)

    raise OfficeLayoutError(
        "LibreOffice Writer is required for faithful Word page-layout rendering. "
        "Install LibreOffice or set OFFICE_LAYOUT_CONVERTER to the soffice executable."
    )


def office_mime_type(filename: str | None) -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    return OFFICE_MIME_BY_EXTENSION.get(suffix, "application/octet-stream")


def normalize_office_source_to_docx(content: bytes, filename: str | None, *, timeout_seconds: int = 90) -> bytes:
    """Return DOCX bytes for semantic extraction while retaining the original source elsewhere."""
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in SUPPORTED_OFFICE_EXTENSIONS:
        raise OfficeLayoutError(f"Unsupported Office source type: {suffix or 'unknown'}")
    if suffix == ".docx":
        return content
    if not content:
        raise OfficeLayoutError("The Office source file is empty")

    digest = hashlib.sha256(content).hexdigest()
    cache_target = _normalized_docx_cache_root() / f"{digest}.docx"
    if cache_target.exists() and cache_target.is_file():
        cached = cache_target.read_bytes()
        if cached.startswith(b"PK\x03\x04"):
            return cached
        cache_target.unlink(missing_ok=True)

    binary = _office_binary()
    with tempfile.TemporaryDirectory(prefix="office-normalize-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / f"source{suffix}"
        input_path.write_bytes(content)
        profile = temp_dir / "lo-profile"
        profile.mkdir(parents=True, exist_ok=True)
        command = [
            binary,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to",
            "docx:Office Open XML Text",
            "--outdir",
            str(temp_dir),
            str(input_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(15, int(timeout_seconds)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficeLayoutError("Office source normalization timed out") from exc

        output = temp_dir / "source.docx"
        if completed.returncode != 0 or not output.exists():
            detail = (completed.stderr or completed.stdout or "conversion failed").strip()
            raise OfficeLayoutError(f"Office source normalization failed: {detail[:500]}")
        payload = output.read_bytes()
        if not payload.startswith(b"PK\x03\x04"):
            raise OfficeLayoutError("Office source normalization produced an invalid DOCX package")
        with tempfile.NamedTemporaryFile(
            prefix=f"{digest}-",
            suffix=".tmp",
            dir=cache_target.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name).resolve()
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, cache_target)
        finally:
            temporary.unlink(missing_ok=True)
        return payload


def prepare_office_layout_pdf(revision, *, timeout_seconds: int = 120) -> OfficeLayoutDerivative:
    source = _source_path(revision)
    checksum = _source_checksum(revision, source)
    target = office_layout_pdf_path(revision)
    if target is None:
        raise OfficeLayoutError("Office layout target could not be resolved")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            _validate_pdf(target)
            return OfficeLayoutDerivative(
                path=target,
                page_count=_pdf_page_count(target),
                size_bytes=target.stat().st_size,
                source_sha256=checksum,
                pdf_sha256=_pdf_checksum(target),
                created=False,
            )
        except OfficeLayoutError:
            target.unlink(missing_ok=True)

    binary = _office_binary()
    with tempfile.TemporaryDirectory(prefix=".office-layout-", dir=str(target.parent)) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / f"source{source.suffix.lower()}"
        shutil.copy2(source, input_path)
        profile = temp_dir / "lo-profile"
        profile.mkdir(parents=True, exist_ok=True)
        command = [
            binary,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(temp_dir),
            str(input_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(15, int(timeout_seconds)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficeLayoutError("Office layout conversion timed out") from exc

        output = temp_dir / "source.pdf"
        if completed.returncode != 0 or not output.exists():
            detail = (completed.stderr or completed.stdout or "conversion failed").strip()
            raise OfficeLayoutError(f"Office layout conversion failed: {detail[:500]}")
        _validate_pdf(output)

        # The conversion already runs in a unique temporary directory under the
        # target filesystem. Move that unique output into place atomically so
        # concurrent upload/read conversions never share a staging filename.
        os.replace(output, target)

    _validate_pdf(target)
    return OfficeLayoutDerivative(
        path=target,
        page_count=_pdf_page_count(target),
        size_bytes=target.stat().st_size,
        source_sha256=checksum,
        pdf_sha256=_pdf_checksum(target),
        created=True,
    )


def precompute_office_layout_assets(revision_id: str) -> None:
    """Materialize the stable Office layout proof once after source upload."""
    from amodb.database import WriteSessionLocal
    from . import models

    db = WriteSessionLocal()
    try:
        revision = (
            db.query(models.ManualRevision)
            .filter(models.ManualRevision.id == revision_id)
            .first()
        )
        if revision is None:
            LOGGER.warning("Office layout precompute skipped: revision %s not found", revision_id)
            return
        raw = str(getattr(revision, "source_storage_path", "") or "").strip()
        if not raw or Path(raw).suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS:
            return
        derivative = prepare_office_layout_pdf(revision)
        revision.source_page_count = derivative.page_count
        db.add(revision)
        db.commit()
    except Exception:
        db.rollback()
        LOGGER.exception("Office layout precompute failed for revision %s", revision_id)
    finally:
        db.close()
