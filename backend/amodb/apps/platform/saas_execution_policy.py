from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import models as platform_models
from . import saas_models as models
from . import saas_queue, saas_services

OPERATIONAL_PROVIDER_STATUSES = frozenset({"CONFIGURED", "HEALTHY"})
ACTIVE_AI_JOB_STATUSES = frozenset({"PENDING", "RUNNING", "RETRY"})

_INSTALLED = False
_ORIGINAL_FISCALIZATION: Callable[..., models.SaaSJob] | None = None


def require_operational_provider(credential: Any, *, label: str) -> None:
    status = str(getattr(credential, "status", "") or "").strip().upper()
    if credential is None or status not in OPERATIONAL_PROVIDER_STATUSES:
        raise ValueError(f"{label} provider is disabled or not operational")


def _ticket_jobs(db: Session, *, ticket_id: str, tenant_id: str | None) -> list[models.SaaSJob]:
    scope = tenant_id or "__platform__"
    rows = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "AI_SUPPORT_REPLY",
            models.SaaSJob.tenant_scope == scope,
        )
        .order_by(models.SaaSJob.created_at.asc(), models.SaaSJob.id.asc())
        .all()
    )
    return [
        row
        for row in rows
        if str((row.payload_json or {}).get("ticket_id") or "") == ticket_id
    ]


def next_ai_request_sequence(jobs: Iterable[Any], *, ticket_id: str) -> int:
    return 1 + sum(
        1
        for job in jobs
        if str((getattr(job, "payload_json", None) or {}).get("ticket_id") or "") == ticket_id
    )


def install_saas_execution_policy() -> None:
    global _INSTALLED, _ORIGINAL_FISCALIZATION
    if _INSTALLED:
        return

    _ORIGINAL_FISCALIZATION = saas_services.enqueue_fiscalization

    def guarded_enqueue_fiscalization(
        db: Session,
        *,
        invoice_id: str,
        provider: str,
        actor_user_id: str,
    ) -> models.SaaSJob:
        invoice = db.get(account_models.BillingInvoice, invoice_id)
        provider_code = str(provider or "").strip().lower()
        if invoice is not None and provider_code in {"etims_oscu", "etims_vscu"}:
            credential = saas_services.get_provider_credential(
                db,
                provider=provider_code,
                tenant_id=invoice.amo_id,
            )
            require_operational_provider(credential, label="eTIMS")
        assert _ORIGINAL_FISCALIZATION is not None
        return _ORIGINAL_FISCALIZATION(
            db,
            invoice_id=invoice_id,
            provider=provider,
            actor_user_id=actor_user_id,
        )

    def guarded_enqueue_ai_support_reply(
        db: Session,
        *,
        ticket_id: str,
        actor_user_id: str,
    ) -> models.SaaSJob:
        ticket = db.get(platform_models.PlatformSupportTicket, ticket_id)
        if ticket is None:
            raise ValueError("Support ticket not found")

        credential = saas_services.get_provider_credential(
            db,
            provider="openai",
            tenant_id=ticket.tenant_id,
        )
        require_operational_provider(credential, label="OpenAI")

        prior_jobs = _ticket_jobs(db, ticket_id=ticket_id, tenant_id=ticket.tenant_id)
        for job in reversed(prior_jobs):
            if str(job.status or "").strip().upper() in ACTIVE_AI_JOB_STATUSES:
                return job

        sequence = next_ai_request_sequence(prior_jobs, ticket_id=ticket_id)
        ticket_version = int(ticket.updated_at.timestamp() * 1_000_000) if ticket.updated_at else 0
        action_key = f"ticket:{ticket_id}:ai-reply:{ticket_version}:{sequence}"
        return saas_queue.enqueue_job(
            db,
            job_type="AI_SUPPORT_REPLY",
            queue_name="ai",
            tenant_id=ticket.tenant_id,
            payload={
                "ticket_id": ticket_id,
                "credential_id": credential.id,
                "request_version": ticket_version,
                "request_sequence": sequence,
            },
            idempotency_key=action_key,
            correlation_id=str(uuid.uuid4()),
            created_by=actor_user_id,
            max_attempts=3,
            priority=50,
        )

    saas_services.enqueue_fiscalization = guarded_enqueue_fiscalization
    saas_services.enqueue_ai_support_reply = guarded_enqueue_ai_support_reply
    _INSTALLED = True
