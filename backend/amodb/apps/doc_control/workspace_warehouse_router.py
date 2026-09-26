from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import library_models as lm
from . import records_vault_models as rm
from . import warehouse_models as wm
from . import warehouse_service as warehouse
from .workspace_library_catalog_router import _visible_query
from .workspace_records_vault_router import _can_read_record, _record_access_predicate
from .workspace_service import audit, can_read_manual, get_profile, is_control_user, require_control_user, resolve_tenant, role_value


router = APIRouter(prefix="/workspace", tags=["Document Control Knowledge Warehouse"])


class WarehouseRelationshipCreate(BaseModel):
    source_record_id: str
    target_record_id: str
    relationship_type: str = Field(min_length=2, max_length=64)
    source_version_id: str | None = None
    target_version_id: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WarehouseLocationCreate(BaseModel):
    code: str = Field(min_length=2, max_length=128)
    name: str = Field(min_length=2, max_length=255)
    location_type: str = Field(default="SHELF", min_length=2, max_length=40)
    parent_id: str | None = None
    path_text: str = Field(min_length=2, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WarehouseExternalReferenceCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=64)
    reference_type: str = Field(min_length=2, max_length=64)
    external_id: str | None = Field(default=None, max_length=255)
    url: str = Field(min_length=8, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WarehouseAccessPolicyCreate(BaseModel):
    action: str = Field(default="READ", min_length=2, max_length=32)
    effect: Literal["ALLOW", "DENY"] = "ALLOW"
    principal_type: Literal["USER", "ROLE", "DEPARTMENT", "ALL"] = "ROLE"
    principal_value: str = Field(min_length=1, max_length=255)
    conditions: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10_000)


class WarehouseAcknowledgementCreate(BaseModel):
    method: str = Field(default="READER_SIGNOFF", min_length=2, max_length=40)
    session_metadata: dict[str, Any] = Field(default_factory=dict)


def _resource(db: Session, tenant_id: str, record_id: str) -> wm.WarehouseContentRecord:
    row = (
        db.query(wm.WarehouseContentRecord)
        .filter(
            wm.WarehouseContentRecord.tenant_id == tenant_id,
            wm.WarehouseContentRecord.id == record_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse resource not found")
    return row


def _matching_policy_principals(user: account_models.User) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = [("USER", str(user.id)), ("ALL", "*")]
    role = role_value(user)
    if role:
        values.append(("ROLE", role.upper()))
    department = getattr(user, "department", None)
    for value in (
        getattr(user, "department_id", None),
        getattr(department, "id", None),
        getattr(department, "code", None),
        getattr(department, "name", None),
    ):
        if value:
            values.append(("DEPARTMENT", str(value).upper()))
    return values


def _policy_conditions_match(policy: wm.WarehouseAccessPolicy, user: account_models.User) -> bool:
    conditions = dict(policy.conditions_json or {})
    if not conditions:
        return True

    supported = {"roles", "departments", "user_active"}
    if set(conditions) - supported:
        return False

    if "user_active" in conditions and bool(getattr(user, "is_active", False)) is not bool(conditions["user_active"]):
        return False

    if "roles" in conditions:
        allowed_roles = {str(value).strip().upper() for value in conditions["roles"] if str(value).strip()}
        if role_value(user).upper() not in allowed_roles:
            return False

    if "departments" in conditions:
        department = getattr(user, "department", None)
        actual = {
            str(value).strip().upper()
            for value in (
                getattr(user, "department_id", None),
                getattr(department, "id", None),
                getattr(department, "code", None),
                getattr(department, "name", None),
            )
            if value
        }
        required = {str(value).strip().upper() for value in conditions["departments"] if str(value).strip()}
        if not actual.intersection(required):
            return False

    return True


def _native_policy_decision(db: Session, *, tenant_id: str, record_id: str, user: account_models.User, action: str = "READ") -> bool | None:
    principals = _matching_policy_principals(user)
    matches = (
        db.query(wm.WarehouseAccessPolicy)
        .filter(
            wm.WarehouseAccessPolicy.tenant_id == tenant_id,
            wm.WarehouseAccessPolicy.content_record_id == record_id,
            wm.WarehouseAccessPolicy.action == action.upper(),
            or_(*[
                (
                    (wm.WarehouseAccessPolicy.principal_type == principal_type)
                    & (func.upper(wm.WarehouseAccessPolicy.principal_value) == principal_value.upper())
                )
                for principal_type, principal_value in principals
            ]),
        )
        .order_by(wm.WarehouseAccessPolicy.priority.asc(), wm.WarehouseAccessPolicy.created_at.asc())
        .all()
    )
    applicable = [row for row in matches if _policy_conditions_match(row, user)]
    if any(row.effect == "DENY" for row in applicable):
        return False
    if any(row.effect == "ALLOW" for row in applicable):
        return True
    return None


def _native_policy_allows(db: Session, *, tenant_id: str, record_id: str, user: account_models.User, action: str = "READ") -> bool:
    return _native_policy_decision(db, tenant_id=tenant_id, record_id=record_id, user=user, action=action) is True


def _source_visible(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
    row: wm.WarehouseContentRecord,
) -> bool:
    if is_control_user(user):
        return True

    policy = _native_policy_decision(db, tenant_id=str(tenant.amo_id), record_id=row.id, user=user)
    if policy is False:
        return False

    source_type = row.source_entity_type
    if source_type == "CONTROLLED_DOCUMENT":
        manual = (
            db.query(manual_models.Manual)
            .filter(
                manual_models.Manual.tenant_id == tenant.id,
                manual_models.Manual.id == row.source_entity_id,
            )
            .first()
        )
        return bool(manual and can_read_manual(user, get_profile(db, tenant, manual.id)))

    if source_type == "LIBRARY_CATALOG_ITEM":
        visible = _visible_query(
            db.query(lm.LibraryCatalogItem).filter(
                lm.LibraryCatalogItem.tenant_id == tenant.amo_id,
                lm.LibraryCatalogItem.id == row.source_entity_id,
            ),
            user,
        ).first()
        return visible is not None

    if source_type == "RETAINED_RECORD":
        pair = (
            db.query(rm.TenantRecordAsset, rm.TenantRecordSeries)
            .join(rm.TenantRecordSeries, rm.TenantRecordSeries.id == rm.TenantRecordAsset.series_id)
            .filter(
                rm.TenantRecordAsset.tenant_id == tenant.amo_id,
                rm.TenantRecordAsset.id == row.source_entity_id,
            )
            .first()
        )
        return bool(pair and _can_read_record(user, pair[1], pair[0]))

    return policy is True


def _visible_record_ids(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
) -> list[str] | None:
    if is_control_user(user):
        return None

    allowed_sources: dict[str, set[str]] = {
        "CONTROLLED_DOCUMENT": set(),
        "LIBRARY_CATALOG_ITEM": set(),
        "RETAINED_RECORD": set(),
    }

    manuals = (
        db.query(manual_models.Manual)
        .filter(manual_models.Manual.tenant_id == tenant.id)
        .all()
    )
    for manual in manuals:
        if can_read_manual(user, get_profile(db, tenant, manual.id)):
            allowed_sources["CONTROLLED_DOCUMENT"].add(str(manual.id))

    library_ids = {
        str(row[0])
        for row in _visible_query(
            db.query(lm.LibraryCatalogItem.id).filter(lm.LibraryCatalogItem.tenant_id == tenant.amo_id),
            user,
        ).all()
    }
    allowed_sources["LIBRARY_CATALOG_ITEM"] = library_ids

    record_ids = {
        str(row[0])
        for row in (
            db.query(rm.TenantRecordAsset.id)
            .join(rm.TenantRecordSeries, rm.TenantRecordSeries.id == rm.TenantRecordAsset.series_id)
            .filter(
                rm.TenantRecordAsset.tenant_id == tenant.amo_id,
                rm.TenantRecordSeries.tenant_id == tenant.amo_id,
                _record_access_predicate(user),
            )
            .all()
        )
    }
    allowed_sources["RETAINED_RECORD"] = record_ids

    source_conditions = []
    for source_type, ids in allowed_sources.items():
        if ids:
            source_conditions.append(
                (wm.WarehouseContentRecord.source_entity_type == source_type)
                & (wm.WarehouseContentRecord.source_entity_id.in_(ids))
            )

    policy_record_ids: set[str] = set()
    principals = _matching_policy_principals(user)
    policies = (
        db.query(wm.WarehouseAccessPolicy)
        .filter(
            wm.WarehouseAccessPolicy.tenant_id == tenant.amo_id,
            wm.WarehouseAccessPolicy.action == "READ",
            or_(*[
                (
                    (wm.WarehouseAccessPolicy.principal_type == principal_type)
                    & (func.upper(wm.WarehouseAccessPolicy.principal_value) == principal_value.upper())
                )
                for principal_type, principal_value in principals
            ]),
        )
        .all()
    )
    applicable = [row for row in policies if _policy_conditions_match(row, user)]
    denied = {str(row.content_record_id) for row in applicable if row.effect == "DENY"}
    # Explicit grants only introduce native warehouse records. Source-backed
    # records must still satisfy the source module's own access policy.
    policy_record_ids = {str(row.content_record_id) for row in applicable if row.effect == "ALLOW"} - denied

    if source_conditions:
        source_ids = {
            str(row[0])
            for row in (
                db.query(wm.WarehouseContentRecord.id)
                .filter(
                    wm.WarehouseContentRecord.tenant_id == tenant.amo_id,
                    or_(*source_conditions),
                )
                .all()
            )
        }
    else:
        source_ids = set()
    candidate_ids = (source_ids | policy_record_ids) - denied
    if not candidate_ids:
        return []
    candidates = db.query(wm.WarehouseContentRecord).filter(
        wm.WarehouseContentRecord.tenant_id == tenant.amo_id,
        wm.WarehouseContentRecord.id.in_(candidate_ids),
    ).all()
    return sorted(row.id for row in candidates if (
        row.source_entity_type in allowed_sources and row.source_entity_id in allowed_sources[row.source_entity_type]
    ) or (row.source_entity_type not in allowed_sources and row.id in policy_record_ids))


def _target_path(tenant: manual_models.Tenant, row: wm.WarehouseContentRecord) -> str | None:
    base = f"/maintenance/{tenant.slug.upper()}/document-control"
    if row.source_entity_type == "CONTROLLED_DOCUMENT":
        return f"{base}/library/{row.source_entity_id}"
    if row.source_entity_type == "LIBRARY_CATALOG_ITEM":
        return f"{base}/library?library_item={row.source_entity_id}"
    if row.source_entity_type == "RETAINED_RECORD":
        return f"{base}/records?record={row.source_entity_id}"
    return None


def _serialize_resource(tenant: manual_models.Tenant, row: wm.WarehouseContentRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "resource_type": row.resource_type,
        "canonical_code": row.canonical_code,
        "title": row.title,
        "description": row.description,
        "classification": row.classification,
        "lifecycle_status": row.lifecycle_status,
        "owner_department": row.owner_department,
        "source": {
            "entity_type": row.source_entity_type,
            "entity_id": row.source_entity_id,
        },
        "metadata": dict(row.metadata_json or {}),
        "target_path": _target_path(tenant, row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/t/{tenant_slug}/warehouse/reconcile")
def reconcile_warehouse(
    tenant_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    counts = warehouse.reconcile_tenant_warehouse(
        db,
        manual_tenant=tenant,
        actor_user_id=str(current_user.id),
    )
    audit(
        db,
        tenant,
        request,
        "document.warehouse.reconciled",
        "tenant_knowledge_warehouse",
        str(tenant.amo_id),
        counts,
    )
    db.commit()
    return {
        "status": "RECONCILED",
        "counts": counts,
        "source_of_truth": {
            "metadata": "PostgreSQL operational domains",
            "binaries": "existing controlled/records storage",
            "warehouse": "canonical governed-resource registry",
        },
    }


@router.get("/t/{tenant_slug}/warehouse/overview")
def warehouse_overview(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Permission-filtered operational picture of the tenant knowledge warehouse."""
    tenant = resolve_tenant(db, tenant_slug, current_user)
    visible_ids = _visible_record_ids(db, tenant=tenant, user=current_user)
    record_ids = visible_ids
    if record_ids is None:
        record_ids = [
            str(row[0])
            for row in db.query(wm.WarehouseContentRecord.id)
            .filter(wm.WarehouseContentRecord.tenant_id == tenant.amo_id)
            .all()
        ]
    scoped_ids = record_ids or ["-"]

    resource_rows = (
        db.query(wm.WarehouseContentRecord.resource_type, func.count(wm.WarehouseContentRecord.id))
        .filter(
            wm.WarehouseContentRecord.tenant_id == tenant.amo_id,
            wm.WarehouseContentRecord.id.in_(scoped_ids),
        )
        .group_by(wm.WarehouseContentRecord.resource_type)
        .all()
    )
    version_rows = (
        db.query(wm.WarehouseContentVersion.lifecycle_status, func.count(wm.WarehouseContentVersion.id))
        .filter(
            wm.WarehouseContentVersion.tenant_id == tenant.amo_id,
            wm.WarehouseContentVersion.content_record_id.in_(scoped_ids),
        )
        .group_by(wm.WarehouseContentVersion.lifecycle_status)
        .all()
    )
    copy_rows = (
        db.query(wm.WarehouseItemCopy.status, func.count(wm.WarehouseItemCopy.id))
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
            wm.WarehouseItemCopy.content_record_id.in_(scoped_ids),
        )
        .group_by(wm.WarehouseItemCopy.status)
        .all()
    )
    revision_required = int(
        db.query(func.count(wm.WarehouseItemCopy.id))
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
            wm.WarehouseItemCopy.content_record_id.in_(scoped_ids),
            wm.WarehouseItemCopy.revision_compliance == "REVISION_REQUIRED",
        )
        .scalar() or 0
    )
    unverified_relationships = int(
        db.query(func.count(wm.WarehouseRelationship.id))
        .filter(
            wm.WarehouseRelationship.tenant_id == tenant.amo_id,
            wm.WarehouseRelationship.status == "ACTIVE",
            wm.WarehouseRelationship.verified_by_user_id.is_(None),
            wm.WarehouseRelationship.source_record_id.in_(scoped_ids),
            wm.WarehouseRelationship.target_record_id.in_(scoped_ids),
        )
        .scalar() or 0
    )

    patron = (
        db.query(wm.WarehousePatron)
        .filter(
            wm.WarehousePatron.tenant_id == tenant.amo_id,
            wm.WarehousePatron.user_id == current_user.id,
        )
        .first()
    )
    my_active_loans = 0
    my_active_holds = 0
    if patron is not None:
        my_active_loans = int(
            db.query(func.count(wm.WarehouseLoan.id))
            .filter(
                wm.WarehouseLoan.tenant_id == tenant.amo_id,
                wm.WarehouseLoan.patron_id == patron.id,
                wm.WarehouseLoan.status == "ACTIVE",
            )
            .scalar() or 0
        )
        my_active_holds = int(
            db.query(func.count(wm.WarehouseHold.id))
            .filter(
                wm.WarehouseHold.tenant_id == tenant.amo_id,
                wm.WarehouseHold.patron_id == patron.id,
                wm.WarehouseHold.status == "ACTIVE",
            )
            .scalar() or 0
        )

    my_acknowledgements = int(
        db.query(func.count(wm.WarehouseAcknowledgement.id))
        .filter(
            wm.WarehouseAcknowledgement.tenant_id == tenant.amo_id,
            wm.WarehouseAcknowledgement.user_id == current_user.id,
            wm.WarehouseAcknowledgement.content_record_id.in_(scoped_ids),
        )
        .scalar() or 0
    )
    total_relationships = int(
        db.query(func.count(wm.WarehouseRelationship.id))
        .filter(
            wm.WarehouseRelationship.tenant_id == tenant.amo_id,
            wm.WarehouseRelationship.status == "ACTIVE",
            wm.WarehouseRelationship.source_record_id.in_(scoped_ids),
            wm.WarehouseRelationship.target_record_id.in_(scoped_ids),
        )
        .scalar() or 0
    )

    return {
        "resources": {
            "total": sum(int(count or 0) for _, count in resource_rows),
            "by_type": {str(kind): int(count or 0) for kind, count in resource_rows},
        },
        "versions": {
            "total": sum(int(count or 0) for _, count in version_rows),
            "by_status": {str(status): int(count or 0) for status, count in version_rows},
        },
        "physical_copies": {
            "total": sum(int(count or 0) for _, count in copy_rows),
            "by_status": {str(status): int(count or 0) for status, count in copy_rows},
            "revision_required": revision_required,
        },
        "relationships": {
            "total": total_relationships,
            "unverified": unverified_relationships,
        },
        "my_work": {
            "active_loans": my_active_loans,
            "active_holds": my_active_holds,
            "acknowledgements_completed": my_acknowledgements,
        },
        "capabilities": {"control": is_control_user(current_user)},
    }


@router.get("/t/{tenant_slug}/warehouse/resources")
def list_warehouse_resources(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    resource_type: str | None = Query(default=None, max_length=64),
    lifecycle_status: str | None = Query(default=None, max_length=32),
    classification: str | None = Query(default=None, max_length=32),
    revision_required: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    visible_ids = _visible_record_ids(db, tenant=tenant, user=current_user)
    query = db.query(wm.WarehouseContentRecord).filter(
        wm.WarehouseContentRecord.tenant_id == tenant.amo_id,
    )
    if visible_ids is not None:
        query = query.filter(wm.WarehouseContentRecord.id.in_(visible_ids or ["-"]))
    if resource_type:
        query = query.filter(wm.WarehouseContentRecord.resource_type == resource_type.strip().upper())
    if lifecycle_status:
        query = query.filter(wm.WarehouseContentRecord.lifecycle_status == lifecycle_status.strip().upper())
    if classification:
        query = query.filter(wm.WarehouseContentRecord.classification == classification.strip().upper())
    if revision_required:
        query = query.filter(
            db.query(wm.WarehouseItemCopy.id).filter(
                wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
                wm.WarehouseItemCopy.content_record_id == wm.WarehouseContentRecord.id,
                wm.WarehouseItemCopy.revision_compliance == "REVISION_REQUIRED",
            ).exists()
        )

    search = " ".join(str(q or "").split())
    if search:
        normalized = search.upper()
        identifier_match = db.query(wm.WarehouseIdentifier.id).filter(
            wm.WarehouseIdentifier.tenant_id == tenant.amo_id,
            wm.WarehouseIdentifier.content_record_id == wm.WarehouseContentRecord.id,
            or_(
                func.upper(wm.WarehouseIdentifier.normalized_value) == normalized,
                wm.WarehouseIdentifier.display_value.ilike(f"%{search}%"),
            ),
        ).exists()
        if db.get_bind().dialect.name == "postgresql":
            tsquery = func.websearch_to_tsquery("simple", search)
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
            needle = f"%{search}%"
            query = query.filter(or_(
                wm.WarehouseContentRecord.canonical_code.ilike(needle),
                wm.WarehouseContentRecord.title.ilike(needle),
                wm.WarehouseContentRecord.description.ilike(needle),
                identifier_match,
            ))
        query = query.order_by(
            case((func.upper(wm.WarehouseContentRecord.canonical_code) == normalized, 0), else_=1),
            wm.WarehouseContentRecord.title.asc(),
        )
    else:
        query = query.order_by(wm.WarehouseContentRecord.title.asc(), wm.WarehouseContentRecord.canonical_code.asc())

    total = int(query.order_by(None).count())
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    ids = [row.id for row in rows]
    version_counts = dict(
        db.query(wm.WarehouseContentVersion.content_record_id, func.count(wm.WarehouseContentVersion.id))
        .filter(wm.WarehouseContentVersion.content_record_id.in_(ids or ["-"]))
        .group_by(wm.WarehouseContentVersion.content_record_id)
        .all()
    )
    copy_rows = (
        db.query(
            wm.WarehouseItemCopy.content_record_id,
            func.count(wm.WarehouseItemCopy.id),
            func.sum(case((wm.WarehouseItemCopy.revision_compliance == "REVISION_REQUIRED", 1), else_=0)),
        )
        .filter(wm.WarehouseItemCopy.content_record_id.in_(ids or ["-"]))
        .group_by(wm.WarehouseItemCopy.content_record_id)
        .all()
    )
    copy_counts = {
        str(record_id): {"total": int(total_count or 0), "revision_required": int(revision_count or 0)}
        for record_id, total_count, revision_count in copy_rows
    }
    return {
        "items": [
            {
                **_serialize_resource(tenant, row),
                "versions_count": int(version_counts.get(row.id, 0)),
                "copies": copy_counts.get(str(row.id), {"total": 0, "revision_required": 0}),
            }
            for row in rows
        ],
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(rows)},
        "capabilities": {"control": is_control_user(current_user)},
    }


@router.get("/t/{tenant_slug}/warehouse/resources/{record_id}")
def get_warehouse_resource(
    tenant_slug: str,
    record_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _resource(db, str(tenant.amo_id), record_id)
    if not _source_visible(db, tenant=tenant, user=current_user, row=row):
        raise HTTPException(status_code=403, detail="This warehouse resource is outside your authorized scope")

    versions = (
        db.query(wm.WarehouseContentVersion)
        .filter(
            wm.WarehouseContentVersion.tenant_id == tenant.amo_id,
            wm.WarehouseContentVersion.content_record_id == row.id,
        )
        .order_by(wm.WarehouseContentVersion.sequence.desc())
        .all()
    )
    if row.source_entity_type == "CONTROLLED_DOCUMENT" and not is_control_user(current_user):
        versions = [version for version in versions if version.lifecycle_status in {"PUBLISHED", "SUPERSEDED"}]
    identifiers = (
        db.query(wm.WarehouseIdentifier)
        .filter(
            wm.WarehouseIdentifier.tenant_id == tenant.amo_id,
            wm.WarehouseIdentifier.content_record_id == row.id,
        )
        .order_by(wm.WarehouseIdentifier.scheme.asc())
        .all()
    )
    copies = (
        db.query(wm.WarehouseItemCopy)
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
            wm.WarehouseItemCopy.content_record_id == row.id,
        )
        .order_by(wm.WarehouseItemCopy.copy_number.asc(), wm.WarehouseItemCopy.barcode.asc())
        .all()
    )
    outgoing = (
        db.query(wm.WarehouseRelationship)
        .filter(
            wm.WarehouseRelationship.tenant_id == tenant.amo_id,
            wm.WarehouseRelationship.source_record_id == row.id,
            wm.WarehouseRelationship.status == "ACTIVE",
        )
        .all()
    )
    incoming = (
        db.query(wm.WarehouseRelationship)
        .filter(
            wm.WarehouseRelationship.tenant_id == tenant.amo_id,
            wm.WarehouseRelationship.target_record_id == row.id,
            wm.WarehouseRelationship.status == "ACTIVE",
        )
        .all()
    )
    visible_ids = _visible_record_ids(db, tenant=tenant, user=current_user)
    if visible_ids is not None:
        visible_set = set(visible_ids)
        outgoing = [relation for relation in outgoing if relation.target_record_id in visible_set]
        incoming = [relation for relation in incoming if relation.source_record_id in visible_set]
    references = (
        db.query(wm.WarehouseExternalReference)
        .filter(
            wm.WarehouseExternalReference.tenant_id == tenant.amo_id,
            wm.WarehouseExternalReference.content_record_id == row.id,
        )
        .all()
    )
    own_acknowledgements = (
        db.query(wm.WarehouseAcknowledgement)
        .filter(
            wm.WarehouseAcknowledgement.tenant_id == tenant.amo_id,
            wm.WarehouseAcknowledgement.content_record_id == row.id,
            wm.WarehouseAcknowledgement.user_id == current_user.id,
        )
        .all()
    )

    return {
        "resource": _serialize_resource(tenant, row),
        "versions": [{
            "id": version.id,
            "version_label": version.version_label,
            "sequence": version.sequence,
            "lifecycle_status": version.lifecycle_status,
            "file_hash": version.file_hash if is_control_user(current_user) else None,
            "effective_at": version.effective_at.isoformat() if version.effective_at else None,
            "superseded_at": version.superseded_at.isoformat() if version.superseded_at else None,
            "immutable": bool(version.immutable),
            "metadata": dict(version.metadata_json or {}),
        } for version in versions],
        "identifiers": [{
            "scheme": identifier.scheme,
            "value": identifier.display_value,
            "source": identifier.source,
        } for identifier in identifiers],
        "copies": [{
            "id": copy.id,
            "copy_number": copy.copy_number,
            "barcode": copy.barcode,
            "format": copy.format,
            "status": copy.status,
            "location": copy.location_text,
            "installed_version": copy.installed_version_label,
            "required_version": copy.required_version_label,
            "revision_compliance": copy.revision_compliance,
            "last_inventory_at": copy.last_inventory_at.isoformat() if copy.last_inventory_at else None,
        } for copy in copies],
        "relationships": {
            "outgoing": [{
                "id": relation.id,
                "type": relation.relationship_type,
                "target_record_id": relation.target_record_id,
                "source_version_id": relation.source_version_id,
                "target_version_id": relation.target_version_id,
                "status": relation.status,
            } for relation in outgoing],
            "incoming": [{
                "id": relation.id,
                "type": relation.relationship_type,
                "source_record_id": relation.source_record_id,
                "source_version_id": relation.source_version_id,
                "target_version_id": relation.target_version_id,
                "status": relation.status,
            } for relation in incoming],
        },
        "external_references": [{
            "id": reference.id,
            "provider": reference.provider,
            "reference_type": reference.reference_type,
            "external_id": reference.external_id,
            "url": reference.url,
        } for reference in references],
        "acknowledgements": [{
            "version_id": acknowledgement.content_version_id,
            "method": acknowledgement.acknowledgement_method,
            "acknowledged_at": acknowledgement.acknowledged_at.isoformat() if acknowledgement.acknowledged_at else None,
        } for acknowledgement in own_acknowledgements],
        "capabilities": {"control": is_control_user(current_user)},
    }


@router.get("/t/{tenant_slug}/warehouse/resources/{record_id}/impact")
def warehouse_resource_impact(
    tenant_slug: str,
    record_id: str,
    depth: int = Query(default=2, ge=1, le=3),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Traverse verified and unverified governed relationships without crossing access boundaries."""
    tenant = resolve_tenant(db, tenant_slug, current_user)
    root = _resource(db, str(tenant.amo_id), record_id)
    if not _source_visible(db, tenant=tenant, user=current_user, row=root):
        raise HTTPException(status_code=403, detail="This warehouse resource is outside your authorized scope")

    visible_ids = _visible_record_ids(db, tenant=tenant, user=current_user)
    allowed_ids = None if visible_ids is None else set(visible_ids)
    discovered = {root.id}
    frontier = {root.id}
    edges: list[wm.WarehouseRelationship] = []

    for _ in range(depth):
        if not frontier:
            break
        batch = (
            db.query(wm.WarehouseRelationship)
            .filter(
                wm.WarehouseRelationship.tenant_id == tenant.amo_id,
                wm.WarehouseRelationship.status == "ACTIVE",
                or_(
                    wm.WarehouseRelationship.source_record_id.in_(frontier),
                    wm.WarehouseRelationship.target_record_id.in_(frontier),
                ),
            )
            .all()
        )
        next_frontier: set[str] = set()
        for relation in batch:
            if allowed_ids is not None and (
                relation.source_record_id not in allowed_ids
                or relation.target_record_id not in allowed_ids
            ):
                continue
            if all(existing.id != relation.id for existing in edges):
                edges.append(relation)
            for candidate in (relation.source_record_id, relation.target_record_id):
                if candidate not in discovered:
                    discovered.add(candidate)
                    next_frontier.add(candidate)
        frontier = next_frontier

    nodes = (
        db.query(wm.WarehouseContentRecord)
        .filter(
            wm.WarehouseContentRecord.tenant_id == tenant.amo_id,
            wm.WarehouseContentRecord.id.in_(list(discovered)),
        )
        .all()
    )
    revision_rows = (
        db.query(
            wm.WarehouseItemCopy.content_record_id,
            func.count(wm.WarehouseItemCopy.id),
        )
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
            wm.WarehouseItemCopy.content_record_id.in_(list(discovered)),
            wm.WarehouseItemCopy.revision_compliance == "REVISION_REQUIRED",
        )
        .group_by(wm.WarehouseItemCopy.content_record_id)
        .all()
    )
    revision_required = {str(rid): int(count or 0) for rid, count in revision_rows}
    return {
        "root_record_id": root.id,
        "depth": depth,
        "nodes": [
            {
                **_serialize_resource(tenant, node),
                "revision_required_copies": revision_required.get(str(node.id), 0),
            }
            for node in nodes
        ],
        "edges": [{
            "id": relation.id,
            "source_record_id": relation.source_record_id,
            "source_version_id": relation.source_version_id,
            "relationship_type": relation.relationship_type,
            "target_record_id": relation.target_record_id,
            "target_version_id": relation.target_version_id,
            "verified": relation.verified_by_user_id is not None,
            "verified_by_user_id": relation.verified_by_user_id if is_control_user(current_user) else None,
            "effective_from": relation.effective_from.isoformat() if relation.effective_from else None,
            "effective_to": relation.effective_to.isoformat() if relation.effective_to else None,
        } for relation in edges],
        "summary": {
            "resources": len(nodes),
            "relationships": len(edges),
            "unverified_relationships": sum(1 for relation in edges if relation.verified_by_user_id is None),
            "revision_required_copies": sum(revision_required.values()),
        },
    }


@router.get("/t/{tenant_slug}/warehouse/resolve/{token}")
def resolve_warehouse_copy(
    tenant_slug: str,
    token: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    value = token.strip()
    copy = (
        db.query(wm.WarehouseItemCopy)
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
            or_(
                wm.WarehouseItemCopy.barcode == value,
                wm.WarehouseItemCopy.qr_token == value,
            ),
        )
        .first()
    )
    if copy is None:
        raise HTTPException(status_code=404, detail="No warehouse copy matches this barcode or QR token")
    record = _resource(db, str(tenant.amo_id), copy.content_record_id)
    if not _source_visible(db, tenant=tenant, user=current_user, row=record):
        raise HTTPException(status_code=403, detail="This warehouse item is outside your authorized scope")
    return {
        "resource": _serialize_resource(tenant, record),
        "copy": {
            "id": copy.id,
            "copy_number": copy.copy_number,
            "barcode": copy.barcode,
            "qr_token": copy.qr_token if is_control_user(current_user) else None,
            "format": copy.format,
            "status": copy.status,
            "location": copy.location_text,
            "installed_version": copy.installed_version_label,
            "required_version": copy.required_version_label,
            "revision_compliance": copy.revision_compliance,
            "last_inventory_at": copy.last_inventory_at.isoformat() if copy.last_inventory_at else None,
        },
    }


@router.get("/t/{tenant_slug}/warehouse/revision-exceptions")
def list_revision_exceptions(
    tenant_slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = (
        db.query(wm.WarehouseItemCopy, wm.WarehouseContentRecord)
        .join(wm.WarehouseContentRecord, wm.WarehouseContentRecord.id == wm.WarehouseItemCopy.content_record_id)
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant.amo_id,
            wm.WarehouseItemCopy.revision_compliance == "REVISION_REQUIRED",
        )
    )
    total = int(query.count())
    rows = (
        query.order_by(wm.WarehouseContentRecord.canonical_code.asc(), wm.WarehouseItemCopy.copy_number.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "items": [{
            "resource": _serialize_resource(tenant, record),
            "copy": {
                "id": copy.id,
                "copy_number": copy.copy_number,
                "barcode": copy.barcode,
                "location": copy.location_text,
                "installed_version": copy.installed_version_label,
                "required_version": copy.required_version_label,
                "status": copy.status,
            },
        } for copy, record in rows],
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(rows)},
    }


@router.post("/t/{tenant_slug}/warehouse/relationships", status_code=201)
def create_warehouse_relationship(
    tenant_slug: str,
    payload: WarehouseRelationshipCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    source = _resource(db, str(tenant.amo_id), payload.source_record_id)
    target = _resource(db, str(tenant.amo_id), payload.target_record_id)
    if source.id == target.id:
        raise HTTPException(status_code=422, detail="A warehouse relationship must connect two distinct resources")

    source_version_id = None
    if payload.source_version_id:
        source_version = (
            db.query(wm.WarehouseContentVersion)
            .filter(
                wm.WarehouseContentVersion.tenant_id == tenant.amo_id,
                wm.WarehouseContentVersion.id == payload.source_version_id,
                wm.WarehouseContentVersion.content_record_id == source.id,
            )
            .first()
        )
        if source_version is None:
            raise HTTPException(status_code=422, detail="Source version does not belong to the source resource")
        source_version_id = source_version.id
    target_version_id = None
    if payload.target_version_id:
        target_version = (
            db.query(wm.WarehouseContentVersion)
            .filter(
                wm.WarehouseContentVersion.tenant_id == tenant.amo_id,
                wm.WarehouseContentVersion.id == payload.target_version_id,
                wm.WarehouseContentVersion.content_record_id == target.id,
            )
            .first()
        )
        if target_version is None:
            raise HTTPException(status_code=422, detail="Target version does not belong to the target resource")
        target_version_id = target_version.id

    relation_type = payload.relationship_type.strip().upper().replace(" ", "_")
    duplicate = (
        db.query(wm.WarehouseRelationship)
        .filter(
            wm.WarehouseRelationship.tenant_id == tenant.amo_id,
            wm.WarehouseRelationship.source_record_id == source.id,
            wm.WarehouseRelationship.target_record_id == target.id,
            wm.WarehouseRelationship.relationship_type == relation_type,
            wm.WarehouseRelationship.source_version_id == source_version_id,
            wm.WarehouseRelationship.target_version_id == target_version_id,
            wm.WarehouseRelationship.status == "ACTIVE",
        )
        .first()
    )
    if duplicate:
        return {"id": duplicate.id, "status": duplicate.status, "duplicate": True}

    relation = wm.WarehouseRelationship(
        tenant_id=tenant.amo_id,
        source_record_id=source.id,
        source_version_id=source_version_id,
        relationship_type=relation_type,
        target_record_id=target.id,
        target_version_id=target_version_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        metadata_json=dict(payload.metadata),
        created_by_user_id=current_user.id,
    )
    db.add(relation)
    db.flush()
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=source.id,
        content_version_id=source_version_id,
        event_type="relationship.created",
        actor_user_id=str(current_user.id),
        metadata={"relationship_id": relation.id, "type": relation_type, "target_record_id": target.id},
    )
    audit(db, tenant, request, "document.warehouse.relationship_created", "warehouse_relationship", relation.id, {
        "source_record_id": source.id,
        "target_record_id": target.id,
        "relationship_type": relation_type,
    })
    db.commit()
    return {"id": relation.id, "status": relation.status, "duplicate": False}


@router.post("/t/{tenant_slug}/warehouse/relationships/{relationship_id}/verify")
def verify_warehouse_relationship(
    tenant_slug: str,
    relationship_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    relation = (
        db.query(wm.WarehouseRelationship)
        .filter(
            wm.WarehouseRelationship.tenant_id == tenant.amo_id,
            wm.WarehouseRelationship.id == relationship_id,
            wm.WarehouseRelationship.status == "ACTIVE",
        )
        .first()
    )
    if relation is None:
        raise HTTPException(status_code=404, detail="Warehouse relationship not found")
    relation.verified_by_user_id = current_user.id
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=relation.source_record_id,
        content_version_id=relation.source_version_id,
        event_type="relationship.verified",
        actor_user_id=str(current_user.id),
        metadata={
            "relationship_id": relation.id,
            "relationship_type": relation.relationship_type,
            "target_record_id": relation.target_record_id,
        },
    )
    audit(
        db,
        tenant,
        request,
        "document.warehouse.relationship_verified",
        "warehouse_relationship",
        relation.id,
        {
            "source_record_id": relation.source_record_id,
            "target_record_id": relation.target_record_id,
            "relationship_type": relation.relationship_type,
        },
    )
    db.commit()
    return {"id": relation.id, "status": relation.status, "verified": True}


@router.post("/t/{tenant_slug}/warehouse/resources/{record_id}/external-references", status_code=201)
def create_external_reference(
    tenant_slug: str,
    record_id: str,
    payload: WarehouseExternalReferenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    record = _resource(db, str(tenant.amo_id), record_id)
    if not payload.url.lower().startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="External reference URL must use http or https")
    row = wm.WarehouseExternalReference(
        tenant_id=tenant.amo_id,
        content_record_id=record.id,
        provider=payload.provider.strip().upper(),
        reference_type=payload.reference_type.strip().upper().replace(" ", "_"),
        external_id=(payload.external_id or "").strip() or None,
        url=payload.url.strip(),
        metadata_json=dict(payload.metadata),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=record.id,
        event_type="external_reference.created",
        actor_user_id=str(current_user.id),
        metadata={"external_reference_id": row.id, "provider": row.provider},
    )
    audit(db, tenant, request, "document.warehouse.external_reference_created", "warehouse_external_reference", row.id, {
        "content_record_id": record.id,
        "provider": row.provider,
        "reference_type": row.reference_type,
    })
    db.commit()
    return {"id": row.id, "provider": row.provider, "reference_type": row.reference_type, "url": row.url}


@router.post("/t/{tenant_slug}/warehouse/resources/{record_id}/access-policies", status_code=201)
def create_access_policy(
    tenant_slug: str,
    record_id: str,
    payload: WarehouseAccessPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    record = _resource(db, str(tenant.amo_id), record_id)
    supported_condition_keys = {"roles", "departments", "user_active"}
    unknown_conditions = set(payload.conditions) - supported_condition_keys
    if unknown_conditions:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported access-policy conditions: {', '.join(sorted(unknown_conditions))}",
        )
    for key in ("roles", "departments"):
        if key in payload.conditions and not isinstance(payload.conditions[key], list):
            raise HTTPException(status_code=422, detail=f"Access-policy condition '{key}' must be a list")
    if "user_active" in payload.conditions and not isinstance(payload.conditions["user_active"], bool):
        raise HTTPException(status_code=422, detail="Access-policy condition 'user_active' must be boolean")
    principal_value = payload.principal_value.strip()
    if payload.principal_type in {"ROLE", "DEPARTMENT", "ALL"}:
        principal_value = principal_value.upper()
    row = wm.WarehouseAccessPolicy(
        tenant_id=tenant.amo_id,
        content_record_id=record.id,
        action=payload.action.strip().upper(),
        effect=payload.effect,
        principal_type=payload.principal_type,
        principal_value=principal_value,
        conditions_json=dict(payload.conditions),
        priority=payload.priority,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=record.id,
        event_type="access_policy.created",
        actor_user_id=str(current_user.id),
        metadata={"policy_id": row.id, "action": row.action, "effect": row.effect, "principal_type": row.principal_type},
    )
    audit(db, tenant, request, "document.warehouse.access_policy_created", "warehouse_access_policy", row.id, {
        "content_record_id": record.id,
        "action": row.action,
        "effect": row.effect,
        "principal_type": row.principal_type,
    })
    db.commit()
    return {"id": row.id, "action": row.action, "effect": row.effect}


@router.post("/t/{tenant_slug}/warehouse/resources/{record_id}/versions/{version_id}/acknowledge")
def acknowledge_warehouse_version(
    tenant_slug: str,
    record_id: str,
    version_id: str,
    payload: WarehouseAcknowledgementCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    record = _resource(db, str(tenant.amo_id), record_id)
    if not _source_visible(db, tenant=tenant, user=current_user, row=record):
        raise HTTPException(status_code=403, detail="This warehouse resource is outside your authorized scope")
    version = (
        db.query(wm.WarehouseContentVersion)
        .filter(
            wm.WarehouseContentVersion.tenant_id == tenant.amo_id,
            wm.WarehouseContentVersion.id == version_id,
            wm.WarehouseContentVersion.content_record_id == record.id,
        )
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Warehouse version not found")

    existing = (
        db.query(wm.WarehouseAcknowledgement)
        .filter(
            wm.WarehouseAcknowledgement.tenant_id == tenant.amo_id,
            wm.WarehouseAcknowledgement.content_version_id == version.id,
            wm.WarehouseAcknowledgement.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        return {
            "id": existing.id,
            "acknowledged_at": existing.acknowledged_at.isoformat() if existing.acknowledged_at else None,
            "already_acknowledged": True,
        }

    acknowledgement = wm.WarehouseAcknowledgement(
        tenant_id=tenant.amo_id,
        content_record_id=record.id,
        content_version_id=version.id,
        user_id=current_user.id,
        file_hash=version.file_hash,
        acknowledgement_method=payload.method.strip().upper(),
        session_metadata_json=dict(payload.session_metadata),
    )
    db.add(acknowledgement)
    db.flush()
    warehouse.record_event(
        db,
        tenant_id=str(tenant.amo_id),
        content_record_id=record.id,
        content_version_id=version.id,
        event_type="acknowledgement.completed",
        actor_user_id=str(current_user.id),
        metadata={"acknowledgement_id": acknowledgement.id, "file_hash": version.file_hash},
    )
    audit(db, tenant, request, "document.warehouse.acknowledged", "warehouse_content_version", version.id, {
        "content_record_id": record.id,
        "file_hash": version.file_hash,
        "method": acknowledgement.acknowledgement_method,
    })
    db.commit()
    return {
        "id": acknowledgement.id,
        "acknowledged_at": acknowledgement.acknowledged_at.isoformat() if acknowledgement.acknowledged_at else None,
        "already_acknowledged": False,
    }


@router.post("/t/{tenant_slug}/warehouse/locations", status_code=201)
def create_warehouse_location(
    tenant_slug: str,
    payload: WarehouseLocationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    code = payload.code.strip().upper()
    if db.query(wm.WarehouseLocation.id).filter(
        wm.WarehouseLocation.tenant_id == tenant.amo_id,
        wm.WarehouseLocation.code == code,
    ).first():
        raise HTTPException(status_code=409, detail="Warehouse location code already exists")
    if payload.parent_id and not db.query(wm.WarehouseLocation.id).filter(
        wm.WarehouseLocation.tenant_id == tenant.amo_id,
        wm.WarehouseLocation.id == payload.parent_id,
    ).first():
        raise HTTPException(status_code=422, detail="Parent location does not belong to this tenant")
    row = wm.WarehouseLocation(
        tenant_id=tenant.amo_id,
        code=code,
        name=payload.name.strip(),
        location_type=payload.location_type.strip().upper(),
        parent_id=payload.parent_id,
        path_text=payload.path_text.strip(),
        metadata_json=dict(payload.metadata),
    )
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.warehouse.location_created", "warehouse_location", row.id, {
        "code": row.code,
        "path": row.path_text,
    })
    db.commit()
    return {"id": row.id, "code": row.code, "name": row.name, "path_text": row.path_text}


@router.get("/t/{tenant_slug}/warehouse/audit")
def warehouse_audit(
    tenant_slug: str,
    record_id: str | None = None,
    event_type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(wm.WarehouseAuditEvent).filter(wm.WarehouseAuditEvent.tenant_id == tenant.amo_id)
    if record_id:
        query = query.filter(wm.WarehouseAuditEvent.content_record_id == record_id)
    if event_type:
        query = query.filter(wm.WarehouseAuditEvent.event_type == event_type.strip())
    rows = query.order_by(wm.WarehouseAuditEvent.created_at.desc()).limit(limit).all()
    return {"items": [{
        "id": row.id,
        "content_record_id": row.content_record_id,
        "content_version_id": row.content_version_id,
        "item_copy_id": row.item_copy_id,
        "event_type": row.event_type,
        "actor_user_id": row.actor_user_id,
        "transaction_id": row.transaction_id,
        "metadata": dict(row.metadata_json or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]}
