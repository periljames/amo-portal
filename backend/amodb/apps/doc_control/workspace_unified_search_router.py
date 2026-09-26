from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import library_models as lm
from . import records_vault_models as rm
from . import warehouse_models as wm
from .workspace_library_catalog_router import _serialize_item, _visible_query
from .workspace_records_vault_router import _record_access_predicate, _record_payload
from .workspace_warehouse_router import _target_path, _visible_record_ids
from .workspace_service import can_read_manual, get_profile, is_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Unified Search"])

_MAX_PER_SOURCE = 25


def _controlled_documents(
    db: Session,
    *,
    tenant,
    user: account_models.User,
    query_text: str,
    limit: int,
) -> list[dict[str, Any]]:
    manuals = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            manual_models.Manual.status == "ACTIVE",
        )
        .all()
    )
    visible_ids = [
        row.id
        for row in manuals
        if can_read_manual(user, get_profile(db, tenant, row.id))
    ]
    if not visible_ids:
        return []

    revision_ids = [
        row[0]
        for row in db.query(manual_models.Manual.current_published_rev_id)
        .filter(
            manual_models.Manual.id.in_(visible_ids),
            manual_models.Manual.current_published_rev_id.isnot(None),
        )
        .all()
        if row[0]
    ]
    if is_control_user(user):
        latest = (
            db.query(manual_models.ManualRevision.manual_id, func.max(manual_models.ManualRevision.created_at).label("latest_created_at"))
            .filter(manual_models.ManualRevision.manual_id.in_(visible_ids))
            .group_by(manual_models.ManualRevision.manual_id)
            .subquery()
        )
        revision_ids.extend(
            row[0]
            for row in db.query(manual_models.ManualRevision.id)
            .join(
                latest,
                (latest.c.manual_id == manual_models.ManualRevision.manual_id)
                & (latest.c.latest_created_at == manual_models.ManualRevision.created_at),
            )
            .all()
        )
    revision_ids = list(dict.fromkeys(revision_ids))
    needle = query_text.strip()
    if not needle:
        return []

    rows: list[Any]
    if db.get_bind().dialect.name == "postgresql":
        language = "simple"
        tsquery = func.websearch_to_tsquery(language, needle)
        heading_vector = func.to_tsvector(language, func.coalesce(manual_models.ManualSection.heading, ""))
        body_vector = func.to_tsvector(language, func.coalesce(manual_models.ManualBlock.text_plain, ""))
        rank = func.ts_rank_cd(heading_vector, tsquery) * 1.5 + func.ts_rank_cd(body_vector, tsquery)
        rows = (
            db.query(
                manual_models.Manual,
                manual_models.ManualRevision,
                manual_models.ManualSection,
                manual_models.ManualBlock,
                rank.label("rank"),
            )
            .join(manual_models.ManualRevision, manual_models.ManualRevision.manual_id == manual_models.Manual.id)
            .join(manual_models.ManualSection, manual_models.ManualSection.revision_id == manual_models.ManualRevision.id)
            .outerjoin(manual_models.ManualBlock, manual_models.ManualBlock.section_id == manual_models.ManualSection.id)
            .filter(
                manual_models.ManualRevision.id.in_(revision_ids or ["-"]),
                or_(heading_vector.op("@@")(tsquery), body_vector.op("@@")(tsquery)),
            )
            .order_by(rank.desc())
            .limit(limit * 3)
            .all()
        )
    else:
        like = f"%{needle}%"
        rows = [
            (*row, 0.0)
            for row in (
                db.query(
                    manual_models.Manual,
                    manual_models.ManualRevision,
                    manual_models.ManualSection,
                    manual_models.ManualBlock,
                )
                .join(manual_models.ManualRevision, manual_models.ManualRevision.manual_id == manual_models.Manual.id)
                .join(manual_models.ManualSection, manual_models.ManualSection.revision_id == manual_models.ManualRevision.id)
                .outerjoin(manual_models.ManualBlock, manual_models.ManualBlock.section_id == manual_models.ManualSection.id)
                .filter(
                    manual_models.ManualRevision.id.in_(revision_ids or ["-"]),
                    or_(
                        manual_models.Manual.code.ilike(like),
                        manual_models.Manual.title.ilike(like),
                        manual_models.ManualSection.heading.ilike(like),
                        manual_models.ManualBlock.text_plain.ilike(like),
                    ),
                )
                .limit(limit * 3)
                .all()
            )
        ]

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for manual, revision, section, block, rank in rows:
        key = (revision.id, section.id)
        if key in seen:
            continue
        seen.add(key)
        metadata = dict(section.metadata_json or {})
        page = int(metadata.get("page_start") or 0) or None
        text = " ".join(str(getattr(block, "text_plain", "") or "").split())
        if len(text) > 420:
            text = text[:417].rstrip() + "..."
        output.append({
            "kind": "CONTROLLED_DOCUMENT",
            "id": manual.id,
            "revision_id": revision.id,
            "code": manual.code,
            "title": manual.title,
            "heading": section.heading,
            "page_number": page,
            "snippet": text,
            "score": float(rank or 0),
            "status": str(getattr(getattr(revision, "status_enum", None), "value", getattr(revision, "status_enum", ""))),
            "target_path": (
                f"/maintenance/{tenant.slug.upper()}/document-control/library/{manual.id}"
                f"?tab=content&revision={revision.id}"
                + (f"&page={page}" if page else "")
            ),
        })
        if len(output) >= limit:
            break
    return output


def _catalog(
    db: Session,
    *,
    tenant,
    user: account_models.User,
    query_text: str,
    limit: int,
) -> list[dict[str, Any]]:
    query = _visible_query(
        db.query(lm.LibraryCatalogItem).filter(
            lm.LibraryCatalogItem.tenant_id == tenant.amo_id,
            lm.LibraryCatalogItem.status == "ACTIVE",
        ),
        user,
    )
    if db.get_bind().dialect.name == "postgresql":
        tsquery = func.websearch_to_tsquery("simple", query_text)
        vector = func.to_tsvector("simple", lm.LibraryCatalogItem.search_text)
        rows = query.filter(vector.op("@@")(tsquery)).order_by(func.ts_rank_cd(vector, tsquery).desc()).limit(limit).all()
    else:
        like = f"%{query_text}%"
        rows = query.filter(or_(
            lm.LibraryCatalogItem.title.ilike(like),
            lm.LibraryCatalogItem.subtitle.ilike(like),
            lm.LibraryCatalogItem.search_text.ilike(like),
        )).limit(limit).all()
    return [{
        "kind": "LIBRARY_ITEM",
        **_serialize_item(row),
        "target_path": f"/maintenance/{tenant.slug.upper()}/document-control/library?library_item={row.id}",
    } for row in rows]


def _records(
    db: Session,
    *,
    tenant,
    user: account_models.User,
    query_text: str,
    limit: int,
) -> list[dict[str, Any]]:
    query = (
        db.query(rm.TenantRecordAsset, rm.TenantRecordSeries)
        .join(rm.TenantRecordSeries, rm.TenantRecordSeries.id == rm.TenantRecordAsset.series_id)
        .filter(
            rm.TenantRecordAsset.tenant_id == tenant.amo_id,
            rm.TenantRecordSeries.tenant_id == tenant.amo_id,
            _record_access_predicate(user),
        )
    )
    if db.get_bind().dialect.name == "postgresql":
        tsquery = func.websearch_to_tsquery("simple", query_text)
        vector = func.to_tsvector("simple", rm.TenantRecordAsset.search_text)
        rows = query.filter(vector.op("@@")(tsquery)).order_by(func.ts_rank_cd(vector, tsquery).desc()).limit(limit).all()
    else:
        like = f"%{query_text}%"
        rows = query.filter(or_(
            rm.TenantRecordAsset.record_number.ilike(like),
            rm.TenantRecordAsset.title.ilike(like),
            rm.TenantRecordAsset.filename.ilike(like),
            rm.TenantRecordAsset.search_text.ilike(like),
        )).limit(limit).all()
    return [{
        "kind": "RETAINED_RECORD",
        **_record_payload(row, series, user),
        "target_path": f"/maintenance/{tenant.slug.upper()}/document-control/records?record={row.id}",
    } for row, series in rows]



def _governed_resources(
    db: Session,
    *,
    tenant,
    user: account_models.User,
    query_text: str,
    limit: int,
) -> list[dict[str, Any]]:
    visible_ids = _visible_record_ids(db, tenant=tenant, user=user)
    query = db.query(wm.WarehouseContentRecord).filter(
        wm.WarehouseContentRecord.tenant_id == tenant.amo_id,
    )
    if visible_ids is not None:
        query = query.filter(wm.WarehouseContentRecord.id.in_(visible_ids or ["-"]))

    normalized = query_text.strip().upper()
    identifier_match = db.query(wm.WarehouseIdentifier.id).filter(
        wm.WarehouseIdentifier.tenant_id == tenant.amo_id,
        wm.WarehouseIdentifier.content_record_id == wm.WarehouseContentRecord.id,
        or_(
            func.upper(wm.WarehouseIdentifier.normalized_value) == normalized,
            wm.WarehouseIdentifier.display_value.ilike(f"%{query_text}%"),
        ),
    ).exists()
    if db.get_bind().dialect.name == "postgresql":
        tsquery = func.websearch_to_tsquery("simple", query_text)
        vector = func.to_tsvector(
            "simple",
            func.concat_ws(
                " ",
                wm.WarehouseContentRecord.canonical_code,
                wm.WarehouseContentRecord.title,
                func.coalesce(wm.WarehouseContentRecord.description, ""),
            ),
        )
        query = query.filter(or_(
            func.upper(wm.WarehouseContentRecord.canonical_code) == normalized,
            identifier_match,
            vector.op("@@")(tsquery),
        ))
    else:
        needle = f"%{query_text}%"
        query = query.filter(or_(
            wm.WarehouseContentRecord.canonical_code.ilike(needle),
            wm.WarehouseContentRecord.title.ilike(needle),
            wm.WarehouseContentRecord.description.ilike(needle),
            identifier_match,
        ))

    rows = query.order_by(
        wm.WarehouseContentRecord.title.asc(),
        wm.WarehouseContentRecord.canonical_code.asc(),
    ).limit(limit).all()
    ids = [row.id for row in rows]
    copy_summary: dict[str, dict[str, int]] = {}
    if ids:
        copy_rows = db.query(wm.WarehouseItemCopy).filter(
            wm.WarehouseItemCopy.content_record_id.in_(ids),
        ).all()
        for copy in copy_rows:
            summary = copy_summary.setdefault(str(copy.content_record_id), {"total": 0, "revision_required": 0})
            summary["total"] += 1
            if copy.revision_compliance == "REVISION_REQUIRED":
                summary["revision_required"] += 1

    return [{
        "kind": "GOVERNED_RESOURCE",
        "id": row.id,
        "code": row.canonical_code,
        "title": row.title,
        "resource_type": row.resource_type,
        "classification": row.classification,
        "status": row.lifecycle_status,
        "source_entity_type": row.source_entity_type,
        "target_path": _target_path(tenant, row),
        "copies": copy_summary.get(str(row.id), {"total": 0, "revision_required": 0}),
    } for row in rows]

@router.get("/t/{tenant_slug}/search")
def unified_search(
    tenant_slug: str,
    q: str = Query(min_length=2, max_length=255),
    scope: Literal["everything", "repository", "library", "records", "external"] = "everything",
    limit: int = Query(default=12, ge=1, le=_MAX_PER_SOURCE),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Search the tenant warehouse without leaking restricted content.

    Internet links are generated from the user's explicit search terms only. No
    tenant document text, record text or metadata is sent to an external service.
    """
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query_text = " ".join(q.split())
    governed = _governed_resources(db, tenant=tenant, user=current_user, query_text=query_text, limit=limit) if scope == "everything" else []
    controlled = _controlled_documents(db, tenant=tenant, user=current_user, query_text=query_text, limit=limit) if scope in {"everything", "repository"} else []
    catalog = _catalog(db, tenant=tenant, user=current_user, query_text=query_text, limit=limit) if scope in {"everything", "library"} else []
    records = _records(db, tenant=tenant, user=current_user, query_text=query_text, limit=limit) if scope in {"everything", "records"} else []
    encoded = quote_plus(query_text)
    return {
        "query": query_text,
        "scope": scope,
        "groups": {
            "governed_resources": governed,
            "controlled_documents": controlled,
            "library_items": catalog,
            "retained_records": records,
        },
        "counts": {
            "governed_resources": len(governed),
            "controlled_documents": len(controlled),
            "library_items": len(catalog),
            "retained_records": len(records),
        },
        "internet": {
            "enabled": scope in {"everything", "external"},
            "privacy": "External links contain only the search terms you entered. Tenant content is never appended.",
            "links": {
                "google": f"https://www.google.com/search?q={encoded}",
                "google_books": f"https://books.google.com/books?q={encoded}",
                "open_library": f"https://openlibrary.org/search?q={encoded}",
                "kcaa": f"https://www.google.com/search?q=site%3Akcaa.or.ke+{encoded}",
                "easa": f"https://www.google.com/search?q=site%3Aeasa.europa.eu+{encoded}",
                "faa": f"https://www.google.com/search?q=site%3Afaa.gov+{encoded}",
            },
        },
        "capabilities": {"control": is_control_user(current_user)},
    }
