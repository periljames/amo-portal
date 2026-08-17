from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import fitz

from amodb.apps.training import models as training_models
from amodb.apps.training.record_presentation import _compact_pdf_builder


def test_normal_fifteen_requirement_record_is_one_controlled_a4_page():
    user = SimpleNamespace(
        id="ID-FL28MRNH",
        full_name="Mercy Etende",
        first_name="Mercy",
        last_name="Etende",
        position_title="Procurement Officer",
        staff_code="ETEN01",
        licence_number=None,
    )
    amo = SimpleNamespace(name="Safarilink Aviation Limited")

    course_by_id = {}
    status_items = []
    for index in range(15):
        course = SimpleNamespace(
            id=f"course-{index}",
            course_id=f"TRN-{index:02d}",
            course_name=f"Training Requirement {index + 1}",
            kind=training_models.TrainingKind.RECURRENT,
            status="Recurrent",
            group_code=None,
            prerequisite_course_id=None,
            frequency_months=24,
        )
        course_by_id[course.id] = course
        status_items.append(
            SimpleNamespace(
                course_id=course.course_id,
                course_name=course.course_name,
                status="OK",
                last_completion_date=date(2025, 8, 5),
                valid_until=date(2027, 8, 5),
                extended_due_date=None,
                upcoming_event_date=None,
            )
        )

    pdf_bytes = _compact_pdf_builder(
        lambda *args, **kwargs: b"legacy",
        user=user,
        amo=amo,
        logo_path=None,
        status_items=status_items,
        records=[],
        course_by_id=course_by_id,
        upcoming_events=[],
        deferrals=[],
        verification_url="https://portal.example.test/public/training/users/ID-FL28MRNH/verify?format=html&amo=safarilink&report_token=trp1.test",
        report_settings={},
    )

    assert pdf_bytes.startswith(b"%PDF")
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert document.page_count == 1
    text = "\n".join(page.get_text() for page in document)
    assert "INDIVIDUAL TRAINING & COMPLIANCE RECORD" in text
    assert "Next Due" in text
    assert "Scheduled" in text
    assert "QAM/49A Rev 00" in text
    assert "Page 1 of 1" in text
    assert "trp1.test" not in text


def test_pdf_rejects_relative_verification_qr_source():
    user = SimpleNamespace(id="u", full_name="User", first_name="U", last_name="Ser", position_title=None, staff_code="S1", licence_number=None)
    amo = SimpleNamespace(name="Example Aviation")

    try:
        _compact_pdf_builder(
            lambda *args, **kwargs: b"legacy",
            user=user,
            amo=amo,
            logo_path=None,
            status_items=[],
            records=[],
            course_by_id={},
            upcoming_events=[],
            deferrals=[],
            verification_url="/public/training/users/u/verify?report_token=bad",
            report_settings={},
        )
    except RuntimeError as exc:
        assert "absolute HTTPS verification URL" in str(exc)
    else:
        raise AssertionError("relative QR source must fail closed")
