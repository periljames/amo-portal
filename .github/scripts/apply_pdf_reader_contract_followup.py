from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"Expected source block not found in {path}: {old[:140]!r}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


replace(
    "backend/amodb/apps/doc_control/tests/test_pdf_reader_source_contract.py",
    '    assert imports == ["backend/amodb/apps/doc_control/pdfium_service.py"]\n',
    '''    assert imports == [
        "backend/amodb/apps/doc_control/pdf_capability_service.py",
        "backend/amodb/apps/doc_control/pdfium_service.py",
    ]
''',
)

replace(
    "backend/amodb/apps/doc_control/tests/test_pdf_reader_interaction_contract.py",
    '''    assert "fs.cpSync" in vite
    assert "pdfJsRuntimeAssetsPlugin" in vite
    for directory in ("wasm", "cmaps", "standard_fonts"):
''',
    '''    assert "fs.cpSync" in vite
    assert "pdfJsRuntimeAssetsPlugin" in vite
    assert "configureServer(server)" in vite
    assert "pdfJsAssetDirectorySet.has" in vite
    assert "assetPath.startsWith(allowedRoot)" in vite
    assert "application/wasm" in vite
    assert "max-age=31536000, immutable" in vite
    assert "nullopenjpeg_nowasm_fallback.js" in vite
    for directory in ("wasm", "cmaps", "standard_fonts"):
''',
)

print("Updated PDFium confinement and Vite decoder-serving contracts.")
