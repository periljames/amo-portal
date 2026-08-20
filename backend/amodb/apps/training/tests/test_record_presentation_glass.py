from __future__ import annotations

from amodb.apps.training import router as training_router
from amodb.apps.training.record_presentation_glass import (
    _GLASS_CSS,
    _REPORT_SCRIPT,
    _training_profile_html,
)


def _payload():
    return {
        "tenant": {
            "amo_id": "ID-Q50VN737",
            "name": "Safarilink Aviation Limited",
            "brand_accent": "#a7862d",
            "logo_url": "/public/training/brand/ID-Q50VN737/logo",
        },
        "user": {
            "user_id": "ID-FL28MRNH",
            "full_name": "Mercy Etende",
            "position_title": "Procurement Officer",
            "staff_code": "ETEN01",
            "is_active": True,
        },
        "summary": {
            "current": 4,
            "completed": 2,
            "due_soon": 0,
            "overdue": 0,
            "deferred": 0,
        },
        "requirements": [
            {
                "course_id": "AVSEC-REF",
                "course_name": "Aviation Security (Refresher)",
                "course_type": "Recurrent",
                "last_completed": "2026-08-04",
                "next_due": "2028-08-04",
                "scheduled": None,
                "compliance_status": "Current",
                "viewer_record_id": "record-1",
                "viewer_label": "View certificate",
                "history": [
                    {
                        "record_id": "record-1",
                        "type": "Recurrent",
                        "course_code": "AVSEC-REF",
                        "completed": "2026-08-04",
                        "certificate_reference": "TC-SL-2026-001",
                        "hours": 4,
                    }
                ],
            }
        ],
    }


def test_glass_report_is_spacious_card_ui_with_large_brand_surface():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "class='brand-visual'" in body
    assert "width: 158px" in body
    assert "height: 88px" in body
    assert "class='training-grid'" in body
    assert "class='training-card'" in body
    assert "<table" not in body
    assert "backdrop-filter: saturate(190%) blur(30px)" in body
    assert "rgba(255, 255, 255, .56)" in body


def test_glass_report_uses_csp_compliant_same_origin_action_script():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "<script src='/public/training/assets/record-report.js' defer></script>" in body
    assert "navigator.share" not in body
    assert "data-share-report" in body
    assert "data-copy-link" in body
    assert "data-download-pdf" in body
    assert "data-print-report" in body
    assert "navigator.share" in _REPORT_SCRIPT
    assert "/record.pdf" in _REPORT_SCRIPT
    assert "format','pdf" not in _REPORT_SCRIPT
    assert 'format", "pdf' not in _REPORT_SCRIPT


def test_glass_report_has_real_certificate_viewer_contract():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "data-view-certificate" in body
    assert "data-record-id='record-1'" in body
    assert "id='certificate-viewer'" in body
    assert "data-certificate-stage" in body
    assert "Open original" in body
    assert "URL.createObjectURL" in _REPORT_SCRIPT
    assert "certificate-frame" in _REPORT_SCRIPT


def test_glass_report_omits_zero_exception_card_noise_and_fake_scheduling():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "No exceptions" in body
    assert "0 due soon" not in body
    assert "0 overdue" not in body
    assert "Not scheduled" not in body
    assert "Scheduled —" not in body


def test_public_glass_routes_are_installed_on_canonical_public_router():
    paths = {route.path for route in training_router.public_router.routes}

    assert "/public/training/assets/record-report.js" in paths
    assert "/public/training/brand/{amo_id}/logo" in paths
    assert "/public/training/users/{user_id}/record.pdf" in paths
    assert "/public/training/users/{user_id}/records/{record_id}/certificate" in paths


def test_glass_css_retains_blob_frame_viewer_and_ios_system_font_stack():
    assert "-apple-system" in _GLASS_CSS
    assert "-webkit-backdrop-filter" in _GLASS_CSS
    assert ".certificate-viewer::backdrop" in _GLASS_CSS
