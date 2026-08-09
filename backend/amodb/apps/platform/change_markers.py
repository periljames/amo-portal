from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .ops_data_models import PlatformChangeMarker


def _safe_details(details: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(details, dict):
        return {}
    return {
        str(key).strip()[:64]: str(value).strip()[:512]
        for key, value in details.items()
        if str(key).strip()
        and value is not None
        and not isinstance(value, (dict, list, tuple, set))
    }


def record_deployment_marker(
    db: Session,
    *,
    reference: str,
    title: str | None = None,
    details: dict[str, Any] | None = None,
) -> PlatformChangeMarker:
    """Record one automated deployment marker for a deployment execution.

    ``reference`` is the idempotency key supplied by the deployment process. A
    retry using the same reference updates the same automation-owned marker
    instead of creating a duplicate. Human-created markers are deliberately
    excluded from this upsert by requiring ``actor_user_id IS NULL``.
    """

    normalized_reference = str(reference or "").strip()[:255]
    if not normalized_reference:
        raise ValueError("deployment marker reference is required")

    normalized_title = str(title or f"Deployment {normalized_reference}").strip()[:255]
    if not normalized_title:
        raise ValueError("deployment marker title is required")

    safe_details = _safe_details(details)
    row = (
        db.query(PlatformChangeMarker)
        .filter(
            PlatformChangeMarker.kind == "DEPLOYMENT",
            PlatformChangeMarker.reference == normalized_reference,
            PlatformChangeMarker.actor_user_id.is_(None),
        )
        .order_by(PlatformChangeMarker.occurred_at.desc())
        .first()
    )
    if row is None:
        row = PlatformChangeMarker(
            kind="DEPLOYMENT",
            reference=normalized_reference,
            title=normalized_title,
            details_json=safe_details,
            actor_user_id=None,
        )
        db.add(row)
    else:
        row.title = normalized_title
        row.details_json = safe_details

    db.commit()
    db.refresh(row)
    return row
