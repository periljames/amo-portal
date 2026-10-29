"""Tenant reference configuration and transaction-scoped numbering locks.

Reference resets never renumber records, including soft-deleted records.
"""
import re
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, inspect, text

DEFAULTS = {"audit_prefix": "QAR", "car_prefix": "CAR", "reliability_car_prefix": "RCAR", "finding_prefix": "F", "sequence_digits": 3, "date_format": "YY"}


DATE_FORMATS = ("YY", "YYYY", "YYYY-MM", "YYYYMM", "YYMM")


def server_date():
    return datetime.now(timezone.utc).date()


def reference_date(issued_on, style="YY"):
    patterns = {"YY": "%y", "YYYY": "%Y", "YYYY-MM": "%Y-%m", "YYYYMM": "%Y%m", "YYMM": "%y%m"}
    if style not in patterns:
        raise HTTPException(422, "Choose a supported reference date format.")
    return issued_on.strftime(patterns[style])


def lock_numbering(db, amo_id):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"qms-numbering:{amo_id}"})


def read_rules(db, amo_id):
    inspector = inspect(db.connection())
    if not inspector.has_table("qms_settings"):
        return {}
    columns = {c["name"] for c in inspector.get_columns("qms_settings")}
    row = db.execute(text("SELECT * FROM qms_settings WHERE amo_id = :amo_id AND deleted_at IS NULL ORDER BY created_at DESC, id DESC LIMIT 1"), {"amo_id": str(amo_id)}).mappings().first()
    if not row:
        return {}
    embedded = row.get("payload") or {}
    if isinstance(embedded, str):
        embedded = json.loads(embedded)
    rules = row.get("numbering_rules") if "numbering_rules" in columns else embedded.get("numbering_rules")
    if isinstance(rules, str):
        rules = json.loads(rules)
    return dict(rules or {})


def validate_rules(rules):
    for key in ("audit_prefix", "car_prefix", "reliability_car_prefix", "finding_prefix"):
        if key in rules and (not isinstance(rules[key], str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,15}", rules[key])):
            raise HTTPException(422, f"{key.replace('_', ' ').title()}: use 1–16 uppercase letters or numbers, starting with a letter.")
    if "audit_prefix" in rules and len(rules["audit_prefix"]) < 2:
        raise HTTPException(422, "Audit prefix must contain 2–16 letters or numbers.")
    if rules.get("date_format", "YY") not in DATE_FORMATS:
        raise HTTPException(422, "Choose YY, YYYY, YYYY-MM, YYYYMM or YYMM for reference dates.")
    digits = rules.get("sequence_digits", 3)
    if type(digits) is not int or not 3 <= digits <= 6:
        raise HTTPException(422, "Sequence digits must be a whole number from 3 to 6.")
    families = [rules.get(key, DEFAULTS[key]) for key in ("audit_prefix", "car_prefix", "reliability_car_prefix")]
    if len(set(families)) != len(families):
        raise HTTPException(422, "Audit, CAR and reliability CAR prefixes must be different.")


def sync_workflow_prefix(db, amo_id, prefix, actor_user_id):
    """Keep the existing audit-scope editor and the Settings workspace consistent."""
    from . import models
    row = db.query(models.QualityTenantWorkflowSettings).filter_by(amo_id=amo_id).with_for_update().first()
    if row is None:
        row = models.QualityTenantWorkflowSettings(amo_id=amo_id, created_by_user_id=actor_user_id)
        db.add(row)
    row.audit_reference_family = prefix
    row.updated_by_user_id = actor_user_id


def sync_legacy_prefix(db, amo_id, prefix, actor_user_id):
    """An older audit-scope client must update the same effective configuration."""
    inspector = inspect(db.connection())
    if not inspector.has_table("qms_settings"):
        return
    columns = {c["name"] for c in inspector.get_columns("qms_settings")}
    row = db.execute(text("SELECT * FROM qms_settings WHERE amo_id = :amo_id AND deleted_at IS NULL ORDER BY created_at DESC, id DESC LIMIT 1"), {"amo_id": amo_id}).mappings().first()
    if not row:
        return
    field = "numbering_rules" if "numbering_rules" in columns else "payload"
    document = row.get(field) or {}
    if isinstance(document, str):
        document = json.loads(document)
    rules = dict(document if field == "numbering_rules" else document.get("numbering_rules") or {})
    rules["audit_prefix"] = prefix
    validate_rules(rules)
    document = rules if field == "numbering_rules" else {**document, "numbering_rules": rules}
    expression = "CAST(:value AS jsonb)" if db.get_bind().dialect.name == "postgresql" else ":value"
    db.execute(text(f"UPDATE qms_settings SET {field} = {expression}, updated_at = CURRENT_TIMESTAMP, updated_by = :actor WHERE id = :id AND amo_id = :amo_id"), {"value": json.dumps(document), "actor": actor_user_id, "id": row["id"], "amo_id": amo_id})


def issued_max(db, amo_id, family, unit, year):
    """Include deleted records and both reference types before lowering a counter."""
    from . import models
    stem = f"{family}/{unit}/"
    full_year = (server_date().year // 100) * 100 + year
    periods = {f"{year:02d}", str(full_year)}
    for month in range(1, 13):
        periods.update({f"{full_year}-{month:02d}", f"{full_year}{month:02d}", f"{year:02d}{month:02d}"})
    maximum = int(db.query(func.max(models.QMSAudit.ref_sequence)).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.reference_family == family,
        models.QMSAudit.unit_code == unit,
        models.QMSAudit.ref_year == year,
    ).scalar() or 0)
    for model, field in ((models.QMSAudit, models.QMSAudit.audit_ref), (models.CorrectiveActionRequest, models.CorrectiveActionRequest.car_number)):
        for (reference,) in db.query(field).filter(model.amo_id == amo_id, field.startswith(stem)).all():
            tail = (reference or "")[len(stem):].split("/")
            if len(tail) == 2 and tail[0] in periods and tail[1].isdigit():
                maximum = max(maximum, int(tail[1]))
    return maximum


def reserve_reference(db, *, amo_id, family, unit, digits=3, date_format="YY", issued_on=None):
    from . import models
    issued_on = issued_on or server_date()
    year = issued_on.year % 100
    lock_numbering(db, amo_id)
    counter = db.query(models.QMSAuditReferenceCounter).filter_by(amo_id=amo_id, reference_family=family, unit_code=unit, ref_year=year).with_for_update().first()
    if counter is None:
        counter = models.QMSAuditReferenceCounter(amo_id=amo_id, reference_family=family, unit_code=unit, ref_year=year, last_value=0)
        db.add(counter)
    counter.last_value = max(counter.last_value or 0, issued_max(db, amo_id, family, unit, year)) + 1
    db.flush()
    return f"{family}/{unit}/{reference_date(issued_on, date_format)}/{counter.last_value:0{digits}d}"
