from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.aircraft_architecture.tenant_programmes import overlay


def interval(*limits: tuple[str, str], mode: str = "WHICHEVER_FIRST", phase: str = "INTERVAL"):
    return {
        "schema": "MPD_INTERVAL_V1",
        "groups": [
            {
                "phase": phase,
                "mode": "SINGLE" if len(limits) == 1 else mode,
                "limits": [{"counter": counter, "value": value} for counter, value in limits],
            }
        ],
    }


def test_equal_and_more_restrictive_amp_limits_are_allowed():
    oem = interval(("FH", "600"), ("MO", "12"))
    equal, reasons = overlay.compare_interval_strictness(oem, interval(("FH", "600"), ("MO", "12")))
    assert equal is True
    assert reasons == []

    tighter, reasons = overlay.compare_interval_strictness(oem, interval(("FH", "500"), ("MO", "10")))
    assert tighter is True
    assert reasons == []


def test_any_relaxed_dimension_blocks_amp_even_when_other_dimension_is_tighter():
    oem = interval(("FH", "600"), ("MO", "12"))
    allowed, reasons = overlay.compare_interval_strictness(oem, interval(("FH", "500"), ("MO", "15")))
    assert allowed is False
    assert any("MO" in reason and "exceeds OEM" in reason for reason in reasons)


def test_amp_cannot_remove_an_oem_clock_or_change_due_logic():
    oem = interval(("FH", "600"), ("MO", "12"))
    missing_clock, reasons = overlay.compare_interval_strictness(
        oem,
        {"schema": "MPD_INTERVAL_V1", "groups": [{"phase": "INTERVAL", "mode": "SINGLE", "limits": [{"counter": "FH", "value": "500"}]}]},
    )
    assert missing_clock is False
    assert reasons

    all_due = interval(("FH", "500"), ("MO", "10"), mode="ALL_DUE")
    changed_mode, reasons = overlay.compare_interval_strictness(oem, all_due)
    assert changed_mode is False
    assert any("mode changed" in reason for reason in reasons)


def test_threshold_repeat_phases_are_compared_independently():
    oem = {
        "schema": "MPD_INTERVAL_V1",
        "groups": [
            {"phase": "THRESHOLD", "mode": "SINGLE", "limits": [{"counter": "FC", "value": "40000"}]},
            {"phase": "REPEAT", "mode": "SINGLE", "limits": [{"counter": "FC", "value": "35000"}]},
        ],
    }
    amp = {
        "schema": "MPD_INTERVAL_V1",
        "groups": [
            {"phase": "THRESHOLD", "mode": "SINGLE", "limits": [{"counter": "FC", "value": "39000"}]},
            {"phase": "REPEAT", "mode": "SINGLE", "limits": [{"counter": "FC", "value": "36000"}]},
        ],
    }
    allowed, reasons = overlay.compare_interval_strictness(oem, amp)
    assert allowed is False
    assert any("REPEAT" in reason and "exceeds OEM" in reason for reason in reasons)


def test_opportunity_requirement_cannot_be_rewritten_as_a_numeric_interval():
    oem = {
        "schema": "MPD_INTERVAL_V1",
        "groups": [{"phase": "INTERVAL", "mode": "OPPORTUNITY", "reference": "WHEN ACCESS IS AVAILABLE"}],
    }
    changed = interval(("FH", "100"))
    allowed, reasons = overlay.compare_interval_strictness(oem, changed)
    assert allowed is False
    assert reasons


def test_explicit_series_wins_and_dash8_model_derivation_is_deterministic():
    explicit = SimpleNamespace(series="300", code="DHC8-315", model="DHC-8-315", variant=None)
    assert overlay.derive_series(explicit)[:2] == ("300", "EXPLICIT")

    derived = SimpleNamespace(series=None, code="DHC8-202", model="DHC-8-202", variant=None)
    assert overlay.derive_series(derived)[:2] == ("200", "DERIVED")

    q400 = SimpleNamespace(series=None, code="Q400", model="DHC-8-402", variant="Q400")
    assert overlay.derive_series(q400)[:2] == ("400", "DERIVED")

    unknown = SimpleNamespace(series=None, code="GENERIC", model="UNKNOWN", variant=None)
    assert overlay.derive_series(unknown)[:2] == (None, "UNRESOLVED")
