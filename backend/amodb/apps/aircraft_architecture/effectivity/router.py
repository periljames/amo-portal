from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services

router = APIRouter(prefix="/effectivity", tags=["aircraft effectivity"])


def _writer(
    current_user: account_models.User = Depends(get_current_active_user),
) -> account_models.User:
    services.require_catalogue_writer(current_user)
    return current_user


@router.get("/rule-sets", response_model=list[schemas.RuleSetRead])
def list_rule_sets(
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return db.query(models.EffectivityRuleSet).order_by(models.EffectivityRuleSet.code).all()


@router.post("/rule-sets", response_model=schemas.RuleSetRead, status_code=201)
def create_rule_set(
    payload: schemas.RuleSetCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_writer),
):
    return services.create_rule_set(db, payload, current_user.id)


@router.get(
    "/rule-sets/{rule_set_id}/versions",
    response_model=list[schemas.RuleVersionRead],
)
def list_versions(
    rule_set_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return (
        db.query(models.EffectivityRuleVersion)
        .filter(models.EffectivityRuleVersion.rule_set_id == rule_set_id)
        .order_by(models.EffectivityRuleVersion.created_at.desc())
        .all()
    )


@router.post(
    "/rule-sets/{rule_set_id}/versions",
    response_model=schemas.RuleVersionRead,
    status_code=201,
)
def create_version(
    rule_set_id: str,
    payload: schemas.RuleVersionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_writer),
):
    return services.create_version(db, rule_set_id, payload, current_user.id)


@router.post(
    "/versions/{version_id}/publish", response_model=schemas.RuleVersionRead
)
def publish_version(
    version_id: str,
    payload: schemas.PublishRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(_writer),
):
    return services.publish_version(
        db,
        version_id,
        current_user.id,
        payload.expected_content_hash,
    )


@router.post("/evaluate", response_model=schemas.EvaluationRead)
def evaluate(
    payload: schemas.EvaluateRequest,
    _: account_models.User = Depends(get_current_active_user),
):
    return services.evaluate_expression(payload.expression, payload.context).to_dict()


@router.post("/versions/{version_id}/evaluate", response_model=schemas.EvaluationRead)
def evaluate_version(
    version_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return services.evaluate_saved_version(db, version_id, payload)


@router.post("/impact")
def analyze_impact(
    payload: schemas.ImpactRequest,
    _: account_models.User = Depends(get_current_active_user),
):
    return services.impact_analysis(
        payload.previous_expression,
        payload.proposed_expression,
        payload.contexts,
    )
