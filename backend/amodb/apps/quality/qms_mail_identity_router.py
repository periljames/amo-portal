"""Tenant-isolated QMS mail identity, built on platform-owned Resend transport.

No API key or webhook secret is accepted or returned by this route. SMTP
delivery, domain approval, and platform rate limits remain Venspera controls.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import service as notification_service
from amodb.apps.notifications.providers import get_email_provider
from amodb.apps.platform import saas_services
from amodb.apps.platform.resend_adapter import email_recipients
from amodb.apps.platform.resend_email_policy import _normalise_domains, _tenant_domain_assignments
from amodb.database import get_read_db, get_write_db
from amodb.security import get_current_active_user
from .tenant_security import (
    TenantContext, require_quality_permission, require_quality_write_permission,
)

router = APIRouter(tags=["Quality / QMS Mail"])


class MailIdentityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_name: str = Field(min_length=2, max_length=150)
    from_email: str = Field(default="", max_length=254)
    reply_to: str = Field(default="", max_length=1000)
    enabled: bool = True
    reason: str = Field(min_length=8, max_length=500)


def _manager_or_admin(user: account_models.User, ctx: TenantContext) -> bool:
    role = str(getattr(user.role, "value", user.role) or "").upper()
    return not ctx.is_superuser and (role == "QUALITY_MANAGER" or ctx.admin_authority)


def _platform_and_tenant(db: Session, amo_id: str):
    platform = saas_services.get_provider_credential(
        db, provider="resend", tenant_id=None, allow_platform_fallback=False,
    )
    tenant = saas_services.get_provider_credential(
        db, provider="resend", tenant_id=amo_id, allow_platform_fallback=False,
    )
    return platform, tenant


def _identity_payload(db: Session, ctx: TenantContext, user: account_models.User) -> dict[str, Any]:
    amo = db.get(account_models.AMO, ctx.amo_id)
    if amo is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    platform, override = _platform_and_tenant(db, ctx.amo_id)
    platform_config = dict(platform.config_json or {}) if platform is not None else {}
    configured = dict(override.config_json or {}) if override is not None else {}
    platform_sender = str(platform_config.get("from_email") or "").strip()
    shared_domain = str(platform_config.get("tenant_default_sender_domain") or "").strip().lower()
    if not shared_domain and "@" in platform_sender:
        shared_domain = platform_sender.rsplit("@", 1)[1].lower()
    slug = re.sub(r"[^a-z0-9]+", ".", str(amo.login_slug or amo.amo_code or "").lower()).strip(".")
    shared_sender = f"quality.{slug}@{shared_domain}" if slug and shared_domain else ""
    allowed_domains = _normalise_domains(platform_config.get("verified_sender_domains"))
    assignments = _tenant_domain_assignments(platform_config.get("tenant_sender_domain_assignments_json"))
    allowed_custom = [domain for domain in assignments.get(str(ctx.amo_id), []) if domain in allowed_domains]
    provider, active = get_email_provider(db=db, amo_id=ctx.amo_id)
    effective_config = getattr(provider, "config", {}) if active else {}
    reply_preview = str(effective_config.get("reply_to") or "")
    if not reply_preview and not configured.get("reply_to"):
        recipients = db.query(account_models.User).filter(
            account_models.User.amo_id == ctx.amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
            account_models.User.role.in_((
                account_models.AccountRole.QUALITY_MANAGER,
                account_models.AccountRole.QUALITY_OFFICER,
            )),
        ).order_by(account_models.User.email.asc()).all()
        reply_preview = ", ".join(dict.fromkeys(
            str(recipient.email).strip() for recipient in recipients if recipient.email
        ))
    platform_mode = str(platform_config.get("sending_mode") or "DISABLED").upper()
    platform_healthy = bool(platform and str(platform.status or "").upper() == "HEALTHY")
    enabled = not (override is not None and str(override.status or "").upper() == "DISABLED")
    sender = str(configured.get("from_email") or "").strip() or shared_sender
    return {
        "tenant_name": str(amo.name or amo.amo_code or "Tenant"),
        "shared_domain": shared_domain,
        "shared_sender": shared_sender,
        "custom_domains": allowed_custom,
        "from_name": str(configured.get("from_name") or amo.name or "AMO Portal"),
        "from_email": sender,
        "reply_to": str(configured.get("reply_to") or ""),
        "effective_reply_to": reply_preview,
        "reply_mode": "CUSTOM" if str(configured.get("reply_to") or "").strip() else "QUALITY_ROLES",
        "sender_mode": "CUSTOM" if sender and sender != shared_sender else "SHARED",
        "enabled": enabled,
        "has_override": override is not None,
        "can_manage": _manager_or_admin(user, ctx),
        "provider_status": str(platform.status or "NOT_CONFIGURED") if platform else "NOT_CONFIGURED",
        "sending_mode": platform_mode,
        "ready": bool(platform_healthy and active and platform_mode != "DISABLED"),
        "status_detail": (
            "Resend is managed by Venspera. Domain verification and actual inbox placement "
            "cannot be established by this page."
        ),
        "reply_note": "Reply All behavior depends on the recipient's email client.",
    }


@router.get("/mail-identity")
def get_qms_mail_identity(
    ctx: TenantContext = Depends(require_quality_permission("qms.settings.view")),
    user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_read_db),
):
    return _identity_payload(db, ctx, user)


@router.put("/mail-identity")
def update_qms_mail_identity(
    payload: MailIdentityUpdate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.settings.manage")),
    user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    if not _manager_or_admin(user, ctx):
        raise HTTPException(status_code=403, detail="Only the tenant Quality Manager or AMO Administrator may change mail identity.")
    platform, _ = _platform_and_tenant(db, ctx.amo_id)
    if platform is None:
        raise HTTPException(status_code=409, detail="Venspera must configure platform Resend transport first.")
    from_name = payload.from_name.strip()
    if "\r" in from_name or "\n" in from_name:
        raise HTTPException(status_code=422, detail="Sender display name contains invalid line breaks.")
    from_email = payload.from_email.strip().lower()
    try:
        addresses = email_recipients(from_email) if from_email else []
        if from_email and (len(addresses) != 1 or addresses[0].lower() != from_email):
            raise ValueError("Sender must contain one mailbox without a display name.")
        replies = email_recipients(payload.reply_to) if payload.reply_to.strip() else []
        if len(replies) > 10:
            raise ValueError("Reply-To may contain at most ten unique mailbox addresses.")
        change = {
            "from_name": from_name,
            **({"from_email": from_email} if from_email else {}),
            **({"reply_to": ", ".join(replies)} if replies else {}),
        }
        clear_fields = [
            field for field, missing in (("from_email", not from_email), ("reply_to", not replies))
            if missing
        ]
        saas_services.upsert_provider_credential(
            db, provider="resend", tenant_id=ctx.amo_id, actor_user_id=str(user.id),
            payload={
                "enabled": payload.enabled,
                "config": change,
                "clear_config_fields": clear_fields,
                "reason": payload.reason.strip(),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _identity_payload(db, ctx, user)


@router.post("/mail-identity/test")
def test_qms_mail_identity(
    ctx: TenantContext = Depends(require_quality_write_permission("qms.settings.manage")),
    user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    if not _manager_or_admin(user, ctx):
        raise HTTPException(status_code=403, detail="Only a tenant Quality Manager or AMO Administrator may test sending.")
    if not str(user.email or "").strip():
        raise HTTPException(status_code=422, detail="Your account needs a verified delivery email address.")
    # Tests may only target the requesting user's own email. The global
    # Resend sending mode, sandbox redirection and rate limits still apply.
    minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    log = notification_service.send_email(
        template_key="qms_mail_identity_test",
        recipient=str(user.email).strip(),
        subject="AMO Portal — QMS mail identity test",
        context={
            "recipient_name": str(user.full_name or "Quality Manager"),
            "purpose": "Confirm the tenant mail sender and Reply-To identity.",
        },
        correlation_id=f"qms-mail-test:{ctx.amo_id}:{user.id}:{minute}",
        email_class="ESSENTIAL",
        recipient_user_id=str(user.id),
        amo_id=ctx.amo_id,
        db=db,
        audit_context={"purpose": "qms-mail-identity-test", "initiator_user_id": str(user.id)},
        cooldown_seconds=60,
    )
    db.commit()
    return {
        "email_log_id": str(log.id),
        "status": str(getattr(log.status, "value", log.status)),
        "delivery_status": str(log.delivery_status or "UNKNOWN"),
        "provider_message_id": log.provider_message_id,
        "detail": "Provider acceptance is not recipient-server delivery, inbox placement or a read receipt.",
    }
