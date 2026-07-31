from __future__ import annotations

from pathlib import Path


SERVICE_PATH = Path("backend/amodb/apps/doc_control/pdfium_service.py")
TEST_PATH = Path("backend/amodb/apps/doc_control/tests/test_pdf_reader_final_hardening.py")


service = SERVICE_PATH.read_text(encoding="utf-8")
old_destination = '''def _destination_payload(destination: dict[str, Any], fallback_page: int | None = None) -> dict[str, Any]:
    point = destination.get("to")
    raw_page = destination.get("page", -1)
    page = int(raw_page) if raw_page is not None else -1
    if page < 0 and fallback_page is not None:
        page = fallback_page
    return {
        "page": page,
        "x": round(float(getattr(point, "x", 0) or 0), 2) if point is not None else None,
        "y": round(float(getattr(point, "y", 0) or 0), 2) if point is not None else None,
        "zoom": round(float(destination.get("zoom", 0) or 0), 3),
    }
'''
new_destination = '''def _destination_payload(destination: dict[str, Any], fallback_page: int | None = None) -> dict[str, Any]:
    point = destination.get("to")
    raw_page = destination.get("page", -1)
    page = int(raw_page) if raw_page is not None else -1
    if page < 0 and fallback_page is not None:
        page = fallback_page
    return {
        "page": page,
        "x": round(float(getattr(point, "x", 0) or 0), 2) if point is not None else None,
        "y": round(float(getattr(point, "y", 0) or 0), 2) if point is not None else None,
        "zoom": round(float(destination.get("zoom", 0) or 0), 3),
        "view": _geometry_payload(destination.get("view")),
        "viewrect": _geometry_payload(destination.get("viewrect")),
    }


def _has_internal_destination(destination: dict[str, Any], fallback_page: int | None = None) -> bool:
    raw_page = destination.get("page", -1)
    try:
        if raw_page is not None and int(raw_page) >= 0:
            return True
    except (TypeError, ValueError):
        pass
    if fallback_page is not None and fallback_page >= 0:
        return True
    if destination.get("to") is not None or destination.get("viewrect") is not None:
        return True
    return destination.get("view") not in (None, "")
'''
if old_destination not in service:
    raise SystemExit("destination helper anchor not found")
service = service.replace(old_destination, new_destination, 1)

old_outline = '''        if kind == pymupdf.LINK_GOTO:
            item["destination"] = _destination_payload(target, int(page_number or 0) - 1)
        else:
'''
new_outline = '''        fallback_page = int(page_number or 0) - 1
        if _has_internal_destination(target, fallback_page):
            item["destination"] = _destination_payload(target, fallback_page)
        else:
'''
if old_outline not in service:
    raise SystemExit("outline navigation anchor not found")
service = service.replace(old_outline, new_outline, 1)

old_link = '''            if kind == pymupdf.LINK_GOTO:
                item["destination"] = _destination_payload(link)
            else:
'''
new_link = '''            if _has_internal_destination(link):
                item["destination"] = _destination_payload(link)
            else:
'''
if old_link not in service:
    raise SystemExit("page-link navigation anchor not found")
service = service.replace(old_link, new_link, 1)
SERVICE_PATH.write_text(service, encoding="utf-8")


tests = TEST_PATH.read_text(encoding="utf-8")
marker = "def test_non_xyz_internal_destinations_are_fingerprinted("
if marker not in tests:
    tests += '''


def _fit_destination_array(document: object, page_index: int, mode: str) -> str:
    suffix = {
        "Fit": "/Fit",
        "FitH": "/FitH 72",
        "FitV": "/FitV 72",
        "FitR": "/FitR 0 0 200 200",
    }[mode]
    return f"[{document[page_index].xref} 0 R {suffix}]"  # type: ignore[index]


def _set_xref_destination(document: object, xref: int, destination: str) -> None:
    action_kind, _ = document.xref_get_key(xref, "A")  # type: ignore[attr-defined]
    if action_kind != "null":
        document.xref_set_key(xref, "A/D", destination)  # type: ignore[attr-defined]
    else:
        document.xref_set_key(xref, "Dest", destination)  # type: ignore[attr-defined]


def _rewrite_non_xyz_navigation(
    source: bytes,
    mode: str,
    page_index: int,
    *,
    outline: bool,
    page_link: bool,
) -> bytes:
    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        destination = _fit_destination_array(document, page_index, mode)
        if outline:
            toc = document.get_toc(simple=False)
            outline_xref = int(toc[0][3]["xref"])
            _set_xref_destination(document, outline_xref, destination)
        if page_link:
            link_xref = int(document[0].get_links()[0]["xref"])
            _set_xref_destination(document, link_xref, destination)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


@pytest.mark.parametrize("mode", ["Fit", "FitH", "FitV", "FitR"])
@pytest.mark.parametrize("navigation_kind", ["outline", "page_link"])
def test_non_xyz_internal_destinations_are_fingerprinted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    navigation_kind: str,
) -> None:
    monkeypatch.setattr(engine, "WORK_ROOT", tmp_path / "work")
    baseline = _controlled_form_with_navigation()
    source_bytes = _rewrite_non_xyz_navigation(
        baseline,
        mode,
        0,
        outline=True,
        page_link=True,
    )
    candidate_bytes = _rewrite_non_xyz_navigation(
        source_bytes,
        mode,
        1,
        outline=navigation_kind == "outline",
        page_link=navigation_kind == "page_link",
    )

    source = engine.inspect_pdf_bytes(source_bytes)
    candidate = engine.inspect_pdf_bytes(candidate_bytes)
    for source_page, candidate_page in zip(
        source.template_fingerprint["pages"],
        candidate.template_fingerprint["pages"],
    ):
        assert source_page["content_sha256"] == candidate_page["content_sha256"]
        assert source_page["resources_sha256"] == candidate_page["resources_sha256"]

    collection = "outlines" if navigation_kind == "outline" else "page_links"
    source_item = source.template_fingerprint["navigation"][collection][0]
    candidate_item = candidate.template_fingerprint["navigation"][collection][0]
    assert source_item["kind"] == candidate_item["kind"]
    assert source_item["destination"] != candidate_item["destination"]
    assert source.template_fingerprint["navigation"] != candidate.template_fingerprint["navigation"]

    with pytest.raises(engine.PdfEngineError) as mismatch:
        engine.validate_template_provenance(source, candidate)
    assert mismatch.value.code == "PDF_TEMPLATE_MISMATCH"
    assert mismatch.value.status_code == 409
    assert "controlled document navigation" in mismatch.value.message
'''
    TEST_PATH.write_text(tests, encoding="utf-8")
