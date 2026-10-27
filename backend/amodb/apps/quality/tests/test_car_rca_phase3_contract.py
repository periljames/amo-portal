"""Phase 3 negative contracts for CAR RCA and public bearer access.

These tests exercise live validation and authorization helpers, not hard-coded
source-text patterns or test-only bypasses.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.quality import car_rca_router as rca


def _node(node_id: str, *, kind: str = "FACT", parent: str | None = None):
    return {
        "id": node_id, "parent_id": parent, "statement": f"Documented cause {node_id}",
        "entry_type": kind, "evidence_references": ["EVIDENCE:independent-audit-record"],
    }


def test_branching_five_whys_and_fishbone_roundtrip_without_losing_evidence():
    investigation = rca.InvestigationDocument.model_validate({
        "problem_statement": "A sampled CAR lacked an effectiveness checkpoint.",
        "investigations": [
            {"id": "five", "method": "FIVE_WHYS", "nodes": [
                _node("root"), _node("branch-a", parent="root"),
                _node("branch-b", parent="root"),
                _node("cause", kind="CAUSAL_CONCLUSION", parent="branch-b"),
            ]},
            {"id": "fishbone", "method": "ISHIKAWA", "nodes": [
                dict(_node("bone"), category="People"),
                dict(_node("bone-child", parent="bone"), category="Process"),
            ]},
        ],
        "conclusion": "The CAR lacked a governed independent effectiveness checkpoint.",
        "supported_cause_ids": ["cause"],
        "conclusion_evidence_references": ["EVIDENCE:independent-audit-record"],
    })
    restored = rca.InvestigationDocument.model_validate(investigation.model_dump(mode="json"))
    assert len(restored.investigations) == 2
    assert restored.investigations[0].nodes[2].parent_id == "root"
    assert restored.investigations[1].nodes[1].category == "Process"
    assert restored.supported_cause_ids == ["cause"]


@pytest.mark.parametrize("methods", [
    [{"id": "one", "method": "FIVE_WHYS", "nodes": [_node("a", parent="b"), _node("b", parent="a")]}],
    [{"id": "one", "method": "FIVE_WHYS", "nodes": [_node("a", parent="a")]}],
    [{"id": "one", "method": "FIVE_WHYS", "nodes": [_node("a", parent="elsewhere")]}],
    [{"id": "one", "method": "FIVE_WHYS", "nodes": [_node("duplicate")]},
     {"id": "two", "method": "ISHIKAWA", "nodes": [_node("duplicate")]}],
])
def test_graph_rejects_cycles_cross_method_parents_and_duplicate_cause_ids(methods):
    with pytest.raises(ValidationError):
        rca.InvestigationDocument.model_validate({"investigations": methods})


def test_conclusions_cannot_reference_hypotheses_or_unsubstantiated_causes():
    with pytest.raises(ValidationError):
        rca.InvestigationDocument.model_validate({
            "investigations": [{"id": "one", "method": "FIVE_WHYS",
                                "nodes": [dict(_node("h"), entry_type="HYPOTHESIS")]}],
            "supported_cause_ids": ["h"],
        })
    with pytest.raises(ValidationError):
        rca.InvestigationDocument.model_validate({
            "investigations": [{"id": "one", "method": "FIVE_WHYS",
                                "nodes": [dict(_node("c", kind="CAUSAL_CONCLUSION"),
                                               evidence_references=[])]}],
            "supported_cause_ids": ["c"],
        })


@pytest.mark.parametrize("rows", [
    [{"category": "Finding A", "count": 7}],
    [{"category": "Finding A", "count": 0, "source_ref": "AUDIT:1"}],
    [{"category": "Finding A", "count": -1, "source_ref": "AUDIT:1"}],
    [{"category": "Finding A", "count": True, "source_ref": "AUDIT:1"}],
    [{"category": "Finding A", "count": "7", "source_ref": "AUDIT:1"}],
])
def test_pareto_rejects_untraceable_or_invalid_frequencies(rows):
    with pytest.raises(ValidationError):
        rca.Investigation.model_validate({
            "id": "pareto-1", "method": "PARETO", "context": {"frequencies": rows},
        })


def test_pareto_preserves_traceable_frequency_sources_and_multiple_methods():
    doc = rca.InvestigationDocument.model_validate({
        "investigations": [
            {"id": "p", "method": "PARETO", "context": {
                "sample_size": 10,
                "frequencies": [
                    {"category": "A", "count": 7, "source_ref": "FINDING:A"},
                    {"category": "B", "count": 3, "source_ref": "FINDING:B"},
                ],
            }},
            {"id": "b", "method": "BARRIER_ANALYSIS"},
            {"id": "f", "method": "FMEA"},
        ],
    })
    assert sum(row["count"] for row in doc.investigations[0].context["frequencies"]) == 10
    assert [item.method for item in doc.investigations] == [
        "PARETO", "BARRIER_ANALYSIS", "FMEA",
    ]


def test_invalid_guest_capability_does_not_resolve_any_car():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as error:
        rca._car_for_guest(db, "unknown-guest-capability")
    assert error.value.status_code == 404


@pytest.mark.parametrize("state", ["revoked", "expired"])
def test_revoked_or_expired_guest_capability_denies_access(state):
    db = MagicMock()
    car = SimpleNamespace(id=uuid4(), amo_id="amo-a")
    now = datetime.now(timezone.utc)
    access = SimpleNamespace(
        revoked_at=now if state == "revoked" else None,
        expires_at=(now - timedelta(minutes=1)) if state == "expired" else None,
    )
    with (
        patch.object(rca, "set_postgres_tenant_context") as tenant_context,
        patch.object(rca, "_control_for_car", return_value=access),
    ):
        with pytest.raises(HTTPException) as error:
            rca.assert_invite_access(db, car)
    assert error.value.status_code == 410
    tenant_context.assert_called_once_with(
        db, amo_id="amo-a",
        user_id="00000000-0000-0000-0000-000000000000",
    )


def test_cross_car_attachment_reference_is_rejected_even_for_valid_uuid():
    db = MagicMock()
    car = SimpleNamespace(id=uuid4(), amo_id="amo-a")
    foreign_attachment = uuid4()
    db.query.return_value.filter.return_value.all.return_value = []
    with pytest.raises(HTTPException) as error:
        rca._validate_attachment_references(
            db, car, [f"CAR-ATTACHMENT:{foreign_attachment}"],
        )
    assert error.value.status_code == 422
    assert "different CAR" in str(error.value.detail)
