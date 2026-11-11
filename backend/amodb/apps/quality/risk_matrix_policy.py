"""Tenant-configured QMS risk matrix: configuration validation and revision control.

No global aviation risk matrix is assumed. A tenant risk assessor supplies only
likelihood/consequence; the server enforces the approved-version lookup cell.
"""
from __future__ import annotations

from typing import Any
from fastapi import HTTPException


def validate_versioned_risk_matrix(candidate: dict[str, Any], previous: dict[str, Any] | None = None) -> None:
    if set(candidate) - {"version", "likelihood_levels", "consequence_levels", "rating_levels", "rating_cells", "description"}:
        raise HTTPException(422, "Unsupported risk matrix configuration keys.")
    version = candidate.get("version")
    if not isinstance(version, str) or not 1 <= len(version.strip()) <= 100:
        raise HTTPException(422, "Risk matrix requires a clear version identifier.")
    for field in ("likelihood_levels", "consequence_levels", "rating_levels"):
        choices = candidate.get(field)
        if (not isinstance(choices, list) or not 1 <= len(choices) <= 12 or
                any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 100 for item in choices) or
                len(set(choices)) != len(choices)):
            raise HTTPException(422, f"Risk matrix {field} must contain 1–12 unique named levels.")
    likelihood = candidate["likelihood_levels"]
    consequence = candidate["consequence_levels"]
    rating = candidate["rating_levels"]
    cells = candidate.get("rating_cells")
    if not isinstance(cells, dict) or set(cells) != set(likelihood):
        raise HTTPException(422, "Every likelihood must have a defined rating row.")
    for level in likelihood:
        row = cells[level]
        if not isinstance(row, dict) or set(row) != set(consequence):
            raise HTTPException(422, "Every likelihood row must cover every consequence exactly once.")
        if any(not isinstance(cell, str) or cell not in rating for cell in row.values()):
            raise HTTPException(422, "All matrix cells must resolve to one declared rating.")
    if previous and isinstance(previous, dict):
        old_version = previous.get("version")
        if old_version == version and previous != candidate:
            raise HTTPException(409, "Editing a published risk matrix requires a new immutable matrix version.")
        if old_version == version and previous == candidate:
            return
        if old_version and old_version == version:
            raise HTTPException(409, "Risk matrix version must change for a new methodology.")
