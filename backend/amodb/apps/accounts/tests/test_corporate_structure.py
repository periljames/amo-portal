from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import router_corporate_structure as corporate


def test_normalise_corporate_codes_are_stable() -> None:
    assert corporate._normalise_code(" quality & compliance ") == "QUALITY_&_COMPLIANCE"
    assert corporate._normalise_code("base-maintenance") == "BASE_MAINTENANCE"


def test_effective_date_order_rejects_end_before_start() -> None:
    with pytest.raises(HTTPException) as exc:
        corporate._date_order(date(2026, 8, 5), date(2026, 8, 4), "Assignment")
    assert exc.value.status_code == 422
    assert "cannot be before" in str(exc.value.detail)


def test_reporting_manager_cannot_be_self() -> None:
    with pytest.raises(HTTPException) as exc:
        corporate._assert_manager_chain(
            SimpleNamespace(),
            amo_id="amo-1",
            user_id="user-1",
            manager_user_id="user-1",
        )
    assert exc.value.status_code == 409
    assert "own reporting manager" in str(exc.value.detail)


def test_readiness_does_not_treat_an_account_as_a_complete_personnel_record() -> None:
    score, gaps = corporate._readiness(None, None, None, [])
    assert score == 14
    assert "No active primary position assignment" in gaps
    assert "Identity has not been verified" in gaps
    assert "Required training is not current" in gaps


def test_contingent_engagements_remain_time_bound_and_sponsor_owned() -> None:
    assert "INTERN" in corporate.TIME_BOUND_ENGAGEMENTS
    assert "INTERN" in corporate.SPONSOR_REQUIRED_ENGAGEMENTS
    assert "CONTRACTOR" in corporate.TIME_BOUND_ENGAGEMENTS
    assert "CONTRACTOR" in corporate.SPONSOR_REQUIRED_ENGAGEMENTS
    assert "EMPLOYEE" not in corporate.TIME_BOUND_ENGAGEMENTS
