from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from .assurance_case_models import QualityAssuranceCase, QualityEffectivenessPlan
from .audit_programme_models import QualityAuditProgrammeItem, QualityAuditUniverseItem
from .excellence_models import (
    QualityAssuranceControl,
    QualityAssuranceEvidenceLink,
    QualityControlTest,
    QualityIntelligenceReview,
)
from .people_models import QualityPrivilege
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/intelligence", tags=["Quality intelligence"])

_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _factor(code: str, label: str, value: Any, *, hard: bool, source: str, rule: str) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "value": value,
        "hard_requirement": hard,
        "source": source,
        "rule": rule,
    }


def _surveillance_item(row: QualityAuditUniverseItem, programme_states: dict[str, list[str]]) -> dict[str, Any]:
    states = programme_states.get(str(row.id), [])
    factors: list[dict[str, Any]] = []
    if row.mandatory_surveillance:
        factors.append(_factor(
            "MANDATORY_SURVEILLANCE",
            "Mandatory surveillance requirement",
            True,
            hard=True,
            source=f"audit-universe:{row.id}",
            rule="Mandatory surveillance is always ranked ahead of discretionary risk factors and is never averaged away.",
        ))
    if row.regulatory_criticality in {"HIGH", "CRITICAL"}:
        factors.append(_factor(
            "REGULATORY_CRITICALITY",
            "Regulatory criticality",
            row.regulatory_criticality,
            hard=False,
            source=f"audit-universe:{row.id}",
            rule="HIGH and CRITICAL regulatory criticality increase surveillance priority.",
        ))
    if row.risk_classification in {"HIGH", "CRITICAL"}:
        factors.append(_factor(
            "RISK_CLASSIFICATION",
            "Governed audit-universe risk classification",
            row.risk_classification,
            hard=False,
            source=f"audit-universe:{row.id}",
            rule="HIGH and CRITICAL governed risk classifications increase surveillance priority.",
        ))
    if "DEFERRED" in states:
        factors.append(_factor(
            "DEFERRED_REQUIREMENT",
            "Programme requirement has been deferred",
            states.count("DEFERRED"),
            hard=False,
            source=f"audit-programme-item:universe:{row.id}",
            rule="A deferred governed requirement is surfaced because repeated deferral increases assurance exposure.",
        ))
    if states and not any(state in {"SCHEDULED", "COMPLETED"} for state in states):
        factors.append(_factor(
            "UNSCHEDULED_REQUIREMENT",
            "Programme requirement is not scheduled or completed",
            states,
            hard=False,
            source=f"audit-programme-item:universe:{row.id}",
            rule="Existing programme requirements with no scheduled/completed state are surfaced for planning attention.",
        ))

    priority = (
        1000 if row.mandatory_surveillance else 0
    ) + (_RANK.get(row.regulatory_criticality, 0) * 100) + (_RANK.get(row.risk_classification, 0) * 10) + (5 if "DEFERRED" in states else 0)
    return {
        "universe_item_id": str(row.id),
        "label": row.display_label,
        "entity_type": row.entity_type,
        "source_owner_module": row.source_owner_module,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_route": row.source_route,
        "mandatory_surveillance": bool(row.mandatory_surveillance),
        "risk_classification": row.risk_classification,
        "regulatory_criticality": row.regulatory_criticality,
        "surveillance_interval_days": row.surveillance_interval_days,
        "programme_states": states,
        "priority_order": priority,
        "factors": factors,
        "explanation": "Deterministic ordering only. This is not a predictive probability or automated compliance conclusion.",
    }


@router.get("/overview")
def intelligence_overview(
    surveillance_limit: int = Query(default=50, ge=1, le=150),
    ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()

    programme_rows = db.query(QualityAuditProgrammeItem.state).filter(QualityAuditProgrammeItem.amo_id == ctx.amo_id).all()
    programme_counts = {key: 0 for key in ("PLANNED", "SCHEDULED", "COMPLETED", "DEFERRED", "CANCELLED", "FOLLOW_UP_REQUIRED")}
    for (state,) in programme_rows:
        if state in programme_counts:
            programme_counts[state] += 1
    programme_total = sum(programme_counts.values())
    executable_total = programme_total - programme_counts["CANCELLED"]

    open_cases = db.query(QualityAssuranceCase).filter(
        QualityAssuranceCase.amo_id == ctx.amo_id,
        QualityAssuranceCase.status.notin_(["CLOSED", "CANCELLED"]),
    ).all()
    overdue_cases = sum(1 for row in open_cases if row.due_date and row.due_date < today)
    ineffective = db.query(QualityEffectivenessPlan).filter(
        QualityEffectivenessPlan.amo_id == ctx.amo_id,
        QualityEffectivenessPlan.conclusion.in_(["INEFFECTIVE", "PARTIALLY_EFFECTIVE", "INCONCLUSIVE"]),
    ).count()

    active_privileges = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.status == "ACTIVE").count()
    privilege_expiry = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.status == "ACTIVE",
        QualityPrivilege.expires_on.is_not(None),
        QualityPrivilege.expires_on >= today,
        QualityPrivilege.expires_on <= today + timedelta(days=60),
    ).count()

    overdue_controls = db.query(QualityAssuranceControl).filter(
        QualityAssuranceControl.amo_id == ctx.amo_id,
        QualityAssuranceControl.status == "ACTIVE",
        QualityAssuranceControl.next_test_due.is_not(None),
        QualityAssuranceControl.next_test_due < today,
    ).count()
    failed_control_tests = db.query(QualityControlTest).filter(
        QualityControlTest.amo_id == ctx.amo_id,
        QualityControlTest.result.in_(["FAIL", "PARTIAL"]),
    ).count()
    stale_evidence = db.query(QualityAssuranceEvidenceLink).filter(
        QualityAssuranceEvidenceLink.amo_id == ctx.amo_id,
        or_(
            QualityAssuranceEvidenceLink.evidence_status == "EXPIRED",
            QualityAssuranceEvidenceLink.valid_until < today,
        ),
    ).count()
    proposed_reviews = db.query(QualityIntelligenceReview).filter(
        QualityIntelligenceReview.amo_id == ctx.amo_id,
        QualityIntelligenceReview.status == "PROPOSED",
    ).count()

    programme_state_rows = db.query(
        QualityAuditProgrammeItem.universe_item_id,
        QualityAuditProgrammeItem.state,
    ).filter(QualityAuditProgrammeItem.amo_id == ctx.amo_id).all()
    programme_states: dict[str, list[str]] = {}
    for universe_id, state in programme_state_rows:
        programme_states.setdefault(str(universe_id), []).append(str(state))

    universe_rows = db.query(QualityAuditUniverseItem).filter(
        QualityAuditUniverseItem.amo_id == ctx.amo_id,
        QualityAuditUniverseItem.active.is_(True),
    ).limit(500).all()
    surveillance = [_surveillance_item(row, programme_states) for row in universe_rows]
    surveillance = [item for item in surveillance if item["factors"]]
    surveillance.sort(key=lambda item: (-int(item["priority_order"]), str(item["label"]).lower()))
    surveillance = surveillance[:surveillance_limit]

    def ratio(numerator: int, denominator: int) -> dict[str, Any]:
        return {
            "numerator": numerator,
            "denominator": denominator,
            "value": round(numerator / denominator, 4) if denominator else None,
        }

    return {
        "as_of": today,
        "programme": {
            "states": programme_counts,
            "completion": ratio(programme_counts["COMPLETED"], executable_total),
            "deferral_rate": ratio(programme_counts["DEFERRED"], executable_total),
            "calculation": "Completed or deferred programme requirements divided by non-cancelled governed requirements. Null when no denominator exists.",
        },
        "assurance": {
            "open_cases": len(open_cases),
            "overdue_cases": overdue_cases,
            "ineffective_or_inconclusive_reviews": ineffective,
        },
        "people": {
            "active_privileges": active_privileges,
            "expiring_within_60_days": privilege_expiry,
        },
        "controls": {
            "overdue_control_tests": overdue_controls,
            "failed_or_partial_test_records": failed_control_tests,
            "stale_or_expired_evidence_links": stale_evidence,
            "proposed_human_reviews": proposed_reviews,
        },
        "targeted_surveillance": surveillance,
        "method": {
            "type": "DETERMINISTIC_RULES",
            "statement": "No predictive or probabilistic risk score is generated. Mandatory surveillance remains a hard requirement; discretionary factors only order attention among auditable entities.",
        },
    }
