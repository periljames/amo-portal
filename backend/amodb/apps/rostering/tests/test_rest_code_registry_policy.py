from __future__ import annotations

from amodb.apps.rostering import code_registry, models


def test_starter_registry_is_minimal_configurable_d_x_rd():
    assert code_registry.STARTER_CODES == ("D", "X", "RD")
    by_code = {row.code: row for row in code_registry.AMO_STARTER_SHIFTS}

    assert by_code["D"].kind == models.ShiftTemplateKind.DAY
    assert by_code["D"].counts_as_duty is True
    assert by_code["D"].start is None
    assert by_code["D"].end is None

    assert by_code["X"].kind == models.ShiftTemplateKind.STANDBY
    assert by_code["X"].counts_as_duty is True
    assert by_code["X"].start is None
    assert by_code["X"].end is None

    assert by_code["RD"].kind == models.ShiftTemplateKind.OFF
    assert by_code["RD"].counts_as_duty is False


def test_off_and_rest_aliases_normalize_destructively_to_rd():
    assert code_registry.normalize_shift_code("RD") == "RD"
    assert code_registry.normalize_shift_code("o") == "RD"
    assert code_registry.normalize_shift_code("OF") == "RD"
    assert code_registry.normalize_shift_code("rr") == "RD"


def test_user_defined_working_codes_remain_user_defined():
    assert code_registry.normalize_shift_code("SA") == "SA"
    assert code_registry.normalize_shift_code("XH") == "XH"
    assert code_registry.normalize_shift_code("N1") == "N1"
