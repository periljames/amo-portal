from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EffectivityResult:
    applicable: bool
    explanations: list[str]


def _lookup(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _normalise(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().upper()
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    actual_n = _normalise(actual)
    expected_n = _normalise(expected)

    if operator in {"eq", "equals"}:
        return actual_n == expected_n
    if operator in {"neq", "not_equals"}:
        return actual_n != expected_n
    if operator == "in":
        return actual_n in (expected_n or [])
    if operator == "not_in":
        return actual_n not in (expected_n or [])
    if operator == "between":
        if actual is None or not isinstance(expected, list) or len(expected) != 2:
            return False
        return expected[0] <= actual <= expected[1]
    if operator == "exists":
        return (actual is not None) is bool(expected)
    if operator == "contains":
        if actual is None:
            return False
        if isinstance(actual_n, (list, tuple, set)):
            return expected_n in actual_n
        return str(expected_n) in str(actual_n)
    if operator == "contains_any":
        values = actual_n if isinstance(actual_n, list) else [actual_n]
        return any(item in values for item in (expected_n or []))
    if operator == "contains_all":
        values = actual_n if isinstance(actual_n, list) else [actual_n]
        return all(item in values for item in (expected_n or []))
    if operator == "prefix":
        return actual_n is not None and str(actual_n).startswith(str(expected_n))
    if operator == "gt":
        return actual is not None and actual > expected
    if operator == "gte":
        return actual is not None and actual >= expected
    if operator == "lt":
        return actual is not None and actual < expected
    if operator == "lte":
        return actual is not None and actual <= expected
    raise ValueError(f"Unsupported effectivity operator: {operator}")


def evaluate_effectivity(expression: dict[str, Any] | None, context: dict[str, Any]) -> EffectivityResult:
    """Evaluate an explainable effectivity expression.

    Supported shapes:
    - {}: universally applicable
    - {"all": [expr, ...]}
    - {"any": [expr, ...]}
    - {"not": expr}
    - {"field": "aircraft.model_code", "operator": "eq", "value": "DHC8-315"}
    """
    expression = expression or {}
    if not expression:
        return EffectivityResult(True, ["No restrictive effectivity criteria were defined."])

    if "all" in expression:
        children = [evaluate_effectivity(child, context) for child in expression.get("all") or []]
        applicable = all(child.applicable for child in children)
        explanations = [f"ALL: {line}" for child in children for line in child.explanations]
        return EffectivityResult(applicable, explanations or ["ALL group contained no criteria."])

    if "any" in expression:
        children = [evaluate_effectivity(child, context) for child in expression.get("any") or []]
        applicable = any(child.applicable for child in children)
        explanations = [f"ANY: {line}" for child in children for line in child.explanations]
        return EffectivityResult(applicable, explanations or ["ANY group contained no criteria."])

    if "not" in expression:
        child = evaluate_effectivity(expression.get("not") or {}, context)
        return EffectivityResult(
            not child.applicable,
            [f"NOT: {line}" for line in child.explanations],
        )

    field = str(expression.get("field") or "").strip()
    operator = str(expression.get("operator") or "eq").strip().lower()
    expected = expression.get("value")
    if not field:
        raise ValueError("Effectivity leaf expression requires a field")
    actual = _lookup(context, field)
    applicable = _compare(actual, operator, expected)
    state = "matched" if applicable else "did not match"
    return EffectivityResult(
        applicable,
        [f"{field} {state}: actual={actual!r}, operator={operator}, expected={expected!r}"],
    )


def validate_expression(expression: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []

    def walk(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path} must be an object")
            return
        logical_keys = [key for key in ("all", "any", "not") if key in node]
        if logical_keys:
            if len(logical_keys) != 1:
                errors.append(f"{path} may contain only one logical operator")
                return
            key = logical_keys[0]
            value = node[key]
            if key in {"all", "any"}:
                if not isinstance(value, list) or not value:
                    errors.append(f"{path}.{key} must be a non-empty list")
                    return
                for index, child in enumerate(value):
                    walk(child, f"{path}.{key}[{index}]")
            else:
                walk(value, f"{path}.not")
            return
        if not node:
            return
        if not node.get("field"):
            errors.append(f"{path}.field is required")
        operator = str(node.get("operator") or "eq").lower()
        supported = {
            "eq", "equals", "neq", "not_equals", "in", "not_in", "between",
            "exists", "contains", "contains_any", "contains_all", "prefix",
            "gt", "gte", "lt", "lte",
        }
        if operator not in supported:
            errors.append(f"{path}.operator '{operator}' is unsupported")
        if operator != "exists" and "value" not in node:
            errors.append(f"{path}.value is required for operator '{operator}'")

    walk(expression or {}, "effectivity")
    return errors
