from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.compliance.ledger import write_ledger_event
from amodb.apps.doc_control import models
from amodb.apps.training.gates import ensure_revision_training_gate_satisfied


@dataclass(frozen=True)
class TransitionRule:
    allowed_from: set[str]
    required_fields: set[str]


REVISION_RULES: dict[str, TransitionRule] = {
    "Review": TransitionRule({"Draft"}, {"change_summary"}),
    "Approved": TransitionRule({"Review"}, {"internal_approval_status"}),
    "Published": TransitionRule({"Approved"}, {"effective_date", "transmittal_notice"}),
    "Superseded": TransitionRule({"Published"}, set()),
    "Archived": TransitionRule({"Superseded"}, set()),
}


def _assert_required(payload: dict, fields: Iterable[str]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "", [])]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required evidence fields: {', '.join(missing)}")


def transition_revision_package(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    package: models.RevisionPackage,
    target_status: str,
    evidence: dict,
    fail_closed_ledger: bool = True,
) -> models.RevisionPackage:
    rule = REVISION_RULES.get(target_status)
    if not rule:
        raise HTTPException(status_code=400, detail=f"Unsupported target status: {target_status}")
    current = package.internal_approval_status
    if current not in rule.allowed_from:
        raise HTTPException(status_code=409, detail=f"Invalid transition {current} -> {target_status}")
    _assert_required(evidence, rule.required_fields)
    if target_status == "Published":
        ensure_revision_training_gate_satisfied(db, amo_id=amo_id, package=package)
    package.internal_approval_status = target_status
    db.add(package)
    write_ledger_event(
        db,
        amo_id=amo_id,
        entity_type="doc_control.revision_package",
        entity_id=str(package.package_id),
        action=f"transition:{current}->{target_status}",
        actor_user_id=actor_user_id,
        payload={"before": current, "after": target_status, "evidence": evidence},
        critical=True,
        fail_closed=fail_closed_ledger,
    )
    return package


def assert_doc_access_allowed(*, doc: models.ControlledDocument, can_view_restricted: bool) -> None:
    if doc.status in {"Superseded", "Archived"}:
        raise HTTPException(status_code=403, detail="Document is obsolete; use archive access path")
    if doc.restricted_flag and not can_view_restricted:
        raise HTTPException(status_code=403, detail="Restricted document access denied")
