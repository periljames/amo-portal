from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.quality.audit_checklist_execution_router import (
    FieldworkFindingMutation,
    FieldworkMutation,
    _canonical_from_legacy,
    _finding_classification,
    _legacy_from_canonical,
    _mutation_hash,
)
from amodb.apps.quality.enums import FindingLevel, QMSFindingType


CAPTURED_AT = datetime(2026, 8, 16, 10, 30, tzinfo=timezone.utc)


def _payload(**overrides):
    values = {
        "client_mutation_id": "qms-fieldwork-11111111",
        "device_id": "qms-device-11111111",
        "device_sequence": 42,
        "client_timestamp": CAPTURED_AT,
        "base_version": 3,
        "operation": "CHECKLIST_UPDATE",
        "canonical_response_status": "COMPLIANT",
        "auditor_notes": "Checked against the controlled maintenance record.",
        "evidence_references": [{"type": "document", "id": "DOC-001"}],
        "reason": "Live audit fieldwork checklist update.",
    }
    values.update(overrides)
    return FieldworkMutation(**values)


def _finding_payload(**overrides):
    values = {
        "client_mutation_id": "qms-fieldwork-finding-11111111",
        "device_id": "qms-device-11111111",
        "device_sequence": 43,
        "client_timestamp": CAPTURED_AT,
        "base_version": 3,
        "operation": "CREATE_FINDING",
        "canonical_response_status": "NONCOMPLIANT",
        "severity": "MAJOR",
        "level": "LEVEL_2",
        "requirement_ref": "QMSM 4.2.3",
        "description": "An obsolete controlled procedure revision was available at a sampled point of use.",
        "objective_evidence": "Station copy Rev 2 versus current Rev 4.",
        "auditor_notes": "Confirmed against the controlled DMS revision.",
        "evidence_references": [{"type": "photo", "id": "IMG-001"}],
        "reason": "Live audit fieldwork non-conformity recorded atomically.",
    }
    values.update(overrides)
    return FieldworkFindingMutation(**values)


def test_fieldwork_mutation_hash_is_stable_for_identical_replay():
    first = _payload()
    second = _payload()
    assert _mutation_hash(first) == _mutation_hash(second)
    assert len(_mutation_hash(first)) == 64


def test_fieldwork_mutation_hash_changes_when_replayed_content_changes():
    original = _payload()
    changed = _payload(canonical_response_status="NOT_APPLICABLE")
    assert _mutation_hash(original) != _mutation_hash(changed)


def test_fieldwork_mutation_hash_includes_client_capture_timestamp():
    original = _payload()
    changed = _payload(client_timestamp=datetime(2026, 8, 16, 10, 31, tzinfo=timezone.utc))
    assert _mutation_hash(original) != _mutation_hash(changed)


def test_fieldwork_mutation_requires_version_device_order_and_capture_metadata():
    with pytest.raises(ValidationError):
        _payload(base_version=-1)
    with pytest.raises(ValidationError):
        _payload(device_sequence=-1)
    with pytest.raises(ValidationError):
        _payload(client_mutation_id="short")
    with pytest.raises(ValidationError):
        _payload(device_id="short")
    with pytest.raises(ValidationError):
        _payload(client_timestamp=None)


def test_fieldwork_mutation_preserves_canonical_legacy_compatibility():
    assert _canonical_from_legacy("NON_CONFORMING") == "NONCOMPLIANT"
    assert _canonical_from_legacy("PENDING") == "NOT_VERIFIED"
    assert _legacy_from_canonical("NONCOMPLIANT") == "NON_CONFORMING"
    assert _legacy_from_canonical("NOT_VERIFIED") == "PENDING"


def test_atomic_finding_classification_reuses_governed_levels():
    level, finding_type = _finding_classification(_finding_payload())
    assert level == FindingLevel.LEVEL_2
    assert finding_type == QMSFindingType.NON_CONFORMITY

    observation = _finding_payload(
        client_mutation_id="qms-fieldwork-finding-22222222",
        canonical_response_status="OBSERVATION",
        severity="MINOR",
        level="LEVEL_4",
    )
    level, finding_type = _finding_classification(observation)
    assert level == FindingLevel.LEVEL_4
    assert finding_type == QMSFindingType.OBSERVATION


def test_atomic_finding_rejects_response_classification_mismatch():
    invalid = _finding_payload(
        canonical_response_status="OBSERVATION",
        severity="MAJOR",
        level="LEVEL_2",
    )
    with pytest.raises(HTTPException) as exc:
        _finding_classification(invalid)
    assert exc.value.status_code == 422
