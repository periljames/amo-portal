from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from amodb.apps.work.package_schemas import WorkPackageCreate, WorkPackageUpdate


def test_program_item_lists_are_not_shared_between_packages():
    first = WorkPackageCreate(aircraft_serial_number="AC-1", title="Package one")
    second = WorkPackageCreate(aircraft_serial_number="AC-2", title="Package two")

    first.program_item_ids.append(10)

    assert first.program_item_ids == [10]
    assert second.program_item_ids == []


def test_create_rejects_reversed_planned_window():
    start = datetime.now(UTC)
    with pytest.raises(ValidationError):
        WorkPackageCreate(
            aircraft_serial_number="AC-1",
            title="Invalid package",
            planned_start=start,
            planned_end=start - timedelta(hours=1),
        )


def test_update_rejects_reversed_planned_window_when_both_supplied():
    start = datetime.now(UTC)
    with pytest.raises(ValidationError):
        WorkPackageUpdate(
            planned_start=start,
            planned_end=start - timedelta(minutes=1),
        )
