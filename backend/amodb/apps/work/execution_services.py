from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.crs.models import CRS, CRSSignoff
from amodb.apps.technical_records import models as technical_record_models

from . import models as work_models
from . import package_services
from . import services as work_services
from .execution_models import (
    ProductionExecutionEvent,
    ProductionExecutionSession,
    ProductionTaskIssue,
    RecordsHandbackEvent,
    RecordsHandbackFinding,
    RecordsHandbackPackage,
)
from .execution_schemas import (
    ExecutionDashboardRead,
    ExecutionEventCreate,
    ExecutionSessionClose,
    ExecutionSessionCreate,
    HandbackBuildRequest,
    HandbackFindingCreate,
    HandbackFindingResolve,
    HandbackRead,
    HandbackReviewRequest,
    HandbackSubmitRequest,
    TaskIssueCreate,
    TaskIssueResolve,
)
from .readiness_models import WorkPackageFreeze


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Unsupported value {type(value)!r}")


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
        ),
    )


def _get_session(db: Session, *, amo_id: str, session_id: str) -> ProductionExecutionSession:
    row = db.query(ProductionExecutionSession).filter(
        ProductionExecutionSession.amo_id == amo_id,
        ProductionExecutionSession.id == session_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Production execution session not found")
    return row


def _get_handback(db: Session, *, amo_id: str, handback_id: str) -> RecordsHandbackPackage:
    row = db.query(RecordsHandbackPackage).filter(
        RecordsHandbackPackage.amo_id == amo_id,
        RecordsHandbackPackage.id == handback_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Records handback package not found")
    return row


def _active_freeze(db: Session, *, amo_id: str, package_id: int) -> WorkPackageFreeze:
    freeze = db.query(WorkPackageFreeze).filter(
        WorkPackageFreeze.amo_id == amo_id,
        WorkPackageFreeze.work_package_id == package_id,
        WorkPackageFreeze.status == "ACTIVE",
    ).order_by(WorkPackageFreeze.version.desc()).first()
    if not freeze:
        raise HTTPException(status_code=409, detail="An active frozen package manifest is required")
    return freeze


def list_sessions(db: Session, *, amo_id: str, package_id: int | None = None) -> list[ProductionExecutionSession]:
    query = db.query(ProductionExecutionSession).filter(ProductionExecutionSession.amo_id == amo_id)
    if package_id:
        query = query.filter(ProductionExecutionSession.work_package_id == package_id)
    return query.order_by(ProductionExecutionSession.started_at.desc()).all()


def start_session(
    db: Session,
    *,
    amo_id: str,
    payload: ExecutionSessionCreate,
    actor: User,
) -> ProductionExecutionSession:
    package = package_services._get_package(db, amo_id=amo_id, package_id=payload.work_package_id)
    if package.status not in {"RELEASED", "IN_PROGRESS"}:
        raise HTTPException(status_code=409, detail="Package must be released before execution can start")
    freeze = _active_freeze(db, amo_id=amo_id, package_id=package.id)
    if payload.work_order_id:
        linked = any(link.work_order_id == payload.work_order_id for link in package.order_links or [])
        if not linked:
            raise HTTPException(status_code=400, detail="Work order is not part of the selected package")
    existing = db.query(ProductionExecutionSession).filter(
        ProductionExecutionSession.amo_id == amo_id,
        ProductionExecutionSession.work_package_id == package.id,
        ProductionExecutionSession.work_order_id == payload.work_order_id,
        ProductionExecutionSession.status.in_(["OPEN", "BLOCKED"]),
    ).first()
    if existing:
        return existing
    row = ProductionExecutionSession(
        amo_id=amo_id,
        work_package_id=package.id,
        work_order_id=payload.work_order_id,
        package_freeze_id=freeze.id,
        shift_reference=payload.shift_reference,
        station=payload.station,
        status="OPEN",
        started_by_user_id=actor.id,
        started_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    db.add(ProductionExecutionEvent(
        amo_id=amo_id,
        session_id=row.id,
        work_order_id=payload.work_order_id,
        event_type="SESSION_START",
        to_status="OPEN",
        payload_json={"package_freeze_id": freeze.id, "manifest_hash": freeze.manifest_hash},
        actor_user_id=actor.id,
        occurred_at=_utcnow(),
    ))
    _audit(db, amo_id=amo_id, actor_user_id=actor.id, entity_type="ProductionExecutionSession", entity_id=row.id, action="start", after={"package_id": package.id, "freeze_id": freeze.id})
    return row


def _task_for_event(db: Session, *, amo_id: str, task_id: int) -> work_models.TaskCard:
    task = db.query(work_models.TaskCard).filter(
        work_models.TaskCard.amo_id == amo_id,
        work_models.TaskCard.id == task_id,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task card not found")
    return task


def record_event(
    db: Session,
    *,
    session: ProductionExecutionSession,
    payload: ExecutionEventCreate,
    actor: User,
) -> ProductionExecutionEvent:
    if session.status not in {"OPEN", "BLOCKED"}:
        raise HTTPException(status_code=409, detail="Execution session is closed")
    task = _task_for_event(db, amo_id=session.amo_id, task_id=payload.task_card_id) if payload.task_card_id else None
    if task:
        package = package_services._get_package(db, amo_id=session.amo_id, package_id=session.work_package_id)
        if not any(task.work_order_id == link.work_order_id for link in package.order_links or []):
            raise HTTPException(status_code=400, detail="Task card is not part of this execution package")
    from_status = task.status.value if task and hasattr(task.status, "value") else (str(task.status) if task else session.status)
    target_status = payload.to_status
    status_by_event = {
        "TASK_START": work_models.TaskStatusEnum.IN_PROGRESS,
        "TASK_PAUSE": work_models.TaskStatusEnum.PAUSED,
        "TASK_RESUME": work_models.TaskStatusEnum.IN_PROGRESS,
        "TASK_COMPLETE": work_models.TaskStatusEnum.COMPLETED,
        "TASK_INSPECT": work_models.TaskStatusEnum.INSPECTED,
    }
    if task and payload.event_type in status_by_event:
        desired = status_by_event[payload.event_type]
        work_services._ensure_valid_task_transition(task, desired)
        if desired == work_models.TaskStatusEnum.COMPLETED:
            work_services._ensure_required_steps_executed(db, task)
        if desired == work_models.TaskStatusEnum.INSPECTED and actor.role not in {
            AccountRole.SUPERUSER,
            AccountRole.AMO_ADMIN,
            AccountRole.PRODUCTION_ENGINEER,
            AccountRole.CERTIFYING_ENGINEER,
            AccountRole.CERTIFYING_TECHNICIAN,
        }:
            raise HTTPException(status_code=403, detail="Inspection transition requires certifying or production authority")
        task.status = desired
        task.updated_by_user_id = actor.id
        if desired == work_models.TaskStatusEnum.IN_PROGRESS and not task.actual_start:
            task.actual_start = _utcnow()
        if desired in {work_models.TaskStatusEnum.COMPLETED, work_models.TaskStatusEnum.INSPECTED}:
            task.actual_end = _utcnow()
        db.add(task)
        target_status = desired.value
    if payload.event_type == "PACKAGE_BLOCKED":
        session.status = "BLOCKED"
        target_status = "BLOCKED"
    if payload.event_type == "PACKAGE_UNBLOCKED":
        session.status = "OPEN"
        target_status = "OPEN"
    event = ProductionExecutionEvent(
        amo_id=session.amo_id,
        session_id=session.id,
        work_order_id=payload.work_order_id or session.work_order_id or (task.work_order_id if task else None),
        task_card_id=task.id if task else payload.task_card_id,
        event_type=payload.event_type,
        from_status=from_status,
        to_status=target_status,
        payload_json=payload.payload_json,
        actor_user_id=actor.id,
        occurred_at=_utcnow(),
    )
    db.add(session)
    db.add(event)
    db.flush()
    return event


def raise_issue(
    db: Session,
    *,
    session: ProductionExecutionSession,
    payload: TaskIssueCreate,
    actor: User,
) -> ProductionTaskIssue:
    package = package_services._get_package(db, amo_id=session.amo_id, package_id=session.work_package_id)
    if not any(link.work_order_id == payload.work_order_id for link in package.order_links or []):
        raise HTTPException(status_code=400, detail="Work order is not part of this execution package")
    if payload.task_card_id:
        task = _task_for_event(db, amo_id=session.amo_id, task_id=payload.task_card_id)
        if task.work_order_id != payload.work_order_id:
            raise HTTPException(status_code=400, detail="Task card does not belong to the selected work order")
    issue = ProductionTaskIssue(
        amo_id=session.amo_id,
        session_id=session.id,
        work_order_id=payload.work_order_id,
        task_card_id=payload.task_card_id,
        category=payload.category,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        status="OPEN",
        evidence_json=payload.evidence_json,
        raised_by_user_id=actor.id,
        raised_at=_utcnow(),
    )
    db.add(issue)
    db.flush()
    db.add(ProductionExecutionEvent(
        amo_id=session.amo_id,
        session_id=session.id,
        work_order_id=payload.work_order_id,
        task_card_id=payload.task_card_id,
        event_type="ISSUE_RAISED",
        payload_json={"issue_id": issue.id, "category": issue.category, "severity": issue.severity},
        actor_user_id=actor.id,
        occurred_at=_utcnow(),
    ))
    return issue


def resolve_issue(
    db: Session,
    *,
    amo_id: str,
    issue_id: str,
    payload: TaskIssueResolve,
    actor: User,
) -> ProductionTaskIssue:
    issue = db.query(ProductionTaskIssue).filter(
        ProductionTaskIssue.amo_id == amo_id,
        ProductionTaskIssue.id == issue_id,
    ).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Production issue not found")
    if issue.status != "OPEN":
        raise HTTPException(status_code=409, detail="Production issue is already resolved")
    if payload.linked_non_routine_task_id:
        task = _task_for_event(db, amo_id=amo_id, task_id=payload.linked_non_routine_task_id)
        if task.work_order_id != issue.work_order_id:
            raise HTTPException(status_code=400, detail="Non-routine task belongs to a different work order")
    issue.status = "RESOLVED"
    issue.disposition = payload.disposition
    issue.linked_non_routine_task_id = payload.linked_non_routine_task_id
    issue.resolution_notes = payload.resolution_notes
    issue.resolved_by_user_id = actor.id
    issue.resolved_at = _utcnow()
    db.add(issue)
    db.add(ProductionExecutionEvent(
        amo_id=amo_id,
        session_id=issue.session_id,
        work_order_id=issue.work_order_id,
        task_card_id=issue.task_card_id,
        event_type="ISSUE_RESOLVED",
        payload_json={"issue_id": issue.id, "disposition": issue.disposition},
        actor_user_id=actor.id,
        occurred_at=_utcnow(),
    ))
    return issue


def close_session(
    db: Session,
    *,
    session: ProductionExecutionSession,
    payload: ExecutionSessionClose,
    actor: User,
) -> ProductionExecutionSession:
    if session.status == "CLOSED":
        return session
    open_issues = db.query(ProductionTaskIssue).filter(
        ProductionTaskIssue.session_id == session.id,
        ProductionTaskIssue.status == "OPEN",
    ).count()
    if open_issues:
        raise HTTPException(status_code=409, detail=f"Resolve {open_issues} open issue(s) before closing the session")
    session.status = "CLOSED"
    session.closed_by_user_id = actor.id
    session.closed_at = _utcnow()
    session.closure_notes = payload.closure_notes
    db.add(session)
    db.add(ProductionExecutionEvent(
        amo_id=session.amo_id,
        session_id=session.id,
        work_order_id=session.work_order_id,
        event_type="SESSION_CLOSE",
        from_status="OPEN",
        to_status="CLOSED",
        payload_json={"closure_notes": payload.closure_notes},
        actor_user_id=actor.id,
        occurred_at=_utcnow(),
    ))
    return session


def _handback_readiness(db: Session, *, amo_id: str, package_id: int) -> dict[str, Any]:
    package = package_services._get_package(db, amo_id=amo_id, package_id=package_id)
    freeze = _active_freeze(db, amo_id=amo_id, package_id=package_id)
    blockers: list[str] = []
    warnings: list[str] = []
    sessions = db.query(ProductionExecutionSession).filter(
        ProductionExecutionSession.amo_id == amo_id,
        ProductionExecutionSession.work_package_id == package_id,
    ).all()
    if not sessions:
        blockers.append("No production execution session exists for the package.")
    open_sessions = [session for session in sessions if session.status != "CLOSED"]
    if open_sessions:
        blockers.append(f"{len(open_sessions)} execution session(s) remain open or blocked.")
    issues = db.query(ProductionTaskIssue).filter(
        ProductionTaskIssue.amo_id == amo_id,
        ProductionTaskIssue.session_id.in_([session.id for session in sessions]) if sessions else False,
    ).all()
    open_issues = [issue for issue in issues if issue.status == "OPEN"]
    if open_issues:
        blockers.append(f"{len(open_issues)} production issue(s) remain open.")
    orders = [link.work_order for link in package.order_links or []]
    tasks = [task for order in orders for task in (order.tasks or [])]
    incomplete_tasks = [
        task for task in tasks
        if task.status not in {
            work_models.TaskStatusEnum.COMPLETED,
            work_models.TaskStatusEnum.INSPECTED,
            work_models.TaskStatusEnum.CLOSED,
        }
    ]
    if incomplete_tasks:
        blockers.append(f"{len(incomplete_tasks)} task card(s) are incomplete.")
    evidence_by_order: dict[int, int] = {}
    gate_by_order: dict[int, Any] = {}
    crs_by_order: dict[int, int] = {}
    for order in orders:
        evidence_count = db.query(technical_record_models.ProductionExecutionEvidence).filter(
            technical_record_models.ProductionExecutionEvidence.amo_id == amo_id,
            technical_record_models.ProductionExecutionEvidence.work_order_id == order.id,
        ).count()
        evidence_by_order[order.id] = evidence_count
        gate = db.query(technical_record_models.ProductionReleaseGate).filter(
            technical_record_models.ProductionReleaseGate.amo_id == amo_id,
            technical_record_models.ProductionReleaseGate.work_order_id == order.id,
        ).first()
        gate_by_order[order.id] = gate
        crs_count = db.query(CRS).filter(CRS.work_order_id == order.id).count()
        crs_by_order[order.id] = crs_count
        if not evidence_count:
            blockers.append(f"Work order {order.wo_number} has no execution evidence.")
        if not gate or not gate.signed_off_at:
            blockers.append(f"Work order {order.wo_number} release gate is not signed.")
        if not crs_count and order.closure_reason != "NO_CRS_REQUIRED":
            blockers.append(f"Work order {order.wo_number} has no CRS.")
        if crs_count:
            signed = db.query(CRSSignoff).join(CRS, CRSSignoff.crs_id == CRS.id).filter(CRS.work_order_id == order.id).count()
            if not signed:
                blockers.append(f"Work order {order.wo_number} CRS has no sign-off rows.")
    readiness_status = "BLOCKED" if blockers else ("ATTENTION" if warnings else "READY")
    return {
        "status": readiness_status,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": {
            "sessions": len(sessions),
            "open_sessions": len(open_sessions),
            "issues": len(issues),
            "open_issues": len(open_issues),
            "orders": len(orders),
            "tasks": len(tasks),
            "incomplete_tasks": len(incomplete_tasks),
            "evidence_by_order": evidence_by_order,
            "crs_by_order": crs_by_order,
        },
        "freeze_id": freeze.id,
        "freeze_hash": freeze.manifest_hash,
    }


def _handback_manifest(db: Session, *, amo_id: str, package_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_services._get_package(db, amo_id=amo_id, package_id=package_id)
    readiness = _handback_readiness(db, amo_id=amo_id, package_id=package_id)
    freeze = _active_freeze(db, amo_id=amo_id, package_id=package_id)
    sessions = list_sessions(db, amo_id=amo_id, package_id=package_id)
    orders = []
    for link in package.order_links or []:
        order = link.work_order
        evidence = db.query(technical_record_models.ProductionExecutionEvidence).filter(
            technical_record_models.ProductionExecutionEvidence.amo_id == amo_id,
            technical_record_models.ProductionExecutionEvidence.work_order_id == order.id,
        ).all()
        gate = db.query(technical_record_models.ProductionReleaseGate).filter(
            technical_record_models.ProductionReleaseGate.amo_id == amo_id,
            technical_record_models.ProductionReleaseGate.work_order_id == order.id,
        ).first()
        crs_rows = db.query(CRS).filter(CRS.work_order_id == order.id).all()
        orders.append({
            "id": order.id,
            "wo_number": order.wo_number,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "tasks": [{
                "id": task.id,
                "task_code": task.task_code,
                "title": task.title,
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "actual_start": task.actual_start,
                "actual_end": task.actual_end,
            } for task in order.tasks or []],
            "evidence": [{"id": row.id, "file_name": row.file_name, "task_card_id": row.task_card_id} for row in evidence],
            "release_gate": {
                "id": gate.id,
                "status": gate.status,
                "signed_off_at": gate.signed_off_at,
                "handed_to_records": gate.handed_to_records,
            } if gate else None,
            "crs": [{"id": row.id, "serial": row.crs_serial, "issue_date": row.crs_issue_date} for row in crs_rows],
        })
    manifest = {
        "schema": "amo-portal.records-handback.v1",
        "generated_at": _utcnow(),
        "package": package_services.package_read(package).model_dump(mode="json"),
        "planning_freeze": {"id": freeze.id, "version": freeze.version, "manifest_hash": freeze.manifest_hash},
        "execution_sessions": [{
            "id": session.id,
            "status": session.status,
            "started_at": session.started_at,
            "closed_at": session.closed_at,
            "events": len(session.events or []),
            "issues": len(session.issues or []),
        } for session in sessions],
        "orders": orders,
    }
    return manifest, readiness


def list_handbacks(db: Session, *, amo_id: str, package_id: int | None = None) -> list[HandbackRead]:
    query = db.query(RecordsHandbackPackage).filter(RecordsHandbackPackage.amo_id == amo_id)
    if package_id:
        query = query.filter(RecordsHandbackPackage.work_package_id == package_id)
    rows = query.order_by(RecordsHandbackPackage.updated_at.desc()).all()
    return [HandbackRead.model_validate(row) for row in rows]


def build_handback(
    db: Session,
    *,
    amo_id: str,
    payload: HandbackBuildRequest,
    actor: User,
) -> RecordsHandbackPackage:
    manifest, readiness = _handback_manifest(db, amo_id=amo_id, package_id=payload.work_package_id)
    freeze = _active_freeze(db, amo_id=amo_id, package_id=payload.work_package_id)
    version = db.query(RecordsHandbackPackage).filter(
        RecordsHandbackPackage.work_package_id == payload.work_package_id
    ).count() + 1
    row = RecordsHandbackPackage(
        amo_id=amo_id,
        work_package_id=payload.work_package_id,
        package_freeze_id=freeze.id,
        version=version,
        status="DRAFT",
        manifest_hash=_hash(manifest),
        manifest_json=manifest,
        readiness_json=readiness,
        created_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    db.add(RecordsHandbackEvent(
        amo_id=amo_id,
        handback_id=row.id,
        event_type="BUILD",
        to_status="DRAFT",
        notes=f"Manifest {row.manifest_hash}",
        actor_user_id=actor.id,
        created_at=_utcnow(),
    ))
    return row


def submit_handback(
    db: Session,
    *,
    handback: RecordsHandbackPackage,
    payload: HandbackSubmitRequest,
    actor: User,
) -> RecordsHandbackPackage:
    if handback.status not in {"DRAFT", "REJECTED"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected handbacks can be submitted")
    manifest, readiness = _handback_manifest(db, amo_id=handback.amo_id, package_id=handback.work_package_id)
    open_findings = [finding for finding in handback.findings or [] if finding.status == "OPEN"]
    if readiness["status"] != "READY" or open_findings:
        raise HTTPException(status_code=409, detail={"message": "Records handback is not ready", "readiness": readiness, "open_findings": [finding.id for finding in open_findings]})
    previous = handback.status
    handback.manifest_json = manifest
    handback.manifest_hash = _hash(manifest)
    handback.readiness_json = readiness
    handback.status = "SUBMITTED"
    handback.submitted_by_user_id = actor.id
    handback.submitted_at = _utcnow()
    db.add(handback)
    db.add(RecordsHandbackEvent(
        amo_id=handback.amo_id,
        handback_id=handback.id,
        event_type="SUBMIT",
        from_status=previous,
        to_status="SUBMITTED",
        notes=payload.submission_notes,
        actor_user_id=actor.id,
        created_at=_utcnow(),
    ))
    return handback


def add_finding(
    db: Session,
    *,
    handback: RecordsHandbackPackage,
    payload: HandbackFindingCreate,
    actor: User,
) -> RecordsHandbackFinding:
    if handback.status not in {"SUBMITTED", "UNDER_REVIEW", "REJECTED"}:
        raise HTTPException(status_code=409, detail="Findings can only be raised during records review")
    if handback.status == "SUBMITTED":
        handback.status = "UNDER_REVIEW"
        db.add(handback)
    finding = RecordsHandbackFinding(
        amo_id=handback.amo_id,
        handback_id=handback.id,
        category=payload.category,
        severity=payload.severity,
        description=payload.description,
        status="OPEN",
        raised_by_user_id=actor.id,
        raised_at=_utcnow(),
    )
    db.add(finding)
    db.flush()
    return finding


def resolve_finding(
    db: Session,
    *,
    amo_id: str,
    finding_id: str,
    payload: HandbackFindingResolve,
    actor: User,
) -> RecordsHandbackFinding:
    finding = db.query(RecordsHandbackFinding).filter(
        RecordsHandbackFinding.amo_id == amo_id,
        RecordsHandbackFinding.id == finding_id,
    ).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Records handback finding not found")
    if finding.status != "OPEN":
        raise HTTPException(status_code=409, detail="Finding is already resolved")
    finding.status = "RESOLVED"
    finding.response_notes = payload.response_notes
    finding.resolved_by_user_id = actor.id
    finding.resolved_at = _utcnow()
    db.add(finding)
    return finding


def review_handback(
    db: Session,
    *,
    handback: RecordsHandbackPackage,
    payload: HandbackReviewRequest,
    actor: User,
) -> RecordsHandbackPackage:
    if handback.status not in {"SUBMITTED", "UNDER_REVIEW"}:
        raise HTTPException(status_code=409, detail="Handback is not awaiting records review")
    open_findings = [finding for finding in handback.findings or [] if finding.status == "OPEN"]
    if payload.decision == "ACCEPT" and open_findings:
        raise HTTPException(status_code=409, detail="Resolve all records findings before acceptance")
    previous = handback.status
    handback.reviewed_by_user_id = actor.id
    handback.reviewed_at = _utcnow()
    handback.review_notes = payload.review_notes
    if payload.decision == "REJECT":
        handback.status = "REJECTED"
    else:
        readiness = _handback_readiness(db, amo_id=handback.amo_id, package_id=handback.work_package_id)
        if readiness["status"] != "READY":
            raise HTTPException(status_code=409, detail={"message": "Handback readiness changed before acceptance", "readiness": readiness})
        handback.status = "ACCEPTED"
        handback.accepted_at = _utcnow()
        package = package_services._get_package(db, amo_id=handback.amo_id, package_id=handback.work_package_id)
        package.status = "CLOSED"
        db.add(package)
        for link in package.order_links or []:
            gate = db.query(technical_record_models.ProductionReleaseGate).filter(
                technical_record_models.ProductionReleaseGate.amo_id == handback.amo_id,
                technical_record_models.ProductionReleaseGate.work_order_id == link.work_order_id,
            ).first()
            if gate:
                gate.handed_to_records = True
                gate.handed_to_records_at = _utcnow()
                db.add(gate)
    db.add(handback)
    db.add(RecordsHandbackEvent(
        amo_id=handback.amo_id,
        handback_id=handback.id,
        event_type="REVIEW",
        from_status=previous,
        to_status=handback.status,
        notes=payload.review_notes,
        actor_user_id=actor.id,
        created_at=_utcnow(),
    ))
    _audit(db, amo_id=handback.amo_id, actor_user_id=actor.id, entity_type="RecordsHandbackPackage", entity_id=handback.id, action="review", before={"status": previous}, after={"status": handback.status})
    return handback


def dashboard(db: Session, *, amo_id: str) -> ExecutionDashboardRead:
    return ExecutionDashboardRead(
        open_sessions=db.query(ProductionExecutionSession).filter(ProductionExecutionSession.amo_id == amo_id, ProductionExecutionSession.status == "OPEN").count(),
        blocked_sessions=db.query(ProductionExecutionSession).filter(ProductionExecutionSession.amo_id == amo_id, ProductionExecutionSession.status == "BLOCKED").count(),
        open_issues=db.query(ProductionTaskIssue).filter(ProductionTaskIssue.amo_id == amo_id, ProductionTaskIssue.status == "OPEN").count(),
        critical_issues=db.query(ProductionTaskIssue).filter(ProductionTaskIssue.amo_id == amo_id, ProductionTaskIssue.status == "OPEN", ProductionTaskIssue.severity == "CRITICAL").count(),
        draft_handbacks=db.query(RecordsHandbackPackage).filter(RecordsHandbackPackage.amo_id == amo_id, RecordsHandbackPackage.status == "DRAFT").count(),
        submitted_handbacks=db.query(RecordsHandbackPackage).filter(RecordsHandbackPackage.amo_id == amo_id, RecordsHandbackPackage.status.in_(["SUBMITTED", "UNDER_REVIEW"])).count(),
        rejected_handbacks=db.query(RecordsHandbackPackage).filter(RecordsHandbackPackage.amo_id == amo_id, RecordsHandbackPackage.status == "REJECTED").count(),
        accepted_handbacks=db.query(RecordsHandbackPackage).filter(RecordsHandbackPackage.amo_id == amo_id, RecordsHandbackPackage.status == "ACCEPTED").count(),
    )
