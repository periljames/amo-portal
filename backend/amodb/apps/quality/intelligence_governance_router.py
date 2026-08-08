from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from . import models
from .assurance_case_models import QualityAssuranceCase, QualityEffectivenessPlan
from .audit_programme_models import QualityAuditProgramme, QualityAuditProgrammeItem
from .intelligence_models import QualityRequirementLink, QualityRequirementNode, QualitySignalObservation, QualitySignalRule
from .people_models import QualityPrivilege, QualityPrivilegeRule
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context

router = APIRouter(prefix="/intelligence", tags=["Quality intelligence governance"])

Metric = Literal["PROGRAMME_COMPLETION_RATE", "PROGRAMME_DEFERRAL_RATE", "OPEN_FINDING_COUNT", "FINDING_RECURRENCE_COUNT", "OVERDUE_CAR_COUNT", "CAR_AGE_DAYS", "INEFFECTIVE_ACTION_RATE", "AUDITOR_CAPACITY_EXCEPTIONS", "OPEN_ASSURANCE_CASES"]
Operator = Literal["GT", "GTE", "LT", "LTE", "EQ"]
SignalSeverity = Literal["INFO", "WATCH", "WARNING", "CRITICAL"]
NodeType = Literal["REQUIREMENT", "APPROVAL", "MANUAL", "PROCEDURE", "FORM", "TRAINING", "ROLE", "CHECKLIST", "EVIDENCE", "MISSION", "FINDING", "ACTION", "CAPABILITY"]
SupportState = Literal["SUPPORTED", "UNSUPPORTED", "STALE", "UNRESOLVED", "BLOCKED"]
Relationship = Literal["REQUIRES", "IMPLEMENTS", "EVIDENCES", "AUTHORIZES", "DEPENDS_ON", "AFFECTS", "VERIFIES", "BLOCKS", "SUPERSEDES"]


class SignalRuleCreate(BaseModel):
    rule_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_\-]+$")
    title: str = Field(min_length=3, max_length=255)
    metric: Metric
    operator: Operator
    threshold: Decimal
    severity: SignalSeverity = "WATCH"
    explanation: str = Field(min_length=8, max_length=4000)
    source_contract: dict[str, Any] = Field(default_factory=dict)


class RequirementNodeCreate(BaseModel):
    node_type: NodeType
    title: str = Field(min_length=2, max_length=255)
    source_owner_module: str = Field(min_length=2, max_length=80)
    source_type: str = Field(min_length=2, max_length=80)
    source_id: str = Field(min_length=1, max_length=160)
    source_route: str | None = Field(default=None, max_length=500)
    support_state: SupportState = "UNRESOLVED"
    state_reason: str = Field(min_length=8, max_length=4000)
    source_snapshot: dict[str, Any] | None = None
    evidence_as_of: datetime | None = None


class RequirementLinkCreate(BaseModel):
    from_node_id: str = Field(min_length=1, max_length=36)
    to_node_id: str = Field(min_length=1, max_length=36)
    relationship: Relationship
    rationale: str = Field(min_length=8, max_length=4000)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _number(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _percent(part: int, total: int) -> Decimal:
    return Decimal("0.000000") if total <= 0 else _number((Decimal(part) * Decimal(100)) / Decimal(total))


def _active_programme_items(db: Session, amo_id: str) -> list[QualityAuditProgrammeItem]:
    ids = [row[0] for row in db.query(QualityAuditProgramme.id).filter(QualityAuditProgramme.amo_id == amo_id, QualityAuditProgramme.status.in_(["APPROVED", "ACTIVE"])).all()]
    if not ids:
        return []
    return db.query(QualityAuditProgrammeItem).filter(QualityAuditProgrammeItem.amo_id == amo_id, QualityAuditProgrammeItem.programme_id.in_(ids)).limit(10000).all()


def _metric_snapshot(db: Session, amo_id: str, metric: str, as_of: datetime) -> tuple[Decimal, dict[str, Any], list[dict[str, Any]]]:
    today = as_of.date()
    if metric in {"PROGRAMME_COMPLETION_RATE", "PROGRAMME_DEFERRAL_RATE"}:
        items = _active_programme_items(db, amo_id)
        states = Counter(str(item.state) for item in items)
        key = "COMPLETED" if metric == "PROGRAMME_COMPLETION_RATE" else "DEFERRED"
        return _percent(states.get(key, 0), len(items)), {"total_requirements": len(items), "states": dict(states), "formula": f"{key.lower()} / approved-or-active programme requirements × 100"}, [{"source_type": "QUALITY_AUDIT_PROGRAMME_ITEM", "count": len(items)}]
    if metric == "OPEN_FINDING_COUNT":
        count = db.query(models.QMSAuditFinding.id).filter(models.QMSAuditFinding.amo_id == amo_id, models.QMSAuditFinding.closed_at.is_(None)).count()
        return _number(count), {"formula": "count(findings where closed_at is null)", "open_findings": count}, [{"source_type": "QMS_AUDIT_FINDING", "count": count}]
    if metric == "FINDING_RECURRENCE_COUNT":
        since = as_of - timedelta(days=365)
        rows = db.query(models.QMSAuditFinding.requirement_ref).filter(models.QMSAuditFinding.amo_id == amo_id, models.QMSAuditFinding.created_at >= since, models.QMSAuditFinding.requirement_ref.is_not(None)).limit(10000).all()
        counts = Counter(str(row[0]).strip() for row in rows if str(row[0] or "").strip())
        recurring = {key: count for key, count in counts.items() if count > 1}
        value = sum(count - 1 for count in recurring.values())
        return _number(value), {"window_days": 365, "recurring_requirement_refs": recurring, "formula": "sum(count(requirement_ref)-1) for repeated requirement references"}, [{"source_type": "QMS_AUDIT_FINDING", "rows": len(rows)}]
    if metric == "OVERDUE_CAR_COUNT":
        count = db.query(models.CorrectiveActionRequest.id).filter(models.CorrectiveActionRequest.amo_id == amo_id, models.CorrectiveActionRequest.closed_at.is_(None), models.CorrectiveActionRequest.due_date.is_not(None), models.CorrectiveActionRequest.due_date < today).count()
        return _number(count), {"formula": "count(open CAR where due_date < as_of)", "as_of_date": today.isoformat()}, [{"source_type": "QUALITY_CAR", "count": count}]
    if metric == "CAR_AGE_DAYS":
        row = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.amo_id == amo_id, models.CorrectiveActionRequest.closed_at.is_(None)).order_by(models.CorrectiveActionRequest.created_at.asc()).first()
        age = max((as_of - row.created_at).days, 0) if row else 0
        return _number(age), {"formula": "as_of - oldest open CAR created_at", "oldest_open_car_id": str(row.id) if row else None}, [{"source_type": "QUALITY_CAR", "source_id": str(row.id) if row else None}]
    if metric == "INEFFECTIVE_ACTION_RATE":
        plans = db.query(QualityEffectivenessPlan).filter(QualityEffectivenessPlan.amo_id == amo_id, QualityEffectivenessPlan.status == "CONCLUDED").limit(10000).all()
        ineffective = [plan for plan in plans if plan.conclusion in {"INEFFECTIVE", "PARTIALLY_EFFECTIVE"}]
        return _percent(len(ineffective), len(plans)), {"formula": "(ineffective + partially effective) / concluded effectiveness tests × 100", "concluded_tests": len(plans), "ineffective_or_partial": len(ineffective)}, [{"source_type": "QUALITY_EFFECTIVENESS_PLAN", "count": len(plans)}]
    if metric == "AUDITOR_CAPACITY_EXCEPTIONS":
        rules = db.query(QualityPrivilegeRule).filter(QualityPrivilegeRule.amo_id == amo_id, QualityPrivilegeRule.is_active.is_(True), QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"])).all()
        gaps = []
        for rule in rules:
            active = db.query(QualityPrivilege.id).filter(QualityPrivilege.amo_id == amo_id, QualityPrivilege.privilege_code == rule.privilege_code, QualityPrivilege.status == "ACTIVE").count()
            if active == 0:
                gaps.append({"privilege_code": rule.privilege_code, "title": rule.title})
        return _number(len(gaps)), {"formula": "count(active auditor privilege rules with zero active authorized people)", "coverage_gaps": gaps}, [{"source_type": "QUALITY_PRIVILEGE", "rules_evaluated": len(rules)}]
    if metric == "OPEN_ASSURANCE_CASES":
        count = db.query(QualityAssuranceCase.id).filter(QualityAssuranceCase.amo_id == amo_id, QualityAssuranceCase.status.notin_(["CLOSED", "CANCELLED"])).count()
        return _number(count), {"formula": "count(assurance cases excluding CLOSED/CANCELLED)", "open_cases": count}, [{"source_type": "QUALITY_ASSURANCE_CASE", "count": count}]
    raise HTTPException(status_code=422, detail=f"Metric '{metric}' is not implemented.")


def _compare(value: Decimal, operator: str, threshold: Decimal) -> bool:
    return {"GT": value > threshold, "GTE": value >= threshold, "LT": value < threshold, "LTE": value <= threshold, "EQ": value == threshold}[operator]


def _rule_dict(row: QualitySignalRule) -> dict[str, Any]:
    return {"id": str(row.id), "rule_code": row.rule_code, "title": row.title, "metric": row.metric, "operator": row.operator, "threshold": float(row.threshold), "severity": row.severity, "explanation": row.explanation, "source_contract": row.source_contract or {}, "is_active": bool(row.is_active)}


def _node_dict(row: QualityRequirementNode) -> dict[str, Any]:
    return {"id": str(row.id), "node_type": row.node_type, "title": row.title, "source_owner_module": row.source_owner_module, "source_type": row.source_type, "source_id": row.source_id, "source_route": row.source_route, "support_state": row.support_state, "state_reason": row.state_reason, "source_snapshot": row.source_snapshot, "evidence_as_of": row.evidence_as_of, "updated_at": row.updated_at}


def _link_dict(row: QualityRequirementLink) -> dict[str, Any]:
    return {"id": str(row.id), "from_node_id": str(row.from_node_id), "to_node_id": str(row.to_node_id), "relationship": row.relationship, "rationale": row.rationale, "evidence_references": row.evidence_references or [], "created_at": row.created_at}


_DEFAULT_RULES = [
    ("PROGRAMME_COMPLETION_LOW", "Audit programme completion below 80%", "PROGRAMME_COMPLETION_RATE", "LT", Decimal("80"), "WARNING", "The approved/active audit programme completion rate is below 80%. Review outstanding governed requirements before changing the programme."),
    ("PROGRAMME_DEFERRAL_HIGH", "Audit programme deferral above 10%", "PROGRAMME_DEFERRAL_RATE", "GT", Decimal("10"), "WARNING", "More than 10% of approved/active programme requirements are deferred. Review attributable deferral reasons and surveillance exposure."),
    ("OVERDUE_CARS_PRESENT", "Overdue corrective actions present", "OVERDUE_CAR_COUNT", "GT", Decimal("0"), "WARNING", "At least one open CAR is past its due date."),
    ("INEFFECTIVE_ACTIONS_HIGH", "Ineffective action rate above 10%", "INEFFECTIVE_ACTION_RATE", "GT", Decimal("10"), "CRITICAL", "More than 10% of concluded effectiveness tests are ineffective or only partially effective."),
    ("AUDITOR_COVERAGE_GAP", "Auditor privilege coverage gap", "AUDITOR_CAPACITY_EXCEPTIONS", "GT", Decimal("0"), "WARNING", "At least one active auditor/lead-auditor privilege rule has no active authorized person."),
]


@router.get("/signal-rules")
def list_signal_rules(ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = db.query(QualitySignalRule).filter(QualitySignalRule.amo_id == ctx.amo_id).order_by(QualitySignalRule.rule_code.asc()).all()
    return {"items": [_rule_dict(row) for row in rows]}


@router.post("/signal-rules/defaults")
def configure_default_signal_rules(ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.reports.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    created = 0
    for code, title, metric, operator, threshold, severity, explanation in _DEFAULT_RULES:
        if db.query(QualitySignalRule.id).filter(QualitySignalRule.amo_id == ctx.amo_id, QualitySignalRule.rule_code == code).first():
            continue
        db.add(QualitySignalRule(amo_id=ctx.amo_id, rule_code=code, title=title, metric=metric, operator=operator, threshold=threshold, severity=severity, explanation=explanation, source_contract={"authoritative": True, "metric": metric, "calculation": "deterministic"}, created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id))
        created += 1
    db.commit()
    return {"created": created, "configured": len(_DEFAULT_RULES)}


@router.post("/signal-rules", status_code=status.HTTP_201_CREATED)
def create_signal_rule(payload: SignalRuleCreate, ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.reports.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    code = payload.rule_code.strip().upper()
    if db.query(QualitySignalRule.id).filter(QualitySignalRule.amo_id == ctx.amo_id, QualitySignalRule.rule_code == code).first():
        raise HTTPException(status_code=409, detail="A signal rule with this code already exists.")
    row = QualitySignalRule(amo_id=ctx.amo_id, rule_code=code, title=payload.title.strip(), metric=payload.metric, operator=payload.operator, threshold=payload.threshold, severity=payload.severity, explanation=payload.explanation.strip(), source_contract=payload.source_contract, created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id)
    db.add(row); db.commit(); db.refresh(row)
    return _rule_dict(row)


@router.post("/signals/evaluate")
def evaluate_signals(ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.reports.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rules = db.query(QualitySignalRule).filter(QualitySignalRule.amo_id == ctx.amo_id, QualitySignalRule.is_active.is_(True)).all()
    as_of = _utcnow(); observations = []
    for rule in rules:
        value, snapshot, references = _metric_snapshot(db, ctx.amo_id, rule.metric, as_of)
        threshold = Decimal(str(rule.threshold)); triggered = _compare(value, rule.operator, threshold)
        explanation = f"{rule.title}: observed {value} {rule.operator} threshold {threshold}. {rule.explanation}"
        row = QualitySignalObservation(amo_id=ctx.amo_id, rule_id=rule.id, metric=rule.metric, observed_value=value, threshold=threshold, operator=rule.operator, triggered=triggered, severity=rule.severity, explanation=explanation, source_snapshot=snapshot, source_references=references, as_of=as_of, state="OPEN" if triggered else "CLOSED", observed_by_user_id=ctx.user_id)
        db.add(row); db.flush()
        observations.append({"id": str(row.id), "rule_code": rule.rule_code, "metric": rule.metric, "value": float(value), "threshold": float(threshold), "operator": rule.operator, "triggered": triggered, "severity": rule.severity, "explanation": explanation, "source_snapshot": snapshot, "as_of": as_of})
    db.commit()
    return {"as_of": as_of, "evaluated": len(observations), "triggered": sum(1 for item in observations if item["triggered"]), "observations": observations}


@router.get("/signals")
def list_signals(triggered_only: bool = True, limit: int = Query(default=100, ge=1, le=500), ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualitySignalObservation).filter(QualitySignalObservation.amo_id == ctx.amo_id)
    if triggered_only:
        query = query.filter(QualitySignalObservation.triggered.is_(True))
    rows = query.order_by(QualitySignalObservation.observed_at.desc()).limit(limit).all()
    return {"items": [{"id": str(row.id), "rule_id": str(row.rule_id), "metric": row.metric, "observed_value": float(row.observed_value), "threshold": float(row.threshold), "operator": row.operator, "triggered": row.triggered, "severity": row.severity, "explanation": row.explanation, "source_snapshot": row.source_snapshot, "source_references": row.source_references, "as_of": row.as_of, "state": row.state} for row in rows]}


@router.get("/approval-graph")
def approval_graph(node_type: NodeType | None = None, state: SupportState | None = None, ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityRequirementNode).filter(QualityRequirementNode.amo_id == ctx.amo_id)
    if node_type:
        query = query.filter(QualityRequirementNode.node_type == node_type)
    if state:
        query = query.filter(QualityRequirementNode.support_state == state)
    nodes = query.order_by(QualityRequirementNode.node_type.asc(), QualityRequirementNode.title.asc()).limit(2000).all()
    ids = [row.id for row in nodes]
    links = db.query(QualityRequirementLink).filter(QualityRequirementLink.amo_id == ctx.amo_id, QualityRequirementLink.from_node_id.in_(ids)).limit(5000).all() if ids else []
    return {"nodes": [_node_dict(row) for row in nodes], "links": [_link_dict(row) for row in links]}


@router.post("/approval-graph/nodes", status_code=status.HTTP_201_CREATED)
def create_requirement_node(payload: RequirementNodeCreate, ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.settings.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    existing = db.query(QualityRequirementNode).filter(QualityRequirementNode.amo_id == ctx.amo_id, QualityRequirementNode.node_type == payload.node_type, QualityRequirementNode.source_owner_module == payload.source_owner_module, QualityRequirementNode.source_type == payload.source_type, QualityRequirementNode.source_id == payload.source_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="This authoritative source is already represented in the approval impact graph.")
    row = QualityRequirementNode(amo_id=ctx.amo_id, node_type=payload.node_type, title=payload.title.strip(), source_owner_module=payload.source_owner_module.strip(), source_type=payload.source_type.strip(), source_id=payload.source_id.strip(), source_route=payload.source_route, support_state=payload.support_state, state_reason=payload.state_reason.strip(), source_snapshot=payload.source_snapshot, evidence_as_of=payload.evidence_as_of, created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id)
    db.add(row); db.commit(); db.refresh(row)
    return _node_dict(row)


@router.post("/approval-graph/links", status_code=status.HTTP_201_CREATED)
def create_requirement_link(payload: RequirementLinkCreate, ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.settings.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    nodes = db.query(QualityRequirementNode.id).filter(QualityRequirementNode.amo_id == ctx.amo_id, QualityRequirementNode.id.in_([payload.from_node_id, payload.to_node_id])).all()
    if len({str(row[0]) for row in nodes}) != 2:
        raise HTTPException(status_code=422, detail="Both graph nodes must exist in the same AMO tenant.")
    if payload.from_node_id == payload.to_node_id:
        raise HTTPException(status_code=422, detail="A graph node cannot link to itself.")
    if db.query(QualityRequirementLink.id).filter(QualityRequirementLink.amo_id == ctx.amo_id, QualityRequirementLink.from_node_id == payload.from_node_id, QualityRequirementLink.to_node_id == payload.to_node_id, QualityRequirementLink.relationship == payload.relationship).first():
        raise HTTPException(status_code=409, detail="This impact relationship already exists and is immutable.")
    row = QualityRequirementLink(amo_id=ctx.amo_id, from_node_id=payload.from_node_id, to_node_id=payload.to_node_id, relationship=payload.relationship, rationale=payload.rationale.strip(), evidence_references=payload.evidence_references, created_by_user_id=ctx.user_id)
    db.add(row); db.commit(); db.refresh(row)
    return _link_dict(row)


@router.get("/approval-digital-twin")
def approval_digital_twin(ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")), db: Session = Depends(get_read_db)) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    nodes = db.query(QualityRequirementNode).filter(QualityRequirementNode.amo_id == ctx.amo_id).limit(5000).all()
    counts = Counter(row.support_state for row in nodes)
    overall = next((state for state in ["BLOCKED", "UNSUPPORTED", "STALE", "UNRESOLVED", "SUPPORTED"] if counts.get(state, 0)), "UNRESOLVED")
    blockers = [{"id": str(row.id), "node_type": row.node_type, "title": row.title, "support_state": row.support_state, "state_reason": row.state_reason, "source_route": row.source_route} for row in nodes if row.support_state != "SUPPORTED"]
    return {"as_of": _utcnow(), "assurance_state": overall, "is_compliance_declaration": False, "state_counts": dict(counts), "blockers": blockers[:500], "explanation": "This is an evidence-support/readiness view. It does not declare regulatory compliance; each state must be traced to authoritative source evidence."}
