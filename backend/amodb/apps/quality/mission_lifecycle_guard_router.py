from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from .mission_models import QualityMissionDecision
from .mission_router import (
    MissionDecisionCreate,
    _apply_decision_to_mission,
    _decision_evidence_snapshot,
    _load_mission,
    _mission_dict,
    _utcnow,
    assert_mission_decision_allowed,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/missions", tags=["Quality mission lifecycle"])


def assert_mission_actor_allowed(mission, payload: MissionDecisionCreate, actor_user_id: str) -> None:
    """Bind governed decisions to the named Mission role.

    Generic qms.change.manage permission is necessary but not sufficient for an
    attributable approval. The Mission owner records Quality/authority workflow
    decisions; the explicitly assigned sponsor records the Accountable Executive
    decision. This prevents a Quality administrator from silently impersonating
    the executive approval role.
    """

    if payload.decision_type == "ACCOUNTABLE_EXECUTIVE":
        if not mission.sponsor_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assign the Mission Accountable Executive before recording an executive decision.",
            )
        if str(mission.sponsor_user_id) != str(actor_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Accountable Executive assigned to this Mission may record this decision.",
            )
        return

    if payload.decision_type in {"QUALITY_SELF_EVALUATION", "AUTHORITY_SUBMISSION", "AUTHORITY_ACCEPTANCE"}:
        if not mission.owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assign a Quality Mission owner before recording this decision.",
            )
        if str(mission.owner_user_id) != str(actor_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned Quality Mission owner may record this decision.",
            )


@router.post("/{mission_id}/decisions", status_code=status.HTTP_201_CREATED)
def record_governed_mission_decision(
    mission_id: str,
    payload: MissionDecisionCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.manage")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    mission = _load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id, for_update=True)
    assert_mission_actor_allowed(mission, payload, ctx.user_id)
    assert_mission_decision_allowed(mission, payload)

    now = _utcnow()
    decision = QualityMissionDecision(
        amo_id=ctx.amo_id,
        mission_id=mission.id,
        decision_type=payload.decision_type,
        status=payload.status,
        rationale=payload.rationale.strip(),
        evidence_snapshot=_decision_evidence_snapshot(mission),
        decided_by_user_id=ctx.user_id,
        decided_at=now,
        created_at=now,
    )
    db.add(decision)
    _apply_decision_to_mission(mission, payload)
    mission.updated_by_user_id = ctx.user_id
    mission.updated_at = now
    db.commit()

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)
