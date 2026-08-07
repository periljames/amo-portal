from decimal import Decimal

import pytest

from amodb.apps.aircraft_architecture.daily_utilisation.services import (
    ComponentState,
    Override,
    blockers_for,
    build_exposures,
)


def component(
    component_id: int,
    position: str,
    *,
    role: str,
    hours: str | None = "100.00",
    cycles: int | None = 50,
):
    return ComponentState(
        component_id=component_id,
        position=position,
        description=position,
        role=role,
        current_hours=Decimal(hours) if hours is not None else None,
        current_cycles=cycles,
    )


def test_shared_daily_increment_propagates_only_to_explicit_engine_and_prop_roles():
    rows = build_exposures(
        daily_hours=Decimal("4.25"),
        daily_cycles=3,
        airframe_hours=Decimal("1200.00"),
        airframe_cycles=800,
        components=[
            component(1, "LH ENGINE", role="ENGINE"),
            component(2, "RH ENGINE", role="ENGINE"),
            component(3, "LH PROPELLER", role="PROPELLER"),
            component(4, "RH PROPELLER", role="PROPELLER"),
            component(5, "APU", role="APU"),
        ],
    )
    by_position = {row.component_position: row for row in rows}
    for position in (
        "AIRFRAME",
        "LH ENGINE",
        "RH ENGINE",
        "LH PROPELLER",
        "RH PROPELLER",
    ):
        assert by_position[position].hours_delta == Decimal("4.25")
        assert by_position[position].cycles_delta == 3
        assert by_position[position].derivation == "SHARED_DAILY"
    assert by_position["APU"].hours_delta == Decimal("0.00")
    assert by_position["APU"].cycles_delta == 0
    assert by_position["APU"].derivation == "ZERO_DEFAULT"


def test_position_text_never_overrides_authoritative_role_mapping():
    rows = build_exposures(
        daily_hours=Decimal("2.00"),
        daily_cycles=2,
        airframe_hours=Decimal("1000.00"),
        airframe_cycles=500,
        components=[
            component(1, "ENG-1", role="OTHER"),
            component(2, "GENERATOR", role="ENGINE"),
        ],
    )
    by_position = {row.component_position: row for row in rows}
    assert by_position["ENG-1"].target_type == "COMPONENT"
    assert by_position["ENG-1"].hours_delta == Decimal("0.00")
    assert by_position["GENERATOR"].target_type == "ENGINE"
    assert by_position["GENERATOR"].hours_delta == Decimal("2.00")


def test_component_override_requires_explicit_reason_and_changes_only_that_target():
    rows = build_exposures(
        daily_hours=Decimal("2.00"),
        daily_cycles=2,
        airframe_hours=Decimal("1000.00"),
        airframe_cycles=500,
        components=[
            component(1, "LH ENGINE", role="ENGINE"),
            component(2, "RH ENGINE", role="ENGINE"),
        ],
        overrides=[
            Override(
                2,
                Decimal("1.50"),
                1,
                "Engine changed after first sector",
            )
        ],
    )
    by_position = {row.component_position: row for row in rows}
    assert by_position["LH ENGINE"].hours_delta == Decimal("2.00")
    assert by_position["RH ENGINE"].hours_delta == Decimal("1.50")
    assert by_position["RH ENGINE"].cycles_delta == 1
    assert by_position["RH ENGINE"].derivation == "OVERRIDE"
    assert (
        by_position["RH ENGINE"].override_reason
        == "Engine changed after first sector"
    )


def test_missing_baseline_blocks_positive_shared_increment():
    rows = build_exposures(
        daily_hours=Decimal("1.00"),
        daily_cycles=1,
        airframe_hours=Decimal("100.00"),
        airframe_cycles=60,
        components=[
            component(
                1,
                "ENGINE",
                role="ENGINE",
                hours=None,
                cycles=None,
            )
        ],
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
        components=[component(1, "APU", role="APU")],
        overrides=[Override(1, Decimal("0.75"), 0, "APU operated on ground")],
    )
    apu = rows[1]
    assert apu.target_type == "APU"
    assert apu.hours_delta == Decimal("0.75")
    assert apu.cycles_delta == 0


@pytest.mark.parametrize("role", ["", "engine-one", "PROPS", "COMPONENT"])
def test_uncontrolled_roles_are_rejected(role):
    with pytest.raises(ValueError, match="not controlled"):
        build_exposures(
            daily_hours=Decimal("1.00"),
            daily_cycles=1,
            airframe_hours=Decimal("100.00"),
            airframe_cycles=60,
            components=[component(1, "ANY", role=role)],
        )
