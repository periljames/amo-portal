"""Legacy manual mutation routes must never bypass governed DMS review."""
import pytest
from fastapi import HTTPException
from amodb.apps.manuals import core_router


@pytest.mark.parametrize("action", [
    "approve_quality", "approve_regulator", "publish", "archive",
])
def test_legacy_workflow_cannot_change_approval_or_publication(action):
    with pytest.raises(HTTPException) as denied:
        core_router.transition_revision(
            tenant_slug="tenant", manual_id="manual", rev_id="revision",
            payload=core_router.TransitionRequest(action=action),
            request=None, db=None,
        )
    assert denied.value.status_code == 410
    assert "governed DMS" in denied.value.detail


def test_legacy_lifecycle_transition_is_retired():
    with pytest.raises(HTTPException) as denied:
        core_router.transition_revision_lifecycle(
            tenant_slug="tenant", manual_id="manual", rev_id="revision",
            payload=None, request=None, db=None, current_user=None,
        )
    assert denied.value.status_code == 410
