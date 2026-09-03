from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .assurance_case_models import QualityAssuranceCase, QualityEffectivenessPlan
from .assurance_metrics_router import _full_metrics
from .assurance_wiring_router import _safe_identifier, _table_columns
from .audit_programme_models import QualityAuditProgrammeItem, QualityAuditUniverseItem
from .mission_models import QualityMission
from .models import QMSAudit, QMSAuditFinding, QMSAuditSchedule
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(tags=["Quality risk-based audit planning"])

_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_SAFETY_OCCURRENCE_SOURCE_CONTRACT = {
    "source_owner_module": "safety",
    "source_type": "SAFETY_OCCURRENCE",
    "source_id": "authoritative Safety occurrence identifier",
    "source_route": "optional deep link into the authoritative Safety record",
    "audit_universe_source_id": "optional exact Quality Audit Universe source_id used only for explicit targeting",
}
_MISSION_AIRCRAFT_SCOPE_KEYS = (
    "aircraft_type",
    "aircraft_types",
    "aircraft_type_id",
    "aircraft_type_ids",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _factor(
    code: str,
    label: str,
    value: Any,
    *,
    source: str,
    rationale: str,
    hard: bool = False,
    planning_weight: int | None = None,
    source_record: str | None = None,
    source_date: str | None = None,
) -> dict[str, Any]:
    payload = {
        "code": code,
        "label": label,
        "value": value,
        "source": source,
        "source_record": source_record or source,
        "source_date": source_date,
        "hard_requirement": hard,
        "rationale": rationale,
    }
    if planning_weight is not None:
        payload["planning_weight"] = max(int(planning_weight), 0)
    return payload


def _normalize_title(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _is_safety_occurrence_reference(reference: Any) -> bool:
    if not isinstance(reference, dict):
        return False
    owner = str(
        reference.get("source_owner_module")
        or reference.get("owner_module")
        or reference.get("module")
        or ""
    ).strip().lower()
    source_type = str(reference.get("source_type") or reference.get("type") or "").strip().upper()
    return owner == "safety" and source_type == "SAFETY_OCCURRENCE"


def _scope_values(scope: Any, keys: tuple[str, ...]) -> list[str]:
    if not isinstance(scope, dict):
        return []
    values: list[str] = []
    for key in keys:
        raw = scope.get(key)
        if raw is None:
            continue
        candidates = raw if isinstance(raw, list) else [raw]
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("id") or candidate.get("code") or candidate.get("name")
            text_value = str(candidate or "").strip()
            if text_value and text_value not in values:
                values.append(text_value)
    return values


def _mission_change_context(db: Session, amo_id: str) -> dict[str, Any]:
    rows = db.query(QualityMission).filter(
        QualityMission.amo_id == amo_id,
        QualityMission.status.notin_(("COMPLETE", "CANCELLED")),
    ).limit(1000).all()

    capability_records: list[dict[str, Any]] = []
    aircraft_type_records: list[dict[str, Any]] = []
    by_universe_source_id: dict[str, dict[str, int]] = {}
    latest_change_at: datetime | None = None

    for mission in rows:
        changed_at = _aware(mission.updated_at or mission.created_at)
        if changed_at is not None and (latest_change_at is None or changed_at > latest_change_at):
            latest_change_at = changed_at
        scope = mission.scope if isinstance(mission.scope, dict) else {}
        universe_ids = _scope_values(scope, ("audit_universe_source_id", "audit_universe_source_ids"))
        base_record = {
            "mission_id": str(mission.id),
            "mission_ref": mission.mission_ref,
            "mission_type": mission.mission_type,
            "title": mission.title,
            "status": mission.status,
            "risk_level": mission.risk_level,
            "updated_at": changed_at.isoformat() if changed_at else None,
            "route": f"/quality/missions/{mission.id}",
        }

        if mission.mission_type in {"CAPABILITY_ADDITION", "CAPABILITY_CHANGE"}:
            capability_records.append(base_record)
            for universe_source_id in universe_ids:
                bucket = by_universe_source_id.setdefault(universe_source_id, {})
                bucket["capability"] = bucket.get("capability", 0) + 1

        aircraft_types = _scope_values(scope, _MISSION_AIRCRAFT_SCOPE_KEYS)
        if aircraft_types:
            aircraft_type_records.append({**base_record, "aircraft_types": aircraft_types})
            for universe_source_id in universe_ids:
                bucket = by_universe_source_id.setdefault(universe_source_id, {})
                bucket["aircraft_type"] = bucket.get("aircraft_type", 0) + 1

    return {
        "open_capability_missions": len(capability_records),
        "open_aircraft_type_missions": len(aircraft_type_records),
        "capability_records": capability_records,
        "aircraft_type_records": aircraft_type_records,
        "by_universe_source_id": by_universe_source_id,
        "latest_change_at": latest_change_at.isoformat() if latest_change_at else None,
        "aircraft_scope_contract": {
            "accepted_keys": list(_MISSION_AIRCRAFT_SCOPE_KEYS),
            "method": "Aircraft-type exposure is counted only from explicit governed Mission scope keys; mission title/description text is never parsed as aircraft-type evidence.",
        },
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
    if event_columns and "amo_id" in event_columns:
        where = ["amo_id = :amo_id"]
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
    elif not event_columns:
        warnings.append({"source": "reliability_events", "type": "SourceUnavailable", "message": "Reliability event ledger is unavailable."})
    else:
        warnings.append({"source": "reliability_events", "type": "TenantIsolationUnavailable", "message": "Reliability event ledger has no tenant key and was excluded."})

    recurring_columns = _table_columns(db, "reliability_recurring_findings")
    if recurring_columns and "amo_id" in recurring_columns:
        conditions = ["amo_id = :amo_id"]
        if "occurrence_count" in recurring_columns:
            conditions.append("occurrence_count > 1")
        values["recurring_findings"] = int(db.execute(text(
            f"SELECT COUNT(*) FROM {_safe_identifier('reliability_recurring_findings')}" + (" WHERE " + " AND ".join(conditions) if conditions else "")
        ), {"amo_id": ctx.amo_id}).scalar() or 0)
    elif not recurring_columns:
        warnings.append({"source": "reliability_recurring_findings", "type": "SourceUnavailable", "message": "Reliability recurring-finding ledger is unavailable."})
    else:
        warnings.append({"source": "reliability_recurring_findings", "type": "TenantIsolationUnavailable", "message": "Reliability recurring-finding ledger has no tenant key and was excluded."})

    recommendation_columns = _table_columns(db, "reliability_recommendations")
    if recommendation_columns and "amo_id" in recommendation_columns:
        conditions = ["amo_id = :amo_id"]
        if "status" in recommendation_columns:
            conditions.append("UPPER(CAST(status AS TEXT)) NOT IN ('CLOSED','CANCELLED')")
        if "priority" in recommendation_columns:
            conditions.append("UPPER(CAST(priority AS TEXT)) = 'HIGH'")
        values["open_high_recommendations"] = int(db.execute(text(
            f"SELECT COUNT(*) FROM {_safe_identifier('reliability_recommendations')}" + (" WHERE " + " AND ".join(conditions) if conditions else "")
        ), {"amo_id": ctx.amo_id}).scalar() or 0)
    elif not recommendation_columns:
        warnings.append({"source": "reliability_recommendations", "type": "SourceUnavailable", "message": "Reliability recommendation ledger is unavailable."})
    else:
        warnings.append({"source": "reliability_recommendations", "type": "TenantIsolationUnavailable", "message": "Reliability recommendation ledger has no tenant key and was excluded."})

    return values, warnings


def _audit_history_context(db: Session, amo_id: str) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    rows = db.query(
        QualityAuditProgrammeItem.universe_item_id,
        QualityAuditProgrammeItem.state,
        QMSAuditSchedule.title,
        QMSAuditSchedule.last_run_at,
    ).outerjoin(
        QMSAuditSchedule,
        and_(
            QualityAuditProgrammeItem.schedule_id == QMSAuditSchedule.id,
            QualityAuditProgrammeItem.amo_id == QMSAuditSchedule.amo_id,
        ),
    ).filter(
        QualityAuditProgrammeItem.amo_id == amo_id,
    ).limit(10000).all()

    states: dict[str, list[str]] = {}
    titles_by_universe: dict[str, set[str]] = {}
    last_by_universe: dict[str, datetime] = {}
    all_titles: set[str] = set()
    for universe_id, state, schedule_title, last_run_at in rows:
        universe_key = str(universe_id)
        states.setdefault(universe_key, []).append(str(state))
        title_key = _normalize_title(schedule_title)
        if title_key:
            titles_by_universe.setdefault(universe_key, set()).add(title_key)
            all_titles.add(title_key)
        last_value = _aware(last_run_at)
        if last_value is not None and (universe_key not in last_by_universe or last_value > last_by_universe[universe_key]):
            last_by_universe[universe_key] = last_value

    history_by_title: dict[str, dict[str, Any]] = {}
    if all_titles:
        title_expr = func.lower(func.trim(QMSAudit.title))
        audit_dates = db.query(
            title_expr.label("title_key"),
            func.max(func.coalesce(QMSAudit.actual_end, QMSAudit.actual_start)).label("last_audit_at"),
        ).filter(
            QMSAudit.amo_id == amo_id,
            title_expr.in_(sorted(all_titles)),
        ).group_by(title_expr).all()
        for title_key, last_audit_at in audit_dates:
            normalized = _normalize_title(title_key)
            history_by_title.setdefault(normalized, {})["last_audit_at"] = _aware(last_audit_at)

        finding_totals = db.query(
            title_expr.label("title_key"),
            func.count(QMSAuditFinding.id).label("finding_count"),
        ).join(
            QMSAuditFinding,
            QMSAuditFinding.audit_id == QMSAudit.id,
        ).filter(
            QMSAudit.amo_id == amo_id,
            QMSAuditFinding.amo_id == amo_id,
            title_expr.in_(sorted(all_titles)),
        ).group_by(title_expr).all()
        for title_key, finding_count in finding_totals:
            history_by_title.setdefault(_normalize_title(title_key), {})["finding_count"] = int(finding_count or 0)

        requirement_expr = func.lower(func.trim(QMSAuditFinding.requirement_ref))
        repeats = db.query(
            title_expr.label("title_key"),
            requirement_expr.label("requirement_key"),
            func.count(func.distinct(QMSAudit.id)).label("audit_count"),
        ).join(
            QMSAuditFinding,
            QMSAuditFinding.audit_id == QMSAudit.id,
        ).filter(
            QMSAudit.amo_id == amo_id,
            QMSAuditFinding.amo_id == amo_id,
            title_expr.in_(sorted(all_titles)),
            QMSAuditFinding.requirement_ref.isnot(None),
            requirement_expr != "",
        ).group_by(title_expr, requirement_expr).having(
            func.count(func.distinct(QMSAudit.id)) > 1,
        ).all()
        for title_key, _requirement_key, audit_count in repeats:
            bucket = history_by_title.setdefault(_normalize_title(title_key), {})
            bucket["repeat_requirement_count"] = int(bucket.get("repeat_requirement_count", 0)) + 1
            bucket["repeat_occurrence_count"] = int(bucket.get("repeat_occurrence_count", 0)) + max(int(audit_count or 0) - 1, 0)

    now = _utcnow()
    by_universe: dict[str, dict[str, Any]] = {}
    for universe_key, titles in titles_by_universe.items():
        last_candidates = [last_by_universe[universe_key]] if universe_key in last_by_universe else []
        finding_count = 0
        repeat_requirement_count = 0
        repeat_occurrence_count = 0
        for title_key in titles:
            payload = history_by_title.get(title_key, {})
            if payload.get("last_audit_at") is not None:
                last_candidates.append(payload["last_audit_at"])
            finding_count += int(payload.get("finding_count", 0))
            repeat_requirement_count += int(payload.get("repeat_requirement_count", 0))
            repeat_occurrence_count += int(payload.get("repeat_occurrence_count", 0))
        last_audit_at = max(last_candidates) if last_candidates else None
        by_universe[universe_key] = {
            "schedule_titles": sorted(titles),
            "last_audit_at": last_audit_at.isoformat() if last_audit_at else None,
            "days_since_last_audit": max((now - last_audit_at).days, 0) if last_audit_at else None,
            "finding_count": finding_count,
            "repeat_requirement_count": repeat_requirement_count,
            "repeat_occurrence_count": repeat_occurrence_count,
        }
    return states, by_universe


def _effectiveness_context(db: Session, amo_id: str) -> dict[str, Any]:
    rows = db.query(
        QualityEffectivenessPlan.source_type,
        QualityEffectivenessPlan.source_id,
        QualityEffectivenessPlan.source_route,
    ).filter(
        QualityEffectivenessPlan.amo_id == amo_id,
        QualityEffectivenessPlan.conclusion == "INEFFECTIVE",
    ).all()
    by_source_id: dict[str, int] = {}
    for _source_type, source_id, _source_route in rows:
        if source_id:
            by_source_id[str(source_id)] = by_source_id.get(str(source_id), 0) + 1
    return {
        "ineffective_corrective_actions": len(rows),
        "by_source_id": by_source_id,
        "source": "quality_effectiveness_plans.conclusion=INEFFECTIVE",
    }


def _safety_occurrence_context(db: Session, amo_id: str) -> dict[str, Any]:
    rows = db.query(
        QualityAssuranceCase.id,
        QualityAssuranceCase.status,
        QualityAssuranceCase.source_references,
    ).filter(
        QualityAssuranceCase.amo_id == amo_id,
        QualityAssuranceCase.status.notin_(("CLOSED", "CANCELLED")),
    ).all()
    occurrence_keys: set[str] = set()
    by_universe_source_id: dict[str, int] = {}
    references: list[dict[str, Any]] = []
    for case_id, _status, source_references in rows:
        for index, reference in enumerate(source_references or []):
            if not _is_safety_occurrence_reference(reference):
                continue
            source_id = str(reference.get("source_id") or f"case:{case_id}:ref:{index}")
            if source_id in occurrence_keys:
                continue
            occurrence_keys.add(source_id)
            references.append({
                "source_id": source_id,
                "source_route": reference.get("source_route"),
                "assurance_case_id": str(case_id),
                "audit_universe_source_id": reference.get("audit_universe_source_id"),
            })
            universe_source_id = reference.get("audit_universe_source_id")
            if universe_source_id:
                key = str(universe_source_id)
                by_universe_source_id[key] = by_universe_source_id.get(key, 0) + 1
    return {
        "open_linked_occurrences": len(occurrence_keys),
        "by_universe_source_id": by_universe_source_id,
        "references": references,
        "source_contract": _SAFETY_OCCURRENCE_SOURCE_CONTRACT,
        "method": "Only explicit Safety-owned SAFETY_OCCURRENCE source references are consumed. Generic risk records are not relabelled as Safety occurrences.",
    }


def _global_factors(
    metrics: dict[str, int],
    reliability: dict[str, int],
    effectiveness: dict[str, Any] | None = None,
    safety: dict[str, Any] | None = None,
    mission_change: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    effectiveness = effectiveness or {}
    safety = safety or {}
    mission_change = mission_change or {}
    observed_at = _utcnow().isoformat()
    mapping = (
        ("OPEN_FINDINGS", "Open audit findings", metrics.get("open_findings", 0), "quality", "quality_assurance_metrics.open_findings", "Open findings increase assurance demand and may require targeted follow-up."),
        ("OVERDUE_CARS", "Overdue corrective actions", metrics.get("overdue_cars", 0), "quality", "quality_assurance_metrics.overdue_cars", "Overdue corrective actions are an explicit assurance exposure."),
        ("INEFFECTIVE_CORRECTIVE_ACTIONS", "Ineffective corrective-action effectiveness reviews", effectiveness.get("ineffective_corrective_actions", 0), "effectiveness", "quality_effectiveness_plans.conclusion=INEFFECTIVE", "A governed INEFFECTIVE effectiveness conclusion is direct evidence that corrective action did not achieve the expected outcome."),
        ("EXPIRED_TRAINING", "Expired training records", metrics.get("expired_training", 0), "training", "quality_assurance_metrics.expired_training", "Expired competence evidence can increase personnel-related surveillance need."),
        ("SUPPLIER_APPROVAL_EXPIRY", "Expired supplier approvals", metrics.get("expired_supplier_approvals", 0), "supplier", "quality_assurance_metrics.expired_supplier_approvals", "Expired supplier approval evidence increases supplier-surveillance exposure."),
        ("CALIBRATION_OVERDUE", "Overdue calibrations", metrics.get("overdue_calibrations", 0), "calibration", "quality_assurance_metrics.overdue_calibrations", "Overdue calibration can affect inspection/test assurance."),
        ("OUT_OF_TOLERANCE", "Open out-of-tolerance events", metrics.get("out_of_tolerance", 0), "calibration", "quality_assurance_metrics.out_of_tolerance", "Out-of-tolerance events may require impact-focused surveillance."),
        ("HIGH_CRITICAL_RISKS", "High / critical risks", metrics.get("high_risks", 0) + metrics.get("critical_risks", 0), "risk", "quality_assurance_metrics.high_risks+critical_risks", "Open high or critical governed risks increase assurance attention."),
        ("SAFETY_OCCURRENCES", "Open explicitly linked Safety occurrences", safety.get("open_linked_occurrences", 0), "safety-occurrence", "quality_assurance_cases.source_references[safety/SAFETY_OCCURRENCE]", "Only explicit Safety-owned SAFETY_OCCURRENCE references attached to open assurance cases contribute this factor."),
        ("PENDING_CHANGES", "Pending organizational / process changes", metrics.get("pending_changes", 0), "change", "quality_assurance_metrics.pending_changes", "Active changes can require post-implementation or transition surveillance."),
        ("NEW_CAPABILITIES", "Open capability additions / changes", mission_change.get("open_capability_missions", 0), "mission-capability", "quality_missions.mission_type in CAPABILITY_ADDITION/CAPABILITY_CHANGE", "Governed capability additions or changes require readiness and post-implementation surveillance attention."),
        ("NEW_AIRCRAFT_TYPES", "Open Missions explicitly scoped to aircraft types", mission_change.get("open_aircraft_type_missions", 0), "mission-aircraft-type", "quality_missions.scope.aircraft_type(s)", "Aircraft-type planning exposure is counted only where a governed Mission scope explicitly identifies an aircraft type."),
        ("MANAGEMENT_REVIEW_OVERDUE", "Overdue management-review actions", metrics.get("overdue_review_actions", 0), "management-review", "quality_assurance_metrics.overdue_review_actions", "Overdue management commitments are assurance obligations."),
        ("REGULATOR_FINDINGS", "Open regulator findings", metrics.get("open_regulator_findings", 0), "regulator", "quality_assurance_metrics.open_regulator_findings", "Open authority findings are explicit regulatory-consequence exposure."),
        ("EXTERNAL_COMMITMENTS", "Overdue external commitments", metrics.get("overdue_external_commitments", 0), "regulator", "quality_assurance_metrics.overdue_external_commitments", "Overdue authority/customer commitments require visible surveillance attention."),
        ("RELIABILITY_EVENTS", "High / critical reliability events (90d)", reliability.get("high_critical_events_90d", 0), "reliability", "reliability_events", "Recent high/critical reliability events can justify focused technical surveillance."),
        ("REPEAT_RELIABILITY", "Repeat reliability events (90d)", reliability.get("repeat_events_90d", 0), "reliability", "reliability_events.repeat_key", "Repeated reliability events are a deterministic recurrence signal."),
        ("RELIABILITY_RECURRING_FINDINGS", "Reliability recurring findings", reliability.get("recurring_findings", 0), "reliability", "reliability_recurring_findings", "Recurring reliability findings increase targeted-surveillance attention."),
        ("RELIABILITY_RECOMMENDATIONS", "Open high-priority reliability recommendations", reliability.get("open_high_recommendations", 0), "reliability", "reliability_recommendations", "Open high-priority reliability recommendations represent unresolved operational exposure."),
    )
    return [
        _factor(code, label, value, source=source, source_record=source_record, source_date=observed_at, rationale=rationale)
        for code, label, value, source, source_record, rationale in mapping
        if int(value or 0) > 0
    ]


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
        "safety-occurrence": ("safety", "sms", "occurrence", "incident", "hazard"),
        "change": ("change", "capability", "organization"),
        "mission-capability": ("capability", "approval", "rating", "maintenance"),
        "mission-aircraft-type": ("aircraft", "fleet", "type", "capability", "maintenance"),
        "management-review": ("management", "review"),
        "regulator": ("regulator", "authority", "approval", "commitment"),
        "reliability": ("reliability", "aircraft", "fleet", "technical", "maintenance"),
        "quality": ("quality", "audit", "finding", "car", "capa"),
        "effectiveness": ("quality", "audit", "finding", "car", "capa", "corrective", "assurance"),
    }.get(source, (source,))
    haystack = " ".join((owner, source_type, entity)).lower()
    return any(term in haystack for term in terms)


def _factor_weight(factor: dict[str, Any]) -> int:
    if "planning_weight" in factor:
        return int(factor["planning_weight"] or 0)
    value = factor.get("value")
    return int(value) if isinstance(value, int) else 1


def _item_context(
    item: QualityAuditUniverseItem,
    states: list[str],
    global_factors: list[dict[str, Any]],
    history: dict[str, Any] | None = None,
    effectiveness: dict[str, Any] | None = None,
    safety: dict[str, Any] | None = None,
    mission_change: dict[str, Any] | None = None,
) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []
    history = history or {}
    effectiveness = effectiveness or {}
    safety = safety or {}
    mission_change = mission_change or {}
    now_iso = _utcnow().isoformat()
    if item.mandatory_surveillance:
        factors.append(_factor("MANDATORY_SURVEILLANCE", "Mandatory surveillance", True, source="audit-universe", source_record=f"quality_audit_universe_items:{item.id}", source_date=now_iso, rationale="Mandatory surveillance is a hard requirement and is never averaged away.", hard=True))
    if item.regulatory_criticality in {"HIGH", "CRITICAL"}:
        factors.append(_factor("REGULATORY_CRITICALITY", "Regulatory criticality", item.regulatory_criticality, source="audit-universe", source_record=f"quality_audit_universe_items:{item.id}", source_date=now_iso, rationale="Governed HIGH/CRITICAL regulatory criticality increases planning priority."))
    if item.risk_classification in {"HIGH", "CRITICAL"}:
        factors.append(_factor("UNIVERSE_RISK", "Audit-universe risk classification", item.risk_classification, source="audit-universe", source_record=f"quality_audit_universe_items:{item.id}", source_date=now_iso, rationale="Governed HIGH/CRITICAL universe classification increases planning priority."))
    if "DEFERRED" in states:
        factors.append(_factor("REPEATED_DEFERRAL_PRESSURE", "Deferred programme requirement", states.count("DEFERRED"), source="audit-programme", source_record=f"quality_audit_programme_items:universe:{item.id}", source_date=now_iso, rationale="A deferred governed requirement remains visible as planning exposure."))

    days_since = history.get("days_since_last_audit")
    if days_since is not None:
        interval = int(item.surveillance_interval_days or 0)
        overdue_days = max(int(days_since) - interval, 0) if interval > 0 else 0
        factors.append(_factor(
            "TIME_SINCE_LAST_AUDIT",
            "Time since last completed audit",
            int(days_since),
            source="audit-history",
            source_record=", ".join(history.get("schedule_titles") or []) or f"universe:{item.id}",
            source_date=history.get("last_audit_at"),
            rationale=(
                f"The most recent attributable audit is {int(days_since)} day(s) old; the governed surveillance interval is {interval} day(s)."
                if interval > 0
                else f"The most recent attributable audit is {int(days_since)} day(s) old."
            ),
            planning_weight=min(max((overdue_days // 30) + 1, 1), 24),
        ))
    elif history.get("schedule_titles"):
        factors.append(_factor(
            "NO_COMPLETED_AUDIT_HISTORY",
            "No completed audit history",
            True,
            source="audit-history",
            source_record=", ".join(history.get("schedule_titles") or []),
            source_date=None,
            rationale="A programme-linked schedule exists but no attributable completed audit date is recorded.",
            planning_weight=12,
        ))

    if int(history.get("finding_count", 0)) > 0:
        factors.append(_factor(
            "AUDIT_FINDING_HISTORY",
            "Historical audit findings",
            int(history["finding_count"]),
            source="audit-history",
            source_record=", ".join(history.get("schedule_titles") or []) or f"universe:{item.id}",
            source_date=history.get("last_audit_at"),
            rationale="Historical findings from exact-title-linked audit instances remain visible to the planner.",
        ))
    if int(history.get("repeat_occurrence_count", 0)) > 0:
        factors.append(_factor(
            "REPEAT_AUDIT_FINDINGS",
            "Repeat audit findings",
            int(history["repeat_occurrence_count"]),
            source="audit-history",
            source_record=", ".join(history.get("schedule_titles") or []) or f"universe:{item.id}",
            source_date=history.get("last_audit_at"),
            rationale=f"{int(history.get('repeat_requirement_count', 0))} requirement reference(s) recurred across distinct attributable audits.",
            planning_weight=min(int(history["repeat_occurrence_count"]) * 3, 30),
        ))

    direct_ineffective = int((effectiveness.get("by_source_id") or {}).get(str(item.source_id), 0))
    if direct_ineffective > 0:
        factors.append(_factor(
            "DIRECT_INEFFECTIVE_CORRECTIVE_ACTION",
            "Ineffective corrective action linked to this source",
            direct_ineffective,
            source="effectiveness",
            source_record=f"quality_effectiveness_plans:source_id:{item.source_id}",
            source_date=now_iso,
            rationale="The governed effectiveness plan source_id exactly matches this Audit Universe source record.",
            planning_weight=min(direct_ineffective * 5, 30),
        ))

    direct_safety = int((safety.get("by_universe_source_id") or {}).get(str(item.source_id), 0))
    if direct_safety > 0:
        factors.append(_factor(
            "DIRECT_SAFETY_OCCURRENCE",
            "Safety occurrence explicitly linked to this Audit Universe source",
            direct_safety,
            source="safety-occurrence",
            source_record=f"quality_assurance_cases.source_references:audit_universe_source_id:{item.source_id}",
            source_date=now_iso,
            rationale="The Safety-owned source reference explicitly names this Audit Universe source_id; no inferred linkage is used.",
            planning_weight=min(direct_safety * 5, 30),
        ))

    mission_bucket = (mission_change.get("by_universe_source_id") or {}).get(str(item.source_id), {})
    direct_capability = int(mission_bucket.get("capability", 0))
    if direct_capability > 0:
        factors.append(_factor(
            "DIRECT_NEW_CAPABILITY",
            "Capability Mission explicitly linked to this source",
            direct_capability,
            source="mission-capability",
            source_record=f"quality_missions.scope.audit_universe_source_id:{item.source_id}",
            source_date=mission_change.get("latest_change_at"),
            rationale="A governed capability addition/change Mission explicitly targets this Audit Universe source_id.",
            planning_weight=min(direct_capability * 5, 30),
        ))
    direct_aircraft = int(mission_bucket.get("aircraft_type", 0))
    if direct_aircraft > 0:
        factors.append(_factor(
            "DIRECT_NEW_AIRCRAFT_TYPE",
            "Aircraft-type Mission explicitly linked to this source",
            direct_aircraft,
            source="mission-aircraft-type",
            source_record=f"quality_missions.scope.audit_universe_source_id:{item.source_id}",
            source_date=mission_change.get("latest_change_at"),
            rationale="A governed Mission with explicit aircraft-type scope also explicitly targets this Audit Universe source_id.",
            planning_weight=min(direct_aircraft * 5, 30),
        ))

    factors.extend(factor for factor in global_factors if _applies(item, factor))

    score = (10000 if item.mandatory_surveillance else 0) + (_RANK.get(item.regulatory_criticality, 0) * 1000) + (_RANK.get(item.risk_classification, 0) * 100)
    score += min(sum(_factor_weight(factor) for factor in factors if not factor["hard_requirement"]), 99)
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
        "audit_history": history,
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
    effectiveness = _effectiveness_context(db, ctx.amo_id)
    safety = _safety_occurrence_context(db, ctx.amo_id)
    mission_change = _mission_change_context(db, ctx.amo_id)
    global_factors = _global_factors(metrics, reliability, effectiveness, safety, mission_change)
    states, audit_history = _audit_history_context(db, ctx.amo_id)
    universe = db.query(QualityAuditUniverseItem).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.active.is_(True),
    ).limit(1000).all()
    items = [
        _item_context(
            row,
            states.get(str(row.id), []),
            global_factors,
            audit_history.get(str(row.id), {}),
            effectiveness,
            safety,
            mission_change,
        )
        for row in universe
    ]
    items.sort(key=lambda row: (-int(row["planning_order"]), str(row["label"]).lower()))
    return {
        "as_of": _utcnow().isoformat(),
        "items": items[:limit],
        "global_factors": global_factors,
        "authoritative_metrics": metrics,
        "reliability": reliability,
        "effectiveness": effectiveness,
        "safety_occurrence": safety,
        "mission_change": mission_change,
        "source_warnings": [*assurance_warnings, *reliability_warnings],
        "method": {
            "type": "DETERMINISTIC_SOURCE_ATTRIBUTION",
            "statement": "Mandatory surveillance remains a hard obligation. Audit history, repeat findings, governed ineffective corrective actions, explicit capability/aircraft-type Missions, and explicitly linked Safety occurrences are source-attributed planning inputs. Factors expose source record, observation date and rationale; they order planning attention only and do not declare compliance or calculate a predictive probability.",
        },
    }
