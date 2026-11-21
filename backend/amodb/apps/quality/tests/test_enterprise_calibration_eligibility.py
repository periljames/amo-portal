"""Stage calibration source eligibility checks; run with real DB in Phase 3."""
from datetime import date, timedelta

from amodb.apps.quality.equipment_calibration_governance_router import _eligibility


def _asset(*, status="SERVICEABLE", due=None, certificate="verified-1"):
    return {
        "id": "qms-asset-1",
        "status": status,
        "due_date": due,
        "payload": {"verified_calibration_id": certificate},
    }


def test_current_independently_verified_calibration_is_eligible():
    today = date(2026, 11, 11)
    result = _eligibility(_asset(due=today + timedelta(days=2)), today=today)
    assert result["eligible"] is True
    assert result["verified_calibration_id"] == "verified-1"


def test_legacy_serviceable_status_cannot_bypass_independent_certificate():
    today = date(2026, 11, 11)
    result = _eligibility(_asset(due=today + timedelta(days=2), certificate=None), today=today)
    assert result["eligible"] is False
    assert result["reason"] == "NO_INDEPENDENTLY_VERIFIED_CALIBRATION"


def test_due_date_boundary_is_inclusive_but_overdue_is_blocked():
    today = date(2026, 11, 11)
    assert _eligibility(_asset(due=today), today=today)["eligible"]
    result = _eligibility(_asset(due=today - timedelta(days=1)), today=today)
    assert result["reason"] == "CALIBRATION_OVERDUE"


def test_quarantined_even_with_current_calibration_is_blocked():
    today = date(2026, 11, 11)
    result = _eligibility(_asset(status="QUARANTINED", due=today + timedelta(days=3)), today=today)
    assert result["eligible"] is False
    assert result["reason"] == "STATUS_QUARANTINED"
