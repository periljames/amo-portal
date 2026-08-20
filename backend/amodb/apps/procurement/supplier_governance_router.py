from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.quality.tenant_security import set_postgres_tenant_context
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles

from . import schemas as procurement_schemas
from . import service as procurement_service
from . import supplier_governance_schemas as schemas
from . import supplier_governance_service as service


router = APIRouter(
    prefix="/api/maintenance/{amo_code}/procurement",
    tags=["procurement supplier governance"],
    dependencies=[Depends(require_module("finance_inventory"))],
)

QUALITY_GOVERNANCE_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.QUALITY_MANAGER,
)
QUALITY_REVIEW_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
)
EVALUATION_AUTHOR_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
    account_models.AccountRole.PROCUREMENT_OFFICER,
    account_models.AccountRole.STORES_MANAGER,
)


def _tenant(db: Session, *, amo_code: str, current_user: account_models.User) -> str:
    amo_id = procurement_service.resolve_tenant_amo_id(db, amo_code=amo_code, current_user=current_user)
    set_postgres_tenant_context(db, amo_id=amo_id, user_id=str(current_user.id))
    return amo_id


def _commit(db: Session, value):
    db.commit()
    return value


@router.get("/supplier-governance/policy")
def supplier_governance_policy_read(
    amo_code: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.read_policy(db, amo_id=amo_id)
    if row is None:
        return {"configured": False, "amo_id": amo_id}
    return {"configured": True, **schemas.SupplierGovernancePolicyRead.model_validate(row).model_dump(mode="json")}


@router.put("/supplier-governance/policy")
def supplier_governance_policy_update(
    amo_code: str,
    payload: schemas.SupplierGovernancePolicyUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_GOVERNANCE_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.update_policy(db, amo_id=amo_id, payload=payload, actor_user_id=str(current_user.id))
    db.commit()
    db.refresh(row)
    return {"configured": True, **schemas.SupplierGovernancePolicyRead.model_validate(row).model_dump(mode="json")}


@router.get("/supplier-governance/templates", response_model=list[schemas.SupplierEvaluationTemplateRead])
def supplier_evaluation_templates(
    amo_code: str,
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_templates(db, amo_id=amo_id, active_only=active_only)


@router.post(
    "/supplier-governance/templates",
    response_model=schemas.SupplierEvaluationTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def supplier_evaluation_template_create(
    amo_code: str,
    payload: schemas.SupplierEvaluationTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_GOVERNANCE_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    result = service.create_template(db, amo_id=amo_id, payload=payload, actor_user_id=str(current_user.id))
    db.commit()
    return result


@router.post(
    "/supplier-governance/templates/{template_id}/activate",
    response_model=schemas.SupplierEvaluationTemplateRead,
)
def supplier_evaluation_template_activate(
    amo_code: str,
    template_id: str,
    payload: schemas.SupplierEvaluationTemplateActivate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_GOVERNANCE_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    result = service.activate_template(
        db,
        amo_id=amo_id,
        template_id=template_id,
        rationale=payload.rationale,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    return result


@router.post(
    "/suppliers/{supplier_id}/evaluations",
    response_model=schemas.SupplierEvaluationRead,
    status_code=status.HTTP_201_CREATED,
)
def supplier_evaluation_create(
    amo_code: str,
    supplier_id: int,
    payload: schemas.SupplierEvaluationCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*EVALUATION_AUTHOR_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.create_evaluation(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)
    return service.evaluation_payload(db, row)


@router.get("/supplier-governance/evaluations/{evaluation_id}", response_model=schemas.SupplierEvaluationRead)
def supplier_evaluation_read(
    amo_code: str,
    evaluation_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service._evaluation(db, amo_id=amo_id, evaluation_id=evaluation_id)
    return service.evaluation_payload(db, row)


@router.patch("/supplier-governance/evaluations/{evaluation_id}/responses", response_model=schemas.SupplierEvaluationRead)
def supplier_evaluation_responses_update(
    amo_code: str,
    evaluation_id: str,
    payload: schemas.SupplierEvaluationResponsesUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*EVALUATION_AUTHOR_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.update_responses(
        db,
        amo_id=amo_id,
        evaluation_id=evaluation_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)
    return service.evaluation_payload(db, row)


@router.post("/supplier-governance/evaluations/{evaluation_id}/submit", response_model=schemas.SupplierEvaluationRead)
def supplier_evaluation_submit(
    amo_code: str,
    evaluation_id: str,
    payload: schemas.SupplierEvaluationSubmit,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*EVALUATION_AUTHOR_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.submit_evaluation(
        db,
        amo_id=amo_id,
        evaluation_id=evaluation_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)
    return service.evaluation_payload(db, row)


@router.post("/supplier-governance/evaluations/{evaluation_id}/review", response_model=schemas.SupplierEvaluationRead)
def supplier_evaluation_review(
    amo_code: str,
    evaluation_id: str,
    payload: schemas.SupplierEvaluationReview,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_REVIEW_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.review_evaluation(
        db,
        amo_id=amo_id,
        evaluation_id=evaluation_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)
    return service.evaluation_payload(db, row)


@router.get("/suppliers/{supplier_id}/governance", response_model=schemas.SupplierGovernanceDetail)
def supplier_governance_detail(
    amo_code: str,
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.governance_detail(db, amo_id=amo_id, supplier_id=supplier_id)


@router.post("/supplier-governance/re-evaluation/scan", response_model=schemas.SupplierReevaluationScanResult)
def supplier_re_evaluation_scan(
    amo_code: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_REVIEW_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    result = service.scan_re_evaluation(db, amo_id=amo_id, actor_user_id=str(current_user.id))
    return _commit(db, result)


# These two paths intentionally shadow the older Procurement handlers when this
# router is mounted first. Direct API clients therefore cannot bypass the same
# governed evaluation and scope gates enforced by the new workspace.
@router.post(
    "/suppliers/{supplier_id}/approval-scopes",
    response_model=procurement_schemas.ApprovalScopeRead,
    status_code=status.HTTP_201_CREATED,
)
def governed_supplier_scope_create(
    amo_code: str,
    supplier_id: int,
    payload: procurement_schemas.ApprovalScopeCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_REVIEW_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.create_governed_scope(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/suppliers/{supplier_id}/decision", response_model=procurement_schemas.SupplierRead)
def governed_supplier_decision(
    amo_code: str,
    supplier_id: int,
    payload: procurement_schemas.SupplierDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_REVIEW_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    row = service.decide_supplier(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)
    return row
