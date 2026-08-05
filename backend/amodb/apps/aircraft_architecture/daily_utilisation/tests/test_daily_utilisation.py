from decimal import Decimal

import pytest

from amodb.apps.aircraft_architecture.daily_utilisation.services import (
    ComponentState,
    Override,
    blockers_for,
    build_exposures,
    classify_component,
)


def component(component_id: int, position: str, hours="100.00", cycles=50):
    return ComponentState(
        component_id=component_id,
        position=position,
        description=position,
        current_hours=Decimal(hours) if hours is not None else None,
        current_cycles=cycles,
    )


def test_shared_daily_increment_propagates_to_airframe_engines_and_props():
    rows = build_exposures(
        daily_hours=Decimal("4.25"),
        daily_cycles=3,
        airframe_hours=Decimal("1200.00"),
        airframe_cycles=800,
        components=[
            component(1, "LH ENGINE"),
            component(2, "RH ENGINE"),
            component(3, "LH PROPELLER"),
            component(4, "RH PROPELLER"),
            component(5, "APU"),
        ],
    )
    by_position = {row.component_position: row for row in rows}
    for position in ("AIRFRAME", "LH ENGINE", "RH ENGINE", "LH PROPELLER", "RH PROPELLER"):
        assert by_position[position].hours_delta == Decimal("4.25")
        assert by_position[position].cycles_delta == 3
        assert by_position[position].derivation == "SHARED_DAILY"
    assert by_position["APU"].hours_delta == Decimal("0.00")
    assert by_position["APU"].cycles_delta == 0
    assert by_position["APU"].derivation == "ZERO_DEFAULT"


def test_component_override_requires_explicit_reason_and_changes_only_that_target():
    rows = build_exposures(
        daily_hours=Decimal("2.00"),
        daily_cycles=2,
        airframe_hours=Decimal("1000.00"),
        airframe_cycles=500,
        components=[component(1, "LH ENGINE"), component(2, "RH ENGINE")],
        overrides=[Override(2, Decimal("1.50"), 1, "Engine changed after first sector")],
    )
    by_position = {row.component_position: row for row in rows}
    assert by_position["LH ENGINE"].hours_delta == Decimal("2.00")
    assert by_position["RH ENGINE"].hours_delta == Decimal("1.50")
    assert by_position["RH ENGINE"].cycles_delta == 1
    assert by_position["RH ENGINE"].derivation == "OVERRIDE"
    assert by_position["RH ENGINE"].override_reason == "Engine changed after first sector"


def test_missing_baseline_blocks_positive_shared_increment():
    rows = build_exposures(
        daily_hours=Decimal("1.00"),
        daily_cycles=1,
        airframe_hours=Decimal("100.00"),
        airframe_cycles=60,
        components=[component(1, "ENGINE", hours=None, cycles=None)],
    )
    assert blockers_for(rows) == [
        "ENGINE has no approved utilisation baseline for the requested increment"
    ]


def test_apu_override_is_supported_but_not_implicitly_equal_to_airframe():
    rows = build_exposures(
        daily_hours=Decimal("3.00"),
        daily_cycles=2,
        airframe_hours=Decimal("100.00"),
        airframe_cycles=60,
        components=[component(1, "APU")],
        overrides=[Override(1, Decimal("0.75"), 0, "APU operated on ground")],
    )
    apu = rows[1]
    assert apu.target_type == "APU"
    assert apu.hours_delta == Decimal("0.75")
    assert apu.cycles_delta == 0


@pytest.mark.parametrize(
    ("position", "description", "expected"),
    [
        ("ENG 1", None, "ENGINE"),
        ("RH ENGINE", None, "ENGINE"),
        ("PROP LH", None, "PROPELLER"),
        ("APU", None, "APU"),
        ("NOSE GEAR", None, "COMPONENT"),
    ],
)
def test_component_classification(position, description, expected):
    assert classify_component(position, description) == expected
