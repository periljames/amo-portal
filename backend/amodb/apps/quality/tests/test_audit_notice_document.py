from __future__ import annotations

import pypdfium2 as pdfium

from amodb.apps.quality.audit_notice_document import render_audit_notice_pdf


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
        auditee="Base Maintenance Manager",
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
    assert "Electronically signed and issued through AMO Portal" in text
