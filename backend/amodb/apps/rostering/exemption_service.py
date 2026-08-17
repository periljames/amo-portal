from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..doc_control import models as doc_models
from . import common
from .consent_models import RosterRegulatoryExemption

UTC = timezone.utc
_DISALLOWED_EVIDENCE_STATES = {"draft", "obsolete", "superseded", "archived", "withdrawn", "cancelled"}


def _supporting_document(
    db: Session,
    *,
    amo_id: str,
    document_id: str,
    require_current: bool = True,
) -> doc_models.ControlledDocument:
    document = db.query(doc_models.ControlledDocument).filter(
        doc_models.ControlledDocument.tenant_id == amo_id,
        doc_models.ControlledDocument.id == document_id,
    ).first()
    if document is None:
        raise ValueError("Supporting exemption document was not found in this tenant")
    state = str(document.status or "").strip().lower()
    if require_current and state in _DISALLOWED_EVIDENCE_STATES:
        raise ValueError("Supporting exemption evidence must be a current controlled document")
    if require_current and not document.current_asset_id:
        raise ValueError("Supporting exemption evidence has no current controlled asset")
    return document


def exemption_record_is_in_force(
    row: RosterRegulatoryExemption,
    *,
    amo_id: str,
    on_date: date,
) -> bool:
    """Defense-in-depth validity check independent of the SQL predicate.

    The database query already narrows these fields, but rechecking the material
    Authority conditions here prevents a future query refactor, eager-loaded
    object, or test adapter from accidentally applying an exemption outside the
    tenant or its controlled validity window.
    """

    return bool(
        row.amo_id == amo_id
        and row.verified_at is not None
        and not row.is_revoked
        and row.effective_date <= on_date <= row.expiry_date
    )


def create_exemption(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    authority: str,
    exemption_reference: str,
    regulation_provision: str,
    scope: str,
    effective_date: date,
    expiry_date: date,
    supporting_document_id: str,
    personnel_id: str | None = None,
    role_applicability: str | None = None,
    conditions: dict[str, Any] | None = None,
) -> RosterRegulatoryExemption:
    if expiry_date < effective_date:
        raise ValueError("Exemption expiry date must be on or after its effective date")
    _supporting_document(db, amo_id=amo_id, document_id=supporting_document_id)
    if personnel_id:
        common.require_user(db, amo_id=amo_id, user_id=personnel_id, active_only=False)
    row = RosterRegulatoryExemption(
        amo_id=amo_id,
        authority=authority.strip(),
        exemption_reference=exemption_reference.strip(),
        regulation_provision=regulation_provision.strip().upper(),
        scope=scope.strip(),
        personnel_id=personnel_id,
        role_applicability=role_applicability.strip().upper() if role_applicability else None,
        conditions_json=conditions or {},
        effective_date=effective_date,
        expiry_date=expiry_date,
        supporting_document_id=supporting_document_id,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRegulatoryExemption",
        entity_id=row.id,
        action="exemption_attached",
        after={
            "authority": row.authority,
            "reference": row.exemption_reference,
            "regulation_provision": row.regulation_provision,
            "effective_date": row.effective_date.isoformat(),
            "expiry_date": row.expiry_date.isoformat(),
            "supporting_document_id": row.supporting_document_id,
        },
        critical=True,
    )
    return row


def verify_exemption(db: Session, *, row: RosterRegulatoryExemption, actor_user_id: str) -> RosterRegulatoryExemption:
    if row.is_revoked:
        raise ValueError("A revoked regulatory exemption cannot be verified")
    if row.verified_at is not None:
        return row
    _supporting_document(db, amo_id=row.amo_id, document_id=row.supporting_document_id)
    row.verified_by_user_id = actor_user_id
    row.verified_at = datetime.now(UTC)
    db.add(row)
    common.audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRegulatoryExemption",
        entity_id=row.id,
        action="exemption_verified",
        after={
            "authority": row.authority,
            "reference": row.exemption_reference,
            "regulation_provision": row.regulation_provision,
            "verified_at": row.verified_at.isoformat(),
            "supporting_document_id": row.supporting_document_id,
        },
        critical=True,
    )
    return row


def revoke_exemption(db: Session, *, row: RosterRegulatoryExemption, actor_user_id: str, reason: str) -> RosterRegulatoryExemption:
    if row.is_revoked:
        raise ValueError("Regulatory exemption is already revoked")
    row.is_revoked = True
    row.revoked_at = datetime.now(UTC)
    row.revocation_reason = reason.strip()
    db.add(row)
    common.audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRegulatoryExemption",
        entity_id=row.id,
        action="exemption_revoked",
        after={"reason": row.revocation_reason},
        critical=True,
    )
    return row


def applicable_exemption(
    db: Session,
    *,
    amo_id: str,
    user: account_models.User | None,
    rule_code: str,
    on_date: date,
    assignment_ids: list[str] | None = None,
) -> RosterRegulatoryExemption | None:
    """Return a verified Authority exemption only when every stored condition matches."""

    code = rule_code.strip().upper()
    rows = db.query(RosterRegulatoryExemption).filter(
        RosterRegulatoryExemption.amo_id == amo_id,
        RosterRegulatoryExemption.regulation_provision == code,
        RosterRegulatoryExemption.is_revoked.is_(False),
        RosterRegulatoryExemption.verified_at.isnot(None),
        RosterRegulatoryExemption.effective_date <= on_date,
        RosterRegulatoryExemption.expiry_date >= on_date,
    ).order_by(RosterRegulatoryExemption.verified_at.desc()).all()
    user_id = getattr(user, "id", None)
    role = str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or "").upper()
    requested_assignments = set(assignment_ids or [])
    for row in rows:
        if not exemption_record_is_in_force(row, amo_id=amo_id, on_date=on_date):
            continue
        try:
            _supporting_document(db, amo_id=amo_id, document_id=row.supporting_document_id)
        except ValueError:
            continue
        if row.personnel_id and row.personnel_id != user_id:
            continue
        if row.role_applicability and row.role_applicability != role:
            continue
        conditions = dict(row.conditions_json or {})
        rule_codes = {str(item).upper() for item in conditions.get("rule_codes", [])}
        if rule_codes and code not in rule_codes:
            continue
        personnel_ids = {str(item) for item in conditions.get("personnel_ids", [])}
        if personnel_ids and str(user_id or "") not in personnel_ids:
            continue
        scoped_assignments = {str(item) for item in conditions.get("assignment_ids", [])}
        if scoped_assignments and not requested_assignments.intersection(scoped_assignments):
            continue
        if conditions.get("manual_conditions") and conditions.get("conditions_verified") is not True:
            continue
        return row
    return None
