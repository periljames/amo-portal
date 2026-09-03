from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from amodb.user_id import generate_user_id

from .excellence_models import (
    QualityAssuranceControl,
    QualityAssuranceEvent,
    QualityAssuranceEvidenceLink,
    QualityControlTest,
    QualityIntelligenceReview,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/excellence", tags=["Quality assurance wiring"])

ControlCriticality = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ControlStatus = Literal["DRAFT", "ACTIVE", "RETIRED"]
ApprovalStatus = Literal["DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "RETIRED"]
EvidenceStatus = Literal["LINKED", "VERIFIED", "EXPIRED", "REJECTED"]
TestResult = Literal["PASS", "FAIL", "PARTIAL", "NOT_TESTED"]


@dataclass(frozen=True)
class SourceSpec:
    source_type: str
    label: str
    table: str
    identity_fields: tuple[str, ...]
    label_fields: tuple[str, ...]
    valid_until_fields: tuple[str, ...]
    route_template: str
    description: str


SOURCE_REGISTRY: dict[str, SourceSpec] = {
    "AUDIT": SourceSpec("AUDIT", "Audit", "qms_audits", ("id", "audit_ref"), ("audit_ref", "title"), ("planned_end",), "/maintenance/{amo_code}/quality/audits/{id}/setup", "Approved audit scope, fieldwork, report and closeout record."),
    "AUDIT_SCHEDULE": SourceSpec("AUDIT_SCHEDULE", "Audit schedule", "qms_audit_schedules", ("id",), ("title", "kind", "auditee"), ("next_due_date",), "/maintenance/{amo_code}/quality/audits/schedules/{id}", "Risk-based audit programme commitment."),
    "FINDING": SourceSpec("FINDING", "Finding", "qms_audit_findings", ("id", "finding_ref"), ("finding_ref", "description"), ("target_close_date",), "/maintenance/{amo_code}/quality/findings/{id}/overview", "Objective evidence, classification and closeout state."),
    "CAR": SourceSpec("CAR", "CAR / CAPA", "quality_cars", ("id", "car_number"), ("car_number", "title"), ("due_date",), "/maintenance/{amo_code}/quality/cars/{id}/overview", "Containment, root cause, action, effectiveness and closure record."),
    "DOCUMENT": SourceSpec("DOCUMENT", "Controlled document", "qms_documents", ("id", "doc_code"), ("doc_code", "title"), ("review_due_date", "expiry_date"), "/maintenance/{amo_code}/quality/documents/library/{id}", "Approved controlled procedure, manual, form or work instruction."),
    "TRAINING": SourceSpec("TRAINING", "Training / competence", "training_records", ("id",), ("course_code", "course_id", "user_id"), ("valid_until",), "/maintenance/{amo_code}/training/competence/people/{user_id}/course-history", "Current personnel qualification or recurrent-training evidence."),
    "SUPPLIER": SourceSpec("SUPPLIER", "Supplier", "qms_suppliers", ("id", "supplier_code", "reference"), ("supplier_code", "name", "title"), ("approval_expiry", "valid_until"), "/maintenance/{amo_code}/quality/suppliers/{id}/profile", "Approved supplier identity, scope and monitoring status."),
    "SUPPLIER_APPROVAL": SourceSpec("SUPPLIER_APPROVAL", "Supplier approval", "qms_supplier_approvals", ("id", "reference"), ("reference", "title", "supplier_id"), ("valid_until", "expiry_date", "approval_expiry"), "/maintenance/{amo_code}/quality/suppliers/{supplier_id}/approvals", "Supplier approval decision and validity period."),
    "CALIBRATION": SourceSpec("CALIBRATION", "Calibration record", "qms_calibration_records", ("id", "certificate_number", "reference"), ("certificate_number", "reference", "equipment_id"), ("next_due_date", "due_date", "valid_until"), "/maintenance/{amo_code}/quality/equipment-calibration/{equipment_id}/calibration-history", "Traceable calibration result and next-due status."),
    "CALIBRATION_CERTIFICATE": SourceSpec("CALIBRATION_CERTIFICATE", "Calibration certificate", "qms_calibration_certificates", ("id", "certificate_number", "reference"), ("certificate_number", "reference", "equipment_id"), ("valid_until", "expiry_date"), "/maintenance/{amo_code}/quality/equipment-calibration/{equipment_id}/certificates", "Calibration certificate and traceability evidence."),
    "EQUIPMENT": SourceSpec("EQUIPMENT", "Equipment", "qms_equipment", ("id", "equipment_code", "asset_number"), ("equipment_code", "asset_number", "name", "title"), ("calibration_due_date", "next_due_date"), "/maintenance/{amo_code}/quality/equipment-calibration/{id}/profile", "Controlled inspection, test or measuring equipment record."),
    "RISK": SourceSpec("RISK", "Risk", "qms_risks", ("id", "reference"), ("reference", "title", "description"), ("review_due_date", "due_date"), "/maintenance/{amo_code}/quality/risk/{id}/overview", "Risk assessment, controls and treatment evidence."),
    "CHANGE": SourceSpec("CHANGE", "Change control", "qms_change_controls", ("id", "reference"), ("reference", "title", "description"), ("review_due_date", "due_date"), "/maintenance/{amo_code}/quality/change-control/{id}/overview", "Impact, risk, approval and post-implementation review record."),
    "MANAGEMENT_REVIEW_ACTION": SourceSpec("MANAGEMENT_REVIEW_ACTION", "Management-review action", "qms_management_review_actions", ("id", "reference"), ("reference", "title", "description"), ("due_date",), "/maintenance/{amo_code}/quality/management-review/actions", "Management-review decision and assigned action."),
    "REGULATOR_FINDING": SourceSpec("REGULATOR_FINDING", "Regulator finding", "qms_regulator_findings", ("id", "reference"), ("reference", "title", "description"), ("due_date", "target_close_date"), "/maintenance/{amo_code}/quality/external-interface/regulator-findings", "Authority finding, response and closure commitment."),
    "EXTERNAL_COMMITMENT": SourceSpec("EXTERNAL_COMMITMENT", "External commitment", "qms_external_commitments", ("id", "reference"), ("reference", "title", "description"), ("due_date",), "/maintenance/{amo_code}/quality/external-interface/commitments", "Authority, customer or contractual commitment."),
    "REPORT": SourceSpec("REPORT", "Quality report", "qms_report_exports", ("id", "reference"), ("reference", "title", "name"), ("valid_until",), "/maintenance/{amo_code}/quality/reports/exports", "Governed report export or management information pack."),
}

SOURCE_ALIASES = {
    "CAPA": "CAR",
    "CORRECTIVE_ACTION": "CAR",
    "TRAINING_RECORD": "TRAINING",
    "COMPETENCE": "TRAINING",
    "CALIBRATION_RECORD": "CALIBRATION",
    "DOCUMENT_CONTROL": "DOCUMENT",
    "SUPPLIER_RECORD": "SUPPLIER",
}

INVALID_SOURCE_STATUSES = {"CANCELLED", "OBSOLETE", "REJECTED", "DELETED", "VOID", "SUPERSEDED"}
_TABLE_COLUMNS_CACHE: dict[str, set[str]] = {}


class ControlCreate(BaseModel):
    control_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/ -]*$")
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    control_objective: str | None = None
    test_method: str | None = None
    framework: str = Field(default="INTERNAL_QMS", min_length=2, max_length=120)
    clause_reference: str | None = Field(default=None, max_length=255)
    process_area: str = Field(min_length=2, max_length=160)
    owner_user_id: str | None = None
    criticality: ControlCriticality = "MEDIUM"
    status: ControlStatus = "DRAFT"
    approval_status: ApprovalStatus = "DRAFT"
    test_frequency_days: int = Field(default=365, ge=1, le=3650)
    evidence_expectation: str | None = None
    last_tested_at: datetime | None = None
    next_test_due: date | None = None


class ControlPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    control_objective: str | None = None
    test_method: str | None = None
    framework: str | None = Field(default=None, min_length=2, max_length=120)
    clause_reference: str | None = Field(default=None, max_length=255)
    process_area: str | None = Field(default=None, min_length=2, max_length=160)
    owner_user_id: str | None = None
    criticality: ControlCriticality | None = None
    status: ControlStatus | None = None
    approval_status: ApprovalStatus | None = None
    test_frequency_days: int | None = Field(default=None, ge=1, le=3650)
    evidence_expectation: str | None = None
    next_test_due: date | None = None


class EvidenceCreate(BaseModel):
    source_type: str = Field(min_length=2, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")
    source_id: str = Field(min_length=1, max_length=160)
    relationship: str = Field(default="EVIDENCES", min_length=2, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")
    label: str | None = Field(default=None, max_length=255)
    evidence_status: EvidenceStatus = "LINKED"
    valid_until: date | None = None
    notes: str | None = None


class EvidenceDecision(BaseModel):
    evidence_status: EvidenceStatus
    note: str | None = None


class ControlTestCreate(BaseModel):
    result: TestResult
    tested_at: datetime | None = None
    method: str | None = None
    notes: str | None = None
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    next_test_due: date | None = None


class ApprovalDecision(BaseModel):
    approval_status: Literal["PENDING_APPROVAL", "APPROVED", "REJECTED", "RETIRED"]
    note: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_source_type(value: str) -> str:
    normalised = value.strip().upper().replace("-", "_").replace(" ", "_")
    return SOURCE_ALIASES.get(normalised, normalised)


def _normalise_code(value: str) -> str:
    return "-".join(value.strip().upper().replace("_", "-").split())


def _safe_identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError("Unsafe database identifier")
    return f'"{value}"'


def _table_columns(db: Session, table: str) -> set[str]:
    cached = _TABLE_COLUMNS_CACHE.get(table)
    if cached is not None:
        return cached
    if db.get_bind().dialect.name != "postgresql":
        return set()
    rows = db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    ).scalars().all()
    columns = set(rows)
    _TABLE_COLUMNS_CACHE[table] = columns
    return columns


def _string(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _date_value(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _format_route(template: str, amo_code: str, record: dict[str, Any]) -> str:
    values = {key: str(value) for key, value in record.items() if value is not None}
    values["amo_code"] = amo_code
    values.setdefault("id", str(record.get("id") or ""))
    try:
        return template.format_map(values)
    except KeyError:
        return template.replace("{amo_code}", amo_code).replace("{id}", str(record.get("id") or ""))


def _source_label(spec: SourceSpec, record: dict[str, Any]) -> str:
    values: list[str] = []
    for field in spec.label_fields:
        value = _string(record.get(field))
        if value and value not in values:
            values.append(value)
    return " · ".join(values[:2]) or f"{spec.label} {record.get('id', '')}".strip()


def _source_valid_until(spec: SourceSpec, record: dict[str, Any]) -> date | None:
    for field in spec.valid_until_fields:
        parsed = _date_value(record.get(field))
        if parsed:
            return parsed
    return None


def _source_invalid_reason(record: dict[str, Any]) -> str | None:
    if record.get("deleted_at"):
        return "The authoritative record has been soft-deleted."
    source_status = str(record.get("status") or "").upper()
    if source_status in INVALID_SOURCE_STATUSES:
        return f"The authoritative record status is {source_status}."
    return None


def _resolve_source(
    db: Session,
    ctx: TenantContext,
    source_type: str,
    source_id: str,
) -> dict[str, Any]:
    normalised = _normalise_source_type(source_type)
    spec = SOURCE_REGISTRY.get(normalised)
    if not spec:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported evidence source type '{normalised}'. Select an authoritative source from the catalogue.",
        )
    columns = _table_columns(db, spec.table)
    if not columns:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The authoritative {spec.label.lower()} source is unavailable because table '{spec.table}' is missing.",
        )
    identity_fields = [field for field in spec.identity_fields if field in columns]
    if not identity_fields:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"The {spec.label.lower()} source has no supported identity field.")
    projection = set(identity_fields)
    projection.update(field for field in spec.label_fields if field in columns)
    projection.update(field for field in spec.valid_until_fields if field in columns)
    projection.update(
        field for field in (
            "id", "amo_id", "status", "deleted_at", "updated_at", "created_at", "user_id",
            "supplier_id", "equipment_id", "owner_user_id", "due_date", "valid_until",
        ) if field in columns
    )
    where = ["(" + " OR ".join(f"CAST({_safe_identifier(field)} AS TEXT) = :source_id" for field in identity_fields) + ")"]
    params: dict[str, Any] = {"source_id": source_id}
    if "amo_id" in columns:
        where.append("amo_id = :amo_id")
        params["amo_id"] = ctx.amo_id
    sql = f"SELECT {', '.join(_safe_identifier(field) for field in sorted(projection))} FROM {_safe_identifier(spec.table)} WHERE {' AND '.join(where)} LIMIT 1"
    row = db.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{spec.label} record was not found in this tenant.")
    record = dict(row)
    invalid_reason = _source_invalid_reason(record)
    valid_until = _source_valid_until(spec, record)
    return {
        "source_type": normalised,
        "source_table": spec.table,
        "source_id": str(record.get("id") or source_id),
        "source_label": _source_label(spec, record),
        "source_route": _format_route(spec.route_template, ctx.amo_code, record),
        "source_snapshot": record,
        "valid_until": valid_until,
        "invalid_reason": invalid_reason,
        "description": spec.description,
    }


def _control_dict(
    row: QualityAssuranceControl,
    evidence_count: int = 0,
    verified_count: int = 0,
    latest_test: QualityControlTest | None = None,
) -> dict[str, Any]:
    today = date.today()
    due_state = "UNSCHEDULED"
    if row.next_test_due:
        due_state = "OVERDUE" if row.next_test_due < today else "DUE_SOON" if row.next_test_due <= today + timedelta(days=30) else "CURRENT"
    return {
        "id": row.id,
        "control_code": row.control_code,
        "title": row.title,
        "description": row.description,
        "control_objective": row.control_objective,
        "test_method": row.test_method,
        "framework": row.framework,
        "clause_reference": row.clause_reference,
        "process_area": row.process_area,
        "owner_user_id": row.owner_user_id,
        "criticality": row.criticality,
        "status": row.status,
        "approval_status": row.approval_status,
        "version_no": row.version_no,
        "test_frequency_days": row.test_frequency_days,
        "evidence_expectation": row.evidence_expectation,
        "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "next_test_due": row.next_test_due.isoformat() if row.next_test_due else None,
        "due_state": due_state,
        "evidence_count": evidence_count,
        "verified_evidence_count": verified_count,
        "latest_test_result": latest_test.result if latest_test else None,
        "latest_tested_at": latest_test.tested_at.isoformat() if latest_test else None,
        "approved_by_user_id": row.approved_by_user_id,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _evidence_dict(row: QualityAssuranceEvidenceLink) -> dict[str, Any]:
    return {
        "id": row.id,
        "control_id": row.control_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_table": row.source_table,
        "source_route": row.source_route,
        "source_label": row.source_label,
        "source_snapshot": row.source_snapshot or {},
        "relationship": row.relationship,
        "label": row.label,
        "evidence_status": row.evidence_status,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "notes": row.notes,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "source_verified_at": row.source_verified_at.isoformat() if row.source_verified_at else None,
        "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        "invalidated_at": row.invalidated_at.isoformat() if row.invalidated_at else None,
        "invalidation_reason": row.invalidation_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _test_dict(row: QualityControlTest) -> dict[str, Any]:
    return {
        "id": row.id,
        "control_id": row.control_id,
        "result": row.result,
        "tested_at": row.tested_at.isoformat() if row.tested_at else None,
        "tested_by_user_id": row.tested_by_user_id,
        "method": row.method,
        "notes": row.notes,
        "evidence_summary": row.evidence_summary or {},
        "next_test_due": row.next_test_due.isoformat() if row.next_test_due else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/source-catalog")
def source_catalog(
    ctx: TenantContext = Depends(require_quality_permission("qms.evidence.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return {
        "items": [
            {
                "source_type": spec.source_type,
                "label": spec.label,
                "table": spec.table,
                "available": bool(_table_columns(db, spec.table)),
                "description": spec.description,
            }
            for spec in SOURCE_REGISTRY.values()
        ]
    }


@router.get("/source-search")
def source_search(
    source_type: str = Query(..., min_length=2, max_length=48),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    ctx: TenantContext = Depends(require_quality_permission("qms.evidence.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    normalised = _normalise_source_type(source_type)
    spec = SOURCE_REGISTRY.get(normalised)
    if not spec:
        raise HTTPException(status_code=422, detail="Unsupported evidence source type.")
    columns = _table_columns(db, spec.table)
    if not columns:
        return {"items": [], "source_type": normalised, "warning": f"Table '{spec.table}' is unavailable."}
    searchable = [field for field in (*spec.identity_fields, *spec.label_fields) if field in columns]
    projection = set(searchable)
    projection.update(field for field in ("id", "amo_id", "status", "user_id", "supplier_id", "equipment_id", *spec.valid_until_fields) if field in columns)
    where = ["amo_id = :amo_id"] if "amo_id" in columns else ["1=1"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "limit": limit}
    if q.strip() and searchable:
        where.append("(" + " OR ".join(f"CAST({_safe_identifier(field)} AS TEXT) ILIKE :q" for field in searchable) + ")")
        params["q"] = f"%{q.strip()}%"
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    order_field = "updated_at" if "updated_at" in columns else "created_at" if "created_at" in columns else "id"
    sql = f"SELECT {', '.join(_safe_identifier(field) for field in sorted(projection))} FROM {_safe_identifier(spec.table)} WHERE {' AND '.join(where)} ORDER BY {_safe_identifier(order_field)} DESC NULLS LAST LIMIT :limit"
    rows = [dict(row) for row in db.execute(text(sql), params).mappings().all()]
    return {
        "source_type": normalised,
        "items": [
            {
                "id": str(row.get("id")),
                "label": _source_label(spec, row),
                "status": row.get("status"),
                "valid_until": (_source_valid_until(spec, row).isoformat() if _source_valid_until(spec, row) else None),
                "route": _format_route(spec.route_template, ctx.amo_code, row),
                "snapshot": row,
            }
            for row in rows
        ],
    }


@router.get("/controls")
def list_controls(
    status_filter: ControlStatus | None = Query(default=None, alias="status"),
    approval_status: ApprovalStatus | None = Query(default=None),
    limit: int = Query(default=250, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAssuranceControl).filter(QualityAssuranceControl.amo_id == ctx.amo_id)
    if status_filter:
        query = query.filter(QualityAssuranceControl.status == status_filter)
    if approval_status:
        query = query.filter(QualityAssuranceControl.approval_status == approval_status)
    total = query.count()
    criticality_order = case(
        (QualityAssuranceControl.criticality == "CRITICAL", 0),
        (QualityAssuranceControl.criticality == "HIGH", 1),
        (QualityAssuranceControl.criticality == "MEDIUM", 2),
        else_=3,
    )
    rows = query.order_by(criticality_order, QualityAssuranceControl.control_code.asc()).limit(limit).all()
    ids = [row.id for row in rows]
    evidence_rows = db.query(
        QualityAssuranceEvidenceLink.control_id,
        func.count(QualityAssuranceEvidenceLink.id),
        func.sum(case((QualityAssuranceEvidenceLink.evidence_status == "VERIFIED", 1), else_=0)),
    ).filter(
        QualityAssuranceEvidenceLink.amo_id == ctx.amo_id,
        QualityAssuranceEvidenceLink.control_id.in_(ids or ["__none__"]),
    ).group_by(QualityAssuranceEvidenceLink.control_id).all()
    counts = {control_id: (int(total_count or 0), int(verified or 0)) for control_id, total_count, verified in evidence_rows}
    tests = db.query(QualityControlTest).filter(
        QualityControlTest.amo_id == ctx.amo_id,
        QualityControlTest.control_id.in_(ids or ["__none__"]),
    ).order_by(QualityControlTest.tested_at.desc()).all()
    latest_tests: dict[str, QualityControlTest] = {}
    for test in tests:
        latest_tests.setdefault(test.control_id, test)
    return {
        "items": [_control_dict(row, *counts.get(row.id, (0, 0)), latest_tests.get(row.id)) for row in rows],
        "total": total,
        "as_of": _now().isoformat(),
    }
def _create_control(
    payload: ControlCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = QualityAssuranceControl(
        id=generate_user_id(),
        amo_id=ctx.amo_id,
        control_code=_normalise_code(payload.control_code),
        title=payload.title.strip(),
        description=payload.description,
        control_objective=payload.control_objective,
        test_method=payload.test_method,
        framework=payload.framework.strip().upper(),
        clause_reference=payload.clause_reference,
        process_area=payload.process_area.strip(),
        owner_user_id=payload.owner_user_id,
        criticality=payload.criticality,
        status=payload.status,
        approval_status=payload.approval_status,
        test_frequency_days=payload.test_frequency_days,
        evidence_expectation=payload.evidence_expectation,
        last_tested_at=payload.last_tested_at,
        next_test_due=payload.next_test_due,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A control with this code already exists for the tenant.") from exc
    db.refresh(row)
    return _control_dict(row)


@router.patch("/controls/{control_id}")
def update_control(
    control_id: str,
    payload: ControlPatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAssuranceControl).filter(QualityAssuranceControl.id == control_id, QualityAssuranceControl.amo_id == ctx.amo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assurance control not found.")
    changes = payload.model_dump(exclude_unset=True)
    material_fields = {"title", "description", "control_objective", "test_method", "framework", "clause_reference", "process_area", "criticality", "test_frequency_days", "evidence_expectation"}
    if row.approval_status == "APPROVED" and material_fields.intersection(changes):
        row.version_no += 1
        row.approval_status = "DRAFT"
        row.approved_by_user_id = None
        row.approved_at = None
    for field, value in changes.items():
        setattr(row, field, value.strip() if isinstance(value, str) else value)
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _control_dict(row)


def _decide_control_approval(
    control_id: str,
    payload: ApprovalDecision,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAssuranceControl).filter(QualityAssuranceControl.id == control_id, QualityAssuranceControl.amo_id == ctx.amo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assurance control not found.")
    if payload.approval_status == "APPROVED" and not row.evidence_expectation:
        raise HTTPException(status_code=422, detail="Define the expected evidence before approving this control.")
    row.approval_status = payload.approval_status
    row.status = "RETIRED" if payload.approval_status == "RETIRED" else "ACTIVE" if payload.approval_status == "APPROVED" else row.status
    row.approved_by_user_id = ctx.user_id if payload.approval_status == "APPROVED" else None
    row.approved_at = _now() if payload.approval_status == "APPROVED" else None
    row.retired_at = _now() if payload.approval_status == "RETIRED" else None
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _control_dict(row)


def _record_control_test(
    control_id: str,
    payload: ControlTestCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    control = db.query(QualityAssuranceControl).filter(QualityAssuranceControl.id == control_id, QualityAssuranceControl.amo_id == ctx.amo_id).first()
    if not control:
        raise HTTPException(status_code=404, detail="Assurance control not found.")
    tested_at = payload.tested_at or _now()
    next_due = payload.next_test_due or (tested_at.date() + timedelta(days=control.test_frequency_days))
    row = QualityControlTest(
        id=generate_user_id(),
        amo_id=ctx.amo_id,
        control_id=control.id,
        result=payload.result,
        tested_at=tested_at,
        tested_by_user_id=ctx.user_id,
        method=payload.method or control.test_method,
        notes=payload.notes,
        evidence_summary=payload.evidence_summary,
        next_test_due=next_due,
    )
    db.add(row)
    control.last_tested_at = tested_at
    control.next_test_due = next_due
    control.updated_by_user_id = ctx.user_id
    control.updated_at = _now()
    if payload.result in {"FAIL", "PARTIAL"}:
        fingerprint = f"control-test:{control.id}:{tested_at.isoformat()}"
        db.add(QualityIntelligenceReview(
            id=generate_user_id(),
            amo_id=ctx.amo_id,
            insight_type="CONTROL_TEST_FAILURE",
            title=f"Control test requires action: {control.control_code}",
            rationale=f"The latest operating-effectiveness test result was {payload.result}.",
            recommendation="Review the failed test evidence, open or link corrective action, and retest before accepting the control as effective.",
            payload={"control_id": control.id, "control_code": control.control_code, "test_result": payload.result},
            source_fingerprint=fingerprint,
            risk_level="HIGH" if payload.result == "FAIL" else "MEDIUM",
            status="PROPOSED",
            created_by="RULE_ENGINE",
        ))
    db.commit()
    db.refresh(row)
    return _test_dict(row)


@router.get("/controls/{control_id}/tests")
def list_control_tests(
    control_id: str,
    limit: int = Query(default=50, ge=1, le=250),
    ctx: TenantContext = Depends(require_quality_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = db.query(QualityControlTest).filter(QualityControlTest.amo_id == ctx.amo_id, QualityControlTest.control_id == control_id).order_by(QualityControlTest.tested_at.desc()).limit(limit).all()
    return {"items": [_test_dict(row) for row in rows], "total": len(rows)}


@router.post("/controls/{control_id}/evidence", status_code=status.HTTP_201_CREATED)
def link_validated_evidence(
    control_id: str,
    payload: EvidenceCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    control = db.query(QualityAssuranceControl).filter(QualityAssuranceControl.id == control_id, QualityAssuranceControl.amo_id == ctx.amo_id).first()
    if not control:
        raise HTTPException(status_code=404, detail="Assurance control not found.")
    source = _resolve_source(db, ctx, payload.source_type, payload.source_id.strip())
    now = _now()
    valid_until = source["valid_until"] or payload.valid_until
    invalid_reason = source["invalid_reason"]
    evidence_status: EvidenceStatus = "REJECTED" if invalid_reason else "EXPIRED" if valid_until and valid_until < date.today() else payload.evidence_status
    row = QualityAssuranceEvidenceLink(
        id=generate_user_id(),
        amo_id=ctx.amo_id,
        control_id=control.id,
        source_type=source["source_type"],
        source_id=source["source_id"],
        source_table=source["source_table"],
        source_route=source["source_route"],
        source_label=source["source_label"],
        source_snapshot=source["source_snapshot"],
        relationship=payload.relationship.strip().upper(),
        label=payload.label or source["source_label"],
        evidence_status=evidence_status,
        valid_until=valid_until,
        notes=payload.notes,
        created_by_user_id=ctx.user_id,
        verified_by_user_id=ctx.user_id if evidence_status == "VERIFIED" else None,
        verified_at=now if evidence_status == "VERIFIED" else None,
        source_verified_at=now,
        last_synced_at=now,
        invalidated_at=now if invalid_reason else None,
        invalidation_reason=invalid_reason,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This authoritative evidence relationship already exists.") from exc
    db.refresh(row)
    return _evidence_dict(row)


@router.patch("/evidence/{evidence_id}")
def decide_evidence(
    evidence_id: str,
    payload: EvidenceDecision,
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAssuranceEvidenceLink).filter(QualityAssuranceEvidenceLink.id == evidence_id, QualityAssuranceEvidenceLink.amo_id == ctx.amo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Evidence relationship not found.")
    source = _resolve_source(db, ctx, row.source_type, row.source_id)
    if payload.evidence_status == "VERIFIED" and source["invalid_reason"]:
        raise HTTPException(status_code=422, detail=source["invalid_reason"])
    now = _now()
    row.evidence_status = payload.evidence_status
    row.verified_by_user_id = ctx.user_id if payload.evidence_status == "VERIFIED" else None
    row.verified_at = now if payload.evidence_status == "VERIFIED" else None
    row.notes = payload.note or row.notes
    row.source_snapshot = source["source_snapshot"]
    row.source_verified_at = now
    row.last_synced_at = now
    row.invalidated_at = now if payload.evidence_status == "REJECTED" else None
    row.invalidation_reason = payload.note if payload.evidence_status == "REJECTED" else None
    db.commit()
    db.refresh(row)
    return _evidence_dict(row)


def _reconcile_row(db: Session, ctx: TenantContext, row: QualityAssuranceEvidenceLink) -> tuple[bool, str | None]:
    try:
        source = _resolve_source(db, ctx, row.source_type, row.source_id)
    except HTTPException as exc:
        row.evidence_status = "REJECTED"
        row.invalidated_at = _now()
        row.invalidation_reason = str(exc.detail)
        row.last_synced_at = _now()
        return True, str(exc.detail)
    valid_until = source["valid_until"] or row.valid_until
    invalid_reason = source["invalid_reason"]
    next_status = "REJECTED" if invalid_reason else "EXPIRED" if valid_until and valid_until < date.today() else "VERIFIED" if row.evidence_status == "VERIFIED" else "LINKED"
    changed = any((
        row.source_table != source["source_table"],
        row.source_route != source["source_route"],
        row.source_label != source["source_label"],
        row.source_snapshot != source["source_snapshot"],
        row.valid_until != valid_until,
        row.evidence_status != next_status,
        row.invalidation_reason != invalid_reason,
    ))
    now = _now()
    row.source_table = source["source_table"]
    row.source_route = source["source_route"]
    row.source_label = source["source_label"]
    row.source_snapshot = source["source_snapshot"]
    row.valid_until = valid_until
    row.evidence_status = next_status
    row.source_verified_at = now
    row.last_synced_at = now
    row.invalidated_at = now if invalid_reason else None
    row.invalidation_reason = invalid_reason
    return changed, invalid_reason


@router.post("/reconcile")
def reconcile_assurance(
    limit: int = Query(default=500, ge=1, le=2000),
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = db.query(QualityAssuranceEvidenceLink).filter(QualityAssuranceEvidenceLink.amo_id == ctx.amo_id).order_by(QualityAssuranceEvidenceLink.updated_at.asc()).limit(limit).all()
    changed = 0
    rejected = 0
    errors: list[dict[str, str]] = []
    for row in rows:
        was_changed, error = _reconcile_row(db, ctx, row)
        changed += int(was_changed)
        rejected += int(row.evidence_status == "REJECTED")
        if error:
            errors.append({"evidence_id": row.id, "message": error})
    events = db.query(QualityAssuranceEvent).filter(QualityAssuranceEvent.amo_id == ctx.amo_id, QualityAssuranceEvent.processing_status == "PENDING").order_by(QualityAssuranceEvent.occurred_at.asc()).limit(limit).all()
    for event in events:
        event.processing_status = "PROCESSED"
        event.processed_at = _now()
        event.processing_error = None
    db.commit()
    return {"reviewed": len(rows), "changed": changed, "rejected": rejected, "events_processed": len(events), "errors": errors[:50], "as_of": _now().isoformat()}


@router.get("/events")
def assurance_events(
    processing_status: Literal["PENDING", "PROCESSED", "ERROR"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.evidence.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAssuranceEvent).filter(QualityAssuranceEvent.amo_id == ctx.amo_id)
    if processing_status:
        query = query.filter(QualityAssuranceEvent.processing_status == processing_status)
    rows = query.order_by(QualityAssuranceEvent.occurred_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "source_table": row.source_table,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "event_type": row.event_type,
                "changed_fields": row.changed_fields or [],
                "processing_status": row.processing_status,
                "processing_error": row.processing_error,
                "actor_user_id": row.actor_user_id,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "processed_at": row.processed_at.isoformat() if row.processed_at else None,
            }
            for row in rows
        ],
        "total": query.count(),
    }


@router.get("/evidence-graph")
def evidence_graph(
    limit: int = Query(default=500, ge=1, le=1000),
    ctx: TenantContext = Depends(require_quality_permission("qms.evidence.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    controls = db.query(QualityAssuranceControl).filter(QualityAssuranceControl.amo_id == ctx.amo_id, QualityAssuranceControl.status != "RETIRED").order_by(QualityAssuranceControl.control_code.asc()).limit(limit).all()
    control_ids = [row.id for row in controls]
    links = db.query(QualityAssuranceEvidenceLink).filter(QualityAssuranceEvidenceLink.amo_id == ctx.amo_id, QualityAssuranceEvidenceLink.control_id.in_(control_ids or ["__none__"])).order_by(QualityAssuranceEvidenceLink.created_at.desc()).limit(limit * 4).all()
    source_nodes: dict[tuple[str, str], dict[str, Any]] = {}
    for link in links:
        key = (link.source_type, link.source_id)
        source_nodes.setdefault(key, {
            "id": f"source:{link.source_type}:{link.source_id}",
            "kind": "evidence",
            "type": link.source_type,
            "label": link.source_label or link.label or f"{link.source_type} {link.source_id}",
            "status": link.evidence_status,
            "route": link.source_route,
            "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
            "invalidation_reason": link.invalidation_reason,
        })
    nodes = [{
        "id": f"control:{row.id}",
        "kind": "control",
        "label": f"{row.control_code} · {row.title}",
        "framework": row.framework,
        "process_area": row.process_area,
        "criticality": row.criticality,
        "status": row.status,
        "approval_status": row.approval_status,
        "version_no": row.version_no,
    } for row in controls] + list(source_nodes.values())
    edges = [{
        "id": row.id,
        "from": f"control:{row.control_id}",
        "to": f"source:{row.source_type}:{row.source_id}",
        "relationship": row.relationship,
        "status": row.evidence_status,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "source_route": row.source_route,
        "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        "invalidation_reason": row.invalidation_reason,
    } for row in links]
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "controls": len(controls),
            "evidence_records": len(source_nodes),
            "relationships": len(edges),
            "controls_without_evidence": len({row.id for row in controls} - {row.control_id for row in links}),
            "invalid_relationships": sum(1 for row in links if row.evidence_status in {"EXPIRED", "REJECTED"}),
            "verified_relationships": sum(1 for row in links if row.evidence_status == "VERIFIED"),
        },
        "as_of": _now().isoformat(),
    }
