from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from amodb.apps.training.integration import training_record_summary

from .assurance_wiring_router import (
    SOURCE_REGISTRY,
    _safe_identifier,
)
from .assurance_sources import source_columns, source_result, responsibility, query_scalar, require_source_access, SourceFailure
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence", tags=["Quality assurance metrics"])


def _score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _readiness(metrics: dict[str, int | None]) -> dict[str, Any]:
    if any(value is None for value in metrics.values()):
        return {
            "score": None, "band": "UNAVAILABLE", "dimensions": [],
            "method": "cross_module_continuous_assurance_v2",
            "disclaimer": "Readiness is unavailable while required source data is incomplete. This indicator supports operational review; organizational approval remains external.",
        }
    total_docs = metrics.get("active_documents", 0) + metrics.get("draft_documents", 0)
    active_controls = metrics.get("active_controls", 0)
    dimensions = {
        "audit_programme": _score(100 - metrics.get("overdue_audits", 0) * 18 - metrics.get("audits_due_30", 0) * 2),
        "capa_discipline": _score(100 - metrics.get("overdue_cars", 0) * 14 - max(0, metrics.get("open_cars", 0) - metrics.get("overdue_cars", 0)) * 2),
        "finding_control": _score(100 - metrics.get("open_findings", 0) * 4),
        "document_currency": _score(50 if total_docs == 0 else metrics.get("active_documents", 0) / total_docs * 100),
        "competence": _score(100 - metrics.get("expired_training", 0) * 10),
        "supplier_calibration": _score(100 - metrics.get("expired_supplier_approvals", 0) * 10 - metrics.get("overdue_calibrations", 0) * 10 - metrics.get("out_of_tolerance", 0) * 15),
        "risk_change": _score(100 - metrics.get("critical_risks", 0) * 18 - metrics.get("high_risks", 0) * 8 - metrics.get("pending_changes", 0) * 3),
        "continuous_controls": _score(25 if active_controls == 0 else (metrics.get("verified_controls", 0) / max(1, active_controls) * 70 + metrics.get("approved_controls", 0) / max(1, active_controls) * 30 - metrics.get("controls_due", 0) * 4 - metrics.get("failed_control_tests", 0) * 8)),
        "external_commitments": _score(100 - metrics.get("open_regulator_findings", 0) * 12 - metrics.get("overdue_external_commitments", 0) * 12),
        "management_review": _score(100 - metrics.get("overdue_review_actions", 0) * 10),
    }
    weights = {
        "audit_programme": 0.15,
        "capa_discipline": 0.15,
        "finding_control": 0.08,
        "document_currency": 0.08,
        "competence": 0.08,
        "supplier_calibration": 0.10,
        "risk_change": 0.10,
        "continuous_controls": 0.16,
        "external_commitments": 0.05,
        "management_review": 0.05,
    }
    overall = _score(sum(dimensions[key] * weights[key] for key in weights))
    band = "STRONG" if overall >= 85 else "WATCH" if overall >= 70 else "AT_RISK" if overall >= 50 else "CRITICAL"
    return {
        "score": overall,
        "band": band,
        "dimensions": [{"id": key, "label": key.replace("_", " ").title(), "score": dimensions[key], "weight": weights[key]} for key in weights],
        "method": "cross_module_continuous_assurance_v2",
        "disclaimer": "Readiness is a transparent operational indicator, not a regulatory compliance declaration.",
    }


def _priority_queue(metrics: dict[str, int | None], amo_code: str) -> list[dict[str, Any]]:
    candidates = [
        ("overdue-cars", "Overdue corrective actions", "overdue_cars", "CRITICAL", "Closure dates have passed while CAR records remain open.", f"/maintenance/{amo_code}/quality/cars/overdue"),
        ("regulator-findings", "Open regulator findings", "open_regulator_findings", "CRITICAL", "Authority findings remain open and require governed response evidence.", f"/maintenance/{amo_code}/quality/external-interface/regulator-findings"),
        ("overdue-audits", "Overdue audit commitments", "overdue_audits", "HIGH", "Approved audit programme dates have passed.", f"/maintenance/{amo_code}/quality/audits/plan?view=calendar"),
        ("calibration", "Overdue calibration", "overdue_calibrations", "HIGH", "Measuring or inspection equipment has passed its calibration due date.", f"/maintenance/{amo_code}/quality/equipment-calibration/overdue"),
        ("supplier-approval", "Expired supplier approvals", "expired_supplier_approvals", "HIGH", "Supplier approval evidence is no longer current.", f"/maintenance/{amo_code}/quality/suppliers/expired-approvals"),
        ("training", "Expired competence evidence", "expired_training", "HIGH", "Latest recurrent training or qualification validity has expired.", f"/maintenance/{amo_code}/quality/training-competence/overdue"),
        ("controls", "Controls needing retest", "controls_due", "HIGH", "Controls have no future test date or fall due within 30 days.", f"/maintenance/{amo_code}/quality?hub=controls"),
        ("evidence", "Invalid assurance evidence", "invalid_evidence", "HIGH", "Linked evidence is expired, rejected or no longer supported by its source.", f"/maintenance/{amo_code}/quality?hub=evidence"),
        ("risk", "Critical quality risks", "critical_risks", "HIGH", "Critical risks remain open without accepted treatment closure.", f"/maintenance/{amo_code}/quality/risk/register"),
        ("review", "Overdue management-review actions", "overdue_review_actions", "MEDIUM", "Management decisions have actions beyond their due date.", f"/maintenance/{amo_code}/quality/management-review/open-actions"),
        ("events", "Assurance updates awaiting reconciliation", "pending_assurance_events", "INFO", "Authoritative records changed and their control links need reconciliation.", f"/maintenance/{amo_code}/quality?hub=evidence"),
    ]
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    items = [
        {"id": item_id, "label": label, "count": metrics.get(metric, 0), "severity": severity, "why": why, "path": path}
        for item_id, label, metric, severity, why, path in candidates
        if metrics.get(metric) is not None and metrics[metric] > 0
    ]
    return sorted(items, key=lambda item: (rank[item["severity"]], -item["count"]))


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


def _projection_columns(db, table):
    return source_result(lambda: source_columns(db, table)).value or set()


def _count(
    db: Session,
    ctx: TenantContext,
    *,
    source: str,
    table: str,
    conditions: list[str] | None = None,
    params: dict[str, Any] | None = None,
    warnings: list[dict[str, str]],
    view: str = "global",
) -> int | None:
    def run():
        require_source_access(db, ctx, table)
        columns = source_columns(db, table)
        where = ["amo_id = :amo_id", *(conditions or [])]
        query_params = {**(params or {}), "amo_id": ctx.amo_id, "actor_user_id": ctx.user_id}
        if "deleted_at" in columns:
            where.append("deleted_at IS NULL")
        if table == "qms_audit_findings":
            source_columns(db, "qms_audits", ("id", "deleted_at"))
            where.append("EXISTS (SELECT 1 FROM qms_audits parent WHERE parent.id = qms_audit_findings.audit_id AND parent.amo_id = qms_audit_findings.amo_id AND parent.deleted_at IS NULL)")
        if view == "mine":
            scope = responsibility(db, table, columns)
            if scope == "1 = 0":
                raise SourceFailure("SOURCE_UNAVAILABLE", "This source has no supported personal responsibility projection.")
            where.append(scope)
        return query_scalar(db, f"SELECT COUNT(*) FROM {_safe_identifier(table)} WHERE " + " AND ".join(where), query_params)
    result = source_result(run)
    if result.status != "SUCCESS":
        warnings.append(result.warning(source))
    return result.value


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
    view: str = "global",
) -> tuple[int | None, int | None]:
    shape = source_result(lambda: source_columns(db, table))
    columns = shape.value or set()
    if not columns:
        warnings.append(shape.warning(source))
        return None, None
    due_column = _first(columns, *due_candidates)
    if not due_column:
        warnings.append({
            "source": source,
            "message": f"Source table '{table}' has no supported due or validity column.",
            "type": "SCHEMA_UNAVAILABLE",
        })
        return None, None
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
        warnings=warnings, view=view,
    )
    upcoming = _count(
        db,
        ctx,
        source=f"{source}_due_30",
        table=table,
        conditions=[*base, f"{quoted_due} BETWEEN :today AND :due_30"],
        params={"today": today, "due_30": due_30},
        warnings=warnings, view=view,
    )
    return overdue, upcoming


def _risk_counts(db: Session, ctx: TenantContext, warnings: list[dict[str, str]], view: str = "global") -> tuple[int | None, int | None]:
    table = "qms_risks"
    shape = source_result(lambda: source_columns(db, table))
    columns = shape.value or set()
    if not columns:
        warnings.append(shape.warning("risks"))
        return None, None
    severity_column = _first(columns, "rating", "risk_level", "severity")
    if severity_column:
        expression = f"UPPER(COALESCE({_safe_identifier(severity_column)}, ''))"
    elif "payload" in columns:
        expression = "UPPER(COALESCE(payload->>'rating', payload->>'risk_level', payload->>'severity', ''))"
    else:
        warnings.append({"source": "risks", "message": "Risk severity is not represented in a supported field.", "type": "SCHEMA_UNAVAILABLE"})
        return None, None
    open_condition = _status_open_condition(columns)
    base = [open_condition] if open_condition else []
    critical = _count(
        db,
        ctx,
        source="critical_risks",
        table=table,
        conditions=[*base, f"{expression} = 'CRITICAL'"],
        warnings=warnings, view=view,
    )
    high = _count(
        db,
        ctx,
        source="high_risks",
        table=table,
        conditions=[*base, f"{expression} = 'HIGH'"],
        warnings=warnings, view=view,
    )
    return critical, high


def _full_metrics(db: Session, ctx: TenantContext, *, view: str = "global") -> tuple[dict[str, int | None], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    metrics: dict[str, int | None] = {}

    metrics["overdue_audits"], metrics["audits_due_30"] = _due_counts(
        db,
        ctx,
        source="audit_programme",
        table="qms_audit_schedules",
        due_candidates=("next_due_date", "due_date"),
        warnings=warnings, view=view,
    )
    metrics["overdue_cars"], metrics["cars_due_30"] = _due_counts(
        db,
        ctx,
        source="corrective_actions",
        table="quality_cars",
        due_candidates=("due_date", "target_closure_date"),
        warnings=warnings, view=view,
    )
    car_columns = _projection_columns(db, "quality_cars")
    car_open = _status_open_condition(car_columns)
    metrics["open_cars"] = _count(
        db,
        ctx,
        source="open_cars",
        table="quality_cars",
        conditions=[car_open] if car_open else [],
        warnings=warnings, view=view,
    )

    finding_columns = _projection_columns(db, "qms_audit_findings")
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
        warnings=warnings, view=view,
    )

    document_columns = _projection_columns(db, "qms_documents")
    if "status" in document_columns:
        metrics["active_documents"] = _count(
            db,
            ctx,
            source="active_documents",
            table="qms_documents",
            conditions=["UPPER(status) IN ('ACTIVE','APPROVED','EFFECTIVE','PUBLISHED')"],
            warnings=warnings, view=view,
        )
        metrics["draft_documents"] = _count(
            db,
            ctx,
            source="draft_documents",
            table="qms_documents",
            conditions=["UPPER(status) IN ('DRAFT','PENDING_APPROVAL','UNDER_REVIEW')"],
            warnings=warnings, view=view,
        )
    else:
        metrics["active_documents"] = None
        metrics["draft_documents"] = None
        warnings.append({"source": "documents", "message": "Document status is unavailable.", "type": "SCHEMA_UNAVAILABLE"})

    def training_count():
        require_source_access(db, ctx, "training_records")
        source_columns(db, "training_records", ("valid_until",))
        # The integration resolves latest recurrent evidence. It has no personal
        # scope contract; never substitute a tenant aggregate for My Work.
        if view == "mine":
            from .assurance_sources import SourceFailure
            raise SourceFailure("SCHEMA_UNAVAILABLE", "Personal latest-training projection is not supported.")
        with db.begin_nested():
            return training_record_summary(db, amo_id=ctx.amo_id, as_of=date.today()).expired
    training = source_result(training_count)
    metrics["expired_training"] = training.value
    if training.status != "SUCCESS":
        warnings.append(training.warning("expired_training"))

    metrics["expired_supplier_approvals"], metrics["supplier_approvals_due_30"] = _due_counts(
        db,
        ctx,
        source="supplier_approvals",
        table="qms_supplier_approvals",
        due_candidates=("valid_until", "expiry_date", "approval_expiry", "due_date"),
        warnings=warnings, view=view,
    )
    metrics["overdue_calibrations"], metrics["calibrations_due_30"] = _due_counts(
        db,
        ctx,
        source="calibration",
        table="qms_calibration_records",
        due_candidates=("next_due_date", "due_date", "valid_until"),
        warnings=warnings, view=view,
    )

    oot_columns = _projection_columns(db, "qms_out_of_tolerance_events")
    oot_open = _status_open_condition(oot_columns)
    metrics["out_of_tolerance"] = _count(
        db,
        ctx,
        source="out_of_tolerance",
        table="qms_out_of_tolerance_events",
        conditions=[oot_open] if oot_open else [],
        warnings=warnings, view=view,
    )

    metrics["critical_risks"], metrics["high_risks"] = _risk_counts(db, ctx, warnings, view=view)

    change_columns = _projection_columns(db, "qms_change_controls")
    change_open = _status_open_condition(change_columns)
    metrics["pending_changes"] = _count(
        db,
        ctx,
        source="pending_changes",
        table="qms_change_controls",
        conditions=[change_open] if change_open else [],
        warnings=warnings, view=view,
    )

    metrics["overdue_review_actions"], _ = _due_counts(
        db,
        ctx,
        source="management_review_actions",
        table="qms_management_review_actions",
        due_candidates=("due_date",),
        warnings=warnings, view=view,
    )

    regulator_columns = _projection_columns(db, "qms_regulator_findings")
    regulator_open = _status_open_condition(regulator_columns)
    metrics["open_regulator_findings"] = _count(
        db,
        ctx,
        source="regulator_findings",
        table="qms_regulator_findings",
        conditions=[regulator_open] if regulator_open else [],
        warnings=warnings, view=view,
    )

    metrics["overdue_external_commitments"], _ = _due_counts(
        db,
        ctx,
        source="external_commitments",
        table="qms_external_commitments",
        due_candidates=("due_date",),
        warnings=warnings, view=view,
    )

    control_columns = _projection_columns(db, "quality_assurance_controls")
    control_active = ["status = 'ACTIVE'"] if "status" in control_columns else []
    metrics["active_controls"] = _count(db, ctx, source="active_controls", table="quality_assurance_controls", conditions=control_active, warnings=warnings, view=view)
    metrics["approved_controls"] = _count(db, ctx, source="approved_controls", table="quality_assurance_controls", conditions=[*control_active, "approval_status = 'APPROVED'"], warnings=warnings, view=view)
    metrics["controls_due"] = _count(
        db,
        ctx,
        source="controls_due",
        table="quality_assurance_controls",
        conditions=[*control_active, "(next_test_due IS NULL OR next_test_due <= :due_30)"],
        params={"due_30": date.today() + timedelta(days=30)},
        warnings=warnings, view=view,
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
        warnings=warnings, view=view,
    )
    metrics["invalid_evidence"] = _count(
        db,
        ctx,
        source="invalid_evidence",
        table="quality_assurance_evidence_links",
        conditions=["evidence_status IN ('EXPIRED','REJECTED')"],
        warnings=warnings, view=view,
    )
    metrics["failed_control_tests"] = _count(
        db,
        ctx,
        source="failed_control_tests",
        table="quality_control_tests",
        conditions=["result IN ('FAIL','PARTIAL')", "tested_at >= NOW() - INTERVAL '365 days'"],
        warnings=warnings, view=view,
    )
    metrics["pending_assurance_events"] = _count(
        db,
        ctx,
        source="pending_assurance_events",
        table="quality_assurance_events",
        conditions=["processing_status = 'PENDING'"],
        warnings=warnings, view=view,
    )
    metrics["proposed_insights"] = _count(
        db,
        ctx,
        source="proposed_insights",
        table="quality_intelligence_reviews",
        conditions=["status = 'PROPOSED'"],
        warnings=warnings, view=view,
    )
    return metrics, warnings


@router.get("/overview/full")
def schema_aware_assurance_overview(
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    metrics, warnings = _full_metrics(db, ctx)
    pressure_values = [
        metrics.get(key, 0)
        for key in (
            "audits_due_30",
            "cars_due_30",
            "controls_due",
            "supplier_approvals_due_30",
            "calibrations_due_30",
        )
    ]
    pressure = None if any(value is None for value in pressure_values) else sum(pressure_values)
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "as_of": _now().isoformat(),
        "readiness": _readiness(metrics),
        "metrics": metrics,
        "priority_queue": _priority_queue(metrics, ctx.amo_code),
        "forecast": {
            "commitments_due_30_days": pressure,
            "band": "UNAVAILABLE" if pressure is None else "HEAVY" if pressure >= 20 else "ELEVATED" if pressure >= 8 else "MANAGEABLE",
            "explanation": "Audit, CAR, control-test, supplier-approval and calibration commitments falling within 30 days.",
        },
        "capabilities": [
            {"id": "control-twin", "label": "Approved control twin", "description": "Versioned controls with ownership, evidence, approval and operating-effectiveness tests.", "path": f"/maintenance/{ctx.amo_code}/quality?hub=controls"},
            {"id": "evidence-graph", "label": "Validated evidence graph", "description": "Tenant-validated links that refresh when authoritative records change.", "path": f"/maintenance/{ctx.amo_code}/quality?hub=evidence"},
            {"id": "management-pack", "label": "Management-review pack", "description": "Current assurance exposure, decisions and evidence gaps prepared from live sources.", "path": f"/maintenance/{ctx.amo_code}/quality/management-review/dashboard"},
            {"id": "human-intelligence", "label": "Human-governed intelligence", "description": "Deterministic and future AI recommendations remain advisory until a named decision is recorded.", "path": f"/maintenance/{ctx.amo_code}/quality?hub=intelligence"},
        ],
        "source_coverage": {
            "available": sum(1 for spec in SOURCE_REGISTRY.values() if _projection_columns(db, spec.table)),
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
    display = lambda key: "unavailable" if metrics.get(key) is None else str(metrics[key])
    return {
        "generated_at": _now().isoformat(),
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "readiness": readiness,
        "executive_summary": [
            "Operational readiness is unavailable while source data is incomplete." if readiness["score"] is None else f"Operational readiness is {readiness['score']}% ({readiness['band'].replace('_', ' ').lower()}).",
            f"{display('overdue_cars')} corrective actions and {display('overdue_audits')} audit commitments are overdue.",
            f"{display('invalid_evidence')} assurance relationships are expired or rejected.",
            f"{display('critical_risks')} critical quality risks and {display('open_regulator_findings')} regulator findings remain open.",
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
