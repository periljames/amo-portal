"""Chronology for scheduled audit meetings, evaluated in the tenant timezone."""
from datetime import datetime, time, timezone

from fastapi import HTTPException


def validate_meeting_timeline(audit, meeting_type, start, end, zone, *, now=None, planned=True):
    if start is None:
        raise HTTPException(422, "Meeting start is required.")
    if planned and end is None:
        raise HTTPException(422, "Meeting end is required.")
    local_start = (start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start).astimezone(zone)
    if planned and local_start < (now or datetime.now(timezone.utc)).astimezone(zone):
        raise HTTPException(422, "Planned meetings cannot start in the past. Choose a future time.")
    if end is not None:
        local_end = (end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end).astimezone(zone)
        if local_end <= local_start:
            raise HTTPException(422, "Meeting end must be after its start.")
    day = audit.planned_start if meeting_type == "OPENING" else audit.planned_end
    if not day or meeting_type not in {"OPENING", "CLOSING"}:
        return
    clock = audit.planned_start_time if meeting_type == "OPENING" else audit.planned_end_time
    if isinstance(clock, str):
        clock = time.fromisoformat(clock)
    boundary = datetime.combine(day, clock or time(9 if meeting_type == "OPENING" else 17), tzinfo=zone)
    if meeting_type == "OPENING" and local_start > boundary:
        raise HTTPException(422, "Opening meeting must start on or before the audit starts.")
    if meeting_type == "CLOSING" and local_start < boundary:
        raise HTTPException(422, "Closing meeting must start on or after the audit ends.")
