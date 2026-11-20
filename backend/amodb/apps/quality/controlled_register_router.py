"""Operational forms for the existing system, risk, equipment and external registers.

View-to-table and field definitions are server-owned. Tenant ownership, field
validation, attribution and optimistic editing are enforced on every write.
"""
from __future__ import annotations

import csv
import io
import hashlib
import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from .management_review_router import StrictBody, _members, _payload, _public, _record, _save, _version
from .tenant_security import TenantContext, assert_quality_permission, resolve_tenant_context, set_postgres_tenant_context

router = APIRouter(prefix="/register-workspace", tags=["Quality operational registers"])


def field(key, label, kind="text", required=False, options=None):
    return {"key": key, "label": label, "type": kind, "required": required, "options": options or []}


RISK_FIELDS = [field("likelihood", "Likelihood (1–5)", "number", True), field("consequence", "Consequence (1–5)", "number", True),
    field("rating", "Assessed risk level", "select", True, ["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
    field("existing_controls", "Existing controls", "textarea", True), field("assessment_basis", "Assessment rationale", "textarea", True),
    field("residual_risk", "Residual risk and acceptance rationale", "textarea")]
EQUIPMENT_FIELDS = [field("asset_reference", "Asset / equipment reference", required=True), field("serial_number", "Serial number", required=True),
    field("location", "Location"), field("manufacturer", "Manufacturer / model"), field("calibration_basis", "Calibration interval and basis", "textarea", True), field("serviceability_basis", "Serviceability / return-to-service evidence", "textarea")]
SOURCE_SPECS = {
    "processes": {"table": "qms_processes", "label": "Processes", "fields": [field("purpose", "Process purpose", "textarea", True), field("inputs", "Process inputs", "textarea", True), field("outputs", "Process outputs", "textarea", True), field("measure", "Performance measure"), field("target", "Target / acceptance criteria")]},
    "scope": {"table": "qms_quality_policy", "label": "QMS scope", "fields": [field("boundaries", "Scope and organizational boundaries", "textarea", True), field("applicability", "Applicable activities and requirements", "textarea", True), field("exclusions", "Exclusions and justification", "textarea")]},
    "objectives": {"table": "qms_quality_objectives", "label": "Quality objectives", "fields": [field("measure", "Measure / KPI", required=True), field("target", "Target", required=True), field("current_result", "Current result"), field("evaluation", "Evaluation and planned actions", "textarea")]},
    "risks": {"table": "qms_risks", "label": "Risk register", "fields": RISK_FIELDS},
    "opportunities": {"table": "qms_opportunities", "label": "Opportunities", "fields": [field("benefit", "Expected benefit", "textarea", True), field("implementation", "Implementation plan", "textarea", True), field("evaluation", "Outcome evaluation", "textarea")]},
    "treatments": {"table": "qms_risk_actions", "label": "Risk treatment plans", "fields": [field("related_reference", "Related risk reference", required=True), field("treatment", "Treatment / control action", "textarea", True), field("completion_evidence", "Completion and effectiveness evidence", "textarea")]},
    "equipment": {"table": "qms_equipment", "label": "Equipment register", "fields": EQUIPMENT_FIELDS, "statuses": ["ACTIVE", "OUT_OF_SERVICE", "RETIRED"]},
    "calibrations": {"table": "qms_calibration_records", "label": "Calibration history", "equipment_parent": True, "immutable": True, "fields": [field("equipment_id", "Equipment", "equipment", True), field("performed_on", "Calibration date", "date", True), field("certificate_reference", "Certificate reference", required=True), field("result", "Calibration result", "select", True, ["PASS", "FAIL"]), field("laboratory", "Laboratory / provider", required=True), field("completion_evidence", "Results and evidence reference", "textarea", True)], "statuses": ["COMPLETE"]},
    "certificates": {"table": "qms_calibration_certificates", "label": "Calibration certificates", "equipment_parent": True, "fields": [field("equipment_id", "Equipment", "equipment", True), field("certificate_reference", "Certificate reference", required=True), field("issued_on", "Issued on", "date", True), field("issuer", "Issuing laboratory", required=True), field("evidence_reference", "Retained certificate location / document reference", required=True)], "statuses": ["VALID", "SUPERSEDED"]},
    "out-of-tolerance": {"table": "qms_out_of_tolerance_events", "label": "Out-of-tolerance events", "equipment_parent": True, "fields": [field("equipment_id", "Equipment", "equipment", True), field("discovered_on", "Discovered on", "date", True), field("impact", "Affected work and impact assessment", "textarea", True), field("containment", "Containment and disposition", "textarea", True), field("completion_evidence", "Resolution evidence", "textarea")]},
}
for key, label, table in [
    ("regulator-findings", "Regulator findings", "qms_regulator_findings"), ("customer-complaints", "Customer complaints", "qms_customer_complaints"),
    ("customer-feedback", "Customer feedback", "qms_customer_feedback"), ("authority-correspondence", "Authority correspondence", "qms_authority_correspondence"),
    ("commitments", "External commitments", "qms_external_commitments"), ("responses", "External responses", "qms_external_responses"),
]:
    SOURCE_SPECS[key] = {"table": table, "label": label, "fields": [field("external_reference", "External reference", required=True), field("party", "Authority / customer / external party", required=True), field("received_on", "Received / recorded on", "date", True), field("related_reference", "Related finding / correspondence reference"), field("response", "Response / action plan", "textarea"), field("completion_evidence", "Resolution and evidence reference", "textarea")]}

for source in ("customer-complaints", "customer-feedback"):
    SOURCE_SPECS[source]["fields"][0].update(label="Customer reference (if supplied)", required=False)
    SOURCE_SPECS[source]["fields"][1].update(label="Customer / reporting organization")
    SOURCE_SPECS[source]["fields"] += [field("category", "Category", "select", True, ["SERVICE", "PRODUCT_QUALITY", "AIRWORTHINESS", "SAFETY", "COMMUNICATION", "OTHER"]), field("impact", "Reported issue and impact", "textarea", True), field("containment", "Immediate action / containment", "textarea")]
SOURCE_SPECS["regulator-findings"]["fields"] += [
    field("finding_origin", "Finding issued by", "select", True, ["REGULATORY_AUTHORITY", "CUSTOMER", "EXTERNAL_AUDITOR", "PROVIDER", "OTHER_EXTERNAL_PARTY"]),
    field("finding_level", "Finding level as issued", "select", True, ["LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4", "MAJOR", "MINOR", "OBSERVATION", "OTHER"]),
    field("issued_classification", "Exact issuer classification / other level"),
    field("requirement_reference", "Regulation / requirement reference", required=True),
    field("impact", "Compliance / airworthiness impact", "textarea", True),
    field("containment", "Immediate containment and operating restrictions", "textarea", True),
    field("closure_acceptance", "Authority acceptance / closure reference", "textarea"),
]
SOURCE_SPECS["regulator-findings"]["label"] = "External & regulatory findings"
for source in ("regulator-findings", "customer-complaints", "customer-feedback", "authority-correspondence", "commitments", "responses"):
    SOURCE_SPECS[source]["fields"].append(field("provider_id", "Related registered provider (if applicable)", "provider"))
SOURCE_SPECS["provider-findings"] = {"table": "qms_supplier_findings", "label": "Provider findings", "fields": [
    field("provider_id", "Registered provider", "provider", True),
    field("external_reference", "Finding / report reference", required=True),
    field("received_on", "Finding issued on", "date", True),
    field("finding_level", "Finding level as issued", "select", True, ["LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4", "MAJOR", "MINOR", "OBSERVATION", "OTHER"]),
    field("issued_classification", "Exact classification / other level"),
    field("requirement_reference", "Applicable requirement", required=True),
    field("impact", "Affected work and impact", "textarea", True),
    field("containment", "Immediate containment", "textarea", True),
    field("response", "Provider response / corrective action plan", "textarea"),
    field("completion_evidence", "Verification and closure evidence", "textarea"),
]}

VIEW_SOURCES = {
    "suppliers": {"supplier-findings": "provider-findings"},
    "system": {"processes": "processes", "qms-scope": "scope", "quality-objectives": "objectives", "risk-register": "risks", "opportunities": "opportunities"},
    "risk": {"register": "risks", "risk-matrix": "risks", "trends": "risks", "opportunities": "opportunities", "treatment-plans": "treatments"},
    "equipment-calibration": {"register": "equipment", "due-soon": "equipment", "overdue": "equipment", "certificates": "certificates", "reports": "calibrations", "calibration-history": "calibrations", "out-of-tolerance": "out-of-tolerance"},
    "external-interface": {key: key for key in ("regulator-findings", "customer-complaints", "customer-feedback", "authority-correspondence", "commitments", "responses")},
}
PERMISSIONS = {"system": "qms.risk", "risk": "qms.risk", "equipment-calibration": "qms.equipment", "external-interface": "qms.external"}
PERMISSIONS["suppliers"] = "qms.supplier"
DEFAULT_STATUSES = ["OPEN", "IN_PROGRESS", "PENDING_REVIEW", "CLOSED", "CANCELLED"]


class RegisterBody(StrictBody):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(default="", max_length=12000)
    status: str = Field(max_length=40)
    owner_user_id: str = Field(min_length=1, max_length=36)
    due_date: date | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)
    submission_id: str | None = Field(default=None, min_length=16, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")


def spec_for(module, view):
    source = VIEW_SOURCES.get(module, {}).get(view)
    if not source:
        raise HTTPException(404, "This Quality register view is unavailable.")
    return source, SOURCE_SPECS[source]


def _context(db, ctx, module, *, write=False):
    assert_quality_permission(db, ctx, PERMISSIONS[module] + (".manage" if write else ".view"))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def validate_fields(spec, body):
    body.title = body.title.strip()
    if len(body.title) < 3:
        raise HTTPException(422, "Enter a meaningful record title of at least three characters.")
    allowed = {f["key"] for f in spec["fields"]}
    if set(body.fields) - allowed:
        raise HTTPException(422, "Unsupported fields were supplied for this register.")
    if body.status not in spec.get("statuses", DEFAULT_STATUSES):
        raise HTTPException(422, "Choose an available status for this register.")
    cleaned = {}
    for f in spec["fields"]:
        value = body.fields.get(f["key"], "")
        if value is not None and (isinstance(value, (dict, list, bool)) or not isinstance(value, (str, int, float))):
            raise HTTPException(422, f"{f['label']} must be a single entered or selected value.")
        value = str(value).strip() if value is not None else ""
        if f["required"] and not value:
            raise HTTPException(422, f"{f['label']} is required.")
        if f["key"] == "party" and value and (len(value) < 2 or not any(ch.isalnum() for ch in value)):
            raise HTTPException(422, "Enter the reporting customer, authority or organization's name.")
        if len(value) > 12000:
            raise HTTPException(422, f"{f['label']} is too long.")
        if value and f["type"] == "number":
            if value not in {"1", "2", "3", "4", "5"}: raise HTTPException(422, f"{f['label']} must be an integer from 1 to 5.")
            value = int(value)
        if value and f["type"] == "date":
            try: value = date.fromisoformat(value).isoformat()
            except ValueError: raise HTTPException(422, f"{f['label']} must be a valid date.")
            if f["key"] in {"received_on", "issued_on", "discovered_on"} and date.fromisoformat(value) > date.today():
                raise HTTPException(422, f"{f['label']} cannot be in the future.")
        if value and f["type"] == "select" and value not in f["options"]:
            raise HTTPException(422, f"Choose an available {f['label'].lower()}.")
        cleaned[f["key"]] = value
    if body.status == "CLOSED" and "completion_evidence" in allowed and not cleaned.get("completion_evidence"):
        raise HTTPException(422, "Record completion / resolution evidence before closing this item.")
    if spec["table"] in {"qms_regulator_findings", "qms_supplier_findings"}:
        if not body.due_date:
            raise HTTPException(422, "Record the issuer's response / corrective action deadline.")
        if cleaned.get("finding_level") == "OTHER" and not cleaned.get("issued_classification"):
            raise HTTPException(422, "Enter the exact finding classification given in the issued report.")
        if body.status == "CLOSED" and cleaned.get("finding_origin") == "REGULATORY_AUTHORITY" and not cleaned.get("closure_acceptance"):
            raise HTTPException(422, "Record the authority's acceptance before closing a regulatory finding.")
    if (spec.get("equipment_parent") or spec["table"] == "qms_equipment") and not body.due_date:
        raise HTTPException(422, "Set the next calibration / review due date.")
    if cleaned.get("performed_on") and date.fromisoformat(cleaned["performed_on"]) > date.today():
        raise HTTPException(422, "A completed calibration cannot have a future performance date. Use the equipment's next due date to plan future calibration.")
    if cleaned.get("performed_on") and body.due_date and body.due_date < date.fromisoformat(cleaned["performed_on"]):
        raise HTTPException(422, "Next calibration due date cannot precede the calibration date.")
    return cleaned


def _where(ctx, view, q, status):
    where = "amo_id=:amo AND deleted_at IS NULL"
    params = {"amo": ctx.amo_id, "q": "%" + q.lower() + "%", "status": status}
    if q: where += " AND (lower(title) LIKE :q OR lower(COALESCE(description,'')) LIKE :q)"
    if status: where += " AND status=:status"
    if view == "overdue": where += " AND due_date<CURRENT_DATE AND status NOT IN ('RETIRED','CLOSED','CANCELLED')"
    if view == "due-soon":
        from datetime import timedelta
        where += " AND due_date BETWEEN :today AND :soon AND status NOT IN ('RETIRED','CLOSED','CANCELLED')"
        params.update(today=date.today(), soon=date.today() + timedelta(days=30))
    return where, params


def equipment_report(db, ctx):
    params = {"amo": ctx.amo_id}
    equipment = dict(db.execute(text("""SELECT count(*) AS equipment_total,
        sum(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) AS active,
        sum(CASE WHEN status='ACTIVE' AND due_date>=CURRENT_DATE THEN 1 ELSE 0 END) AS active_within_due_date,
        sum(CASE WHEN status='ACTIVE' AND due_date<CURRENT_DATE THEN 1 ELSE 0 END) AS active_overdue,
        sum(CASE WHEN status='ACTIVE' AND due_date IS NULL THEN 1 ELSE 0 END) AS active_missing_due_date,
        sum(CASE WHEN status='OUT_OF_SERVICE' THEN 1 ELSE 0 END) AS out_of_service
        FROM qms_equipment WHERE amo_id=:amo AND deleted_at IS NULL"""), params).mappings().one())
    result = "payload->>'result'" if db.bind.dialect.name == "postgresql" else "json_extract(payload,'$.result')"
    calibrations = dict(db.execute(text(f"""SELECT count(*) AS retained_calibrations,
        sum(CASE WHEN {result}='PASS' THEN 1 ELSE 0 END) AS passed,
        sum(CASE WHEN {result}='FAIL' THEN 1 ELSE 0 END) AS failed
        FROM qms_calibration_records WHERE amo_id=:amo AND deleted_at IS NULL AND status='COMPLETE'"""), params).mappings().one())
    open_events = db.execute(text("SELECT count(*) FROM qms_out_of_tolerance_events WHERE amo_id=:amo AND deleted_at IS NULL AND status NOT IN ('CLOSED','CANCELLED')"), params).scalar_one()
    values = {**equipment, **calibrations, "open_tolerance_cases": open_events}
    return {key: int(value or 0) for key, value in values.items()}


@router.get("/{module}/{view}")
def register(module: str, view: str, q: str = Query("", max_length=80), status: str = Query("", max_length=40), offset: int = Query(0, ge=0, le=100000),
             ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    source, spec = spec_for(module, view)
    _context(db, ctx, module)
    where, params = _where(ctx, view, q, status)
    params["offset"] = offset
    total = db.execute(text(f"SELECT count(*) FROM {spec['table']} WHERE {where}"), params).scalar_one()
    rows = db.execute(text(f"SELECT * FROM {spec['table']} WHERE {where} ORDER BY created_at DESC, id LIMIT 30 OFFSET :offset"), params).mappings().all()
    members = db.execute(text("SELECT id, first_name, last_name, email FROM users WHERE amo_id=:amo AND is_active=true ORDER BY first_name,last_name"), params).mappings().all()
    equipment = db.execute(text("SELECT id,title FROM qms_equipment WHERE amo_id=:amo AND deleted_at IS NULL AND status<>'RETIRED' ORDER BY title"), params).mappings().all() if spec.get("equipment_parent") else []
    providers = db.execute(text("SELECT id,legal_name AS title FROM procurement_suppliers WHERE amo_id=:amo AND is_active=true ORDER BY legal_name"), params).mappings().all() if module in {"external-interface", "suppliers"} else []
    parties = []
    if module == "external-interface":
        party_value = "payload->>'party'" if db.bind.dialect.name == "postgresql" else "json_extract(payload, '$.party')"
        parties = [r[0] for r in db.execute(text(f"SELECT DISTINCT trim({party_value}) AS party FROM {spec['table']} WHERE amo_id=:amo AND deleted_at IS NULL AND trim(COALESCE({party_value},''))<>'' ORDER BY party LIMIT 250"), params)]
    groups = db.execute(text(f"SELECT status,count(*) AS count FROM {spec['table']} WHERE {where} GROUP BY status"), params).mappings().all()
    matrix = [[0] * 5 for _ in range(5)]
    unassessed = 0
    risk_history = []
    if source == "risks":
        for r in db.execute(text(f"SELECT id,title,status,payload FROM {spec['table']} WHERE {where}"), params).mappings():
            p = _payload(r)
            for event in p.get("history", []):
                if isinstance(event, dict) and isinstance(event.get("assessment"), dict):
                    risk_history.append({"record_id": r["id"], "title": r["title"], **event})
            if r["status"] in {"CLOSED", "CANCELLED"}: continue
            try:
                likelihood, consequence = int(p.get("likelihood", 0)), int(p.get("consequence", 0))
                if not (1 <= likelihood <= 5 and 1 <= consequence <= 5): raise ValueError()
                matrix[likelihood - 1][consequence - 1] += 1
            except (ValueError, TypeError): unassessed += 1
    return {"items": [_public(r) for r in rows], "total": total, "offset": offset, "limit": 30,
        "source": source, "label": ({"reports": "Calibration reports", "due-soon": "Equipment due within 30 days", "overdue": "Overdue equipment"}.get(view, spec["label"]) if module == "equipment-calibration" else spec["label"]), "fields": spec["fields"], "statuses": spec.get("statuses", DEFAULT_STATUSES),
        "members": [dict(m) for m in members], "equipment": [dict(e) for e in equipment], "providers": [dict(p) for p in providers], "parties": parties,
        "status_counts": [dict(g) for g in groups], "risk_matrix": matrix if source == "risks" else None, "unassessed": unassessed, "immutable": spec.get("immutable", False),
        "risk_history": sorted(risk_history, key=lambda r: r.get("at", ""), reverse=True) if view == "trends" else [],
        "equipment_report": equipment_report(db, ctx) if module == "equipment-calibration" and view == "reports" else None}


@router.get("/{module}/{view}/export")
def export(module: str, view: str, q: str = Query("", max_length=80), status: str = Query("", max_length=40), ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _, spec = spec_for(module, view)
    _context(db, ctx, module)
    assert_quality_permission(db, ctx, "qms.reports.export")
    where, params = _where(ctx, view, q, status)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    fields = [f["key"] for f in spec["fields"]]
    def safe(value):
        value = str("" if value is None else value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
    if module == "equipment-calibration" and view == "reports":
        writer.writerow(["Tenant totals (unfiltered)", "Value"])
        for key, value in equipment_report(db, ctx).items():
            writer.writerow([key.replace("_", " ").capitalize(), safe(value)])
        writer.writerow([])
    writer.writerow(["Recorded at", "Risk", "Status", "Assessor ID", "Likelihood", "Consequence", "Assessed level", "Score"] if view == "trends" else ["Title", "Status", "Due date", "Owner ID", "Description", *[f["label"] for f in spec["fields"]]])
    for row in db.execute(text(f"SELECT * FROM {spec['table']} WHERE {where} ORDER BY created_at DESC,id"), params).mappings():
        p = _payload(row)
        if view == "trends":
            for event in p.get("history", []):
                if isinstance(event, dict) and isinstance(event.get("assessment"), dict):
                    a = event["assessment"]
                    writer.writerow([safe(event.get("at")), safe(row["title"]), safe(event.get("status")), safe(event.get("by")), *[safe(a.get(k)) for k in ("likelihood", "consequence", "rating", "risk_score")]])
            continue
        writer.writerow([safe(row.get(k)) for k in ("title", "status", "due_date", "owner_user_id", "description")] + [safe(p.get(k)) for k in fields])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="QMS-{module}-{view}.csv"'})


@router.get("/{module}/{view}/{record_id}")
def detail(module: str, view: str, record_id: str, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _, spec = spec_for(module, view)
    _context(db, ctx, module)
    return _record(db, spec["table"], ctx, record_id)


def _write(module, view, body, request, ctx, db, record_id=None):
    source, spec = spec_for(module, view)
    _context(db, ctx, module, write=True)
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode="json", exclude={"submission_id", "expected_version"}), sort_keys=True).encode()).hexdigest()
    if not record_id and body.submission_id:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"register:{ctx.amo_id}:{source}:{body.submission_id}"})
        relation = "payload->>'submission_id'" if db.bind.dialect.name == "postgresql" else "json_extract(payload, '$.submission_id')"
        prior = db.execute(text(f"SELECT * FROM {spec['table']} WHERE amo_id=:amo AND {relation}=:submission"), {"amo": ctx.amo_id, "submission": body.submission_id}).mappings().first()
        if prior:
            if _payload(prior).get("submission_fingerprint") != fingerprint:
                raise HTTPException(409, "This draft was already saved. Reopen its saved record before changing it.")
            return _public(prior)
    clean = validate_fields(spec, body)
    _members(db, ctx, [body.owner_user_id])
    if clean.get("provider_id") and not db.execute(text("SELECT id FROM procurement_suppliers WHERE amo_id=:amo AND CAST(id AS TEXT)=:id AND is_active=true"), {"amo": ctx.amo_id, "id": clean["provider_id"]}).first():
        raise HTTPException(422, "Choose an active registered provider from this organization.")
    parent = None
    if spec.get("equipment_parent"):
        parent = _record(db, "qms_equipment", ctx, clean["equipment_id"], lock=True)
        if parent["status"] == "RETIRED": raise HTTPException(422, "Choose equipment that has not been retired.")
    existing = _record(db, spec["table"], ctx, record_id, lock=True) if record_id else None
    if existing:
        if spec.get("immutable"):
            raise HTTPException(409, "Completed calibration evidence is retained unchanged. Record a new calibration to supersede it.")
        if body.expected_version is None: raise HTTPException(422, "The current record version is required.")
        _version(existing, body.expected_version)
        if spec.get("equipment_parent") and clean["equipment_id"] != _payload(existing).get("equipment_id"):
            raise HTTPException(422, "A retained equipment record cannot be reassigned to a different asset.")
        if source == "equipment" and existing["status"] in {"OUT_OF_SERVICE", "RETIRED"} and body.status == "ACTIVE" and not clean.get("serviceability_basis"):
            raise HTTPException(422, "Record return-to-service evidence before reactivating equipment.")
        if source == "equipment" and body.status == "ACTIVE":
            relation = "payload->>'equipment_id'" if db.bind.dialect.name == "postgresql" else "json_extract(payload, '$.equipment_id')"
            open_events = db.execute(text(f"SELECT count(*) FROM qms_out_of_tolerance_events WHERE amo_id=:amo AND deleted_at IS NULL AND status NOT IN ('CLOSED','CANCELLED') AND {relation}=:equipment"), {"amo": ctx.amo_id, "equipment": existing["id"]}).scalar_one()
            if open_events:
                raise HTTPException(422, "Resolve the open out-of-tolerance events before returning this equipment to service.")
    payload = {**(_payload(existing) if existing else {}), **clean, "source": source}
    if not existing and body.submission_id:
        payload.update(submission_id=body.submission_id, submission_fingerprint=fingerprint)
    if source == "risks": payload["risk_score"] = clean["likelihood"] * clean["consequence"]
    values = {"title": body.title, "description": body.description, "status": body.status, "owner_user_id": body.owner_user_id, "due_date": body.due_date, "payload": payload}
    row = _save(db, spec["table"], ctx, values, existing=existing, event="REGISTER_UPDATED" if existing else "REGISTER_CREATED", request=request, module=module)
    if source == "calibrations" and parent:
        previous = _payload(parent)
        if not previous.get("last_calibrated_on") or clean["performed_on"] >= previous["last_calibrated_on"]:
            _save(db, "qms_equipment", ctx, {"due_date": body.due_date, "status": parent["status"] if clean["result"] == "PASS" else "OUT_OF_SERVICE", "payload": {**previous, "last_calibrated_on": clean["performed_on"], "last_calibration_id": row["id"]}}, existing=parent, event="CALIBRATION_RECORDED", request=request, module=module)
    if source == "out-of-tolerance" and parent and body.status not in {"CLOSED", "CANCELLED"}:
        _save(db, "qms_equipment", ctx, {"status": "OUT_OF_SERVICE", "payload": _payload(parent)}, existing=parent, event="OUT_OF_TOLERANCE_RECORDED", request=request, module=module)
    db.commit()
    return row


@router.post("/{module}/{view}", status_code=201)
def create(module: str, view: str, body: RegisterBody, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    return _write(module, view, body, request, ctx, db)


@router.put("/{module}/{view}/{record_id}")
def update(module: str, view: str, record_id: str, body: RegisterBody, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    return _write(module, view, body, request, ctx, db, record_id)
