from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_read_db, get_write_db

from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)


provider_governance_router = APIRouter()

ProviderKind = Literal[
    "SUPPLIER",
    "CONTRACTOR",
    "SUBCONTRACTOR",
    "SERVICE_PROVIDER",
    "CONSULTANT",
    "LABORATORY",
    "CALIBRATION_PROVIDER",
    "OTHER",
]
ProviderStatus = Literal[
    "PROSPECTIVE",
    "UNDER_REVIEW",
    "CONDITIONALLY_APPROVED",
    "APPROVED",
    "RESTRICTED",
    "SUSPENDED",
    "EXPIRED",
    "REJECTED",
    "ARCHIVED",
]
ProviderRisk = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ContractStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "EXPIRED", "TERMINATED", "SUPERSEDED"]
EvidenceStatus = Literal["PENDING", "VERIFIED", "EXPIRED", "REJECTED", "SUPERSEDED"]

_PROVIDER_TABLES = (
    "procurement_suppliers",
    "quality_external_provider_profiles",
    "quality_external_provider_contracts",
    "quality_external_provider_evidence",
)

_PROVIDER_TRANSITIONS: dict[str, set[str]] = {
    "PROSPECTIVE": {"UNDER_REVIEW", "REJECTED", "ARCHIVED"},
    "UNDER_REVIEW": {"CONDITIONALLY_APPROVED", "APPROVED", "RESTRICTED", "REJECTED", "ARCHIVED"},
    "CONDITIONALLY_APPROVED": {"APPROVED", "RESTRICTED", "SUSPENDED", "EXPIRED", "ARCHIVED"},
    "APPROVED": {"RESTRICTED", "SUSPENDED", "EXPIRED", "ARCHIVED"},
    "RESTRICTED": {"APPROVED", "SUSPENDED", "EXPIRED", "ARCHIVED"},
    "SUSPENDED": {"UNDER_REVIEW", "APPROVED", "RESTRICTED", "ARCHIVED"},
    "EXPIRED": {"UNDER_REVIEW", "ARCHIVED"},
    "REJECTED": {"UNDER_REVIEW", "ARCHIVED"},
    "ARCHIVED": set(),
}

_CONTRACT_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"ACTIVE", "TERMINATED", "SUPERSEDED"},
    "ACTIVE": {"SUSPENDED", "EXPIRED", "TERMINATED", "SUPERSEDED"},
    "SUSPENDED": {"ACTIVE", "TERMINATED", "SUPERSEDED"},
    "EXPIRED": {"SUPERSEDED"},
    "TERMINATED": set(),
    "SUPERSEDED": set(),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _now().date()


def _require_tables(db: Session) -> None:
    inspector = inspect(db.get_bind())
    missing = [table_name for table_name in _PROVIDER_TABLES if not inspector.has_table(table_name)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "External provider governance is not migrated on this database.",
                "missing_tables": missing,
            },
        )


def _row_dict(row) -> dict[str, Any]:
    return dict(row._mapping) if row is not None else {}


def _normalise_provider_kind(value: str | None) -> str:
    raw = str(value or "SUPPLIER").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "VENDOR": "SUPPLIER",
        "SERVICE": "SERVICE_PROVIDER",
        "LAB": "LABORATORY",
        "CALIBRATION": "CALIBRATION_PROVIDER",
    }
    return aliases.get(raw, raw)


def _effective_contract_status(row: dict[str, Any]) -> str:
    stored = str(row.get("status") or "DRAFT").upper()
    expires_on = row.get("expires_on")
    if stored == "ACTIVE" and isinstance(expires_on, date) and expires_on < _today():
        return "EXPIRED"
    return stored


def _effective_evidence_status(row: dict[str, Any]) -> str:
    stored = str(row.get("status") or "PENDING").upper()
    valid_until = row.get("valid_until")
    if stored == "VERIFIED" and isinstance(valid_until, date) and valid_until < _today():
        return "EXPIRED"
    return stored


def _serialize_contract(row) -> dict[str, Any]:
    item = _row_dict(row)
    item["effective_status"] = _effective_contract_status(item)
    return item


def _serialize_evidence(row) -> dict[str, Any]:
    item = _row_dict(row)
    item["effective_status"] = _effective_evidence_status(item)
    return item


def _provider_row(db: Session, *, amo_id: str, provider_id: int, lock: bool = False):
    suffix = " FOR UPDATE" if lock and db.get_bind().dialect.name == "postgresql" else ""
    return db.execute(
        text(
            f"""
            SELECT
                s.id,
                s.amo_id,
                s.supplier_code,
                s.legal_name,
                s.trading_name,
                s.supplier_type,
                s.qms_supplier_id,
                CAST(s.status AS TEXT) AS status,
                CAST(s.risk_level AS TEXT) AS risk_level,
                s.email,
                s.phone,
                s.website,
                s.country,
                s.physical_address,
                s.quality_contact_name,
                s.quality_contact_email,
                s.notes,
                s.is_active,
                s.approved_at,
                s.approved_by_user_id,
                s.suspended_at,
                s.suspended_by_user_id,
                s.suspension_reason,
                s.created_at,
                s.updated_at,
                p.id AS profile_id,
                p.provider_kind,
                p.contract_required,
                p.oversight_owner_user_id,
                p.review_interval_days,
                p.last_reviewed_on,
                p.next_review_due_on,
                p.scope_summary,
                p.quality_requirements,
                p.version AS governance_version
            FROM procurement_suppliers s
            LEFT JOIN quality_external_provider_profiles p
              ON p.amo_id = s.amo_id AND p.supplier_id = s.id
            WHERE s.amo_id = :amo_id AND s.id = :provider_id
            {suffix}
            """
        ),
        {"amo_id": amo_id, "provider_id": provider_id},
    ).mappings().first()


def _provider_or_404(db: Session, *, amo_id: str, provider_id: int, lock: bool = False) -> dict[str, Any]:
    row = _provider_row(db, amo_id=amo_id, provider_id=provider_id, lock=lock)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External provider was not found in this tenant.")
    item = dict(row)
    item["provider_kind"] = _normalise_provider_kind(item.get("provider_kind") or item.get("supplier_type"))
    item["contract_required"] = bool(item.get("contract_required"))
    item["governance_version"] = int(item.get("governance_version") or 0)
    return item


def _ensure_profile(db: Session, *, ctx: TenantContext, provider: dict[str, Any]) -> dict[str, Any]:
    if provider.get("profile_id"):
        return provider
    profile_id = str(uuid.uuid4())
    provider_kind = _normalise_provider_kind(provider.get("supplier_type"))
    db.execute(
        text(
            """
            INSERT INTO quality_external_provider_profiles (
                id, amo_id, supplier_id, provider_kind, contract_required,
                review_interval_days, version, created_by_user_id, updated_by_user_id,
                created_at, updated_at
            ) VALUES (
                :id, :amo_id, :supplier_id, :provider_kind, FALSE,
                365, 1, :actor, :actor, NOW(), NOW()
            )
            """
        ),
        {
            "id": profile_id,
            "amo_id": ctx.amo_id,
            "supplier_id": provider["id"],
            "provider_kind": provider_kind,
            "actor": ctx.user_id,
        },
    )
    provider["profile_id"] = profile_id
    provider["provider_kind"] = provider_kind
    provider["contract_required"] = False
    provider["review_interval_days"] = 365
    provider["governance_version"] = 1
    return provider


def _assert_expected_version(provider: dict[str, Any], expected_version: int) -> None:
    current = int(provider.get("governance_version") or 0)
    if current != int(expected_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "External provider governance changed after it was loaded. Refresh and review the current record.",
                "expected_version": expected_version,
                "current_version": current,
            },
        )


def _active_contract_exists(db: Session, *, amo_id: str, provider_id: int) -> bool:
    today = _today()
    return bool(
        db.execute(
            text(
                """
                SELECT 1
                FROM quality_external_provider_contracts
                WHERE amo_id = :amo_id
                  AND supplier_id = :provider_id
                  AND status = 'ACTIVE'
                  AND (effective_on IS NULL OR effective_on <= :today)
                  AND (expires_on IS NULL OR expires_on >= :today)
                LIMIT 1
                """
            ),
            {"amo_id": amo_id, "provider_id": provider_id, "today": today},
        ).first()
    )


def _active_scope_exists(db: Session, *, amo_id: str, provider_id: int) -> bool:
    return bool(
        db.execute(
            text(
                """
                SELECT 1
                FROM procurement_supplier_approval_scopes
                WHERE amo_id = :amo_id
                  AND supplier_id = :provider_id
                  AND CAST(status AS TEXT) = 'ACTIVE'
                  AND (effective_on IS NULL OR effective_on <= :today)
                  AND (expires_on IS NULL OR expires_on >= :today)
                LIMIT 1
                """
            ),
            {"amo_id": amo_id, "provider_id": provider_id, "today": _today()},
        ).first()
    )


def _provider_contracts(db: Session, *, amo_id: str, provider_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id, supplier_id, contract_number, title, status, scope_text,
                   effective_on, expires_on, termination_notice_days, renewal_terms,
                   controlled_document_id, controlled_document_revision, owner_user_id,
                   approved_by_user_id, approved_at, transition_reason, version,
                   created_at, updated_at
            FROM quality_external_provider_contracts
            WHERE amo_id = :amo_id AND supplier_id = :provider_id
            ORDER BY COALESCE(expires_on, DATE '9999-12-31') ASC, created_at DESC
            """
        ),
        {"amo_id": amo_id, "provider_id": provider_id},
    ).all()
    return [_serialize_contract(row) for row in rows]


def _provider_evidence(db: Session, *, amo_id: str, provider_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id, supplier_id, contract_id, evidence_type, source_system, source_id,
                   title, status, valid_from, valid_until, verified_by_user_id, verified_at,
                   notes, created_at, updated_at
            FROM quality_external_provider_evidence
            WHERE amo_id = :amo_id AND supplier_id = :provider_id
            ORDER BY COALESCE(valid_until, DATE '9999-12-31') ASC, created_at DESC
            """
        ),
        {"amo_id": amo_id, "provider_id": provider_id},
    ).all()
    return [_serialize_evidence(row) for row in rows]


def _provider_scopes(db: Session, *, amo_id: str, provider_id: int) -> list[dict[str, Any]]:
    if not inspect(db.get_bind()).has_table("procurement_supplier_approval_scopes"):
        return []
    return [
        dict(row._mapping)
        for row in db.execute(
            text(
                """
                SELECT id, site_code, category, product_family, manufacturer, authority,
                       approval_number, CAST(status AS TEXT) AS status, effective_on, expires_on,
                       restrictions, incoming_inspection_level, evidence_reference,
                       qms_evaluation_id, qms_audit_id, approved_by_user_id, approved_at
                FROM procurement_supplier_approval_scopes
                WHERE amo_id = :amo_id AND supplier_id = :provider_id
                ORDER BY category ASC, product_family ASC, id ASC
                """
            ),
            {"amo_id": amo_id, "provider_id": provider_id},
        ).all()
    ]


def _provider_detail(db: Session, *, ctx: TenantContext, provider_id: int) -> dict[str, Any]:
    provider = _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    contracts = _provider_contracts(db, amo_id=ctx.amo_id, provider_id=provider_id)
    evidence = _provider_evidence(db, amo_id=ctx.amo_id, provider_id=provider_id)
    scopes = _provider_scopes(db, amo_id=ctx.amo_id, provider_id=provider_id)
    provider["approval_scopes"] = scopes
    provider["contracts"] = contracts
    provider["evidence"] = evidence
    provider["active_contract_count"] = sum(item["effective_status"] == "ACTIVE" for item in contracts)
    provider["verified_evidence_count"] = sum(item["effective_status"] == "VERIFIED" for item in evidence)
    provider["active_scope_count"] = sum(str(item.get("status") or "") == "ACTIVE" for item in scopes)
    provider["review_due"] = bool(
        provider.get("next_review_due_on") and provider["next_review_due_on"] <= _today()
    )
    provider["allowed_transitions"] = sorted(_PROVIDER_TRANSITIONS.get(str(provider.get("status") or ""), set()))
    return provider


class ProviderCreate(BaseModel):
    supplier_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    legal_name: str = Field(min_length=2, max_length=255)
    trading_name: str | None = Field(default=None, max_length=255)
    provider_kind: ProviderKind = "SUPPLIER"
    risk_level: ProviderRisk = "MEDIUM"
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    website: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=64)
    physical_address: str | None = None
    quality_contact_name: str | None = Field(default=None, max_length=255)
    quality_contact_email: EmailStr | None = None
    default_currency: str = Field(default="USD", min_length=3, max_length=8)
    contract_required: bool = False
    oversight_owner_user_id: str | None = None
    review_interval_days: int = Field(default=365, ge=30, le=3650)
    next_review_due_on: date | None = None
    scope_summary: str | None = None
    quality_requirements: str | None = None
    notes: str | None = None


class ProviderProfilePatch(BaseModel):
    expected_version: int = Field(ge=1)
    provider_kind: ProviderKind | None = None
    risk_level: ProviderRisk | None = None
    contract_required: bool | None = None
    oversight_owner_user_id: str | None = None
    review_interval_days: int | None = Field(default=None, ge=30, le=3650)
    last_reviewed_on: date | None = None
    next_review_due_on: date | None = None
    scope_summary: str | None = None
    quality_requirements: str | None = None
    reason: str = Field(min_length=8, max_length=1000)


class ProviderTransition(BaseModel):
    expected_version: int = Field(ge=1)
    target_status: ProviderStatus
    reason: str = Field(min_length=8, max_length=2000)


class ContractCreate(BaseModel):
    contract_number: str = Field(min_length=2, max_length=128)
    title: str = Field(min_length=2, max_length=255)
    scope_text: str = Field(min_length=3)
    effective_on: date | None = None
    expires_on: date | None = None
    termination_notice_days: int | None = Field(default=None, ge=0, le=3650)
    renewal_terms: str | None = None
    controlled_document_id: str | None = Field(default=None, max_length=64)
    controlled_document_revision: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "ContractCreate":
        if self.effective_on and self.expires_on and self.expires_on < self.effective_on:
            raise ValueError("Contract expiry cannot be before its effective date.")
        return self


class ContractTransition(BaseModel):
    expected_version: int = Field(ge=1)
    target_status: ContractStatus
    reason: str = Field(min_length=8, max_length=2000)


class EvidenceCreate(BaseModel):
    evidence_type: str = Field(min_length=2, max_length=64)
    source_system: str = Field(default="DOCUMENT_CONTROL", min_length=2, max_length=64)
    source_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=2, max_length=255)
    contract_id: str | None = Field(default=None, max_length=36)
    valid_from: date | None = None
    valid_until: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "EvidenceCreate":
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("Evidence validity end cannot be before its start date.")
        return self


class EvidenceDecision(BaseModel):
    target_status: EvidenceStatus
    reason: str = Field(min_length=8, max_length=2000)


@provider_governance_router.get("/suppliers/governance")
def provider_governance_summary(
    ctx: TenantContext = Depends(require_quality_permission("qms.supplier.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _require_tables(db)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = _today()
    horizon = today + timedelta(days=60)
    row = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE s.is_active IS TRUE) AS total,
              COUNT(*) FILTER (WHERE CAST(s.status AS TEXT) = 'APPROVED' AND s.is_active IS TRUE) AS approved,
              COUNT(*) FILTER (WHERE CAST(s.status AS TEXT) = 'SUSPENDED' AND s.is_active IS TRUE) AS suspended,
              COUNT(*) FILTER (WHERE p.next_review_due_on IS NOT NULL AND p.next_review_due_on <= :today AND s.is_active IS TRUE) AS review_due,
              COUNT(*) FILTER (
                WHERE p.contract_required IS TRUE AND s.is_active IS TRUE
                  AND NOT EXISTS (
                    SELECT 1 FROM quality_external_provider_contracts c
                    WHERE c.amo_id = s.amo_id AND c.supplier_id = s.id
                      AND c.status = 'ACTIVE'
                      AND (c.effective_on IS NULL OR c.effective_on <= :today)
                      AND (c.expires_on IS NULL OR c.expires_on >= :today)
                  )
              ) AS required_contract_missing,
              (SELECT COUNT(*) FROM quality_external_provider_contracts c
                WHERE c.amo_id = :amo_id AND c.status = 'ACTIVE'
                  AND c.expires_on BETWEEN :today AND :horizon) AS contracts_expiring,
              (SELECT COUNT(*) FROM quality_external_provider_evidence e
                WHERE e.amo_id = :amo_id AND e.status = 'VERIFIED'
                  AND e.valid_until BETWEEN :today AND :horizon) AS evidence_expiring
            FROM procurement_suppliers s
            LEFT JOIN quality_external_provider_profiles p
              ON p.amo_id = s.amo_id AND p.supplier_id = s.id
            WHERE s.amo_id = :amo_id
            """
        ),
        {"amo_id": ctx.amo_id, "today": today, "horizon": horizon},
    ).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


@provider_governance_router.get("/suppliers/providers")
def list_external_providers(
    search: str | None = Query(default=None, max_length=120),
    provider_status: ProviderStatus | None = Query(default=None, alias="status"),
    provider_kind: ProviderKind | None = Query(default=None),
    risk_level: ProviderRisk | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    ctx: TenantContext = Depends(require_quality_permission("qms.supplier.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _require_tables(db)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    where = ["s.amo_id = :amo_id", "s.is_active IS TRUE"]
    params: dict[str, Any] = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    if search:
        where.append("(LOWER(s.supplier_code) LIKE :search OR LOWER(s.legal_name) LIKE :search OR LOWER(COALESCE(s.trading_name, '')) LIKE :search)")
        params["search"] = f"%{search.strip().lower()}%"
    if provider_status:
        where.append("CAST(s.status AS TEXT) = :status")
        params["status"] = provider_status
    if provider_kind:
        where.append("COALESCE(p.provider_kind, s.supplier_type, 'SUPPLIER') = :provider_kind")
        params["provider_kind"] = provider_kind
    if risk_level:
        where.append("CAST(s.risk_level AS TEXT) = :risk_level")
        params["risk_level"] = risk_level
    where_sql = " AND ".join(where)
    rows = db.execute(
        text(
            f"""
            SELECT
              s.id, s.supplier_code, s.legal_name, s.trading_name,
              CAST(s.status AS TEXT) AS status, CAST(s.risk_level AS TEXT) AS risk_level,
              COALESCE(p.provider_kind, s.supplier_type, 'SUPPLIER') AS provider_kind,
              COALESCE(p.contract_required, FALSE) AS contract_required,
              p.oversight_owner_user_id, p.next_review_due_on,
              COALESCE(p.version, 0) AS governance_version,
              (SELECT COUNT(*) FROM procurement_supplier_approval_scopes a
                 WHERE a.amo_id = s.amo_id AND a.supplier_id = s.id
                   AND CAST(a.status AS TEXT) = 'ACTIVE') AS active_scope_count,
              (SELECT COUNT(*) FROM quality_external_provider_contracts c
                 WHERE c.amo_id = s.amo_id AND c.supplier_id = s.id
                   AND c.status = 'ACTIVE'
                   AND (c.effective_on IS NULL OR c.effective_on <= :today)
                   AND (c.expires_on IS NULL OR c.expires_on >= :today)) AS active_contract_count,
              (SELECT COUNT(*) FROM quality_external_provider_evidence e
                 WHERE e.amo_id = s.amo_id AND e.supplier_id = s.id
                   AND e.status = 'VERIFIED'
                   AND (e.valid_until IS NULL OR e.valid_until >= :today)) AS verified_evidence_count
            FROM procurement_suppliers s
            LEFT JOIN quality_external_provider_profiles p
              ON p.amo_id = s.amo_id AND p.supplier_id = s.id
            WHERE {where_sql}
            ORDER BY s.legal_name ASC, s.id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "today": _today()},
    ).mappings().all()
    count = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM procurement_suppliers s
            LEFT JOIN quality_external_provider_profiles p
              ON p.amo_id = s.amo_id AND p.supplier_id = s.id
            WHERE {where_sql}
            """
        ),
        params,
    ).scalar()
    items = []
    for row in rows:
        item = dict(row)
        item["provider_kind"] = _normalise_provider_kind(item.get("provider_kind"))
        item["review_due"] = bool(item.get("next_review_due_on") and item["next_review_due_on"] <= _today())
        item["contract_gap"] = bool(item.get("contract_required") and not int(item.get("active_contract_count") or 0))
        items.append(item)
    return {"items": items, "total": int(count or 0), "limit": limit, "offset": offset}


@provider_governance_router.post("/suppliers/providers", status_code=status.HTTP_201_CREATED)
def create_external_provider(
    payload: ProviderCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    profile_id = str(uuid.uuid4())
    try:
        provider_id = db.execute(
            text(
                """
                INSERT INTO procurement_suppliers (
                    amo_id, supplier_code, legal_name, trading_name, supplier_type,
                    status, risk_level, email, phone, website, country, physical_address,
                    default_currency, quality_contact_name, quality_contact_email, notes,
                    is_active, created_by_user_id, created_at, updated_at
                ) VALUES (
                    :amo_id, :supplier_code, :legal_name, :trading_name, :supplier_type,
                    'PROSPECTIVE', :risk_level, :email, :phone, :website, :country, :physical_address,
                    :default_currency, :quality_contact_name, :quality_contact_email, :notes,
                    TRUE, :actor, NOW(), NOW()
                ) RETURNING id
                """
            ),
            {
                "amo_id": ctx.amo_id,
                "supplier_code": payload.supplier_code.strip().upper(),
                "legal_name": payload.legal_name.strip(),
                "trading_name": payload.trading_name,
                "supplier_type": payload.provider_kind,
                "risk_level": payload.risk_level,
                "email": str(payload.email) if payload.email else None,
                "phone": payload.phone,
                "website": payload.website,
                "country": payload.country,
                "physical_address": payload.physical_address,
                "default_currency": payload.default_currency.upper(),
                "quality_contact_name": payload.quality_contact_name,
                "quality_contact_email": str(payload.quality_contact_email) if payload.quality_contact_email else None,
                "notes": payload.notes,
                "actor": ctx.user_id,
            },
        ).scalar_one()
        db.execute(
            text(
                """
                INSERT INTO quality_external_provider_profiles (
                    id, amo_id, supplier_id, provider_kind, contract_required,
                    oversight_owner_user_id, review_interval_days, next_review_due_on,
                    scope_summary, quality_requirements, version,
                    created_by_user_id, updated_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :amo_id, :supplier_id, :provider_kind, :contract_required,
                    :owner, :review_interval_days, :next_review_due_on,
                    :scope_summary, :quality_requirements, 1,
                    :actor, :actor, NOW(), NOW()
                )
                """
            ),
            {
                "id": profile_id,
                "amo_id": ctx.amo_id,
                "supplier_id": provider_id,
                "provider_kind": payload.provider_kind,
                "contract_required": payload.contract_required,
                "owner": payload.oversight_owner_user_id,
                "review_interval_days": payload.review_interval_days,
                "next_review_due_on": payload.next_review_due_on,
                "scope_summary": payload.scope_summary,
                "quality_requirements": payload.quality_requirements,
                "actor": ctx.user_id,
            },
        )
        audit_services.log_event(
            db,
            amo_id=ctx.amo_id,
            actor_user_id=ctx.user_id,
            entity_type="external_provider",
            entity_id=str(provider_id),
            action="create",
            after={"supplier_code": payload.supplier_code, "legal_name": payload.legal_name, "provider_kind": payload.provider_kind},
            correlation_id=f"qms-provider-create:{provider_id}",
            metadata={"source_master": "procurement_suppliers"},
            critical=True,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider code or governed provider identity already exists in this tenant.",
        ) from exc
    return _provider_detail(db, ctx=ctx, provider_id=int(provider_id))


@provider_governance_router.get("/suppliers/providers/{provider_id}")
def get_external_provider(
    provider_id: int,
    ctx: TenantContext = Depends(require_quality_permission("qms.supplier.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _require_tables(db)
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _provider_detail(db, ctx=ctx, provider_id=provider_id)


@provider_governance_router.patch("/suppliers/providers/{provider_id}/profile")
def update_external_provider_profile(
    provider_id: int,
    payload: ProviderProfilePatch,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    provider = _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id, lock=True)
    provider = _ensure_profile(db, ctx=ctx, provider=provider)
    _assert_expected_version(provider, payload.expected_version)
    before = {
        "provider_kind": provider.get("provider_kind"),
        "risk_level": provider.get("risk_level"),
        "contract_required": provider.get("contract_required"),
        "next_review_due_on": str(provider.get("next_review_due_on") or ""),
    }
    db.execute(
        text(
            """
            UPDATE quality_external_provider_profiles
            SET provider_kind = COALESCE(:provider_kind, provider_kind),
                contract_required = COALESCE(:contract_required, contract_required),
                oversight_owner_user_id = COALESCE(:oversight_owner_user_id, oversight_owner_user_id),
                review_interval_days = COALESCE(:review_interval_days, review_interval_days),
                last_reviewed_on = COALESCE(:last_reviewed_on, last_reviewed_on),
                next_review_due_on = COALESCE(:next_review_due_on, next_review_due_on),
                scope_summary = COALESCE(:scope_summary, scope_summary),
                quality_requirements = COALESCE(:quality_requirements, quality_requirements),
                version = version + 1,
                updated_by_user_id = :actor,
                updated_at = NOW()
            WHERE amo_id = :amo_id AND supplier_id = :provider_id
            """
        ),
        {
            "provider_kind": payload.provider_kind,
            "contract_required": payload.contract_required,
            "oversight_owner_user_id": payload.oversight_owner_user_id,
            "review_interval_days": payload.review_interval_days,
            "last_reviewed_on": payload.last_reviewed_on,
            "next_review_due_on": payload.next_review_due_on,
            "scope_summary": payload.scope_summary,
            "quality_requirements": payload.quality_requirements,
            "actor": ctx.user_id,
            "amo_id": ctx.amo_id,
            "provider_id": provider_id,
        },
    )
    if payload.provider_kind or payload.risk_level:
        db.execute(
            text(
                """
                UPDATE procurement_suppliers
                SET supplier_type = COALESCE(:provider_kind, supplier_type),
                    risk_level = COALESCE(:risk_level, risk_level),
                    updated_at = NOW()
                WHERE amo_id = :amo_id AND id = :provider_id
                """
            ),
            {
                "provider_kind": payload.provider_kind,
                "risk_level": payload.risk_level,
                "amo_id": ctx.amo_id,
                "provider_id": provider_id,
            },
        )
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="external_provider",
        entity_id=str(provider_id),
        action="governance_profile_update",
        before=before,
        after=payload.model_dump(mode="json", exclude={"reason", "expected_version"}),
        correlation_id=f"qms-provider-profile:{provider_id}:{payload.expected_version}",
        metadata={"reason": payload.reason},
        critical=True,
    )
    db.commit()
    return _provider_detail(db, ctx=ctx, provider_id=provider_id)


@provider_governance_router.post("/suppliers/providers/{provider_id}/transition")
def transition_external_provider(
    provider_id: int,
    payload: ProviderTransition,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    provider = _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id, lock=True)
    provider = _ensure_profile(db, ctx=ctx, provider=provider)
    _assert_expected_version(provider, payload.expected_version)
    current = str(provider.get("status") or "PROSPECTIVE").upper()
    target = payload.target_status
    if target == current:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Provider is already {current}.")
    if target not in _PROVIDER_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Provider transition {current} → {target} is not allowed.",
        )
    if target in {"APPROVED", "CONDITIONALLY_APPROVED"}:
        if provider.get("contract_required") and not _active_contract_exists(db, amo_id=ctx.amo_id, provider_id=provider_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This provider requires a current active contract before Quality approval.",
            )
        has_scope = _active_scope_exists(db, amo_id=ctx.amo_id, provider_id=provider_id)
        if not has_scope and not str(provider.get("scope_summary") or "").strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Define an approved scope or governed scope summary before Quality approval.",
            )
    approved = target in {"APPROVED", "CONDITIONALLY_APPROVED"}
    suspended = target == "SUSPENDED"
    db.execute(
        text(
            """
            UPDATE procurement_suppliers
            SET status = :target,
                approved_at = CASE WHEN :approved THEN NOW() ELSE approved_at END,
                approved_by_user_id = CASE WHEN :approved THEN :actor ELSE approved_by_user_id END,
                suspended_at = CASE WHEN :suspended THEN NOW() ELSE suspended_at END,
                suspended_by_user_id = CASE WHEN :suspended THEN :actor ELSE suspended_by_user_id END,
                suspension_reason = CASE WHEN :suspended THEN :reason ELSE suspension_reason END,
                updated_at = NOW()
            WHERE amo_id = :amo_id AND id = :provider_id
            """
        ),
        {
            "target": target,
            "approved": approved,
            "suspended": suspended,
            "actor": ctx.user_id,
            "reason": payload.reason,
            "amo_id": ctx.amo_id,
            "provider_id": provider_id,
        },
    )
    db.execute(
        text(
            """
            UPDATE quality_external_provider_profiles
            SET version = version + 1, updated_by_user_id = :actor, updated_at = NOW()
            WHERE amo_id = :amo_id AND supplier_id = :provider_id
            """
        ),
        {"actor": ctx.user_id, "amo_id": ctx.amo_id, "provider_id": provider_id},
    )
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="external_provider",
        entity_id=str(provider_id),
        action="lifecycle_transition",
        before={"status": current},
        after={"status": target},
        correlation_id=f"qms-provider-transition:{provider_id}:{payload.expected_version}",
        metadata={"reason": payload.reason},
        critical=True,
    )
    db.commit()
    return _provider_detail(db, ctx=ctx, provider_id=provider_id)


@provider_governance_router.get("/suppliers/providers/{provider_id}/contracts")
def list_provider_contracts(
    provider_id: int,
    ctx: TenantContext = Depends(require_quality_permission("qms.supplier.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _require_tables(db)
    _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    return {"items": _provider_contracts(db, amo_id=ctx.amo_id, provider_id=provider_id)}


@provider_governance_router.post("/suppliers/providers/{provider_id}/contracts", status_code=status.HTTP_201_CREATED)
def create_provider_contract(
    provider_id: int,
    payload: ContractCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    contract_id = str(uuid.uuid4())
    try:
        db.execute(
            text(
                """
                INSERT INTO quality_external_provider_contracts (
                    id, amo_id, supplier_id, contract_number, title, status, scope_text,
                    effective_on, expires_on, termination_notice_days, renewal_terms,
                    controlled_document_id, controlled_document_revision, owner_user_id,
                    version, created_by_user_id, updated_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :amo_id, :supplier_id, :contract_number, :title, 'DRAFT', :scope_text,
                    :effective_on, :expires_on, :notice_days, :renewal_terms,
                    :controlled_document_id, :controlled_document_revision, :owner_user_id,
                    1, :actor, :actor, NOW(), NOW()
                )
                """
            ),
            {
                "id": contract_id,
                "amo_id": ctx.amo_id,
                "supplier_id": provider_id,
                "contract_number": payload.contract_number.strip(),
                "title": payload.title.strip(),
                "scope_text": payload.scope_text.strip(),
                "effective_on": payload.effective_on,
                "expires_on": payload.expires_on,
                "notice_days": payload.termination_notice_days,
                "renewal_terms": payload.renewal_terms,
                "controlled_document_id": payload.controlled_document_id,
                "controlled_document_revision": payload.controlled_document_revision,
                "owner_user_id": payload.owner_user_id,
                "actor": ctx.user_id,
            },
        )
        audit_services.log_event(
            db,
            amo_id=ctx.amo_id,
            actor_user_id=ctx.user_id,
            entity_type="external_provider_contract",
            entity_id=contract_id,
            action="create",
            after=payload.model_dump(mode="json"),
            correlation_id=f"qms-provider-contract-create:{contract_id}",
            metadata={"provider_id": provider_id},
            critical=True,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract number already exists in this tenant.") from exc
    row = db.execute(
        text("SELECT * FROM quality_external_provider_contracts WHERE amo_id = :amo_id AND id = :id"),
        {"amo_id": ctx.amo_id, "id": contract_id},
    ).first()
    return _serialize_contract(row)


@provider_governance_router.post("/suppliers/providers/{provider_id}/contracts/{contract_id}/transition")
def transition_provider_contract(
    provider_id: int,
    contract_id: str,
    payload: ContractTransition,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    lock_suffix = " FOR UPDATE" if db.get_bind().dialect.name == "postgresql" else ""
    row = db.execute(
        text(
            f"SELECT * FROM quality_external_provider_contracts WHERE amo_id = :amo_id AND supplier_id = :provider_id AND id = :id{lock_suffix}"
        ),
        {"amo_id": ctx.amo_id, "provider_id": provider_id, "id": contract_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider contract was not found.")
    current_version = int(row.get("version") or 1)
    if current_version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract changed after it was loaded. Refresh before changing status.")
    current = _effective_contract_status(dict(row))
    target = payload.target_status
    if target not in _CONTRACT_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Contract transition {current} → {target} is not allowed.")
    if target == "ACTIVE":
        effective_on = row.get("effective_on")
        expires_on = row.get("expires_on")
        if expires_on and expires_on < _today():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An expired contract cannot be activated. Create or revise the current agreement.")
        if effective_on and expires_on and expires_on < effective_on:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract dates are invalid.")
    db.execute(
        text(
            """
            UPDATE quality_external_provider_contracts
            SET status = :target,
                approved_by_user_id = CASE WHEN :target = 'ACTIVE' THEN :actor ELSE approved_by_user_id END,
                approved_at = CASE WHEN :target = 'ACTIVE' THEN NOW() ELSE approved_at END,
                transition_reason = :reason,
                version = version + 1,
                updated_by_user_id = :actor,
                updated_at = NOW()
            WHERE amo_id = :amo_id AND supplier_id = :provider_id AND id = :id
            """
        ),
        {
            "target": target,
            "reason": payload.reason,
            "actor": ctx.user_id,
            "amo_id": ctx.amo_id,
            "provider_id": provider_id,
            "id": contract_id,
        },
    )
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="external_provider_contract",
        entity_id=contract_id,
        action="lifecycle_transition",
        before={"status": current, "version": current_version},
        after={"status": target, "version": current_version + 1},
        correlation_id=f"qms-provider-contract-transition:{contract_id}:{current_version}",
        metadata={"provider_id": provider_id, "reason": payload.reason},
        critical=True,
    )
    db.commit()
    updated = db.execute(
        text("SELECT * FROM quality_external_provider_contracts WHERE amo_id = :amo_id AND id = :id"),
        {"amo_id": ctx.amo_id, "id": contract_id},
    ).first()
    return _serialize_contract(updated)


@provider_governance_router.get("/suppliers/providers/{provider_id}/evidence")
def list_provider_evidence(
    provider_id: int,
    ctx: TenantContext = Depends(require_quality_permission("qms.supplier.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _require_tables(db)
    _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    return {"items": _provider_evidence(db, amo_id=ctx.amo_id, provider_id=provider_id)}


@provider_governance_router.post("/suppliers/providers/{provider_id}/evidence", status_code=status.HTTP_201_CREATED)
def create_provider_evidence(
    provider_id: int,
    payload: EvidenceCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    if payload.contract_id:
        contract = db.execute(
            text("SELECT 1 FROM quality_external_provider_contracts WHERE amo_id = :amo_id AND supplier_id = :provider_id AND id = :id"),
            {"amo_id": ctx.amo_id, "provider_id": provider_id, "id": payload.contract_id},
        ).first()
        if not contract:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evidence contract does not belong to this provider.")
    evidence_id = str(uuid.uuid4())
    try:
        db.execute(
            text(
                """
                INSERT INTO quality_external_provider_evidence (
                    id, amo_id, supplier_id, contract_id, evidence_type, source_system,
                    source_id, title, status, valid_from, valid_until, notes,
                    created_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :amo_id, :supplier_id, :contract_id, :evidence_type, :source_system,
                    :source_id, :title, 'PENDING', :valid_from, :valid_until, :notes,
                    :actor, NOW(), NOW()
                )
                """
            ),
            {
                "id": evidence_id,
                "amo_id": ctx.amo_id,
                "supplier_id": provider_id,
                "contract_id": payload.contract_id,
                "evidence_type": payload.evidence_type.strip().upper().replace(" ", "_"),
                "source_system": payload.source_system.strip().upper().replace(" ", "_"),
                "source_id": payload.source_id.strip(),
                "title": payload.title.strip(),
                "valid_from": payload.valid_from,
                "valid_until": payload.valid_until,
                "notes": payload.notes,
                "actor": ctx.user_id,
            },
        )
        audit_services.log_event(
            db,
            amo_id=ctx.amo_id,
            actor_user_id=ctx.user_id,
            entity_type="external_provider_evidence",
            entity_id=evidence_id,
            action="link",
            after=payload.model_dump(mode="json"),
            correlation_id=f"qms-provider-evidence-create:{evidence_id}",
            metadata={"provider_id": provider_id},
            critical=True,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This evidence source is already linked to the provider.") from exc
    row = db.execute(
        text("SELECT * FROM quality_external_provider_evidence WHERE amo_id = :amo_id AND id = :id"),
        {"amo_id": ctx.amo_id, "id": evidence_id},
    ).first()
    return _serialize_evidence(row)


@provider_governance_router.post("/suppliers/providers/{provider_id}/evidence/{evidence_id}/decision")
def decide_provider_evidence(
    provider_id: int,
    evidence_id: str,
    payload: EvidenceDecision,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _require_tables(db)
    assert_quality_permission(db, ctx, "qms.supplier.manage")
    _provider_or_404(db, amo_id=ctx.amo_id, provider_id=provider_id)
    row = db.execute(
        text("SELECT * FROM quality_external_provider_evidence WHERE amo_id = :amo_id AND supplier_id = :provider_id AND id = :id"),
        {"amo_id": ctx.amo_id, "provider_id": provider_id, "id": evidence_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider evidence was not found.")
    current = _effective_evidence_status(dict(row))
    target = payload.target_status
    if current in {"REJECTED", "SUPERSEDED"} and target == "VERIFIED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rejected or superseded evidence cannot be re-verified; link a new authoritative revision.")
    if target == "VERIFIED" and row.get("valid_until") and row["valid_until"] < _today():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Expired evidence cannot be verified as current.")
    db.execute(
        text(
            """
            UPDATE quality_external_provider_evidence
            SET status = :target,
                verified_by_user_id = CASE WHEN :target = 'VERIFIED' THEN :actor ELSE verified_by_user_id END,
                verified_at = CASE WHEN :target = 'VERIFIED' THEN NOW() ELSE verified_at END,
                notes = CASE WHEN notes IS NULL OR notes = '' THEN :reason ELSE notes || E'\n' || :reason END,
                updated_at = NOW()
            WHERE amo_id = :amo_id AND supplier_id = :provider_id AND id = :id
            """
        ),
        {
            "target": target,
            "actor": ctx.user_id,
            "reason": payload.reason,
            "amo_id": ctx.amo_id,
            "provider_id": provider_id,
            "id": evidence_id,
        },
    )
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="external_provider_evidence",
        entity_id=evidence_id,
        action="decision",
        before={"status": current},
        after={"status": target},
        correlation_id=f"qms-provider-evidence-decision:{evidence_id}:{target}",
        metadata={"provider_id": provider_id, "reason": payload.reason},
        critical=True,
    )
    db.commit()
    updated = db.execute(
        text("SELECT * FROM quality_external_provider_evidence WHERE amo_id = :amo_id AND id = :id"),
        {"amo_id": ctx.amo_id, "id": evidence_id},
    ).first()
    return _serialize_evidence(updated)
