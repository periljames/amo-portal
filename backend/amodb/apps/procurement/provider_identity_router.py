"""Descriptive provider metadata only: never makes a supplier eligible for operational use."""
from __future__ import annotations

from datetime import date
import json
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as accounts
from amodb.apps.quality.tenant_security import set_postgres_tenant_context
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from . import service

router = APIRouter(
    prefix="/api/maintenance/{amo_code}/procurement",
    tags=["external provider identity"],
    dependencies=[Depends(require_module("finance_inventory"))],
)
_EDIT_ROLES = (accounts.AccountRole.PROCUREMENT_OFFICER, accounts.AccountRole.STORES_MANAGER,
               accounts.AccountRole.QUALITY_MANAGER)
_COLUMNS = {
    "roles": ("role_code", "notes"),
    "sites": ("site_code", "site_name", "country", "address", "is_primary"),
    "contacts": ("contact_name", "email", "phone", "assignment", "site_id"),
    "capabilities": ("site_id", "capability_type", "description", "manufacturer",
                     "product_family", "aircraft_type", "engine_type", "component_part_number",
                     "service_code", "rating", "limitations", "regulatory_authority",
                     "certificate_number", "valid_until", "evidence_id"),
    "source-links": ("source_system", "source_identifier", "source_row",
                     "source_digest", "imported_at"),
    "certificates": ("certificate_type", "certificate_number", "issuing_authority", "jurisdiction",
                     "approval_rating", "limitations", "valid_from", "valid_until", "evidence_id"),
    "relationships": ("parent_supplier_id", "contract_id", "relationship_kind", "function_scope",
                      "consent_evidence_id", "consent_expires_on"),
    "account-links": ("user_id", "contact_id", "requested_scopes"),
    "scope-links": ("approval_scope_id", "site_id", "contracted_function", "service_category", "product_family"),
}
_TABLES = {
    "roles": "external_provider_roles",
    "sites": "external_provider_sites",
    "contacts": "external_provider_contacts",
    "capabilities": "external_provider_capabilities",
    "source-links": "external_provider_source_links",
    "certificates": "external_provider_certificates",
    "relationships": "external_provider_relationships",
    "account-links": "external_provider_account_links",
    "scope-links": "external_provider_scope_links",
}
_REQUIRED = {
    "roles": {"role_code"}, "sites": {"site_code", "site_name"},
    "contacts": {"contact_name", "assignment"},
    "capabilities": {"capability_type", "description"},
    "source-links": {"source_system", "source_identifier"},
    "certificates": {"certificate_type", "certificate_number"},
    "relationships": {"parent_supplier_id", "relationship_kind", "function_scope"},
    "account-links": {"user_id"},
    "scope-links": {"approval_scope_id"},
}
_READ_ONLY = {"source-links"}
_QUALITY_ONLY = {"relationships", "account-links", "scope-links"}
_ALLOWED_ROLES = {"SUPPLIER", "VENDOR", "CONTRACTOR", "SUBCONTRACTOR", "SERVICE_PROVIDER",
                  "LABORATORY", "CALIBRATION_PROVIDER", "CONSULTANT", "OTHER"}
_ALLOWED_ASSIGNMENTS = {"COMMERCIAL", "TECHNICAL", "QUALITY", "OTHER"}

class ProviderIdentityWrite(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)

def _tenant(db: Session, amo_code: str, user: accounts.User) -> str:
    amo_id = service.resolve_tenant_amo_id(db, amo_code=amo_code, current_user=user)
    set_postgres_tenant_context(db, amo_id=amo_id, user_id=str(user.id))
    return amo_id

def _require_supplier(db: Session, amo_id: str, supplier_id: int) -> None:
    found = db.execute(text("SELECT 1 FROM procurement_suppliers WHERE amo_id=:tenant AND id=:supplier"),
                       {"tenant": amo_id, "supplier": supplier_id}).scalar()
    if found is None:
        raise HTTPException(404, "Supplier not found in this tenant.")

def _clean(kind: str, values: dict[str, Any], *, creation: bool) -> dict[str, Any]:
    if kind not in _COLUMNS:
        raise HTTPException(404, "Unknown resource.")
    unexpected = set(values) - set(_COLUMNS[kind])
    if unexpected:
        raise HTTPException(422, f"Unsupported fields: {', '.join(sorted(unexpected))}")
    if creation and (_REQUIRED[kind] - {key for key, val in values.items() if val is not None and val != ""}):
        raise HTTPException(422, "Required provider fields are missing.")
    size_limits = {"role_code":64,"site_code":64,"site_name":255,"country":80,
                   "contact_name":255,"email":255,"phone":80,"assignment":32,
                   "capability_type":64,"manufacturer":255,"product_family":255,
                   "rating":255,"regulatory_authority":128,"certificate_number":160,
                   "certificate_type":80,"issuing_authority":160,"jurisdiction":80,
                   "approval_rating":255,"relationship_kind":32,"contracted_function":128,
                   "service_category":128,"aircraft_type":128,"engine_type":128,
                   "component_part_number":128,"service_code":128}
    for field,maximum in size_limits.items():
        if field in values and values[field] is not None and len(str(values[field]))>maximum:
            raise HTTPException(422, field + " exceeds allowed length.")
    if "role_code" in values and values["role_code"] not in _ALLOWED_ROLES:
        raise HTTPException(422, "Unsupported provider role.")
    if "assignment" in values and values["assignment"] not in _ALLOWED_ASSIGNMENTS:
        raise HTTPException(422, "Unsupported contact assignment.")
    for field in ("valid_from", "valid_until", "consent_expires_on"):
        if field in values and values[field] not in (None, ""):
            try:
                values[field] = date.fromisoformat(str(values[field]))
            except (TypeError, ValueError) as exc:
                raise HTTPException(422, field + " must be ISO date.") from exc
    if values.get("relationship_kind") not in (None, "PARENT", "FURTHER_SUBCONTRACTOR", "AFFILIATE"):
        raise HTTPException(422, "Unsupported provider relationship.")
    if "requested_scopes" in values and not isinstance(values["requested_scopes"], list):
        raise HTTPException(422, "Requested scopes must be an array.")
    if "is_primary" in values and not isinstance(values["is_primary"], bool):
        raise HTTPException(422, "is_primary must be boolean.")
    if "requested_scopes" in values:
        values["requested_scopes"] = json.dumps(values["requested_scopes"])
    return values

def _site_guard(db: Session, amo_id: str, supplier_id: int, values: dict[str, Any]) -> None:
    site_id = values.get("site_id")
    if site_id is None:
        return
    match = db.execute(text("""SELECT 1 FROM external_provider_sites
                             WHERE amo_id=:tenant AND supplier_id=:supplier AND id=:id"""),
                       {"tenant": amo_id, "supplier": supplier_id, "id": site_id}).scalar()
    if not match:
        raise HTTPException(422, "Site must belong to the same provider and tenant.")

def _evidence_guard(db: Session, amo_id: str, supplier_id: int, values: dict[str, Any]) -> None:
    evidence_id = values.get("evidence_id")
    if evidence_id is None:
        return
    match = db.execute(text("""SELECT 1 FROM quality_external_provider_evidence
                             WHERE amo_id=:tenant AND supplier_id=:supplier AND id=:id"""),
                       {"tenant": amo_id, "supplier": supplier_id, "id": evidence_id}).scalar()
    if not match:
        raise HTTPException(422, "Evidence must belong to the same provider and tenant.")

def _check_references(db: Session, tenant: str, supplier_id: int, kind: str,
                      values: dict[str, Any]) -> None:
    _check_references(db, tenant, supplier_id, kind, values)
    for field, table, restricted in (
        ("parent_supplier_id", "procurement_suppliers", False),
        ("user_id", "users", False),
        ("contact_id", "external_provider_contacts", True),
        ("approval_scope_id", "procurement_supplier_approval_scopes", True),
    ):
        identifier = values.get(field)
        if identifier is None:
            continue
        qualifier = " AND supplier_id=:supplier" if restricted else ""
        match = db.execute(text("SELECT 1 FROM " + table +
                                " WHERE amo_id=:tenant AND id=:id" + qualifier),
                           {"tenant":tenant,"id":identifier,"supplier":supplier_id}).scalar()
        if not match:
            raise HTTPException(422, field + " must belong to this tenant/provider.")
    if values.get("parent_supplier_id") == supplier_id:
        raise HTTPException(422, "A provider cannot be its own parent.")
    if values.get("contract_id"):
        if not values.get("parent_supplier_id"):
            raise HTTPException(422, "Parent provider must accompany a contract link.")
        ok = db.execute(text("""SELECT 1 FROM quality_external_provider_contracts
             WHERE amo_id=:tenant AND supplier_id=:parent AND id=:id"""),
             {"tenant":tenant,"parent":values["parent_supplier_id"],"id":values["contract_id"]}).scalar()
        if not ok:
            raise HTTPException(422, "Contract is not owned by the parent provider.")
    if values.get("consent_evidence_id"):
        if not values.get("parent_supplier_id"):
            raise HTTPException(422, "Parent provider is required for consent evidence.")
        ok = db.execute(text("""SELECT 1 FROM quality_external_provider_evidence
             WHERE amo_id=:tenant AND supplier_id=:parent AND id=:id"""),
             {"tenant":tenant,"parent":values["parent_supplier_id"],
              "id":values["consent_evidence_id"]}).scalar()
        if not ok:
            raise HTTPException(422, "Consent evidence does not belong to the parent provider.")

def _audit_change(db: Session, tenant: str, supplier_id: int, record_id: str,
                  kind: str, actor: str, action: str, changes: dict[str, Any]) -> None:
    db.execute(text("""INSERT INTO external_provider_change_events
        (id,amo_id,supplier_id,event_type,actor_user_id,source_system,source_identifier,after_json)
        VALUES (:id,:amo,:supplier,:action,:actor,'PORTAL',:source,CAST(:payload AS JSON))"""),
        {"id":str(uuid4()),"amo":tenant,"supplier":supplier_id,"action":action,
         "actor":actor,"source":record_id,"payload":json.dumps(changes,default=str)})
    service._event(db,amo_id=tenant,entity_type="ExternalProviderMetadata",
                   entity_id=record_id,action=action,actor_user_id=actor,
                   detail={"supplier_id":supplier_id,"kind":kind})

@router.get("/suppliers/{supplier_id}/identity/{kind}")
def list_identity(amo_code: str, supplier_id: int, kind: str,
                  limit: int = Query(200, ge=1, le=500),
                  db: Session = Depends(get_db),
                  current_user: accounts.User = Depends(get_current_active_user)):
    if kind not in _TABLES:
        raise HTTPException(404, "Unknown resource.")
    tenant = _tenant(db, amo_code, current_user)
    _require_supplier(db, tenant, supplier_id)
    rows = db.execute(text(f"""SELECT * FROM {_TABLES[kind]}
                             WHERE amo_id=:tenant AND supplier_id=:supplier
                             ORDER BY created_at, id LIMIT :limit"""),
                      {"tenant": tenant, "supplier": supplier_id, "limit": limit}).mappings()
    return [dict(row) for row in rows]

@router.post("/suppliers/{supplier_id}/identity/{kind}", status_code=201)
def create_identity(amo_code: str, supplier_id: int, kind: str, payload: ProviderIdentityWrite,
                    db: Session = Depends(get_db),
                    current_user: accounts.User = Depends(require_roles(*_EDIT_ROLES))):
    if kind not in _TABLES or kind in _READ_ONLY:
        raise HTTPException(404, "Unsupported resource.")
    if kind in _QUALITY_ONLY and current_user.role != accounts.AccountRole.QUALITY_MANAGER:
        raise HTTPException(403, "Quality Manager authorization required.")
    tenant = _tenant(db, amo_code, current_user)
    _require_supplier(db, tenant, supplier_id)
    values = _clean(kind, dict(payload.fields), creation=True)
    _site_guard(db, tenant, supplier_id, values)
    _evidence_guard(db, tenant, supplier_id, values)
    record_id = str(uuid4())
    columns = ["id", "amo_id", "supplier_id", *values]
    params = {"id": record_id, "amo_id": tenant, "supplier_id": supplier_id, **values}
    try:
        db.execute(text(f"""INSERT INTO {_TABLES[kind]} ({', '.join(columns)})
                      VALUES ({', '.join('CAST(:'+c+' AS JSON)' if c=='requested_scopes' else ':'+c for c in columns)})"""), params)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Duplicate or conflicting provider metadata.") from exc
    _audit_change(db,tenant,supplier_id,record_id,kind,str(current_user.id),
                  "create_"+kind,{"fields":values})
    row = db.execute(text(f"SELECT * FROM {_TABLES[kind]} WHERE id=:id AND amo_id=:tenant"),
                     {"id": record_id, "tenant": tenant}).mappings().one()
    db.commit()
    return dict(row)

@router.patch("/suppliers/{supplier_id}/identity/{kind}/{record_id}")
def update_identity(amo_code: str, supplier_id: int, kind: str, record_id: str,
                    payload: ProviderIdentityWrite,
                    db: Session = Depends(get_db),
                    current_user: accounts.User = Depends(require_roles(*_EDIT_ROLES))):
    if kind not in _TABLES or kind in _READ_ONLY:
        raise HTTPException(404, "Unsupported resource.")
    if kind in _QUALITY_ONLY and current_user.role != accounts.AccountRole.QUALITY_MANAGER:
        raise HTTPException(403, "Quality Manager authorization required.")
    if payload.expected_version is None:
        raise HTTPException(428, "expected_version is required.")
    tenant = _tenant(db, amo_code, current_user)
    _require_supplier(db, tenant, supplier_id)
    values = _clean(kind, dict(payload.fields), creation=False)
    if not values:
        raise HTTPException(422, "No changes supplied.")
    _site_guard(db, tenant, supplier_id, values)
    _evidence_guard(db, tenant, supplier_id, values)
    assignments = ", ".join(f"{key}=CAST(:{key} AS JSON)" if key=="requested_scopes"
                            else f"{key}=:{key}" for key in values)
    if kind=="certificates":
        assignments += ", verification_state='UNVERIFIED', verified_by_user_id=NULL, verified_at=NULL"
    if kind=="relationships":
        assignments += ", consent_state='PENDING'"
    if kind=="account-links":
        assignments += ", account_state='PENDING', authorized_by_user_id=NULL, authorized_at=NULL"
    try:
        row = db.execute(text(f"""UPDATE {_TABLES[kind]} SET {assignments},
                         version=version+1, updated_at=now()
                         WHERE amo_id=:tenant AND supplier_id=:supplier
                         AND id=:id AND version=:version RETURNING *"""),
                     {**values, "tenant": tenant, "supplier": supplier_id,
                      "id": record_id, "version": payload.expected_version}).mappings().first()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Duplicate or conflicting provider details.") from exc
    if row is None:
        raise HTTPException(409, "Record not found or stale version. Refresh and retry.")
    _audit_change(db,tenant,supplier_id,record_id,kind,str(current_user.id),
                  "update_"+kind,{"fields":values,"version":row["version"]})
    db.commit()
    return dict(row)

class ProviderGovernanceDecision(BaseModel):
    action: str
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=2000)

@router.post("/suppliers/{supplier_id}/identity/{kind}/{record_id}/governance")
def decide_metadata(amo_code: str, supplier_id: int, kind: str, record_id: str,
                    payload: ProviderGovernanceDecision,
                    db: Session = Depends(get_db),
                    current_user: accounts.User = Depends(require_roles(accounts.AccountRole.QUALITY_MANAGER))):
    columns = {
        "certificates": ("verification_state", {
            "VERIFY": "VERIFIED", "REJECT": "REJECTED", "SUPERSEDE": "SUPERSEDED"}),
        "relationships": ("consent_state", {
            "VERIFY": "VERIFIED", "REVOKE": "REVOKED"}),
        "account-links": ("account_state", {
            "VERIFY": "VERIFIED", "REVOKE": "REVOKED"}),
    }
    if kind not in columns:
        raise HTTPException(404, "Unsupported governance decision.")
    status_column, allowed = columns[kind]
    if payload.action not in allowed:
        raise HTTPException(422, "Unsupported governance action.")
    tenant = _tenant(db, amo_code, current_user)
    _require_supplier(db, tenant, supplier_id)
    table = _TABLES[kind]
    row = db.execute(text("SELECT * FROM " + table +
         " WHERE amo_id=:tenant AND supplier_id=:supplier AND id=:id FOR UPDATE"),
         {"tenant":tenant,"supplier":supplier_id,"id":record_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Provider record not found.")
    if row["version"] != payload.expected_version:
        raise HTTPException(409, "Record has changed; refresh and retry.")
    target = allowed[payload.action]
    if row[status_column] == target:
        raise HTTPException(409, "Record already in the requested state.")
    if payload.action == "VERIFY" and kind == "certificates":
        if not row["evidence_id"]:
            raise HTTPException(409, "Link verified documentary evidence before certification.")
        verified = db.execute(text("""SELECT 1 FROM quality_external_provider_evidence
            WHERE amo_id=:tenant AND supplier_id=:supplier AND id=:evidence
            AND status='VERIFIED' AND (valid_until IS NULL OR valid_until >= :today)"""),
            {"tenant":tenant,"supplier":supplier_id,"evidence":row["evidence_id"],
             "today":date.today()}).scalar()
        if not verified or (row["valid_until"] and row["valid_until"] < date.today()):
            raise HTTPException(409, "Evidence or certificate is expired or unverified.")
    if payload.action == "VERIFY" and kind == "relationships":
        if not row["consent_evidence_id"]:
            raise HTTPException(409, "Written consent evidence is required.")
        verified = db.execute(text("""SELECT 1 FROM quality_external_provider_evidence
            WHERE amo_id=:tenant AND supplier_id=:parent AND id=:evidence
            AND status='VERIFIED' AND (valid_until IS NULL OR valid_until >= :today)"""),
            {"tenant":tenant,"parent":row["parent_supplier_id"],
             "evidence":row["consent_evidence_id"],"today":date.today()}).scalar()
        if not verified or (row["consent_expires_on"] and row["consent_expires_on"] < date.today()):
            raise HTTPException(409, "Written subcontracting consent is not current and verified.")
        if row["relationship_kind"] == "FURTHER_SUBCONTRACTOR":
            current = db.execute(text("""SELECT 1 FROM quality_external_provider_contracts
                WHERE amo_id=:tenant AND supplier_id=:parent AND id=:contract
                AND status='ACTIVE'
                AND (effective_on IS NULL OR effective_on <= :today)
                AND (expires_on IS NULL OR expires_on >= :today)"""),
                {"tenant":tenant,"parent":row["parent_supplier_id"],
                 "contract":row["contract_id"],"today":date.today()}).scalar()
            if not current:
                raise HTTPException(409, "Current parent contract required for further subcontracting.")
    updates = status_column + "=:target, version=version+1, updated_at=NOW()"
    params = {"tenant":tenant,"supplier":supplier_id,"id":record_id,
              "target":target,"version":payload.expected_version,"actor":str(current_user.id)}
    if kind == "certificates":
        updates += ", verified_by_user_id=:actor, verified_at=NOW()"
    if kind == "account-links":
        updates += ", authorized_by_user_id=:actor, authorized_at=NOW()"
    updated = db.execute(text("UPDATE " + table + " SET " + updates +
        " WHERE amo_id=:tenant AND supplier_id=:supplier AND id=:id AND version=:version RETURNING *"),
        params).mappings().first()
    if updated is None:
        raise HTTPException(409, "Concurrent governance change.")
    _audit_change(db,tenant,supplier_id,record_id,kind,str(current_user.id),
                  "governance_"+payload.action.lower(),
                  {"from":row[status_column],"to":target,"reason":payload.reason})
    db.commit()
    return dict(updated)
