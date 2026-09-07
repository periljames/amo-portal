from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pypdfium2 as pdfium

from amodb.apps.quality.audit_notice_document import render_audit_notice_pdf
from amodb.apps.quality.audit_notice_router import _safe_pdf_filename


def test_controlled_audit_notice_pdf_contains_populated_governance_record() -> None:
    payload = render_audit_notice_pdf(
        amo_name="Safarilink Aviation Limited",
        contact_email="quality@example.test",
        notice_id="notice-1",
        revision_no=2,
        notice_date_display="Thursday 3rd September 2026",
        audit_ref="QAR/AC/26/001",
        audit_title="Hangar quality system audit",
        audit_date_display="Friday 11th September 2026",
        auditee_representative="Base Maintenance Manager",
        audit_area="Base Maintenance / Hangar",
        audit_scope="Aircraft maintenance quality system",
        audit_criteria="Approved AMO procedures",
        subject="Notice of Hangar quality system audit - QAR/AC/26/001",
        opening_meeting={"window": "Friday 11th September 2026 from 8:00 am to 9:00 am", "location": "Briefing room"},
        closing_meeting={"window": "Friday 11th September 2026 from 4:00 pm to 5:00 pm", "location": "Briefing room"},
        sequence_window="9:00 am to 4:00 pm",
        staff=["Base Maintenance Manager", "Stores Supervisor"],
        issuer_name="James Quality",
        issuer_title="Quality Officer",
        signed_at_display="Thursday 3rd September 2026, 8:03 am Africa/Nairobi",
        form_number="QAM/45",
        form_issue_date="24 Sep 20",
        form_revision="02",
        record_url="https://portal.example.test/maintenance/AMO-NOTICE/quality/audits/audit-1/setup#notice",
    )

    assert payload.startswith(b"%PDF-")
    document = pdfium.PdfDocument(payload)
    try:
        assert len(document) >= 1
        text = "\n".join(document[index].get_textpage().get_text_range() for index in range(len(document)))
    finally:
        document.close()
    assert "Audit Notice/Timetable" in text
    assert "QAR/AC/26/001" in text
    assert "Base Maintenance Manager" in text
    assert "auditee representative and coordination contact" in text
    assert "accountability for the process and records remains" in text
    assert "Electronically signed in AMO Portal" in text
    assert "QR identifies the record only" in text


def test_controlled_notice_filename_is_human_readable_and_not_a_uuid() -> None:
    audit = SimpleNamespace(audit_ref="QAR/MO/26/003", title="Work Pack Audit", id="audit-uuid")
    notice = SimpleNamespace(notice_date=date(2026, 9, 5), revision_no=1)

    assert _safe_pdf_filename(audit, notice) == "(Notice) QAR-MO-26-003 - Work Pack Audit - 2026-09-05 - Rev 01.pdf"
