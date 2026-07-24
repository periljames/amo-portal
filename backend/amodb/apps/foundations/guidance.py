from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..workforce import models as workforce_models

GUIDANCE_ROOT_KEY = "_contextual_guidance"


class GuidanceStateRead(BaseModel):
    topic: str
    version: int
    acknowledged: bool
    acknowledged_at: Optional[datetime] = None


class GuidanceAcknowledgeRequest(BaseModel):
    version: int = Field(ge=1)


def _preference(db: Session, *, amo_id: str, user_id: str) -> workforce_models.PlannerPreference:
    row = db.query(workforce_models.PlannerPreference).filter(
        workforce_models.PlannerPreference.amo_id == amo_id,
        workforce_models.PlannerPreference.user_id == user_id,
    ).first()
    if row:
        return row
    row = workforce_models.PlannerPreference(
        amo_id=amo_id,
        user_id=user_id,
        density="compact",
        group_by="department",
        zoom="day",
        filters_json={},
    )
    db.add(row)
    db.flush()
    return row


def _topic_state(row: workforce_models.PlannerPreference, topic: str, version: int) -> Optional[str]:
    filters = dict(row.filters_json or {})
    guidance = filters.get(GUIDANCE_ROOT_KEY)
    if not isinstance(guidance, dict):
        return None
    topic_versions = guidance.get(topic)
    if not isinstance(topic_versions, dict):
        return None
    value = topic_versions.get(str(version))
    return value if isinstance(value, str) and value else None


def guidance_state(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    topic: str,
    version: int,
) -> GuidanceStateRead:
    row = _preference(db, amo_id=amo_id, user_id=user_id)
    acknowledged_at_raw = _topic_state(row, topic, version)
    acknowledged_at: Optional[datetime] = None
    if acknowledged_at_raw:
        try:
            acknowledged_at = datetime.fromisoformat(acknowledged_at_raw)
        except ValueError:
            acknowledged_at = None
    return GuidanceStateRead(
        topic=topic,
        version=version,
        acknowledged=acknowledged_at_raw is not None,
        acknowledged_at=acknowledged_at,
    )


def acknowledge_guidance(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    topic: str,
    version: int,
) -> GuidanceStateRead:
    row = _preference(db, amo_id=amo_id, user_id=user_id)
    filters = dict(row.filters_json or {})
    guidance = dict(filters.get(GUIDANCE_ROOT_KEY) or {})
    topic_versions = dict(guidance.get(topic) or {})
    acknowledged_at = datetime.now(timezone.utc)
    topic_versions[str(version)] = acknowledged_at.isoformat()
    guidance[topic] = topic_versions
    filters[GUIDANCE_ROOT_KEY] = guidance
    row.filters_json = filters
    db.add(row)
    db.flush()
    return GuidanceStateRead(
        topic=topic,
        version=version,
        acknowledged=True,
        acknowledged_at=acknowledged_at,
    )
