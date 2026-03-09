from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.compliance.ledger import write_ledger_event
from amodb.apps.training.gates import ensure_finding_training_gate_satisfied
from amodb.apps.quality import models


@dataclass(frozen=True)
class Rule:
    allowed_from: set[str]
    evidence_required: bool = False


CAR_STATUS_RULES: dict[str, Rule] = {
    "ACKNOWLEDGED": Rule({"DRAFT", "OPEN"}, evidence_required=True),
    "RCA_IN_PROGRESS": Rule({"ACKNOWLEDGED"}, evidence_required=True),
    "CAPA_IN_PROGRESS": Rule({"RCA_IN_PROGRESS"}, evidence_required=True),
    "IMPLEMENTED": Rule({"CAPA_IN_PROGRESS"}, evidence_required=True),
    "EFFECTIVENESS_PENDING": Rule({"IMPLEMENTED"}, evidence_required=True),
    "CLOSED": Rule({"EFFECTIVENESS_PENDING"}, evidence_required=True),
    "REOPENED": Rule({"CLOSED"}, evidence_required=True),
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
    rule = CAR_STATUS_RULES.get(target_status)
    if not rule:
        raise HTTPException(status_code=400, detail=f"Unsupported CAR transition target: {target_status}")
    current = str(car.status.value if hasattr(car.status, "value") else car.status)
    if current not in rule.allowed_from:
        raise HTTPException(status_code=409, detail=f"Invalid CAR transition {current}->{target_status}")
    if rule.evidence_required and not evidence_ref:
        raise HTTPException(status_code=400, detail="evidence_ref is required for this transition")
    if target_status == "CLOSED" and car.finding_id:
        ensure_finding_training_gate_satisfied(db, amo_id=amo_id, finding_id=str(car.finding_id))
    car.status = target_status
    if evidence_ref:
        car.evidence_ref = evidence_ref
    db.add(car)
    write_ledger_event(
        db,
        amo_id=amo_id,
        entity_type="quality.car",
        entity_id=str(car.id),
        action=f"transition:{current}->{target_status}",
        actor_user_id=actor_user_id,
        payload={"before": current, "after": target_status, "evidence_ref": evidence_ref},
        critical=True,
        fail_closed=fail_closed_ledger,
    )
    return car
