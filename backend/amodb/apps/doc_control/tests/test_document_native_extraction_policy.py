from __future__ import annotations

from amodb.apps.doc_control import document_text_extractor as extractor
from amodb.apps.manuals.core_router import _build_pdf_sections


def test_native_text_extraction_does_not_call_tika(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Tika must not run before a successful native extractor.")

    monkeypatch.setattr(extractor, "_tika_extract", fail_if_called)

    result = extractor.extract_document_text(
        "procedure.txt",
        b"MPM 2.5.8 calibration control procedure",
        "text/plain",
    )

    assert result.engine == "TEXT"
    assert "MPM 2.5.8" in result.text


def test_tika_remains_broad_format_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        extractor,
        "_tika_extract",
        lambda *_args, **_kwargs: extractor.ExtractedDocumentText(
            text="fallback extracted text",
            engine="APACHE_TIKA",
            truncated=False,
        ),
    )

    result = extractor.extract_document_text(
        "legacy.bin",
        b"not natively supported",
        "application/octet-stream",
    )

    assert result.engine == "APACHE_TIKA"
    assert result.text == "fallback extracted text"



def test_unbookmarked_pdf_detects_numbered_logical_sections() -> None:
    result = _build_pdf_sections(
        {
            "outline": [],
            "page_count": 3,
            "pages": [
                {"page_number": 1, "text": "Controlled Manual\nTable of Contents"},
                {
                    "page_number": 2,
                    "text": "2.5 Tools and Equipment\nGeneral requirements\n2.5.1 Calibration Control\nCalibration register requirements",
                },
                {
                    "page_number": 3,
                    "text": "2.5.8 Calibration Status\nVerify calibration status before use",
                },
            ],
        }
    )

    numbered = [row for row in result if row.get("section_number")]
    assert [row["section_number"] for row in numbered] == ["2.5", "2.5.1", "2.5.8"]
    assert numbered[0]["section_detection"] == "NUMBERED_HEADING"
    assert numbered[1]["heading"].startswith("2.5.1 ")
    assert "Calibration register requirements" in "\n".join(numbered[1]["paragraphs"])


def test_unbookmarked_pdf_falls_back_when_heading_identity_is_weak() -> None:
    result = _build_pdf_sections(
        {
            "outline": [],
            "page_count": 2,
            "pages": [
                {"page_number": 1, "text": "2.5 Tools and Equipment\nGeneral requirements"},
                {"page_number": 2, "text": "Ordinary narrative with no numbered heading"},
            ],
        }
    )

    assert [row["heading"] for row in result] == ["Page 1", "Page 2"]
    assert all(row["section_detection"] == "PAGE_FALLBACK" for row in result)


def test_pdf_outline_preserves_detectable_section_number() -> None:
    result = _build_pdf_sections(
        {
            "outline": [{"heading": "3.5.2 Quality Records", "level": 3, "page_number": 4}],
            "page_count": 4,
            "pages": [{"page_number": 4, "text": "3.5.2 Quality Records\nRetain controlled records"}],
        }
    )

    assert result[0]["section_number"] == "3.5.2"
    assert result[0]["section_detection"] == "PDF_OUTLINE"



def test_xlsx_uses_native_openpyxl_before_tika(monkeypatch) -> None:
    from io import BytesIO

    from openpyxl import Workbook

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Tika must not run when native XLSX extraction succeeds.")

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Calibration Register"
    worksheet.append(["Asset", "Status", "Due"])
    worksheet.append(["SL-ENG-488", "SERVICEABLE", "2026-12-31"])
    payload = BytesIO()
    workbook.save(payload)
    workbook.close()

    monkeypatch.setattr(extractor, "_tika_extract", fail_if_called)
    result = extractor.extract_document_text(
        "calibration-register.xlsx",
        payload.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert result.engine == "OPENPYXL"
    assert "Calibration Register" in result.text
    assert "SL-ENG-488" in result.text
    assert "SERVICEABLE" in result.text
