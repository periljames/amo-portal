from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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
