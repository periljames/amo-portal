from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from amodb.apps.rostering.services import _ensure_source_owned_state


NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("assignment_status", "owner"),
    [
        ("TRAINING", "Training"),
        ("LEAVE", "Workforce"),
        ("UNAVAILABLE", "Workforce"),
    ],
)
def test_manual_external_state_is_rejected_before_database_mutation(assignment_status, owner):
    with pytest.raises(ValueError, match=owner):
        _ensure_source_owned_state(
            None,
            amo_id="amo-1",
            user_id="user-1",
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=8),
            assignment_status=assignment_status,
            assignment_source="MANUAL",
            source_reference_id=None,
        )


def test_trusted_source_owned_assignment_is_allowed_without_duplicate_checks():
    _ensure_source_owned_state(
        None,
        amo_id="amo-1",
        user_id="user-1",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=8),
        assignment_status="TRAINING",
        assignment_source="TRAINING",
        source_reference_id="event-1",
    )
