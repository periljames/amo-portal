"""Acceptance scenarios staged for Phase 3; no execution claimed in Phase 2."""
import pytest
from fastapi import HTTPException

from amodb.apps.quality.risk_matrix_policy import validate_versioned_risk_matrix


def matrix(version="2026-v1"):
    return {
        "version": version,
        "likelihood_levels": ["UNLIKELY", "LIKELY"],
        "consequence_levels": ["MINOR", "SEVERE"],
        "rating_levels": ["LOW", "MEDIUM", "HIGH"],
        "rating_cells": {
            "UNLIKELY": {"MINOR": "LOW", "SEVERE": "MEDIUM"},
            "LIKELY": {"MINOR": "MEDIUM", "SEVERE": "HIGH"},
        },
    }


def test_accepts_complete_tenant_defined_matrix():
    validate_versioned_risk_matrix(matrix())


@pytest.mark.parametrize("mutation", [
    lambda m: m["rating_cells"]["LIKELY"].pop("SEVERE"),
    lambda m: m["rating_cells"]["LIKELY"].update({"SEVERE": "UNDECLARED"}),
    lambda m: m.update({"likelihood_levels": ["LIKELY", "LIKELY"]}),
    lambda m: m["rating_cells"].update({"NOT_IN_MATRIX": {"MINOR": "LOW"}}),
])
def test_incomplete_or_inconsistent_matrix_fails_closed(mutation):
    payload = matrix()
    mutation(payload)
    with pytest.raises(HTTPException) as failure:
        validate_versioned_risk_matrix(payload)
    assert failure.value.status_code == 422


def test_changed_cells_cannot_reuse_published_matrix_version():
    original = matrix()
    changed = matrix()
    changed["rating_cells"]["LIKELY"]["SEVERE"] = "MEDIUM"
    with pytest.raises(HTTPException) as failure:
        validate_versioned_risk_matrix(changed, original)
    assert failure.value.status_code == 409


def test_changed_matrix_requires_new_version_even_if_levels_constant():
    original = matrix()
    changed = matrix("2026-v2")
    changed["rating_cells"]["LIKELY"]["SEVERE"] = "MEDIUM"
    validate_versioned_risk_matrix(changed, original)
