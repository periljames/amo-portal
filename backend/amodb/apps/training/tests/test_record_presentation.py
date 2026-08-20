from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from amodb.apps.training import compliance
from amodb.apps.training import models as training_models
from amodb.apps.training.record_presentation import (
    _training_profile_html,
    absolute_training_verification_url,
    canonical_public_origin,
    explicit_recurrence_key,
    is_recurrent_course_explicit,
    mask_public_email,
    mask_public_phone,
    normalized_training_kind,
    training_type_label,
)


def _course(**overrides):
    values = {
        "id": "course-1",
        "course_id": "HF-REF",
        "course_name": "Human Factors in Aviation",
        "kind": training_models.TrainingKind.RECURRENT,
        "status": "Recurrent",
        "group_code": None,
        "prerequisite_course_id": None,
        "frequency_months": 24,
        "planning_lead_days": 45,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _public_payload(*, scheduled=None, logo_url=None, photo_url=None):
    return {
        "tenant": {
            "name": "Safarilink Aviation Limited",
            "brand_accent": "#8a6f20",
            "logo_url": logo_url,
        },
        "user": {
            "full_name": "Mercy Etende",
            "position_title": "Procurement Officer",
            "staff_code": "ETEN01",
            "licence_number": None,
            "is_active": True,
            "photo_url": photo_url,
        },
        "summary": {"current": 1, "due_soon": 0, "overdue": 0, "deferred": 0},
        "requirements": [
            {
                "requirement_key": "group:avsec",
                "course_id": "AVSEC-REF",
                "course_name": "Aviation Security (Refresher)",
                "course_type": "Recurrent",
                "last_completed": "2026-08-04",
                "next_due": "2028-08-04",
                "scheduled": scheduled,
                "compliance_status": "Current",
                "evidence_available": False,
                "record_count": 1,
                "history": [
                    {
                        "record_id": "record-1",
                        "type": "Recurrent",
                        "course_code": "AVSEC-REF",
                        "completed": "2026-08-04",
                    }
                ],
            }
        ],
    }


def test_legacy_refresher_is_presented_as_recurrent_without_touching_code():
    course = _course(kind=training_models.TrainingKind.REFRESHER, course_id="HF-REF")
    assert normalized_training_kind(course.kind) == "RECURRENT"
    assert training_type_label(course.kind) == "Recurrent"
    assert is_recurrent_course_explicit(course) is True
    assert course.course_id == "HF-REF"


def test_continuation_is_recurrent_user_facing_lifecycle_type():
    assert training_type_label(training_models.TrainingKind.CONTINUATION) == "Recurrent"


def test_suffix_does_not_create_a_course_family():
    initial = _course(id="a", course_id="HF-INIT", kind=training_models.TrainingKind.INITIAL)
    recurrent = _course(id="b", course_id="HF-REF", kind=training_models.TrainingKind.RECURRENT)
    courses = [initial, recurrent]
    assert explicit_recurrence_key(initial, courses) == "course:a"
    assert explicit_recurrence_key(recurrent, courses) == "course:b"


def test_explicit_group_code_groups_initial_and_recurrent():
    initial = _course(id="a", course_id="HF-INIT", kind=training_models.TrainingKind.INITIAL, group_code="HF")
    recurrent = _course(id="b", course_id="HF-REF", kind=training_models.TrainingKind.REFRESHER, group_code="HF")
    courses = [initial, recurrent]
    assert explicit_recurrence_key(initial, courses) == explicit_recurrence_key(recurrent, courses) == "group:hf"


def test_explicit_prerequisite_groups_initial_and_recurrent():
    initial = _course(id="a", course_id="SMS-INIT", kind=training_models.TrainingKind.INITIAL)
    recurrent = _course(
        id="b",
        course_id="SMS-REF",
        kind=training_models.TrainingKind.RECURRENT,
        prerequisite_course_id="SMS-INIT",
    )
    courses = [initial, recurrent]
    assert explicit_recurrence_key(initial, courses) == "prerequisite:sms-init"
    assert explicit_recurrence_key(recurrent, courses) == "prerequisite:sms-init"


def test_scheduled_after_next_due_does_not_make_requirement_current():
    item = compliance.build_status_item_from_dates(
        course=_course(),
        last_completion_date=date(2024, 7, 30),
        due_date=date(2026, 7, 30),
        deferral_due=None,
        upcoming_event_id="event-1",
        upcoming_event_date=date(2026, 8, 22),
        today=date(2026, 8, 17),
    )
    assert item.status == "OVERDUE"
    assert item.valid_until == date(2026, 7, 30)
    assert item.upcoming_event_date == date(2026, 8, 22)


def test_scheduled_before_next_due_keeps_current_compliance():
    item = compliance.build_status_item_from_dates(
        course=_course(),
        last_completion_date=date(2025, 8, 5),
        due_date=date(2027, 8, 5),
        deferral_due=None,
        upcoming_event_id="event-2",
        upcoming_event_date=date(2027, 7, 29),
        today=date(2026, 8, 17),
    )
    assert item.status == "OK"
    assert item.valid_until == date(2027, 8, 5)
    assert item.upcoming_event_date == date(2027, 7, 29)


def test_public_phone_masking_local_and_international():
    assert mask_public_phone("0719199733") == "0719 *** 733"
    assert mask_public_phone("+254719199733") == "+254 719 *** 733"


def test_public_email_masking():
    assert mask_public_email("jamesmuisyo99@gmail.com") == "j***99@gmail.com"


def test_absolute_verification_url_uses_explicit_https_origin(monkeypatch):
    monkeypatch.setenv("APP_PUBLIC_BASE_URL", "https://portal.example.test/some/api/path")
    amo = SimpleNamespace(login_slug="safari link", amo_code="AMO-1", id="amo-1")
    url = absolute_training_verification_url(
        db=None,
        user_id="ID / 7",
        amo=amo,
        report_token="trp1.token + special",
    )
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "portal.example.test"
    assert parsed.path == "/public/training/users/ID%20%2F%207/verify"
    assert query["format"] == ["html"]
    assert query["amo"] == ["safari link"]
    assert query["report_token"] == ["trp1.token + special"]


def test_canonical_origin_never_falls_back_to_relative_or_http(monkeypatch):
    for key in ("APP_PUBLIC_BASE_URL", "PUBLIC_APP_URL", "PLATFORM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="Canonical HTTPS public origin"):
        canonical_public_origin(None, None)

    monkeypatch.setenv("APP_PUBLIC_BASE_URL", "http://portal.example.test")
    with pytest.raises(RuntimeError, match="Canonical HTTPS public origin"):
        canonical_public_origin(None, None)


def test_public_html_omits_empty_scheduling_and_duplicate_course_rendering():
    response = _training_profile_html(_public_payload())
    body = response.body.decode("utf-8")

    assert "Not scheduled" not in body
    assert "Scheduled —" not in body
    assert "No public evidence link" not in body
    assert body.count("Aviation Security (Refresher)") == 2  # one row + one next-due callout
    assert "<table" not in body
    assert "class='cards'" not in body


def test_public_html_exposes_native_report_actions_and_ios_visual_contract():
    response = _training_profile_html(_public_payload())
    body = response.body.decode("utf-8")

    assert "data-share-report" in body
    assert "data-copy-link" in body
    assert "data-download-pdf" in body
    assert "data-print-report" in body
    assert "navigator.share" in body
    assert "-apple-system" in body
    assert "backdrop-filter" in body
    assert "viewport-fit=cover" in body


def test_public_html_renders_schedule_only_when_real_event_exists():
    response = _training_profile_html(_public_payload(scheduled="2028-07-28"))
    body = response.body.decode("utf-8")

    assert "Scheduled 28 Jul 2028" in body
    assert "Not scheduled" not in body


def test_public_html_uses_only_safe_high_resolution_image_sources():
    response = _training_profile_html(
        _public_payload(
            logo_url="https://cdn.example.test/tenant-logo@2x.png",
            photo_url="https://cdn.example.test/personnel/mercy@2x.webp",
        )
    )
    body = response.body.decode("utf-8")

    assert "tenant-logo@2x.png" in body
    assert "mercy@2x.webp" in body
    assert "fetchpriority='high'" in body
    assert "decoding='async'" in body

    unsafe = _public_payload(
        logo_url="javascript:alert(1)",
        photo_url="http://insecure.example.test/photo.png",
    )
    unsafe_body = _training_profile_html(unsafe).body.decode("utf-8")
    assert "javascript:" not in unsafe_body
    assert "http://insecure.example.test" not in unsafe_body
