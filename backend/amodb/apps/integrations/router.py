from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Request, status, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import require_roles
from amodb.apps.accounts.models import AccountRole, User

from . import schemas, services


router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
)


@router.get("/configs", response_model=List[schemas.IntegrationConfigRead])
def list_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AccountRole.SUPERUSER, AccountRole.AMO_ADMIN)),
):
    return services.list_integration_configs(db, amo_id=current_user.amo_id)


@router.post(
    "/configs",
    response_model=schemas.IntegrationConfigRead,
    status_code=status.HTTP_201_CREATED,
)
def create_config(
    payload: schemas.IntegrationConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AccountRole.SUPERUSER, AccountRole.AMO_ADMIN)),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    config = services.create_integration_config(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(config)
    return config


@router.post(
    "/{integration_key}/ingest",
    response_model=schemas.IntegrationInboundEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_event(
    integration_key: str,
    payload: schemas.IntegrationInboundIngest,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    signature: str = Header(..., alias="X-Signature"),
    amo_id: str = Header(..., alias="X-AMO-ID"),
):
    raw_body = await request.body()
    event = services.ingest_inbound_event(
        db,
        amo_id=amo_id,
        integration_key=integration_key,
        event_type=payload.event_type,
        payload_json=payload.payload,
        idempotency_key=idempotency_key,
        signature=signature,
        source_ip=request.client.host if request.client else None,
        raw_body=raw_body,
    )
    db.commit()
    db.refresh(event)
    if not event.signature_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    return event
