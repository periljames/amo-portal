from __future__ import annotations

"""Provider-status callbacks for durable Training notification delivery."""

import hmac
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import Body, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from . import models as training_models
from . import operating_models
from .notification_dispatch import OUTBOX_WORKFLOW_TYPE

UTC = timezone.utc


class ProviderDeliveryStatus(BaseModel):
    status: Literal["DELIVERED", "READ", "FAILED"]
    provider_message_id: str | None = Field(None, max_length=512)
    error: str | None = Field(None, max_length=4000)
    occurred_at: datetime | None = None


def install_training_notification_dispatch_routes(router_module) -> None:
    public_router = router_module.public_router

    @public_router.post("/training/notification-delivery/{amo_id}/{outbox_id}")
    def record_training_notification_delivery(
        amo_id: str,
        outbox_id: str,
        payload: ProviderDeliveryStatus = Body(...),
        callback_secret: str | None = Header(None, alias="X-Training-Provider-Secret"),
        db: Session = Depends(get_db),
    ):
        expected = str(os.getenv("TRAINING_NOTIFICATION_PROVIDER_CALLBACK_SECRET") or "").strip()
        supplied = str(callback_secret or "").strip()
        if not expected:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Training provider callbacks are not configured.")
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Training provider callback secret.")

        workflow = db.query(operating_models.TrainingWorkflowInstance).filter(
            operating_models.TrainingWorkflowInstance.id == outbox_id,
            operating_models.TrainingWorkflowInstance.amo_id == amo_id,
            operating_models.TrainingWorkflowInstance.workflow_type == OUTBOX_WORKFLOW_TYPE,
        ).first()
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training notification delivery was not found.")

        data = dict(workflow.data_json or {})
        recorded_id = str(data.get("provider_message_id") or "").strip()
        supplied_id = str(payload.provider_message_id or "").strip()
        if recorded_id and supplied_id and not hmac.compare_digest(recorded_id, supplied_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider message identifier does not match this delivery.")

        event_at = payload.occurred_at or datetime.now(UTC)
        if event_at.tzinfo is None:
            event_at = event_at.replace(tzinfo=UTC)
        prior = str(workflow.status or "UNKNOWN").upper()
        next_state = payload.status
        if prior == "READ" and payload.status == "DELIVERED":
            next_state = "READ"
        if supplied_id and not recorded_id:
            data["provider_message_id"] = supplied_id

        if payload.status == "DELIVERED":
            data["delivered_at"] = data.get("delivered_at") or event_at.isoformat()
            data["last_error"] = None
        elif payload.status == "READ":
            data["delivered_at"] = data.get("delivered_at") or event_at.isoformat()
            data["read_at"] = data.get("read_at") or event_at.isoformat()
            data["last_error"] = None
        else:
            data["last_error"] = str(payload.error or "Provider reported delivery failure")[:4000]
            data["provider_failed_at"] = event_at.isoformat()

        workflow.status = next_state
        workflow.data_json = data
        workflow.revision_no = int(workflow.revision_no or 0) + 1
        workflow.updated_at = datetime.now(UTC)
        db.add(training_models.TrainingAuditLog(
            amo_id=workflow.amo_id,
            actor_user_id=None,
            action="NOTIFICATION_OUTBOX_PROVIDER_STATUS",
            entity_type="TrainingWorkflowInstance",
            entity_id=str(workflow.id),
            details={
                "from": prior,
                "to": next_state,
                "provider_message_id": data.get("provider_message_id"),
                "occurred_at": event_at.isoformat(),
                "error": data.get("last_error"),
            },
        ))
        db.commit()
        return {
            "id": str(workflow.id),
            "status": str(workflow.status),
            "provider_message_id": data.get("provider_message_id"),
            "delivered_at": data.get("delivered_at"),
            "read_at": data.get("read_at"),
        }


__all__ = ["ProviderDeliveryStatus", "install_training_notification_dispatch_routes"]
