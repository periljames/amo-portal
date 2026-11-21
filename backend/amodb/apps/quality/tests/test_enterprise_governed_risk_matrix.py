"""Phase 3 executable contract coverage (added during Phase 2, NOT RUN).

Governed risk rating must be derived from tenant-controlled lookup cells. A
client may not select an arbitrary low-risk value for a high-risk cell.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality import risk_governance_router as risk


def _assessment(*, rating="HIGH", likelihood="LIKELY", consequence="MAJOR"):
    return risk.Assessment(
        expected_version=1,
        assessment_type="INITIAL",
        matrix_version="tenant-2026-rev-3",
        likelihood=likelihood,
        consequence=consequence,
        rating=rating,
        evidence_basis="Observed recurrent failures and documented business impacts.",
        evidence_record_ids=[],
    )


def _matrix():
    return {
        "version": "tenant-2026-rev-3",
        "likelihood_levels": ["RARE", "LIKELY"],
        "consequence_levels": ["MINOR", "MAJOR"],
        "rating_levels": ["LOW", "MEDIUM", "HIGH"],
        "rating_cells": {
            "RARE": {"MINOR": "LOW", "MAJOR": "MEDIUM"},
            "LIKELY": {"MINOR": "MEDIUM", "MAJOR": "HIGH"},
        },
    }


def test_tenant_matrix_accepts_only_its_governed_cell(monkeypatch):
    monkeypatch.setattr(risk, "_matrix", lambda _db, _ctx: _matrix())
    risk._require_matrix(object(), SimpleNamespace(amo_id="tenant-a"), _assessment())


@pytest.mark.parametrize("rating", ["LOW", "MEDIUM"])
def test_rejects_client_selected_rating_instead_of_calculated_rating(monkeypatch, rating):
    monkeypatch.setattr(risk, "_matrix", lambda _db, _ctx: _matrix())
    with pytest.raises(HTTPException) as failure:
        risk._require_matrix(object(), SimpleNamespace(amo_id="tenant-a"), _assessment(rating=rating))
    assert failure.value.status_code == 422


@pytest.mark.parametrize("change", ["no_cells", "missing_cell", "unknown_rating"])
def test_fails_closed_when_versioned_matrix_cannot_determine_rating(monkeypatch, change):
    matrix = _matrix()
    if change == "no_cells":
        matrix.pop("rating_cells")
    elif change == "missing_cell":
        matrix["rating_cells"]["LIKELY"].pop("MAJOR")
    else:
        matrix["rating_cells"]["LIKELY"]["MAJOR"] = "UNDEFINED"
    monkeypatch.setattr(risk, "_matrix", lambda _db, _ctx: matrix)
    with pytest.raises(HTTPException) as failure:
        risk._require_matrix(object(), SimpleNamespace(amo_id="tenant-a"), _assessment())
    assert failure.value.status_code == 409


def test_risk_matrix_revision_conflict_requires_reassessment(monkeypatch):
    matrix = _matrix()
    matrix["version"] = "tenant-2026-rev-4"
    monkeypatch.setattr(risk, "_matrix", lambda _db, _ctx: matrix)
    with pytest.raises(HTTPException) as failure:
        risk._require_matrix(object(), SimpleNamespace(amo_id="tenant-a"), _assessment())
    assert failure.value.status_code == 409
