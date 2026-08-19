from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from amodb.apps.quality.audit_closing_assurance_router import (
    OutputPolicyRevisionCreate,
    _signature_digest,
)


def test_signature_digest_is_bound_to_report_hash_revision_signer_and_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("amodb.apps.quality.audit_closing_assurance_router.SECRET_KEY", "closing-assurance-test-key")
    audit_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    signed_at = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    common = dict(
        amo_id="tenant-1",
        audit_id=audit_id,
        report_revision_id="report-revision-7",
        signer_user_id="quality-manager-1",
        report_sha256="a" * 64,
        reason="Approve the issued report following closing review.",
        nonce="b" * 32,
        signed_at=signed_at,
    )
    first = _signature_digest(**common)
    second = _signature_digest(**common)
    assert first == second
    assert len(first) == 64
    assert _signature_digest(**{**common, "report_sha256": "c" * 64}) != first
    assert _signature_digest(**{**common, "report_revision_id": "report-revision-8"}) != first
    assert _signature_digest(**{**common, "signer_user_id": "quality-manager-2"}) != first
    assert _signature_digest(**{**common, "reason": "Different approval purpose and rationale."}) != first


def test_supplementary_output_policy_requires_explicit_controlled_copy() -> None:
    with pytest.raises(ValidationError):
        OutputPolicyRevisionCreate(
            artifact_policy="CERTIFICATE",
            artifact_title=None,
            artifact_statement=None,
            rationale="Certificate output enabled by approved tenant policy.",
        )

    policy = OutputPolicyRevisionCreate(
        artifact_policy="ATTESTATION",
        artifact_title="Audit conformity attestation",
        artifact_statement="This attestation is issued only under the configured Quality output policy.",
        rationale="Approved Quality output for this tenant and audit class.",
    )
    assert policy.artifact_policy == "ATTESTATION"


def test_report_only_policy_never_requires_supplementary_artifact_copy() -> None:
    policy = OutputPolicyRevisionCreate(
        artifact_policy="REPORT_ONLY",
        rationale="The governed issued audit report is the only authorised closing output.",
    )
    assert policy.artifact_title is None
    assert policy.artifact_statement is None
