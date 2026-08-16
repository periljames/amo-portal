from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models

from . import models
from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .enums import FindingLevel, QMSAuditStatus, QMSFindingSeverity, QMSFindingType
from .service import compute_target_close_date, normalize_finding_level


@dataclass
class OfficialFindingTransactionResult:
    audit: models.QMSAudit
    item: models.QualityAuditChecklistItem
    governance: QualityAuditChecklistExecutionGovernance
    finding: models.QMSAuditFinding
    car: Any | None
    committed_version: int
    row_snapshot: dict[str, Any]
    finding_snapshot: dict[str, Any]
    events: list[audit_models.AuditEvent]


def _classification(
    *,
    canonical_response_status: str,
    severity: QMSFindingSeverity,
    level: FindingLevel,
) -> tuple[FindingLevel, QMSFindingType]:
    requested_type = QMSFindingType.OBSERVATION if canonical_response_status == "OBSERVATION" else QMSFindingType.NON_CONFORMITY
    normalized = normalize_finding_level(severity, level, requested_type)
    finding_type = QMSFindingType.OBSERVATION if normalized == FindingLevel.LEVEL_4 else QMSFindingType.NON_CONFORMITY
    if canonical_response_status == "OBSERVATION" and finding_type != QMSFindingType.OBSERVATION:
        raise HTTPException(status_code=422, detail="An OBSERVATION checklist response must use the governed Level 4 observation classification.")
    if canonical_response_status == "NONCOMPLIANT" and finding_type != QMSFindingType.NON_CONFORMITY:
        raise HTTPException(status_code=422, detail="A NONCOMPLIANT checklist response must use a governed Level 1, 2 or 3 non-conformity classification.")
    return normalized, finding_type


def create_official_finding_transaction(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    checklist_item_id: uuid.UUID,
    actor_user_id: str,
    canonical_response_status: str,
    severity: QMSFindingSeverity,
    level: FindingLevel,
    requirement_ref: str | None,
    description: str,
    objective_evidence: str | None,
    safety_sensitive: bool,
    target_close_date: date | None,
    execution_auditor_notes: str | None,
    execution_evidence_references: list[dict[str, Any] | str],
    execution_reason: str,
    correlation_id: str,
    source_metadata: dict[str, Any] | None = None,
    expected_base_version: int | None = None,
) -> OfficialFindingTransactionResult:
    """Build the authoritative finding/checklist/CAR unit without committing.

    The caller owns the transaction boundary. This lets Live Audit and an
    external-draft promotion share exactly one official finding implementation.
    A caller may append its own lifecycle event in the same transaction before
    committing. No realtime publish occurs here.
    """

    # Import lazily to avoid a module-registration cycle while reusing the
    # current canonical Quality helpers and checklist governance functions.
    from . import router as quality_router
    from .audit_checklist_execution_router import (
        ChecklistExecutionUpdate,
        _apply_execution_update,
        _assert_base_version,
        _item,
        _locked_governance,
        _row_dict,
    )

    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).with_for_update().first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")

    user = db.query(account_models.User).filter(
        account_models.User.id == actor_user_id,
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=403, detail="Active internal Quality identity is required to create an official finding.")
    quality_router._require_audit_fieldwork_write_access(user, audit)

    item = _item(db, amo_id=amo_id, audit_id=audit_id, item_id=checklist_item_id, lock=True)
    governance = _locked_governance(
        db,
        ctx=type("FindingCtx", (), {"amo_id": amo_id, "user_id": actor_user_id})(),
        audit_id=audit_id,
        item_id=checklist_item_id,
    )
    current_version = int(governance.entity_version or 1) if governance is not None else 0
    if expected_base_version is not None:
        _assert_base_version(
            payload_base_version=expected_base_version,
            client_mutation_id=correlation_id,
            item=item,
            governance=governance,
        )
    if item.finding_id is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELDWORK_FINDING_ALREADY_LINKED",
                "message": "This checklist item already has a governed finding.",
                "finding_id": str(item.finding_id),
            },
        )

    normalized_level, finding_type = _classification(
        canonical_response_status=canonical_response_status,
        severity=severity,
        level=level,
    )
    effective_target = target_close_date
    if effective_target is None and normalized_level != FindingLevel.LEVEL_4:
        effective_target = compute_target_close_date(normalized_level)

    finding = models.QMSAuditFinding(
        amo_id=amo_id,
        audit_id=audit_id,
        finding_ref=quality_router._next_audit_finding_ref(db, audit),
        finding_type=finding_type,
        severity=severity,
        level=normalized_level,
        requirement_ref=requirement_ref.strip() if requirement_ref else None,
        description=description.strip(),
        objective_evidence=objective_evidence.strip() if objective_evidence else None,
        safety_sensitive=safety_sensitive,
        target_close_date=effective_target,
        created_by_user_id=actor_user_id,
    )
    db.add(finding)
    db.flush()
    item.finding_id = finding.id

    if normalized_level != FindingLevel.LEVEL_4:
        task_owner = audit.lead_auditor_user_id or actor_user_id
        quality_router.task_services.create_task(
            db,
            amo_id=amo_id,
            title="Respond to finding",
            description=f"Finding {finding.finding_ref or finding.id} requires response.",
            owner_user_id=task_owner,
            supervisor_user_id=audit.observer_auditor_user_id,
            due_at=quality_router._date_to_datetime(finding.target_close_date),
            entity_type="qms_finding",
            entity_id=str(finding.id),
            priority=2,
        )
        if audit.status in (QMSAuditStatus.PLANNED, QMSAuditStatus.IN_PROGRESS):
            audit.status = QMSAuditStatus.CAP_OPEN

    car = quality_router._ensure_car_for_finding(
        db,
        audit=audit,
        finding=finding,
        requested_by_user_id=actor_user_id,
    )

    execution_ctx = type("FindingCtx", (), {"amo_id": amo_id, "user_id": actor_user_id})()
    governance = _apply_execution_update(
        db,
        ctx=execution_ctx,
        item=item,
        payload=ChecklistExecutionUpdate(
            canonical_response_status=canonical_response_status,
            auditor_notes=execution_auditor_notes,
            evidence_references=execution_evidence_references,
            reason=execution_reason,
        ),
        governance=governance,
    )
    committed_version = int(governance.entity_version or 1)
    db.flush()

    metadata = {
        "module": "quality",
        "auditId": str(audit_id),
        "checklistItemId": str(checklist_item_id),
        **(source_metadata or {}),
    }
    finding_event = audit_models.AuditEvent(
        amo_id=amo_id,
        entity_type="qms.finding",
        entity_id=str(finding.id),
        action="CREATED",
        actor_user_id=actor_user_id,
        before=None,
        after={
            "audit_id": str(audit_id),
            "finding_ref": finding.finding_ref,
            "severity": finding.severity.value,
            "level": finding.level.value,
            "target_close_date": str(finding.target_close_date) if finding.target_close_date else None,
            "checklist_item_id": str(checklist_item_id),
        },
        correlation_id=correlation_id,
        metadata_json=metadata,
    )
    checklist_event = audit_models.AuditEvent(
        amo_id=amo_id,
        entity_type="qms.audit.checklist_item",
        entity_id=str(checklist_item_id),
        action="UPDATED_WITH_FINDING",
        actor_user_id=actor_user_id,
        before={"entity_version": current_version},
        after={"entity_version": committed_version, "canonical_response_status": canonical_response_status, "finding_id": str(finding.id)},
        correlation_id=correlation_id,
        metadata_json=metadata,
    )
    events = [finding_event, checklist_event]
    if car is not None:
        events.append(audit_models.AuditEvent(
            amo_id=amo_id,
            entity_type="qms.car",
            entity_id=str(car.id),
            action="AUTO_CREATED_FROM_FINDING",
            actor_user_id=actor_user_id,
            before=None,
            after={"finding_id": str(finding.id), "car_number": car.car_number},
            correlation_id=correlation_id,
            metadata_json=metadata,
        ))
    db.add_all(events)
    db.flush()

    return OfficialFindingTransactionResult(
        audit=audit,
        item=item,
        governance=governance,
        finding=finding,
        car=car,
        committed_version=committed_version,
        row_snapshot=jsonable_row(_row_dict(item, governance)),
        finding_snapshot=jsonable_row(quality_router._serialize_finding(finding)),
        events=events,
    )


def jsonable_row(value: Any) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder
    encoded = jsonable_encoder(value)
    return dict(encoded)
