from datetime import date

from amodb.apps.training.integration import (
    training_record_status_snapshot,
    training_source_status_snapshot,
)


TODAY = date(2026, 8, 13)


def test_verified_current_record_is_ready() -> None:
    assert training_record_status_snapshot(
        {
            "record_status": "ACTIVE",
            "source_status": "ACTIVE",
            "verification_status": "VERIFIED",
            "valid_until": date(2026, 9, 1),
        },
        as_of=TODAY,
    ) == "READY"


def test_expired_or_unverified_record_never_releases_dms() -> None:
    base = {"record_status": "ACTIVE", "source_status": "ACTIVE"}
    assert training_record_status_snapshot(
        {**base, "verification_status": "VERIFIED", "valid_until": date(2026, 8, 12)},
        as_of=TODAY,
    ) == "EXPIRED"
    assert training_record_status_snapshot(
        {**base, "verification_status": "PENDING", "valid_until": date(2026, 9, 1)},
        as_of=TODAY,
    ) == "PENDING"


def test_superseded_record_never_releases_dms() -> None:
    assert training_record_status_snapshot(
        {
            "record_status": "SUPERSEDED",
            "source_status": "ACTIVE",
            "verification_status": "VERIFIED",
            "valid_until": date(2027, 1, 1),
        },
        as_of=TODAY,
    ) == "SUPERSEDED"


def test_certified_attendance_and_passed_assessment_are_resolved() -> None:
    assert training_source_status_snapshot(
        "training_attendance_windows", {}, fallback="CERTIFIED", as_of=TODAY,
    ) == "COMPLETED"
    assert training_source_status_snapshot(
        "training_assessment_instances", {"outcome": "PASS"}, fallback="APPROVED", as_of=TODAY,
    ) == "READY"
