from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.compliance.ledger import write_ledger_event
from amodb.apps.training.gates import ensure_finding_training_gate_satisfied
from amodb.apps.quality import models
from amodb.apps.quality.enums import CARStatus


@dataclass(frozen=True)
class Rule:
    allowed_from: set[str]
    evidence_required: bool = False


CAR_STATUS_RULES: dict[str, Rule] = {
    CARStatus.OPEN.value: Rule({CARStatus.DRAFT.value, CARStatus.ESCALATED.value}, evidence_required=False),
    CARStatus.IN_PROGRESS.value: Rule({CARStatus.OPEN.value, CARStatus.ESCALATED.value}, evidence_required=False),
    CARStatus.PENDING_VERIFICATION.value: Rule({CARStatus.IN_PROGRESS.value, CARStatus.ESCALATED.value}, evidence_required=True),
    CARStatus.CLOSED.value: Rule({CARStatus.PENDING_VERIFICATION.value, CARStatus.ESCALATED.value}, evidence_required=True),
    CARStatus.ESCALATED.value: Rule(
        {CARStatus.OPEN.value, CARStatus.IN_PROGRESS.value, CARStatus.PENDING_VERIFICATION.value},
        evidence_required=False,
    ),
    CARStatus.CANCELLED.value: Rule(
        {
            CARStatus.DRAFT.value,
            CARStatus.OPEN.value,
            CARStatus.IN_PROGRESS.value,
            CARStatus.PENDING_VERIFICATION.value,
            CARStatus.ESCALATED.value,
        },
        evidence_required=True,
    ),
}


def transition_car(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    car: models.CorrectiveActionRequest,
    target_status: str,
    evidence_ref: str | None,
    fail_closed_ledger: bool = True,
) -> models.CorrectiveActionRequest:
    target = str(target_status.value if hasattr(target_status, "value") else target_status)
    rule = CAR_STATUS_RULES.get(target)
    if not rule:
        raise HTTPException(status_code=400, detail=f"Unsupported CAR transition target: {target}")

    current = str(car.status.value if hasattr(car.status, "value") else car.status)
    if current not in rule.allowed_from:
        raise HTTPException(status_code=409, detail=f"Invalid CAR transition {current}->{target}")

    if rule.evidence_required and not evidence_ref:
        raise HTTPException(status_code=400, detail="evidence_ref is required for this transition")

    if target == CARStatus.CLOSED.value and car.finding_id:
        ensure_finding_training_gate_satisfied(db, amo_id=amo_id, finding_id=str(car.finding_id))

    car.status = target
    if evidence_ref:
        car.evidence_ref = evidence_ref
    db.add(car)

    write_ledger_event(
        db,
        amo_id=amo_id,
        entity_type="quality.car",
        entity_id=str(car.id),
        action=f"transition:{current}->{target}",
        actor_user_id=actor_user_id,
        payload={"before": current, "after": target, "evidence_ref": evidence_ref},
        critical=True,
        fail_closed=fail_closed_ledger,
    )
    return car
