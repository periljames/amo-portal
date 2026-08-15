from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from amodb.apps.workforce import schemas


def test_automatic_pattern_requires_an_explicit_anchor():
    with pytest.raises(ValidationError):
        schemas.WorkPatternApplicability(auto_assign=True)


def test_pattern_scope_normalizes_duplicate_selectors():
    rule = schemas.WorkPatternApplicability(
        auto_assign=True,
        anchor_date=date(2026, 7, 31),
        department_ids=["engineering", "engineering", "line"],
        position_ids=["engineer", "engineer"],
        contract_types=["PERMANENT", "PERMANENT", "FIXED_TERM"],
    )

    assert rule.department_ids == ["engineering", "line"]
    assert rule.position_ids == ["engineer"]
    assert [str(value.value) for value in rule.contract_types] == ["FIXED_TERM", "PERMANENT"]


def test_pattern_scope_stays_opt_in_by_default():
    rule = schemas.WorkPatternApplicability()

    assert rule.auto_assign is False
    assert rule.anchor_date is None
    assert rule.department_ids == []
    assert rule.position_ids == []
    assert rule.contract_types == []
