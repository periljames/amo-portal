from types import SimpleNamespace as Row

from amodb.apps.workforce.supervisor_governance import OrganisationResolver


def snapshot(*, duplicate=False, cycle=False, named=None, primary_conflict=False):
    users = [Row(id=name) for name in ("executive", "manager-a", "manager-b", "officer", "second-manager")]
    units = [Row(id="company", parent_id=None), Row(id="quality", parent_id="company")]
    positions = [
        Row(id="executive", reports_to_position_id="officer" if cycle else None),
        Row(id="manager", reports_to_position_id="executive"),
        Row(id="officer", reports_to_position_id="manager"),
    ]

    def appointment(user, position, unit="quality", base=None, supervisor=None, kind="PRIMARY"):
        return Row(user_id=user, position_id=position, org_unit_id=unit, base_station_id=base,
                   supervisor_user_id=supervisor, placement_type=kind)

    placements = [
        appointment("executive", "executive", "company"),
        appointment("manager-a", "manager", base="base-a"),
        appointment("manager-b", "manager", base="base-b"),
        appointment("officer", "officer", base="base-a", supervisor=named),
    ]
    if duplicate:
        placements.append(appointment("second-manager", "manager", base="base-a"))
    if primary_conflict:
        placements.append(appointment("officer", "officer", base="base-b"))
    return OrganisationResolver(users=users, positions=positions, units=units, placements=placements)


def test_two_base_managers_receive_only_their_actual_reports():
    resolver = snapshot()
    assert resolver.direct_manager("officer").manager_user_id == "manager-a"
    assert resolver.reports("manager-a") == ["officer"]
    assert resolver.reports("manager-b") == []
    assert resolver.reporting_chain("officer") == (["manager-a", "executive"], "ROOT_POSITION")
    assert resolver.reports("executive", indirect=True) == ["manager-a", "manager-b", "officer"]


def test_equal_scope_managers_are_explicitly_ambiguous():
    result = snapshot(duplicate=True).direct_manager("officer")
    assert result.code == "APPROVER_AMBIGUOUS"
    assert result.manager_user_id is None
    assert result.candidate_user_ids == ("manager-a", "second-manager")


def test_named_manager_disambiguates_only_within_actual_parent_scope():
    assert snapshot(duplicate=True, named="second-manager").direct_manager("officer").manager_user_id == "second-manager"
    assert snapshot(named="manager-b").direct_manager("officer").code == "REPORTING_RELATIONSHIP_CONFLICT"


def test_cycle_and_conflicting_primary_appointments_cannot_resolve():
    assert snapshot(cycle=True).direct_manager("officer").code == "REPORTING_CYCLE"
    assert snapshot(primary_conflict=True).direct_manager("officer").code == "APPOINTMENT_CONFLICT"


def test_vacancy_is_not_replaced_with_an_unrelated_role_holder():
    resolver = snapshot()
    resolver.by_position["manager"] = [row for row in resolver.by_position["manager"] if row.user_id != "manager-a"]
    assert resolver.direct_manager("officer").code == "REPORTING_POSITION_VACANT"


def test_invalid_unit_hierarchy_and_missing_identity_fail_explicitly():
    resolver = snapshot()
    resolver.units["company"].parent_id = "quality"
    assert resolver.direct_manager("officer").code == "ORGANISATION_HIERARCHY_INVALID"
    assert resolver.direct_manager("foreign-user").code == "APPOINTMENT_INACTIVE"


def test_matrix_appointment_has_separate_functional_manager():
    resolver = snapshot()
    resolver.by_user["officer"].append(Row(
        user_id="officer", position_id="officer", org_unit_id="quality",
        base_station_id="base-b", supervisor_user_id=None, placement_type="MATRIX",
    ))
    assert resolver.direct_manager("officer").manager_user_id == "manager-a"
    assert resolver.direct_manager("officer", placement_type="MATRIX").manager_user_id == "manager-b"
