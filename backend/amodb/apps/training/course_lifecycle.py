from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from . import models as training_models


_RECURRENT_VALUES = {"REFRESHER", "RECURRENT", "CONTINUATION", "RENEWAL"}


def normalized_training_kind(value: Any) -> str:
    """Return the canonical controlled lifecycle kind.

    Historical REFRESHER/CONTINUATION/RENEWAL values remain stored as-is but are
    evaluated as RECURRENT. Course names and codes are intentionally ignored.
    """

    raw = getattr(value, "value", value)
    normalized = str(raw or "").strip().upper()
    if normalized == "INITIAL":
        return "INITIAL"
    if normalized in _RECURRENT_VALUES:
        return "RECURRENT"
    if normalized in {"ONE_OFF", "ONE-OFF", "ONE OFF"}:
        return "ONE_OFF"
    return normalized or "OTHER"


def training_kind_for_course(course: training_models.TrainingCourse | Any) -> str:
    kind = normalized_training_kind(getattr(course, "kind", None))
    if kind != "OTHER":
        return kind
    return normalized_training_kind(getattr(course, "status", None))


def is_initial_course(course: training_models.TrainingCourse | Any) -> bool:
    return training_kind_for_course(course) == "INITIAL"


def is_recurrent_course(course: training_models.TrainingCourse | Any) -> bool:
    return training_kind_for_course(course) == "RECURRENT"


def explicit_recurrence_key(
    course: training_models.TrainingCourse | Any,
    courses: Iterable[training_models.TrainingCourse | Any] = (),
) -> str:
    """Return a relationship key using only explicit catalogue data."""

    group_code = str(getattr(course, "group_code", "") or "").strip()
    if group_code:
        return f"group:{group_code.casefold()}"

    prerequisite = str(getattr(course, "prerequisite_course_id", "") or "").strip()
    if prerequisite:
        return f"prerequisite:{prerequisite.casefold()}"

    course_ids = {
        str(getattr(course, "id", "") or "").strip().casefold(),
        str(getattr(course, "course_id", "") or "").strip().casefold(),
    }
    course_ids.discard("")
    for candidate in courses:
        declared = str(getattr(candidate, "prerequisite_course_id", "") or "").strip().casefold()
        if declared and declared in course_ids:
            return f"prerequisite:{declared}"

    identity = str(getattr(course, "id", None) or getattr(course, "course_id", None) or "unknown")
    return f"course:{identity}"


def related_recurrent_courses(
    db: Session,
    *,
    amo_id: str,
    initial_course: training_models.TrainingCourse,
) -> list[training_models.TrainingCourse]:
    """Resolve Initial -> Recurrent relationships from explicit catalogue fields only."""

    initial_ids = {
        str(getattr(initial_course, "id", "") or "").strip().casefold(),
        str(getattr(initial_course, "course_id", "") or "").strip().casefold(),
    }
    initial_ids.discard("")
    initial_group = str(getattr(initial_course, "group_code", "") or "").strip().casefold()

    courses = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.is_active.is_(True),
        )
        .all()
    )

    related: list[training_models.TrainingCourse] = []
    for course in courses:
        if str(getattr(course, "id", "")) == str(getattr(initial_course, "id", "")):
            continue
        if not is_recurrent_course(course):
            continue

        prerequisite = str(getattr(course, "prerequisite_course_id", "") or "").strip().casefold()
        group_code = str(getattr(course, "group_code", "") or "").strip().casefold()
        if prerequisite and prerequisite in initial_ids:
            related.append(course)
            continue
        if initial_group and group_code and group_code == initial_group:
            related.append(course)

    return related


@dataclass(frozen=True)
class LifecycleProblem:
    course_id: str
    code: str
    problem: str


def validate_lifecycle_relationships(courses: Iterable[training_models.TrainingCourse | Any]) -> list[LifecycleProblem]:
    """Return catalogue relationship problems without mutating production data."""

    rows = list(courses)
    by_identifier: dict[str, Any] = {}
    for course in rows:
        for value in (getattr(course, "id", None), getattr(course, "course_id", None)):
            key = str(value or "").strip().casefold()
            if key:
                by_identifier[key] = course

    problems: list[LifecycleProblem] = []
    for course in rows:
        prerequisite = str(getattr(course, "prerequisite_course_id", "") or "").strip()
        if not prerequisite:
            continue
        target = by_identifier.get(prerequisite.casefold())
        if target is None:
            problems.append(
                LifecycleProblem(
                    course_id=str(getattr(course, "id", "")),
                    code=str(getattr(course, "course_id", "")),
                    problem=f"Declared prerequisite {prerequisite!r} does not resolve to a course in this catalogue.",
                )
            )
            continue
        if is_recurrent_course(course) and not is_initial_course(target):
            problems.append(
                LifecycleProblem(
                    course_id=str(getattr(course, "id", "")),
                    code=str(getattr(course, "course_id", "")),
                    problem=f"Recurrent prerequisite {prerequisite!r} is not explicitly classified as Initial.",
                )
            )
    return problems


__all__ = [
    "LifecycleProblem",
    "explicit_recurrence_key",
    "is_initial_course",
    "is_recurrent_course",
    "normalized_training_kind",
    "related_recurrent_courses",
    "training_kind_for_course",
    "validate_lifecycle_relationships",
]
