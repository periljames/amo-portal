import pytest
from fastapi import HTTPException

from amodb.apps.qms import security
from amodb.apps.qms.router import _record_id_from_parts, _resolve_view
from amodb.apps.qms.security import _permission_matches


class DummyUser:
    role = "SUPERUSER"
    is_superuser = True
    is_amo_admin = False


def test_exact_permission_match():
    assert _permission_matches("qms.audit.view", "qms.audit.view")


def test_wildcard_permission_match():
    assert _permission_matches("qms.*", "qms.audit.close")


def test_global_permission_match_helper_still_matches():
    assert _permission_matches("*", "qms.settings.manage")


def test_permission_mismatch():
    assert not _permission_matches("qms.audit.view", "qms.car.close")


def test_platform_superuser_has_no_role_qms_permission():
    assert security._has_role_permission(DummyUser(), "qms.dashboard.view") is False


def test_platform_superuser_denial_message_is_explicit():
    with pytest.raises(HTTPException) as exc:
        security._deny_platform_superuser()
    assert exc.value.status_code == 403
    assert "Platform superuser" in exc.value.detail


def test_qms_view_resolution_for_filtered_register_route():
    assert _resolve_view("cars", ["overdue"]) == "overdue"
    assert _record_id_from_parts(["overdue"], "quality_cars", "cars") is None


def test_qms_view_resolution_for_record_subroute():
    record_id = "123e4567-e89b-12d3-a456-426614174000"
    assert _resolve_view("cars", [record_id, "root-cause"]) == "root-cause"
    assert _record_id_from_parts([record_id, "root-cause"], "qms_car_root_causes", "cars") == record_id


def test_qms_view_resolution_does_not_treat_long_view_names_as_record_ids():
    assert _resolve_view("change-control", ["pending-approval"]) == "pending-approval"
    assert _record_id_from_parts(["pending-approval"], "qms_change_controls", "change-control") is None
