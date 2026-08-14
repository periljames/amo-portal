from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..fleet import models as fleet_models
from . import calendar_feed, common, exports, models, reports
from .aircraft_allocation import RosterAircraftAllocation
from .code_registry_models import (
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)
from .roster_control_models import (
    RosterAssignmentLineage,
    RosterCalendarSubscription,
    RosterControlledDocumentSettings,
    RosterPublicationSnapshot,
    RosterShiftAlias,
)

_ALIAS_SPACE_RE = re.compile(r"\s+")


def normalize_alias(value: str) -> str:
    alias = _ALIAS_SPACE_RE.sub(" ", str(value or "").strip().upper())
    if not alias or len(alias) > 64:
        raise ValueError("Legacy alias must contain 1-64 visible characters")
    return alias


def list_aliases(db: Session, *, amo_id: str, template_id: Optional[str] = None) -> list[RosterShiftAlias]:
    query = db.query(RosterShiftAlias).filter(RosterShiftAlias.amo_id == amo_id)
    if template_id:
        query = query.filter(RosterShiftAlias.shift_template_id == template_id)
    return query.order_by(RosterShiftAlias.alias.asc(), RosterShiftAlias.id.asc()).all()


def create_alias(
    db: Session,
    *,
    amo_id: str,
    template_id: str,
    alias: str,
    actor_user_id: str,
    context_label: Optional[str] = None,
    aircraft_registration: Optional[str] = None,
    notes: Optional[str] = None,
) -> RosterShiftAlias:
    template = db.query(models.ShiftTemplate).filter(
        models.ShiftTemplate.amo_id == amo_id,
        models.ShiftTemplate.id == template_id,
    ).first()
    if not template:
        raise LookupError("Shift template not found")
    normalized = normalize_alias(alias)
    canonical_collision = db.query(models.ShiftTemplate.id).filter(
        models.ShiftTemplate.amo_id == amo_id,
        func.upper(models.ShiftTemplate.code) == normalized,
    ).first()
    if canonical_collision:
        raise ValueError("Legacy alias conflicts with an existing canonical roster code")
    existing = db.query(RosterShiftAlias.id).filter(
        RosterShiftAlias.amo_id == amo_id,
        func.upper(RosterShiftAlias.alias) == normalized,
    ).first()
    if existing:
        raise ValueError("Legacy alias already exists for this tenant")
    row = RosterShiftAlias(
        amo_id=amo_id,
        alias=normalized,
        shift_template_id=template_id,
        context_label=(context_label or "").strip() or None,
        aircraft_registration=(aircraft_registration or "").strip().upper() or None,
        notes=(notes or "").strip() or None,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterShiftAlias",
        entity_id=row.id,
        action="create",
        after={
            "alias": row.alias,
            "shift_template_id": row.shift_template_id,
            "context_label": row.context_label,
            "aircraft_registration": row.aircraft_registration,
        },
    )
    return row


def delete_alias(db: Session, *, amo_id: str, alias_id: str, actor_user_id: str) -> None:
    row = db.query(RosterShiftAlias).filter(
        RosterShiftAlias.amo_id == amo_id,
        RosterShiftAlias.id == alias_id,
    ).first()
    if not row:
        raise LookupError("Legacy alias not found")
    before = {"alias": row.alias, "shift_template_id": row.shift_template_id}
    db.delete(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterShiftAlias",
        entity_id=alias_id,
        action="delete",
        before=before,
    )


def get_or_create_settings(db: Session, *, amo_id: str, actor_user_id: Optional[str] = None) -> RosterControlledDocumentSettings:
    row = db.query(RosterControlledDocumentSettings).filter(
        RosterControlledDocumentSettings.amo_id == amo_id
    ).first()
    if row:
        return row
    row = RosterControlledDocumentSettings(
        amo_id=amo_id,
        form_number="ROSTER",
        footer_note="Times are shown in the roster period time zone. Unpaid breaks are stated in the applicable shift-code legend.",
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def update_settings(
    db: Session,
    *,
    row: RosterControlledDocumentSettings,
    actor_user_id: str,
    values: dict[str, Any],
) -> RosterControlledDocumentSettings:
    before = {
        "form_number": row.form_number,
        "revision_label": row.revision_label,
        "revision_date": row.revision_date.isoformat() if row.revision_date else None,
        "footer_note": row.footer_note,
        "prepared_by_label": row.prepared_by_label,
        "approved_by_label": row.approved_by_label,
        "page_size": row.page_size,
    }
    for key, value in values.items():
        if key in {"form_number", "revision_label", "prepared_by_label", "approved_by_label", "page_size"} and isinstance(value, str):
            value = value.strip()
        setattr(row, key, value)
    if row.page_size not in {"A3", "A4"}:
        raise ValueError("Controlled roster page size must be A3 or A4")
    if not row.form_number:
        raise ValueError("Controlled roster form number is required")
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterControlledDocumentSettings",
        entity_id=row.id,
        action="update",
        before=before,
        after={
            "form_number": row.form_number,
            "revision_label": row.revision_label,
            "revision_date": row.revision_date.isoformat() if row.revision_date else None,
            "footer_note": row.footer_note,
            "page_size": row.page_size,
        },
        critical=True,
    )
    return row


def _assignment_signature(row: models.RosterAssignment) -> tuple[Any, ...]:
    return (
        row.user_id,
        row.department_id,
        row.base_station_id,
        row.shift_template_id,
        common.enum_value(row.status),
        common.enum_value(row.source),
        row.source_reference_id,
        row.starts_at,
        row.ends_at,
        row.planned_minutes,
        row.role_label,
        row.team_code,
        row.location_label,
        row.task_note,
    )


def _lineage_key(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]


def ensure_assignment_lineages(db: Session, *, version: models.RosterVersion) -> dict[str, str]:
    assignments = [row for row in version.assignments or [] if row.deleted_at is None]
    if not assignments:
        return {}
    existing = {
        row.assignment_id: row
        for row in db.query(RosterAssignmentLineage).filter(
            RosterAssignmentLineage.amo_id == version.amo_id,
            RosterAssignmentLineage.assignment_id.in_([item.id for item in assignments]),
        ).all()
    }
    source_by_signature: dict[tuple[Any, ...], list[models.RosterAssignment]] = defaultdict(list)
    source_lineages: dict[str, str] = {}
    if version.source_version_id:
        source_version = db.query(models.RosterVersion).filter(
            models.RosterVersion.amo_id == version.amo_id,
            models.RosterVersion.id == version.source_version_id,
        ).first()
        if source_version:
            source_lineages = ensure_assignment_lineages(db, version=source_version)
            for source in [row for row in source_version.assignments or [] if row.deleted_at is None]:
                source_by_signature[_assignment_signature(source)].append(source)

    for assignment in assignments:
        if assignment.id in existing:
            continue
        source_assignment = None
        candidates = source_by_signature.get(_assignment_signature(assignment)) or []
        if candidates:
            source_assignment = candidates.pop(0)
        if source_assignment:
            lineage = source_lineages.get(source_assignment.id) or _lineage_key(
                f"{version.amo_id}:{source_assignment.source_reference_id or source_assignment.id}"
            )
        else:
            lineage = _lineage_key(
                f"{version.amo_id}:{assignment.source_reference_id or assignment.id}"
            )
        row = RosterAssignmentLineage(
            amo_id=version.amo_id,
            assignment_id=assignment.id,
            source_assignment_id=source_assignment.id if source_assignment else None,
            lineage_key=lineage,
        )
        db.add(row)
        existing[assignment.id] = row
    db.flush()
    return {assignment_id: row.lineage_key for assignment_id, row in existing.items()}


def registry_issues(db: Session, *, version: models.RosterVersion) -> list[str]:
    active = [row for row in version.assignments or [] if row.deleted_at is None]
    template_ids = {row.shift_template_id for row in active if row.shift_template_id}
    templates = {
        row.id: row
        for row in db.query(models.ShiftTemplate).filter(
            models.ShiftTemplate.amo_id == version.amo_id,
            models.ShiftTemplate.id.in_(template_ids or ["__none__"]),
        ).all()
    }
    policies = {
        row.shift_template_id: row
        for row in db.query(RosterShiftTemplatePolicy).filter(
            RosterShiftTemplatePolicy.amo_id == version.amo_id,
            RosterShiftTemplatePolicy.shift_template_id.in_(template_ids or ["__none__"]),
        ).all()
    }
    issues: list[str] = []
    required_statuses = {
        models.RosterAssignmentStatus.DUTY,
        models.RosterAssignmentStatus.STANDBY,
        models.RosterAssignmentStatus.TRAINING,
    }
    for assignment in active:
        if assignment.status in required_statuses and not assignment.shift_template_id:
            issues.append(f"Assignment {assignment.id} has {common.enum_value(assignment.status)} status without a roster code")
            continue
        if not assignment.shift_template_id:
            continue
        template = templates.get(assignment.shift_template_id)
        if not template:
            issues.append(f"Assignment {assignment.id} references a missing roster code")
            continue
        if not template.is_active:
            issues.append(f"Roster code {template.code} is retired and cannot be used for a new publication")
        policy = policies.get(template.id)
        if not policy:
            issues.append(f"Roster code {template.code} has not been reviewed in the code registry")
            continue
        verification = common.enum_value(policy.verification_status)
        if verification != RosterCodeVerificationStatus.CONFIRMED.value:
            issues.append(f"Roster code {template.code} is {verification.replace('_', ' ').lower()}")
        duty_date = assignment.starts_at.date()
        if policy.effective_from and duty_date < policy.effective_from:
            issues.append(f"Roster code {template.code} is not effective on {duty_date.isoformat()}")
        if policy.effective_to and duty_date > policy.effective_to:
            issues.append(f"Roster code {template.code} expired before {duty_date.isoformat()}")
    return list(dict.fromkeys(issues))


def assert_registry_ready(db: Session, *, version: models.RosterVersion) -> None:
    issues = registry_issues(db, version=version)
    if issues:
        preview = "; ".join(issues[:8])
        suffix = f"; plus {len(issues) - 8} more" if len(issues) > 8 else ""
        raise ValueError(f"Roster code registry is not publication-ready: {preview}{suffix}")


def _user_name(db: Session, *, amo_id: str, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    row = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
    ).first()
    return getattr(row, "full_name", None) if row else None


def _aircraft_by_assignment(db: Session, *, amo_id: str, assignment_ids: list[str]) -> dict[str, dict[str, str]]:
    if not assignment_ids:
        return {}
    buckets: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"registrations": [], "display_codes": []})
    rows = (
        db.query(RosterAircraftAllocation, fleet_models.Aircraft)
        .join(
            fleet_models.Aircraft,
            fleet_models.Aircraft.serial_number == RosterAircraftAllocation.aircraft_serial_number,
        )
        .filter(
            RosterAircraftAllocation.amo_id == amo_id,
            RosterAircraftAllocation.roster_assignment_id.in_(assignment_ids),
            fleet_models.Aircraft.amo_id == amo_id,
        )
        .order_by(RosterAircraftAllocation.roster_assignment_id.asc(), RosterAircraftAllocation.starts_at.asc())
        .all()
    )
    for allocation, aircraft in rows:
        bucket = buckets[allocation.roster_assignment_id]
        registration = str(aircraft.registration)
        display_code = str(aircraft.internal_aircraft_identifier or aircraft.registration)
        if registration not in bucket["registrations"]:
            bucket["registrations"].append(registration)
        if display_code not in bucket["display_codes"]:
            bucket["display_codes"].append(display_code)
    return {
        key: {
            "aircraft_registrations": ", ".join(value["registrations"]),
            "aircraft_display_codes": ", ".join(value["display_codes"]),
        }
        for key, value in buckets.items()
    }


def build_snapshot(db: Session, *, version: models.RosterVersion, legacy_reconstructed: bool = False) -> dict[str, Any]:
    settings = get_or_create_settings(db, amo_id=version.amo_id, actor_user_id=version.created_by_user_id)
    assignments = sorted(
        [row for row in version.assignments or [] if row.deleted_at is None],
        key=lambda row: (getattr(row.user, "full_name", "") or "", row.starts_at, row.id),
    )
    lineages = ensure_assignment_lineages(db, version=version)
    aircraft = _aircraft_by_assignment(db, amo_id=version.amo_id, assignment_ids=[row.id for row in assignments])
    template_ids = {row.shift_template_id for row in assignments if row.shift_template_id}
    policies = {
        row.shift_template_id: row
        for row in db.query(RosterShiftTemplatePolicy).filter(
            RosterShiftTemplatePolicy.amo_id == version.amo_id,
            RosterShiftTemplatePolicy.shift_template_id.in_(template_ids or ["__none__"]),
        ).all()
    }
    legend_map: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for assignment in assignments:
        template = assignment.shift_template
        policy = policies.get(assignment.shift_template_id) if assignment.shift_template_id else None
        shift_code = getattr(template, "code", None) or common.enum_value(assignment.status)
        if template and shift_code not in legend_map:
            legend_map[shift_code] = {
                "code": shift_code,
                "label": template.label,
                "default_start_time": template.default_start_time,
                "default_end_time": template.default_end_time,
                "unpaid_break_minutes": int(getattr(policy, "unpaid_break_minutes", 0) or 0),
                "duty_semantic": common.enum_value(getattr(policy, "duty_semantic", RosterDutySemantic.DUTY)),
                "verification_status": common.enum_value(getattr(policy, "verification_status", RosterCodeVerificationStatus.UNRESOLVED)),
                "description": template.description,
            }
        aircraft_values = aircraft.get(assignment.id, {})
        rows.append({
            "assignment_id": assignment.id,
            "calendar_lineage": lineages.get(assignment.id),
            "staff_code": getattr(assignment.user, "staff_code", None),
            "full_name": getattr(assignment.user, "full_name", assignment.user_id),
            "department_code": getattr(assignment.department, "code", None),
            "base_code": getattr(assignment.base_station, "code", None),
            "shift_code": shift_code,
            "status": common.enum_value(assignment.status),
            "starts_at": assignment.starts_at.isoformat(),
            "ends_at": assignment.ends_at.isoformat(),
            "planned_minutes": assignment.planned_minutes,
            "role_label": assignment.role_label,
            "team_code": assignment.team_code,
            "location_label": assignment.location_label,
            "aircraft_registrations": aircraft_values.get("aircraft_registrations", ""),
            "aircraft_display_codes": aircraft_values.get("aircraft_display_codes", ""),
        })
    return {
        "schema_version": 1,
        "legacy_reconstructed": legacy_reconstructed,
        "amo_id": version.amo_id,
        "version_id": version.id,
        "version_no": version.version_no,
        "status": common.enum_value(version.status),
        "period": {
            "id": version.period_id,
            "code": version.period.period_code,
            "name": version.period.name,
            "starts_on": version.period.starts_on.isoformat(),
            "ends_on": version.period.ends_on.isoformat(),
            "timezone_name": version.period.timezone_name,
        },
        "document": {
            "form_number": settings.form_number,
            "revision_label": settings.revision_label,
            "revision_date": settings.revision_date.isoformat() if settings.revision_date else None,
            "footer_note": settings.footer_note,
            "prepared_by_label": settings.prepared_by_label,
            "approved_by_label": settings.approved_by_label,
            "page_size": settings.page_size,
            "prepared_by": _user_name(db, amo_id=version.amo_id, user_id=version.created_by_user_id),
            "prepared_date": version.created_at.date().isoformat() if version.created_at else None,
            "approved_by": _user_name(db, amo_id=version.amo_id, user_id=version.approved_by_user_id),
            "approved_date": version.approved_at.date().isoformat() if version.approved_at else None,
            "published_by": _user_name(db, amo_id=version.amo_id, user_id=version.published_by_user_id),
            "published_at": version.published_at.isoformat() if version.published_at else None,
        },
        "legend": [legend_map[key] for key in sorted(legend_map)],
        "rows": rows,
    }


def _snapshot_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def capture_publication_snapshot(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
) -> RosterPublicationSnapshot:
    existing = db.query(RosterPublicationSnapshot).filter(
        RosterPublicationSnapshot.amo_id == version.amo_id,
        RosterPublicationSnapshot.version_id == version.id,
    ).first()
    if existing:
        return existing
    payload = build_snapshot(db, version=version)
    row = RosterPublicationSnapshot(
        amo_id=version.amo_id,
        version_id=version.id,
        snapshot_json=payload,
        snapshot_hash=_snapshot_hash(payload),
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterPublicationSnapshot",
        entity_id=row.id,
        action="capture",
        after={"version_id": version.id, "snapshot_hash": row.snapshot_hash},
        critical=True,
    )
    return row


def snapshot_for_export(db: Session, *, version: models.RosterVersion, actor_user_id: Optional[str] = None) -> dict[str, Any]:
    if version.status == models.RosterVersionStatus.PUBLISHED:
        row = db.query(RosterPublicationSnapshot).filter(
            RosterPublicationSnapshot.amo_id == version.amo_id,
            RosterPublicationSnapshot.version_id == version.id,
        ).first()
        if row:
            return dict(row.snapshot_json)
        payload = build_snapshot(db, version=version, legacy_reconstructed=True)
        row = RosterPublicationSnapshot(
            amo_id=version.amo_id,
            version_id=version.id,
            snapshot_json=payload,
            snapshot_hash=_snapshot_hash(payload),
            created_by_user_id=actor_user_id,
        )
        db.add(row)
        db.flush()
        return payload
    return build_snapshot(db, version=version)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def subscription_status(db: Session, *, amo_id: str, user_id: str) -> Optional[RosterCalendarSubscription]:
    return db.query(RosterCalendarSubscription).filter(
        RosterCalendarSubscription.amo_id == amo_id,
        RosterCalendarSubscription.user_id == user_id,
    ).first()


def issue_calendar_subscription(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    actor_user_id: str,
) -> tuple[RosterCalendarSubscription, str]:
    raw_token = secrets.token_urlsafe(32)
    hashed = _token_hash(raw_token)
    row = subscription_status(db, amo_id=amo_id, user_id=user_id)
    now = common.utcnow()
    if row:
        row.token_hash = hashed
        row.rotated_at = now
        row.revoked_at = None
    else:
        row = RosterCalendarSubscription(
            amo_id=amo_id,
            user_id=user_id,
            token_hash=hashed,
            created_by_user_id=actor_user_id,
        )
        db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterCalendarSubscription",
        entity_id=row.id,
        action="rotate" if row.rotated_at else "create",
        after={"user_id": user_id, "active": True},
        critical=True,
    )
    return row, raw_token


def revoke_calendar_subscription(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    actor_user_id: str,
) -> Optional[RosterCalendarSubscription]:
    row = subscription_status(db, amo_id=amo_id, user_id=user_id)
    if not row:
        return None
    row.revoked_at = common.utcnow()
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterCalendarSubscription",
        entity_id=row.id,
        action="revoke",
        after={"user_id": user_id, "active": False},
        critical=True,
    )
    return row


def resolve_calendar_subscription(db: Session, *, raw_token: str) -> Optional[RosterCalendarSubscription]:
    row = db.query(RosterCalendarSubscription).filter(
        RosterCalendarSubscription.token_hash == _token_hash(raw_token),
        RosterCalendarSubscription.revoked_at.is_(None),
    ).first()
    if row:
        row.last_used_at = common.utcnow()
        db.add(row)
        db.flush()
    return row


def stable_personal_calendar(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> str:
    content = calendar_feed.personal_calendar(
        db,
        amo_id=amo_id,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
    )
    start = from_date or (date.today() - __import__("datetime").timedelta(days=30))
    end = to_date or (date.today() + __import__("datetime").timedelta(days=400))
    assignments = calendar_feed._published_assignments(
        db,
        amo_id=amo_id,
        user_id=user_id,
        from_date=start,
        to_date=end,
    )
    replacements: dict[str, str] = {}
    by_version: dict[str, list[models.RosterAssignment]] = defaultdict(list)
    for assignment in assignments:
        by_version[assignment.version_id].append(assignment)
    for version_id in by_version:
        version = db.query(models.RosterVersion).filter(
            models.RosterVersion.amo_id == amo_id,
            models.RosterVersion.id == version_id,
        ).first()
        if not version:
            continue
        lineages = ensure_assignment_lineages(db, version=version)
        for assignment in by_version[version_id]:
            lineage = lineages.get(assignment.id)
            if lineage:
                replacements[assignment.id] = lineage
                if assignment.source_reference_id:
                    replacements[assignment.source_reference_id] = lineage
    for old_key, lineage in replacements.items():
        content = content.replace(
            f"UID:roster:{old_key}@amo-portal",
            f"UID:roster:{lineage}@amo-portal",
        )
    return content


def _stable_assignment_ics(rows: list[dict[str, Any]], *, calendar_name: str = "AMO Duty Roster") -> str:
    from datetime import datetime, timezone

    generated = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AMO Portal//Duty Rostering//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{exports._ics_escape(calendar_name)}",
    ]
    for row in rows:
        starts_at = datetime.fromisoformat(str(row["starts_at"]))
        ends_at = datetime.fromisoformat(str(row["ends_at"]))
        aircraft = row.get("aircraft_registrations") or ""
        summary_parts = [row.get("shift_code") or row.get("status") or "Duty", row.get("base_code") or "Base unassigned"]
        if aircraft:
            summary_parts.append(aircraft)
        summary = " · ".join(str(value) for value in summary_parts if value)
        description = "\n".join(filter(None, [
            f"Status: {row.get('status')}",
            f"Role: {row.get('role_label')}" if row.get("role_label") else None,
            f"Team: {row.get('team_code')}" if row.get("team_code") else None,
            f"Aircraft: {aircraft}" if aircraft else None,
            f"Location: {row.get('location_label')}" if row.get("location_label") else None,
        ]))
        uid = row.get("calendar_lineage") or row.get("assignment_id")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:roster:{exports._ics_escape(uid)}@amo-portal",
            f"DTSTAMP:{exports._ics_datetime(generated)}",
            f"DTSTART:{exports._ics_datetime(starts_at)}",
            f"DTEND:{exports._ics_datetime(ends_at)}",
            f"SUMMARY:{exports._ics_escape(summary)}",
            f"DESCRIPTION:{exports._ics_escape(description)}",
            f"LOCATION:{exports._ics_escape(row.get('location_label') or row.get('base_code') or '')}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def install_service_policy(service_module) -> None:
    if getattr(service_module, "_roster_control_policy_installed", False):
        return
    original_create_version = service_module.create_version
    original_publish_version = service_module.publish_version
    original_export_rows = service_module.assignment_export_rows
    original_notify = common.notify_email

    def create_version_with_lineage(*args, **kwargs):
        row = original_create_version(*args, **kwargs)
        db = args[0] if args else kwargs["db"]
        ensure_assignment_lineages(db, version=row)
        return row

    def publish_version_controlled(*args, **kwargs):
        db = args[0] if args else kwargs["db"]
        version = kwargs.get("version") or (args[1] if len(args) > 1 else None)
        actor_user_id = kwargs.get("actor_user_id") or (args[2] if len(args) > 2 else None)
        assert_registry_ready(db, version=version)
        ensure_assignment_lineages(db, version=version)
        row = original_publish_version(*args, **kwargs)
        capture_publication_snapshot(db, version=row, actor_user_id=actor_user_id)
        return row

    def export_rows_with_lineage(*args, **kwargs):
        db = args[0] if args else kwargs["db"]
        rows = original_export_rows(*args, **kwargs)
        assignment_ids = [str(row.get("assignment_id")) for row in rows if row.get("assignment_id")]
        mappings = {
            row.assignment_id: row.lineage_key
            for row in db.query(RosterAssignmentLineage).filter(
                RosterAssignmentLineage.assignment_id.in_(assignment_ids or ["__none__"])
            ).all()
        }
        for item in rows:
            item["calendar_lineage"] = mappings.get(str(item.get("assignment_id")))
        return rows

    def notify_without_legacy_calendar_link(*args, **kwargs):
        if kwargs.get("template_key") == "rostering.published" and isinstance(kwargs.get("context"), dict):
            context = dict(kwargs["context"])
            route = str(context.get("route") or "/rostering/my-roster")
            context["calendar_feed_path"] = f"{route}?calendar=1"
            kwargs["context"] = context
        return original_notify(*args, **kwargs)

    service_module.create_version = create_version_with_lineage
    service_module.publish_version = publish_version_controlled
    service_module.assignment_export_rows = export_rows_with_lineage
    exports.assignment_ics = _stable_assignment_ics
    common.notify_email = notify_without_legacy_calendar_link
    service_module._roster_control_policy_installed = True
