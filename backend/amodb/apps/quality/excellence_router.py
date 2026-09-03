from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from .excellence_models import QualityIntelligenceReview
from .tenant_security import (
    TenantContext,
    require_quality_permission,
    set_postgres_tenant_context,
)


router = APIRouter(prefix="/excellence", tags=["Quality excellence"])

InsightStatus = Literal["PROPOSED", "ACCEPTED", "DISMISSED", "IMPLEMENTED"]
RiskLevel = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


class IntelligenceDecision(BaseModel):
    status: InsightStatus
    note: str | None = None


class IntelligenceManualCreate(BaseModel):
    insight_type: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=3, max_length=255)
    rationale: str = Field(min_length=3)
    recommendation: str | None = None
    risk_level: RiskLevel = "MEDIUM"
    payload: dict[str, Any] = Field(default_factory=dict)
    source_fingerprint: str = Field(min_length=3, max_length=160)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _score_readiness(metrics: dict[str, int]) -> dict[str, Any]:
    """Return a transparent, deterministic readiness score.

    This is not a compliance declaration. It is an operational pressure model
    whose deductions remain visible to the user and can be challenged during
    management review.
    """

    dimensions = {
        "audit_programme": _clamp_score(
            100
            - metrics.get("overdue_audits", 0) * 18
            - metrics.get("audits_due_30", 0) * 2
        ),
        "capa_discipline": _clamp_score(
            100
            - metrics.get("overdue_cars", 0) * 14
            - max(0, metrics.get("open_cars", 0) - metrics.get("overdue_cars", 0)) * 2
        ),
        "finding_control": _clamp_score(100 - metrics.get("open_findings", 0) * 4),
        "document_currency": _clamp_score(
            50
            if metrics.get("active_documents", 0) + metrics.get("draft_documents", 0) == 0
            else (
                metrics.get("active_documents", 0)
                / max(1, metrics.get("active_documents", 0) + metrics.get("draft_documents", 0))
                * 100
            )
        ),
        "competence": _clamp_score(100 - metrics.get("expired_training", 0) * 10),
        "continuous_controls": _clamp_score(
            35
            if metrics.get("active_controls", 0) == 0
            else (
                metrics.get("verified_controls", 0)
                / max(1, metrics.get("active_controls", 0))
                * 100
                - metrics.get("controls_due", 0) * 5
            )
        ),
    }
    weights = {
        "audit_programme": 0.20,
        "capa_discipline": 0.25,
        "finding_control": 0.15,
        "document_currency": 0.15,
        "competence": 0.15,
        "continuous_controls": 0.10,
    }
    overall = _clamp_score(sum(dimensions[key] * weights[key] for key in weights))
    band = "STRONG" if overall >= 85 else "WATCH" if overall >= 70 else "AT_RISK" if overall >= 50 else "CRITICAL"
    return {
        "score": overall,
        "band": band,
        "dimensions": [
            {
                "id": key,
                "label": key.replace("_", " ").title(),
                "score": dimensions[key],
                "weight": weights[key],
            }
            for key in weights
        ],
        "method": "transparent_weighted_operational_pressure_v1",
        "disclaimer": "Readiness is an operational indicator, not a regulatory compliance declaration.",
    }


def _insight_dict(row: QualityIntelligenceReview) -> dict[str, Any]:
    return {
        "id": row.id,
        "insight_type": row.insight_type,
        "title": row.title,
        "rationale": row.rationale,
        "recommendation": row.recommendation,
        "payload": row.payload or {},
        "source_fingerprint": row.source_fingerprint,
        "risk_level": row.risk_level,
        "status": row.status,
        "created_by": row.created_by,
        "human_decision_by_user_id": row.human_decision_by_user_id,
        "human_decision_note": row.human_decision_note,
        "decision_at": row.decision_at.isoformat() if row.decision_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _scalar(
    db: Session,
    ctx: TenantContext,
    sql: str,
    params: dict[str, Any],
    warnings: list[dict[str, str]],
    source: str,
) -> int:
    try:
        value = db.execute(text(sql), params).scalar()
        return int(value or 0)
    except Exception as exc:
        db.rollback()
        set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
        warnings.append({"source": source, "message": str(exc), "type": exc.__class__.__name__})
        return 0


def _overview_metrics(db: Session, ctx: TenantContext) -> tuple[dict[str, int], list[dict[str, str]]]:
    today = date.today()
    due_30 = today + timedelta(days=30)
    params = {"amo_id": ctx.amo_id, "today": today, "due_30": due_30}
    warnings: list[dict[str, str]] = []
    queries = {
        "overdue_audits": """
            SELECT COUNT(*) FROM qms_audit_schedules
            WHERE amo_id = :amo_id AND is_active IS TRUE
              AND next_due_date IS NOT NULL AND next_due_date < :today
        """,
        "audits_due_30": """
            SELECT COUNT(*) FROM qms_audit_schedules
            WHERE amo_id = :amo_id AND is_active IS TRUE
              AND next_due_date BETWEEN :today AND :due_30
        """,
        "open_cars": """
            SELECT COUNT(*) FROM quality_cars
            WHERE amo_id = :amo_id AND status NOT IN ('CLOSED', 'CANCELLED')
        """,
        "overdue_cars": """
            SELECT COUNT(*) FROM quality_cars
            WHERE amo_id = :amo_id AND status NOT IN ('CLOSED', 'CANCELLED')
              AND due_date IS NOT NULL AND due_date < :today
        """,
        "cars_due_30": """
            SELECT COUNT(*) FROM quality_cars
            WHERE amo_id = :amo_id AND status NOT IN ('CLOSED', 'CANCELLED')
              AND due_date BETWEEN :today AND :due_30
        """,
        "open_findings": """
            SELECT COUNT(*) FROM qms_audit_findings
            WHERE amo_id = :amo_id AND closed_at IS NULL
        """,
        "active_documents": """
            SELECT COUNT(*) FROM qms_documents
            WHERE amo_id = :amo_id AND status = 'ACTIVE'
        """,
        "draft_documents": """
            SELECT COUNT(*) FROM qms_documents
            WHERE amo_id = :amo_id AND status = 'DRAFT'
        """,
        "expired_training": """
            SELECT COUNT(*) FROM (
                SELECT DISTINCT ON (user_id, course_id) user_id, course_id, valid_until
                FROM training_records
                WHERE amo_id = :amo_id AND valid_until IS NOT NULL
                  AND UPPER(CAST(verification_status AS TEXT)) = 'VERIFIED'
                  AND COALESCE(UPPER(NULLIF(record_status, '')), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')
                  AND COALESCE(UPPER(NULLIF(source_status, '')), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')
                ORDER BY user_id, course_id, completion_date DESC NULLS LAST,
                         created_at DESC NULLS LAST, id DESC
            ) latest WHERE valid_until < :today
        """,
        "active_controls": """
            SELECT COUNT(*) FROM quality_assurance_controls
            WHERE amo_id = :amo_id AND status = 'ACTIVE'
        """,
        "controls_due": """
            SELECT COUNT(*) FROM quality_assurance_controls
            WHERE amo_id = :amo_id AND status = 'ACTIVE'
              AND (next_test_due IS NULL OR next_test_due <= :due_30)
        """,
        "verified_controls": """
            SELECT COUNT(DISTINCT control_id)
            FROM quality_assurance_evidence_links
            WHERE amo_id = :amo_id AND evidence_status = 'VERIFIED'
              AND (valid_until IS NULL OR valid_until >= :today)
        """,
        "proposed_insights": """
            SELECT COUNT(*) FROM quality_intelligence_reviews
            WHERE amo_id = :amo_id AND status = 'PROPOSED'
        """,
    }
    metrics = {
        name: _scalar(db, ctx, sql, params, warnings, name)
        for name, sql in queries.items()
    }
    return metrics, warnings


def _priority_queue(metrics: dict[str, int], amo_code: str) -> list[dict[str, Any]]:
    candidates = [
        {
            "id": "overdue-cars",
            "label": "Overdue corrective actions",
            "count": metrics.get("overdue_cars", 0),
            "severity": "CRITICAL",
            "why": "Closure dates have passed while the CAR remains open.",
            "path": f"/maintenance/{amo_code}/quality/cars/overdue",
        },
        {
            "id": "overdue-audits",
            "label": "Overdue audit commitments",
            "count": metrics.get("overdue_audits", 0),
            "severity": "HIGH",
            "why": "The approved audit programme contains dates that have passed.",
            "path": f"/maintenance/{amo_code}/quality/audits/plan?view=calendar",
        },
        {
            "id": "controls-due",
            "label": "Controls needing evidence or retest",
            "count": metrics.get("controls_due", 0),
            "severity": "HIGH",
            "why": "Continuous controls have no future test date or fall due within 30 days.",
            "path": f"/maintenance/{amo_code}/quality?hub=controls",
        },
        {
            "id": "expired-training",
            "label": "Expired competence evidence",
            "count": metrics.get("expired_training", 0),
            "severity": "HIGH",
            "why": "The latest recorded course validity has expired.",
            "path": f"/maintenance/{amo_code}/training/competence/overdue",
        },
        {
            "id": "open-findings",
            "label": "Open findings",
            "count": metrics.get("open_findings", 0),
            "severity": "MEDIUM",
            "why": "Unclosed findings continue to consume assurance capacity.",
            "path": f"/maintenance/{amo_code}/quality/findings/register",
        },
        {
            "id": "draft-documents",
            "label": "Draft controlled documents",
            "count": metrics.get("draft_documents", 0),
            "severity": "MEDIUM",
            "why": "Draft procedures may indicate unfinished change or approval work.",
            "path": f"/maintenance/{amo_code}/quality/documents/approvals",
        },
        {
            "id": "insight-review",
            "label": "Quality intelligence awaiting review",
            "count": metrics.get("proposed_insights", 0),
            "severity": "INFO",
            "why": "Recommendations remain advisory until a named user decides them.",
            "path": f"/maintenance/{amo_code}/quality?hub=intelligence",
        },
    ]
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    return sorted(
        [item for item in candidates if item["count"] > 0],
        key=lambda item: (rank[item["severity"]], -item["count"]),
    )


@router.get("/overview")
def excellence_overview(
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, warnings = _overview_metrics(db, ctx)
    readiness = _score_readiness(metrics)
    pressure_30 = (
        metrics.get("audits_due_30", 0)
        + metrics.get("cars_due_30", 0)
        + metrics.get("controls_due", 0)
    )
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "as_of": _now().isoformat(),
        "readiness": readiness,
        "metrics": metrics,
        "priority_queue": _priority_queue(metrics, ctx.amo_code),
        "forecast": {
            "commitments_due_30_days": pressure_30,
            "band": "HEAVY" if pressure_30 >= 15 else "ELEVATED" if pressure_30 >= 7 else "MANAGEABLE",
            "explanation": "Audit dates, CAR due dates and assurance-control test dates falling within 30 days.",
        },
        "capabilities": [
            {
                "id": "control-twin",
                "label": "Control twin",
                "description": "A durable control record connecting regulation, process, owner, test cadence and evidence.",
                "path": f"/maintenance/{ctx.amo_code}/quality?hub=controls",
            },
            {
                "id": "evidence-graph",
                "label": "Evidence graph",
                "description": "Trace each control to documents, audits, findings, CAPA, competence and supplier evidence.",
                "path": f"/maintenance/{ctx.amo_code}/quality?hub=evidence",
            },
            {
                "id": "human-governed-intelligence",
                "label": "Human-governed intelligence",
                "description": "Recommendations enter a review queue and never alter regulated records automatically.",
                "path": f"/maintenance/{ctx.amo_code}/quality?hub=intelligence",
            },
        ],
        "warnings": warnings,
    }


@router.get("/insights")
def list_intelligence_reviews(
    status_filter: InsightStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityIntelligenceReview).filter(QualityIntelligenceReview.amo_id == ctx.amo_id)
    if status_filter:
        query = query.filter(QualityIntelligenceReview.status == status_filter)
    total = query.count()
    rows = query.order_by(QualityIntelligenceReview.created_at.desc()).limit(limit).all()
    return {"items": [_insight_dict(row) for row in rows], "total": total, "as_of": _now().isoformat()}


@router.post("/insights", status_code=status.HTTP_201_CREATED)
def create_manual_intelligence_review(
    payload: IntelligenceManualCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = QualityIntelligenceReview(
        amo_id=ctx.amo_id,
        insight_type=payload.insight_type.strip().upper(),
        title=payload.title.strip(),
        rationale=payload.rationale.strip(),
        recommendation=payload.recommendation,
        payload=payload.payload,
        source_fingerprint=payload.source_fingerprint.strip(),
        risk_level=payload.risk_level,
        status="PROPOSED",
        created_by="HUMAN",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An insight with this source fingerprint already exists.") from exc
    db.refresh(row)
    return _insight_dict(row)


def _rule_candidates(metrics: dict[str, int], today: date) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if metrics.get("overdue_cars", 0):
        candidates.append({
            "type": "CAPA_ESCALATION",
            "title": "Escalate overdue corrective-action exposure",
            "rationale": f"{metrics['overdue_cars']} CAR records are beyond their target closure date.",
            "recommendation": "Review accountable owners, extension decisions and containment sufficiency before the next management review.",
            "risk": "CRITICAL" if metrics["overdue_cars"] >= 5 else "HIGH",
            "fingerprint": f"rule:overdue-cars:{today.isoformat()}:{metrics['overdue_cars']}",
            "payload": {"count": metrics["overdue_cars"], "module": "cars"},
        })
    if metrics.get("overdue_audits", 0):
        candidates.append({
            "type": "AUDIT_PROGRAMME_DRIFT",
            "title": "Recover the approved audit programme",
            "rationale": f"{metrics['overdue_audits']} active audit schedules have passed their next due date.",
            "recommendation": "Reschedule with documented justification or issue the audit into fieldwork; do not silently move the programme date.",
            "risk": "HIGH",
            "fingerprint": f"rule:overdue-audits:{today.isoformat()}:{metrics['overdue_audits']}",
            "payload": {"count": metrics["overdue_audits"], "module": "audits"},
        })
    if metrics.get("expired_training", 0):
        candidates.append({
            "type": "COMPETENCE_RISK",
            "title": "Resolve expired competence evidence",
            "rationale": f"{metrics['expired_training']} latest training records are expired.",
            "recommendation": "Confirm role impact, restrict affected authorisations where required and schedule renewal evidence.",
            "risk": "HIGH",
            "fingerprint": f"rule:expired-training:{today.isoformat()}:{metrics['expired_training']}",
            "payload": {"count": metrics["expired_training"], "module": "training"},
        })
    if metrics.get("active_controls", 0) == 0:
        candidates.append({
            "type": "CONTROL_LIBRARY_GAP",
            "title": "Establish the continuous assurance control library",
            "rationale": "No active durable controls are registered, so compliance evidence remains tied only to isolated audits and records.",
            "recommendation": "Start with critical Part-145, authority, exposition and internal-process obligations, then link current evidence.",
            "risk": "MEDIUM",
            "fingerprint": f"rule:no-controls:{today.isoformat()}",
            "payload": {"count": 0, "module": "controls"},
        })
    elif metrics.get("controls_due", 0):
        candidates.append({
            "type": "CONTROL_TEST_DUE",
            "title": "Retest controls with ageing assurance evidence",
            "rationale": f"{metrics['controls_due']} controls have no future test date or fall due within 30 days.",
            "recommendation": "Assign evidence owners and verify operating effectiveness before the due date.",
            "risk": "HIGH" if metrics["controls_due"] >= 10 else "MEDIUM",
            "fingerprint": f"rule:controls-due:{today.isoformat()}:{metrics['controls_due']}",
            "payload": {"count": metrics["controls_due"], "module": "controls"},
        })
    return candidates


@router.post("/insights/rebuild")
def rebuild_rule_engine_insights(
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, warnings = _overview_metrics(db, ctx)
    generated: list[QualityIntelligenceReview] = []
    skipped = 0
    for candidate in _rule_candidates(metrics, date.today()):
        exists = (
            db.query(QualityIntelligenceReview.id)
            .filter(
                QualityIntelligenceReview.amo_id == ctx.amo_id,
                QualityIntelligenceReview.source_fingerprint == candidate["fingerprint"],
            )
            .first()
        )
        if exists:
            skipped += 1
            continue
        row = QualityIntelligenceReview(
            amo_id=ctx.amo_id,
            insight_type=candidate["type"],
            title=candidate["title"],
            rationale=candidate["rationale"],
            recommendation=candidate["recommendation"],
            payload=candidate["payload"],
            source_fingerprint=candidate["fingerprint"],
            risk_level=candidate["risk"],
            status="PROPOSED",
            created_by="RULE_ENGINE",
        )
        db.add(row)
        generated.append(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        generated = []
        skipped += 1
    return {
        "generated": len(generated),
        "skipped_existing": skipped,
        "items": [_insight_dict(row) for row in generated],
        "warnings": warnings,
        "as_of": _now().isoformat(),
    }


@router.patch("/insights/{insight_id}")
def decide_intelligence_review(
    insight_id: str,
    payload: IntelligenceDecision,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = (
        db.query(QualityIntelligenceReview)
        .filter(
            QualityIntelligenceReview.id == insight_id,
            QualityIntelligenceReview.amo_id == ctx.amo_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality intelligence item not found.")
    row.status = payload.status
    row.human_decision_by_user_id = ctx.user_id
    row.human_decision_note = payload.note
    row.decision_at = _now()
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _insight_dict(row)
