from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db

from .mission_models import QualityMission, QualityMissionDecision, QualityMissionGate
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/missions", tags=["Quality missions"])

MissionType = Literal[
    "CAPABILITY_ADDITION",
    "CAPABILITY_CHANGE",
    "LINE_STATION",
    "SUPPLIER_APPROVAL",
    "SUBCONTRACTOR_APPROVAL",
    "REGULATORY_TRANSITION",
    "AMO_RENEWAL",
    "AUTHORIZATION_CAMPAIGN",
    "PROCEDURE_CHANGE",
    "IMPROVEMENT",
]
MissionStatus = Literal[
    "DRAFT",
    "PLANNING",
    "IN_PROGRESS",
    "GATE_REVIEW",
    "READY_FOR_APPROVAL",
    "APPROVED",
    "SUBMITTED_TO_AUTHORITY",
    "COMPLETE",
    "CANCELLED",
]
MissionRisk = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
GateStatus = Literal["PENDING", "IN_PROGRESS", "PASS", "FAIL", "BLOCKED"]
EvidenceStatus = Literal["UNLINKED", "LINKED", "VERIFIED", "REJECTED", "EXPIRED"]
DecisionType = Literal[
    "QUALITY_SELF_EVALUATION",
    "ACCOUNTABLE_EXECUTIVE",
    "AUTHORITY_SUBMISSION",
    "AUTHORITY_ACCEPTANCE",
    "CUSTOM",
]
DecisionStatus = Literal["APPROVED", "REJECTED", "RETURNED"]


class MissionCreate(BaseModel):
    mission_type: MissionType
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    regulatory_basis: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_level: MissionRisk = "MEDIUM"
    owner_user_id: str | None = Field(default=None, max_length=36)
    sponsor_user_id: str | None = Field(default=None, max_length=36)
    target_date: date | None = None


class GatePatch(BaseModel):
    status: GateStatus | None = None
    source_owner_module: str | None = Field(default=None, max_length=80)
    source_type: str | None = Field(default=None, max_length=48)
    source_id: str | None = Field(default=None, max_length=160)
    source_route: str | None = Field(default=None, max_length=500)
    source_snapshot: dict[str, Any] | None = None
    evidence_status: EvidenceStatus | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None
    blocking_reason: str | None = None


class MissionDecisionCreate(BaseModel):
    decision_type: DecisionType
    status: DecisionStatus
    rationale: str = Field(min_length=3)


CAPABILITY_ADDITION_GATE_TEMPLATE: tuple[dict[str, Any], ...] = (
    {
        "gate_code": "APPROVAL_RATING",
        "title": "Approval / rating",
        "category": "Approval",
        "requirement_ref": "Capability self-evaluation: approved rating and limitations",
        "source_owner_module": "quality",
        "source_type": "APPROVAL",
        "sort_order": 10,
    },
    {
        "gate_code": "FACILITIES",
        "title": "Facilities and housing",
        "category": "Facilities",
        "requirement_ref": "Capability self-evaluation: suitable facilities and housing",
        "source_owner_module": "facilities",
        "source_type": "FACILITY",
        "sort_order": 20,
    },
    {
        "gate_code": "TECHNICAL_DATA",
        "title": "Current technical data",
        "category": "Technical data",
        "requirement_ref": "Capability self-evaluation: current approved technical data",
        "source_owner_module": "document-control",
        "source_type": "DOCUMENT",
        "sort_order": 30,
    },
    {
        "gate_code": "TOOLING",
        "title": "Tooling and test equipment",
        "category": "Tooling",
        "requirement_ref": "Capability self-evaluation: required serviceable tooling and equipment",
        "source_owner_module": "tooling",
        "source_type": "EQUIPMENT",
        "sort_order": 40,
    },
    {
        "gate_code": "MATERIALS",
        "title": "Materials and parts support",
        "category": "Materials",
        "requirement_ref": "Capability self-evaluation: required materials and parts support",
        "source_owner_module": "stores",
        "source_type": "MATERIAL_READINESS",
        "sort_order": 50,
    },
    {
        "gate_code": "PERSONNEL",
        "title": "Qualified personnel",
        "category": "People",
        "requirement_ref": "Capability self-evaluation: qualified and authorized personnel",
        "source_owner_module": "people",
        "source_type": "PERSONNEL_COVERAGE",
        "sort_order": 60,
    },
    {
        "gate_code": "TRAINING",
        "title": "Training and competence evidence",
        "category": "People",
        "requirement_ref": "Capability self-evaluation: current training and competence evidence",
        "source_owner_module": "training",
        "source_type": "TRAINING",
        "sort_order": 70,
    },
    {
        "gate_code": "PROCEDURES",
        "title": "Approved procedures",
        "category": "Procedures",
        "requirement_ref": "Capability self-evaluation: applicable approved procedures",
        "source_owner_module": "document-control",
        "source_type": "DOCUMENT",
        "sort_order": 80,
    },
    {
        "gate_code": "CONTRACTED_FUNCTIONS",
        "title": "Contracted functions and specialist support",
        "category": "External support",
        "requirement_ref": "Capability self-evaluation: approved contracted functions and specialist support",
        "source_owner_module": "procurement",
        "source_type": "CONTRACTED_SERVICE",
        "sort_order": 90,
    },
    {
        "gate_code": "MANPOWER",
        "title": "Manpower and competent coverage",
        "category": "Resources",
        "requirement_ref": "Capability self-evaluation: adequate competent manpower for planned work",
        "source_owner_module": "rostering",
        "source_type": "MANPOWER_COVERAGE",
        "sort_order": 100,
    },
    {
        "gate_code": "SAFETY_CHANGE_ASSESSMENT",
        "title": "Safety / change assessment",
        "category": "Change assurance",
        "requirement_ref": "Capability self-evaluation: change risk assessed and accepted",
        "source_owner_module": "safety",
        "source_type": "CHANGE_ASSESSMENT",
        "sort_order": 110,
    },
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mission_ref() -> str:
    """Generate a non-sequential collision-resistant reference without count+1 races."""
    return f"MSN-{_utcnow().year % 100:02d}-{uuid.uuid4().hex[:8].upper()}"


def _gate_dict(gate: QualityMissionGate) -> dict[str, Any]:
    return {
        "id": str(gate.id),
        "gate_code": gate.gate_code,
        "title": gate.title,
        "category": gate.category,
        "description": gate.description,
        "gate_type": gate.gate_type,
        "status": gate.status,
        "requirement_ref": gate.requirement_ref,
        "source_owner_module": gate.source_owner_module,
        "source_type": gate.source_type,
        "source_id": gate.source_id,
        "source_route": gate.source_route,
        "source_snapshot": gate.source_snapshot,
        "evidence_status": gate.evidence_status,
        "owner_user_id": gate.owner_user_id,
        "due_date": gate.due_date,
        "blocking_reason": gate.blocking_reason,
        "sort_order": gate.sort_order,
        "passed_at": gate.passed_at,
        "passed_by_user_id": gate.passed_by_user_id,
        "updated_at": gate.updated_at,
    }


def _decision_dict(decision: QualityMissionDecision) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "decision_type": decision.decision_type,
        "status": decision.status,
        "rationale": decision.rationale,
        "evidence_snapshot": decision.evidence_snapshot,
        "decided_by_user_id": decision.decided_by_user_id,
        "decided_at": decision.decided_at,
    }


def mission_readiness(gates: list[QualityMissionGate]) -> dict[str, Any]:
    hard = [gate for gate in gates if gate.gate_type == "HARD"]
    soft = [gate for gate in gates if gate.gate_type == "SOFT"]
    hard_passed = sum(1 for gate in hard if gate.status == "PASS")
    soft_passed = sum(1 for gate in soft if gate.status == "PASS")
    blockers = [
        {
            "id": str(gate.id),
            "gate_code": gate.gate_code,
            "title": gate.title,
            "status": gate.status,
            "evidence_status": gate.evidence_status,
            "blocking_reason": gate.blocking_reason,
        }
        for gate in hard
        if gate.status != "PASS"
    ]
    return {
        "hard_gates": {"passed": hard_passed, "total": len(hard)},
        "soft_gates": {"passed": soft_passed, "total": len(soft)},
        "ready_for_quality_self_evaluation": bool(hard) and hard_passed == len(hard),
        "blocking_gates": blockers,
    }


def _mission_dict(mission: QualityMission, *, include_detail: bool = False) -> dict[str, Any]:
    gates = list(mission.gates or [])
    result: dict[str, Any] = {
        "id": str(mission.id),
        "mission_ref": mission.mission_ref,
        "mission_type": mission.mission_type,
        "title": mission.title,
        "description": mission.description,
        "scope": mission.scope,
        "regulatory_basis": mission.regulatory_basis,
        "risk_level": mission.risk_level,
        "status": mission.status,
        "owner_user_id": mission.owner_user_id,
        "requested_by_user_id": mission.requested_by_user_id,
        "sponsor_user_id": mission.sponsor_user_id,
        "requested_at": mission.requested_at,
        "target_date": mission.target_date,
        "started_at": mission.started_at,
        "approved_at": mission.approved_at,
        "completed_at": mission.completed_at,
        "created_at": mission.created_at,
        "updated_at": mission.updated_at,
        "readiness": mission_readiness(gates),
    }
    if include_detail:
        result["gates"] = [_gate_dict(gate) for gate in gates]
        result["decisions"] = [_decision_dict(item) for item in list(mission.decisions or [])]
    return result


def _mission_query(db: Session, *, amo_id: str):
    return db.query(QualityMission).filter(QualityMission.amo_id == amo_id)


def _load_mission(db: Session, *, amo_id: str, mission_id: str, for_update: bool = False) -> QualityMission:
    query = (
        _mission_query(db, amo_id=amo_id)
        .options(selectinload(QualityMission.gates), selectinload(QualityMission.decisions))
        .filter(QualityMission.id == mission_id)
    )
    if for_update:
        query = query.with_for_update()
    mission = query.first()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quality Mission not found.")
    return mission


def _latest_decision(mission: QualityMission, decision_type: str) -> QualityMissionDecision | None:
    matches = [item for item in mission.decisions if item.decision_type == decision_type]
    if not matches:
        return None
    return max(matches, key=lambda item: (item.decided_at or item.created_at, item.created_at))


def assert_mission_decision_allowed(mission: QualityMission, payload: MissionDecisionCreate) -> None:
    if mission.status in {"COMPLETE", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mission decisions are immutable after {mission.status}.",
        )
    if payload.decision_type == "CUSTOM":
        return

    readiness = mission_readiness(list(mission.gates or []))
    if payload.decision_type == "QUALITY_SELF_EVALUATION" and payload.status == "APPROVED":
        if not readiness["ready_for_quality_self_evaluation"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Quality self-evaluation cannot be approved until every HARD readiness gate has passed.",
            )

    prerequisites: dict[str, tuple[str, str]] = {
        "ACCOUNTABLE_EXECUTIVE": ("QUALITY_SELF_EVALUATION", "Quality self-evaluation"),
        "AUTHORITY_SUBMISSION": ("ACCOUNTABLE_EXECUTIVE", "Accountable Executive approval"),
        "AUTHORITY_ACCEPTANCE": ("AUTHORITY_SUBMISSION", "Authority submission decision"),
    }
    prerequisite = prerequisites.get(payload.decision_type)
    if prerequisite:
        prior_type, label = prerequisite
        prior = _latest_decision(mission, prior_type)
        if not prior or prior.status != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{payload.decision_type.replace('_', ' ').title()} requires an APPROVED {label} first.",
            )

    required_state = {
        "QUALITY_SELF_EVALUATION": "GATE_REVIEW",
        "ACCOUNTABLE_EXECUTIVE": "READY_FOR_APPROVAL",
        "AUTHORITY_SUBMISSION": "APPROVED",
        "AUTHORITY_ACCEPTANCE": "SUBMITTED_TO_AUTHORITY",
    }[payload.decision_type]
    if mission.status != required_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{payload.decision_type.replace('_', ' ').title()} requires Mission state {required_state}.",
        )

    if payload.decision_type == "QUALITY_SELF_EVALUATION" and payload.status == "APPROVED":
        return


def _decision_evidence_snapshot(mission: QualityMission) -> dict[str, Any]:
    return {
        "mission_ref": mission.mission_ref,
        "mission_type": mission.mission_type,
        "readiness": mission_readiness(list(mission.gates or [])),
        "gates": [
            {
                "gate_code": gate.gate_code,
                "status": gate.status,
                "evidence_status": gate.evidence_status,
                "source_type": gate.source_type,
                "source_id": gate.source_id,
                "source_route": gate.source_route,
                "updated_at": gate.updated_at.isoformat() if gate.updated_at else None,
            }
            for gate in mission.gates
        ],
        "captured_at": _utcnow().isoformat(),
    }


def _apply_decision_to_mission(mission: QualityMission, payload: MissionDecisionCreate) -> None:
    if payload.status in {"REJECTED", "RETURNED"}:
        if payload.decision_type in {"QUALITY_SELF_EVALUATION", "ACCOUNTABLE_EXECUTIVE"}:
            mission.status = "IN_PROGRESS"
        return

    if payload.decision_type == "QUALITY_SELF_EVALUATION":
        mission.status = "READY_FOR_APPROVAL"
    elif payload.decision_type == "ACCOUNTABLE_EXECUTIVE":
        mission.status = "APPROVED"
        mission.approved_at = _utcnow()
    elif payload.decision_type == "AUTHORITY_SUBMISSION":
        mission.status = "SUBMITTED_TO_AUTHORITY"
    elif payload.decision_type == "AUTHORITY_ACCEPTANCE":
        mission.status = "COMPLETE"
        mission.completed_at = _utcnow()


@router.get("/templates")
def mission_templates(
    ctx: TenantContext = Depends(require_quality_permission("qms.change.view")),
) -> dict[str, Any]:
    return {
        "items": [
            {
                "mission_type": "CAPABILITY_ADDITION",
                "label": "Aircraft / capability inclusion",
                "description": "Govern the readiness evidence and approval chain for adding an aircraft, article or maintenance capability.",
                "hard_gates": [dict(item) for item in CAPABILITY_ADDITION_GATE_TEMPLATE],
            }
        ],
        "tenant": {"amo_code": ctx.amo_code},
    }


@router.get("")
def list_missions(
    mission_type: MissionType | None = None,
    status_filter: MissionStatus | None = Query(default=None, alias="status"),
    owner_user_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_quality_permission("qms.change.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = _mission_query(db, amo_id=ctx.amo_id).options(selectinload(QualityMission.gates))
    if mission_type:
        query = query.filter(QualityMission.mission_type == mission_type)
    if status_filter:
        query = query.filter(QualityMission.status == status_filter)
    if owner_user_id:
        query = query.filter(QualityMission.owner_user_id == owner_user_id)

    total = int(query.order_by(None).count())
    rows = (
        query.order_by(QualityMission.target_date.asc().nullslast(), QualityMission.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_mission_dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }


@router.get("/{mission_id}")
def get_mission(
    mission_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)
