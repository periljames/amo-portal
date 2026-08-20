from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models


@dataclass(frozen=True, slots=True)
class TenantTimezone:
    name: str
    tzinfo: tzinfo
    warning: str | None = None


def _parse_timezone(value: str | None) -> TenantTimezone:
    """Resolve an IANA or fixed-offset tenant timezone without guessing a locale.

    Tenant timezone is configuration, not deployment geography. Invalid or absent
    legacy values fall back to UTC and return a warning so callers can surface the
    configuration defect without silently treating the tenant as Nairobi/EAT.
    """

    label = (value or "").strip()
    if not label:
        return TenantTimezone(
            name="UTC",
            tzinfo=timezone.utc,
            warning="Tenant timezone is not configured; UTC is being used.",
        )
    if label.upper() == "UTC":
        return TenantTimezone(name="UTC", tzinfo=timezone.utc)
    try:
        return TenantTimezone(name=label, tzinfo=ZoneInfo(label))
    except ZoneInfoNotFoundError:
        fixed = re.fullmatch(r"UTC([+-])(\d{1,2})(?::?(\d{2}))?", label.upper())
        if fixed:
            sign, hours_raw, minutes_raw = fixed.groups()
            hours = int(hours_raw)
            minutes = int(minutes_raw or "0")
            if hours <= 14 and minutes < 60:
                offset = timedelta(hours=hours, minutes=minutes)
                if sign == "-":
                    offset = -offset
                normalised = f"UTC{sign}{hours:02d}:{minutes:02d}"
                return TenantTimezone(name=normalised, tzinfo=timezone(offset))
        return TenantTimezone(
            name="UTC",
            tzinfo=timezone.utc,
            warning=f"Configured tenant timezone '{label}' is invalid or unavailable; UTC is being used.",
        )


def resolve_tenant_timezone(db: Session, *, amo_id: str) -> TenantTimezone:
    configured = (
        db.query(account_models.AMO.time_zone)
        .filter(account_models.AMO.id == str(amo_id))
        .scalar()
    )
    return _parse_timezone(configured)


def require_requested_tenant_timezone(
    db: Session,
    *,
    amo_id: str,
    requested: str | None,
) -> TenantTimezone:
    """Return the tenant timezone and reject attempts to create a second planner clock."""

    resolved = resolve_tenant_timezone(db, amo_id=amo_id)
    requested_name = (requested or "").strip()
    if requested_name and requested_name != resolved.name:
        raise ValueError(
            f"Quality planner schedules use the tenant timezone '{resolved.name}'. "
            f"Change the AMO profile timezone instead of overriding a single schedule."
        )
    return resolved
