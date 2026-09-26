from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import createBarcodeDrawing, qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import library_models as lm
from .workspace_library_router import _scope_match
from .workspace_service import (
    active_tenant_users,
    audit,
    is_control_user,
    require_control_user,
    resolve_tenant,
    role_value,
    utcnow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Library Catalogue"])

MATERIAL_TYPES = {
    "BOOK",
    "JOURNAL",
    "MAGAZINE",
    "REFERENCE",
    "MEDIA",
    "MAP",
    "ARCHIVE_OBJECT",
    "OTHER",
}
HOLDING_STATUSES = {"AVAILABLE", "CHECKED_OUT", "ON_HOLD", "LOST", "DAMAGED", "WITHDRAWN", "IN_REPAIR"}
_ACTIVE_HOLD_STATUSES = {"ACTIVE", "READY"}
_EXTERNAL_TIMEOUT_SECONDS = 4.0
_EXTERNAL_LIMIT = 12
_EXTERNAL_CACHE_TTL_SECONDS = 15 * 60
_EXTERNAL_CACHE_MAX = 256
_EXTERNAL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class CatalogItemCreate(BaseModel):
    catalogue_code: str = Field(min_length=1, max_length=128)
    material_type: str = Field(default="BOOK", max_length=40)
    title: str = Field(min_length=1, max_length=500)
    subtitle: str | None = Field(default=None, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=50)
    publisher: str | None = Field(default=None, max_length=255)
    publication_year: int | None = Field(default=None, ge=1000, le=3000)
    edition: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)
    identifiers: dict[str, str] = Field(default_factory=dict)
    subjects: list[str] = Field(default_factory=list, max_length=100)
    description: str | None = Field(default=None, max_length=20_000)
    source_provider: str = Field(default="MANUAL", max_length=64)
    source_record_id: str | None = Field(default=None, max_length=255)
    source_url: str | None = None
    cover_url: str | None = None
    restricted: bool = False
    access_scope: dict[str, Any] = Field(default_factory=dict)
    circulation_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_type(self):
        self.material_type = self.material_type.strip().upper().replace(" ", "_")
        if self.material_type not in MATERIAL_TYPES:
            raise ValueError("Unsupported library material type")
        return self


class HoldingCreate(BaseModel):
    barcode: str = Field(min_length=2, max_length=128)
    accession_number: str | None = Field(default=None, max_length=128)
    call_number: str | None = Field(default=None, max_length=128)
    format: str = Field(default="PHYSICAL", max_length=32)
    home_location: str = Field(min_length=2, max_length=255)
    acquired_on: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CirculationRequest(BaseModel):
    action: Literal["CHECK_OUT", "CHECK_IN", "RENEW", "VERIFY_LOCATION"]
    patron_user_id: str | None = None
    due_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    acknowledgement: bool = False
    override_hold: bool = False
    comments: str | None = Field(default=None, max_length=2000)


class HoldCreate(BaseModel):
    pickup_location: str | None = Field(default=None, max_length=255)
    expires_at: datetime | None = None


class HoldingControlRequest(BaseModel):
    action: Literal["MARK_LOST", "MARK_DAMAGED", "SEND_REPAIR", "RETURN_TO_SHELF", "WITHDRAW"]
    location: str | None = Field(default=None, max_length=255)
    reason: str = Field(min_length=2, max_length=2000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=25)


def _normalize_identifier(scheme: str, value: str) -> tuple[str, str] | None:
    normalized_scheme = str(scheme or "").strip().lower().replace("-", "_")
    display = str(value or "").strip()
    if not normalized_scheme or not display:
        return None
    if normalized_scheme in {"isbn", "isbn_10", "isbn_13", "issn", "ean", "upc"}:
        normalized = re.sub(r"[^0-9Xx]", "", display).upper()
    elif normalized_scheme == "doi":
        normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", display, flags=re.IGNORECASE).strip().lower()
    else:
        normalized = re.sub(r"\s+", "", display).lower()
    if not normalized:
        return None
    return normalized_scheme[:32], normalized[:255]


def _identifier_pairs(identifiers: dict[str, str]) -> list[tuple[str, str, str]]:
    output: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for scheme, display in identifiers.items():
        normalized = _normalize_identifier(scheme, display)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append((normalized[0], normalized[1], str(display).strip()[:255]))
    return output


def _existing_identifier_map(
    db: Session,
    *,
    tenant_id: str,
    items: list[dict[str, Any]],
) -> dict[tuple[str, str], str]:
    pairs = {
        (scheme, normalized)
        for item in items
        for scheme, normalized, _display in _identifier_pairs(dict(item.get("identifiers") or {}))
    }
    if not pairs:
        return {}
    clauses = [
        and_(
            lm.LibraryCatalogIdentifier.scheme == scheme,
            lm.LibraryCatalogIdentifier.normalized_value == normalized,
        )
        for scheme, normalized in pairs
    ]
    rows = db.query(lm.LibraryCatalogIdentifier).filter(
        lm.LibraryCatalogIdentifier.tenant_id == tenant_id,
        or_(*clauses),
    ).all()
    return {(row.scheme, row.normalized_value): row.catalog_item_id for row in rows}


def _clean_list(values: list[str], *, limit: int, item_limit: int = 255) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in result:
            result.append(cleaned[:item_limit])
        if len(result) >= limit:
            break
    return result


def _search_text(payload: CatalogItemCreate) -> str:
    identifiers = " ".join(str(value) for value in payload.identifiers.values())
    return " ".join(
        part
        for part in [
            payload.catalogue_code,
            payload.title,
            payload.subtitle or "",
            " ".join(payload.authors),
            payload.publisher or "",
            payload.edition or "",
            identifiers,
            " ".join(payload.subjects),
            payload.description or "",
        ]
        if part
    )[:100_000]


def _policy(row: lm.LibraryCatalogItem) -> dict[str, Any]:
    raw = dict(row.circulation_policy_json or {})
    return {
        "circulatable": bool(raw.get("circulatable", True)),
        "self_checkout": bool(raw.get("self_checkout", False)),
        "loan_period_days": max(1, min(365, int(raw.get("loan_period_days", 14) or 14))),
        "max_renewals": max(0, min(20, int(raw.get("max_renewals", 2) or 0))),
        "reference_only": bool(raw.get("reference_only", False)),
    }


def _visible_query(query, user: account_models.User):
    if is_control_user(user):
        return query
    item = lm.LibraryCatalogItem
    conditions = [
        item.restricted_flag.is_(False),
        _scope_match(item.access_scope_json, "user_ids", str(user.id)),
    ]
    current_role = role_value(user)
    if current_role:
        conditions.append(_scope_match(item.access_scope_json, "roles", current_role, case_insensitive=True))
    department = getattr(getattr(user, "department", None), "code", None)
    if department:
        conditions.append(_scope_match(item.access_scope_json, "departments", str(department), case_insensitive=True))
    return query.filter(or_(*conditions))


def _item(db: Session, tenant_id: str, item_id: str, user: account_models.User) -> lm.LibraryCatalogItem:
    query = db.query(lm.LibraryCatalogItem).filter(
        lm.LibraryCatalogItem.tenant_id == tenant_id,
        lm.LibraryCatalogItem.id == item_id,
        lm.LibraryCatalogItem.status != "DELETED",
    )
    row = _visible_query(query, user).first()
    if not row:
        raise HTTPException(status_code=404, detail="Library item not found")
    return row


def _holding(db: Session, tenant_id: str, holding_id: str) -> lm.LibraryHolding:
    row = db.query(lm.LibraryHolding).filter(
        lm.LibraryHolding.tenant_id == tenant_id,
        lm.LibraryHolding.id == holding_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Library holding not found")
    return row


def _holding_by_scan(db: Session, tenant_id: str, code: str) -> lm.LibraryHolding | None:
    clean = code.strip()
    return db.query(lm.LibraryHolding).filter(
        lm.LibraryHolding.tenant_id == tenant_id,
        or_(
            lm.LibraryHolding.barcode == clean,
            lm.LibraryHolding.qr_token == clean,
            lm.LibraryHolding.id == clean,
        ),
    ).first()


def _holding_summary(rows: list[lm.LibraryHolding]) -> dict[str, int]:
    return {
        "total": len(rows),
        "available": sum(1 for row in rows if row.status == "AVAILABLE"),
        "checked_out": sum(1 for row in rows if row.status == "CHECKED_OUT"),
        "on_hold": sum(1 for row in rows if row.status == "ON_HOLD"),
        "overdue": sum(1 for row in rows if row.status == "CHECKED_OUT" and row.due_at and row.due_at < utcnow()),
    }


def _serialize_item(row: lm.LibraryCatalogItem, holdings: list[lm.LibraryHolding] | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "catalogue_code": row.catalogue_code,
        "material_type": row.material_type,
        "title": row.title,
        "subtitle": row.subtitle,
        "authors": list(row.authors_json or []),
        "publisher": row.publisher,
        "publication_year": row.publication_year,
        "edition": row.edition,
        "language": row.language,
        "identifiers": dict(row.identifiers_json or {}),
        "subjects": list(row.subjects_json or []),
        "description": row.description,
        "source_provider": row.source_provider,
        "source_record_id": row.source_record_id,
        "source_url": row.source_url,
        "cover_url": row.cover_url,
        "restricted": bool(row.restricted_flag),
        "circulation_policy": _policy(row),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if holdings is not None:
        payload["holdings"] = _holding_summary(holdings)
    return payload


def _serialize_holding(row: lm.LibraryHolding, *, controller: bool, own: bool = False) -> dict[str, Any]:
    expose_holder = controller or own
    return {
        "id": row.id,
        "catalog_item_id": row.catalog_item_id,
        "barcode": row.barcode,
        "qr_token": row.qr_token if controller else None,
        "accession_number": row.accession_number,
        "call_number": row.call_number,
        "format": row.format,
        "home_location": row.home_location,
        "current_location": row.current_location,
        "status": row.status,
        "holder_user_id": row.holder_user_id if expose_holder else None,
        "checked_out_at": row.checked_out_at.isoformat() if expose_holder and row.checked_out_at else None,
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "renewal_count": row.renewal_count if expose_holder else None,
        "last_inventory_at": row.last_inventory_at.isoformat() if row.last_inventory_at else None,
        "overdue": bool(row.status == "CHECKED_OUT" and row.due_at and row.due_at < utcnow()),
        "version": row.version,
    }


def _external_json(url: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _EXTERNAL_CACHE.get(url)
    if cached and now - cached[0] <= _EXTERNAL_CACHE_TTL_SECONDS:
        return dict(cached[1])

    contact = str(os.getenv("LIBRARY_EXTERNAL_CONTACT") or "").strip()
    user_agent = "AMO-Portal-DMS/1.0"
    if contact:
        user_agent += f" ({contact})"
    else:
        user_agent += " (+https://github.com/periljames/amo-portal)"
    request = UrlRequest(
        url,
        headers={"Accept": "application/json", "User-Agent": user_agent},
        method="GET",
    )
    try:
        with urlopen(request, timeout=_EXTERNAL_TIMEOUT_SECONDS) as response:
            if int(getattr(response, "status", 200)) != 200:
                raise HTTPException(status_code=502, detail="External catalogue provider returned an error")
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
            if len(_EXTERNAL_CACHE) >= _EXTERNAL_CACHE_MAX:
                oldest = min(_EXTERNAL_CACHE, key=lambda key: _EXTERNAL_CACHE[key][0])
                _EXTERNAL_CACHE.pop(oldest, None)
            _EXTERNAL_CACHE[url] = (now, payload)
            return dict(payload)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="External catalogue provider is temporarily unavailable") from exc


def _google_books(query: str, limit: int) -> list[dict[str, Any]]:
    url = "https://www.googleapis.com/books/v1/volumes?" + urlencode({
        "q": query,
        "maxResults": min(limit, 40),
        "projection": "lite",
        "printType": "all",
    })
    payload = _external_json(url)
    output = []
    for raw in payload.get("items") or []:
        info = raw.get("volumeInfo") or {}
        identifiers = {
            str(item.get("type") or "").lower(): str(item.get("identifier") or "")
            for item in info.get("industryIdentifiers") or []
            if item.get("identifier")
        }
        output.append({
            "provider": "GOOGLE_BOOKS",
            "provider_id": raw.get("id"),
            "material_type": "JOURNAL" if info.get("printType") == "MAGAZINE" else "BOOK",
            "title": info.get("title") or "Untitled",
            "subtitle": info.get("subtitle"),
            "authors": info.get("authors") or [],
            "publisher": info.get("publisher"),
            "published_date": info.get("publishedDate"),
            "language": info.get("language"),
            "identifiers": identifiers,
            "subjects": info.get("categories") or [],
            "description": info.get("description"),
            "cover_url": str((info.get("imageLinks") or {}).get("thumbnail") or "").replace("http://", "https://") or None,
            "source_url": info.get("canonicalVolumeLink") or info.get("infoLink"),
        })
    return output[:limit]


def _open_library(query: str, limit: int) -> list[dict[str, Any]]:
    url = "https://openlibrary.org/search.json?" + urlencode({
        "q": query,
        "limit": min(limit, 50),
        "fields": "key,title,subtitle,author_name,first_publish_year,publisher,isbn,language,subject,cover_i",
    })
    payload = _external_json(url)
    output = []
    for raw in payload.get("docs") or []:
        isbns = [str(value) for value in raw.get("isbn") or [] if value]
        identifiers: dict[str, str] = {}
        for value in isbns:
            if len(value.replace("-", "")) == 13 and "isbn_13" not in identifiers:
                identifiers["isbn_13"] = value
            elif len(value.replace("-", "")) == 10 and "isbn_10" not in identifiers:
                identifiers["isbn_10"] = value
        key = str(raw.get("key") or "")
        cover_id = raw.get("cover_i")
        output.append({
            "provider": "OPEN_LIBRARY",
            "provider_id": key,
            "material_type": "BOOK",
            "title": raw.get("title") or "Untitled",
            "subtitle": raw.get("subtitle"),
            "authors": raw.get("author_name") or [],
            "publisher": (raw.get("publisher") or [None])[0],
            "published_date": str(raw.get("first_publish_year") or "") or None,
            "language": (raw.get("language") or [None])[0],
            "identifiers": identifiers,
            "subjects": (raw.get("subject") or [])[:20],
            "description": None,
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
            "source_url": f"https://openlibrary.org{key}" if key.startswith("/") else None,
        })
    return output[:limit]


@router.get("/t/{tenant_slug}/catalog/external-search")
def external_catalog_search(
    tenant_slug: str,
    q: str = Query(min_length=2, max_length=255),
    provider: Literal["all", "google", "openlibrary"] = "all",
    limit: int = Query(default=8, ge=1, le=_EXTERNAL_LIMIT),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    # External discovery is intentionally explicit. Queries are sent to the named
    # public provider only after the user invokes this endpoint.
    tenant = resolve_tenant(db, tenant_slug, current_user)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    providers = ["google", "openlibrary"] if provider == "all" else [provider]
    for selected in providers:
        try:
            rows = _google_books(q, limit) if selected == "google" else _open_library(q, limit)
            results.extend(rows)
        except HTTPException as exc:
            errors.append({"provider": selected.upper(), "message": str(exc.detail)})
    selected_results = results[: limit * len(providers)]
    existing = _existing_identifier_map(db, tenant_id=tenant.amo_id, items=selected_results)
    for item in selected_results:
        matches = [
            existing.get((scheme, normalized))
            for scheme, normalized, _display in _identifier_pairs(dict(item.get("identifiers") or {}))
            if existing.get((scheme, normalized))
        ]
        item["existing_catalog_item_id"] = matches[0] if matches else None
    return {
        "query": q,
        "items": selected_results,
        "provider_errors": errors,
        "links": {
            "google_search": f"https://www.google.com/search?q={quote_plus(q)}",
            "google_books": f"https://books.google.com/books?q={quote_plus(q)}",
            "open_library": f"https://openlibrary.org/search?q={quote_plus(q)}",
        },
        "privacy_notice": "Internet search terms are sent to the selected external catalogue provider.",
    }


@router.get("/t/{tenant_slug}/catalog/items")
def list_catalog_items(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    material_type: str | None = Query(default=None, max_length=40),
    availability: Literal["any", "available", "checked_out"] = "any",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
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
    if material_type:
        query = query.filter(lm.LibraryCatalogItem.material_type == material_type.strip().upper())
    if q and q.strip():
        search = q.strip()
        if db.get_bind().dialect.name == "postgresql":
            tsquery = func.websearch_to_tsquery("simple", search)
            vector = func.to_tsvector("simple", lm.LibraryCatalogItem.search_text)
            query = query.filter(vector.op("@@")(tsquery)).order_by(func.ts_rank_cd(vector, tsquery).desc())
        else:
            needle = f"%{search}%"
            identifier_match = db.query(lm.LibraryCatalogIdentifier.id).filter(
                lm.LibraryCatalogIdentifier.tenant_id == tenant.amo_id,
                lm.LibraryCatalogIdentifier.catalog_item_id == lm.LibraryCatalogItem.id,
                or_(
                    lm.LibraryCatalogIdentifier.normalized_value.ilike(needle),
                    lm.LibraryCatalogIdentifier.display_value.ilike(needle),
                ),
            ).exists()
            query = query.filter(or_(
                lm.LibraryCatalogItem.title.ilike(needle),
                lm.LibraryCatalogItem.subtitle.ilike(needle),
                lm.LibraryCatalogItem.search_text.ilike(needle),
                cast(lm.LibraryCatalogItem.identifiers_json, String).ilike(needle),
                identifier_match,
            ))
    if availability != "any":
        wanted = ["AVAILABLE"] if availability == "available" else ["CHECKED_OUT"]
        query = query.filter(
            db.query(lm.LibraryHolding.id).filter(
                lm.LibraryHolding.catalog_item_id == lm.LibraryCatalogItem.id,
                lm.LibraryHolding.status.in_(wanted),
            ).exists()
        )
    total = int(query.order_by(None).count())
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    ids = [row.id for row in rows]
    holdings = db.query(lm.LibraryHolding).filter(
        lm.LibraryHolding.tenant_id == tenant.amo_id,
        lm.LibraryHolding.catalog_item_id.in_(ids or ["-"]),
        lm.LibraryHolding.status != "WITHDRAWN",
    ).all()
    grouped: dict[str, list[lm.LibraryHolding]] = {item_id: [] for item_id in ids}
    for holding in holdings:
        grouped.setdefault(holding.catalog_item_id, []).append(holding)
    return {
        "items": [_serialize_item(row, grouped.get(row.id, [])) for row in rows],
        "facets": {
            "material_types": dict(
                _visible_query(
                    db.query(lm.LibraryCatalogItem.material_type, func.count(lm.LibraryCatalogItem.id)).filter(
                        lm.LibraryCatalogItem.tenant_id == tenant.amo_id,
                        lm.LibraryCatalogItem.status == "ACTIVE",
                    ),
                    current_user,
                ).group_by(lm.LibraryCatalogItem.material_type).all()
            )
        },
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(rows)},
        "capabilities": {"read": True, "control": is_control_user(current_user)},
    }


@router.post("/t/{tenant_slug}/catalog/items", status_code=201)
def create_catalog_item(
    tenant_slug: str,
    payload: CatalogItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    normalized_identifiers = _identifier_pairs(payload.identifiers)
    if normalized_identifiers:
        duplicate = db.query(lm.LibraryCatalogIdentifier).filter(
            lm.LibraryCatalogIdentifier.tenant_id == tenant.amo_id,
            or_(*[
                and_(
                    lm.LibraryCatalogIdentifier.scheme == scheme,
                    lm.LibraryCatalogIdentifier.normalized_value == normalized,
                )
                for scheme, normalized, _display in normalized_identifiers
            ]),
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A catalogue item with this identifier already exists.",
                    "existing_catalog_item_id": duplicate.catalog_item_id,
                    "scheme": duplicate.scheme,
                    "identifier": duplicate.display_value,
                },
            )

    row = lm.LibraryCatalogItem(
        tenant_id=tenant.amo_id,
        catalogue_code=payload.catalogue_code.strip(),
        material_type=payload.material_type,
        title=payload.title.strip(),
        subtitle=(payload.subtitle or "").strip() or None,
        authors_json=_clean_list(payload.authors, limit=50),
        publisher=(payload.publisher or "").strip() or None,
        publication_year=payload.publication_year,
        edition=(payload.edition or "").strip() or None,
        language=(payload.language or "").strip() or None,
        identifiers_json={str(k).lower(): str(v).strip() for k, v in payload.identifiers.items() if str(v).strip()},
        subjects_json=_clean_list(payload.subjects, limit=100),
        description=(payload.description or "").strip() or None,
        search_text=_search_text(payload),
        source_provider=payload.source_provider.strip().upper(),
        source_record_id=(payload.source_record_id or "").strip() or None,
        source_url=payload.source_url,
        cover_url=payload.cover_url,
        restricted_flag=payload.restricted,
        access_scope_json=dict(payload.access_scope),
        circulation_policy_json=dict(payload.circulation_policy),
        metadata_json=dict(payload.metadata),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    try:
        db.flush()
        for scheme, normalized, display in normalized_identifiers:
            db.add(lm.LibraryCatalogIdentifier(
                tenant_id=tenant.amo_id,
                catalog_item_id=row.id,
                scheme=scheme,
                normalized_value=normalized,
                display_value=display,
                source=row.source_provider,
            ))
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Catalogue code already exists in this tenant") from exc
    audit(db, tenant, request, "document.library.catalogued", "library_catalog_item", row.id, {
        "catalogue_code": row.catalogue_code,
        "material_type": row.material_type,
        "source_provider": row.source_provider,
    })
    db.commit()
    return _serialize_item(row, [])


@router.get("/t/{tenant_slug}/catalog/items/{item_id}")
def get_catalog_item(
    tenant_slug: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _item(db, tenant.amo_id, item_id, current_user)
    holdings = db.query(lm.LibraryHolding).filter(
        lm.LibraryHolding.tenant_id == tenant.amo_id,
        lm.LibraryHolding.catalog_item_id == row.id,
        lm.LibraryHolding.status != "WITHDRAWN",
    ).order_by(lm.LibraryHolding.call_number.asc(), lm.LibraryHolding.barcode.asc()).all()
    controller = is_control_user(current_user)
    return {
        **_serialize_item(row, holdings),
        "physical_items": [
            _serialize_holding(holding, controller=controller, own=str(holding.holder_user_id or "") == str(current_user.id))
            for holding in holdings
        ],
    }


@router.post("/t/{tenant_slug}/catalog/items/{item_id}/holdings", status_code=201)
def create_holding(
    tenant_slug: str,
    item_id: str,
    payload: HoldingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    item = _item(db, tenant.amo_id, item_id, current_user)
    location = payload.home_location.strip()
    row = lm.LibraryHolding(
        tenant_id=tenant.amo_id,
        catalog_item_id=item.id,
        barcode=payload.barcode.strip(),
        accession_number=(payload.accession_number or "").strip() or None,
        call_number=(payload.call_number or "").strip() or None,
        format=payload.format.strip().upper(),
        home_location=location,
        current_location=location,
        acquired_on=payload.acquired_on,
        metadata_json=dict(payload.metadata),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Barcode already exists in this tenant library") from exc
    db.add(lm.LibraryCirculationEvent(
        tenant_id=tenant.amo_id,
        holding_id=row.id,
        event_type="REGISTER",
        actor_user_id=current_user.id,
        from_status=None,
        to_status="AVAILABLE",
        to_location=location,
    ))
    audit(db, tenant, request, "document.library.holding_registered", "library_holding", row.id, {
        "catalog_item_id": item.id,
        "barcode": row.barcode,
        "home_location": location,
    })
    db.commit()
    return _serialize_holding(row, controller=True)


@router.get("/t/{tenant_slug}/catalog/holdings")
def list_holdings(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=32),
    overdue: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(lm.LibraryHolding, lm.LibraryCatalogItem).join(
        lm.LibraryCatalogItem,
        lm.LibraryCatalogItem.id == lm.LibraryHolding.catalog_item_id,
    ).filter(
        lm.LibraryHolding.tenant_id == tenant.amo_id,
        lm.LibraryCatalogItem.tenant_id == tenant.amo_id,
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(
            lm.LibraryHolding.barcode.ilike(needle),
            lm.LibraryHolding.accession_number.ilike(needle),
            lm.LibraryHolding.call_number.ilike(needle),
            lm.LibraryHolding.home_location.ilike(needle),
            lm.LibraryHolding.current_location.ilike(needle),
            lm.LibraryCatalogItem.catalogue_code.ilike(needle),
            lm.LibraryCatalogItem.title.ilike(needle),
        ))
    if status:
        query = query.filter(lm.LibraryHolding.status == status.strip().upper())
    if overdue:
        query = query.filter(
            lm.LibraryHolding.status == "CHECKED_OUT",
            lm.LibraryHolding.due_at.isnot(None),
            lm.LibraryHolding.due_at < utcnow(),
        )
    total = int(query.count())
    rows = query.order_by(
        lm.LibraryCatalogItem.title.asc(),
        lm.LibraryHolding.call_number.asc(),
        lm.LibraryHolding.barcode.asc(),
    ).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [{
            "item": _serialize_item(item),
            "holding": _serialize_holding(holding, controller=True),
        } for holding, item in rows],
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(rows)},
        "summary": {
            "available": sum(1 for holding, _item_row in rows if holding.status == "AVAILABLE"),
            "checked_out": sum(1 for holding, _item_row in rows if holding.status == "CHECKED_OUT"),
            "on_hold": sum(1 for holding, _item_row in rows if holding.status == "ON_HOLD"),
            "overdue": sum(1 for holding, _item_row in rows if holding.status == "CHECKED_OUT" and holding.due_at and holding.due_at < utcnow()),
            "exceptions": sum(1 for holding, _item_row in rows if holding.status in {"LOST", "DAMAGED", "IN_REPAIR"}),
        },
    }


@router.post("/t/{tenant_slug}/catalog/holdings/{holding_id}/control")
def control_holding(
    tenant_slug: str,
    holding_id: str,
    payload: HoldingControlRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    holding = _holding(db, tenant.amo_id, holding_id)
    item = _item(db, tenant.amo_id, holding.catalog_item_id, current_user)
    before_status = holding.status
    before_location = holding.current_location

    if payload.action in {"MARK_DAMAGED", "SEND_REPAIR", "WITHDRAW"} and holding.holder_user_id:
        raise HTTPException(
            status_code=409,
            detail="Check the item in or record it lost before changing its physical-control state.",
        )
    if payload.action == "MARK_LOST":
        holding.status = "LOST"
    elif payload.action == "MARK_DAMAGED":
        holding.status = "DAMAGED"
    elif payload.action == "SEND_REPAIR":
        holding.status = "IN_REPAIR"
    elif payload.action == "RETURN_TO_SHELF":
        holding.status = "AVAILABLE"
        holding.holder_user_id = None
        holding.checked_out_at = None
        holding.due_at = None
        holding.renewal_count = 0
        holding.current_location = str(payload.location or holding.home_location).strip()
    else:
        holding.status = "WITHDRAWN"
        holding.holder_user_id = None
        holding.checked_out_at = None
        holding.due_at = None

    if payload.location:
        holding.current_location = payload.location.strip()
    holding.version = int(holding.version or 0) + 1
    db.add(lm.LibraryCirculationEvent(
        tenant_id=tenant.amo_id,
        holding_id=holding.id,
        event_type=payload.action,
        actor_user_id=current_user.id,
        patron_user_id=holding.holder_user_id,
        from_status=before_status,
        to_status=holding.status,
        from_location=before_location,
        to_location=holding.current_location,
        due_at=holding.due_at,
        notes=payload.reason.strip(),
        metadata_json={"evidence": list(payload.evidence)},
    ))
    audit(db, tenant, request, f"document.library.{payload.action.lower()}", "library_holding", holding.id, {
        "catalog_item_id": item.id,
        "barcode": holding.barcode,
        "from_status": before_status,
        "to_status": holding.status,
        "from_location": before_location,
        "to_location": holding.current_location,
        "reason": payload.reason.strip(),
    })
    db.commit()
    return {"item": _serialize_item(item), "holding": _serialize_holding(holding, controller=True)}


@router.get("/t/{tenant_slug}/catalog/scan/{code}")
def scan_holding(
    tenant_slug: str,
    code: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    holding = _holding_by_scan(db, tenant.amo_id, code)
    if not holding:
        raise HTTPException(status_code=404, detail="No library item matches this barcode or QR code")
    item = _item(db, tenant.amo_id, holding.catalog_item_id, current_user)
    controller = is_control_user(current_user)
    own = str(holding.holder_user_id or "") == str(current_user.id)
    events = db.query(lm.LibraryCirculationEvent).filter(
        lm.LibraryCirculationEvent.holding_id == holding.id,
    ).order_by(lm.LibraryCirculationEvent.created_at.desc()).limit(80 if controller else 20).all()
    return {
        "item": _serialize_item(item),
        "holding": _serialize_holding(holding, controller=controller, own=own),
        "events": [{
            "id": event.id,
            "event_type": event.event_type,
            "patron_user_id": event.patron_user_id if controller or str(event.patron_user_id or "") == str(current_user.id) else None,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "from_location": event.from_location,
            "to_location": event.to_location,
            "due_at": event.due_at.isoformat() if event.due_at else None,
            "notes": event.notes if controller or str(event.patron_user_id or "") == str(current_user.id) else None,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        } for event in events if controller or own],
        "capabilities": {
            "control": controller,
            "self_checkout": _policy(item)["self_checkout"],
            "check_in": controller or own,
            "renew": controller or own,
            "place_hold": bool(_policy(item)["circulatable"] and not _policy(item)["reference_only"]),
        },
    }


@router.post("/t/{tenant_slug}/catalog/holdings/{holding_id}/circulation")
def circulate_holding(
    tenant_slug: str,
    holding_id: str,
    payload: CirculationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    holding = _holding(db, tenant.amo_id, holding_id)
    item = _item(db, tenant.amo_id, holding.catalog_item_id, current_user)
    controller = is_control_user(current_user)
    own = str(holding.holder_user_id or "") == str(current_user.id)
    policy = _policy(item)
    before_status = holding.status
    before_location = holding.current_location
    patron_id = holding.holder_user_id

    if payload.action == "CHECK_OUT":
        if holding.status not in {"AVAILABLE", "ON_HOLD"} or holding.holder_user_id:
            raise HTTPException(status_code=409, detail="This library item is not currently available")
        if not policy["circulatable"] or policy["reference_only"]:
            raise HTTPException(status_code=409, detail="This item is reference-only and cannot be checked out")
        if not controller and not policy["self_checkout"]:
            raise HTTPException(status_code=403, detail="This item requires librarian checkout")
        if not payload.acknowledgement:
            raise HTTPException(status_code=422, detail="Custody acknowledgement is required")
        target_user_id = payload.patron_user_id if controller and payload.patron_user_id else str(current_user.id)
        patron = active_tenant_users(db, tenant, [target_user_id])[0]
        other_hold = db.query(lm.LibraryHoldRequest).filter(
            lm.LibraryHoldRequest.tenant_id == tenant.amo_id,
            lm.LibraryHoldRequest.catalog_item_id == item.id,
            lm.LibraryHoldRequest.status.in_(_ACTIVE_HOLD_STATUSES),
            lm.LibraryHoldRequest.user_id != patron.id,
        ).order_by(lm.LibraryHoldRequest.created_at.asc()).first()
        if other_hold and not (controller and payload.override_hold):
            raise HTTPException(status_code=409, detail="This title is reserved for another reader")
        due_at = payload.due_at if controller and payload.due_at else utcnow() + timedelta(days=policy["loan_period_days"])
        holding.status = "CHECKED_OUT"
        holding.holder_user_id = patron.id
        holding.checked_out_at = utcnow()
        holding.due_at = due_at
        holding.renewal_count = 0
        if payload.location:
            holding.current_location = payload.location.strip()
        patron_id = patron.id
        event_type = "CHECK_OUT"
    elif payload.action == "CHECK_IN":
        if not (controller or own):
            raise HTTPException(status_code=403, detail="Only the current borrower or librarian may check this item in")
        if holding.status != "CHECKED_OUT":
            raise HTTPException(status_code=409, detail="This item is not checked out")
        patron_id = holding.holder_user_id
        waiting = db.query(lm.LibraryHoldRequest).filter(
            lm.LibraryHoldRequest.tenant_id == tenant.amo_id,
            lm.LibraryHoldRequest.catalog_item_id == item.id,
            lm.LibraryHoldRequest.status == "ACTIVE",
            lm.LibraryHoldRequest.user_id != patron_id,
        ).order_by(lm.LibraryHoldRequest.created_at.asc()).first()
        holding.holder_user_id = None
        holding.checked_out_at = None
        holding.due_at = None
        holding.renewal_count = 0
        holding.status = "ON_HOLD" if waiting else "AVAILABLE"
        holding.current_location = (payload.location or holding.home_location).strip()
        if waiting:
            waiting.status = "READY"
            waiting.fulfilled_holding_id = holding.id
        event_type = "CHECK_IN"
    elif payload.action == "RENEW":
        if not (controller or own):
            raise HTTPException(status_code=403, detail="Only the current borrower or librarian may renew this item")
        if holding.status != "CHECKED_OUT":
            raise HTTPException(status_code=409, detail="This item is not checked out")
        if holding.renewal_count >= policy["max_renewals"]:
            raise HTTPException(status_code=409, detail="Renewal limit has been reached")
        waiting = db.query(lm.LibraryHoldRequest.id).filter(
            lm.LibraryHoldRequest.tenant_id == tenant.amo_id,
            lm.LibraryHoldRequest.catalog_item_id == item.id,
            lm.LibraryHoldRequest.status.in_(_ACTIVE_HOLD_STATUSES),
            lm.LibraryHoldRequest.user_id != holding.holder_user_id,
        ).first()
        if waiting and not (controller and payload.override_hold):
            raise HTTPException(status_code=409, detail="This title has a waiting hold and cannot be renewed")
        base = holding.due_at if holding.due_at and holding.due_at > utcnow() else utcnow()
        holding.due_at = payload.due_at if controller and payload.due_at else base + timedelta(days=policy["loan_period_days"])
        holding.renewal_count += 1
        patron_id = holding.holder_user_id
        event_type = "RENEW"
    else:
        if not (controller or own):
            raise HTTPException(status_code=403, detail="Only the current borrower or librarian may verify this item location")
        location = str(payload.location or holding.current_location).strip()
        if not location:
            raise HTTPException(status_code=422, detail="A physical location is required")
        holding.current_location = location
        holding.last_inventory_at = utcnow()
        patron_id = holding.holder_user_id
        event_type = "LOCATION_VERIFIED"

    holding.version = int(holding.version or 0) + 1
    db.add(lm.LibraryCirculationEvent(
        tenant_id=tenant.amo_id,
        holding_id=holding.id,
        event_type=event_type,
        actor_user_id=current_user.id,
        patron_user_id=patron_id,
        from_status=before_status,
        to_status=holding.status,
        from_location=before_location,
        to_location=holding.current_location,
        due_at=holding.due_at,
        notes=(payload.comments or "").strip() or None,
        metadata_json={
            "acknowledgement": payload.acknowledgement,
            "override_hold": bool(controller and payload.override_hold),
        },
    ))
    audit(db, tenant, request, f"document.library.{event_type.lower()}", "library_holding", holding.id, {
        "catalog_item_id": item.id,
        "barcode": holding.barcode,
        "from_status": before_status,
        "to_status": holding.status,
        "patron_user_id": patron_id,
        "due_at": holding.due_at.isoformat() if holding.due_at else None,
    })
    db.commit()
    return {
        "item": _serialize_item(item),
        "holding": _serialize_holding(holding, controller=controller, own=str(holding.holder_user_id or "") == str(current_user.id)),
    }


@router.post("/t/{tenant_slug}/catalog/items/{item_id}/holds", status_code=201)
def create_hold(
    tenant_slug: str,
    item_id: str,
    payload: HoldCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    item = _item(db, tenant.amo_id, item_id, current_user)
    policy = _policy(item)
    if not policy["circulatable"] or policy["reference_only"]:
        raise HTTPException(status_code=409, detail="This item cannot be reserved for circulation")
    existing = db.query(lm.LibraryHoldRequest).filter(
        lm.LibraryHoldRequest.tenant_id == tenant.amo_id,
        lm.LibraryHoldRequest.catalog_item_id == item.id,
        lm.LibraryHoldRequest.user_id == current_user.id,
        lm.LibraryHoldRequest.status.in_(_ACTIVE_HOLD_STATUSES),
    ).first()
    if existing:
        return {"id": existing.id, "status": existing.status, "already_exists": True}
    row = lm.LibraryHoldRequest(
        tenant_id=tenant.amo_id,
        catalog_item_id=item.id,
        user_id=current_user.id,
        pickup_location=(payload.pickup_location or "").strip() or None,
        expires_at=payload.expires_at,
    )
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.library.hold_placed", "library_hold", row.id, {"catalog_item_id": item.id})
    db.commit()
    return {"id": row.id, "status": row.status, "already_exists": False}


@router.delete("/t/{tenant_slug}/catalog/holds/{hold_id}")
def cancel_hold(
    tenant_slug: str,
    hold_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(lm.LibraryHoldRequest).filter(
        lm.LibraryHoldRequest.tenant_id == tenant.amo_id,
        lm.LibraryHoldRequest.id == hold_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Library hold not found")
    if str(row.user_id) != str(current_user.id) and not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Only the reader or librarian may cancel this hold")
    if row.status not in _ACTIVE_HOLD_STATUSES:
        raise HTTPException(status_code=409, detail="This hold is no longer active")
    row.status = "CANCELLED"
    audit(db, tenant, request, "document.library.hold_cancelled", "library_hold", row.id, {"catalog_item_id": row.catalog_item_id})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/t/{tenant_slug}/catalog/me")
def my_library_account(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    loans = db.query(lm.LibraryHolding, lm.LibraryCatalogItem).join(
        lm.LibraryCatalogItem, lm.LibraryCatalogItem.id == lm.LibraryHolding.catalog_item_id,
    ).filter(
        lm.LibraryHolding.tenant_id == tenant.amo_id,
        lm.LibraryHolding.holder_user_id == current_user.id,
        lm.LibraryHolding.status == "CHECKED_OUT",
    ).order_by(lm.LibraryHolding.due_at.asc()).all()
    holds = db.query(lm.LibraryHoldRequest, lm.LibraryCatalogItem).join(
        lm.LibraryCatalogItem, lm.LibraryCatalogItem.id == lm.LibraryHoldRequest.catalog_item_id,
    ).filter(
        lm.LibraryHoldRequest.tenant_id == tenant.amo_id,
        lm.LibraryHoldRequest.user_id == current_user.id,
        lm.LibraryHoldRequest.status.in_(_ACTIVE_HOLD_STATUSES),
    ).order_by(lm.LibraryHoldRequest.created_at.asc()).all()
    return {
        "loans": [{
            "item": _serialize_item(item),
            "holding": _serialize_holding(holding, controller=False, own=True),
        } for holding, item in loans],
        "holds": [{
            "id": hold.id,
            "status": hold.status,
            "pickup_location": hold.pickup_location,
            "expires_at": hold.expires_at.isoformat() if hold.expires_at else None,
            "item": _serialize_item(item),
        } for hold, item in holds],
    }


def _draw_qr(target: str, size: float = 32 * mm) -> Drawing:
    widget = qr.QrCodeWidget(target)
    x1, y1, x2, y2 = widget.getBounds()
    scale = min(size / max(1.0, x2 - x1), size / max(1.0, y2 - y1))
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    return drawing


@router.get("/t/{tenant_slug}/catalog/holdings/{holding_id}/label.pdf")
def holding_label(
    tenant_slug: str,
    holding_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    holding = _holding(db, tenant.amo_id, holding_id)
    item = _item(db, tenant.amo_id, holding.catalog_item_id, current_user)
    origin = str(request.headers.get("origin") or str(request.base_url).rstrip("/")).rstrip("/")
    scan_url = f"{origin}/maintenance/{tenant_slug}/document-control/library?library_scan={quote_plus(holding.qr_token)}"

    output = BytesIO()
    width, height = A6
    pdf = canvas.Canvas(output, pagesize=A6)
    pdf.setTitle(f"Library item {holding.barcode}")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(8 * mm, height - 12 * mm, item.catalogue_code[:42])
    pdf.setFont("Helvetica", 8)
    title = item.title if len(item.title) <= 52 else f"{item.title[:49]}..."
    pdf.drawString(8 * mm, height - 18 * mm, title)
    pdf.drawString(8 * mm, height - 24 * mm, f"Call no: {holding.call_number or '—'}")
    pdf.drawString(8 * mm, height - 30 * mm, f"Home: {holding.home_location[:52]}")
    barcode = createBarcodeDrawing("Code128", value=holding.barcode, barHeight=12 * mm, humanReadable=True)
    renderPDF.draw(barcode, pdf, 8 * mm, height - 55 * mm)
    renderPDF.draw(_draw_qr(scan_url), pdf, width - 43 * mm, 14 * mm)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(8 * mm, 14 * mm, "Scan requires login; the code is an item identifier, not an access credential.")
    pdf.rect(4 * mm, 4 * mm, width - 8 * mm, height - 8 * mm)
    pdf.showPage()
    pdf.save()
    filename = f"{item.catalogue_code}-{holding.barcode}-library-label.pdf".replace("/", "-").replace("\\", "-")
    return Response(
        content=output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )
