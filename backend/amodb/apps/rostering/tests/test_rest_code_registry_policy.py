from __future__ import annotations

from amodb.apps.rostering import code_registry, models


def test_starter_registry_is_minimal_and_has_no_fixed_working_times():
    assert code_registry.STARTER_CODES == ("D", "X", "RD")
    by_code = {row.code: row for row in code_registry.AMO_STARTER_SHIFTS}

    working_codes = ("D", "X")
    for code in working_codes:
        assert by_code[code].counts_as_duty is True
        assert by_code[code].start is None
        assert by_code[code].end is None
        assert by_code[code].duration_minutes is None
        assert by_code[code].unpaid_break_minutes == 0

    assert by_code["D"].kind == models.ShiftTemplateKind.DAY
    assert by_code["X"].kind == models.ShiftTemplateKind.STANDBY
    assert by_code["RD"].kind == models.ShiftTemplateKind.OFF
    assert by_code["RD"].counts_as_duty is False


def test_historical_rest_aliases_normalize_to_canonical_rd():
    assert code_registry.normalize_shift_code("RD") == "RD"
    assert code_registry.normalize_shift_code("o") == "RD"
    assert code_registry.normalize_shift_code("rr") == "RD"
    assert code_registry.normalize_shift_code("OF") == "RD"


def test_user_defined_working_codes_remain_user_defined():
    assert code_registry.normalize_shift_code("SA") == "SA"
    assert code_registry.normalize_shift_code("XH") == "XH"
    assert code_registry.normalize_shift_code("N1") == "N1"
