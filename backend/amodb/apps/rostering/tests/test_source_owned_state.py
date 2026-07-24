from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import assignments, services
from amodb.apps.rostering.services import _ensure_source_owned_state


NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)


class _Query:
    def __init__(self, result):
        self.result = result

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.result


class _Database:
    def __init__(self, results):
        self.results = iter(results)

    def query(self, *_args, **_kwargs):
        return _Query(next(self.results))


class _BulkPayload:
    def __init__(self, items, *, atomic=False):
        self.assignments = list(items)
        self.atomic = atomic

    def model_copy(self, *, update):
        return _BulkPayload(update.get("assignments", self.assignments), atomic=self.atomic)


@pytest.mark.parametrize(
    ("assignment_status", "owner"),
    [
        ("TRAINING", "Training"),
        ("LEAVE", "Workforce"),
        ("UNAVAILABLE", "Workforce"),
    ],
)
def test_manual_external_state_is_rejected_before_database_mutation(assignment_status, owner):
    with pytest.raises(ValueError, match=owner):
        _ensure_source_owned_state(
            None,
            amo_id="amo-1",
            user_id="user-1",
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=8),
            assignment_status=assignment_status,
            assignment_source="MANUAL",
            source_reference_id=None,
        )


def test_trusted_source_owned_assignment_is_allowed_without_duplicate_checks():
    _ensure_source_owned_state(
        None,
        amo_id="amo-1",
        user_id="user-1",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=8),
        assignment_status="TRAINING",
        assignment_source="TRAINING",
        source_reference_id="event-1",
    )


def test_productive_assignment_requires_active_contract_for_entire_window(monkeypatch):
    monkeypatch.setattr(
        "amodb.apps.rostering.services.workforce_services.active_contract_for_user",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(ValueError, match="active employment contract"):
        _ensure_source_owned_state(
            None,
            amo_id="amo-1",
            user_id="user-1",
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=8),
            assignment_status="DUTY",
            assignment_source="MANUAL",
            source_reference_id=None,
        )


def test_quality_audit_commitment_blocks_productive_assignment(monkeypatch):
    monkeypatch.setattr(
        "amodb.apps.rostering.services.workforce_services.active_contract_for_user",
        lambda *_args, **_kwargs: object(),
    )
    database = _Database([None, None, object()])

    with pytest.raises(ValueError, match="Quality audit"):
        _ensure_source_owned_state(
            database,
            amo_id="amo-1",
            user_id="user-1",
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=8),
            assignment_status="DUTY",
            assignment_source="MANUAL",
            source_reference_id=None,
        )


def test_non_atomic_bulk_preserves_valid_items_and_original_conflict_indexes(monkeypatch):
    bad = SimpleNamespace(
        user_id="bad-user",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=8),
        status="DUTY",
        source="MANUAL",
        source_reference_id=None,
        client_id="bad-client",
    )
    good = SimpleNamespace(
        user_id="good-user",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=8),
        status="DUTY",
        source="MANUAL",
        source_reference_id=None,
        client_id="good-client",
    )
    forwarded = []

    def guard(_db, **kwargs):
        if kwargs["user_id"] == "bad-user":
            raise ValueError("blocking Training commitment")

    def underlying(_db, *, version, actor_user_id, payload):
        del version, actor_user_id
        forwarded.extend(payload.assignments)
        return SimpleNamespace(skipped=[{"index": 0, "reason": "duplicate"}], conflicts=[])

    monkeypatch.setattr(services, "_ensure_source_owned_state", guard)
    monkeypatch.setattr(services, "_bulk_create_assignments", underlying)

    result = services.bulk_create_assignments(
        object(),
        version=SimpleNamespace(amo_id="amo-1"),
        actor_user_id="planner-1",
        payload=_BulkPayload([bad, good], atomic=False),
    )

    assert forwarded == [good]
    assert result.conflicts == [{"index": 0, "client_id": "bad-client", "reason": "blocking Training commitment"}]
    assert result.skipped == [{"index": 1, "reason": "duplicate"}]


def test_pattern_generation_uses_the_guarded_bulk_path():
    assert assignments.bulk_create_assignments is services.bulk_create_assignments
