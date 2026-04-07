from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from . import models, schemas


@dataclass
class ParsedCourseRow:
    row_number: int
    course_id: str
    course_name: str
    frequency_months: Optional[int]
    status: str
    category_raw: Optional[str]
    is_mandatory: bool
    scope: Optional[str]
    reference: Optional[str]


EXPECTED_HEADERS = [
    "CourseID",
    "CourseName",
    "FrequencyMonths",
    "Status",
    "Category",
    "Mandatory",
    "Scope",
    "Reference",
]

ALLOWED_STATUSES = {
    "initial": "Initial",
    "recurrent": "Recurrent",
    "one_off": "One_Off",
}


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_course_name(value: Any) -> Optional[str]:
    raw = _clean(value)
    if raw is None:
        return None
    # Intentionally normalize all whitespace (including embedded newlines) to single spaces.
    return re.sub(r"\s+", " ", raw).strip()


def _parse_frequency(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("FrequencyMonths must be an integer or blank")
    if isinstance(value, (int, float)):
        if int(value) != value:
            raise ValueError("FrequencyMonths must be an integer or blank")
        return int(value)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    raise ValueError("FrequencyMonths must be an integer or blank")


def _parse_mandatory(value: Any) -> bool:
    raw = (_clean(value) or "").lower()
    if raw in {"", "no", "n", "false", "0"}:
        return False
    if raw in {"yes", "y", "true", "1"}:
        return True
    raise ValueError("Mandatory must be Yes/No (or blank)")


def _parse_status(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        raise ValueError("Status is required")
    canonical = ALLOWED_STATUSES.get(raw.lower())
    if canonical is None:
        raise ValueError("Status must be one of: Initial, Recurrent, One_Off")
    return canonical


def parse_courses_sheet(file_bytes: bytes, *, filename: str, sheet_name: str = "Courses") -> list[dict[str, Any]]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in {"xlsx", "xlsm", "xltx", "xltm"}:
        raise ValueError("Only Excel .xlsx/.xlsm files are supported for courses import.")
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for courses import. Install openpyxl.") from exc

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found.")
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(c).strip() if c is not None else "" for c in rows[0]]
    if headers != EXPECTED_HEADERS:
        raise ValueError(
            f"Unexpected headers in '{sheet_name}'. Expected exact order {EXPECTED_HEADERS}, got {headers}"
        )

    parsed: list[dict[str, Any]] = []
    for idx, values in enumerate(rows[1:], start=2):
        row = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))}
        if not any(v is not None and str(v).strip() for v in row.values()):
            continue
        parsed.append({"row_number": idx, **row})
    return parsed


def _build_parsed_course(raw: dict[str, Any]) -> ParsedCourseRow:
    course_id = (_clean(raw.get("CourseID")) or "").upper()
    course_name = _normalize_course_name(raw.get("CourseName")) or ""
    if not course_id:
        raise ValueError("CourseID is required")
    if not course_name:
        raise ValueError("CourseName is required")
    return ParsedCourseRow(
        row_number=int(raw["row_number"]),
        course_id=course_id,
        course_name=course_name,
        frequency_months=_parse_frequency(raw.get("FrequencyMonths")),
        status=_parse_status(raw.get("Status")),
        category_raw=_clean(raw.get("Category")),
        is_mandatory=_parse_mandatory(raw.get("Mandatory")),
        scope=_clean(raw.get("Scope")),
        reference=_clean(raw.get("Reference")),
    )


def import_courses_rows(
    db: Session,
    *,
    amo_id: str,
    rows: list[dict[str, Any]],
    dry_run: bool,
) -> schemas.CourseImportSummary:
    issues: list[schemas.CourseImportRowIssue] = []
    created_courses = 0
    updated_courses = 0
    seen_ids: set[str] = set()

    for raw in rows:
        try:
            parsed = _build_parsed_course(raw)
        except ValueError as exc:
            issues.append(schemas.CourseImportRowIssue(row_number=int(raw.get("row_number") or 0), reason=str(exc)))
            continue

        if parsed.course_id.lower() in seen_ids:
            issues.append(
                schemas.CourseImportRowIssue(
                    row_number=parsed.row_number,
                    course_id=parsed.course_id,
                    reason="Duplicate CourseID inside import file.",
                )
            )
            continue
        seen_ids.add(parsed.course_id.lower())

        existing = (
            db.query(models.TrainingCourse)
            .filter(models.TrainingCourse.amo_id == amo_id, models.TrainingCourse.course_id == parsed.course_id)
            .first()
        )
        if existing is None:
            created_courses += 1
            if not dry_run:
                db.add(
                    models.TrainingCourse(
                        amo_id=amo_id,
                        course_id=parsed.course_id,
                        course_name=parsed.course_name,
                        frequency_months=parsed.frequency_months,
                        status=parsed.status,
                        category_raw=parsed.category_raw,
                        scope=parsed.scope,
                        regulatory_reference=parsed.reference,
                        is_mandatory=parsed.is_mandatory,
                    )
                )
            continue

        updated_courses += 1
        if not dry_run:
            existing.course_name = parsed.course_name
            existing.frequency_months = parsed.frequency_months
            existing.status = parsed.status
            existing.category_raw = parsed.category_raw
            existing.scope = parsed.scope
            existing.regulatory_reference = parsed.reference
            existing.is_mandatory = parsed.is_mandatory
            db.add(existing)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return schemas.CourseImportSummary(
        dry_run=dry_run,
        total_rows=len(rows),
        created_courses=created_courses,
        updated_courses=updated_courses,
        skipped_rows=len(issues),
        issues=issues,
    )
