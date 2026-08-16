from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality.audit_external_finding_draft_router import (
    ExternalFindingDraftCreate,
    _assert_classification,
    _draft_hash,
    _status,
)


CAPTURED_AT = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def payload(**overrides):
    values = {
        "client_mutation_id": "qms-external-draft-11111111",
        "device_id": "qms-external-device-11111111",
        "device_sequence": 101,
        "client_timestamp": CAPTURED_AT,
        "draft_type": "NON_CONFORMITY",
        "proposed_severity": "MAJOR",
        "proposed_level": "LEVEL_2",
        "requirement_ref": "QMSM 4.2.3",
        "description": "An obsolete controlled procedure revision was available at a sampled point of use.",
        "objective_evidence": "Station copy Rev 2 while the DMS controlled revision is Rev 4.",
        "evidence_references": ["photo:IMG-001"],
    }
    values.update(overrides)
    return ExternalFindingDraftCreate(**values)


def test_external_draft_hash_is_replay_stable_and_content_sensitive():
    first = payload()
    second = payload()
    changed = payload(description="A different finding statement that must not share the same mutation receipt.")
    assert _draft_hash(first) == _draft_hash(second)
    assert len(_draft_hash(first)) == 64
    assert _draft_hash(first) != _draft_hash(changed)


def test_external_draft_classification_uses_existing_quality_levels():
    _assert_classification(payload())
    _assert_classification(payload(
        client_mutation_id="qms-external-draft-22222222",
        draft_type="OBSERVATION",
        proposed_severity="MINOR",
        proposed_level="LEVEL_4",
    ))


def test_external_draft_rejects_observation_with_nonconformity_level():
    invalid = payload(
        draft_type="OBSERVATION",
        proposed_severity="MAJOR",
        proposed_level="LEVEL_2",
    )
    with pytest.raises(HTTPException) as exc:
        _assert_classification(invalid)
    assert exc.value.status_code == 422


def test_external_draft_status_is_derived_from_append_only_events():
    row = SimpleNamespace(events=[])
    assert _status(row) == "CREATED"
    row.events = [SimpleNamespace(event_type="CREATED"), SimpleNamespace(event_type="SUBMITTED")]
    assert _status(row) == "SUBMITTED"
    row.events.append(SimpleNamespace(event_type="RETURNED"))
    assert _status(row) == "RETURNED"


def test_returned_revision_content_must_be_superseded_not_mutated_in_place():
    original = payload()
    revision = payload(
        client_mutation_id="qms-external-draft-33333333",
        supersedes_draft_id="draft-returned-1",
        description="Revised statement after Quality review while preserving immutable original history.",
    )
    assert original.supersedes_draft_id is None
    assert revision.supersedes_draft_id == "draft-returned-1"
    assert _draft_hash(original) != _draft_hash(revision)
