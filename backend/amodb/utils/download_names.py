"""Public filenames are business labels; storage keys remain internal."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", re.I)


def download_name(*parts: object, extension: str = "", fallback: str = "document") -> str:
    value = "-".join(str(part).strip() for part in parts if part is not None and str(part).strip())
    value = unicodedata.normalize("NFC", _UUID.sub("", value))
    suffix = extension if extension.startswith(".") or not extension else f".{extension}"
    if suffix and value.lower().endswith(suffix.lower()):
        value = value[:-len(suffix)]
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]+', "-", value)
    value = re.sub(r"[-_]{2,}", "-", re.sub(r"\s+", " ", value)).strip(" .-_")
    value = value or fallback
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value, re.I):
        value = f"file-{value}"
    return value[:180-len(suffix)].rstrip() + suffix


def attachment_header(filename: str) -> str:
    """ASCII fallback plus RFC 5987 UTF-8 for Response (FileResponse does this itself)."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "document"
    ascii_name = ascii_name.replace('"', "").replace("\r", "").replace("\n", "")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
