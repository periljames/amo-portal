from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from . import models
from .assurance_metrics_router import _full_metrics
from .assurance_wiring_router import _safe_identifier, _table_columns
from .audit_checklist_template_models import QualityAuditChecklistBinding
from .audit_preparation_models import QualityAuditPreparationRevision
from .audit_risk_planning_router import _global_factors, _reliability_context
from .audit_source_link_models import QualityAuditSourceLink
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(tags=["Quality audit preparation context"])


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _enum(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _audit_dict(row: models.QMSAudit) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_ref": row.audit_ref,
        "title": row.title,
        "status": _enum(row.status),
        "kind": _enum(getattr(row, "kind", None)),
        "domain": _enum(getattr(row, "domain", None)),
        "audit_scope_id": str(getattr(row, "audit_scope_id", "") or "") or None,
        "scope": row.scope,
        "criteria": row.criteria,
        "planned_start": _jsonable(row.planned_start),
        "planned_end": _jsonable(row.planned_end),
        "actual_start": _jsonable(row.actual_start),
        "actual_end": _jsonable(row.actual_end),
        "lead_auditor_user_id": getattr(row, "lead_auditor_user_id", None),
        "observer_auditor_user_id": getattr(row, "observer_auditor_user_id", None),
        "assistant_auditor_user_id": getattr(row, "assistant_auditor_user_id", None),
        "location": getattr(row, "location", None),
    }


def _finding_dict(row: models.QMSAuditFinding) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "finding_ref": getattr(row, "finding_ref", None),
        "title": getattr(row, "title", None),
        "description": getattr(row, "description", None),
        "severity": _enum(getattr(row, "severity", None)),
        "classification": _enum(getattr(row, "classification", None)),
        "status": _enum(getattr(row, "status", None)),
        "requirement_ref": getattr(row, "requirement_ref", None),
        "closed_at": _jsonable(getattr(row, "closed_at", None)),
        "created_at": _jsonable(getattr(row, "created_at", None)),
    }


def _car_dict(row: models.CorrectiveActionRequest) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "finding_id": str(row.finding_id) if getattr(row, "finding_id", None) else None,
        "car_number": getattr(row, "car_number", None),
        "status": _enum(getattr(row, "status", None)),
        "due_date": _jsonable(getattr(row, "due_date", None)),
        "assigned_to_user_id": getattr(row, "assigned_to_user_id", None),
        "closed_at": _jsonable(getattr(row, "closed_at", None)),
    }


def _project_table(
    db: Session,
    *,
    table_names: tuple[str, ...],
    amo_id: str,
    audit_id: uuid.UUID,
    preferred_fields: tuple[str, ...],
    limit: int = 100,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    for table_name in table_names:
        columns = _table_columns(db, table_name)
        if not columns:
            continue
        if "audit_id" not in columns:
            warnings.append({"source": table_name, "type": "SchemaMismatch", "message": "Table exists but does not expose audit_id for preparation projection."})
            continue
        selected = [field for field in preferred_fields if field in columns]
        if "id" in columns and "id" not in selected:
            selected.insert(0, "id")
        if not selected:
            warnings.append({"source": table_name, "type": "SchemaMismatch", "message": "Table exists but no controlled preparation fields are projectable."})
            continue
        where = ["audit_id = :audit_id"]
        params: dict[str, Any] = {"audit_id": str(audit_id), "amo_id": amo_id, "limit": limit}
        if "amo_id" in columns:
            where.append("amo_id = :amo_id")
        order_column = "created_at" if "created_at" in columns else "id"
        sql = text(
            f"SELECT {', '.join(_safe_identifier(field) for field in selected)} "
            f"FROM {_safe_identifier(table_name)} WHERE {' AND '.join(where)} "
            f"ORDER BY {_safe_identifier(order_column)} DESC LIMIT :limit"
        )
        rows = db.execute(sql, params).mappings().all()
        return [{key: _jsonable(value) for key, value in row.items()} for row in rows], warnings
    return [], warnings


def _prior_audits(db: Session, *, current: models.QMSAudit, amo_id: str) -> list[models.QMSAudit]:
    query = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id != current.id,
        models.QMSAudit.deleted_at.is_(None),
    )
    scope_id = getattr(current, "audit_scope_id", None)
    if scope_id is not None and hasattr(models.QMSAudit, "audit_scope_id"):
        query = query.filter(models.QMSAudit.audit_scope_id == scope_id)
    elif getattr(current, "kind", None) is not None and hasattr(models.QMSAudit, "kind"):
        query = query.filter(models.QMSAudit.kind == current.kind)
    elif getattr(current, "domain", None) is not None and hasattr(models.QMSAudit, "domain"):
        query = query.filter(models.QMSAudit.domain == current.domain)
    order_column = getattr(models.QMSAudit, "actual_end", None) or models.QMSAudit.planned_end
    return query.order_by(desc(order_column)).limit(12).all()


@router.get("/audits/{audit_id}/preparation-context")
def get_audit_preparation_context(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")

    prior = _prior_audits(db, current=audit, amo_id=ctx.amo_id)
    prior_ids = [row.id for row in prior]
    finding_query = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.amo_id == ctx.amo_id)
    if prior_ids:
        finding_query = finding_query.filter(models.QMSAuditFinding.audit_id.in_(prior_ids))
        prior_findings = finding_query.order_by(desc(models.QMSAuditFinding.created_at)).limit(150).all()
    else:
        prior_findings = []
    finding_ids = [row.id for row in prior_findings]
    cars = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.finding_id.in_(finding_ids)
    ).limit(250).all() if finding_ids else []

    current_findings = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == ctx.amo_id,
        models.QMSAuditFinding.audit_id == audit.id,
    ).order_by(desc(models.QMSAuditFinding.created_at)).limit(150).all()

    latest_preparation = db.query(QualityAuditPreparationRevision).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit.id,
    ).order_by(QualityAuditPreparationRevision.revision_no.desc()).first()
    checklist_bindings = db.query(QualityAuditChecklistBinding).filter(
        QualityAuditChecklistBinding.amo_id == ctx.amo_id,
        QualityAuditChecklistBinding.audit_id == audit.id,
    ).order_by(QualityAuditChecklistBinding.applied_at.desc()).limit(20).all()

    occurrence = db.query(QMSPlannerScheduleMetadata).filter(
        QMSPlannerScheduleMetadata.amo_id == ctx.amo_id,
        QMSPlannerScheduleMetadata.audit_id == audit.id,
    ).first()
    schedule_id = occurrence.source_schedule_id if occurrence else None
    source_links = db.query(QualityAuditSourceLink).filter(
        QualityAuditSourceLink.amo_id == ctx.amo_id,
        QualityAuditSourceLink.schedule_id == schedule_id,
    ).order_by(QualityAuditSourceLink.created_at.asc()).all() if schedule_id else []

    document_requests, document_warnings = _project_table(
        db,
        table_names=("qms_audit_document_requests", "quality_audit_document_requests"),
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        preferred_fields=("id", "document_ref", "document_id", "title", "description", "status", "requested_from", "requested_at", "due_date", "received_at", "review_status", "notes", "created_at"),
    )
    meeting_records, meeting_warnings = _project_table(
        db,
        table_names=("qms_audit_opening_meetings", "qms_audit_meetings", "quality_audit_meetings"),
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        preferred_fields=("id", "meeting_type", "status", "scheduled_at", "held_at", "attendees", "agenda", "notes", "minutes", "created_at"),
        limit=25,
    )

    metrics, metric_warnings = _full_metrics(db, ctx)
    reliability, reliability_warnings = _reliability_context(db, ctx)
    global_factors = _global_factors(metrics, reliability)

    prior_finding_types: dict[str, int] = {}
    for finding in prior_findings:
        key = _enum(getattr(finding, "classification", None)) or _enum(getattr(finding, "severity", None)) or "UNCLASSIFIED"
        prior_finding_types[key] = prior_finding_types.get(key, 0) + 1

    unresolved_cars = [row for row in cars if (_enum(getattr(row, "status", None)) or "").upper() not in {"CLOSED", "CANCELLED"}]
    source_references: list[Any] = []
    if latest_preparation:
        source_references.extend(latest_preparation.source_references or [])
    for binding in checklist_bindings:
        source_references.extend(binding.source_references or [])
    source_references.extend({
        "source_type": link.source_type,
        "source_id": link.source_id,
        "source_route": link.source_route,
        "rationale": link.rationale,
    } for link in source_links)

    return {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "audit": _audit_dict(audit),
        "prior_audit_history": {
            "items": [_audit_dict(row) for row in prior],
            "matching_basis": "audit_scope_id" if getattr(audit, "audit_scope_id", None) else "kind/domain fallback",
        },
        "prior_findings": {
            "items": [_finding_dict(row) for row in prior_findings],
            "classification_counts": prior_finding_types,
            "total": len(prior_findings),
        },
        "car_exposure": {
            "items": [_car_dict(row) for row in cars],
            "open_count": len(unresolved_cars),
            "total": len(cars),
        },
        "current_findings": [_finding_dict(row) for row in current_findings],
        "document_requests": document_requests,
        "opening_meeting_records": meeting_records,
        "controlled_preparation": {
            "latest_revision": {
                "id": str(latest_preparation.id),
                "revision_no": latest_preparation.revision_no,
                "status": latest_preparation.status,
                "source_fingerprint": latest_preparation.source_fingerprint,
                "issued_at": _jsonable(latest_preparation.issued_at),
                "change_reason": latest_preparation.change_reason,
            } if latest_preparation else None,
            "checklist_bindings": [
                {
                    "id": str(binding.id),
                    "template_code": binding.template_code,
                    "revision_no": binding.revision_no,
                    "content_sha256": binding.content_sha256,
                    "applied_at": _jsonable(binding.applied_at),
                    "application_reason": binding.application_reason,
                }
                for binding in checklist_bindings
            ],
            "source_references": _jsonable(source_references),
        },
        "source_lineage": {
            "planner_schedule_id": str(schedule_id) if schedule_id else None,
            "items": [
                {
                    "source_type": link.source_type,
                    "source_id": link.source_id,
                    "source_route": link.source_route,
                    "rationale": link.rationale,
                    "source_snapshot": _jsonable(link.source_snapshot or {}),
                }
                for link in source_links
            ],
        },
        "cross_source_assurance_pressure": {
            "factors": global_factors,
            "authoritative_metrics": metrics,
            "reliability": reliability,
            "statement": "These are attributable AMO-level assurance pressures for auditor preparation, not an automated conclusion about this audit subject.",
        },
        "regulatory_and_manual_basis": {
            "audit_criteria": audit.criteria,
            "audit_scope": audit.scope,
            "source_references": _jsonable(source_references),
        },
        "data_quality": {
            "warnings": [*document_warnings, *meeting_warnings, *metric_warnings, *reliability_warnings],
            "statement": "Unavailable source systems are surfaced as warnings and are never silently interpreted as zero exposure.",
        },
    }
