from amodb.apps.accounts.role_registry import (
    AccountRole,
    canonical_position_title,
    canonical_role_key,
    infer_regulated_role,
    role_catalogue,
)


def test_legacy_kcar_titles_resolve_to_canonical_2025_roles():
    assert AccountRole("accountable_manager") is AccountRole.ACCOUNTABLE_EXECUTIVE
    assert AccountRole("CEO") is AccountRole.ACCOUNTABLE_EXECUTIVE
    assert AccountRole("Head of Base Maintenance") is AccountRole.BASE_MAINTENANCE_MANAGER
    assert AccountRole("HOLM") is AccountRole.LINE_MAINTENANCE_MANAGER
    assert AccountRole("Head of Workshop") is AccountRole.WORKSHOP_MANAGER
    assert AccountRole("Head of Quality") is AccountRole.QUALITY_MANAGER
    assert AccountRole("Quality Officer") is AccountRole.QUALITY_OFFICER
    assert AccountRole("QO") is AccountRole.QUALITY_OFFICER
    assert infer_regulated_role("Quality Officer") is None


def test_role_catalogue_has_unique_aliases_and_separates_admin_from_management():
    catalogue = role_catalogue(include_superuser=True)
    keys = {item.key for item in catalogue}
    assert len(keys) == len(catalogue)
    assert canonical_role_key("amo_admin") == "AMO_ADMIN"
    assert canonical_role_key("Accountable Manager") == "ACCOUNTABLE_EXECUTIVE"
    assert infer_regulated_role("Head of Line Maintenance") is AccountRole.LINE_MAINTENANCE_MANAGER
    assert canonical_position_title("HOBM") == "Base Maintenance Manager"
    accountable = next(item for item in catalogue if item.key == "ACCOUNTABLE_EXECUTIVE")
    assert accountable.can_manage_accounts is False
    assert accountable.can_have_supervisor is False
    quality_officer = next(item for item in catalogue if item.key == "QUALITY_OFFICER")
    assert quality_officer.can_manage_accounts is False
