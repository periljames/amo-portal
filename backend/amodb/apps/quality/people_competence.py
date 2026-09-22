"""QMS People ↔ Training competence package evaluation and auto-suspend.

Default Lead/Auditor rules require all configured courses with AND
(QMS-INIT AND QMS-REF AND QMS-ADMIN). Tenants may set join=OR or an Advanced
expression using the words AND / OR. Legacy packages that only declare
``currency_any_of`` keep OR currency semantics for backward compatibility.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.training.integration import (
    QMS_ADMIN,
    QMS_CURRENCY_CODES,
    QMS_INIT,
    QMS_REF,
    current_training_evidence,
    current_training_evidence_with_alternatives,
    qms_auditor_competence_evidence,
)

from .people_models import QualityPrivilege, QualityPrivilegeDecision, QualityPrivilegeRule

QM_BYPASS_REF_TYPE = "QM_TRAINING_BYPASS"

DEFAULT_QMS_COMPETENCE_PACKAGE: dict[str, Any] = {
    "codes": [QMS_INIT, QMS_REF, QMS_ADMIN],
    "join": "AND",
    "expression": "QMS-INIT AND QMS-REF AND QMS-ADMIN",
    "currency_any_of": list(QMS_CURRENCY_CODES),
    "tracked_admin": QMS_ADMIN,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_codes(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        code = str(value or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _normalize_expression(value: str) -> str:
    text = " ".join(str(value or "").upper().replace("&&", " AND ").replace("||", " OR ").split())
    return text.replace("( ", "(").replace(" )", ")").strip()


def _tokenize_expression(raw: str) -> list[str] | None:
    text = _normalize_expression(raw)
    if not text:
        return []
    tokens: list[str] = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        ch = text[i]
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue
        if text.startswith("AND", i) and (i + 3 >= len(text) or text[i + 3] in " ()"):
            tokens.append("AND")
            i += 3
            continue
        if text.startswith("OR", i) and (i + 2 >= len(text) or text[i + 2] in " ()"):
            tokens.append("OR")
            i += 2
            continue
        start = i
        while i < len(text) and (text[i].isalnum() or text[i] in "._-/"):
            i += 1
        if i == start:
            return None
        tokens.append(text[start:i].strip().upper())
    return tokens


def _parse_expression_tokens(tokens: list[str]) -> dict[str, Any] | None:
    index = 0

    def peek() -> str | None:
        return tokens[index] if index < len(tokens) else None

    def consume(expected: str | None = None) -> str | None:
        nonlocal index
        token = peek()
        if expected is not None and token != expected:
            return None
        if token is None:
            return None
        index += 1
        return token

    def parse_primary() -> dict[str, Any] | None:
        token = peek()
        if token is None:
            return None
        if token == "(":
            consume("(")
            inner = parse_or()
            if inner is None or consume(")") != ")":
                return None
            return inner
        if token in {"AND", "OR", ")"}:
            return None
        consume()
        return {"type": "code", "code": str(token).strip().upper()}

    def parse_and() -> dict[str, Any] | None:
        left = parse_primary()
        if left is None:
            return None
        while peek() == "AND":
            consume("AND")
            right = parse_primary()
            if right is None:
                return None
            left = {"type": "and", "left": left, "right": right}
        return left

    def parse_or() -> dict[str, Any] | None:
        left = parse_and()
        if left is None:
            return None
        while peek() == "OR":
            consume("OR")
            right = parse_and()
            if right is None:
                return None
            left = {"type": "or", "left": left, "right": right}
        return left

    ast = parse_or()
    if ast is None or index != len(tokens):
        return None
    return ast


def _collect_expression_codes(node: dict[str, Any], out: list[str] | None = None) -> list[str]:
    out = out if out is not None else []
    if node.get("type") == "code":
        code = str(node.get("code") or "").strip().upper()
        if code and code not in out:
            out.append(code)
        return out
    _collect_expression_codes(node["left"], out)
    _collect_expression_codes(node["right"], out)
    return out


def _expression_uses_or(node: dict[str, Any]) -> bool:
    kind = node.get("type")
    if kind == "or":
        return True
    if kind == "code":
        return False
    return _expression_uses_or(node["left"]) or _expression_uses_or(node["right"])


def parse_training_expression(value: str) -> dict[str, Any]:
    """Parse ``QMS-INIT AND QMS-REF`` style expressions (words, not symbols)."""

    tokens = _tokenize_expression(value)
    if tokens is None:
        return {"ok": False, "error": "Use course codes with AND / OR (and parentheses if needed)."}
    if not tokens:
        return {"ok": True, "codes": [], "join": "AND", "ast": {"type": "code", "code": ""}}
    ast = _parse_expression_tokens(tokens)
    if ast is None:
        return {"ok": False, "error": "Could not read that rule. Example: QMS-INIT AND QMS-REF AND QMS-ADMIN"}
    codes = _collect_expression_codes(ast)
    return {
        "ok": True,
        "codes": codes,
        "join": "OR" if _expression_uses_or(ast) else "AND",
        "ast": ast,
    }


def evaluate_training_expression(expression: str, satisfied_codes: list[str] | set[str]) -> bool:
    parsed = parse_training_expression(expression)
    if not parsed.get("ok"):
        return False
    codes = list(parsed.get("codes") or [])
    if not codes:
        return True
    satisfied = {str(code).strip().upper() for code in satisfied_codes if str(code).strip()}

    def eval_node(node: dict[str, Any]) -> bool:
        kind = node.get("type")
        if kind == "code":
            code = str(node.get("code") or "").strip().upper()
            return (not code) or code in satisfied
        if kind == "and":
            return eval_node(node["left"]) and eval_node(node["right"])
        return eval_node(node["left"]) or eval_node(node["right"])

    return eval_node(parsed["ast"])


def resolve_rule_competence(rule: QualityPrivilegeRule | None) -> dict[str, Any] | None:
    """Return the QMS competence package from a rule scope_schema, if configured."""

    if rule is None:
        return None
    scope = rule.scope_schema if isinstance(rule.scope_schema, dict) else {}
    package = scope.get("qms_competence")
    if not isinstance(package, dict):
        return None

    expression_raw = str(package.get("expression") or "").strip()
    expression = _normalize_expression(expression_raw) if expression_raw else None
    join_raw = str(package.get("join") or "").strip().upper()
    join = "OR" if join_raw == "OR" else "AND"

    legacy_currency = _normalize_codes(package.get("currency_any_of") or [])
    tracked_admin = str(package.get("tracked_admin") or "").strip().upper() or None
    codes = _normalize_codes(package.get("codes") or [])
    if not codes and expression:
        parsed = parse_training_expression(expression)
        if parsed.get("ok"):
            codes = list(parsed.get("codes") or [])
    if not codes:
        codes = _normalize_codes([*legacy_currency, *([tracked_admin] if tracked_admin else [])])
    if not codes and not expression and not legacy_currency and not tracked_admin:
        return None

    if expression:
        parsed = parse_training_expression(expression)
        if parsed.get("ok"):
            join = str(parsed.get("join") or join)
    elif not package.get("join") and not package.get("codes") and legacy_currency:
        join = "OR"

    return {
        "codes": codes,
        "join": join,
        "expression": expression,
        "currency_any_of": legacy_currency,
        "tracked_admin": tracked_admin,
        "legacy_or_currency": bool(legacy_currency) and not package.get("codes") and not expression,
    }


def evaluate_qms_competence_for_privilege(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    rule: QualityPrivilegeRule,
    as_of: date,
) -> dict[str, Any]:
    """Evaluate training evidence using the rule competence package or legacy AND-list."""

    package = resolve_rule_competence(rule)
    if package:
        codes = list(package.get("codes") or [])
        expression = str(package.get("expression") or "").strip() or None
        join = str(package.get("join") or "AND").upper()
        legacy_or = bool(package.get("legacy_or_currency"))
        track_admin = bool(package.get("tracked_admin"))

        display = qms_auditor_competence_evidence(
            db,
            amo_id=amo_id,
            user_id=user_id,
            as_of=as_of,
            track_admin=track_admin or (QMS_ADMIN in codes),
        )

        if legacy_or:
            currency_codes = package.get("currency_any_of") or list(QMS_CURRENCY_CODES)
            if list(currency_codes) != list(QMS_CURRENCY_CODES):
                alt = current_training_evidence_with_alternatives(
                    db,
                    amo_id=amo_id,
                    user_id=user_id,
                    alternative_groups=[[code] for code in currency_codes],
                    as_of=as_of,
                )
                evidence = {
                    **display,
                    **alt,
                    "passed": bool(alt["passed"]),
                    "currency_passed": bool(alt["passed"]),
                    "currency_lapsed": not bool(alt["passed"]),
                    "suspend_recommended": (not bool(alt["passed"])) or bool(display.get("admin_lapsed")),
                    "package": package,
                    "tracked_records": display.get("tracked_records") or [],
                    "records": display.get("tracked_records") or alt.get("records") or [],
                }
            else:
                evidence = {**display, "package": package}
            evidence["mode"] = "qms_competence_package"
            if "tracked_records" not in evidence:
                evidence["tracked_records"] = list(evidence.get("records") or [])
            return evidence

        and_evidence = current_training_evidence(
            db,
            amo_id=amo_id,
            user_id=user_id,
            required_codes=codes,
            as_of=as_of,
        )
        satisfied = set(and_evidence.get("satisfied") or [])
        if expression:
            # Gather per-code currency so OR branches can pass without AND of every code.
            per_code = current_training_evidence_with_alternatives(
                db,
                amo_id=amo_id,
                user_id=user_id,
                alternative_groups=[[code] for code in codes],
                as_of=as_of,
            )
            satisfied = set(per_code.get("satisfied") or [])
            passed = evaluate_training_expression(expression, satisfied)
            and_evidence = {**and_evidence, **per_code}
        elif join == "OR":
            alt = current_training_evidence_with_alternatives(
                db,
                amo_id=amo_id,
                user_id=user_id,
                alternative_groups=[[code] for code in codes],
                as_of=as_of,
            )
            satisfied = set(alt.get("satisfied") or [])
            passed = bool(alt.get("passed"))
            and_evidence = {**and_evidence, **alt}
        else:
            passed = bool(and_evidence.get("passed"))

        missing = [code for code in codes if code not in satisfied] if not passed else []
        return {
            **display,
            **and_evidence,
            "required": codes,
            "satisfied": sorted(satisfied),
            "missing": missing,
            "passed": passed,
            "currency_passed": passed,
            "currency_lapsed": (not passed) and bool(and_evidence.get("expired")),
            "suspend_recommended": (not passed) or bool(display.get("admin_lapsed")),
            "package": package,
            "mode": "qms_competence_package",
            "tracked_records": display.get("tracked_records") or and_evidence.get("records") or [],
            "records": display.get("tracked_records") or and_evidence.get("records") or [],
        }

    required = list(rule.required_training_course_codes or [])
    legacy = current_training_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required_codes=required,
        as_of=as_of,
    )
    package_evidence = qms_auditor_competence_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        as_of=as_of,
        track_admin=False,
    )
    return {
        **legacy,
        "currency_passed": bool(legacy["passed"]),
        "currency_lapsed": not bool(legacy["passed"]) and bool(required),
        "admin": package_evidence.get("admin") or {"status": "none", "course_code": QMS_ADMIN, "record": None},
        "admin_lapsed": False,
        "expired_records": package_evidence.get("expired_records") or [],
        "tracked_records": package_evidence.get("tracked_records") or legacy.get("records") or [],
        "records": package_evidence.get("tracked_records") or legacy.get("records") or [],
        "track_admin": False,
        "suspend_recommended": not bool(legacy["passed"]) and bool(required),
        "package": None,
        "mode": "required_training_course_codes",
    }


def earliest_competence_valid_until(
    training: dict[str, Any] | None,
    *,
    as_of: date | None = None,
) -> date | None:
    """Soonest course ``valid_until`` among current competence evidence.

    Open-ended courses (null ``valid_until``) do not contribute a cap. When the
    training snapshot lists ``satisfied`` codes, only those records count —
    matching OR-currency packages that pass on a subset of courses.
    """

    if not isinstance(training, dict):
        return None
    day = as_of or date.today()
    satisfied = {
        str(code or "").strip().upper()
        for code in (training.get("satisfied") or [])
        if str(code or "").strip()
    }
    rows: list[Any] = []
    for key in ("records", "tracked_records"):
        value = training.get(key)
        if isinstance(value, list):
            rows.extend(value)

    earliest: date | None = None
    seen_codes: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("course_code") or "").strip().upper()
        if satisfied and code and code not in satisfied:
            continue
        until = _parse_date(row.get("valid_until"))
        if until is None or until < day:
            continue
        dedupe_key = code or str(row.get("record_id") or "")
        if dedupe_key and dedupe_key in seen_codes:
            continue
        if dedupe_key:
            seen_codes.add(dedupe_key)
        if earliest is None or until < earliest:
            earliest = until
    return earliest


def cap_privilege_expires_on(
    requested: date | None,
    training: dict[str, Any] | None,
    *,
    as_of: date | None = None,
) -> date | None:
    """Force authorization expiry onto (or before) the governing course expiry.

    When competence evidence has a course ``valid_until``, the privilege cannot
    outlive that calendar day. A shorter requested expiry is preserved.
    """

    course_cap = earliest_competence_valid_until(training, as_of=as_of)
    if course_cap is None:
        return requested
    if requested is None:
        return course_cap
    return min(requested, course_cap)


def active_qm_bypass(privilege: QualityPrivilege | None, *, as_of: date | None = None) -> dict[str, Any] | None:
    """Return the active time-bounded QM training bypass, if any."""

    if privilege is None:
        return None
    as_of = as_of or date.today()

    scope = privilege.scope if isinstance(privilege.scope, dict) else {}
    controlled = scope.get("controlled_exemption")
    if isinstance(controlled, dict):
        effective_from = _parse_date(controlled.get("effective_from"))
        valid_until = _parse_date(controlled.get("expires_on"))
        if (
            valid_until
            and valid_until >= as_of
            and (effective_from is None or effective_from <= as_of)
            and str(controlled.get("criterion") or "").strip()
        ):
            return {
                "rationale": "Controlled exemption / conditional authorization",
                "valid_until": valid_until.isoformat(),
                "approved_by_user_id": controlled.get("approved_by_user_id"),
                "approved_at": controlled.get("approved_at"),
                "criterion": controlled.get("criterion"),
                "conditions": list(controlled.get("conditions") or []),
                "limitations": list(controlled.get("limitations") or []),
                "supervision_required": bool(controlled.get("supervision_required")),
                "supervisor_user_id": controlled.get("supervisor_user_id"),
                "source": "controlled_exemption",
            }

    scoped = scope.get("qm_training_bypass")
    if isinstance(scoped, dict):
        valid_until = _parse_date(scoped.get("valid_until"))
        if valid_until and valid_until >= as_of and str(scoped.get("rationale") or "").strip():
            return {
                "rationale": str(scoped.get("rationale") or "").strip(),
                "valid_until": valid_until.isoformat(),
                "approved_by_user_id": scoped.get("approved_by_user_id"),
                "approved_at": scoped.get("approved_at"),
                "source": "privilege_scope",
            }

    decisions = list(getattr(privilege, "decisions", None) or [])
    for decision in reversed(decisions):
        refs = decision.source_references if isinstance(decision.source_references, list) else []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("type") or "").strip().upper() != QM_BYPASS_REF_TYPE:
                continue
            valid_until = _parse_date(ref.get("valid_until") or decision.expires_on)
            if valid_until and valid_until >= as_of:
                return {
                    "rationale": str(ref.get("rationale") or decision.rationale or "").strip(),
                    "valid_until": valid_until.isoformat(),
                    "approved_by_user_id": ref.get("approved_by_user_id") or decision.decided_by_user_id,
                    "approved_at": ref.get("approved_at") or (decision.decided_at.isoformat() if decision.decided_at else None),
                    "decision_id": str(decision.id),
                    "source": "decision_source_references",
                }
        snap = decision.eligibility_snapshot if isinstance(decision.eligibility_snapshot, dict) else {}
        bypass = snap.get("qm_training_bypass")
        if isinstance(bypass, dict):
            valid_until = _parse_date(bypass.get("valid_until"))
            if valid_until and valid_until >= as_of:
                return {
                    "rationale": str(bypass.get("rationale") or decision.rationale or "").strip(),
                    "valid_until": valid_until.isoformat(),
                    "approved_by_user_id": bypass.get("approved_by_user_id") or decision.decided_by_user_id,
                    "approved_at": bypass.get("approved_at") or (decision.decided_at.isoformat() if decision.decided_at else None),
                    "decision_id": str(decision.id),
                    "source": "decision_eligibility_snapshot",
                }
    return None


def apply_auto_suspend_if_currency_lapsed(
    db: Session,
    *,
    amo_id: str,
    privilege: QualityPrivilege,
    rule: QualityPrivilegeRule,
    competence: dict[str, Any],
    as_of: date,
    actor_user_id: str | None = None,
) -> QualityPrivilegeDecision | None:
    """Idempotently SUSPEND an ACTIVE privilege when required QMS currency has lapsed.

    Does nothing when a time-bounded QM bypass is active, when the privilege is
    not ACTIVE, or when competence does not recommend suspension.
    """

    if privilege is None or str(privilege.status or "").upper() != "ACTIVE":
        return None
    if active_qm_bypass(privilege, as_of=as_of):
        return None
    if not competence.get("suspend_recommended"):
        return None

    expired_codes: list[str] = []
    for item in (competence.get("expired_records") or competence.get("expired") or []):
        if isinstance(item, dict):
            code = str(item.get("course_code") or "").strip().upper()
        else:
            code = str(item or "").strip().upper()
        if code:
            expired_codes.append(code)
    if competence.get("admin_lapsed") and QMS_ADMIN not in expired_codes:
        expired_codes.append(QMS_ADMIN)
    # Do not treat never-trained "missing" as an auto-suspend trigger.
    if not expired_codes:
        return None

    cited = ", ".join(dict.fromkeys(expired_codes))
    rationale = (
        f"Automatic suspension: required QMS competence currency lapsed ({cited}). "
        f"Rule {rule.privilege_code}."
    )

    # Idempotency: skip if the latest decision is already an auto-currency SUSPEND.
    latest = (
        db.query(QualityPrivilegeDecision)
        .filter(
            QualityPrivilegeDecision.amo_id == amo_id,
            QualityPrivilegeDecision.privilege_id == privilege.id,
        )
        .order_by(QualityPrivilegeDecision.created_at.desc(), QualityPrivilegeDecision.id.desc())
        .first()
    )
    if latest is not None and latest.decision_type == "SUSPEND" and latest.resulting_status == "SUSPENDED":
        refs = latest.source_references if isinstance(latest.source_references, list) else []
        if any(isinstance(ref, dict) and str(ref.get("type") or "").upper() == "AUTO_CURRENCY_LAPSE" for ref in refs):
            if str(privilege.status).upper() != "SUSPENDED":
                privilege.status = "SUSPENDED"
                privilege.updated_at = _utcnow()
            return None

    decision = QualityPrivilegeDecision(
        amo_id=amo_id,
        privilege_id=privilege.id,
        decision_type="SUSPEND",
        resulting_status="SUSPENDED",
        rationale=rationale,
        eligibility_snapshot={
            "auto_suspend": True,
            "competence": competence,
            "as_of": as_of.isoformat(),
        },
        source_references=[
            {
                "type": "AUTO_CURRENCY_LAPSE",
                "expired_course_codes": expired_codes,
                "rule_id": str(rule.id),
                "privilege_code": rule.privilege_code,
            }
        ],
        effective_from=privilege.effective_from,
        expires_on=privilege.expires_on,
        decided_by_user_id=actor_user_id,
        decided_at=_utcnow(),
    )
    db.add(decision)
    db.flush()
    privilege.status = "SUSPENDED"
    privilege.latest_decision_id = decision.id
    privilege.updated_by_user_id = actor_user_id
    privilege.updated_at = _utcnow()
    return decision


def record_qm_training_bypass(
    db: Session,
    *,
    amo_id: str,
    privilege: QualityPrivilege,
    rationale: str,
    valid_until: date,
    actor_user_id: str,
) -> QualityPrivilegeDecision:
    """Record a time-bounded QM bypass of the training/expiry gate (never permanent).

    Requires an ACTIVE privilege. Writes privilege.scope and an append-only RENEW
    decision that keeps ACTIVE without altering authorization dates.
    """

    if str(privilege.status or "").upper() != "ACTIVE":
        raise ValueError("QM training bypass can only be granted on an ACTIVE authorization.")
    if valid_until < date.today():
        raise ValueError("QM bypass valid_until must be today or a future date.")
    text = rationale.strip()
    if len(text) < 8:
        raise ValueError("QM bypass rationale must be at least 8 characters.")

    bypass_payload = {
        "type": QM_BYPASS_REF_TYPE,
        "rationale": text,
        "valid_until": valid_until.isoformat(),
        "approved_by_user_id": actor_user_id,
        "approved_at": _utcnow().isoformat(),
        "gate": "training_current_verified",
    }
    scope = dict(privilege.scope or {})
    scope["qm_training_bypass"] = {
        "rationale": text,
        "valid_until": valid_until.isoformat(),
        "approved_by_user_id": actor_user_id,
        "approved_at": bypass_payload["approved_at"],
    }
    privilege.scope = scope

    decision = QualityPrivilegeDecision(
        amo_id=amo_id,
        privilege_id=privilege.id,
        decision_type="RENEW",
        resulting_status="ACTIVE",
        rationale=f"[QM training bypass until {valid_until.isoformat()}] {text}",
        eligibility_snapshot={"qm_training_bypass": bypass_payload, "gate": "training_current_verified"},
        source_references=[bypass_payload],
        effective_from=privilege.effective_from,
        expires_on=privilege.expires_on,
        decided_by_user_id=actor_user_id,
        decided_at=_utcnow(),
    )
    db.add(decision)
    db.flush()
    privilege.latest_decision_id = decision.id
    privilege.updated_by_user_id = actor_user_id
    privilege.updated_at = _utcnow()
    return decision


def select_best_qms_certificate_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer QMS-REF, then QMS-INIT, then QMS-ADMIN among available certificate rows."""

    preference = (QMS_REF, QMS_INIT, QMS_ADMIN)
    by_code = {str(row.get("course_code") or "").upper(): row for row in records}
    for code in preference:
        if code in by_code:
            return by_code[code]
    return records[0] if records else None


def rule_training_match_spec(rule: QualityPrivilegeRule | None) -> dict[str, Any]:
    """Derive the authorize-form training filter from the rule configuration only.

    - Competence package with join AND (default) → match when every listed course
      has a record or scheduled enrollment (AND semantics).
    - Competence package with join OR / legacy currency_any_of → any listed course (OR).
    - Legacy ``required_training_course_codes`` → AND semantics.
    - Empty / unsupervised developmental rules → no training filter.
    """

    if rule is None:
        return {"mode": "none", "codes": []}
    package = resolve_rule_competence(rule)
    if package:
        codes = list(package.get("codes") or [])
        if not codes:
            return {"mode": "none", "codes": []}
        join = str(package.get("join") or "AND").upper()
        if package.get("legacy_or_currency") or join == "OR":
            return {"mode": "any_of", "codes": codes}
        return {"mode": "all_of", "codes": codes}
    required = sorted({
        str(code).strip().upper()
        for code in (rule.required_training_course_codes or [])
        if str(code).strip()
    })
    if required:
        return {"mode": "all_of", "codes": required}
    return {"mode": "none", "codes": []}


def _normalize_course_token(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _resolve_rule_course_ids(db: Session, *, amo_id: str, codes: list[str]) -> dict[str, str]:
    """Map rule short course codes → TrainingCourse primary keys for this tenant.

    Matches exact course_id first, then compact alphanumeric tokens so
    ``QMS-INIT`` still resolves when Training stores ``QMS INIT``.
    """

    from amodb.apps.training import models as training_models

    wanted = [str(code).strip().upper() for code in codes if str(code).strip()]
    if not wanted:
        return {}
    rows = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.is_active.is_(True),
        )
        .all()
    )
    by_exact: dict[str, str] = {}
    by_token: dict[str, str] = {}
    for row in rows:
        course_code = str(row.course_id or "").strip().upper()
        if not course_code:
            continue
        pk = str(row.id)
        by_exact[course_code] = pk
        token = _normalize_course_token(course_code)
        if token and token not in by_token:
            by_token[token] = pk
    resolved: dict[str, str] = {}
    for code in wanted:
        pk = by_exact.get(code) or by_token.get(_normalize_course_token(code))
        if pk:
            resolved[code] = pk
    return resolved


def _user_ids_with_training_records(
    db: Session,
    *,
    amo_id: str,
    course_pks: list[str],
) -> tuple[dict[str, set[str]], dict[str, date | None]]:
    """user_id → course PKs with an active record, plus best valid_until per user."""

    from amodb.apps.training import models as training_models
    from amodb.apps.training.record_lifecycle import active_records_filter

    if not course_pks:
        return {}, {}
    rows = (
        db.query(
            training_models.TrainingRecord.user_id,
            training_models.TrainingRecord.course_id,
            training_models.TrainingRecord.valid_until,
        )
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.course_id.in_(course_pks),
            active_records_filter(training_models.TrainingRecord),
        )
        .all()
    )
    out: dict[str, set[str]] = {}
    valid_until_by_user: dict[str, date | None] = {}
    for user_id, course_pk, valid_until in rows:
        if not user_id or not course_pk:
            continue
        uid = str(user_id)
        out.setdefault(uid, set()).add(str(course_pk))
        if valid_until is None:
            continue
        current = valid_until_by_user.get(uid)
        # Prefer the soonest future/past expiry among matched courses (most urgent).
        if current is None or valid_until < current:
            valid_until_by_user[uid] = valid_until
    return out, valid_until_by_user


def _user_ids_with_scheduled_training(
    db: Session,
    *,
    amo_id: str,
    course_pks: list[str],
) -> dict[str, set[str]]:
    """user_id → set of course PKs with a planned/in-progress scheduled enrollment."""

    from amodb.apps.training import models as training_models

    if not course_pks:
        return {}
    rows = (
        db.query(
            training_models.TrainingEventParticipant.user_id,
            training_models.TrainingEvent.course_id,
        )
        .join(
            training_models.TrainingEvent,
            training_models.TrainingEvent.id == training_models.TrainingEventParticipant.event_id,
        )
        .filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEvent.amo_id == amo_id,
            training_models.TrainingEvent.course_id.in_(course_pks),
            training_models.TrainingEvent.status.in_([
                training_models.TrainingEventStatus.PLANNED,
                training_models.TrainingEventStatus.IN_PROGRESS,
            ]),
            training_models.TrainingEventParticipant.status.in_([
                training_models.TrainingParticipantStatus.SCHEDULED,
                training_models.TrainingParticipantStatus.INVITED,
                training_models.TrainingParticipantStatus.CONFIRMED,
            ]),
        )
        .distinct()
        .all()
    )
    out: dict[str, set[str]] = {}
    for user_id, course_pk in rows:
        if not user_id or not course_pk:
            continue
        out.setdefault(str(user_id), set()).add(str(course_pk))
    return out


def user_ids_matching_rule_training(
    db: Session,
    *,
    amo_id: str,
    rule: QualityPrivilegeRule,
) -> dict[str, Any]:
    """Return active-user ids that satisfy the rule's configured training filter.

    Match sources (relational to rule course codes only):
    - Training records on file (current or overdue — any active lifecycle record)
    - Scheduled / invited / confirmed enrollment on a planned event
    """

    spec = rule_training_match_spec(rule)
    mode = str(spec.get("mode") or "none")
    codes = list(spec.get("codes") or [])
    if mode == "none" or not codes:
        return {
            "mode": "none",
            "codes": [],
            "course_ids": {},
            "user_ids": None,  # None = unrestricted
            "match_by_user": {},
        }

    code_to_pk = _resolve_rule_course_ids(db, amo_id=amo_id, codes=codes)
    course_pks = list(dict.fromkeys(code_to_pk.values()))
    if not course_pks:
        # Rule names courses that are not provisioned in Training yet — no candidates.
        return {
            "mode": mode,
            "codes": codes,
            "course_ids": code_to_pk,
            "user_ids": set(),
            "match_by_user": {},
        }

    pk_to_code = {pk: code for code, pk in code_to_pk.items()}
    records, valid_until_by_user = _user_ids_with_training_records(db, amo_id=amo_id, course_pks=course_pks)
    scheduled = _user_ids_with_scheduled_training(db, amo_id=amo_id, course_pks=course_pks)

    required_pks = [code_to_pk[code] for code in codes if code in code_to_pk]
    match_by_user: dict[str, dict[str, Any]] = {}
    for user_id in set(records) | set(scheduled):
        record_pks = records.get(user_id, set())
        scheduled_pks = scheduled.get(user_id, set())
        covered = record_pks | scheduled_pks
        if mode == "all_of":
            if not required_pks or not all(pk in covered for pk in required_pks):
                continue
        else:  # any_of
            if not covered.intersection(required_pks):
                continue
        reasons: list[str] = []
        if record_pks.intersection(required_pks):
            reasons.append("RECORD")
        if scheduled_pks.intersection(required_pks):
            reasons.append("SCHEDULED")
        valid_until = valid_until_by_user.get(user_id)
        match_by_user[user_id] = {
            "reasons": reasons,
            "course_codes": sorted({pk_to_code[pk] for pk in covered if pk in pk_to_code}),
            "valid_until": valid_until.isoformat() if valid_until else None,
        }

    return {
        "mode": mode,
        "codes": codes,
        "course_ids": code_to_pk,
        "user_ids": set(match_by_user),
        "match_by_user": match_by_user,
    }
