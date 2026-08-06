from amodb.apps.accounts import corporate_structure_models as org_models
from amodb.apps.accounts import reporting_line_models as line_models


def _check_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    }


def test_organization_unit_base_station_is_a_real_foreign_key() -> None:
    foreign_keys = org_models.OrganizationUnit.__table__.c.base_station_id.foreign_keys
    assert len(foreign_keys) == 1
    foreign_key = next(iter(foreign_keys))
    assert foreign_key.target_fullname == "base_stations.id"
    assert foreign_key.ondelete == "SET NULL"


def test_assignment_model_contains_effective_period_and_matrix_constraints() -> None:
    names = _check_names(org_models.PositionAssignment.__table__)
    assert "ck_position_assignments_effective_period" in names
    assert "ck_position_assignments_matrix_reason" in names
    assert "ck_position_assignments_fte_range" in names


def test_engagement_and_title_status_constraints_match_migrations() -> None:
    assert (
        "ck_workforce_engagements_effective_period"
        in _check_names(org_models.WorkforceEngagement.__table__)
    )
    assert (
        "ck_personnel_title_preferences_status"
        in _check_names(line_models.PersonnelTitlePreference.__table__)
    )
