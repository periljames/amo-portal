"""MOPM-based defaults shared by retention and external-work workflows.

Periods are calendar periods from their stated event, never upload age.
Unknown events preserve records; an administrator cannot shorten a floor.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import HTTPException

POLICY_VERSION = "KE-AMO-2025-MOPM-4-00-20260831"
SOURCE_SHA256 = "dcb0645eab8ee8dc77d8c4d691bb2f484559c86de65a0da4f347589f61f93b3e"
REGULATION_URL = "https://libraryir.parliament.go.ke/bitstreams/94f8dcfe-9e20-44b8-8599-3009633bdf1a/download"


@dataclass(frozen=True)
class RetentionRule:
    code: str
    label: str
    event: str
    years: int = 0
    days: int = 0
    reference: str = ""
    regulatory_minimum_years: int | None = None


RULES = {rule.code: rule for rule in (
    RetentionRule("MAINTENANCE_RECORDS", "Maintenance work packages and releases", "release_signed_at", years=3, reference="MOPM 2.14.1.2; AMO Regulation 34(3)", regulatory_minimum_years=2),
    RetentionRule("WORKSHOP_RECORDS", "Workshop worksheets, tests and releases", "release_signed_at", years=3, reference="MOPM 2.14.1.2"),
    RetentionRule("TECHNICAL_LOGS", "Technical logs and deferred defects", "last_entry_at", years=3, reference="MOPM 2.14.1.2; apply LOGBOOKS where associated"),
    RetentionRule("MAJOR_REPAIR_MODIFICATION", "Major repair and modification records", "release_signed_at", years=3, reference="MOPM 2.14.1.2"),
    RetentionRule("LOGBOOKS", "Logbooks, associated records and life-limited history", "permanent_withdrawal_at", years=2, reference="MOPM 2.14.1.3; Airworthiness Regulation 41(8)"),
    RetentionRule("STATUS_SUMMARIES", "Standalone status summaries with underlying evidence retained", "permanent_withdrawal_at", days=90, reference="MOPM 2.14.1.1"),
    RetentionRule("OPERATOR_CONTRACT_RECORDS", "Copies of contracted operator records", "contract_ended_at", years=2, reference="MOPM 2.17.2; 4.3.1"),
    RetentionRule("OCCURRENCE_RECORDS", "Occurrence reports and investigation evidence", "permanent_withdrawal_at", years=2, reference="MOPM 2.18.9; longer SMS requirements also apply"),
    RetentionRule("CALIBRATION_CERTIFICATES", "Calibration certificates and results", "tool_scrapped_at", years=2, reference="MOPM 2.5"),
    RetentionRule("SCRAP_REGISTER", "Scrapped-component register", "scrapped_at", years=7, reference="MOPM 2.3.3.4; 2.22.7"),
    RetentionRule("PERSONNEL_RECORDS", "Maintenance staff and training records", "employment_ended_at", years=2, reference="MOPM 3.5; AMO Regulation 26"),
    RetentionRule("AUTHORIZATION_HISTORY", "Withdrawn personnel authorizations", "authorization_withdrawn_at", years=2, reference="MOPM 3.5; 3.8.9"),
    RetentionRule("QMS_AUDIT_RECORDS", "Audit, corrective-action and effectiveness records", "qms_retention_event_at", years=5, reference="MOPM 3.3; QMSM 4.11 calculation event must be confirmed"),
    RetentionRule("MAINTENANCE_AGREEMENTS", "Maintenance agreements and amendments", "quality_retention_determined_at", reference="MOPM 2.23.9; QMS records schedule required"),
)}


def policy_catalogue() -> dict[str, Any]:
    return {
        "version": POLICY_VERSION,
        "source": "MOPM Issue 4 Revision 00, 31 August 2026",
        "source_sha256": SOURCE_SHA256,
        "regulation": {"title": "Civil Aviation (Approved Maintenance Organization) Regulations, 2025", "legal_notice": "20 of 2026", "url": REGULATION_URL},
        "retention": [asdict(rule) for rule in RULES.values()],
        "contracting": {
            "approved_amo_required": True, "complete_type_certificated_product_contracting_permitted": False,
            "current_scope_site_capability_required": True, "written_agreement_required": True,
            "authority_access_required": True, "further_subcontracting_prior_written_acceptance_required": True,
            "maximum_supplier_review_days": 365, "initial_qualification_required": True,
            "reference": "MOPM 2.1; 2.20; 2.23; 3.13; AMO Regulations 14, 31 and 37",
        },
        "tenant_options": {"retention": "Extend periods only", "supplier_review": "Shorten the annual interval", "reminders": "Adjust delivery lead times and recipients"},
    }


def _instant(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, date):
            result = datetime.combine(value, time.max)
        elif isinstance(value, str) and len(value) == 10:
            result = datetime.combine(date.fromisoformat(value), time.max)
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise HTTPException(422, "Enter a valid ISO date for each retention event.") from None


def _anniversary(value: datetime, years: int) -> datetime:
    year = value.year + years
    if not 1 <= year <= 9999:
        raise HTTPException(422, "Retention event and period exceed the supported date range.")
    return value.replace(year=year, day=min(value.day, monthrange(year, value.month)[1]))


def reclassification_metadata(old_class: str, old_metadata: dict | None, incoming: dict) -> dict:
    """A later edit cannot silently discard a known longer record obligation."""
    previous = (old_metadata or {}).get("compliance_retention") or {}
    facts = incoming.get("compliance_retention") or {}
    if not isinstance(facts, dict):
        raise HTTPException(422, "Retention facts must be an object.")
    retained = [code for code in [old_class, *(previous.get("classes") or [])] if code in RULES or code == "PERMANENT"]
    classes = facts.get("classes") or []
    if not isinstance(classes, list):
        raise HTTPException(422, "Retention classes must be a list.")
    return {**dict(old_metadata or {}), **incoming, "compliance_retention": {**previous, **facts,
        "classes": list(dict.fromkeys([*retained, *classes]))}}


def validate_retention_extensions(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict) or set(value) - {"extensions_years", "extensions_days"}:
        raise HTTPException(422, "Retention options may only extend the governed years or days for a known record class.")
    for key, baseline in (("extensions_years", "years"), ("extensions_days", "days")):
        entries = value.get(key, {})
        if not isinstance(entries, dict):
            raise HTTPException(422, "Retention extensions must map record classes to whole numbers.")
        for code, amount in entries.items():
            rule = RULES.get(code)
            floor = getattr(rule, baseline) if rule else 0
            if not rule or not floor or type(amount) is not int or not floor <= amount <= (100 if baseline == "years" else 36500):
                raise HTTPException(422, f"{code}: keep the governed minimum and event; only a longer period is permitted.")
    return value


def retention_assessment(retention_class: str, metadata: dict | None = None, *, requested_until: Any = None, extensions: dict | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    facts = metadata.get("compliance_retention") or {}
    if not isinstance(facts, dict):
        raise HTTPException(422, "Retention facts must be an object.")
    primary = str(retention_class or "").strip().upper()
    classes = facts.get("classes") or [primary]
    if not isinstance(classes, list) or len(classes) > 16 or any(not isinstance(item, str) for item in classes):
        raise HTTPException(422, "Select the applicable retention classes.")
    classes = list(dict.fromkeys([primary, *classes]))
    events = facts.get("events") or {}
    if not isinstance(events, dict):
        raise HTTPException(422, "Retention event dates must be an object.")
    extensions = validate_retention_extensions(extensions or {})
    dates: list[datetime] = []
    unresolved: list[str] = []
    for code in classes:
        rule = RULES.get(code)
        if rule is None:
            unresolved.append(f"Classify {code or 'this record'} against the retention schedule")
            continue
        event = _instant(events.get(rule.event))
        if not event:
            unresolved.append(rule.event)
            continue
        if not rule.years and not rule.days:
            schedule = _instant(facts.get("quality_schedule_until"))
            if not schedule or len(str(facts.get("quality_schedule_reference") or "").strip()) < 8:
                unresolved.append(f"{code}: confirm the governing Quality records schedule")
            else:
                dates.append(schedule)
            continue
        if code == "STATUS_SUMMARIES" and facts.get("underlying_records_separately_retained") is not True:
            unresolved.append("Confirm underlying maintenance and required logbook evidence remain retained")
        years = extensions.get("extensions_years", {}).get(code, rule.years)
        days = extensions.get("extensions_days", {}).get(code, rule.days)
        dates.append(_anniversary(event, years) + timedelta(days=days))
    for key in ("contractual_until", "linked_record_until", "sms_until"):
        value = _instant(facts.get(key))
        if value:
            dates.append(value)
    minimum = max(dates) if dates else None
    requested = _instant(requested_until)
    if minimum and requested and requested < minimum:
        raise HTTPException(422, f"Retention cannot end before {minimum.isoformat()}; the longest applicable requirement governs.")
    effective = max([value for value in (minimum, requested) if value], default=None)
    holds = bool(facts.get("preservation_hold") or facts.get("investigation_open") or facts.get("requirements_unconfirmed"))
    return {"version": POLICY_VERSION, "classes": classes, "minimum_until": minimum.isoformat() if minimum else None,
            "effective_until": effective.isoformat() if effective and not unresolved and not holds else None,
            "unresolved": unresolved, "preservation_hold": holds, "event_dates": events}


def assert_disposition_due(row: Any, *, extensions: dict | None = None, now: datetime | None = None) -> None:
    if getattr(row, "legal_hold", False):
        raise HTTPException(409, "Disposition is blocked by legal hold.")
    metadata = dict(getattr(row, "metadata_json", None) or {})
    result = retention_assessment(getattr(row, "retention_class", "STANDARD"), metadata, extensions=extensions)
    if result["unresolved"] or result["preservation_hold"] or not result["effective_until"]:
        raise HTTPException(409, {"code": "RETENTION_REQUIREMENTS_UNCONFIRMED", "message": "Retain this record until its classification, event dates and preservation obligations are confirmed.", "unresolved": result["unresolved"]})
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    due = max(value for value in (_instant(result["effective_until"]), _instant(getattr(row, "retention_until", None))) if value)
    if due > current:
        raise HTTPException(409, {"code": "RETENTION_PERIOD_ACTIVE", "message": "The applicable retention period has not expired.", "retain_until": due.isoformat()})


def tenant_retention_extensions(db, amo_id: str) -> dict:
    if db.get_bind().dialect.name != "postgresql":
        return {}
    from sqlalchemy import text
    row = db.execute(text("SELECT to_jsonb(s) AS record FROM qms_settings s WHERE amo_id=:amo AND deleted_at IS NULL ORDER BY created_at DESC, id DESC LIMIT 1"), {"amo": str(amo_id)}).scalar()
    if not row:
        return {}
    value = row.get("retention_rules") if "retention_rules" in row else (row.get("payload") or {}).get("retention_rules")
    return validate_retention_extensions(value or {})


def prepare_retention(retention_class: str, metadata: dict | None, requested_until: Any = None, *, extensions: dict | None = None, series_years: int | None = None) -> tuple[datetime | None, dict]:
    if series_years:
        rule = RULES.get(str(retention_class).upper())
        event = _instant(((metadata or {}).get("compliance_retention") or {}).get("events", {}).get(rule.event)) if rule else None
        if event:
            baseline = retention_assessment(retention_class, metadata, extensions=extensions)
            requested_until = max(value for value in (_anniversary(event, series_years), _instant(baseline["minimum_until"]), _instant(requested_until)) if value)
    result = retention_assessment(retention_class, metadata, requested_until=requested_until, extensions=extensions)
    return _instant(result["effective_until"]), {**dict(metadata or {}), "retention_assessment": result}
