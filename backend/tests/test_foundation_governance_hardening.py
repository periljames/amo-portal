from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from amodb.apps.foundations import models, schemas
from amodb.apps.workforce import permissions


def test_invalid_iana_timezone_is_rejected():
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        schemas.BaseStationCreate(
            code="BAD",
            name="Invalid timezone base",
            base_type=models.BaseStationType.LINE_STATION,
            time_zone="Africa/Not-A-Place",
        )


def test_valid_iana_timezone_is_preserved():
    payload = schemas.BaseStationCreate(
        code="WIL",
        name="Wilson Airport",
        base_type=models.BaseStationType.MAIN_BASE,
        time_zone="Africa/Nairobi",
    )
    assert payload.time_zone == "Africa/Nairobi"


@pytest.mark.parametrize(
    "kind",
    [
        models.BaseAssignmentKind.TEMPORARY,
        models.BaseAssignmentKind.RELIEF,
        models.BaseAssignmentKind.TRAINING,
    ],
)
def test_dated_deployment_kinds_require_end_date(kind):
    with pytest.raises(ValidationError, match="require an end date"):
        schemas.UserBaseAssignmentCreate(
            user_id="user-1",
            base_station_id="base-1",
            assignment_kind=kind,
            effective_from=date(2026, 8, 1),
        )


def test_home_base_may_remain_open_ended():
    payload = schemas.UserBaseAssignmentCreate(
        user_id="user-1",
        base_station_id="base-1",
        assignment_kind=models.BaseAssignmentKind.HOME_BASE,
        effective_from=date(2026, 8, 1),
    )
    assert payload.effective_to is None


def test_operating_structure_permissions_are_distinct():
    assert permissions.PermissionCode.ORGANISATION_BASES_VIEW.value == "organisation.bases.view"
    assert permissions.PermissionCode.ORGANISATION_BASES_MANAGE.value == "organisation.bases.manage"
    assert permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW.value == "workforce.deployments.view"
    assert permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE.value == "workforce.deployments.manage"


def test_quality_can_view_but_not_move_personnel():
    assert permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW.value in permissions.QUALITY
    assert permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE.value not in permissions.QUALITY


def test_planner_can_manage_dated_deployments():
    assert permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_VIEW.value in permissions.PLANNER
    assert permissions.PermissionCode.WORKFORCE_DEPLOYMENTS_MANAGE.value in permissions.PLANNER
