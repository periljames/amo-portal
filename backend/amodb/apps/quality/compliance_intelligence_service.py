from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable


EVIDENCE_CONTEXTS = {
    "GENERAL",
    "CAPABILITY_SCOPE",
    "PERSONNEL_AUTHORIZATION",
    "CONTRACT_SCOPE",
    "TECHNICAL_DATA",
    "RECORD_RETENTION",
    "TOOLING_CALIBRATION",
    "FACILITY",
}

EVIDENCE_ROLES = {
    "APPROVAL_CERTIFICATE",
    "SOP",
    "CAPABILITY_LIST",
    "CONTRACT_SCOPE",
    "CONTROLLED_MANUAL",
    "QWI",
    "FORM_RECORD",
    "OTHER",
}

# This is deliberately context-specific. It is not a universal legal hierarchy.
_CONTEXT_PRECEDENCE: dict[str, dict[str, int]] = {
    "CAPABILITY_SCOPE": {
        "APPROVAL_CERTIFICATE": 100,
        "SOP": 95,
        "CAPABILITY_LIST": 90,
        "CONTRACT_SCOPE": 80,
        "CONTROLLED_MANUAL": 45,
        "QWI": 35,
        "FORM_RECORD": 20,
        "OTHER": 10,
    },
    "CONTRACT_SCOPE": {
        "CONTRACT_SCOPE": 100,
        "APPROVAL_CERTIFICATE": 90,
        "SOP": 80,
        "CONTROLLED_MANUAL": 45,
        "QWI": 35,
        "OTHER": 10,
    },
    "PERSONNEL_AUTHORIZATION": {
        "APPROVAL_CERTIFICATE": 90,
        "SOP": 80,
        "CONTROLLED_MANUAL": 50,
        "FORM_RECORD": 45,
        "QWI": 35,
        "OTHER": 10,
    },
    "TECHNICAL_DATA": {
        "CONTROLLED_MANUAL": 90,
        "QWI": 80,
        "FORM_RECORD": 40,
        "OTHER": 10,
    },
    "RECORD_RETENTION": {
        "APPROVAL_CERTIFICATE": 80,
        "SOP": 75,
        "CONTROLLED_MANUAL": 70,
        "QWI": 60,
        "FORM_RECORD": 40,
        "OTHER": 10,
    },
    "TOOLING_CALIBRATION": {
        "APPROVAL_CERTIFICATE": 85,
        "SOP": 80,
        "CONTROLLED_MANUAL": 70,
        "QWI": 65,
        "FORM_RECORD": 50,
        "OTHER": 10,
    },
    "FACILITY": {
        "APPROVAL_CERTIFICATE": 100,
        "SOP": 90,
        "CAPABILITY_LIST": 80,
        "CONTROLLED_MANUAL": 45,
        "QWI": 35,
        "OTHER": 10,
    },
}


def normalise_evidence_context(value: str | None) -> str:
    candidate = str(value or "GENERAL").strip().upper()
    return candidate if candidate in EVIDENCE_CONTEXTS else "GENERAL"


def normalise_evidence_role(value: Any) -> str | None:
    candidate = str(value or "").strip().upper()
    return candidate if candidate in EVIDENCE_ROLES else None


def evidence_priority(context: str | None, role: str | None) -> int | None:
    resolved_context = normalise_evidence_context(context)
    resolved_role = normalise_evidence_role(role)
    if resolved_role is None:
        return None
    policy = _CONTEXT_PRECEDENCE.get(resolved_context)
    if not policy:
        return None
    return policy.get(resolved_role)


def precedence_policy(context: str | None) -> dict[str, int]:
    return dict(_CONTEXT_PRECEDENCE.get(normalise_evidence_context(context), {}))


def _active_rule(rule: dict[str, Any], as_of: date) -> bool:
    if str(rule.get("status") or "ACTIVE").upper() != "ACTIVE":
        return False
    effective_from = rule.get("effective_from")
    effective_to = rule.get("effective_to")
    if effective_from and effective_from > as_of:
        return False
    if effective_to and effective_to < as_of:
        return False
    return True


def _same_text(left: Any, right: Any) -> bool:
    return re.sub(r"\s+", " ", str(left or "").strip()).casefold() == re.sub(r"\s+", " ", str(right or "").strip()).casefold()


def _rule_matches_fact(rule: dict[str, Any], fact: dict[str, Any]) -> bool:
    if not _same_text(rule.get("target_type"), fact.get("target_type")):
        return False
    rule_id = str(rule.get("target_id") or "").strip()
    fact_id = str(fact.get("target_id") or "").strip()
    if rule_id:
        return bool(fact_id and rule_id == fact_id)
    rule_value = str(rule.get("target_value") or "").strip()
    fact_value = str(fact.get("target_value") or "").strip()
    return bool(rule_value and fact_value and _same_text(rule_value, fact_value))


def evaluate_applicability(
    rules: Iterable[dict[str, Any]],
    facts: Iterable[dict[str, Any]],
    *,
    as_of: date,
) -> dict[str, Any]:
    active = [dict(rule) for rule in rules if _active_rule(rule, as_of)]
    selected_facts = [dict(fact) for fact in facts]

    if not active:
        return {
            "status": "UNVERIFIED",
            "reason": "No active governed applicability rule is attached to this controlled document.",
            "basis": [],
            "missing_context": [],
            "warnings": [],
        }

    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for rule in active:
        for fact in selected_facts:
            if _rule_matches_fact(rule, fact):
                matched.append((rule, fact))

    exclusions = [(rule, fact) for rule, fact in matched if str(rule.get("rule_type") or "").upper() == "EXCLUDE"]
    if exclusions:
        return {
            "status": "NOT_APPLICABLE",
            "reason": "A governed exclusion rule matches the audit applicability context.",
            "basis": [
                {
                    "rule_id": rule.get("id"),
                    "rule_type": "EXCLUDE",
                    "target_type": rule.get("target_type"),
                    "target_id": rule.get("target_id"),
                    "target_value": rule.get("target_value"),
                    "fact_id": fact.get("id"),
                }
                for rule, fact in exclusions
            ],
            "missing_context": [],
            "warnings": [],
        }

    includes = [rule for rule in active if str(rule.get("rule_type") or "").upper() == "INCLUDE"]
    matched_includes = [(rule, fact) for rule, fact in matched if str(rule.get("rule_type") or "").upper() == "INCLUDE"]
    warning_matches = [(rule, fact) for rule, fact in matched if str(rule.get("rule_type") or "").upper() == "WARNING"]
    warnings = [
        {
            "rule_id": rule.get("id"),
            "target_type": rule.get("target_type"),
            "target_id": rule.get("target_id"),
            "target_value": rule.get("target_value"),
            "fact_id": fact.get("id"),
        }
        for rule, fact in warning_matches
    ]

    if matched_includes:
        return {
            "status": "APPLICABLE",
            "reason": "A governed inclusion rule matches the audit applicability context.",
            "basis": [
                {
                    "rule_id": rule.get("id"),
                    "rule_type": "INCLUDE",
                    "target_type": rule.get("target_type"),
                    "target_id": rule.get("target_id"),
                    "target_value": rule.get("target_value"),
                    "fact_id": fact.get("id"),
                }
                for rule, fact in matched_includes
            ],
            "missing_context": [],
            "warnings": warnings,
        }

    if includes:
        required_types = {str(rule.get("target_type") or "").upper() for rule in includes if rule.get("target_type")}
        provided_types = {str(fact.get("target_type") or "").upper() for fact in selected_facts if fact.get("target_type")}
        missing_types = sorted(required_types - provided_types)
        if missing_types:
            return {
                "status": "UNVERIFIED",
                "reason": "The document has governed inclusion rules, but the audit context is missing required target types.",
                "basis": [],
                "missing_context": missing_types,
                "warnings": warnings,
            }
        return {
            "status": "NOT_APPLICABLE",
            "reason": "The audit context is populated for the governed target type, but no inclusion rule matches it.",
            "basis": [
                {
                    "rule_id": rule.get("id"),
                    "rule_type": "INCLUDE",
                    "target_type": rule.get("target_type"),
                    "target_id": rule.get("target_id"),
                    "target_value": rule.get("target_value"),
                }
                for rule in includes
            ],
            "missing_context": [],
            "warnings": warnings,
        }

    return {
        "status": "APPLICABLE",
        "reason": "No governed inclusion or exclusion rule restricts this document for the selected audit context.",
        "basis": [],
        "missing_context": [],
        "warnings": warnings,
    }


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "from", "after", "before",
    "shall", "must", "may", "should", "be", "is", "are", "was", "were", "at", "in",
    "on", "by", "with", "this", "that", "these", "those", "record", "records",
}
_DURATION = re.compile(r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>day|days|month|months|year|years)\b", re.IGNORECASE)
_RETENTION = re.compile(r"\b(retain|retention|retained|keep|kept|preserve|preserved|maintain|maintained)\b", re.IGNORECASE)
_NEGATIVE = re.compile(r"\b(shall\s+not|must\s+not|may\s+not|is\s+prohibited|are\s+prohibited|not\s+permitted)\b", re.IGNORECASE)
_POSITIVE = re.compile(r"\b(shall|must|required\s+to|is\s+required|are\s+required|permitted\s+to|may)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Constraint:
    evidence_id: str
    reference: str
    clause: str
    kind: str
    value: float | None
    unit: str | None
    polarity: str | None
    tokens: frozenset[str]


def _tokens(value: str) -> frozenset[str]:
    words = re.findall(r"[a-z][a-z0-9_-]{2,}", value.casefold())
    return frozenset(word for word in words if word not in _STOPWORDS and not word.isdigit())


def _duration_days(value: float, unit: str) -> float:
    unit = unit.casefold()
    if unit.startswith("year"):
        return value * 365.0
    if unit.startswith("month"):
        return value * 30.0
    return value


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.;!?])\s+|\n+", text or "") if part.strip()]


def _constraints(candidate: dict[str, Any]) -> list[Constraint]:
    evidence_id = str(candidate.get("evidence_id") or candidate.get("id") or "")
    reference = str(candidate.get("reference") or candidate.get("heading") or candidate.get("document_code") or evidence_id)
    result: list[Constraint] = []
    for clause in _clauses(str(candidate.get("source_text") or candidate.get("snippet") or "")):
        duration = _DURATION.search(clause)
        if duration and _RETENTION.search(clause):
            value = float(duration.group("value"))
            unit = duration.group("unit")
            result.append(Constraint(
                evidence_id=evidence_id,
                reference=reference,
                clause=clause[:1000],
                kind="RETENTION_DURATION",
                value=_duration_days(value, unit),
                unit="DAYS",
                polarity=None,
                tokens=_tokens(clause),
            ))
        negative = _NEGATIVE.search(clause)
        positive = _POSITIVE.search(clause)
        if negative or positive:
            result.append(Constraint(
                evidence_id=evidence_id,
                reference=reference,
                clause=clause[:1000],
                kind="MODAL_POLARITY",
                value=None,
                unit=None,
                polarity="NEGATIVE" if negative else "POSITIVE",
                tokens=_tokens(clause),
            ))
    return result


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / max(1, len(union))


def detect_requirement_conflicts(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    constraints = [constraint for candidate in candidates for constraint in _constraints(dict(candidate))]
    conflicts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, left in enumerate(constraints):
        for right in constraints[index + 1 :]:
            if left.evidence_id == right.evidence_id or left.kind != right.kind:
                continue
            similarity = _overlap(left.tokens, right.tokens)
            if similarity < 0.35 or len(left.tokens & right.tokens) < 2:
                continue

            detector: str | None = None
            if left.kind == "RETENTION_DURATION" and left.value is not None and right.value is not None:
                # Treat equivalent calendar expressions such as 2 years vs
                # 24 months as the same retention period. The tolerance is
                # bounded so materially different periods still surface.
                if not math.isclose(left.value, right.value, rel_tol=0.0, abs_tol=15.0):
                    detector = "RETENTION_DURATION"
            elif left.kind == "MODAL_POLARITY" and left.polarity != right.polarity:
                detector = "MODAL_POLARITY"
            if detector is None:
                continue

            key = tuple(sorted((left.evidence_id, right.evidence_id))) + (detector,)
            if key in seen:
                continue
            seen.add(key)
            conflicts.append({
                "type": "DOCUMENT_CONFLICT",
                "detector": detector,
                "confidence": "HIGH",
                "similarity": round(similarity, 4),
                "sources": [
                    {"evidence_id": left.evidence_id, "reference": left.reference, "clause": left.clause},
                    {"evidence_id": right.evidence_id, "reference": right.reference, "clause": right.clause},
                ],
                "resolution": "AUDITOR_REVIEW_REQUIRED",
            })
    return conflicts
