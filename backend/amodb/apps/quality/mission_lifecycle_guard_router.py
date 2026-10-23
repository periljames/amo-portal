from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from amodb.database import get_write_db, get_read_db

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


class MissionCancellation(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


def _authority_evidence(db, *, amo_id, asset_id=None, search=""):
    return db.execute(text("""SELECT a.id AS asset_id,a.filename,a.sha256,a.size_bytes,a.category
        FROM document_evidence_assets a
        WHERE a.tenant_id=:amo AND a.category='AUTHORITY'
          AND (CAST(:asset AS TEXT) IS NULL OR a.id=:asset)
          AND LOWER(a.filename) LIKE :search
          AND NOT EXISTS (SELECT 1 FROM document_retention_dispositions d
            WHERE d.tenant_id=a.tenant_id AND d.source_type='EVIDENCE_ASSET'
              AND d.source_id=a.id AND d.status='DISPOSED')
        ORDER BY a.created_at DESC LIMIT 50"""),
        {"amo":amo_id,"asset":asset_id,"search":f"%{search.lower()}%"}).mappings().all()


def authority_decision_evidence(db, *, amo_id, payload):
    if payload.decision_type not in {"AUTHORITY_SUBMISSION", "AUTHORITY_ACCEPTANCE"}:
        return None
    if payload.status != "APPROVED" and not payload.evidence_asset_id:
        return None
    if not payload.evidence_asset_id:
        raise HTTPException(422, "Select the retained Authority correspondence before recording this decision.")
    rows = _authority_evidence(db, amo_id=amo_id, asset_id=payload.evidence_asset_id)
    if not rows or len(rows[0]["sha256"] or "") != 64 or (rows[0]["size_bytes"] or 0) <= 0:
        raise HTTPException(422, "Authority evidence must be a retained, available Authority document in this AMO.")
    return dict(rows[0])


@router.get("/{mission_id}/authority-evidence")
def mission_authority_evidence(mission_id: str, search: str = "", ctx: TenantContext = Depends(require_quality_permission("qms.change.view")), db: Session = Depends(get_read_db)):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id)
    return {"items": [dict(row) for row in _authority_evidence(db, amo_id=ctx.amo_id, search=search[:120])]}


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
    authority_evidence = authority_decision_evidence(db, amo_id=ctx.amo_id, payload=payload)

    now = _utcnow()
    decision = QualityMissionDecision(
        amo_id=ctx.amo_id,
        mission_id=mission.id,
        decision_type=payload.decision_type,
        status=payload.status,
        rationale=payload.rationale.strip(),
        evidence_snapshot={**_decision_evidence_snapshot(mission), "authority_evidence": authority_evidence},
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


@router.post("/{mission_id}/cancel")
def cancel_governed_mission(
    mission_id: str,
    payload: MissionCancellation,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.manage")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    mission = _load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id, for_update=True)
    if mission.status in {"COMPLETE", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mission cannot be cancelled from {mission.status}.",
        )
    if not mission.owner_user_id or str(mission.owner_user_id) != str(ctx.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned Mission owner may cancel this Mission.",
        )
    now = _utcnow()
    db.add(QualityMissionDecision(
        amo_id=ctx.amo_id,
        mission_id=mission.id,
        decision_type="CUSTOM",
        status="REJECTED",
        rationale=f"Mission cancelled: {payload.reason.strip()}",
        evidence_snapshot=_decision_evidence_snapshot(mission),
        decided_by_user_id=ctx.user_id,
        decided_at=now,
        created_at=now,
    ))
    mission.status = "CANCELLED"
    mission.updated_by_user_id = ctx.user_id
    mission.updated_at = now
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)
