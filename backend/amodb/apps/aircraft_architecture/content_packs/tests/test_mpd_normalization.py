import pytest

from amodb.apps.aircraft_architecture.content_packs.normalization import (
    IntervalParseError,
    parse_interval_text,
)


def test_parse_whichever_first_q400_interval():
    result = parse_interval_text("8000 FH or 72 MO")
    group = result["groups"][0]
    assert group["mode"] == "WHICHEVER_FIRST"
    assert group["limits"] == [
        {"counter": "FH", "value": 8000},
        {"counter": "MO", "value": 72},
    ]


def test_parse_structural_threshold_repeat_cut_in_and_repeat():
    result = parse_interval_text("T 40000 FC; RC 80000 FC; R 34870 FC")
    assert [row["phase"] for row in result["groups"]] == [
        "THRESHOLD",
        "REPEAT_CUT_IN",
        "REPEAT",
    ]
    assert result["groups"][2]["limits"][0] == {"counter": "FC", "value": 34870}


def test_parse_engine_and_apu_hours():
    assert parse_interval_text("4000 EH")["groups"][0]["limits"][0]["counter"] == "EH"
    assert parse_interval_text("1250.25 APUH")["groups"][0]["limits"][0] == {
        "counter": "APUH",
        "value": "1250.25",
    }


def test_parse_opportunity_without_fabricating_numeric_limit():
    result = parse_interval_text("OPPORTUNITY - MRB SYS Note 5")
    assert result["groups"] == [
        {
            "phase": "INTERVAL",
            "mode": "OPPORTUNITY",
            "reference": "OPPORTUNITY - MRB SYS Note 5",
        }
    ]


def test_ambiguous_interval_fails_closed():
    with pytest.raises(IntervalParseError):
        parse_interval_text("Perform as required based on condition")
