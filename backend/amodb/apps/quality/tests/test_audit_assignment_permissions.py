from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality.audit_assignment_permissions import (
    fieldwork_execution_user_ids,
    require_audit_fieldwork_write_access,
)


def _audit(**overrides):
    values = {
        "lead_auditor_user_id": "lead-1",
        "observer_auditor_user_id": "observer-1",
        "assistant_auditor_user_id": "assistant-1",
        "supporting_auditor_user_ids": ["support-1", "observer-1"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(user_id: str):
    return SimpleNamespace(
        id=user_id,
        role="AUDITOR",
        is_amo_admin=False,
        is_superuser=False,
    )


def test_legacy_supporting_duplicate_does_not_grant_observer_execution() -> None:
    audit = _audit()

    assert fieldwork_execution_user_ids(audit) == {"lead-1", "assistant-1", "support-1"}
    with pytest.raises(HTTPException) as exc:
        require_audit_fieldwork_write_access(_user("observer-1"), audit)
    assert exc.value.status_code == 403
    assert "read-only" in str(exc.value.detail).lower()


def test_explicit_executing_seats_remain_authoritative_for_legacy_overlap() -> None:
    audit = _audit(
        lead_auditor_user_id="observer-1",
        observer_auditor_user_id="observer-1",
    )

    assert "observer-1" in fieldwork_execution_user_ids(audit)
    require_audit_fieldwork_write_access(_user("observer-1"), audit)
