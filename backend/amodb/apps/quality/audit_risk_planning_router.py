from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .assurance_metrics_router import _full_metrics
from .assurance_wiring_router import _safe_identifier, _table_columns
from .audit_programme_models import QualityAuditProgrammeItem, QualityAuditUniverseItem
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(tags=["Quality risk-based audit planning"])

_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _factor(code: str, label: str, value: Any, *, source: str, rationale: str, hard: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "value": value,
        "source": source,
        "hard_requirement": hard,
        "rationale": rationale,
    }


def _reliability_context(db: Session, ctx: TenantContext) -> tuple[dict[str, int], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    values = {
        "high_critical_events_90d": 0,
        "repeat_events_90d": 0,
        "recurring_findings": 0,
        "open_high_recommendations": 0,
    }

    event_columns = _table_columns(db, "reliability_events")
    if event_columns:
        where = ["amo_id = :amo_id"] if "amo_id" in event_columns else []
        params: dict[str, Any] = {"amo_id": ctx.amo_id, "since": _utcnow() - timedelta(days=90)}
        if "occurred_at" in event_columns:
            where.append("occurred_at >= :since")
        if "severity" in event_columns:
            values["high_critical_events_90d"] = int(db.execute(text(
                f"SELECT COUNT(*) FROM reliability_events WHERE {' AND '.join([*where, 'UPPER(CAST(severity AS TEXT)) IN (\'HIGH\',\'CRITICAL\')'])}"
            ), params).scalar() or 0)
        if "repeat_key" in event_columns:
            values["repeat_events_90d"] = int(db.execute(text(
                f"SELECT COALESCE(SUM(n - 1),0) FROM (SELECT repeat_key, COUNT(*) n FROM reliability_events WHERE {' AND '.join([*where, 'repeat_key IS NOT NULL'])} GROUP BY repeat_key HAVING COUNT(*) > 1) q"
            ), params).scalar() or 0)
    else:
        warnings.append({"source": "reliability_events", "type": "SourceUnavailable", "message": "Reliability event ledger is unavailable."})

    recurring_columns = _table_columns(db, "reliability_recurring_findings")
    if recurring_columns:
        conditions = ["amo_id = :amo_id"] if "amo_id" in recurring_columns else []
        if "occurrence_count" in recurring_columns:
            conditions.append("occurrence_count > 1")
        values["recurring_findings"] = int(db.execute(text(
            f"SELECT COUNT(*) FROM {_safe_identifier('reliability_recurring_findings')}" + (" WHERE " + " AND ".join(conditions) if conditions else "")
        ), {"amo_id": ctx.amo_id}).scalar() or 0)
    else:
        warnings.append({"source": "reliability_recurring_findings", "type": "SourceUnavailable", "message": "Reliability recurring-finding ledger is unavailable."})

    recommendation_columns = _table_columns(db, "reliability_recommendations")
    if recommendation_columns:
        conditions = ["amo_id = :amo_id"] if "amo_id" in recommendation_columns else []
        if "status" in recommendation_columns:
            conditions.append("UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED','CANCELLED')")
        if "priority" in recommendation_columns:
            conditions.append("UPPER(CAST(priority AS TEXT)) = 'HIGH'")
        values["open_high_recommendations"] = int(db.execute(text(
            f"SELECT COUNT(*) FROM {_safe_identifier('reliability_recommendations')}" + (" WHERE " + " AND ".join(conditions) if conditions else "")
        ), {"amo_id": ctx.amo_id}).scalar() or 0)
    else:
        warnings.append({"source": "reliability_recommendations", "type": "SourceUnavailable", "message": "Reliability recommendation ledger is unavailable."})

    return values, warnings


def _programme_states(db: Session, amo_id: str) -> dict[str, list[str]]:
    rows = db.query(QualityAuditProgrammeItem.universe_item_id, QualityAuditProgrammeItem.state).filter(
        QualityAuditProgrammeItem.amo_id == amo_id,
    ).limit(10000).all()
    result: dict[str, list[str]] = {}
    for universe_id, state in rows:
        result.setdefault(str(universe_id), []).append(str(state))
    return result


def _global_factors(metrics: dict[str, int], reliability: dict[str, int]) -> list[dict[str, Any]]:
    mapping = (
        ("OPEN_FINDINGS", "Open audit findings", metrics.get("open_findings", 0), "quality", "Open findings increase assurance demand and may require targeted follow-up."),
        ("OVERDUE_CARS", "Overdue corrective actions", metrics.get("overdue_cars", 0), "quality", "Overdue corrective actions are an explicit assurance exposure."),
        ("EXPIRED_TRAINING", "Expired training records", metrics.get("expired_training", 0), "training", "Expired competence evidence can increase personnel-related surveillance need."),
        ("SUPPLIER_APPROVAL_EXPIRY", "Expired supplier approvals", metrics.get("expired_supplier_approvals", 0), "supplier", "Expired supplier approval evidence increases supplier-surveillance exposure."),
        ("CALIBRATION_OVERDUE", "Overdue calibrations", metrics.get("overdue_calibrations", 0), "calibration", "Overdue calibration can affect inspection/test assurance."),
        ("OUT_OF_TOLERANCE", "Open out-of-tolerance events", metrics.get("out_of_tolerance", 0), "calibration", "Out-of-tolerance events may require impact-focused surveillance."),
        ("HIGH_CRITICAL_RISKS", "High / critical risks", metrics.get("high_risks", 0) + metrics.get("critical_risks", 0), "risk", "Open high or critical governed risks increase assurance attention."),
        ("PENDING_CHANGES", "Pending organizational / process changes", metrics.get("pending_changes", 0), "change", "Active changes can require post-implementation or transition surveillance."),
        ("MANAGEMENT_REVIEW_OVERDUE", "Overdue management-review actions", metrics.get("overdue_review_actions", 0), "management-review", "Overdue management commitments are assurance obligations."),
        ("REGULATOR_FINDINGS", "Open regulator findings", metrics.get("open_regulator_findings", 0), "regulator", "Open authority findings are explicit regulatory-consequence exposure."),
        ("EXTERNAL_COMMITMENTS", "Overdue external commitments", metrics.get("overdue_external_commitments", 0), "regulator", "Overdue authority/customer commitments require visible surveillance attention."),
        ("RELIABILITY_EVENTS", "High / critical reliability events (90d)", reliability.get("high_critical_events_90d", 0), "reliability", "Recent high/critical reliability events can justify focused technical surveillance."),
        ("REPEAT_RELIABILITY", "Repeat reliability events (90d)", reliability.get("repeat_events_90d", 0), "reliability", "Repeated reliability events are a deterministic recurrence signal."),
        ("RELIABILITY_RECURRING_FINDINGS", "Reliability recurring findings", reliability.get("recurring_findings", 0), "reliability", "Recurring reliability findings increase targeted-surveillance attention."),
        ("RELIABILITY_RECOMMENDATIONS", "Open high-priority reliability recommendations", reliability.get("open_high_recommendations", 0), "reliability", "Open high-priority reliability recommendations represent unresolved operational exposure."),
    )
    return [_factor(code, label, value, source=source, rationale=rationale) for code, label, value, source, rationale in mapping if int(value or 0) > 0]


def _applies(item: QualityAuditUniverseItem, factor: dict[str, Any]) -> bool:
    owner = str(item.source_owner_module or "").lower()
    source_type = str(item.source_type or "").lower()
    entity = str(item.entity_type or "").lower()
    source = factor["source"]
    terms = {
        "training": ("training", "person", "competence", "authorization"),
        "supplier": ("supplier", "vendor", "procurement", "contractor"),
        "calibration": ("calibration", "tool", "equipment", "test equipment"),
        "risk": ("risk", "safety"),
        "change": ("change", "capability", "organization"),
        "management-review": ("management", "review"),
        "regulator": ("regulator", "authority", "approval", "commitment"),
        "reliability": ("reliability", "aircraft", "fleet", "technical", "maintenance"),
        "quality": ("quality", "audit", "finding", "car", "capa"),
    }.get(source, (source,))
    haystack = " ".join((owner, source_type, entity)).lower()
    return any(term in haystack for term in terms)


def _item_context(item: QualityAuditUniverseItem, states: list[str], global_factors: list[dict[str, Any]]) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []
    if item.mandatory_surveillance:
        factors.append(_factor("MANDATORY_SURVEILLANCE", "Mandatory surveillance", True, source="audit-universe", rationale="Mandatory surveillance is a hard requirement and is never averaged away.", hard=True))
    if item.regulatory_criticality in {"HIGH", "CRITICAL"}:
        factors.append(_factor("REGULATORY_CRITICALITY", "Regulatory criticality", item.regulatory_criticality, source="audit-universe", rationale="Governed HIGH/CRITICAL regulatory criticality increases planning priority."))
    if item.risk_classification in {"HIGH", "CRITICAL"}:
        factors.append(_factor("UNIVERSE_RISK", "Audit-universe risk classification", item.risk_classification, source="audit-universe", rationale="Governed HIGH/CRITICAL universe classification increases planning priority."))
    if "DEFERRED" in states:
        factors.append(_factor("REPEATED_DEFERRAL_PRESSURE", "Deferred programme requirement", states.count("DEFERRED"), source="audit-programme", rationale="A deferred governed requirement remains visible as planning exposure."))
    factors.extend(factor for factor in global_factors if _applies(item, factor))

    score = (10000 if item.mandatory_surveillance else 0) + (_RANK.get(item.regulatory_criticality, 0) * 1000) + (_RANK.get(item.risk_classification, 0) * 100)
    score += min(sum(int(factor["value"]) if isinstance(factor["value"], int) else 1 for factor in factors if not factor["hard_requirement"]), 99)
    return {
        "universe_item_id": str(item.id),
        "label": item.display_label,
        "entity_type": item.entity_type,
        "source_owner_module": item.source_owner_module,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "source_route": item.source_route,
        "mandatory_surveillance": bool(item.mandatory_surveillance),
        "risk_classification": item.risk_classification,
        "regulatory_criticality": item.regulatory_criticality,
        "programme_states": states,
        "planning_order": score,
        "factors": factors,
        "method": "Deterministic ordering from governed universe properties plus attributable authoritative-source pressures; not a probability or automated compliance conclusion.",
    }


@router.get("/audit-programmes/risk-context")
def audit_programme_risk_context(
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, assurance_warnings = _full_metrics(db, ctx)
    reliability, reliability_warnings = _reliability_context(db, ctx)
    global_factors = _global_factors(metrics, reliability)
    states = _programme_states(db, ctx.amo_id)
    universe = db.query(QualityAuditUniverseItem).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.active.is_(True),
    ).limit(1000).all()
    items = [_item_context(row, states.get(str(row.id), []), global_factors) for row in universe]
    items.sort(key=lambda row: (-int(row["planning_order"]), str(row["label"]).lower()))
    return {
        "as_of": _utcnow().isoformat(),
        "items": items[:limit],
        "global_factors": global_factors,
        "authoritative_metrics": metrics,
        "reliability": reliability,
        "source_warnings": [*assurance_warnings, *reliability_warnings],
        "method": {
            "type": "DETERMINISTIC_SOURCE_ATTRIBUTION",
            "statement": "Mandatory surveillance remains a hard obligation. Other factors order planning attention only; they do not declare compliance or calculate a predictive probability.",
        },
    }
