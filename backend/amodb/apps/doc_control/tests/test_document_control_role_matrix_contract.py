from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.accounts.models import AccountRole
from amodb.apps.doc_control.workspace_capabilities import document_control_capabilities


def _user(role: AccountRole, *, is_amo_admin: bool = False, is_superuser: bool = False):
    return SimpleNamespace(
        role=role,
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


def test_quality_controller_can_administer_without_inheriting_accountable_approval() -> None:
    inspector = document_control_capabilities(_user(AccountRole.QUALITY_INSPECTOR))
    assert inspector["control"] is True
    assert inspector["edit_properties"] is True
    assert inspector["manage_distribution"] is True
    assert inspector["approve"] is False
    assert inspector["publish"] is False


def test_quality_manager_has_control_and_accountable_decision_capability() -> None:
    manager = document_control_capabilities(_user(AccountRole.QUALITY_MANAGER))
    assert manager["control"] is True
    assert manager["approve"] is True
    assert manager["publish"] is True


def test_tenant_admin_has_administration_and_decision_capability_under_current_policy() -> None:
    admin = document_control_capabilities(_user(AccountRole.AMO_ADMIN, is_amo_admin=True))
    assert admin["control"] is True
    assert admin["approve"] is True
    assert admin["register"] is True
    assert admin["publish"] is True


def test_superuser_capability_is_explicit_not_role_cache_magic() -> None:
    superuser = document_control_capabilities(_user(AccountRole.VIEW_ONLY, is_superuser=True))
    assert superuser["control"] is True
    assert superuser["approve"] is True
    assert superuser["publish"] is True
