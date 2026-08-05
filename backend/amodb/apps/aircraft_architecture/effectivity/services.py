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
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


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
    db: Session, payload: schemas.RuleSetCreate, actor_id: str | None
) -> models.EffectivityRuleSet:
    duplicate = (
        db.query(models.EffectivityRuleSet.id)
        .filter(models.EffectivityRuleSet.code == payload.code)
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Effectivity rule-set code already exists")
    row = models.EffectivityRuleSet(
        **payload.model_dump(), created_by_user_id=actor_id
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
) -> models.EffectityRuleVersion:
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
    if expected_hash and expected_hash€„ô…ÑÕ…±}¡…Í è(€€€€€€€É…¥Í”!QQAá•ÁÑ¥½¸ (€€€€€€€€€€€ÍÑ…ÑÕÍ}½‘”ôÐÀä°(€€€€€€€€€€€‘•Ñ…¥°ô‰™™•Ñ¥Ù¥Ñä½¹Ñ•¹Ð¡…¹•…™Ñ•ÈÉ•Ù¥•ÜìÉ•™É•Í ‰•™½É”ÁÕ‰±¥Í¡¥¹œˆ°(€€€€€€€€¤(€€€ÕÉÉ•¹Ð€ô€ (€€€€€€€‘ˆ¹ÅÕ•Éä¡µ½‘•±Ì¹™™•Ñ¥Ù¥ÑåIÕ±•Y•ÉÍ¥½¸¤(€€€€€€€€¹™¥±Ñ•È (€€€€€€€€€€€µ½‘•±Ì¹™™•Ñ¥Ù¥ÑåIÕ±•Y•ÉÍ¥½¸¹ÉÕ±•}Í•Ñ}¥€ôôÙ•ÉÍ¥½¸¹ÉÕ±•}Í•Ñ}¥°(€€€€€€€€€€€µ½‘•±Ì¹™™•Ñ¥Ù¥ÑåIÕ±•Y•ÉÍ¥½¸¹ÍÑ…ÑÕÌ€ôô€‰AU	1%M!ˆ°(€€€€€€€€¤(€€€€€€€€¹Ý¥Ñ¡}™½É}ÕÁ‘…Ñ” ¤(€€€€€€€€¹…±° ¤(€€€€¤(€€€™½ÈÁÉ•Ù¥½ÕÌ¥¸ÕÉÉ•¹Ðè(€€€€€€€ÁÉ•Ù¥½ÕÌ¹ÍÑ…ÑÕÌ€ô€‰MUAIMˆ(€€€€€€€‘ˆ¹…‘¡ÁÉ•Ù¥½ÕÌ¤(€€€Ù•ÉÍ¥½¸¹½¹Ñ•¹Ñ}¡…Í €ô…ÑÕ…±}¡…Í (€€€Ù•ÉÍ¥½¸¹ÍÑ…ÑÕÌ€ô€‰AU	1%M!ˆ(€€€Ù•ÉÍ¥½¸¹ÁÕ‰±¥Í¡•‘}‰å}ÕÍ•É}¥€ô…Ñ½É}¥(€€€Ù•ÉÍ¥½¸¹ÁÕ‰±¥Í¡•‘}…Ð€ô‘…Ñ•Ñ¥µ”¹¹½Ü¡Ñ¥µ•é½¹”¹ÕÑŒ¤(€€€‘ˆ¹…‘¡Ù•ÉÍ¥½¸¤(€€€‘ˆ¹½µµ¥Ð ¤(€€€‘ˆ¹É•™É•Í ¡Ù•ÉÍ¥½¸¤(€€€É•ÑÕÉ¸Ù•ÉÍ¥½¸(()‘•˜•Ù…±Õ…Ñ•}Í…Ù•‘}Ù•ÉÍ¥½¸ (€€€‘ˆèM•ÍÍ¥½¸°Ù•ÉÍ¥½¹}¥èÍÑÈ°½¹Ñ•áÐè‘¥ÑmÍÑÈ°¹åt(¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€Ù•ÉÍ¥½¸€ô•Ñ}Ù•ÉÍ¥½¸¡‘ˆ°Ù•ÉÍ¥½¹}¥¤(€€€É•ÑÕÉ¸•Ù…±Õ…Ñ•}•áÁÉ•ÍÍ¥½¸¡Ù•ÉÍ¥½¸¹•áÁÉ•ÍÍ¥½¹}©Í½¸°½¹Ñ•áÐ¤¹Ñ½}‘¥Ð ¤(()}}…±±}|€ôl(€€€€‰½µÁÕÑ•}½¹Ñ•¹Ñ}¡…Í ˆ°(€€€€‰É•…Ñ•}ÉÕ±•}Í•Ðˆ°(€€€€‰É•…Ñ•}Ù•ÉÍ¥½¸ˆ°(€€€€‰•Ù…±Õ…Ñ•}•áÁÉ•ÍÍ¥½¸ˆ°(€€€€‰•Ù…±Õ…Ñ•}Í…Ù•‘}Ù•ÉÍ¥½¸ˆ°(€€€€‰¥µÁ…Ñ}…¹…±åÍ¥Ìˆ°(€€€€‰ÁÕ‰±¥Í¡}Ù•ÉÍ¥½¸ˆ°(€€€€‰É•ÅÕ¥É•}…Ñ…±½Õ•}ÝÉ¥Ñ•Èˆ°(€€€€‰É•ÅÕ¥É•}‘É…™Ðˆ°)t(