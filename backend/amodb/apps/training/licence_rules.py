"""Governed mapping between regulatory licence courses and licence expiry."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from . import workbook_models


_AUTHORITY_BY_CODE = {
    "AMEL": "KCAA",
    "KAMEL": "KCAA",
    "KENYAAMEL": "KCAA",
    "EAMEL": "ETHIOPIAN_CAA",
    "ETHIOPIANAMEL": "ETHIOPIAN_CAA",
    "ETHIOPIAAMEL": "ETHIOPIAN_CAA",
    "GAMEL": "GHANA_CAA",
    "GHANAAMEL": "GHANA_CAA",
}


def infer_licence_authority(course_code: str | None, course_name: str | None = None) -> str | None:
    """Return an authority only for an explicit AMEL-style licence course."""
    normalized_code = re.sub(r"[^A-Z0-9]+", "", str(course_code or "").upper())
    if normalized_code in _AUTHORITY_BY_CODE:
        return _AUTHORITY_BY_CODE[normalized_code]

    normalized_name = re.sub(r"\s+", " ", str(course_name or "").strip().upper())
    is_licence_course = (
        "AMEL" in normalized_name
        or (
            "AIRCRAFT MAINTENANCE" in normalized_name
            and "ENGINEER" in normalized_name
            and ("LICENCE" in normalized_name or "LICENSE" in normalized_name)
        )
    )
    if not is_licence_course:
        return None
    if "GHANA" in normalized_name:
        return "GHANA_CAA"
    if "ETHIOPI" in normalized_name:
        return "ETHIOPIAN_CAA"
    if "KENYA" in normalized_name or normalized_code == "AMEL":
        return "KCAA"
    return None


def authority_for_course(course: object) -> str | None:
    configured = str(getattr(course, "licence_authority", "") or "").strip().upper()
    return configured or infer_licence_authority(
        getattr(course, "course_id", None),
        getattr(course, "course_name", None),
    )


def sync_licence_expiry_from_records(
    db: Session,
    *,
    amo_id: str,
    records: Iterable[object],
    courses_by_id: dict[str, object],
) -> int:
    """Synchronize each authority from the latest governed AMEL renewal record."""
    candidates: dict[tuple[str, str], tuple[object, object]] = {}
    for record in records:
        valid_until = getattr(record, "valid_until", None)
        if valid_until is None:
            continue
        course = courses_by_id.get(str(getattr(record, "course_id", "")))
        if course is None:
            continue
        authority = authority_for_course(course)
        if not authority:
            continue
        key = (str(getattr(record, "user_id")), authority)
        current = candidates.get(key)
        current_record = current[0] if current else None
        record_key = (
            getattr(record, "completion_date", None) or getattr(record, "valid_until", None),
            str(getattr(record, "id", "")),
        )
        current_key = (
            (getattr(current_record, "completion_date", None) or getattr(current_record, "valid_until", None))
            if current_record is not None else None,
            str(getattr(current_record, "id", "")) if current_record is not None else "",
        )
        if current_record is None or record_key > current_key:
            candidates[key] = (record, course)

    if not candidates:
        return 0
    user_ids = sorted({user_id for user_id, _authority in candidates})
    authorities = sorted({authority for _user_id, authority in candidates})
    licences = db.query(workbook_models.PersonnelLicence).filter(
        workbook_models.PersonnelLicence.amo_id == amo_id,
        workbook_models.PersonnelLicence.user_id.in_(user_ids),
        workbook_models.PersonnelLicence.authority.in_(authorities),
        workbook_models.PersonnelLicence.status == "ACTIVE",
    ).all()
    now = datetime.now(timezone.utc)
    updated = 0
    for licence in licences:
        candidate = candidates.get((str(licence.user_id), str(licence.authority).upper()))
        if candidate is None:
            continue
        record, course = candidate
        licence.expires_on = record.valid_until
        licence.expiry_source_record_id = str(record.id)
        licence.expiry_source_course_id = str(course.id)
        licence.expiry_synced_at = now
        db.add(licence)
        updated += 1
    return updated
