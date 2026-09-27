from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


SUPPORTED_WORD_EXTENSIONS = {".docx", ".doc", ".odt", ".rtf"}


class OfficeRenderError(RuntimeError):
    pass


def _cache_root() -> Path:
    configured = str(os.getenv("DOCUMENT_OFFICE_RENDER_CACHE_DIR", "") or "").strip()
    root = Path(configured) if configured else Path("uploads/manuals/rendered-office")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _source_key(source_path: Path, explicit_checksum: str | None = None) -> str:
    checksum = str(explicit_checksum or "").strip().lower()
    if checksum and all(character in "0123456789abcdef" for character in checksum):
        return checksum
    digest = hashlib.sha256()
    with source_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_word_source_to_pdf(
    source_path: Path,
    *,
    source_checksum: str | None = None,
    timeout_seconds: int | None = None,
) -> Path:
    source_path = source_path.resolve()
    if not source_path.exists() or not source_path.is_file():
        raise OfficeRenderError("The Word source file is unavailable.")

    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_WORD_EXTENSIONS:
        raise OfficeRenderError(f"Unsupported Word source format: {suffix or 'unknown'}.")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise OfficeRenderError(
            "LibreOffice Writer is not installed. Install libreoffice-writer so Word documents can be rendered faithfully."
        )

    key = _source_key(source_path, source_checksum)
    target_dir = _cache_root() / key[:2] / key
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "document.pdf"
    if target.exists() and target.stat().st_size > 0:
        return target

    timeout = max(10, int(timeout_seconds or os.getenv("DOCUMENT_OFFICE_RENDER_TIMEOUT_SECONDS", "90")))
    with tempfile.TemporaryDirectory(prefix="amo-office-render-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / f"source{suffix}"
        output_dir = temp_dir / "output"
        profile_dir = temp_dir / "profile"
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, input_path)

        command = [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(output_dir),
            str(input_path),
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficeRenderError(f"Word rendering exceeded the {timeout}-second limit.") from exc

        generated = output_dir / "source.pdf"
        if completed.returncode != 0 or not generated.exists() or generated.stat().st_size == 0:
            detail = (completed.stderr or completed.stdout or "LibreOffice did not create a PDF.").strip()
            raise OfficeRenderError(f"Word rendering failed: {detail[:500]}")

        temporary_target = target.with_suffix(".tmp")
        shutil.copyfile(generated, temporary_target)
        os.replace(temporary_target, target)

    return target
