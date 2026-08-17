from __future__ import annotations

from amodb.apps.rostering import catalog, code_registry, common, models
from amodb.apps.rostering.aircraft_allocation import RosterAircraftAllocation
from amodb.apps.rostering.application_router import router
from amodb.apps.rostering.code_registry_models import RosterShiftTemplatePolicy


def _routes():
    return {
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def test_recommended_amo_starter_codes_are_compact_and_resource_neutral():
    assert code_registry.STARTER_CODES == ("D", "X", "RD")
    assert all(1 <= len(code) <= 2 for code in code_registry.STARTER_CODES)
    assert not {"JKIA", "HA", "H.A", "OS", "SS", "LC"}.intersection(code_registry.STARTER_CODES)


def test_shift_code_normalization_accepts_one_or_two_compact_characters_only():
    assert code_registry.normalize_shift_code(" f1 ") == "F1"
    assert code_registry.normalize_shift_code("m") == "M"
    assert catalog._normalize_shift_code(" o ") == "O"
    assert catalog._normalize_shift_code("n2") == "N2"
    for value in ("H.A", "NIGHT", "ABC", "TOO-LONG-CODE"):
        try:
            code_registry.normalize_shift_code(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid canonical roster code: {value}")
        try:
            catalog._normalize_shift_code(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid catalog roster code: {value}")


def test_implicit_shift_seeding_is_a_noop():
    class ExplodingDb:
        def __getattr__(self, name):
            raise AssertionError(f"Implicit seed touched the database via {name}")

    assert catalog.seed_default_shift_templates(ExplodingDb(), amo_id="tenant") is None


def test_code_registry_and_aircraft_allocation_routes_are_registered():
    routes = _routes()
    required = {
        ("GET", "/rostering/shift-templates/code-registry"),
        ("POST", "/rostering/shift-templates/starter-pack"),
        ("PATCH", "/rostering/shift-templates/{template_id}/policy"),
        ("POST", "/rostering/shift-templates/{template_id}/merge"),
        ("DELETE", "/rostering/shift-templates/{template_id}"),
        ("GET", "/rostering/assignments/{assignment_id}/aircraft-allocations"),
        ("POST", "/rostering/assignments/{assignment_id}/aircraft-allocations"),
        ("DELETE", "/rostering/assignments/{assignment_id}/aircraft-allocations/{allocation_id}"),
    }
    assert required.issubset(routes)


def test_new_tables_keep_shift_policy_and_aircraft_allocation_separate():
    shift_columns = set(RosterShiftTemplatePolicy.__table__.columns.keys())
    aircraft_columns = set(RosterAircraftAllocation.__table__.columns.keys())
    assert {"shift_template_id", "unpaid_break_minutes", "calendar_mode"}.issubset(shift_columns)
    assert {"roster_assignment_id", "aircraft_serial_number", "allocation_type"}.issubset(aircraft_columns)
    assert "aircraft_serial_number" not in shift_columns
    assert "shift_template_id" not in aircraft_columns


def test_shift_department_scope_is_normalized_and_enforced():
    assert set(models.shift_template_departments.c.keys()) == {
        "shift_template_id",
        "department_id",
    }
    tenant_wide = type("Shift", (), {"code": "D", "department_ids": []})()
    common.require_shift_department_scope(tenant_wide, department_id="engineering")

    scoped = type("Shift", (), {"code": "N", "department_ids": ["engineering"]})()
    common.require_shift_department_scope(scoped, department_id="engineering")
    try:
        common.require_shift_department_scope(scoped, department_id="quality")
    except ValueError as exc:
        assert "not available" in str(exc)
    else:
        raise AssertionError("Department-scoped shift accepted outside its scope")
