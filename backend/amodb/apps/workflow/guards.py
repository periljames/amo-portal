from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

GuardResult = List[Dict[str, str]]


def _get_value(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def guard_document_publish(
    db: Session,
    *,
    before_obj: Any,
    after_obj: Any,
    from_state: str,
    to_state: str,
) -> GuardResult:
    approved_by_authority = _get_value(after_obj, "approved_by_authority")
    authority_ref = _get_value(after_obj, "authority_ref")
    approved_by_user_id = _get_value(after_obj, "approved_by_user_id")
    approved_at = _get_value(after_obj, "approved_at")

    if approved_by_authority:
        if not authority_ref:
            return [{"field": "authority_ref", "reason": "approval reference required"}]
        return []

    missing = []
    if not approved_by_user_id:
        missing.append({"field": "approved_by_user_id", "reason": "approver required"})
    if not approved_at:
        missing.append({"field": "approved_at", "reason": "approval timestamp required"})
    return missing


def guard_finding_close(
    db: Session,
    *,
    before_obj: Any,
    after_obj: Any,
    from_state: str,
    to_state: str,
) -> GuardResult:
    evidence = _get_value(after_obj, "objective_evidence")
    verified_at = _get_value(after_obj, "verified_at")

    missing = []
    if not evidence:
        missing.append({"field": "objective_evidence", "reason": "evidence required"})
    if not verified_at:
        missing.append({"field": "verified_at", "reason": "verification required"})
    return missing


def guard_cap_close(
    db: Session,
    *,
    before_obj: Any,
    after_obj: Any,
    from_state: str,
    to_state: str,
) -> GuardResult:
    containment_action = _get_value(after_obj, "containment_action")
    corrective_action = _get_value(after_obj, "corrective_action")
    evidence_ref = _get_value(after_obj, "evidence_ref")
    verified_at = _get_value(after_obj, "verified_at")

    missing = []
    if not containment_action:
        missing.append({"field": "containment_action", "reason": "immediate action required"})
    if not corrective_action:
        missing.append({"field": "corrective_action", "reason": "long-term action required"})
    if not evidence_ref:
        missing.append({"field": "evidence_ref", "reason": "evidence required"})
    if not verified_at:
        missing.append({"field": "verified_at", "reason": "verification required"})
    return missing


def guard_audit_close(
    db: Session,
    *,
    before_obj: Any,
    after_obj: Any,
    from_state: str,
    to_state: str,
) -> GuardResult:
    from amodb.apps.quality import models as quality_models

    audit_id = _get_value(after_obj, "audit_id") or _get_value(after_obj, "id")
    if not audit_id:
        return [{"field": "audit_id", "reason": "audit identifier required"}]

    if isinstance(audit_id, str):
        try:
            audit_id = UUID(audit_id)
        except ValueError:
            return [{"field": "audit_id", "reason": "invalid audit identifier"}]

    open_findings = (
        db.query(quality_models.QMSAuditFinding)
        .filter(
            quality_models.QMSAuditFinding.audit_id == audit_id,
            quality_models.QMSAuditFinding.closed_at.is_(None),
        )
        .count()
    )
    if open_findings > 0:
        return [{"field": "findings", "reason": "all findings must be closed"}]
    return []


def guard_training_participant_completion(
    db: Session,
    *,
    before_obj: Any,
    after_obj: Any,
    from_state: str,
    to_state: str,
) -> GuardResult:
    if to_state not in ("ATTENDED", "NO_SHOW"):
        return []

    marked_at = _get_value(after_obj, "attendance_marked_at")
    marked_by = _get_value(after_obj, "attendance_marked_by_user_id")

    missing = []
    if not marked_at:
        missing.append({"field": "attendance_marked_at", "reason": "attendance timestamp required"})
    if not marked_by:
        missing.append({"field": "attendance_marked_by_user_id", "reason": "attendance marker required"})
    return missing
