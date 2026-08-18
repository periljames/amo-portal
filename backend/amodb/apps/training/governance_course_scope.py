"""Compatibility adapters between legacy Training IDs and governed revisions.

TrainingCourse.id remains the canonical course identity for existing authorisations.
New governed workflows frequently carry TrainingCourseRevision.id.  Resolve the
revision back to its parent course before applying technical scope checks so the
revision layer never silently changes the meaning of existing authorisations.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import governance_models as models
from .governance_service import technical_authorisation_readiness as _base_readiness


def technical_authorisation_readiness(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    privilege_type: str,
    on_date: date,
    course_id: str | None = None,
    aircraft: str | None = None,
    require_theory: bool = False,
    require_practical: bool = False,
    require_ojt: bool = False,
) -> dict[str, object]:
    canonical_course_id = course_id
    if course_id:
        revision = (
            db.query(models.TrainingCourseRevision)
            .filter(
                models.TrainingCourseRevision.amo_id == amo_id,
                models.TrainingCourseRevision.id == course_id,
            )
            .first()
        )
        if revision is not None:
            canonical_course_id = str(revision.course_id)

    return _base_readiness(
        db,
        amo_id=amo_id,
        user_id=user_id,
        privilege_type=privilege_type,
        on_date=on_date,
        course_id=canonical_course_id,
        aircraft=aircraft,
        require_theory=require_theory,
        require_practical=require_practical,
        require_ojt=require_ojt,
    )
