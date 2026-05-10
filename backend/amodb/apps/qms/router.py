from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path as FsPath
from typing import Any, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from amodb.apps.audit import services as audit_services
from amodb.apps.quality import models as quality_models
from amodb.apps.quality.enums import CARStatus, QMSAuditStatus, QMSDocStatus
from amodb.apps.training import models as training_models
from .security import TenantContext, assert_qms_permission, has_qms_permission, require_qms_permission, resolve_tenant_context, set_postgres_tenant_context


router = APIRouter(prefix="/api/maintenance/{amo_code}/qms", tags=["Canonical QMS"])
logger = logging.getLogger("amodb.qms")
_TABLE_COLUMNS_CACHE: dict[str, set[str]] = {}


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _as_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _is_open_status(value: Any) -> bool:
    status = (_as_text(value) or "").upper()
    return status not in {"CLOSED", "CANCELLED", "OBSOLETE", "REJECTED"}


def _row_id(value: Any) -> str:
    return str(getattr(value, "id", value))


def _event(module: str, entity_type: str, entity_id: str, title: str, when: Any, event_type: str, link: str | None = None) -> dict[str, Any]:
    return {
        "id": f"{module}:{entity_type}:{entity_id}:{event_type}",
        "module": module,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title,
        "date": _as_date(when),
        "event_type": event_type,
        "link": link,
    }


def _limit(qs, limit: int):
    return qs.limit(max(1, min(limit, 500)))


@router.get("/dashboard")
def qms_dashboard(
    ctx: TenantContext = Depends(require_qms_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if _is_postgres(db):
        db.execute(text("SET LOCAL statement_timeout = '12000ms'"))
    today = date.today()
    due_soon = today + timedelta(days=30)

    audit_qs = db.query(quality_models.QMSAudit).filter(quality_models.QMSAudit.amo_id == ctx.amo_id)
    car_qs = db.query(quality_models.CorrectiveActionRequest).filter(quality_models.CorrectiveActionRequest.amo_id == ctx.amo_id)
    document_qs = db.query(quality_models.QMSDocument).filter(quality_models.QMSDocument.amo_id == ctx.amo_id)
    finding_qs = db.query(quality_models.QMSAuditFinding).filter(quality_models.QMSAuditFinding.amo_id == ctx.amo_id)
    training_qs = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id)

    open_audits = audit_qs.filter(quality_models.QMSAudit.status != QMSAuditStatus.CLOSED).count()
    audits_due_soon = audit_qs.filter(
        quality_models.QMSAudit.planned_start.isnot(None),
        quality_models.QMSAudit.planned_start >= today,
        quality_models.QMSAudit.planned_start <= due_soon,
        quality_models.QMSAudit.status != QMSAuditStatus.CLOSED,
    ).count()
    active_fieldwork = audit_qs.filter(quality_models.QMSAudit.status == QMSAuditStatus.IN_PROGRESS).count()

    open_cars = car_qs.filter(quality_models.CorrectiveActionRequest.status.notin_([CARStatus.CLOSED, CARStatus.CANCELLED])).count()
    overdue_cars = car_qs.filter(
        quality_models.CorrectiveActionRequest.due_date.isnot(None),
        quality_models.CorrectiveActionRequest.due_date < today,
        quality_models.CorrectiveActionRequest.status.notin_([CARStatus.CLOSED, CARStatus.CANCELLED]),
    ).count()
    due_soon_cars = car_qs.filter(
        quality_models.CorrectiveActionRequest.due_date.isnot(None),
        quality_models.CorrectiveActionRequest.due_date >= today,
        quality_models.CorrectiveActionRequest.due_date <= due_soon,
        quality_models.CorrectiveActionRequest.status.notin_([CARStatus.CLOSED, CARStatus.CANCELLED]),
    ).count()

    draft_documents = document_qs.filter(quality_models.QMSDocument.status == QMSDocStatus.DRAFT).count()
    active_documents = document_qs.filter(quality_models.QMSDocument.status == QMSDocStatus.ACTIVE).count()
    open_findings = finding_qs.filter(quality_models.QMSAuditFinding.closed_at.is_(None)).count()
    overdue_training = training_qs.filter(
        training_models.TrainingRecord.valid_until.isnot(None),
        training_models.TrainingRecord.valid_until < today,
    ).count()

    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "source": "tenant_scoped_backend",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "counters": {
            "open_audits": open_audits,
            "audits_due_soon": audits_due_soon,
            "active_audit_fieldwork": active_fieldwork,
            "open_cars": open_cars,
            "overdue_cars": overdue_cars,
            "cars_due_soon": due_soon_cars,
            "open_findings": open_findings,
            "draft_documents": draft_documents,
            "active_documents": active_documents,
            "training_expired_records": overdue_training,
        },
        "links": {
            "open_cars": f"/maintenance/{ctx.amo_code}/qms/cars/overdue",
            "audits_due_soon": f"/maintenance/{ctx.amo_code}/qms/audits/schedule",
            "documents": f"/maintenance/{ctx.amo_code}/qms/documents/library",
            "training": f"/maintenance/{ctx.amo_code}/qms/training-competence/overdue",
        },
        "trace_id": trace_id,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@router.get("/inbox")
def qms_inbox(
    status_filter: str | None = Query(None, alias="status"),
    ctx: TenantContext = Depends(require_qms_permission("qms.inbox.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    qs = (
        db.query(quality_models.QMSNotification)
        .filter(
            quality_models.QMSNotification.amo_id == ctx.amo_id,
            quality_models.QMSNotification.user_id == ctx.user_id,
        )
        .order_by(quality_models.QMSNotification.created_at.desc())
    )
    if status_filter == "unread":
        qs = qs.filter(quality_models.QMSNotification.read_at.is_(None))
    rows = _limit(qs, 100).all()
    return {
        "items": [
            {
                "id": _row_id(row),
                "message": row.message,
                "severity": _as_text(row.severity),
                "created_at": _as_date(row.created_at),
                "read_at": _as_date(row.read_at),
            }
            for row in rows
        ]
    }


@router.get("/inbox/{view}")
def qms_inbox_view(
    view: str,
    ctx: TenantContext = Depends(require_qms_permission("qms.inbox.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    mapped_status = "unread" if view in {"assigned-to-me", "approvals", "overdue", "watching"} else None
    data = qms_inbox(status_filter=mapped_status, ctx=ctx, db=db)
    data["view"] = view
    return data


@router.get("/calendar")
def qms_calendar(
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
    ctx: TenantContext = Depends(require_qms_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if _is_postgres(db):
        db.execute(text("SET LOCAL statement_timeout = '12000ms'"))
    today = date.today()
    start_date = start or today - timedelta(days=30)
    end_date = end or today + timedelta(days=180)
    bounded_limit = max(1, min(limit, 200))
    bounded_offset = max(0, offset)
    source_limit = min(max(bounded_limit + bounded_offset + 10, 50), 250)

    events: list[dict[str, Any]] = []

    audits = (
        db.query(quality_models.QMSAudit)
        .filter(
            quality_models.QMSAudit.amo_id == ctx.amo_id,
            or_(
                quality_models.QMSAudit.planned_start.between(start_date, end_date),
                quality_models.QMSAudit.planned_end.between(start_date, end_date),
            ),
        )
        .limit(source_limit)
        .all()
    )
    for audit in audits:
        if audit.planned_start:
            events.append(_event("audits", "audit", _row_id(audit), audit.title, audit.planned_start, "audit_start", f"/maintenance/{ctx.amo_code}/qms/audits/{audit.id}/overview"))
        if audit.planned_end:
            events.append(_event("audits", "audit", _row_id(audit), audit.title, audit.planned_end, "audit_end", f"/maintenance/{ctx.amo_code}/qms/audits/{audit.id}/overview"))

    cars = (
        db.query(quality_models.CorrectiveActionRequest)
        .filter(
            quality_models.CorrectiveActionRequest.amo_id == ctx.amo_id,
            quality_models.CorrectiveActionRequest.due_date.between(start_date, end_date),
        )
        .limit(source_limit)
        .all()
    )
    for car in cars:
        events.append(_event("cars", "car", _row_id(car), car.title, car.due_date, "car_due", f"/maintenance/{ctx.amo_code}/qms/cars/{car.id}/overview"))

    training = (
        db.query(training_models.TrainingRecord, training_models.TrainingCourse)
        .outerjoin(training_models.TrainingCourse, training_models.TrainingRecord.course_id == training_models.TrainingCourse.id)
        .filter(
            training_models.TrainingRecord.amo_id == ctx.amo_id,
            training_models.TrainingRecord.valid_until.between(start_date, end_date),
        )
        .limit(source_limit)
        .all()
    )
    for record, course in training:
        course_label = None
        if course is not None:
            course_label = course.course_name or course.course_id
        events.append(_event("training-competence", "training_record", _row_id(record), f"Training expires: {course_label or record.course_id}", record.valid_until, "training_expiry", f"/maintenance/{ctx.amo_code}/qms/training-competence/people/{record.user_id}/course-history"))

    events.sort(key=lambda item: item["date"] or "")
    visible = events[bounded_offset:bounded_offset + bounded_limit]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info("QMS calendar read trace_id=%s amo=%s rows=%s elapsed_ms=%s", trace_id, ctx.amo_code, len(visible), elapsed_ms)
    return {
        "module": "calendar",
        "view": "list",
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "items": visible,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": bounded_offset + bounded_limit if len(events) > bounded_offset + bounded_limit else None,
        "has_more": len(events) > bounded_offset + bounded_limit,
        "trace_id": trace_id,
        "elapsed_ms": elapsed_ms,
    }


@router.get("/calendar/{view}")
def qms_calendar_view(
    view: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
    ctx: TenantContext = Depends(require_qms_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    if view in {"audits", "cars", "training", "management-review", "regulatory-deadlines"}:
        data = qms_calendar(start=start, end=end, limit=200, offset=0, ctx=ctx, db=db)
        filtered = [item for item in data.get("items", []) if item.get("module") == view or item.get("event_type", "").startswith(view.rstrip("s"))]
        bounded_limit = max(1, min(limit, 200))
        bounded_offset = max(0, offset)
        data["items"] = filtered[bounded_offset:bounded_offset + bounded_limit]
        data["limit"] = bounded_limit
        data["offset"] = bounded_offset
        data["has_more"] = len(filtered) > bounded_offset + bounded_limit
        data["next_offset"] = bounded_offset + bounded_limit if data["has_more"] else None
    else:
        data = qms_calendar(start=start, end=end, limit=limit, offset=offset, ctx=ctx, db=db)
    data["view"] = view
    return data


@router.get("/audits")
def list_audits(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.QMSAudit)
        .filter(quality_models.QMSAudit.amo_id == ctx.amo_id)
        .order_by(quality_models.QMSAudit.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "audit_ref": row.audit_ref,
                "title": row.title,
                "status": _as_text(row.status),
                "kind": _as_text(row.kind),
                "planned_start": _as_date(row.planned_start),
                "planned_end": _as_date(row.planned_end),
            }
            for row in rows
        ]
    }


@router.get("/findings")
def list_findings(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.finding.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.QMSAuditFinding)
        .filter(quality_models.QMSAuditFinding.amo_id == ctx.amo_id)
        .order_by(quality_models.QMSAuditFinding.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "finding_ref": row.finding_ref,
                "severity": _as_text(row.severity),
                "level": _as_text(row.level),
                "description": row.description,
                "closed_at": _as_date(row.closed_at),
                "target_close_date": _as_date(row.target_close_date),
            }
            for row in rows
        ]
    }


@router.get("/cars")
def list_cars(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.car.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.CorrectiveActionRequest)
        .filter(quality_models.CorrectiveActionRequest.amo_id == ctx.amo_id)
        .order_by(quality_models.CorrectiveActionRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "car_number": row.car_number,
                "title": row.title,
                "status": _as_text(row.status),
                "priority": _as_text(row.priority),
                "due_date": _as_date(row.due_date),
                "closed_at": _as_date(row.closed_at),
            }
            for row in rows
        ]
    }


@router.get("/documents")
def list_documents(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.document.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.QMSDocument)
        .filter(quality_models.QMSDocument.amo_id == ctx.amo_id)
        .order_by(quality_models.QMSDocument.updated_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "doc_code": row.doc_code,
                "title": row.title,
                "doc_type": _as_text(row.doc_type),
                "status": _as_text(row.status),
                "effective_date": _as_date(row.effective_date),
                "updated_at": _as_date(row.updated_at),
            }
            for row in rows
        ]
    }


@router.get("/training-competence/dashboard")
def training_dashboard(
    ctx: TenantContext = Depends(require_qms_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()
    due_soon = today + timedelta(days=30)
    total_records = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id).count()
    expired = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id, training_models.TrainingRecord.valid_until < today).count()
    expiring = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id, training_models.TrainingRecord.valid_until >= today, training_models.TrainingRecord.valid_until <= due_soon).count()
    return {"total_records": total_records, "expired_records": expired, "expiring_records": expiring}


@router.post("/reports/export")
def log_report_export(
    request: Request,
    ctx: TenantContext = Depends(require_qms_permission("qms.reports.export")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms.report",
        entity_id="export",
        action="export_requested",
        metadata={
            "module": "qms",
            "ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
        critical=True,
    )
    db.commit()
    return {"status": "logged", "message": "Report export request was logged. Actual export generation remains with the report service."}


@router.get("/settings")
def get_qms_settings(
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.execute(
        text("""
            SELECT id, numbering_rules, workflow_rules, approval_matrix, notification_rules,
                   retention_rules, risk_matrix, created_at, updated_at
            FROM qms_settings
            WHERE amo_id = :amo_id
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"amo_id": ctx.amo_id},
    ).mappings().first()
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "settings": dict(row) if row else None,
    }

# ---------------------------------------------------------------------------
# Phase 3/4 canonical QMS route registry
# ---------------------------------------------------------------------------

QMS_ROUTE_TREE: dict[str, dict[str, Any]] = {
    "cockpit": {
        "label": "QMS Cockpit",
        "path": "",
        "permission": "qms.dashboard.view",
        "children": [],
    },
    "inbox": {
        "label": "My QMS Work",
        "path": "inbox",
        "permission": "qms.inbox.view",
        "children": ["assigned-to-me", "approvals", "overdue", "watching", "completed"],
    },
    "calendar": {
        "label": "Calendar",
        "path": "calendar",
        "permission": "qms.calendar.view",
        "children": ["month", "week", "list", "audits", "cars", "training", "management-review", "regulatory-deadlines"],
    },
    "system": {
        "label": "System & Processes",
        "path": "system",
        "permission": "qms.risk.view",
        "children": [
            "overview", "qms-scope", "organization-context", "interested-parties", "process-map",
            "processes", "processes/:processId", "processes/:processId/risks",
            "processes/:processId/kpis", "processes/:processId/documents",
            "processes/:processId/audits", "quality-policy", "quality-objectives",
            "risk-register", "opportunities",
        ],
    },
    "documents": {
        "label": "Controlled Documents",
        "path": "documents",
        "permission": "qms.document.view",
        "children": [
            "library", "reader/:documentId", "reader/:documentId/sections/:sectionId",
            "change-requests", "change-requests/new", "change-requests/:changeRequestId",
            "approvals", "approval-letters", "templates", "forms", "obsolete",
            "revision-history", "distribution", "document-matrix",
        ],
    },
    "audits": {
        "label": "Audits",
        "path": "audits",
        "permission": "qms.audit.view",
        "children": [
            "dashboard", "program", "schedule", "calendar", "new", "templates", "checklists",
            "auditors", "auditor-competence", ":auditId/overview", ":auditId/planning",
            ":auditId/scope", ":auditId/team", ":auditId/notice", ":auditId/war-room",
            ":auditId/document-review", ":auditId/checklist", ":auditId/fieldwork",
            ":auditId/evidence", ":auditId/findings", ":auditId/post-brief", ":auditId/report",
            ":auditId/cars", ":auditId/follow-up", ":auditId/archive", ":auditId/activity-log",
        ],
    },
    "findings": {
        "label": "Findings",
        "path": "findings",
        "permission": "qms.finding.view",
        "children": [
            "register", "new", ":findingId/overview", ":findingId/evidence",
            ":findingId/classification", ":findingId/linked-cars",
            ":findingId/linked-documents", ":findingId/activity-log",
            "by-process", "by-severity", "by-source", "trends",
        ],
    },
    "cars": {
        "label": "CAR / CAPA",
        "path": "cars",
        "permission": "qms.car.view",
        "children": [
            "register", "new", "overdue", "due-soon", "awaiting-auditee",
            "awaiting-quality-review", "awaiting-effectiveness-review", "closed", "rejected",
            ":carId/overview", ":carId/containment", ":carId/root-cause",
            ":carId/corrective-action-plan", ":carId/implementation", ":carId/evidence",
            ":carId/quality-review", ":carId/effectiveness-review", ":carId/closure",
            ":carId/activity-log", "trends",
        ],
    },
    "risk": {
        "label": "Risk & Opportunities",
        "path": "risk",
        "permission": "qms.risk.view",
        "children": [
            "register", "new", ":riskId/overview", ":riskId/controls", ":riskId/actions",
            ":riskId/linked-findings", ":riskId/linked-audits", ":riskId/history",
            "risk-matrix", "opportunities", "treatment-plans", "trends",
        ],
    },
    "change-control": {
        "label": "Change Control",
        "path": "change-control",
        "permission": "qms.change.view",
        "children": [
            "register", "new", ":changeId/overview", ":changeId/impact-assessment",
            ":changeId/risk-assessment", ":changeId/approvals", ":changeId/implementation",
            ":changeId/post-implementation-review", ":changeId/activity-log",
            "pending-approval", "implemented", "rejected",
        ],
    },
    "training-competence": {
        "label": "Training & Competence",
        "path": "training-competence",
        "permission": "qms.training.view",
        "children": [
            "dashboard", "people", "people/:personId/profile", "people/:personId/course-history",
            "people/:personId/competence-matrix", "people/:personId/gaps",
            "people/:personId/export", "courses", "requirements", "matrix", "expiring",
            "overdue", "evaluations", "reports",
        ],
    },
    "suppliers": {
        "label": "Suppliers",
        "path": "suppliers",
        "permission": "qms.supplier.view",
        "children": [
            "approved-list", "new", ":supplierId/profile", ":supplierId/approvals",
            ":supplierId/scope", ":supplierId/evaluations", ":supplierId/audits",
            ":supplierId/findings", ":supplierId/performance", ":supplierId/documents",
            "evaluations", "supplier-audits", "supplier-findings", "performance-trends",
            "expired-approvals",
        ],
    },
    "equipment-calibration": {
        "label": "Equipment & Calibration",
        "path": "equipment-calibration",
        "permission": "qms.equipment.view",
        "children": [
            "register", "new", ":equipmentId/profile", ":equipmentId/calibration-history",
            ":equipmentId/certificates", ":equipmentId/maintenance",
            ":equipmentId/out-of-tolerance", ":equipmentId/activity-log", "due-soon",
            "overdue", "out-of-service", "reports",
        ],
    },
    "external-interface": {
        "label": "External Interface",
        "path": "external-interface",
        "permission": "qms.finding.view",
        "children": [
            "regulator-findings", "customer-complaints", "customer-feedback",
            "authority-correspondence", "responses", "commitments", "external-audits",
        ],
    },
    "management-review": {
        "label": "Management Review",
        "path": "management-review",
        "permission": "qms.management_review.view",
        "children": [
            "dashboard", "meetings", "meetings/new", "meetings/:reviewId/agenda",
            "meetings/:reviewId/inputs", "meetings/:reviewId/minutes",
            "meetings/:reviewId/decisions", "meetings/:reviewId/actions",
            "meetings/:reviewId/attachments", "meetings/:reviewId/approval",
            "actions", "open-actions", "closed-actions", "reports",
        ],
    },
    "reports": {
        "label": "Reports & Analytics",
        "path": "reports",
        "permission": "qms.reports.view",
        "children": [
            "executive-dashboard", "audit-performance", "car-performance", "finding-trends",
            "process-performance", "risk-trends", "supplier-performance", "training-compliance",
            "document-control", "management-review", "regulator-readiness", "custom-builder",
            "exports",
        ],
    },
    "evidence-vault": {
        "label": "Evidence Vault",
        "path": "evidence-vault",
        "permission": "qms.evidence.view",
        "children": [
            "search", "audit-packages", "car-packages", "document-approval-packages",
            "management-review-packages", "regulator-packages", "immutable-archive",
            "retention",
        ],
    },
    "settings": {
        "label": "QMS Settings",
        "path": "settings",
        "permission": "qms.settings.view",
        "children": [
            "general", "numbering", "workflow-rules", "approval-matrix", "roles-permissions",
            "notification-rules", "templates", "forms", "risk-matrix",
            "finding-classifications", "car-rules", "retention-rules", "integrations",
            "audit-log",
        ],
    },
}


# ---------------------------------------------------------------------------
# Phase 2 production consolidation: generic canonical QMS module endpoints
# ---------------------------------------------------------------------------

_MODULES: dict[str, dict[str, Any]] = {
    "documents": {
        "permission": "qms.document.view",
        "manage_permission": "qms.document.create",
        "default_table": "qms_documents",
        "views": {
            "library": "qms_documents",
            "reader": "qms_documents",
            "change-requests": "qms_document_change_requests",
            "approvals": "qms_document_approvals",
            "approval-letters": "qms_document_approval_letters",
            "templates": "qms_document_templates",
            "forms": "qms_form_definitions",
            "obsolete": "qms_document_obsolete_records",
            "revision-history": "qms_document_versions",
            "distribution": "qms_document_distribution",
            "document-matrix": "qms_documents",
        },
    },
    "audits": {
        "permission": "qms.audit.view",
        "manage_permission": "qms.audit.update",
        "default_table": "qms_audits",
        "views": {
            "dashboard": "qms_audits",
            "program": "qms_audit_programs",
            "schedule": "qms_audit_schedules",
            "calendar": "qms_audit_schedules",
            "templates": "qms_audit_checklists",
            "checklists": "qms_audit_checklists",
            "auditors": "qms_audit_team_members",
            "auditor-competence": "qms_audit_team_members",
            "overview": "qms_audits",
            "planning": "qms_audits",
            "scope": "qms_audit_scopes",
            "team": "qms_audit_team_members",
            "notice": "qms_audit_notices",
            "war-room": "qms_audit_war_room_files",
            "document-review": "qms_audit_evidence",
            "checklist": "qms_audit_checklists",
            "fieldwork": "qms_audit_evidence",
            "evidence": "qms_audit_evidence",
            "findings": "qms_audit_findings",
            "post-brief": "qms_audit_post_briefs",
            "report": "qms_audit_reports",
            "cars": "quality_cars",
            "follow-up": "qms_corrective_actions",
            "archive": "qms_audit_archives",
            "activity-log": "qms_activity_logs",
        },
    },
    "findings": {
        "permission": "qms.finding.view",
        "manage_permission": "qms.finding.create",
        "default_table": "qms_audit_findings",
        "views": {
            "register": "qms_audit_findings",
            "overview": "qms_audit_findings",
            "evidence": "qms_finding_evidence",
            "classification": "qms_finding_classifications",
            "linked-cars": "quality_cars",
            "linked-documents": "qms_documents",
            "activity-log": "qms_activity_logs",
            "by-process": "qms_audit_findings",
            "by-severity": "qms_audit_findings",
            "by-source": "qms_audit_findings",
            "trends": "qms_audit_findings",
        },
    },
    "cars": {
        "permission": "qms.car.view",
        "manage_permission": "qms.car.issue",
        "default_table": "quality_cars",
        "views": {
            "register": "quality_cars",
            "new": "quality_cars",
            "overdue": "quality_cars",
            "due-soon": "quality_cars",
            "awaiting-auditee": "quality_cars",
            "awaiting-quality-review": "quality_cars",
            "awaiting-effectiveness-review": "quality_cars",
            "closed": "quality_cars",
            "rejected": "quality_cars",
            "overview": "quality_cars",
            "containment": "qms_car_containment_actions",
            "root-cause": "qms_car_root_causes",
            "corrective-action-plan": "qms_car_corrective_action_plans",
            "implementation": "qms_car_action_items",
            "evidence": "qms_car_evidence",
            "quality-review": "qms_car_reviews",
            "effectiveness-review": "qms_car_effectiveness_reviews",
            "closure": "qms_car_closure_records",
            "activity-log": "qms_activity_logs",
            "trends": "quality_cars",
        },
    },
    "training-competence": {
        "permission": "qms.training.view",
        "manage_permission": "qms.training.manage",
        "default_table": "training_records",
        "views": {
            "dashboard": "training_records",
            "people": "users",
            "profile": "users",
            "course-history": "training_records",
            "competence-matrix": "qms_competence_matrix",
            "gaps": "qms_competence_gaps",
            "courses": "training_courses",
            "requirements": "training_requirements",
            "matrix": "qms_competence_matrix",
            "expiring": "training_records",
            "overdue": "training_records",
            "evaluations": "qms_training_evaluations",
            "reports": "training_records",
        },
    },
    "system": {
        "permission": "qms.risk.view",
        "manage_permission": "qms.risk.manage",
        "default_table": "qms_processes",
        "views": {
            "overview": "qms_processes",
            "processes": "qms_processes",
            "quality-objectives": "qms_quality_objectives",
            "risk-register": "qms_risks",
            "opportunities": "qms_opportunities",
        },
    },
    "risk": {
        "permission": "qms.risk.view",
        "manage_permission": "qms.risk.manage",
        "default_table": "qms_risks",
        "views": {
            "register": "qms_risks",
            "treatment-plans": "qms_risk_actions",
            "actions": "qms_risk_actions",
            "opportunities": "qms_opportunities",
            "risk-matrix": "qms_settings",
            "trends": "qms_risks",
        },
    },
    "change-control": {
        "permission": "qms.change.view",
        "manage_permission": "qms.change.manage",
        "default_table": "qms_change_controls",
        "views": {
            "register": "qms_change_controls",
            "pending-approval": "qms_change_controls",
            "implemented": "qms_change_controls",
            "rejected": "qms_change_controls",
        },
    },
    "suppliers": {
        "permission": "qms.supplier.view",
        "manage_permission": "qms.supplier.manage",
        "default_table": "qms_suppliers",
        "views": {
            "approved-list": "qms_suppliers",
            "evaluations": "qms_supplier_evaluations",
            "supplier-audits": "qms_supplier_audits",
            "supplier-findings": "qms_supplier_findings",
            "performance-trends": "qms_supplier_performance_scores",
            "expired-approvals": "qms_supplier_approvals",
        },
    },
    "equipment-calibration": {
        "permission": "qms.equipment.view",
        "manage_permission": "qms.equipment.manage",
        "default_table": "qms_equipment",
        "views": {
            "register": "qms_equipment",
            "calibration-history": "qms_calibration_records",
            "certificates": "qms_calibration_certificates",
            "out-of-tolerance": "qms_out_of_tolerance_events",
            "due-soon": "qms_calibration_records",
            "overdue": "qms_calibration_records",
            "out-of-service": "qms_equipment",
            "reports": "qms_calibration_records",
        },
    },
    "external-interface": {
        "permission": "qms.finding.view",
        "manage_permission": "qms.finding.create",
        "default_table": "qms_external_items",
        "views": {
            "regulator-findings": "qms_regulator_findings",
            "customer-complaints": "qms_customer_complaints",
            "customer-feedback": "qms_customer_feedback",
            "authority-correspondence": "qms_authority_correspondence",
            "responses": "qms_external_responses",
            "commitments": "qms_external_commitments",
            "external-audits": "qms_external_audits",
        },
    },
    "management-review": {
        "permission": "qms.management_review.view",
        "manage_permission": "qms.management_review.manage",
        "default_table": "qms_management_reviews",
        "views": {
            "dashboard": "qms_management_reviews",
            "meetings": "qms_management_reviews",
            "inputs": "qms_management_review_inputs",
            "minutes": "qms_management_review_minutes",
            "decisions": "qms_management_review_decisions",
            "actions": "qms_management_review_actions",
            "open-actions": "qms_management_review_actions",
            "closed-actions": "qms_management_review_actions",
            "reports": "qms_management_reviews",
        },
    },
    "reports": {
        "permission": "qms.reports.view",
        "manage_permission": "qms.reports.export",
        "default_table": "qms_report_exports",
        "views": {
            "executive-dashboard": "qms_dashboard_widgets",
            "audit-performance": "qms_report_exports",
            "car-performance": "qms_report_exports",
            "finding-trends": "qms_report_exports",
            "process-performance": "qms_report_exports",
            "risk-trends": "qms_report_exports",
            "supplier-performance": "qms_report_exports",
            "training-compliance": "qms_report_exports",
            "document-control": "qms_report_exports",
            "management-review": "qms_report_exports",
            "regulator-readiness": "qms_report_exports",
            "custom-builder": "qms_report_definitions",
            "exports": "qms_report_exports",
        },
    },
    "evidence-vault": {
        "permission": "qms.evidence.view",
        "manage_permission": "qms.evidence.archive",
        "default_table": "qms_archive_packages",
        "views": {
            "search": "qms_evidence_files",
            "audit-packages": "qms_archive_packages",
            "car-packages": "qms_archive_packages",
            "document-approval-packages": "qms_archive_packages",
            "management-review-packages": "qms_archive_packages",
            "regulator-packages": "qms_archive_packages",
            "immutable-archive": "qms_archive_packages",
            "retention": "qms_retention_rules",
            "files": "qms_evidence_files",
        },
    },
    "settings": {
        "permission": "qms.settings.view",
        "manage_permission": "qms.settings.manage",
        "default_table": "qms_settings",
        "views": {
            "general": "qms_settings",
            "numbering": "qms_numbering_rules",
            "workflow-rules": "qms_workflow_rules",
            "approval-matrix": "qms_approval_matrix",
            "roles-permissions": "qms_settings",
            "notification-rules": "qms_notification_rules",
            "templates": "qms_templates",
            "forms": "qms_form_definitions",
            "risk-matrix": "qms_settings",
            "finding-classifications": "qms_finding_classifications",
            "car-rules": "qms_workflow_rules",
            "retention-rules": "qms_retention_rules",
            "integrations": "qms_settings",
            "audit-log": "qms_activity_logs",
        },
    },
}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe database identifier.")
    return name


def _module_config(module: str) -> dict[str, Any]:
    try:
        return _MODULES[module]
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown QMS module '{module}'.")


def _resolve_view(module: str, parts: list[str]) -> str | None:
    """Resolve the semantic view/action from a nested QMS URL.

    Examples:
    - cars/overdue -> overdue
    - cars/{carId}/root-cause -> root-cause
    - documents/reader/{documentId}/sections/{sectionId} -> reader
    """
    config = _module_config(module)
    views = set(config.get("views", {}).keys())
    for part in parts:
        if part in {"new"}:
            return None
        if part in views:
            return part
    return None


def _resolve_table(module: str, view: str | None = None) -> str:
    config = _module_config(module)
    table = config.get("views", {}).get(view or "", config["default_table"])
    return _safe_identifier(str(table))


def _record_id_from_parts(parts: list[str], table: str, module: str | None = None) -> str | None:
    skip = {
        "overview", "profile", "history", "actions", "documents", "audits", "findings",
        "approvals", "scope", "performance", "activity-log", "register", "dashboard",
        "new", "reports", "trends", "search", "retention", "approved-list", "evaluations",
        "supplier-audits", "supplier-findings", "performance-trends", "expired-approvals",
        "pending-approval", "implemented", "rejected", "overdue", "due-soon",
        "awaiting-auditee", "awaiting-quality-review", "awaiting-effectiveness-review",
        "closed", "open-actions", "closed-actions", "templates", "checklists",
        "auditors", "auditor-competence", "library", "reader", "sections", "forms",
        "obsolete", "revision-history", "distribution", "document-matrix", "month",
        "week", "list", "training", "management-review", "regulatory-deadlines",
    }
    if module and module in _MODULES:
        skip.update(_MODULES[module].get("views", {}).keys())
    for part in parts:
        if part in skip:
            continue
        if re.fullmatch(r"[0-9a-fA-F-]{32,36}", part) or part.startswith("ID-") or len(part) >= 18:
            return part
    return None


def _json_value(value: Any) -> str:
    return json.dumps(value, default=str)


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _ensure_postgres(db: Session) -> None:
    if not _is_postgres(db):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Canonical QMS modules require PostgreSQL.")


def _check_permission(ctx: TenantContext, db: Session, permission: str) -> None:
    # Superuser and the dependency-based high-risk paths are handled before this helper.
    # For generic endpoints we deliberately fail closed when called outside the router dependency.
    return None


def _table_columns(db: Session, table: str) -> set[str]:
    _ensure_postgres(db)
    cached = _TABLE_COLUMNS_CACHE.get(table)
    if cached is not None:
        return cached
    rows = db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
        """),
        {"table": table},
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"QMS table '{table}' is missing. Run the canonical QMS migration before using this module.",
        )
    columns = set(rows)
    _TABLE_COLUMNS_CACHE[table] = columns
    return columns


def _sort_column(columns: set[str]) -> str:
    for candidate in ("updated_at", "created_at", "due_date", "planned_start", "valid_until", "id"):
        if candidate in columns:
            return candidate
    return sorted(columns)[0]


def _select_columns(columns: set[str]) -> list[str]:
    preferred = [
        "id", "audit_ref", "car_number", "finding_ref", "doc_code", "course_code", "reference",
        "title", "name", "message", "description", "summary", "status", "severity", "kind", "doc_type",
        "owner_user_id", "lead_auditor_user_id", "assigned_to_user_id", "user_id",
        "planned_start", "planned_end", "due_date", "valid_until", "effective_date",
        "created_at", "updated_at", "closed_at", "read_at",
    ]
    selected = [column for column in preferred if column in columns]
    if "payload" in columns:
        selected.append("payload")
    if not selected and "id" in columns:
        selected.append("id")
    return selected[:24]


def _select_records(
    db: Session,
    *,
    table: str,
    amo_id: str,
    record_id: str | None,
    limit: int,
    offset: int = 0,
    view: str | None = None,
    q: str | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    columns = _table_columns(db, table)
    order_column = _sort_column(columns)
    projected_columns = _select_columns(columns)
    where = ["amo_id = :amo_id"] if "amo_id" in columns else ["1 = 1"]
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    bounded_limit = max(1, min(limit, 50))
    bounded_offset = max(0, min(offset, 100_000))
    params: dict[str, Any] = {"amo_id": amo_id, "limit": bounded_limit + 1, "offset": bounded_offset}
    if record_id and "id" in columns:
        where.append("id = :record_id")
        params["record_id"] = record_id
    if q:
        searchable = [column for column in ("title", "name", "message", "description", "summary", "audit_ref", "car_number", "finding_ref", "doc_code", "reference") if column in columns]
        if searchable:
            where.append("(" + " OR ".join(f"CAST({column} AS TEXT) ILIKE :q" for column in searchable) + ")")
            params["q"] = f"%{q[:80]}%"
    if status_filter and "status" in columns:
        where.append("status = :status_filter")
        params["status_filter"] = status_filter.upper().replace(" ", "_")
    today = date.today()
    due_soon = today + timedelta(days=30)
    if view in {"pending-approval"} and "status" in columns:
        where.append("status IN ('PENDING_APPROVAL', 'DRAFT', 'OPEN')")
    elif view in {"awaiting-auditee", "awaiting-quality-review", "awaiting-effectiveness-review"} and "status" in columns:
        where.append("status IN ('AWAITING_AUDITEE', 'AWAITING_QUALITY_REVIEW', 'AWAITING_EFFECTIVENESS_REVIEW', 'PENDING_REVIEW', 'OPEN')")
    elif view in {"implemented", "closed", "closed-actions"} and "status" in columns:
        where.append("status IN ('IMPLEMENTED', 'CLOSED', 'APPROVED', 'COMPLETE', 'COMPLETED')")
    elif view in {"rejected"} and "status" in columns:
        where.append("status = 'REJECTED'")
    elif view in {"open-actions"} and "status" in columns:
        where.append("status NOT IN ('CLOSED', 'COMPLETE', 'COMPLETED', 'REJECTED', 'CANCELLED')")
    due_column = "due_date" if "due_date" in columns else "valid_until" if "valid_until" in columns else None
    if view == "overdue" and due_column:
        where.append(f"{due_column} < :today")
        params["today"] = today
    elif view in {"due-soon", "expiring", "expired-approvals"} and due_column:
        where.append(f"{due_column} >= :today AND {due_column} <= :due_soon")
        params["today"] = today
        params["due_soon"] = due_soon
    select_sql = ", ".join(_safe_identifier(column) for column in projected_columns) or "id"
    sql = f"""
        SELECT {select_sql}
        FROM {_safe_identifier(table)}
        WHERE {' AND '.join(where)}
        ORDER BY {_safe_identifier(order_column)} DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    rows = [dict(row) for row in db.execute(text(sql), params).mappings().all()]
    has_more = len(rows) > bounded_limit
    if has_more:
        rows = rows[:bounded_limit]
    return {
        "items": rows,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": bounded_offset + bounded_limit if has_more else None,
        "has_more": has_more,
        "columns": projected_columns,
    }


def _insert_record(db: Session, *, table: str, amo_id: str, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    columns = _table_columns(db, table)
    record_id = str(uuid.uuid4())
    payload_data = payload.get("payload") if isinstance(payload.get("payload"), dict) else {
        key: value for key, value in payload.items()
        if key not in {"title", "name", "status", "owner_user_id", "due_date", "description", "source_type"}
    }
    values: dict[str, Any] = {
        "id": record_id,
        "amo_id": amo_id,
        "created_by": actor_user_id,
        "updated_by": actor_user_id,
    }
    for key in ("title", "name", "status", "owner_user_id", "due_date", "description", "source_type", "file_name", "file_path", "storage_path", "sha256", "mime_type", "size_bytes"):
        if key in columns and key in payload:
            values[key] = payload[key]
    if "payload" in columns:
        values["payload"] = _json_value(payload_data)
    insert_cols = [key for key in values if key in columns]
    placeholders = [f":{key}" if key != "payload" else "CAST(:payload AS jsonb)" for key in insert_cols]
    sql = f"INSERT INTO {_safe_identifier(table)} ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)}) RETURNING *"
    row = db.execute(text(sql), values).mappings().first()
    return dict(row) if row else {"id": record_id}


def _update_record(db: Session, *, table: str, amo_id: str, actor_user_id: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    columns = _table_columns(db, table)
    allowed = {"title", "name", "status", "owner_user_id", "due_date", "description", "source_type", "file_name", "file_path", "storage_path", "sha256", "mime_type", "size_bytes", "payload"}
    updates = []
    params: dict[str, Any] = {"id": record_id, "amo_id": amo_id, "updated_by": actor_user_id}
    for key, value in payload.items():
        if key not in allowed or key not in columns:
            continue
        params[key] = _json_value(value) if key == "payload" else value
        updates.append(f"{key} = CAST(:{key} AS jsonb)" if key == "payload" else f"{key} = :{key}")
    if "updated_at" in columns:
        updates.append("updated_at = NOW()")
    if "updated_by" in columns:
        updates.append("updated_by = :updated_by")
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported fields supplied for update.")
    sql = f"UPDATE {_safe_identifier(table)} SET {', '.join(updates)} WHERE id = :id AND amo_id = :amo_id RETURNING *"
    row = db.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record was not found in this tenant.")
    return dict(row)


def _soft_delete_record(db: Session, *, table: str, amo_id: str, actor_user_id: str, record_id: str) -> dict[str, Any]:
    columns = _table_columns(db, table)
    if "deleted_at" not in columns:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This table does not support soft deletion.")
    sql = f"""
        UPDATE {_safe_identifier(table)}
        SET deleted_at = NOW(), updated_at = NOW(), updated_by = :actor_user_id
        WHERE id = :id AND amo_id = :amo_id
        RETURNING id, deleted_at
    """
    row = db.execute(text(sql), {"id": record_id, "amo_id": amo_id, "actor_user_id": actor_user_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record was not found in this tenant.")
    return dict(row)


def _log_qms_activity(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    action: str,
    module: str,
    entity_type: str,
    entity_id: str,
    previous_value: Any = None,
    new_value: Any = None,
    request: Request | None = None,
) -> None:
    if not _is_postgres(db):
        return
    db.execute(
        text("""
            INSERT INTO qms_activity_logs
                (id, amo_id, actor_user_id, action, module, entity_type, entity_id,
                 previous_value, new_value, ip_address, user_agent, created_at)
            VALUES
                (:id, :amo_id, :actor_user_id, :action, :module, :entity_type, :entity_id,
                 CAST(:previous_value AS jsonb), CAST(:new_value AS jsonb), :ip_address, :user_agent, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "amo_id": amo_id,
            "actor_user_id": actor_user_id,
            "action": action,
            "module": module,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "previous_value": _json_value(previous_value),
            "new_value": _json_value(new_value),
            "ip_address": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent") if request else None,
        },
    )


@router.get("/activity-log")
def qms_activity_log(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = _select_records(db, table="qms_activity_logs", amo_id=ctx.amo_id, record_id=None, limit=limit)
    return {"module": "activity-log", "items": rows}



@router.get("/route-map")
def qms_route_map(
    ctx: TenantContext = Depends(require_qms_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    modules: list[dict[str, Any]] = []
    for key, meta in QMS_ROUTE_TREE.items():
        permission = str(meta["permission"])
        if has_qms_permission(db, ctx, permission):
            modules.append(
                {
                    "key": key,
                    "label": meta["label"],
                    "path": meta["path"],
                    "permission": permission,
                    "children": list(meta.get("children", [])),
                }
            )
    return {
        "base_path": f"/maintenance/{ctx.amo_code}/qms",
        "api_base_path": f"/api/maintenance/{ctx.amo_code}/qms",
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "modules": modules,
    }


@router.patch("/settings")
def update_qms_settings(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    current = db.execute(text("SELECT id FROM qms_settings WHERE amo_id = :amo_id ORDER BY created_at DESC LIMIT 1"), {"amo_id": ctx.amo_id}).mappings().first()
    allowed = {
        "numbering_rules",
        "workflow_rules",
        "approval_matrix",
        "notification_rules",
        "retention_rules",
        "risk_matrix",
    }
    values = {key: _json_value(payload.get(key, {})) for key in allowed if key in payload}
    if not values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported settings fields supplied.")
    if current:
        sets = ", ".join([f"{key} = CAST(:{key} AS jsonb)" for key in values] + ["updated_at = NOW()", "updated_by = :updated_by"])
        values.update({"id": current["id"], "amo_id": ctx.amo_id, "updated_by": ctx.user_id})
        row = db.execute(text(f"UPDATE qms_settings SET {sets} WHERE id = :id AND amo_id = :amo_id RETURNING *"), values).mappings().first()
    else:
        record_id = str(uuid.uuid4())
        insert_cols = ["id", "amo_id", "created_by", "updated_by"] + list(values.keys())
        insert_values = [":id", ":amo_id", ":created_by", ":updated_by"] + [f"CAST(:{key} AS jsonb)" for key in values.keys()]
        values.update({"id": record_id, "amo_id": ctx.amo_id, "created_by": ctx.user_id, "updated_by": ctx.user_id})
        row = db.execute(text(f"INSERT INTO qms_settings ({', '.join(insert_cols)}) VALUES ({', '.join(insert_values)}) RETURNING *"), values).mappings().first()
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="settings_changed", module="settings", entity_type="qms_settings", entity_id=str(row["id"]), new_value=dict(row), request=request)
    db.commit()
    return {"settings": dict(row)}



@router.get("/evidence-vault/files/{file_id}/download")
def download_evidence_file(
    file_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_qms_permission("qms.evidence.download")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.execute(
        text("""
            SELECT id, title, name, payload
            FROM qms_evidence_files
            WHERE id = :file_id
              AND amo_id = :amo_id
              AND deleted_at IS NULL
            LIMIT 1
        """),
        {"file_id": file_id, "amo_id": ctx.amo_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file was not found in this tenant.")

    payload = row.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    raw_path = payload.get("file_path") or payload.get("storage_path")
    if not raw_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Evidence file metadata has no storage path.")

    storage_root = FsPath(os.getenv("QMS_STORAGE_ROOT", "/storage/tenants")).resolve()
    candidate = FsPath(str(raw_path)).resolve()
    if storage_root not in candidate.parents and candidate != storage_root:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Evidence file path is outside the configured tenant storage root.")
    expected_segment = FsPath(str(ctx.amo_id))
    if str(ctx.amo_id) not in candidate.parts:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Evidence file path is not tenant scoped.")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file is missing from storage.")

    _log_qms_activity(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        action="file_downloaded",
        module="evidence-vault",
        entity_type="qms_evidence_files",
        entity_id=file_id,
        new_value={"file_path": str(candidate)},
        request=request,
    )
    db.execute(
        text("""
            INSERT INTO qms_file_access_logs
                (id, amo_id, title, name, status, source_type, payload, created_by, created_at)
            VALUES
                (:id, :amo_id, :title, :name, 'DOWNLOADED', 'evidence_file',
                 CAST(:payload AS jsonb), :created_by, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "amo_id": ctx.amo_id,
            "title": str(row.get("title") or row.get("name") or file_id),
            "name": str(row.get("name") or row.get("title") or file_id),
            "payload": _json_value({"file_id": file_id, "file_path": str(candidate), "ip": request.client.host if request.client else None}),
            "created_by": ctx.user_id,
        },
    )
    db.commit()
    return FileResponse(path=str(candidate), filename=str(row.get("name") or row.get("title") or candidate.name))



_WORKFLOW_ACTIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("audits", "issue-notice"): {
        "permission": "qms.audit.update",
        "table": "qms_audit_notices",
        "action": "audit_notice_issued",
    },
    ("audits", "complete-fieldwork"): {
        "permission": "qms.audit.execute",
        "table": "qms_audit_evidence",
        "action": "audit_fieldwork_completed",
        "parent_table": "qms_audits",
        "parent_status": "IN_PROGRESS",
    },
    ("audits", "generate-report"): {
        "permission": "qms.audit.report.generate",
        "table": "qms_audit_reports",
        "action": "audit_report_generated",
    },
    ("audits", "archive"): {
        "permission": "qms.audit.archive",
        "table": "qms_audit_archives",
        "action": "audit_archived",
        "parent_table": "qms_audits",
        "parent_status": "CLOSED",
    },
    ("cars", "submit-root-cause"): {
        "permission": "qms.car.respond",
        "table": "qms_car_root_causes",
        "action": "car_root_cause_submitted",
        "parent_table": "quality_cars",
        "parent_status": "IN_PROGRESS",
    },
    ("cars", "submit-corrective-action"): {
        "permission": "qms.car.respond",
        "table": "qms_car_corrective_action_plans",
        "action": "car_corrective_action_submitted",
        "parent_table": "quality_cars",
        "parent_status": "IN_PROGRESS",
    },
    ("cars", "review"): {
        "permission": "qms.car.review",
        "table": "qms_car_reviews",
        "action": "car_reviewed",
        "parent_table": "quality_cars",
        "parent_status": "PENDING_VERIFICATION",
    },
    ("cars", "effectiveness-review"): {
        "permission": "qms.car.review",
        "table": "qms_car_effectiveness_reviews",
        "action": "car_effectiveness_reviewed",
        "parent_table": "quality_cars",
        "parent_status": "PENDING_VERIFICATION",
    },
    ("cars", "close"): {
        "permission": "qms.car.close",
        "table": "qms_car_closure_records",
        "action": "car_closed",
        "parent_table": "quality_cars",
        "parent_status": "CLOSED",
    },
    ("cars", "reject"): {
        "permission": "qms.car.reject",
        "table": "qms_car_rejections",
        "action": "car_rejected",
        "parent_table": "quality_cars",
        "parent_status": "ESCALATED",
    },
    ("documents", "versions"): {
        "permission": "qms.document.create",
        "table": "qms_document_versions",
        "action": "document_version_uploaded",
    },
    ("documents", "submit-approval"): {
        "permission": "qms.document.review",
        "table": "qms_document_approvals",
        "action": "document_approval_submitted",
        "parent_table": "qms_documents",
        "parent_status": "DRAFT",
    },
    ("documents", "approve"): {
        "permission": "qms.document.approve",
        "table": "qms_document_approvals",
        "action": "document_approved",
        "parent_table": "qms_documents",
        "parent_status": "ACTIVE",
    },
    ("documents", "publish"): {
        "permission": "qms.document.publish",
        "table": "qms_document_versions",
        "action": "document_published",
        "parent_table": "qms_documents",
        "parent_status": "ACTIVE",
    },
    ("documents", "obsolete"): {
        "permission": "qms.document.archive",
        "table": "qms_document_obsolete_records",
        "action": "document_obsoleted",
        "parent_table": "qms_documents",
        "parent_status": "OBSOLETE",
    },
}


def _update_parent_status(
    db: Session,
    *,
    table: str,
    amo_id: str,
    record_id: str,
    status_value: str,
    actor_user_id: str,
) -> dict[str, Any] | None:
    columns = _table_columns(db, table)
    if "status" not in columns:
        return None
    updates = ["status = :status"]
    params: dict[str, Any] = {
        "id": record_id,
        "amo_id": amo_id,
        "status": status_value,
        "updated_by": actor_user_id,
    }
    if "updated_at" in columns:
        updates.append("updated_at = NOW()")
    if "updated_by" in columns:
        updates.append("updated_by = :updated_by")
    row = db.execute(
        text(
            f"UPDATE {_safe_identifier(table)} SET {', '.join(updates)} "
            "WHERE id = :id AND amo_id = :amo_id RETURNING *"
        ),
        params,
    ).mappings().first()
    return dict(row) if row else None


@router.post("/{module}/{record_id}/{action}")
def qms_workflow_action(
    module: str,
    record_id: str,
    action: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    action_config = _WORKFLOW_ACTIONS.get((module, action))
    if not action_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported QMS workflow action.")
    assert_qms_permission(db, ctx, str(action_config["permission"]))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)

    table = str(action_config["table"])
    action_payload = dict(payload)
    action_payload.setdefault("source_type", module)
    action_payload.setdefault("title", action.replace("-", " ").title())
    action_payload["payload"] = {
        **(payload.get("payload") if isinstance(payload.get("payload"), dict) else {}),
        "parent_module": module,
        "parent_record_id": record_id,
        "workflow_action": action,
    }
    row = _insert_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, payload=action_payload)

    parent_update = None
    parent_table = action_config.get("parent_table")
    parent_status = action_config.get("parent_status")
    if parent_table and parent_status:
        parent_update = _update_parent_status(
            db,
            table=str(parent_table),
            amo_id=ctx.amo_id,
            record_id=record_id,
            status_value=str(parent_status),
            actor_user_id=ctx.user_id,
        )

    _log_qms_activity(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        action=str(action_config["action"]),
        module=module,
        entity_type=table,
        entity_id=str(row.get("id")),
        new_value={"workflow_record": row, "parent_update": parent_update},
        request=request,
    )
    db.commit()
    return {
        "module": module,
        "record_id": record_id,
        "action": action,
        "table": table,
        "workflow_record": row,
        "parent_update": parent_update,
    }


@router.get("/{module_path:path}")
def generic_qms_get(
    module_path: str,
    limit: int = Query(25, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100_000),
    q: str | None = Query(None, max_length=80),
    status_filter: str | None = Query(None, alias="status", max_length=40),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex[:12]
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        assert_qms_permission(db, ctx, "qms.dashboard.view")
        return qms_dashboard(ctx=ctx, db=db)
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config["permission"]))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    record_id = _record_id_from_parts(parts[1:], table, module)
    logger.info(
        "QMS module read started trace_id=%s amo=%s module=%s view=%s table=%s limit=%s offset=%s",
        trace_id, ctx.amo_code, module, view or "default", table, limit, offset,
    )
    try:
        if _is_postgres(db):
            db.execute(text("SET LOCAL statement_timeout = '12000ms'"))
        page = _select_records(
            db,
            table=table,
            amo_id=ctx.amo_id,
            record_id=record_id,
            limit=limit,
            offset=offset,
            view=view,
            q=q,
            status_filter=status_filter,
        )
        table_missing = False
        warning = None
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE and "QMS table" in detail and "is missing" in detail:
            page = {"items": [], "limit": max(1, min(limit, 50)), "offset": offset, "next_offset": None, "has_more": False, "columns": []}
            table_missing = True
            warning = detail
            logger.warning("QMS module read missing table trace_id=%s table=%s detail=%s", trace_id, table, detail)
        else:
            logger.exception("QMS module read failed trace_id=%s module=%s view=%s", trace_id, module, view or "default")
            raise
    except Exception as exc:
        logger.exception("QMS module read crashed trace_id=%s module=%s view=%s table=%s", trace_id, module, view or "default", table)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"QMS read failed for {module}/{view or 'default'} before a usable response was returned. Trace {trace_id}: {exc}",
        ) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "QMS module read finished trace_id=%s amo=%s module=%s view=%s rows=%s elapsed_ms=%s",
        trace_id, ctx.amo_code, module, view or "default", len(page.get("items", [])), elapsed_ms,
    )
    return {
        "module": module,
        "view": view or "default",
        "table": table,
        "record_id": record_id,
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "items": page["items"],
        "limit": page["limit"],
        "offset": page["offset"],
        "next_offset": page["next_offset"],
        "has_more": page["has_more"],
        "columns": page["columns"],
        "table_missing": table_missing,
        "warning": warning,
        "trace_id": trace_id,
        "elapsed_ms": elapsed_ms,
        "applied_filters": {"q": q or "", "status": status_filter or ""},
    }


@router.post("/{module_path:path}")
def generic_qms_create(
    module_path: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QMS module is required.")
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config.get("manage_permission") or config["permission"]))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    row = _insert_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, payload=payload)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="record_created", module=module, entity_type=table, entity_id=str(row.get("id")), new_value=row, request=request)
    db.commit()
    return {"module": module, "table": table, "record": row}


@router.patch("/{module_path:path}")
def generic_qms_update(
    module_path: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    parts = [part for part in module_path.split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config.get("manage_permission") or config["permission"]))
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    record_id = _record_id_from_parts(parts[1:], table, module)
    if not record_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    before_page = _select_records(db, table=table, amo_id=ctx.amo_id, record_id=record_id, limit=1)
    before = before_page.get("items", [])
    row = _update_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, record_id=record_id, payload=payload)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="record_updated", module=module, entity_type=table, entity_id=record_id, previous_value=before[0] if before else None, new_value=row, request=request)
    db.commit()
    return {"module": module, "table": table, "record": row}


@router.delete("/{module_path:path}")
def generic_qms_delete(
    module_path: str,
    request: Request,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    parts = [part for part in module_path.split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config.get("manage_permission") or "qms.settings.manage"))
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    record_id = _record_id_from_parts(parts[1:], table, module)
    if not record_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _soft_delete_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, record_id=record_id)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="record_deleted", module=module, entity_type=table, entity_id=record_id, new_value=row, request=request)
    db.commit()
    return {"module": module, "table": table, "deleted": row}
