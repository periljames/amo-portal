from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db

from .audit_authority_pack import (
    QualityAuthoritySubmissionAttestation,
    build_authority_pack_zip,
    resolve_authority_pack,
    resolve_issued_report_file,
)
from .audit_report_governance_models import QualityAuditReportRevision
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)


router = APIRouter(tags=["Quality Authority submission pack"])


class AuthorityAttestationCreate(BaseModel):
    report_revision_id: str = Field(min_length=8, max_length=36)
    report_sha256: str = Field(min_length=64, max_length=64)
    rationale: str = Field(min_length=8, max_length=4000)

    @field_validator("report_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise ValueError("report_sha256 must be a 64-character hexadecimal SHA-256 digest")
        return normalized

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("rationale must contain at least 8 non-whitespace characters")
        return normalized


def _role_value(user: account_models.User) -> str:
    value = getattr(getattr(user, "role", None), "value", getattr(user, "role", None))
    return str(value or "").upper()


def _tenant_user(db: Session, ctx: TenantContext) -> account_models.User:
    user = db.query(account_models.User).filter(
        account_models.User.id == ctx.user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None or getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="An active AMO tenant identity is required.")
    return user


def _assert_accountable_executive(db: Session, ctx: TenantContext) -> account_models.User:
    user = _tenant_user(db, ctx)
    if _role_value(user) != "ACCOUNTABLE_EXECUTIVE":
        raise HTTPException(status_code=403, detail="Only the Accountable Executive may attest an Authority submission.")
    return user


def _assert_pack_generation_actor(db: Session, ctx: TenantContext) -> account_models.User:
    user = _tenant_user(db, ctx)
    if not (
        getattr(user, "is_amo_admin", False)
        or _role_value(user) in {"ACCOUNTABLE_EXECUTIVE", "QUALITY_MANAGER", "AMO_ADMIN"}
    ):
        raise HTTPException(status_code=403, detail="Only the Accountable Executive, Quality Manager, or AMO administrator may generate an Authority submission pack.")
    return user


def _serialize(row: QualityAuthoritySubmissionAttestation | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "report_revision_id": row.report_revision_id,
        "report_sha256": row.report_sha256,
        "rationale": row.rationale,
        "attested_by_user_id": row.attested_by_user_id,
        "attested_at": row.attested_at.isoformat() if row.attested_at else None,
        "pack_filename": row.pack_filename,
        "pack_content_type": row.pack_content_type,
        "pack_size_bytes": row.pack_size_bytes,
        "pack_sha256": row.pack_sha256,
    }


def _latest_attestation(db: Session, *, amo_id: str, audit_id: uuid.UUID):
    return db.query(QualityAuthoritySubmissionAttestation).filter(
        QualityAuthoritySubmissionAttestation.amo_id == amo_id,
        QualityAuthoritySubmissionAttestation.audit_id == audit_id,
        QualityAuthoritySubmissionAttestation.superseded_at.is_(None),
    ).order_by(QualityAuthoritySubmissionAttestation.attested_at.desc()).first()


@router.post("/audits/{audit_id}/authority-attestation", status_code=status.HTTP_201_CREATED)
def attest_authority_submission(
    audit_id: uuid.UUID,
    payload: AuthorityAttestationCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.reports.attest_authority")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    actor = _assert_accountable_executive(db, ctx)
    report = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.id == payload.report_revision_id,
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.status == "ISSUED",
    ).first()
    if report is None:
        raise HTTPException(status_code=409, detail="The selected report revision is not the governed ISSUED report for this audit.")
    if report.sha256.lower() != payload.report_sha256:
        raise HTTPException(status_code=409, detail="The attested checksum does not match the governed ISSUED report.")
    resolve_issued_report_file(report)

    existing = db.query(QualityAuthoritySubmissionAttestation).filter(
        QualityAuthoritySubmissionAttestation.amo_id == ctx.amo_id,
        QualityAuthoritySubmissionAttestation.audit_id == audit_id,
        QualityAuthoritySubmissionAttestation.report_revision_id == report.id,
        QualityAuthoritySubmissionAttestation.superseded_at.is_(None),
    ).with_for_update().all()
    attested_at = datetime.now(timezone.utc)
    if db.get_bind().dialect.name == "postgresql" or not existing:
        for prior in existing:
            prior.superseded_at = attested_at
        if existing:
            db.flush()
        row = QualityAuthoritySubmissionAttestation(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            report_revision_id=report.id,
            report_sha256=report.sha256.lower(),
            rationale=payload.rationale,
            attested_by_user_id=str(actor.id),
            attested_at=attested_at,
        )
        db.add(row)
    else:
        # The portable migration uses a full unique key. Reuse that row on
        # non-Postgres test/dev databases while PostgreSQL retains history via
        # its partial unique index.
        row = existing[0]
        row.report_sha256 = report.sha256.lower()
        row.rationale = payload.rationale
        row.attested_by_user_id = str(actor.id)
        row.attested_at = attested_at
        row.pack_filename = None
        row.pack_content_type = None
        row.pack_size_bytes = None
        row.pack_sha256 = None
        row.pack_storage_ref = None
        row.superseded_at = None
    db.commit()
    db.refresh(row)
    return {"attestation": _serialize(row)}


@router.get("/audits/{audit_id}/authority-attestation")
def get_authority_attestation(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return {"attestation": _serialize(_latest_attestation(db, amo_id=ctx.amo_id, audit_id=audit_id))}


@router.post("/audits/{audit_id}/authority-pack", status_code=status.HTTP_201_CREATED)
def generate_authority_pack(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.reports.export")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _assert_pack_generation_actor(db, ctx)
    row = build_authority_pack_zip(db, ctx.amo_id, audit_id, ctx.user_id)
    db.commit()
    db.refresh(row)
    return {"attestation": _serialize(row)}


@router.get("/audits/{audit_id}/authority-pack/download")
def download_authority_pack(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.reports.export")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _latest_attestation(db, amo_id=ctx.amo_id, audit_id=audit_id)
    if row is None or not row.pack_storage_ref or not row.pack_filename or not row.pack_sha256:
        raise HTTPException(status_code=404, detail="An Authority submission pack has not been generated for the current attestation.")
    path = resolve_authority_pack(row.pack_storage_ref, row.pack_sha256)
    return FileResponse(
        path,
        filename=row.pack_filename,
        media_type=row.pack_content_type or "application/zip",
        headers={"X-Content-SHA256": row.pack_sha256},
    )
