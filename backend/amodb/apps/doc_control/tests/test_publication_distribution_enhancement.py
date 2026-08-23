from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control.workspace_capabilities import document_control_capabilities, reader_capabilities
from amodb.apps.doc_control.workspace_publication_distribution import publication_distribution_policy
from amodb.apps.manuals import upload_guard_router


def _user(role: str, *, amo_id: str = "amo-1", superuser: bool = False):
    return SimpleNamespace(
        id=f"user-{role.lower()}",
        role=role,
        amo_id=amo_id,
        is_superuser=superuser,
        is_amo_admin=role == "AMO_ADMIN",
    )


def test_controller_and_publisher_permissions_are_separated() -> None:
    inspector = document_control_capabilities(_user("QUALITY_INSPECTOR"))
    manager = document_control_capabilities(_user("QUALITY_MANAGER"))
    reader = reader_capabilities()

    assert inspector["upload_revision"] is True
    assert inspector["edit_properties"] is True
    assert inspector["publish"] is False
    assert manager["publish"] is True
    assert reader["register"] is False
    assert reader["manage_distribution"] is False


def test_publication_distribution_defaults_to_all_eligible_users() -> None:
    policy = publication_distribution_policy(None)
    assert policy == {
        "auto_issue_on_publish": True,
        "audience_mode": "ALL_ELIGIBLE_USERS",
        "acknowledgement_due_days": 10,
    }


def test_publication_distribution_policy_is_bounded() -> None:
    profile = SimpleNamespace(
        metadata_json={
            "distribution_policy": {
                "auto_issue_on_publish": False,
                "audience_mode": "SELECTED_USERS",
                "acknowledgement_due_days": 9999,
            }
        }
    )
    policy = publication_distribution_policy(profile)
    assert policy["auto_issue_on_publish"] is False
    assert policy["audience_mode"] == "SELECTED_USERS"
    assert policy["acknowledgement_due_days"] == 365


def test_manual_upload_guard_rejects_non_controller(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_guard_router.core,
        "_tenant_by_slug",
        lambda *args, **kwargs: SimpleNamespace(amo_id="amo-1"),
    )
    with pytest.raises(HTTPException) as caught:
        upload_guard_router._require_upload_scope(
            SimpleNamespace(),
            tenant_slug="safarilink",
            current_user=_user("TECHNICIAN"),
        )
    assert caught.value.status_code == 403


def test_manual_upload_guard_rejects_cross_tenant_controller(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_guard_router.core,
        "_tenant_by_slug",
        lambda *args, **kwargs: SimpleNamespace(amo_id="amo-2"),
    )
    with pytest.raises(HTTPException) as caught:
        upload_guard_router._require_upload_scope(
            SimpleNamespace(),
            tenant_slug="other-amo",
            current_user=_user("QUALITY_MANAGER", amo_id="amo-1"),
        )
    assert caught.value.status_code == 403
    assert "outside the active AMO context" in str(caught.value.detail)


def test_frontend_exposes_direct_controlled_actions() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    source = (
        repository_root
        / "frontend"
        / "src"
        / "pages"
        / "documentControl"
        / "DocumentControlPrimaryActions.tsx"
    ).read_text(encoding="utf-8")
    distribution = (
        repository_root
        / "frontend"
        / "src"
        / "pages"
        / "documentControl"
        / "DocumentControlDistributionActions.tsx"
    ).read_text(encoding="utf-8")

    assert "Edit properties" in source
    assert "Upload revision" in source
    assert "Publish and notify users" in source
    assert "ALL_ELIGIBLE_USERS" in distribution
    assert "Issue and notify recipients" in distribution
