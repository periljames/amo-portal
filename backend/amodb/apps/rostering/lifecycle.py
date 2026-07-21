# backend/amodb/apps/rostering/lifecycle.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from . import common, models, schemas, validation


def validate_version(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: Optional[str] = None,
) -> schemas.RosterValidationResult:
    result = validation.run_validation(db, version=version, actor_user_id=actor_user_id)
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterVersion",
        entity_id=version.id,
        action="validate",
        after={
            "validation_fingerprint": result.validation_fingerprint,
            "blocker_count": result.blocker_count,
            "warning_count": result.warning_count,
            "info_count": result.info_count,
            "overridden_count": result.overridden_count,
        },
    )
    return result


def submit_version(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterLifecycleRequest,
) -> models.RosterVersion:
    common.ensure_draft(version)
    common.check_version_revision(version, payload.expected_state_revision)
    active_assignments = [row for row in version.assignments or [] if row.deleted_at is None]
    if not active_assignments:
        raise ValueError("A roster version must contain at least one assignment before submission")
    result = validate_version(db, version=version, actor_user_id=actor_user_id)
    if result.blocker_count:
        raise ValueError("Roster version has unresolved blocker findings and cannot be submitted")
    version.status = models.RosterVersionStatus.SUBMITTED
    version.submitted_by_user_id = actor_user_id
    version.submitted_at = common.utcnow()
    common.bump_version(version)
    db.add(version)
    db.flush()
    common.audit(db, amo_id=version.amo_id, actor_user_id=actor_user_id, entity_type="RosterVersion", entity_id=version.id, action="submit", after={"status": common.enum_value(version.status), "comment": payload.comment, "state_revision": version.state_revision}, critical=True)
    return version


def approve_version(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterLifecycleRequest,
) -> models.RosterVersion:
    if version.status != models.RosterVersionStatus.SUBMITTED:
        raise ValueError("Only submitted roster versions can be approved")
    common.check_version_revision(version, payload.expected_state_revision)
    if actor_user_id in {version.created_by_user_id, version.submitted_by_user_id}:
        raise ValueError("The roster creator or submitter cannot approve the same version")
    result = validate_version(db, version=version, actor_user_id=actor_user_id)
    if result.blocker_count:
        raise ValueError("Roster version has unresolved blocker findings and cannot be approved")
    version.status = models.RosterVersionStatus.APPROVED
    version.approved_by_user_id = actor_user_id
    version.approved_at = common.utcnow()
    common.bump_version(version)
    db.add(version)
    db.flush()
    common.audit(db, amo_id=version.amo_id, actor_user_id=actor_user_id, entity_type="RosterVersion", entity_id=version.id, action="approve", after={"status": common.enum_value(version.status), "comment": payload.comment, "state_revision": version.state_revision}, critical=True)
    return version


def _publication_url(db: Session, *, amo_id: str) -> str:
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    slug = getattr(amo, "login_slug", None) or getattr(amo, "amo_code", None) or amo_id
    return f"/maintenance/{slug}/rostering/my-roster"


def publish_version(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterLifecycleRequest,
) -> models.RosterVersion:
    if version.status == models.RosterVersionStatus.PUBLISHED:
        return version
    if version.status != models.RosterVersionStatus.APPROVED:
        raise ValueError("Only approved roster versions can be published")
    common.check_version_revision(version, payload.expected_state_revision)
    if actor_user_id == version.created_by_user_id:
        raise ValueError("The roster creator cannot publish the same version")
    operation_key = payload.idempotency_key or f"publish:{version.id}:{version.state_revision}"
    request_hash = common.canonical_hash({"version_id": version.id, "state_revision": version.state_revision, "comment": payload.comment})
    receipt = common.command_receipt(db, amo_id=version.amo_id, idempotency_key=operation_key, operation="PUBLISH", request_hash=request_hash)
    if receipt:
        return version
    result = validate_version(db, version=version, actor_user_id=actor_user_id)
    if result.blocker_count:
        raise ValueError("Roster version has unresolved blocker findings and cannot be published")
    siblings = db.query(models.RosterVersion).filter(
        models.RosterVersion.amo_id == version.amo_id,
        models.RosterVersion.period_id == version.period_id,
        models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
        models.RosterVersion.id != version.id,
    ).with_for_update().all()
    for sibling in siblings:
        sibling.status = models.RosterVersionStatus.SUPERSEDED
        sibling.state_revision += 1
        db.add(sibling)
    version.status = models.RosterVersionStatus.PUBLISHED
    version.published_by_user_id = actor_user_id
    version.published_at = common.utcnow()
    version.publication_correlation_key = operation_key
    version.period.status = models.RosterPeriodStatus.OPEN
    common.bump_version(version)
    for assignment in version.assignments or []:
        if assignment.deleted_at is None:
            assignment.locked_after_publish = True
            assignment.state_revision += 1
            db.add(assignment)
    db.add(version)
    db.add(version.period)
    db.flush()
    common.save_command_receipt(
        db,
        amo_id=version.amo_id,
        idempotency_key=operation_key,
        operation="PUBLISH",
        actor_user_id=actor_user_id,
        request_hash=request_hash,
        response_json={"version_id": version.id, "status": models.RosterVersionStatus.PUBLISHED.value, "published_at": version.published_at.isoformat()},
    )
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterVersion",
        entity_id=version.id,
        action="publish",
        after={
            "status": common.enum_value(version.status),
            "version_no": version.version_no,
            "superseded_version_ids": [row.id for row in siblings],
            "comment": payload.comment,
            "publication_correlation_key": operation_key,
            "state_revision": version.state_revision,
        },
        critical=True,
    )
    route = _publication_url(db, amo_id=version.amo_id)
    users: dict[str, account_models.User] = {}
    for assignment in version.assignments or []:
        if assignment.deleted_at is None and assignment.user:
            users[assignment.user_id] = assignment.user
    for user_id in sorted(users):
        user = users[user_id]
        common.notify_email(
            db,
            amo_id=version.amo_id,
            recipient=user.email,
            template_key="rostering.published",
            subject=f"Duty roster published: {version.period.name}",
            context={
                "version_id": version.id,
                "period_id": version.period_id,
                "period_name": version.period.name,
                "version_no": version.version_no,
                "published_at": version.published_at.isoformat(),
                "route": route,
                "user_id": user_id,
            },
            correlation_id=f"{operation_key}:{user_id}",
        )
    return version


def acknowledge_version(
    db: Session,
    *,
    version: models.RosterVersion,
    user_id: str,
    payload: schemas.RosterAcknowledgeRequest,
) -> models.RosterPublicationAcknowledgement:
    if version.status != models.RosterVersionStatus.PUBLISHED:
        raise ValueError("Only published roster versions can be acknowledged")
    assigned = any(row.user_id == user_id and row.deleted_at is None for row in version.assignments or [])
    if not assigned:
        raise ValueError("The user has no assignment in this published roster")
    existing = db.query(models.RosterPublicationAcknowledgement).filter(
        models.RosterPublicationAcknowledgement.amo_id == version.amo_id,
        models.RosterPublicationAcknowledgement.version_id == version.id,
        models.RosterPublicationAcknowledgement.user_id == user_id,
    ).first()
    if existing:
        if payload.acknowledgement_note is not None:
            existing.acknowledgement_note = payload.acknowledgement_note
        if payload.idempotency_key and not existing.idempotency_key:
            existing.idempotency_key = payload.idempotency_key
        existing.acknowledged_at = common.utcnow()
        existing.viewed_at = existing.viewed_at or existing.acknowledged_at
        existing.delivery_status = "ACKNOWLEDGED"
        db.add(existing)
        db.flush()
        return existing
    row = models.RosterPublicationAcknowledgement(
        amo_id=version.amo_id,
        version_id=version.id,
        user_id=user_id,
        idempotency_key=payload.idempotency_key,
        delivery_status="ACKNOWLEDGED",
        viewed_at=common.utcnow(),
        acknowledgement_note=payload.acknowledgement_note,
    )
    db.add(row)
    db.flush()
    common.audit(db, amo_id=version.amo_id, actor_user_id=user_id, entity_type="RosterPublicationAcknowledgement", entity_id=row.id, action="acknowledge", after={"version_id": version.id, "user_id": user_id, "acknowledged_at": row.acknowledged_at.isoformat()})
    return row


def override_finding(
    db: Session,
    *,
    finding: models.RosterValidationFinding,
    actor_user_id: str,
    payload: schemas.RosterRuleOverrideRequest,
) -> models.RosterRuleException:
    exception = validation.override_finding(db, finding=finding, actor_user_id=actor_user_id, payload=payload)
    common.audit(
        db,
        amo_id=finding.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRuleException",
        entity_id=exception.id,
        action="override",
        after={
            "finding_id": finding.id,
            "rule_id": finding.rule_id,
            "decision": common.enum_value(exception.decision),
            "reason": exception.reason,
            "expires_at": exception.expires_at.isoformat() if exception.expires_at else None,
        },
        critical=True,
    )
    return exception


def revoke_exception(db: Session, *, exception: models.RosterRuleException, actor_user_id: str, reason: str) -> models.RosterRuleException:
    if exception.decision == models.RosterExceptionDecision.REVOKE:
        return exception
    previous = common.enum_value(exception.decision)
    exception.decision = models.RosterExceptionDecision.REVOKE
    exception.reason = f"{exception.reason}\nRevoked: {reason}".strip()
    db.add(exception)
    if exception.finding:
        exception.finding.resolved = False
        exception.finding.overridden_at = None
        exception.finding.overridden_by_user_id = None
        exception.finding.override_reason = None
        db.add(exception.finding)
    db.flush()
    common.audit(db, amo_id=exception.amo_id, actor_user_id=actor_user_id, entity_type="RosterRuleException", entity_id=exception.id, action="revoke", before={"decision": previous}, after={"decision": common.enum_value(exception.decision), "reason": reason}, critical=True)
    return exception


def list_exceptions(db: Session, *, amo_id: str, version_id: Optional[str] = None) -> list[models.RosterRuleException]:
    query = db.query(models.RosterRuleException).options(
        selectinload(models.RosterRuleException.finding),
        selectinload(models.RosterRuleException.rule),
    ).filter(models.RosterRuleException.amo_id == amo_id)
    if version_id:
        query = query.filter(models.RosterRuleException.version_id == version_id)
    return query.order_by(models.RosterRuleException.created_at.desc(), models.RosterRuleException.id.desc()).all()
