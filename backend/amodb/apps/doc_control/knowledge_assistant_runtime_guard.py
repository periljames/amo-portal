from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.platform import ai_access, ai_gateway

from .knowledge_assistant_router import DocumentationAssistRequest, SearchContext


def _source_manual_ids(
    context: SearchContext,
    request_payload: DocumentationAssistRequest,
    source_ids: list[str],
) -> list[str]:
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
                return parts[2]
        if len(parts) >= 3 and parts[0] == "section":
            revision = context.revisions.get(parts[1])
            if revision and revision.manual_id == manual_id:
                return parts[1]
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

        revision_id = _source_revision_id(
            context,
            request_payload,
            relevant_source_ids,
            manual_id,
        )
        db.add(
            manual_models.ManualAIHookEvent(
                tenant_id=context.tenant.id,
                revision_id=revision_id,
                event_name="documentation.assisted_search",
                payload_json={
                    "actor_id": str(current_user.id),
                    "actor_contact_id": getattr(current_user, "contact_id", None),
                    "manual_id": manual_id,
                    "source_manual_id": manual_id,
                    "query_sha256": hashlib.sha256(
                        request_payload.query.strip().lower().encode("utf-8")
                    ).hexdigest(),
                    "query_length": len(request_payload.query),
                    "requested_mode": request_payload.mode,
                    "provider_mode": provider_mode,
                    "manual_context_id": request_payload.manual_id,
                    "page_context": request_payload.page_number,
                    "source_ids": relevant_source_ids,
                    "source_count": len(relevant_source_ids),
                    "total_source_count": len(source_ids),
                    "fallback_warning": warning,
                    "scope": (
                        "DOCUMENT"
                        if request_payload.manual_id
                        else "LIBRARY_RESULT_DOCUMENT"
                    ),
                },
            )
        )


def _actor_tenant_ai_access(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
) -> tuple[bool, str | None]:
    """Use the shared AI tenant-data authority before provider prompt assembly."""
    try:
        ai_access.require_tenant_data_access(
            db,
            tenant_id=str(tenant_id),
            actor_user_id=str(user_id),
        )
        return True, None
    except PermissionError as exc:
        return False, str(exc)


def _governed_synthesis(
    db: Session,
    tenant_id: str,
    user_id: str,
    query: str,
    sources: list[dict[str, Any]],
) -> tuple[str | None, list[str], str | None]:
    """Run controlled-document synthesis with explicit tenant request context.

    Tenant authorization is checked before provider source snippets are assembled.
    The common AI gateway then applies entitlement, model, budget, credential,
    privacy and metering rules to the request.
    """
    allowed, scope_warning = _actor_tenant_ai_access(
        db,
        tenant_id=str(tenant_id),
        user_id=str(user_id),
    )
    if not allowed:
        return None, [], f"{scope_warning} Deterministic results are shown instead."

    provider_sources = [
        {
            "id": source["id"],
            "document": f"{source['code']} — {source['title']}",
            "heading": source.get("heading"),
            "page": source.get("page_number"),
            "snippet": str(source.get("snippet") or "")[:900],
        }
        for source in sources[:8]
    ]
    allowed_ids = {str(source["id"]) for source in provider_sources}
    instructions = (
        "You are the AMO Portal controlled-document assistant. Use only the supplied authorised source excerpts. "
        "Do not use outside knowledge to fill gaps. Return only one JSON object with keys answer and source_ids. "
        "answer must be concise and source_ids must contain only IDs from the supplied sources that directly support the answer. "
        "If the sources do not support an answer, return an empty answer and an empty source_ids array."
    )
    prompt = json.dumps(
        {"question": query, "sources": provider_sources},
        ensure_ascii=False,
        separators=(",", ":"),
    )

    try:
        result = ai_gateway.run_ai(
            db,
            prompt=prompt,
            instructions=instructions,
            actor_user_id=user_id,
            tenant_id=tenant_id,
            billing_scope="TENANT",
            feature_code="document_control.assisted_search",
            requires_external_documents=True,
        )
        raw = str(result.get("text") or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip() if len(lines) >= 3 else raw
            if raw.lower().startswith("json\n"):
                raw = raw[5:].strip()
        structured = json.loads(raw)
        if not isinstance(structured, dict):
            raise ValueError("AI synthesis did not return a JSON object")
        cited = [
            str(value)
            for value in structured.get("source_ids", [])
            if str(value) in allowed_ids
        ]
        answer = str(structured.get("answer") or "").strip()
        if not answer or not cited:
            return (
                None,
                [],
                "AI synthesis returned no verifiable controlled-source citation; deterministic results are shown instead.",
            )
        return answer[:1600], cited[:8], None
    except PermissionError as exc:
        return (
            None,
            [],
            f"AI synthesis is unavailable under the tenant AI policy: {exc}. Deterministic results are shown instead.",
        )
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return (
            None,
            [],
            f"AI synthesis could not be verified ({type(exc).__name__}); deterministic results are shown instead.",
        )


def install() -> None:
    # Endpoint functions resolve these module globals at request time. Installing
    # only the AI/audit implementations keeps the canonical reader route owned by
    # knowledge_assistant_router and prevents runtime imports from rewriting it.
    from . import knowledge_assistant_router as assistant

    assistant._audit_assist = audit_assist_safely
    assistant._openai_synthesis = _governed_synthesis
