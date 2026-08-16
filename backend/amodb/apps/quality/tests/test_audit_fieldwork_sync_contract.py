from __future__ import annotations

import pytest
from pydantic import ValidationError

from amodb.apps.quality.audit_checklist_execution_router import (
    FieldworkMutation,
    _canonical_from_legacy,
    _legacy_from_canonical,
    _mutation_hash,
)


def _payload(**overrides):
    values = {
        "client_mutation_id": "qms-fieldwork-11111111",
        "device_id": "qms-device-11111111",
        "device_sequence": 42,
        "base_version": 3,
        "operation": "CHECKLIST_UPDATE",
        "canonical_response_status": "COMPLIANT",
        "auditor_notes": "Checked against the controlled maintenance record.",
        "evidence_references": [{"type": "document", "id": "DOC-001"}],
        "reason": "Live audit fieldwork checklist update.",
    }
    values.update(overrides)
    return FieldworkMutation(**values)


def test_fieldwork_mutation_hash_is_stable_for_identical_replay():
    first = _payload()
    second = _payload()
    assert _mutation_hash(first) == _mutation_hash(second)
    assert len(_mutation_hash(first)) == 64


def test_fieldwork_mutation_hash_changes_when_replayed_content_changes():
    original = _payload()
    changed = _payload(canonical_response_status="NOT_APPLICABLE")
    assert _mutation_hash(original) != _mutation_hash(changed)


def test_fieldwork_mutation_requires_version_and_device_order_metadata():
    with pytest.raises(ValidationError):
        _payload(base_version=-1)
    with pytest.raises(ValidationError):
        _payload(device_sequence=-1)
    with pytest.raises(ValidationError):
        _payload(client_mutation_id="short")
    with pytest.raises(ValidationError):
        _payload(device_id="short")


def test_fieldwork_mutation_preserves_canonical_legacy_compatibility():
    assert _canonical_from_legacy("NON_CONFORMING") == "NONCOMPLIANT"
    assert _canonical_from_legacy("PENDING") == "NOT_VERIFIED"
    assert _legacy_from_canonical("NONCOMPLIANT") == "NON_CONFORMING"
    assert _legacy_from_canonical("NOT_VERIFIED") == "PENDING"
