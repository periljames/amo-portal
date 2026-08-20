from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, literal_column, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models
from . import knowledge_models as km
from .knowledge_service import normalize_code
from .workspace_service import can_read_manual, is_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Assisted Search"])

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{1,63}")
_EXECUTABLE_TYPES = {"FORM", "CHECKLIST", "REGISTER"}


class DocumentationAssistRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    mode: Literal["SEARCH", "ASSIST", "NAVIGATE"] = "ASSIST"
    manual_id: str | None = None
    revision_id: str | None = None
    page_number: int | None = Field(default=None, ge=1, le=100_000)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(cleaned) < 2:
            raise ValueError("Enter at least two non-space characters")
        return cleaned


@dataclass(frozen=True)
class SearchContext:
    tenant: manual_models.Tenant
    manuals: dict[str, manual_models.Manual]
    revisions: dict[str, manual_models.ManualRevision]
    profiles: dict[str, domain_models.DocumentControlProfile]
    nodes: dict[str, km.DocumentationNode]


def _status_value(revision: manual_models.ManualRevision) -> str:
    return str(getattr(revision.status_enum, "value", revision.status_enum or "")).upper()


def _source_type(revision: manual_models.ManualRevision) -> str:
    return str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()


def _tokens(query: str) -> list[str]:
    return list(dict.fromkeys(token.lower() for token in _TOKEN.findall(query) if len(token) >= 2))[:12]


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()


def _snippet(text: str, query: str, limit: int = 420) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    lowered = compact.lower()
    positions = [lowered.find(token) for token in _tokens(query)]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(compact), start + limit)
    start = max(0, end - limit)
    return f"{'…' if start else ''}{compact[start:end].strip()}{'…' if end < len(compact) else ''}"


def _reader_url(
    tenant: manual_models.Tenant,
    manual_id: str,
    revision_id: str,
    *,
    page: int | None,
    anchor: str | None,
) -> str:
    base = f"/maintenance/{tenant.slug.upper()}/publications/{manual_id}/rev/{revision_id}/read"
    params: list[str] = []
    if page:
        params.append(f"page={int(page)}")
    if anchor:
        params.append(f"anchor={quote(anchor, safe='')}")
    return f"{base}?{'&'.join(params)}" if params else base


def _search_context(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
    requested_manual_id: str | None,
    requested_revision_id: str | None,
) -> SearchContext:
    all_manuals = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            manual_models.Manual.status == "ACTIVE",
        )
        .all()
    )
    manual_ids = [manual.id for manual in all_manuals]
    profiles = {
        row.manual_id: row
        for row in db.query(domain_models.DocumentControlProfile)
        .filter(
            domain_models.DocumentControlProfile.tenant_id == tenant.amo_id,
            domain_models.DocumentControlProfile.manual_id.in_(manual_ids or ["-"]),
        )
        .all()
    }
    manuals = {
        manual.id: manual
        for manual in all_manuals
        if can_read_manual(user, profiles.get(manual.id))
    }
    if requested_manual_id and requested_manual_id not in manuals:
        raise HTTPException(status_code=404, detail="The requested document context is unavailable")

    allowed_revision_ids = {
        manual.current_published_rev_id
        for manual in manuals.values()
        if manual.current_published_rev_id
    }
    if requested_revision_id:
        if not requested_manual_id:
            raise HTTPException(status_code=422, detail="A revision context requires its document ID")
        requested = (
            db.query(manual_models.ManualRevision)
            .filter(
                manual_models.ManualRevision.id == requested_revision_id,
                manual_models.ManualRevision.manual_id == requested_manual_id,
            )
            .first()
        )
        if not requested:
            raise HTTPException(status_code=404, detail="The requested revision context is unavailable")
        current_effective = (
            manuals[requested_manual_id].current_published_rev_id == requested.id
            and _status_value(requested) == "PUBLISHED"
        )
        if not current_effective and not is_control_user(user):
            raise HTTPException(status_code=404, detail="The requested revision context is unavailable")
        allowed_revision_ids.add(requested.id)

    revisions = {
        row.id: row
        for row in db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.id.in_(allowed_revision_ids or ["-"]))
        .all()
        if row.manual_id in manuals
        and (
            (
                _status_value(row) == "PUBLISHED"
                and manuals[row.manual_id].current_published_rev_id == row.id
            )
            or (is_control_user(user) and row.id == requested_revision_id)
        )
    }
    nodes = {
        row.manual_id: row
        for row in db.query(km.DocumentationNode)
        .filter(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id.in_(list(manuals) or ["-"]),
            km.DocumentationNode.status == "ACTIVE",
        )
        .all()
    }
    return SearchContext(
        tenant=tenant,
        manuals=manuals,
        revisions=revisions,
        profiles=profiles,
        nodes=nodes,
    )


def _metadata_results(context: SearchContext, query: str) -> list[dict[str, Any]]:
    needle = query.lower()
    normalized = normalize_code(query)
    tokens = _tokens(query)
    revisions_by_manual: dict[str, list[manual_models.ManualRevision]] = {}
    for revision in context.revisions.values():
        revisions_by_manual.setdefault(revision.manual_id, []).append(revision)
    results: list[dict[str, Any]] = []
    for manual in context.manuals.values():
        node = context.nodes.get(manual.id)
        aliases = (
            [manual.code, *list((node.metadata_json or {}).get("aliases", []))]
            if node
            else [manual.code]
        )
        identity = " ".join(
            [
                manual.code,
                manual.title,
                manual.manual_type,
                node.node_type if node else "MANUAL",
                *(str(value) for value in aliases),
            ]
        ).lower()
        exact_code = bool(
            normalized
            and normalized in {normalize_code(value) for value in aliases}
        )
        token_hits = sum(1 for token in tokens if token in identity)
        if not exact_code and needle not in identity and not token_hits:
            continue
        for revision in revisions_by_manual.get(manual.id, []):
            score = 100.0 if exact_code else 72.0 if needle in identity else 40.0 + token_hits * 5
            results.append(
                {
                    "id": f"document:{manual.id}:{revision.id}",
                    "kind": "DOCUMENT",
                    "manual_id": manual.id,
                    "revision_id": revision.id,
                    "code": manual.code,
                    "title": manual.title,
                    "node_type": node.node_type if node else "MANUAL",
                    "hierarchy_path": node.path if node else None,
                    "heading": None,
                    "section_id": None,
                    "anchor": None,
                    "page_number": None,
                    "snippet": (
                        f"{manual.manual_type.replace('_', ' ').title()} · "
                        f"Revision {revision.rev_number} · {_status_value(revision).title()}"
                    ),
                    "score": score,
                    "reader_url": _reader_url(
                        context.tenant,
                        manual.id,
                        revision.id,
                        page=None,
                        anchor=None,
                    ),
                    "source_type": _source_type(revision),
                    "executable": bool(node and node.node_type in _EXECUTABLE_TYPES),
                    "reason": "Exact document code" if exact_code else "Document title, type, or alias match",
                }
            )
    return results


def _content_results(
    db: Session,
    context: SearchContext,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    revision_ids = list(context.revisions)
    if not revision_ids:
        return []
    tokens = _tokens(query)
    base = (
        db.query(
            manual_models.Manual,
            manual_models.ManualRevision,
            manual_models.ManualSection,
            manual_models.ManualBlock,
        )
        .join(
            manual_models.ManualRevision,
            manual_models.ManualRevision.manual_id == manual_models.Manual.id,
        )
        .join(
            manual_models.ManualSection,
            manual_models.ManualSection.revision_id == manual_models.ManualRevision.id,
        )
        .outerjoin(
            manual_models.ManualBlock,
            manual_models.ManualBlock.section_id == manual_models.ManualSection.id,
        )
        .filter(manual_models.ManualRevision.id.in_(revision_ids))
    )
    dialect = str(db.get_bind().dialect.name)
    rows: list[tuple[Any, ...]] = []
    if dialect == "postgresql":
        language = literal_column("'simple'")
        heading_vector = func.to_tsvector(
            language,
            func.coalesce(manual_models.ManualSection.heading, ""),
        )
        block_vector = func.to_tsvector(
            language,
            func.coalesce(manual_models.ManualBlock.text_plain, ""),
        )
        search_query = func.websearch_to_tsquery(language, query)
        rank = (
            func.ts_rank_cd(heading_vector, search_query) * 1.5
            + func.ts_rank_cd(block_vector, search_query)
        )
        rows = (
            base.add_columns(rank.label("search_rank"))
            .filter(
                or_(
                    heading_vector.op("@@")(search_query),
                    block_vector.op("@@")(search_query),
                )
            )
            .order_by(rank.desc(), manual_models.ManualSection.order_index.asc())
            .limit(max(40, limit * 8))
            .all()
        )
    if not rows:
        conditions = [
            manual_models.ManualSection.heading.ilike(f"%{query}%"),
            manual_models.ManualBlock.text_plain.ilike(f"%{query}%"),
        ]
        for token in tokens[:6]:
            conditions.extend(
                [
                    manual_models.ManualSection.heading.ilike(f"%{token}%"),
                    manual_models.ManualBlock.text_plain.ilike(f"%{token}%"),
                ]
            )
        rows = [
            (*row, 0.0)
            for row in base.filter(or_(*conditions)).limit(max(40, limit * 8)).all()
        ]

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    query_lower = query.lower()
    for manual, revision, section, block, raw_rank in rows:
        identity = (revision.id, section.id)
        if identity in seen:
            continue
        seen.add(identity)
        text = str(getattr(block, "text_plain", "") or "")
        combined = f"{section.heading} {text}".lower()
        exact = query_lower in combined
        token_hits = sum(1 for token in tokens if token in combined)
        node = context.nodes.get(manual.id)
        metadata = dict(section.metadata_json or {})
        page = int(metadata.get("page_start") or 0) or None
        output.append(
            {
                "id": f"section:{revision.id}:{section.id}",
                "kind": "SECTION",
                "manual_id": manual.id,
                "revision_id": revision.id,
                "code": manual.code,
                "title": manual.title,
                "node_type": node.node_type if node else "MANUAL",
                "hierarchy_path": node.path if node else None,
                "heading": section.heading,
                "section_id": section.id,
                "anchor": section.anchor_slug,
                "page_number": page,
                "snippet": _snippet(text or section.heading, query),
                "score": float(raw_rank or 0.0) * 100 + (45 if exact else 0) + token_hits * 4,
                "reader_url": _reader_url(
                    context.tenant,
                    manual.id,
                    revision.id,
                    page=page,
                    anchor=section.anchor_slug,
                ),
                "source_type": _source_type(revision),
                "executable": bool(node and node.node_type in _EXECUTABLE_TYPES),
                "reason": "Exact phrase in controlled content" if exact else "Controlled-content keyword match",
            }
        )
    return output


def _apply_context_boost(
    items: list[dict[str, Any]],
    payload: DocumentationAssistRequest,
) -> None:
    for item in items:
        if payload.manual_id and item["manual_id"] == payload.manual_id:
            item["score"] = float(item.get("score") or 0) + 14
        if payload.revision_id and item["revision_id"] == payload.revision_id:
            item["score"] = float(item.get("score") or 0) + 8
        if payload.page_number and item.get("page_number"):
            distance = abs(int(item["page_number"]) - payload.page_number)
            item["score"] = float(item.get("score") or 0) + max(0, 8 - min(8, distance))


def _deduplicate(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(
        items,
        key=lambda item: (
            -float(item.get("score") or 0),
            str(item.get("code") or ""),
            str(item.get("heading") or ""),
        ),
    )
    seen: set[tuple[str, str | None, int | None]] = set()
    result: list[dict[str, Any]] = []
    for item in ordered:
        key = (
            str(item["revision_id"]),
            item.get("section_id"),
            item.get("page_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        item["rank"] = len(result) + 1
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _deterministic_answer(
    query: str,
    sources: list[dict[str, Any]],
    mode: str,
) -> str:
    if not sources:
        return "No authorised effective document matched this request. Try a document code, exact phrase, form number, checklist title, or procedure name."
    first = sources[0]
    if mode == "NAVIGATE":
        location = f", page {first['page_number']}" if first.get("page_number") else ""
        return (
            f"The strongest authorised match is {first['code']} — {first['title']}{location}. "
            "Open the cited source to verify the controlled text."
        )
    return (
        f"Found {len(sources)} authorised controlled source"
        f"{'s' if len(sources) != 1 else ''} for “{query}”. Results are ranked by "
        "document code, title, heading, indexed text, and the current reading context."
    )


def _openai_synthesis(
    db: Session,
    tenant_id: str,
    user_id: str,
    query: str,
    sources: list[dict[str, Any]],
) -> tuple[str | None, list[str], str | None]:
    # Safe default. Document Control's runtime guard replaces this helper with
    # the tenant-aware AI gateway. The authenticated request context is explicit
    # in the function contract, so direct imports cannot bypass tenant entitlement
    # and usage metering through hidden process/thread-local state.
    del db, tenant_id, user_id, query, sources
    return (
        None,
        [],
        "External AI synthesis requires the governed tenant AI runtime; deterministic assisted search remains available.",
    )


def _audit_assist(
    db: Session,
    *,
    context: SearchContext,
    current_user: account_models.User,
    request_payload: DocumentationAssistRequest,
    provider_mode: str,
    source_ids: list[str],
    warning: str | None,
) -> None:
    db.add(
        manual_models.ManualAIHookEvent(
            tenant_id=context.tenant.id,
            revision_id=request_payload.revision_id,
            event_name="documentation.assisted_search",
            payload_json={
                "actor_id": str(current_user.id),
                "query_sha256": _query_hash(request_payload.query),
                "query_length": len(request_payload.query),
                "requested_mode": request_payload.mode,
                "provider_mode": provider_mode,
                "manual_context_id": request_payload.manual_id,
                "page_context": request_payload.page_number,
                "source_ids": source_ids,
                "source_count": len(source_ids),
                "fallback_warning": warning,
            },
        )
    )


@router.post("/t/{tenant_slug}/knowledge/assist")
def assist_documentation_search(
    tenant_slug: str,
    payload: DocumentationAssistRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    context = _search_context(
        db,
        tenant=tenant,
        user=current_user,
        requested_manual_id=payload.manual_id,
        requested_revision_id=payload.revision_id,
    )
    candidates = _metadata_results(context, payload.query)
    candidates.extend(_content_results(db, context, payload.query, payload.limit))
    _apply_context_boost(candidates, payload)
    sources = _deduplicate(candidates, payload.limit)

    answer = _deterministic_answer(payload.query, sources, payload.mode)
    provider_mode = "DETERMINISTIC"
    cited_ids = [source["id"] for source in sources[: min(3, len(sources))]]
    warning: str | None = None
    if payload.mode == "ASSIST" and sources:
        provider_answer, provider_citations, warning = _openai_synthesis(
            db,
            str(tenant.amo_id),
            str(current_user.id),
            payload.query,
            sources,
        )
        if provider_answer and provider_citations:
            answer = provider_answer
            cited_ids = provider_citations
            provider_mode = "OPENAI"

    primary = next(
        (source for source in sources if source["id"] in cited_ids),
        sources[0] if sources else None,
    )
    _audit_assist(
        db,
        context=context,
        current_user=current_user,
        request_payload=payload,
        provider_mode=provider_mode,
        source_ids=[source["id"] for source in sources],
        warning=warning,
    )
    db.commit()
    return {
        "query": payload.query,
        "mode": payload.mode,
        "provider_mode": provider_mode,
        "answer": answer,
        "citations": cited_ids,
        "sources": sources,
        "navigation": {
            "primary_source_id": primary["id"] if primary else None,
            "reader_url": primary["reader_url"] if primary else None,
            "manual_id": primary["manual_id"] if primary else None,
            "revision_id": primary["revision_id"] if primary else None,
            "page_number": primary.get("page_number") if primary else None,
            "anchor": primary.get("anchor") if primary else None,
        },
        "capabilities": {
            "assisted_search": True,
            "external_ai_enabled": provider_mode == "OPENAI",
            "answers_are_advisory": True,
            "controlled_source_is_authoritative": True,
        },
        "warning": warning,
    }
