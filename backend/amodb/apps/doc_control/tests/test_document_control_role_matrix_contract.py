from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.accounts.models import AccountRole
from amodb.apps.doc_control.workspace_capabilities import document_control_capabilities


def _user(role: AccountRole, *, is_amo_admin: bool = False, is_superuser: bool = False):
    return SimpleNamespace(
        role=role,
        amo_id="tenant-a",
        is_active=True,
        is_amo_admin=is_amo_admin,
        is_superuser=is_superuser,
    )


def test_document_control_role_matrix_keeps_reader_and_technical_roles_non_global() -> None:
    ordinary_reader = document_control_capabilities(_user(AccountRole.VIEW_ONLY))
    technical_user = document_control_capabilities(_user(AccountRole.TECHNICIAN))

    for capabilities in (ordinary_reader, technical_user):
        assert capabilities["read"] is True
        assert capabilities["control"] is False
        assert capabilities["approve"] is False
        assert capabilities["edit_properties"] is False
        assert capabilities["publish"] is False


def test_quality_inspector_does_not_inherit_document_controller_authority() -> None:
    inspector = document_control_capabilities(_user(AccountRole.QUALITY_INSPECTOR))
    assert inspector["control"] is False
    assert inspector["edit_properties"] is False
    assert inspector["manage_distribution"] is False
    assert inspector["approve"] is False
    assert inspector["publish"] is False


def test_document_control_officer_can_administer_without_approval() -> None:
    controller = document_control_capabilities(_user(AccountRole.DOCUMENT_CONTROL_OFFICER))
    assert controller["persona"] == "DOCUMENT_CONTROL"
    assert controller["control"] is True
    assert controller["edit_properties"] is True
    assert controller["manage_distribution"] is True
    assert controller["manage_authority_records"] is True
    assert controller["approve"] is False
    assert controller["publish"] is True


def test_quality_manager_does_not_inherit_global_dms_control_or_accountable_approval() -> None:
    manager = document_control_capabilities(_user(AccountRole.QUALITY_MANAGER))
    assert manager["persona"] == "READER"
    assert manager["control"] is False
    assert manager["approve"] is False
    assert manager["publish"] is False


def test_accountable_executive_approves_without_becoming_the_librarian() -> None:
    accountable = document_control_capabilities(_user(AccountRole.ACCOUNTABLE_EXECUTIVE))
    assert accountable["persona"] == "ACCOUNTABLE_EXECUTIVE"
    assert accountable["read"] is True
    assert accountable["approve"] is True
    assert accountable["accountable_approval"] is True
    assert accountable["control"] is False
    assert accountable["upload_revision"] is False
    assert accountable["manage_distribution"] is False
    assert accountable["publish"] is False


def test_tenant_admin_overlay_includes_document_control_authority() -> None:
    admin = document_control_capabilities(_user(AccountRole.AMO_ADMIN, is_amo_admin=True))
    assert admin["persona"] == "ADMIN"
    assert admin["control"] is True
    assert admin["approve"] is True
    assert admin["register"] is True
    assert admin["publish"] is True


def test_superuser_remains_outside_tenant_document_decisions() -> None:
    superuser = document_control_capabilities(_user(AccountRole.VIEW_ONLY, is_superuser=True))
    assert superuser["control"] is False
    assert superuser["approve"] is False
    assert superuser["publish"] is False
