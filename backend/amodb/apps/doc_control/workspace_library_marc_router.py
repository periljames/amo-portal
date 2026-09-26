from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import library_models as lm
from . import warehouse_service as warehouse
from .library_marc import build_marcxml, parse_marcxml
from .workspace_library_catalog_router import (
    CatalogItemCreate,
    _clean_list,
    _identifier_pairs,
    _search_text,
    _visible_query,
)
from .workspace_service import audit, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Library MARC"])


class MarcXmlImportRequest(BaseModel):
    marcxml: str = Field(min_length=20, max_length=5_000_000)
    dry_run: bool = False
    restricted: bool = False
    access_scope: dict[str, Any] = Field(default_factory=dict)
    circulation_policy: dict[str, Any] = Field(default_factory=dict)


def _duplicate_identifier(
    db: Session,
    *,
    tenant_id: str,
    normalized_identifiers: list[tuple[str, str, str]],
) -> lm.LibraryCatalogIdentifier | None:
    if not normalized_identifiers:
        return None
    return db.query(lm.LibraryCatalogIdentifier).filter(
        lm.LibraryCatalogIdentifier.tenant_id == tenant_id,
        or_(*[
            and_(
                lm.LibraryCatalogIdentifier.scheme == scheme,
                lm.LibraryCatalogIdentifier.normalized_value == normalized,
            )
            for scheme, normalized, _display in normalized_identifiers
        ]),
    ).first()


@router.post("/t/{tenant_slug}/catalog/marcxml/import")
def import_marcxml(
    tenant_slug: str,
    payload: MarcXmlImportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    try:
        parsed = parse_marcxml(payload.marcxml)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    preview: list[dict[str, Any]] = []
    pending: list[tuple[CatalogItemCreate, list[tuple[str, str, str]]]] = []
    seen_codes: set[str] = set()
    for raw in parsed:
        raw["restricted"] = payload.restricted
        raw["access_scope"] = dict(payload.access_scope)
        raw["circulation_policy"] = dict(payload.circulation_policy)
        item_payload = CatalogItemCreate(**raw)
        identifiers = _identifier_pairs(item_payload.identifiers)
        duplicate = _duplicate_identifier(db, tenant_id=str(tenant.amo_id), normalized_identifiers=identifiers)
        code = item_payload.catalogue_code.strip()
        code_conflict = code.upper() in seen_codes or db.query(lm.LibraryCatalogItem.id).filter(
            lm.LibraryCatalogItem.tenant_id == tenant.amo_id,
            lm.LibraryCatalogItem.catalogue_code == code,
            lm.LibraryCatalogItem.status != "DELETED",
        ).first() is not None
        seen_codes.add(code.upper())
        if duplicate:
            preview.append({
                "catalogue_code": code,
                "title": item_payload.title,
                "action": "SKIP_DUPLICATE_IDENTIFIER",
                "existing_catalog_item_id": duplicate.catalog_item_id,
                "identifier": duplicate.display_value,
            })
            continue
        if code_conflict:
            preview.append({
                "catalogue_code": code,
                "title": item_payload.title,
                "action": "SKIP_DUPLICATE_CODE",
            })
            continue
        pending.append((item_payload, identifiers))
        preview.append({"catalogue_code": code, "title": item_payload.title, "action": "IMPORT"})

    if payload.dry_run:
        return {
            "dry_run": True,
            "records_received": len(parsed),
            "importable": len(pending),
            "skipped": len(parsed) - len(pending),
            "items": preview,
        }

    imported: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for item_payload, identifiers in pending:
        try:
            with db.begin_nested():
                row = lm.LibraryCatalogItem(
                    tenant_id=tenant.amo_id,
                    catalogue_code=item_payload.catalogue_code.strip(),
                    material_type=item_payload.material_type,
                    title=item_payload.title.strip(),
                    subtitle=(item_payload.subtitle or "").strip() or None,
                    authors_json=_clean_list(item_payload.authors, limit=50),
                    publisher=(item_payload.publisher or "").strip() or None,
                    publication_year=item_payload.publication_year,
                    edition=(item_payload.edition or "").strip() or None,
                    language=(item_payload.language or "").strip() or None,
                    identifiers_json={
                        str(key).lower(): str(value).strip()
                        for key, value in item_payload.identifiers.items()
                        if str(value).strip()
                    },
                    subjects_json=_clean_list(item_payload.subjects, limit=100),
                    description=(item_payload.description or "").strip() or None,
                    search_text=_search_text(item_payload),
                    source_provider="MARC21",
                    source_record_id=(item_payload.source_record_id or "").strip() or None,
                    source_url=item_payload.source_url,
                    cover_url=item_payload.cover_url,
                    restricted_flag=item_payload.restricted,
                    access_scope_json=dict(item_payload.access_scope),
                    circulation_policy_json=dict(item_payload.circulation_policy),
                    metadata_json={**dict(item_payload.metadata), "interchange": "MARC21_MARCXML"},
                    created_by_user_id=current_user.id,
                )
                db.add(row)
                db.flush()
                for scheme, normalized, display in identifiers:
                    db.add(lm.LibraryCatalogIdentifier(
                        tenant_id=tenant.amo_id,
                        catalog_item_id=row.id,
                        scheme=scheme,
                        normalized_value=normalized,
                        display_value=display,
                        source="MARC21",
                    ))
                db.flush()
                warehouse.sync_library_catalog_item(
                    db,
                    tenant_id=str(tenant.amo_id),
                    item=row,
                    actor_user_id=str(current_user.id),
                )
                imported.append({"id": row.id, "catalogue_code": row.catalogue_code, "title": row.title})
        except IntegrityError:
            errors.append({
                "catalogue_code": item_payload.catalogue_code,
                "title": item_payload.title,
                "error": "Identifier or catalogue-code conflict detected while importing.",
            })

    audit(
        db,
        tenant,
        request,
        "document.library.marc_imported",
        "library_catalog",
        str(tenant.amo_id),
        {
            "records_received": len(parsed),
            "imported": len(imported),
            "skipped": len(parsed) - len(pending),
            "errors": len(errors),
        },
    )
    db.commit()
    return {
        "dry_run": False,
        "records_received": len(parsed),
        "imported": len(imported),
        "skipped": len(parsed) - len(pending),
        "errors": errors,
        "items": imported,
    }


@router.get("/t/{tenant_slug}/catalog/marcxml/export")
def export_marcxml(
    tenant_slug: str,
    item_ids: list[str] = Query(default=[]),
    limit: int = Query(default=250, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = _visible_query(
        db.query(lm.LibraryCatalogItem).filter(
            lm.LibraryCatalogItem.tenant_id == tenant.amo_id,
            lm.LibraryCatalogItem.status == "ACTIVE",
        ),
        current_user,
    )
    if item_ids:
        query = query.filter(lm.LibraryCatalogItem.id.in_(item_ids[:500]))
    items = query.order_by(lm.LibraryCatalogItem.catalogue_code.asc()).limit(limit).all()
    identifiers = db.query(lm.LibraryCatalogIdentifier).filter(
        lm.LibraryCatalogIdentifier.tenant_id == tenant.amo_id,
        lm.LibraryCatalogIdentifier.catalog_item_id.in_([item.id for item in items] or ["-"]),
    ).all()
    grouped: dict[str, list[lm.LibraryCatalogIdentifier]] = {}
    for identifier in identifiers:
        grouped.setdefault(str(identifier.catalog_item_id), []).append(identifier)
    xml = build_marcxml(items, grouped)
    return Response(
        content=xml,
        media_type="application/marcxml+xml",
        headers={"Content-Disposition": 'attachment; filename="library-marc21.xml"'},
    )
