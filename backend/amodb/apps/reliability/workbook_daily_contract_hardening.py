"""Forward-operation contract corrections for Reliability source records.

Keep record-level provenance fields distinct from dataset payload fields.  This
module runs after the 16-domain catalogue extension and before mapping/default
contracts are imported so every intake path sees one unambiguous canonical
field name.
"""
from __future__ import annotations

from typing import Any

from . import workbook_parity as wp


def _code(value: Any) -> str:
    return str(getattr(value, "value", value))


def apply() -> None:
    structures = next(
        (definition for code, definition in wp.DATASET_CATALOG.items() if _code(code) == "STRUCTURES"),
        None,
    )
    if structures is None:
        raise RuntimeError("STRUCTURES dataset is missing from the Reliability catalogue")

    structural_description = next((field for field in structures.fields if field.key == "description"), None)
    if structural_description is not None:
        structural_description.key = "structural_description"
        structural_description.label = "Structural description"

    # Accept payloads produced by the pre-correction draft contract without
    # keeping the ambiguous field in new templates/mappings.
    original_normalise = wp._normalise_payload

    def normalise(dataset, payload: dict[str, Any]):
        prepared = dict(payload)
        if _code(dataset.code) == "STRUCTURES":
            if "structural_description" not in prepared and "description" in prepared:
                prepared["structural_description"] = prepared.pop("description")
        return original_normalise(dataset, prepared)

    wp._normalise_payload = normalise


apply()
