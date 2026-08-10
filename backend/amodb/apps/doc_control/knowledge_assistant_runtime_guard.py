from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from .knowledge_assistant_router import DocumentationAssistRequest, SearchContext


def governed_source_url(
    tenant: manual_models.Tenant,
    manual_id: str,
    revision_id: str,
    *,
    page: int | None,
    anchor: str | None,
) -> str:
    """Keep assistant source navigation inside the governed DMS document centre.

    Revision/page/anchor context is preserved in the URL so the document workspace
    can hand the user into the immutable reader without losing source provenance.
    """
    base = f"/maintenance/{tenant.slug.upper()}/document-control/library/{manual_id}"
    params = ["tab=content", f"revision={quote(str(revision_id), safe='')}"]
    if page:
        params.append(f"page={int(page)}")
    if anchor:
        params.append(f"anchor={quote(anchor, safe='')}")
    return f"{base}?{'&'.join(params)}"


def _source_manual_ids(context: SearchContext, request_payload: DocumentationAssistRequest, source_ids: list[str]) -> list[str]:
    if request_payload.manual_id and request_payload.manual_id in context.manuals:
        return [request_payload.manual_id]

    manual_ids: list[str] = []
    for source_id in source_ids:
        parts = str(source_id).split(":")
        manual_id: str | None = None
        if len(parts) >= 3 and parts[0] == "document":
            manual_id = parts[1]
        elif len(parts) >= 3 and parts[0] == "section":
            revision = context.revisions.get(parts[1])
            manual_id = revision.manual_id if revision else None
        if manual_id and manual_id in context.manuals and manual_id not in manual_ids:
            manual_ids.append(manual_id)
    return manual_ids


def _source_revision_id(
    context: SearchContext,
    request_payload: DocumentationAssistRequest,
    source_ids: list[str],
    manual_id: str,
) -> str | None:
    requested_revision_id = request_payload.revision_id
    if requested_revision_id:
        requested_revision = context.revisions.get(requested_revision_id)
        if requested_revision and requested_revision.manual_id == manual_id:
            return requested_revision_id

    for source_id in source_ids:
        parts = str(source_id).split(":")
        if len(parts) >= 3 and parts[0] == "document" and parts[1] == manual_id:
            revision = context.revisions.get(parts[2])
            if revision and revision.manual_id == manual_id:
                return revision.id
        if len(parts) >= 3 and parts[0] == "section":
            revision = context.revisions.get(parts[1])
            if revision and revision.manual_id == manual_id:
                return revision.id
    return None


def audit_assist_safely(
    db: Session,
    *,
    context: SearchContext,
    current_user: account_models.User,
    request_payload: DocumentationAssistRequest,
    provider_mode: str,
    source_ids: list[str],
    warning: str | None,
) -> None:
    """Persist assisted-search audit events using the actual ORM/table contract.

    ``ManualAIHookEvent`` is revision-scoped and intentionally has no ``manual_id``
    or ``actor_contact_id`` columns. Library-wide search therefore emits one event
    per represented document, links it to an authorised revision when available,
    and retains manual/actor context inside the immutable JSON payload. This keeps
    the audit useful without passing invalid SQLAlchemy constructor keywords.
    """
    manual_ids = _source_manual_ids(context, request_payload, source_ids)
    for manual_id in manual_ids:
        relevant_source_ids: list[str] = []
        for source_id in source_ids:
            parts = str(source_id).split(":")
            if len(parts) >= 3 and parts[0] == "document" and parts[1] == manual_id:
                relevant_source_ids.append(source_id)
                continue
            if len(parts) >= 3 and parts[0] == "section":
                revision = context.revisions.get(parts[1])
                if revision and revision.manual_id == manual_id:
                    relevant_source_ids.append(source_id)

        revision_id = _source_revision_id(context, request_payload, relevant_source_ids, manual_id)
        db.add(
            manual_models.ManualAIHookEvent(
                tenant_id=context.tenant.id,
                revision_id=revision_id,
                event_name="documentation.assisted_search",
                payload_json={
                    "actor_id": str(current_user.id),
                    "actor_contact_id": getattr(current_user, "contact_id", None),
                    "manual_id": manual_id,
                    "query_sha256": hashlib.sha256(request_payload.query.strip().lower().encode("utf-8")).hexdigest(),
                    "query_length": len(request_payload.query),
                    "requested_mode": request_payload.mode,
                    "provider_mode": provider_mode,
                    "manual_context_id": request_payload.manual_id,
                    "page_context": request_payload.page_number,
                    "source_ids": relevant_source_ids,
                    "source_count": len(relevant_source_ids),
                    "total_source_count": len(source_ids),
                    "fallback_warning": warning,
                    "scope": "DOCUMENT" if request_payload.manual_id else "LIBRARY_RESULT_DOCUMENT",
                },
            )
        )


def install() -> None:
    # Endpoint functions resolve these module globals at request time. Installing
    # the hardened implementations here avoids a duplicate FastAPI route while
    # keeping the existing public contract stable.
    from . import knowledge_assistant_router as assistant

    assistant._reader_url = governed_source_url
    assistant._audit_assist = audit_assist_safely
