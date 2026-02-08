from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services

from .registry import WORKFLOWS


@dataclass
class TransitionError(Exception):
    code: str
    detail: List[Dict[str, str]]


def _extract_amo_id(db: Session, actor_user_id: Optional[str], before_obj: Any, after_obj: Any) -> Optional[str]:
    for obj in (after_obj, before_obj):
        if isinstance(obj, dict) and obj.get("amo_id"):
            return obj.get("amo_id")
        amo_id = getattr(obj, "amo_id", None)
        if amo_id:
            return amo_id

    if actor_user_id:
        user = db.query(account_models.User).filter(account_models.User.id == actor_user_id).first()
        if user:
            return user.amo_id
    return None


def apply_transition(
    db: Session,
    *,
    actor_user_id: Optional[str],
    entity_type: str,
    entity_id: str,
    from_state: str,
    to_state: str,
    before_obj: Any,
    after_obj: Any,
    correlation_id: Optional[str] = None,
    critical: bool = True,
) -> None:
    workflow = WORKFLOWS.get(entity_type)
    if not workflow:
        raise TransitionError(
            code="invalid_transition",
            detail=[{"field": "entity_type", "reason": f"No workflow registered for {entity_type}"}],
        )

    transitions = workflow.get("transitions", {})
    allowed = transitions.get(from_state, {})
    guards = allowed.get(to_state)

    if guards is None:
        raise TransitionError(
            code="invalid_transition",
            detail=[{"field": "status", "reason": f"Cannot transition from {from_state} to {to_state}"}],
        )

    failures: List[Dict[str, str]] = []
    for guard in guards:
        failures.extend(
            guard(
                db,
                before_obj=before_obj,
                after_obj=after_obj,
                from_state=from_state,
                to_state=to_state,
            )
        )

    if failures:
        raise TransitionError(code="missing_requirements", detail=failures)

    before_payload: Dict[str, Any] = {"status": from_state}
    after_payload: Dict[str, Any] = {"status": to_state}
    if isinstance(before_obj, dict):
        before_payload.update({k: v for k, v in before_obj.items() if k != "amo_id"})
    if isinstance(after_obj, dict):
        after_payload.update({k: v for k, v in after_obj.items() if k != "amo_id"})

    amo_id = _extract_amo_id(db, actor_user_id, before_obj, after_obj)
    if not amo_id:
        raise TransitionError(
            code="invalid_transition",
            detail=[{"field": "amo_id", "reason": "Unable to resolve AMO for transition"}],
        )

    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action="transition",
        before=before_payload,
        after=after_payload,
        correlation_id=correlation_id,
        metadata={"workflow": entity_type},
        critical=critical,
    )
