from __future__ import annotations

from io import BytesIO
import zipfile

import importlib
manuals_router = importlib.import_module("amodb.apps.manuals.router")


def _docx_with_header(header_text: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>INTRO</w:t></w:r></w:p></w:body></w:document>")
        zf.writestr("word/header1.xml", f"<w:hdr><w:p><w:r><w:t>{header_text}</w:t></w:r></w:p></w:hdr>")
    return buf.getvalue()


def test_extract_docx_header_metadata_parses_revision_effectivity_and_title():
    content = _docx_with_header("Manual Title: MPM Revision No: 14 Effectivity: 2026-03-01")
    out = manuals_router._extract_docx_header_metadata(content)

    assert out["manual_title"] and "MPM" in out["manual_title"]
    assert out["revision_number"] == "14"
    assert out["effectivity_date"] == "2026-03-01"


def test_build_prosemirror_json_returns_schema_strict_doc():
    out = manuals_router._build_prosemirror_json(["1 GENERAL", "This is body text."])
    assert out["type"] == "doc"
    assert isinstance(out["content"], list)
    assert out["content"][0]["type"] in {"heading", "paragraph"}
