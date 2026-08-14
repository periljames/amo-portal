from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from amodb.apps.training.integration import training_record_summary

from .assurance_wiring_router import (
    SOURCE_REGISTRY,
    _priority_queue,
    _readiness,
    _safe_identifier,
    _table_columns,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence", tags=["Quality assurance metrics"])


# Canonical QMS tables guarantee due_date and payload even where a richer module
# migration has not added a purpose-specific validity column. Include the shared
# field in source resolution so evidence expiry remains usable across both shapes.
for _source_type in (
    "SUPPLIER",
    "SUPPLIER_APPROVAL",
    "CALIBRATION_CERTIFICATE",
    "REPORT",
):
    _spec = SOURCE_REGISTRY[_source_type]
    if "due_date" not in _spec.valid_until_fields:
        SOURCE_REGISTRY[_source_type] = replace(
            _spec,
            valid_until_fields=(*_spec.valid_until_fields, "due_date"),
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _count(
    db: Session,
    ctx: TenantContext,
    *,
    source: str,
    table: str,
    conditions: list[str] | None = None,
    params: dict[str, Any] | None = None,
    warnings: list[dict[str, str]],
) -> int:
    columns = _table_columns(db, table)
    if not columns:
        warnings.append({
            "source": source,
            "message": f"Authoritative source table '{table}' is unavailable.",
            "type": "SourceUnavailable",
        })
        return 0
    where = list(conditions or [])
    query_params: dict[str, Any] = dict(params or {})
    if "amo_id" in columns:
        where.insert(0, "amo_id = :amo_id")
        query_params["amo_id"] = ctx.amo_id
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    sql = f"SELECT COUNT(*) FROM {_safe_identifier(table)}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    try:
        with db.begin_nested():
            return int(db.execute(text(sql), query_params).scalar() or 0)
    except Exception as exc:
        warnings.append({"source": source, "message": str(exc), "type": exc.__class__.__name__})
        set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
        return 0


def _status_open_condition(columns: set[str]) -> str | None:
    if "status" not in columns:
        return None
    return "UPPER(COALESCE(status, 'OPEN')) NOT IN ('CLOSED','COMPLETED','COMPLETE','CANCELLED','REJECTED','ACCEPTED','RESOLVED','RETIRED','OBSOLETE')"


def _due_counts(
    db: Session,
    ctx: TenantContext,
    *,
    source: str,
    table: str,
    due_candidates: tuple[str, ...],
    warnings: list[dict[str, str]],
    open_only: bool = True,
) -> tuple[int, int]:
    columns = _table_columns(db, table)
    if not columns:
        warnings.append({
            "source": source,
            "message": f"Authoritative source table '{table}' is unavailable.",
            "type": "SourceUnavailable",
        })
        return 0, 0
    due_column = _first(columns, *due_candidates)
    if not due_column:
        warnings.append({
            "source": source,
            "message": f"Source table '{table}' has no supported due or validity column.",
            "type": "SourceShapeUnsupported",
        })
        return 0, 0
    base: list[str] = []
    status_condition = _status_open_condition(columns) if open_only else None
    if status_condition:
        base.append(status_condition)
    quoted_due = _safe_identifier(due_column)
    today = date.today()
    due_30 = today + timedelta(days=30)
    overdue = _count(
        db,
        ctx,
        source=f"{source}_overdue",
        table=table,
        conditions=[*base, f"{quoted_due} IS NOT NULL", f"{quoted_due} < :today"],
        params={"today": today},
        warnings=warnings,
    )
    upcoming = _count(
        db,
        ctx,
        source=f"{source}_due_30",
        table=table,
        conditions=[*base, f"{quoted_due} BETWEEN :today AND :due_30"],
        params={"today": today, "due_30": due_30},
        warnings=warnings,
    )
    return overdue, upcoming


def _risk_counts(db: Session, ctx: TenantContext, warnings: list[dict[str, str]]) -> tuple[int, int]:
    table = "qms_risks"
    columns = _table_columns(db, table)
    if not columns:
        warnings.append({"source": "risks", "message": "Risk register source is unavailable.", "type": "SourceUnavailable"})
        return 0, 0
    severity_column = _first(columns, "rating", "risk_level", "severity")
    if severity_column:
        expression = f"UPPER(COALESCE({_safe_identifier(severity_column)}, ''))"
    elif "payload" in columns:
        expression = "UPPER(COALESCE(payload->>'rating', payload->>'risk_level', payload->>'severity', ''))"
    else:
        warnings.append({"source": "risks", "message": "Risk severity is not represented in a supported field.", "type": "SourceShapeUnsupported"})
        return 0, 0
    open_condition = _status_open_condition(columns)
    base = [open_condition] if open_condition else []
    critical = _count(
        db,
        ctx,
        source="critical_risks",
        table=table,
        conditions=[*base, f"{expression} = 'CRITICAL'"],
        warnings=warnings,
    )
    high = _count(
        db,
        ctx,
        source="high_risks",
        table=table,
        conditions=[*base, f"{expression} = 'HIGH'"],
        warnings=warnings,
    )
    return critical, high


def _full_metrics(db: Session, ctx: TenantContext) -> tuple[dict[str, int], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    metrics: dict[str, int] = {}

    metrics["overdue_audits"], metrics["audits_due_30"] = _due_counts(
        db,
        ctx,
        source="audit_programme",
        table="qms_audit_schedules",
        due_candidates=("next_due_date", "due_date"),
        warnings=warnings,
    )
    metrics["overdue_cars"], metrics["cars_due_30"] = _due_counts(
        db,
        ctx,
        source="corrective_actions",
        table="quality_cars",
        due_candidates=("due_date", "target_close_date"),
        warnings=warnings,
    )
    car_columns = _table_columns(db, "quality_cars")
    car_open = _status_open_condition(car_columns)
    metrics["open_cars"] = _count(
        db,
        ctx,
        source="open_cars",
        table="quality_cars",
        conditions=[car_open] if car_open else [],
        warnings=warnings,
    )

    finding_columns = _table_columns(db, "qms_audit_findings")
    finding_condition = (
        "closed_at IS NULL"
        if "closed_at" in finding_columns
        else _status_open_condition(finding_columns)
    )
    metrics["open_findings"] = _count(
        db,
        ctx,
        source="open_findings",
        table="qms_audit_findings",
        conditions=[finding_condition] if finding_condition else [],
        warnings=warnings,
    )

    document_columns = _table_columns(db, "qms_documents")
    if "status" in document_columns:
        metrics["active_documents"] = _count(
            db,
            ctx,
            source="active_documents",
            table="qms_documents",
            conditions=["UPPER(status) IN ('ACTIVE','APPROVED','EFFECTIVE','PUBLISHED')"],
            warnings=warnings,
        )
        metrics["draft_documents"] = _count(
            db,
            ctx,
            source="draft_documents",
            table="qms_documents",
            conditions=["UPPER(status) IN ('DRAFT','PENDING_APPROVAL','UNDER_REVIEW')"],
            warnings=warnings,
        )
    else:
        metrics["active_documents"] = 0
        metrics["draft_documents"] = 0
        warnings.append({"source": "documents", "message": "Document status is unavailable.", "type": "SourceShapeUnsupported"})

    training_columns = _table_columns(db, "training_records")
    training_validity = _first(training_columns, "valid_until", "due_date")
    if training_validity:
        try:
            metrics["expired_training"] = training_record_summary(
                db,
                amo_id=ctx.amo_id,
                as_of=date.today(),
            ).expired
        except Exception as exc:
            db.rollback()
            metrics["expired_training"] = 0
            warnings.append({"source": "expired_training", "message": str(exc), "type": exc.__class__.__name__})
    else:
        metrics["expired_training"] = 0
    if training_columns and not training_validity:
        warnings.append({"source": "expired_training", "message": "Training validity is not represented in a supported field.", "type": "SourceShapeUnsupported"})

    metrics["expired_supplier_approvals"], metrics["supplier_approvals_due_30"] = _due_counts(
        db,
        ctx,
        source="supplier_approvals",
        table="qms_supplier_approvals",
        due_candidates=("valid_until", "expiry_date", "approval_expiry", "due_date"),
        warnings=warnings,
    )
    metrics["overdue_calibrations"], metrics["calibrations_due_30"] = _due_counts(
        db,
        ctx,
        source="calibration",
        table="qms_calibration_records",
        due_candidates=("next_due_date", "due_date", "valid_until"),
        warnings=warnings,
    )

    oot_columns = _table_columns(db, "qms_out_of_tolerance_events")
    oot_open = _status_open_condition(oot_columns)
    metrics["out_of_tolerance"] = _count(
        db,
        ctx,
        source="out_of_tolerance",
        table="qms_out_of_tolerance_events",
        conditions=[oot_open] if oot_open else [],
        warnings=warnings,
    )

    metrics["critical_risks"], metrics["high_risks"] = _risk_counts(db, ctx, warnings)

    change_columns = _table_columns(db, "qms_change_controls")
    change_open = _status_open_condition(change_columns)
    metrics["pending_changes"] = _count(
        db,
        ctx,
        source="pending_changes",
        table="qms_change_controls",
        conditions=[change_open] if change_open else [],
        warnings=warnings,
    )

    metrics["overdue_review_actions"], _ = _due_counts(
        db,
        ctx,
        source="management_review_actions",
        table="qms_management_review_actions",
        due_candidates=("due_date",),
        warnings=warnings,
    )

    regulator_columns = _table_columns(db, "qms_regulator_findings")
    regulator_open = _status_open_condition(regulator_columns)
    metrics["open_regulator_findings"] = _count(
        db,
        ctx,
        source="regulator_findings",
        table="qms_regulator_findings",
        conditions=[regulator_open] if regulator_open else [],
        warnings=warnings,
    )

    metrics["overdue_external_commitments"], _ = _due_counts(
        db,
        ctx,
        source="external_commitments",
        table="qms_external_commitments",
        due_candidates=("due_date",),
        warnings=warnings,
    )

    control_columns = _table_columns(db, "quality_assurance_controls")
    control_active = ["status = 'ACTIVE'"] if "status" in control_columns else []
    metrics["active_controls"] = _count(db, ctx, source="active_controls", table="quality_assurance_controls", conditions=control_active, warnings=warnings)
    metrics["approved_controls"] = _count(db, ctx, source="approved_controls", table="quality_assurance_controls", conditions=[*control_active, "approval_status = 'APPROVED'"], warnings=warnings)
    metrics["controls_due"] = _count(
        db,
        ctx,
        source="controls_due",
        table="quality_assurance_controls",
        conditions=[*control_active, "(next_test_due IS NULL OR next_test_due <= :due_30)"],
        params={"due_30": date.today() + timedelta(days=30)},
        warnings=warnings,
    )
    metrics["verified_controls"] = _count(
        db,
        ctx,
        source="verified_controls",
        table="quality_assurance_controls",
        conditions=[
            "EXISTS (SELECT 1 FROM quality_assurance_evidence_links e WHERE e.amo_id = quality_assurance_controls.amo_id AND e.control_id = quality_assurance_controls.id AND e.evidence_status = 'VERIFIED' AND (e.valid_until IS NULL OR e.valid_until >= :today))"
        ],
        params={"today": date.today()},
        warnings=warnings,
    )
    metrics["invalid_evidence"] = _count(
        db,
        ctx,
        source="invalid_evidence",
        table="quality_assurance_evidence_links",
        conditions=["evidence_status IN ('EXPIRED','REJECTED')"],
        warnings=warnings,
    )
    metrics["failed_control_tests"] = _count(
        db,
        ctx,
        source="failed_control_tests",
        table="quality_control_tests",
        conditions=["result IN ('FAIL','PARTIAL')", "tested_at >= NOW() - INTERVAL '365 days'"],
        warnings=warnings,
    )
    metrics["pending_assurance_events"] = _count(
        db,
        ctx,
        source="pending_assurance_events",
        table="quality_assurance_events",
        conditions=["processing_status = 'PENDING'"],
        warnings=warnings,
    )
    metrics["proposed_insights"] = _count(
        db,
        ctx,
        source="proposed_insights",
        table="quality_intelligence_reviews",
        conditions=["status = 'PROPOSED'"],
        warnings=warnings,
    )
    return metrics, warnings


@router.get("/overview/full")
def schema_aware_assurance_overview(
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, warnings = _full_metrics(db, ctx)
    pressure = sum(
        metrics.get(key, 0)
        for key in (
            "audits_due_30",
            "cars_due_30",
            "controls_due",
            "supplier_approvals_due_30",
            "calibrations_due_30",
        )
    )
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "as_of": _now().isoformat(),
        "readiness": _readiness(metrics),
        "metrics": metrics,
        "priority_queue": _priority_queue(metrics, ctx.amo_code),
        "forecast": {
            "commitments_due_30_days": pressure,
            "band": "HEAVY" if pressure >= 20 else "ELEVATED" if pressure >= 8 else "MANAGEABLE",
            "explanation": "Audit, CAR, control-test, supplier-approval and calibration commitments falling within 30 days.",
        },
        "capabilities": [
            {"id": "control-twin", "label": "Approved control twin", "description": "Versioned controls with ownership, evidence, approval and operating-effectiveness tests.", "path": f"/maintenance/{ctx.amo_code}/quality?hub=controls"},
            {"id": "evidence-graph", "label": "Validated evidence graph", "description": "Tenant-validated links that refresh when authoritative records change.", "path": f"/maintenance/{ctx.amo_code}/quality?hub=evidence"},
            {"id": "management-pack", "label": "Management-review pack", "description": "Current assurance exposure, decisions and evidence gaps prepared from live sources.", "path": f"/maintenance/{ctx.amo_code}/quality/management-review/dashboard"},
            {"id": "human-intelligence", "label": "Human-governed intelligence", "description": "Deterministic and future AI recommendations remain advisory until a named decision is recorded.", "path": f"/maintenance/{ctx.amo_code}/quality?hub=intelligence"},
        ],
        "source_coverage": {
            "available": sum(1 for spec in SOURCE_REGISTRY.values() if _table_columns(db, spec.table)),
            "warnings": len(warnings),
        },
        "warnings": warnings,
    }


@router.get("/management-review-pack")
def schema_aware_management_review_pack(
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, warnings = _full_metrics(db, ctx)
    readiness = _readiness(metrics)
    priorities = _priority_queue(metrics, ctx.amo_code)
    return {
        "generated_at": _now().isoformat(),
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "readiness": readiness,
        "executive_summary": [
            f"Operational readiness is {readiness['score']}% ({readiness['band'].replace('_', ' ').lower()}).",
            f"{metrics.get('overdue_cars', 0)} corrective actions and {metrics.get('overdue_audits', 0)} audit commitments are overdue.",
            f"{metrics.get('invalid_evidence', 0)} assurance relationships are expired or rejected.",
            f"{metrics.get('critical_risks', 0)} critical quality risks and {metrics.get('open_regulator_findings', 0)} regulator findings remain open.",
        ],
        "decisions_required": [
            {
                "title": item["label"],
                "reason": item["why"],
                "severity": item["severity"],
                "count": item["count"],
                "path": item["path"],
            }
            for item in priorities[:8]
        ],
        "metrics": metrics,
        "evidence_gaps": {
            "invalid_evidence": metrics.get("invalid_evidence", 0),
            "controls_due": metrics.get("controls_due", 0),
            "pending_events": metrics.get("pending_assurance_events", 0),
        },
        "source_warnings": warnings,
    }
