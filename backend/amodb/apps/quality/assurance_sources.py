"""Fail-closed source contracts and server-resolved Assurance responsibility.

My Work means assigned audit participants, programme owner/item participants,
CAR assignee, or control/document owner. Creation/request provenance is not an
assignment. Findings inherit their same-tenant audit participants. Sources with
no supported responsibility relationship have empty personal scope.
"""
from dataclasses import dataclass
from typing import Any, Callable
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .assurance_wiring_router import _table_columns, _safe_identifier

AUDIT_ACTORS = ("lead_auditor_user_id", "observer_auditor_user_id", "assistant_auditor_user_id", "auditee_user_id")
# Explicit ownership contracts; no discovered-column fallback may remove tenancy.
TENANT_COLUMNS = {table: "amo_id" for table in (
    "qms_audits", "qms_audit_findings", "qms_audit_schedules", "quality_cars",
    "quality_audit_programmes", "quality_audit_programme_items", "qms_documents",
    "quality_assurance_controls", "quality_assurance_evidence_links", "quality_control_tests",
    "quality_assurance_events", "quality_intelligence_reviews", "training_records",
    "qms_supplier_approvals", "qms_calibration_records", "qms_risks", "qms_changes",
    "qms_management_review_actions", "qms_regulator_findings", "qms_external_commitments",
    "qms_change_controls", "qms_out_of_tolerance_events",
)}
ACTOR_COLUMNS = {
    "qms_audits": AUDIT_ACTORS,
    "qms_audit_schedules": AUDIT_ACTORS,
    "quality_cars": ("assigned_to_user_id",),
    "quality_assurance_controls": ("owner_user_id",),
    "qms_documents": ("owner_user_id",),
    "training_records": ("user_id",),
}
SOURCE_PERMISSIONS = {
    "qms_audits": "qms.audit.view", "qms_audit_schedules": "qms.audit.view",
    "quality_audit_programmes": "qms.audit.view", "quality_audit_programme_items": "qms.audit.view",
    "qms_audit_findings": "qms.finding.view", "quality_cars": "qms.car.view",
    "qms_documents": "qms.document.view", "training_records": "qms.training.view",
    "qms_supplier_approvals": "qms.supplier.view", "qms_calibration_records": "qms.equipment.view",
    "qms_risks": "qms.risk.view", "qms_changes": "qms.change.view",
    "qms_change_controls": "qms.change.view", "qms_out_of_tolerance_events": "qms.equipment.view",
    "qms_management_review_actions": "qms.management_review.view",
    "qms_regulator_findings": "qms.external.view", "qms_external_commitments": "qms.external.view",
}

class SourceFailure(Exception):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)

@dataclass(frozen=True)
class SourceResult:
    value: Any = None
    status: str = "SUCCESS"
    message: str = ""

    def warning(self, source):
        return {"source": source, "type": self.status, "message": self.message}

def source_result(query: Callable[[], Any]) -> SourceResult:
    try:
        return SourceResult(value=query())
    except SourceFailure as exc:
        return SourceResult(status=exc.status, message=str(exc))
    except SQLAlchemyError as exc:
        code = str(getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(getattr(exc, "orig", None), "pgcode", ""))
        status = ("ACCESS_FAILURE" if code == "42501" else "SCHEMA_UNAVAILABLE" if code.startswith("42") else "SOURCE_UNAVAILABLE" if code.startswith("08") or getattr(exc, "connection_invalidated", False) else "QUERY_FAILURE")
        # Never expose SQL, bound parameters, or driver details to the client.
        return SourceResult(status=status, message="Authoritative source query could not be completed.")

def source_columns(db, table: str, required=()):
    with db.begin_nested():
        columns = _table_columns(db, table)
    if not columns:
        raise SourceFailure("SOURCE_UNAVAILABLE", f"Source {table} is unavailable.")
    tenant = TENANT_COLUMNS.get(table)
    if not tenant or tenant not in columns or not set(required).issubset(columns):
        raise SourceFailure("SCHEMA_UNAVAILABLE", f"Source {table} cannot prove its required schema and tenant ownership.")
    return columns

def require_source_access(db, ctx, table):
    from .tenant_security import has_quality_permission
    permission = SOURCE_PERMISSIONS.get(table, "qms.dashboard.view")
    if not has_quality_permission(db, ctx, permission):
        raise SourceFailure("ACCESS_FAILURE", "Source access is not permitted.")

def actor_condition(columns, candidates, alias=""):
    prefix = f"{_safe_identifier(alias)}." if alias else ""
    terms = [f"{prefix}{_safe_identifier(c)} = :actor_user_id" for c in candidates if c in columns]
    if "supporting_auditor_user_ids" in columns and candidates == AUDIT_ACTORS:
        terms.append(f"CAST({prefix}supporting_auditor_user_ids AS jsonb) @> jsonb_build_array(CAST(:actor_user_id AS text))")
    return "(" + " OR ".join(terms) + ")" if terms else "1 = 0"

def responsibility(db, table, columns, alias=""):
    prefix = f"{_safe_identifier(alias)}." if alias else f"{_safe_identifier(table)}."
    if table == "qms_audit_findings":
        audits = source_columns(db, "qms_audits", ("id",))
        if "audit_id" not in columns:
            raise SourceFailure("SCHEMA_UNAVAILABLE", "Finding audit ownership is unavailable.")
        active = " AND a.deleted_at IS NULL" if "deleted_at" in audits else ""
        return f"EXISTS (SELECT 1 FROM qms_audits a WHERE a.id = {prefix}audit_id AND a.amo_id = {prefix}amo_id{active} AND {actor_condition(audits, AUDIT_ACTORS, 'a')})"
    return actor_condition(columns, ACTOR_COLUMNS.get(table, ()), alias)

def programme_responsibility(db):
    programmes = source_columns(db, "quality_audit_programmes")
    items = source_columns(db, "quality_audit_programme_items")
    return f"({actor_condition(programmes, ('owner_user_id',), 'p')} OR {actor_condition(items, AUDIT_ACTORS, 'i')})"

def query_rows(db, sql, params):
    with db.begin_nested():
        return [dict(row) for row in db.execute(text(sql), params).mappings().all()]

def query_scalar(db, sql, params):
    with db.begin_nested():
        return int(db.execute(text(sql), params).scalar_one())
