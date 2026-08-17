from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import fitz
import pytest

from amodb.apps.training import models as training_models
from amodb.apps.training.record_presentation import _compact_pdf_builder


def _pdf_user():
    return SimpleNamespace(
        id="ID-FL28MRNH",
        full_name="Mercy Etende",
        first_name="Mercy",
        last_name="Etende",
        position_title="Procurement Officer",
        staff_code="ETEN01",
        licence_number=None,
    )


def _verification_url() -> str:
    return "https://portal.example.test/public/training/users/ID-FL28MRNH/verify?format=html&amo=safarilink&report_token=trp1.test"


def test_normal_fifteen_requirement_record_is_one_controlled_a4_page():
    user = _pdf_user()
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
        verification_url=_verification_url(),
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


def test_pdf_honours_tenant_report_metadata_and_section_visibility():
    course = SimpleNamespace(
        id="course-1",
        course_id="HF-REC",
        course_name="Human Factors Recurrent",
        kind=training_models.TrainingKind.RECURRENT,
        status="RECURRENT",
        group_code="HF",
        prerequisite_course_id="HF-INIT",
        frequency_months=24,
    )
    status = SimpleNamespace(
        course_id="HF-REC",
        course_name="Human Factors Recurrent",
        status="OK",
        last_completion_date=date(2026, 8, 1),
        valid_until=date(2028, 8, 1),
        extended_due_date=None,
        upcoming_event_date=None,
    )
    record = SimpleNamespace(
        course_id="course-1",
        completion_date=date(2026, 8, 1),
        valid_until=date(2028, 8, 1),
        certificate_reference="HF-2026-1",
        created_at="2026-08-01T12:00:00Z",
    )
    event = SimpleNamespace(
        course_id="course-1",
        title="HF Renewal Class",
        starts_on=date(2028, 7, 10),
        status="PLANNED",
    )
    deferral = SimpleNamespace(
        course_id="course-1",
        original_due_date=date(2028, 8, 1),
        requested_new_due_date=date(2028, 9, 1),
        status="APPROVED",
    )

    pdf_bytes = _compact_pdf_builder(
        lambda *args, **kwargs: b"legacy",
        user=_pdf_user(),
        amo=SimpleNamespace(name="Safarilink Aviation Limited"),
        logo_path=None,
        status_items=[status],
        records=[record],
        course_by_id={course.id: course},
        upcoming_events=[event],
        deferrals=[deferral],
        verification_url=_verification_url(),
        report_settings={
            "title": "Personnel Training Master Record",
            "subtitle": "Tenant-controlled form",
            "form_no": "TRN/99",
            "revision": "07",
            "issue_date": "17 Aug 2026",
            "footer_note": "Controlled by Quality",
            "show_compliance_summary": False,
            "show_training_history": False,
            "show_scheduled_events": False,
            "show_deferrals": False,
        },
    )

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    assert "PERSONNEL TRAINING MASTER RECORD" in text
    assert "Tenant-controlled form" in text
    assert "TRN/99 Rev 07" in text
    assert "Controlled by Quality" in text
    assert "Training record log" not in text
    assert "Scheduled training and events" not in text
    assert "Deferral and extension history" not in text


def test_generated_pdf_qr_decodes_to_absolute_signed_verification_url():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    verify_url = (
        "https://portal.example.test/public/training/users/ID-FL28MRNH/verify"
        "?format=html&amo=safarilink&report_token=trp1.ID-Q50VN737.ID-FL28MRNH.signature"
    )
    pdf_bytes = _compact_pdf_builder(
        lambda *args, **kwargs: b"legacy",
        user=_pdf_user(),
        amo=SimpleNamespace(name="Safarilink Aviation Limited"),
        logo_path=None,
        status_items=[],
        records=[],
        course_by_id={},
        upcoming_events=[],
        deferrals=[],
        verification_url=verify_url,
        report_settings={},
    )

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    scale = 4
    pixmap = document[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
    detector = cv2.QRCodeDetector()
    decoded, _points, _straight = detector.detectAndDecode(image)
    if not decoded:
        # The controlled identity block keeps the QR in the upper-right quadrant;
        # crop there as a robust fallback for OpenCV builds that dislike page text.
        crop = image[0 : min(image.shape[0], 900), max(0, image.shape[1] - 900) : image.shape[1]]
        decoded, _points, _straight = detector.detectAndDecode(crop)

    assert decoded
    parsed = urlsplit(decoded)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "portal.example.test"
    assert parsed.path == "/public/training/users/ID-FL28MRNH/verify"
    assert query["format"] == ["html"]
    assert query["amo"] == ["safarilink"]
    assert query["report_token"] == ["trp1.ID-Q50VN737.ID-FL28MRNH.signature"]


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
