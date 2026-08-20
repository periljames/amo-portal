from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from . import ai_access, ai_gateway


_INSTALLED = False
_ORIGINAL_RUN_AI: Callable[..., dict[str, Any]] | None = None


def install_ai_execution_policy() -> None:
    """Make tenant-data authority a mandatory AI gateway invariant.

    Feature modules are still expected to apply their own domain permissions, but
    no caller may attach a tenant_id to an external AI request unless the actor is
    an active member of that AMO or a true platform identity holding an active
    governed support session for that exact AMO. This is deliberately independent
    of billing scope: platform-funded support can contain tenant data too.
    """
    global _INSTALLED, _ORIGINAL_RUN_AI
    if _INSTALLED:
        return

    _ORIGINAL_RUN_AI = ai_gateway.run_ai

    def guarded_run_ai(
        db: Session,
        *,
        prompt: str,
        instructions: str,
        actor_user_id: str | None,
        tenant_id: str | None = None,
        requested_model: str | None = None,
        billing_scope: ai_gateway.BillingScope = "PLATFORM_TEST",
        feature_code: str = "platform.playground",
        requires_external_documents: bool = False,
    ) -> dict[str, Any]:
        if tenant_id:
            if not actor_user_id:
                raise PermissionError("Tenant-scoped AI requires an authenticated actor")
            ai_access.require_tenant_data_access(
                db,
                tenant_id=str(tenant_id),
                actor_user_id=str(actor_user_id),
            )

        assert _ORIGINAL_RUN_AI is not None
        return _ORIGINAL_RUN_AI(
            db,
            prompt=prompt,
            instructions=instructions,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            requested_model=requested_model,
            billing_scope=billing_scope,
            feature_code=feature_code,
            requires_external_documents=requires_external_documents,
        )

    ai_gateway.run_ai = guarded_run_ai
    _INSTALLED = True
