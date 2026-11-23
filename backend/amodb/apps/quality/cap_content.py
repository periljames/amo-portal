"""Compatibility for the single corrective action (CAP) narrative."""
from copy import deepcopy


def combine_cap(corrective, preventive):
    values = []
    for value in (corrective, preventive):
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return "\n\n".join(values) or None


def unified_cap(value):
    """Project legacy snapshots without mutating retained historical records."""
    if isinstance(value, list):
        return [unified_cap(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: unified_cap(item) for key, item in deepcopy(value).items()}
    if "preventive_action" in result:
        legacy = result.pop("preventive_action")
        if isinstance(legacy, str) and legacy.strip():
            result["corrective_action"] = combine_cap(result.get("corrective_action"), legacy)
    if result.get("kind") == "PREVENTIVE":
        result["kind"] = "CORRECTIVE"
    if result.get("response_section") == "PREVENTIVE":
        result["response_section"] = "CORRECTIVE"
    return result
