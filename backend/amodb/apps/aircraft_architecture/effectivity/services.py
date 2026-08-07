from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import models, schemas
from .evaluator import evaluate_expression, impact_analysis


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_content_hash(version: models.EffectivityRuleVersion) -> str:
    payload = {
        "rule_set_code": version.rule_set.code,
        "version_code": version.version_code,
        "effective_date": version.effective_date,
        "expression": version.expression_json,
        "source_reference": version.source_reference,
        "source_revision": version.source_revision,
        "source_checksum_sha256": version.source_checksum_sha256,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def require_catalogue_writer(user: Any) -> None:
    if not bool(getattr(user, "is_superuser", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform superusers may publish global effectivity rules.",
        )


def require_draft(version: models.EffectivityRuleVersion) -> None:
    if version.status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published, superseded and withdrawn effectivity versions are immutable.",
        )


def get_version(db: Session, version_id: str) -> models.EffectivityRuleVersion:
    row = db.get(models.EffectivityRuleVersion, version_id)
    if not row:
        raise HTTPException(status_code=404, detail="Effectivity rule version not found")
    return row


def create_rule_set(
    db: Session,
    payload: schemas.RuleSetCreate,
    actor_id: str | None,
) -> models.EffectivityRuleSet:
    duplicate = (
        db.query(models.EffectivityRuleSet.id)
        .filter(models.EffectivityRuleSet.code == payload.code)
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Effectivity rule-set code already exists")
    row = models.EffectivityRuleSet(
        **payload.model_dump(),
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_version(
    db: Session,
    rule_set_id: str,
    payload: schemas.RuleVersionCreate,
    actor_id: str | None,
) -> models.EffectivityRuleVersion:
    rule_set = db.get(models.EffectivityRuleSet, rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="Effectivity rule set not found")
    if payload.supersedes_version_id:
        previous = get_version(db, payload.supersedes_version_id)
        if previous.rule_set_id != rule_set_id or previous.status not in {
            "PUBLISHED",
            "SUPERSEDED",
        }:
            raise HTTPException(
                status_code=409,
                detail="Superseded version must be a published version of the same rule set",
            )
    try:
        evaluate_expression(payload.expression_json, {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duplicate = (
        db.query(models.EffectivityRuleVersion.id)
        .filter(
            models.EffectivityRuleVersion.rule_set_id == rule_set_id,
            models.EffectivityRuleVersion.version_code == payload.version_code,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Effectivity version code already exists")
    values = payload.model_dump()
    if values.get("source_checksum_sha256"):
        values["source_checksum_sha256"] = values["source_checksum_sha256"].lower()
    row = models.EffectivityRuleVersion(
        rule_set_id=rule_set_id,
        **values,
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def publish_version(
    db: Session,
    version_id: str,
    actor_id: str | None,
    expected_hash: str | None,
) -> models.EffectivityRuleVersion:
    version = get_version(db, version_id)
    require_draft(version)
    actual_hash = compute_content_hash(version)
    if expected_hash and expected_hash != actual_hash:
        raise HTTPException(
            status_code=409,
            detail="Effectivity content changed after review; refresh before publishing",
        )
    current = (
        db.query(models.EffectivityRuleVersion)
        .filter(
            models.EffectivityRuleVersion.rule_set_id == version.rule_set_id,
            models.EffectivityRuleVersion.status == "PUBLISHED",
        )
        .with_for_update()
        .all()
    )
    for previous in current:
        previous.status = "SUPERSEDED"
        db.add(previous)
    version.content_hash = actual_hash
    version.status = "PUBLISHED"
    version.published_by_user_id = actor_id
    version.published_at = datetime.now(timezone.utc)
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def evaluate_saved_version(
    db: Session,
    version_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    version = get_version(db, version_id)
    return evaluate_expression(version.expression_json, context).to_dict()


__all__ = [
    "compute_content_hash",
    "create_rule_set",
    "create_version",
    "evaluate_expression",
    "evaluate_saved_version",
    "impact_analysis",
    "publish_version",
    "require_catalogue_writer",
    "require_draft",
]
