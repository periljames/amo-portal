from __future__ import annotations

from typing import Any

CANONICAL_RESPONSE_VALUES = {
    "COMPLIANT",
    "NONCOMPLIANT",
    "OBSERVATION",
    "NOT_APPLICABLE",
    "NOT_VERIFIED",
}

_DEFAULT_SCHEMES: dict[str, list[dict[str, str]]] = {
    "COMPLIANCE": [
        {"value": "COMPLIANT", "label": "Compliant", "canonical_status": "COMPLIANT"},
        {"value": "NONCOMPLIANT", "label": "NCR", "canonical_status": "NONCOMPLIANT"},
        {"value": "OBSERVATION", "label": "Observation", "canonical_status": "OBSERVATION"},
        {"value": "NOT_APPLICABLE", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
        {"value": "NOT_VERIFIED", "label": "Not verified", "canonical_status": "NOT_VERIFIED"},
    ],
    "COMPLIANT_NONCOMPLIANT_OBSERVATION_NA_NOT_VERIFIED": [
        {"value": "COMPLIANT", "label": "Compliant", "canonical_status": "COMPLIANT"},
        {"value": "NONCOMPLIANT", "label": "NCR", "canonical_status": "NONCOMPLIANT"},
        {"value": "OBSERVATION", "label": "Observation", "canonical_status": "OBSERVATION"},
        {"value": "NOT_APPLICABLE", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
        {"value": "NOT_VERIFIED", "label": "Not verified", "canonical_status": "NOT_VERIFIED"},
    ],
    "COMPLIANT_NONCOMPLIANT_NA": [
        {"value": "COMPLIANT", "label": "Compliant", "canonical_status": "COMPLIANT"},
        {"value": "NONCOMPLIANT", "label": "Noncompliant", "canonical_status": "NONCOMPLIANT"},
        {"value": "NOT_APPLICABLE", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
    ],
    "YES_NO_NA": [
        {"value": "YES", "label": "Yes", "canonical_status": "COMPLIANT"},
        {"value": "NO", "label": "No", "canonical_status": "NONCOMPLIANT"},
        {"value": "N/A", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
    ],
    # TEXT historically used the same governed disposition buttons while the
    # narrative itself lived in auditor notes. Preserve that behavior rather
    # than making existing TEXT checklist revisions unexecutable.
    "TEXT": [
        {"value": "COMPLIANT", "label": "Compliant", "canonical_status": "COMPLIANT"},
        {"value": "NONCOMPLIANT", "label": "NCR", "canonical_status": "NONCOMPLIANT"},
        {"value": "OBSERVATION", "label": "Observation", "canonical_status": "OBSERVATION"},
        {"value": "NOT_APPLICABLE", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
        {"value": "NOT_VERIFIED", "label": "Not verified", "canonical_status": "NOT_VERIFIED"},
    ],
}


def normalise_response_options(
    response_type: str | None,
    provided: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Return the governed source response vocabulary for one checklist item.

    A template may supply its own response values and explicit semantic mapping.
    Ambiguous source vocabularies (for example U/S) are never inferred here.
    """
    scheme = str(response_type or "COMPLIANCE").strip().upper() or "COMPLIANCE"
    rows = list(provided or [])
    if not rows:
        default = _DEFAULT_SCHEMES.get(scheme)
        if default is not None:
            return [dict(item) for item in default]
        raise ValueError(
            f"Response type {scheme!r} has no explicit response_options. "
            "Define each source response value and its canonical_status; ambiguous abbreviations are not inferred."
        )

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in rows:
        value = str(raw.get("value") or "").strip()
        label = str(raw.get("label") or value).strip()
        canonical = str(raw.get("canonical_status") or "").strip().upper()
        if not value or len(value) > 64:
            raise ValueError("Each response option requires a value of 1-64 characters.")
        if not label or len(label) > 80:
            raise ValueError("Each response option requires a label of 1-80 characters.")
        if canonical not in CANONICAL_RESPONSE_VALUES:
            raise ValueError(f"Unsupported canonical response status for {value!r}: {canonical!r}.")
        key = value.upper()
        if key in seen:
            raise ValueError(f"Duplicate response option value: {value!r}.")
        seen.add(key)
        result.append({"value": value, "label": label, "canonical_status": canonical})
    return result


def resolve_response_value(
    *,
    response_type: str | None,
    response_options: list[dict[str, Any]] | None,
    response_value: str | None,
    canonical_status: str,
) -> str:
    """Validate a fieldwork selection against the frozen checklist snapshot.

    Legacy callers that send only a canonical status remain valid only when the
    frozen scheme maps that status to one unambiguous source value.
    """
    options = normalise_response_options(response_type, response_options)
    canonical = str(canonical_status or "").strip().upper()
    if response_value is not None:
        requested = str(response_value).strip()
        option = next((row for row in options if row["value"] == requested), None)
        if option is None:
            raise ValueError(f"Response value {requested!r} is not allowed by this checklist item.")
        if option["canonical_status"] != canonical:
            raise ValueError(
                f"Response value {requested!r} maps to {option['canonical_status']}, not {canonical}."
            )
        return option["value"]

    candidates = [row["value"] for row in options if row["canonical_status"] == canonical]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        "This checklist response scheme requires the source response_value to be supplied explicitly."
    )
