from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document

from amodb.apps.quality.audit_checklist_upload_parser import draft_from_upload


def _paper_form() -> bytes:
    document = Document()
    table = document.add_table(rows=0, cols=6)
    for values in [
        ("", "ORGANIZATION/ MANAGEMENT", "S", "U", "N/C", "N/A"),
        ("", "Is there a description and organogram?", "", "", "", ""),
        ("", "Are approved key post holders in place?", "", "", "", ""),
        ("", "Remarks:", "", "", "", ""),
        ("", "FLIGHT SAFETY MANAGEMENT", "S", "U", "N/C", "N/A"),
        ("", "Are risk assessments conducted for all identified hazards?", "", "", "", ""),
        ("", "Remarks:", "", "", "", ""),
    ]:
        cells = table.add_row().cells
        for cell, value in zip(cells, values):
            cell.text = value
    result = BytesIO()
    document.save(result)
    return result.getvalue()


def test_word_form_extraction_keeps_order_sections_and_explicit_source_vocabulary():
    source = _paper_form()
    draft = draft_from_upload(source, "SL-QMS-20.docx")
    assert draft["question_count"] == 3
    assert draft["section_count"] == 2
    assert [item["checklist_ref"] for item in draft["items"]] == ["1", "2", "3"]
    assert [item["section"] for item in draft["items"]] == [
        "ORGANIZATION/ MANAGEMENT", "ORGANIZATION/ MANAGEMENT", "FLIGHT SAFETY MANAGEMENT",
    ]
    assert draft["items"][2]["prompt"].startswith("Are risk assessments")
    assert [item["response_options"][i]["value"] for i in range(4)] == ["S", "U", "N/C", "N/A"]
    assert draft["items"][0]["response_options"][2]["canonical_status"] == "NOT_VERIFIED"
    assert draft["sha256"] and len(draft["sha256"]) == 64


@pytest.mark.parametrize("name,data", [
    ("fake.pdf", b"not a PDF"),
    ("fake.docx", b"not a Word file"),
    ("bad.txt", b"anything"),
    ("empty.docx", b""),
])
def test_invalid_uploads_fail_closed(name: str, data: bytes):
    with pytest.raises(ValueError):
        draft_from_upload(data, name)
