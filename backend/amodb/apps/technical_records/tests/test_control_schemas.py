from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from amodb.apps.technical_records.control_schemas import (
    CanonicalUtilisationCreate,
    UsageCorrectionCreate,
)


def test_canonical_utilisation_accepts_opening_totals_without_increment():
    payload = CanonicalUtilisationCreate(
        tail_id="5Y-ABC",
        entry_date="2026-08-04",
        techlog_no="OPENING",
        hours=12500.4,
        cycles=18420,
    )

    assert payload.block_hours is None
    assert payload.entry_cycles is None
    assert payload.hours == 12500.4


def test_usage_correction_requires_a_changed_field():
    with pytest.raises(ValidationError):
        UsageCorrectionCreate(
            reason="Incorrect accepted entry",
            expected_usage_updated_at=datetime.now(UTC),
        )


def test_usage_correction_accepts_increment_change_with_reason():
    payload = UsageCorrectionCreate(
        reason="Techlog hours were transposed during entry.",
        expected_usage_updated_at=datetime.now(UTC),
        block_hours=2.4,
        cycles=3,
    )

    assert payload.block_hours == 2.4
    assert payload.cycles == 3
