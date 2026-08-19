from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality.audit_external_report_acknowledgement_router import (
    _ACK_STATEMENT,
    _ack_reason,
    _require_auditee,
)


def _grant(*, participant_type: str = "AUDITEE_GUEST", permissions: list[str] | None = None):
    return SimpleNamespace(
        participant=SimpleNamespace(participant_type=participant_type),
        scope_json=permissions or ["audit:read_summary", "audit:acknowledge"],
    )


def test_issued_report_acknowledgement_is_exact_revision_and_hash_bound():
    report = SimpleNamespace(id="report-revision-3", sha256="b" * 64)
    reason = _ack_reason(report)
    assert "report-revision-3" in reason
    assert "b" * 64 in reason
    assert "acknowledged as received" in reason


def test_auditee_report_acknowledgement_statement_preserves_response_rights():
    assert "acknowledge receipt" in _ACK_STATEMENT
    assert "does not waive" in _ACK_STATEMENT
    assert "corrective-action" in _ACK_STATEMENT


def test_issued_report_actions_require_auditee_participant_and_scoped_permission():
    _require_auditee(_grant(), "audit:acknowledge")

    with pytest.raises(HTTPException) as external_exc:
        _require_auditee(_grant(participant_type="EXTERNAL_AUDITOR"), "audit:read_summary")
    assert external_exc.value.status_code == 403

    with pytest.raises(HTTPException) as permission_exc:
        _require_auditee(_grant(permissions=["audit:read_summary"]), "audit:acknowledge")
    assert permission_exc.value.status_code == 403
