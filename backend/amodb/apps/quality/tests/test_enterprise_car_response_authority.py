"""The reviewer must see the last committed CAR response across valid lifecycle states.

Prepared for Phase 3. This is a handler contract test, not a substitute for
the PostgreSQL + invited-browser scenario in run 41999293028.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from amodb.apps.quality.schemas import CARInviteUpdate

from amodb.apps.quality import models


router = importlib.import_module("amodb.apps.quality.router")
public_invites = importlib.import_module("amodb.apps.quality.public_invite_extensions")


@pytest.mark.parametrize("car_status", [
    models.CARStatus.PENDING_VERIFICATION,
    models.CARStatus.IN_PROGRESS,
    models.CARStatus.CLOSED,
])
def test_committed_response_visible_to_authorized_reviewer_after_status_change(monkeypatch, car_status):
    car_id = uuid4()
    recorded = SimpleNamespace(id=uuid4(), root_cause="Revised operational RCA")
    car = SimpleNamespace(id=car_id, status=car_status, submitted_at=None)
    reviewer = SimpleNamespace(id="quality-reviewer", amo_id="tenant-a")
    verified = []

    def get_car(_db, *, amo_id, car_id, lock):
        assert amo_id == "tenant-a"
        assert lock is False
        return car

    monkeypatch.setattr(router, "_current_amo_id", lambda _user: "tenant-a")
    monkeypatch.setattr(router, "_get_car_for_amo", get_car)
    monkeypatch.setattr(router, "_require_car_review_access", lambda _db, _user, _car: verified.append("authorized"))
    monkeypatch.setattr(router, "_car_invite_latest_active_response", lambda _db, _id: recorded)
    monkeypatch.setattr(router, "_serialize_car_response", lambda _db, _id, row, *, is_latest: {
        "id": str(row.id), "root_cause": row.root_cause, "is_latest": is_latest,
    })

    result = router.list_car_responses_for_review(
        car_id=car_id, request=None, response=Response(), mark_open=False, db=object(), current_user=reviewer,
    )
    assert verified == ["authorized"]
    assert result == [{"id": str(recorded.id), "root_cause": "Revised operational RCA", "is_latest": True}]


def test_no_submitted_response_does_not_invent_review_evidence(monkeypatch):
    car_id = uuid4()
    car = SimpleNamespace(id=car_id, status=models.CARStatus.IN_PROGRESS, submitted_at=None)
    monkeypatch.setattr(router, "_current_amo_id", lambda _user: "tenant-a")
    monkeypatch.setattr(router, "_get_car_for_amo", lambda *_args, **_kwargs: car)
    monkeypatch.setattr(router, "_require_car_review_access", lambda *_args: None)
    monkeypatch.setattr(router, "_car_invite_latest_active_response", lambda *_args: None)
    assert router.list_car_responses_for_review(
        car_id=car_id, request=None, response=Response(), mark_open=False, db=object(),
        current_user=SimpleNamespace(amo_id="tenant-a"),
    ) == []



@pytest.mark.parametrize("matches_current_submission", [True, False])
def test_public_invite_uses_only_exact_committed_response_snapshot(
    monkeypatch, matches_current_submission,
):
    """A returned CAR cannot surface rejected text after the new response commits."""
    submitted_at = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)
    current = SimpleNamespace(
        id=uuid4(), invite_token="single-car-token",
        car_number="Q-2026-0101", title="Evidence control", summary="Corrective review",
        priority=models.CARPriority.MEDIUM, status=models.CARStatus.PENDING_VERIFICATION,
        due_date=None, target_closure_date=None, next_reminder_at=None,
        submitted_at=submitted_at, root_cause="Original rejected explanation",
        root_cause_text="Original rejected explanation",
        corrective_action="Original rejected action",
        containment_action="Original containment",
        preventive_action="Original prevention",
        evidence_ref="Original evidence",
        submitted_by_name="Responsible Manager",
        submitted_by_email="manager@example.com",
        finding=None,
    )
    stored = SimpleNamespace(
        submitted_at=submitted_at if matches_current_submission else submitted_at - timedelta(days=1),
        root_cause="Revised evidence-backed explanation",
        corrective_action="Revised action",
        containment_action="Revised containment",
        preventive_action="Revised prevention",
        evidence_ref="Revised evidence",
        submitted_by_name="Responsible Manager",
        submitted_by_email="manager@example.com",
    )
    monkeypatch.setattr(router, "_public_request_origin", lambda _request: "https://portal.example")
    monkeypatch.setattr(
        router, "build_car_invite_link",
        lambda _car, *, request_origin: f"{request_origin}/qms/car-access/single-car-token",
    )
    monkeypatch.setattr(router, "_car_invite_state", lambda _db, _car: {"can_edit": False})
    monkeypatch.setattr(router, "_car_invite_latest_active_response", lambda _db, _id: stored)

    projection = router._car_invite_payload(current, db=object())
    if matches_current_submission:
        assert projection["root_cause"] == "Revised evidence-backed explanation"
        assert projection["corrective_action"] == "Revised action"
        assert projection["evidence_ref"] == "Revised evidence"
    else:
        # An older or recalled snapshot must never masquerade as the current one.
        assert projection["root_cause"] == "Original rejected explanation"
        assert projection["corrective_action"] == "Original rejected action"
        assert projection["evidence_ref"] == "Original evidence"



@pytest.mark.parametrize(("canonical", "alias"), [
    ("root_cause", "root_cause_text"),
    ("corrective_action", "capa_text"),
])
def test_public_submission_rejects_conflicting_legacy_narrative_aliases(canonical, alias):
    car = SimpleNamespace(
        root_cause="Retained RCA", root_cause_text="Retained RCA",
        corrective_action="Retained CAPA", capa_text="Retained CAPA",
    )
    payload = CARInviteUpdate(**{canonical: "Revised conclusion", alias: "Old rejected conclusion"})
    with pytest.raises(HTTPException) as rejected:
        public_invites._persist_detailed_response_fields(car, payload)
    assert rejected.value.status_code == 422
    # Reject before changing a CAR, not after producing mismatched evidence.
    assert car.root_cause == car.root_cause_text == "Retained RCA"
    assert car.corrective_action == car.capa_text == "Retained CAPA"


@pytest.mark.parametrize(("canonical", "alias"), [
    ("root_cause", "root_cause_text"),
    ("corrective_action", "capa_text"),
])
def test_public_submission_legacy_only_narrative_keeps_canonical_fields_consistent(canonical, alias):
    car = SimpleNamespace(
        root_cause="Original RCA", root_cause_text="Original RCA",
        corrective_action="Original CAPA", capa_text="Original CAPA",
    )
    public_invites._persist_detailed_response_fields(
        car, CARInviteUpdate(**{alias: "Revised legacy explanation"}),
    )
    assert getattr(car, canonical) == "Revised legacy explanation"
    assert getattr(car, alias) == "Revised legacy explanation"
