"""Shared, fail-closed verification of submitted structured CAR closeout.

The ordinary CAR update API and the governed control loop must not disagree
about the conditions for safely closing a submitted RCA.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .car_rca_models import QualityCarRcaAction, QualityCarRcaDocument


def ensure_structured_car_ready_for_closure(
    db: Session,
    *,
    amo_id: str,
    car_id: UUID,
    effectiveness_required: bool,
) -> None:
    document = db.query(QualityCarRcaDocument).filter(
        QualityCarRcaDocument.amo_id == amo_id,
        QualityCarRcaDocument.car_id == car_id,
    ).first()
    if document is None or document.submitted_revision is None:
        return

    actions = db.query(QualityCarRcaAction).filter(
        QualityCarRcaAction.amo_id == amo_id,
        QualityCarRcaAction.car_id == car_id,
    ).all()
    verified_corrective = [
        action for action in actions
        if action.kind == "CORRECTIVE" and action.state == "VERIFIED"
    ]
    if not verified_corrective:
        raise HTTPException(
            status_code=409,
            detail="At least one causal corrective action must be independently verified before closure. Cancelled actions do not satisfy the gate.",
        )
    pending = [action.sequence_no for action in actions if action.state not in {"VERIFIED", "CANCELLED"}]
    if pending:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Implementation must be independently verified before CAR closure.",
                "pending_action_numbers": pending,
            },
        )
    # An action marked VERIFIED without recorded independent reviewer or
    # implementation evidence cannot be used as proof of completion.
    unsubstantiated = [
        action.sequence_no for action in actions if action.state == "VERIFIED"
        and (not action.reviewed_by_user_id
             or action.reviewed_by_user_id in {action.owner_user_id}
             or not action.evidence_references)
    ]
    if unsubstantiated:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Verified actions must retain supporting evidence and an independent Quality reviewer.",
                "action_numbers": unsubstantiated,
            },
        )

    # Preserve the explicitly governed effectiveness-required policy. Quality
    # may formally configure whether this control applies; do not silently
    # convert the optional control into an unconditional gate.
    if not effectiveness_required:
        return

    from .assurance_case_models import QualityEffectivenessPlan
    latest = db.query(QualityEffectivenessPlan).filter(
        QualityEffectivenessPlan.amo_id == amo_id,
        QualityEffectivenessPlan.source_type == "CAR",
        QualityEffectivenessPlan.source_id == str(car_id),
        QualityEffectivenessPlan.status != "CANCELLED",
    ).order_by(QualityEffectivenessPlan.created_at.desc()).first()
    if (
        latest is None or latest.status != "CONCLUDED"
        or latest.conclusion != "EFFECTIVE"
        or not latest.concluded_by_user_id
        or not latest.conclusion_evidence
    ):
        raise HTTPException(
            status_code=409,
            detail="A concluded, independently verified EFFECTIVE assurance plan with documented evidence is required before this structured CAR can close.",
        )
    if latest.concluded_by_user_id != latest.responsible_reviewer_user_id:
        raise HTTPException(
            status_code=409,
            detail="The assigned independent reviewer must conclude CAR effectiveness.",
        )
