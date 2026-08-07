from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


MISSING = object()
SUPPORTED_OPERATORS = {
    "eq",
    "ne",
    "in",
    "not_in",
    "gte",
    "lte",
    "gt",
    "lt",
    "between",
    "contains",
    "exists",
}


@dataclass(frozen=True)
class TraceItem:
    path: str
    operator: str
    expected: Any
    actual: Any
    matched: bool
    reason: str


@dataclass(frozen=True)
class EvaluationResult:
    applicable: bool
    reasons: tuple[str, ...]
    trace: tuple[TraceItem, ...]
    unresolved_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "reasons": list(self.reasons),
            "trace": [asdict(item) for item in self.trace],
            "unresolved_paths": list(self.unresolved_paths),
        }


def _lookup(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return MISSING
    return current


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _same(actual: Any, expected: Any) -> bool:
    left = _decimal(actual)
    right = _decimal(expected)
    if left is not None and right is not None:
        return left == right
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip().casefold() == expected.strip().casefold()
    return actual == expected


def _collection(value: Any) -> list[Any]:
    if value is MISSING or value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _predicate(node: dict[str, Any], context: dict[str, Any]) -> tuple[bool, TraceItem, str | None]:
    path = str(node.get("path") or "").strip()
    operator = str(node.get("op") or "eq").strip().lower()
    expected = node.get("value")
    if not path:
        raise ValueError("predicate path is required")
    if operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"unsupported effectivity operator: {operator}")

    actual = _lookup(context, path)
    missing = actual is MISSING
    unresolved = path if missing and operator != "exists" else None

    if operator == "exists":
        expected_flag = bool(True if expected is None else expected)
        matched = (not missing and actual is not None) is expected_flag
    elif missing:
        matched = False
    elif operator == "eq":
        matched = _same(actual, expected)
    elif operator == "ne":
        matched = not _same(actual, expected)
    elif operator in {"in", "not_in"}:
        matched = any(_same(actual, item) for item in _collection(expected))
        if operator == "not_in":
            matched = not matched
    elif operator in {"gt", "gte", "lt", "lte"}:
        left = _decimal(actual)
        right = _decimal(expected)
        if left is None or right is None:
            matched = False
        elif operator == "gt":
            matched = left > right
        elif operator == "gte":
            matched = left >= right
        elif operator == "lt":
            matched = left < right
        else:
            matched = left <= right
    elif operator == "between":
        values = _collection(expected)
        if len(values) != 2:
            raise ValueError("between requires exactly two values")
        actual_num = _decimal(actual)
        lower = _decimal(values[0])
        upper = _decimal(values[1])
        matched = (
            actual_num is not None
            and lower is not None
            and upper is not None
            and lower <= actual_num <= upper
        )
    elif operator == "contains":
        matched = any(_same(item, expected) for item in _collection(actual))
    else:  # pragma: no cover
        matched = False

    label = str(node.get("label") or path)
    if missing:
        reason = f"{label}: value is not available"
    elif matched:
        reason = str(node.get("pass_reason") or f"{label} matched {operator} {expected!r}")
    else:
        reason = str(
            node.get("fail_reason")
            or f"{label} did not match {operator} {expected!r}; actual={actual!r}"
        )
    trace = TraceItem(
        path=path,
        operator=operator,
        expected=expected,
        actual=None if missing else actual,
        matched=matched,
        reason=reason,
    )
    return matched, trace, unresolved


def _evaluate(
    node: dict[str, Any], context: dict[str, Any]
) -> tuple[bool, list[TraceItem], list[str], list[str]]:
    if not isinstance(node, dict):
        raise ValueError("effectivity expression nodes must be objects")
    if "path" in node:
        matched, trace, unresolved = _predicate(node, context)
        return (
            matched,
            [trace],
            [trace.reason] if matched else [],
            [unresolved] if unresolved else [],
        )

    operator = str(node.get("operator") or "ALL").upper()
    children = node.get("conditions")
    if operator not in {"ALL", "ANY", "NOT"}:
        raise ValueError(f"unsupported effectivity group operator: {operator}")
    if not isinstance(children, list) or not children:
        raise ValueError(f"{operator} requires a non-empty conditions list")
    if operator == "NOT" and len(children) != 1:
        raise ValueError("NOT requires exactly one condition")

    results: list[bool] = []
    trace: list[TraceItem] = []
    reasons: list[str] = []
    unresolved: list[str] = []
    for child in children:
        child_result, child_trace, child_reasons, child_unresolved = _evaluate(child, context)
        results.append(child_result)
        trace.extend(child_trace)
        reasons.extend(child_reasons)
        unresolved.extend(child_unresolved)

    if operator == "ALL":
        matched = all(results)
    elif operator == "ANY":
        matched = any(results)
    else:
        matched = not results[0]
        reasons = [str(node.get("pass_reason") or "Excluded condition is not present")] if matched else []

    if matched and node.get("pass_reason"):
        reasons.append(str(node["pass_reason"]))
    return matched, trace, reasons, unresolved


def evaluate_expression(expression: dict[str, Any], context: dict[str, Any]) -> EvaluationResult:
    matched, trace, reasons, unresolved = _evaluate(expression, context)
    return EvaluationResult(
        applicable=matched,
        reasons=tuple(dict.fromkeys(reasons)),
        trace=tuple(trace),
        unresolved_paths=tuple(dict.fromkeys(unresolved)),
    )


def impact_analysis(
    previous_expression: dict[str, Any],
    proposed_expression: dict[str, Any],
    contexts: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for context in contexts:
        previous = evaluate_expression(previous_expression, context)
        proposed = evaluate_expression(proposed_expression, context)
        if previous.applicable != proposed.applicable:
            changes.append(
                {
                    "context_key": context.get("aircraft_serial_number")
                    or context.get("registration")
                    or context.get("id"),
                    "previous_applicable": previous.applicable,
                    "proposed_applicable": proposed.applicable,
                    "previous_reasons": list(previous.reasons),
                    "proposed_reasons": list(proposed.reasons),
                }
            )
    return changes
