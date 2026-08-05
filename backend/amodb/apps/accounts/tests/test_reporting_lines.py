from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import reporting_line_schemas as schemas
from amodb.apps.accounts import router_reporting_lines as reporting


def test_reporting_code_normalisation_is_stable() -> None:
    assert reporting._normalise_code(" Chief Crew ") == "CHIEF_CREW"
    assert reporting._normalise_code("line-supervisor") == "LINE_SUPERVISOR"


def test_assignment_period_rejects_invalid_order() -> None:
    with pytest.raises(HTTPException) as exc:
        reporting._date_order(date(2026, 8, 5), date(2026, 8, 4), "Assignment")
    assert exc.value.status_code == 422
    assert "cannot be before" in str(exc.value.detail)


def test_reporting_manager_cannot_be_self() -> None:
    with pytest.raises(HTTPException) as exc:
        reporting._assert_manager_cycle(
            SimpleNamespace(),
            "amo-1",
            "user-1",
            "user-1",
        )
    assert exc.value.status_code == 409
    assert "report to themselves" in str(exc.value.detail)


def test_guided_assignment_uses_decimal_fte() -> None:
    payload = schemas.GuidedAssignmentCreate(
        user_id="user-1",
        position_id="position-1",
        effective_from=date(2026, 8, 5),
        fte_percent="33.33",
    )
    assert isinstance(payload.fte_percent, Decimal)
    assert payload.fte_percent == Decimal("33.33")


def test_display_titles_explicitly_do_not_change_authority() -> None:
    boundary = reporting.AUTHORIZATION_BOUNDARY.lower()
    assert "display titles" in boundary
    assert "maintenance authorisations" in boundary
    assert "capabilities" in boundary


def test_admin_actor_recognises_governed_administration_roles() -> None:
    amo_admin = SimpleNamespace(is_superuser=False, is_amo_admin=False, role="AMO_ADMIN")
    technician = SimpleNamespace(is_superuser=False, is_amo_admin=False, role="TECHNICIAN")
    assert reporting._is_admin_actor(amo_admin) is True
    assert reporting._is_admin_actor(technician) is False
