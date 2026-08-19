from __future__ import annotations

import hashlib
import hmac
import inspect
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr, model_validator
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.database import get_read_db, get_write_db
from amodb.security import SECRET_KEY, verify_password
from amodb.user_id import generate_user_id

from . import models
from .audit_closing_assurance_models import (
    QualityAuditAssuranceArtifact,
    QualityAuditOutputPolicyRevision,
    QualityAuditSignatureAttempt,
    QualityAuditSignatureEvidence,
)
from .audit_closure_models import QualityAuditClosureState
from .audit_report_governance_models import QualityAuditReportRevision
from .audit_report_governance_router import _safe_report_path, _sha256
from .router import AUDIT_REPORT_DIR
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit closing assurance"])
OutputPolicy = Literal["NONE", "REPORT_ONLY", "APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"]
SupplementaryArtifact = Literal["APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"]
ARTIFACT_DIR = AUDIT_REPORT_DIR.parent / "assurance_artifacts"


class OutputPolicyRevisionCreate(BaseModel):
    artifact_policy: OutputPolicy
    artifact_title: str | None = Field(default=None, max_length=255)
    artifact_statement: str | None = Field(default=None, max_length=12000)
    rationale: str = Field(min_length=8, max_length=4000)

    @model_validator(mode="after")
    def validate_configured_copy(self):
        if self.artifact_policy in {"APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"}:
            if not self.artifact_title or len(self.artifact_title.strip()) < 3:
                raise ValueError("A configured supplementary artifact requires an explicit title.")
            if not self.artifact_statement or len(self.artifact_statement.strip()) < 8:
                raise ValueError("A configured supplementary artifact requires an explicit statement.")
        return self


class PasswordReauthSignatureCreate(BaseModel):
    password: SecretStr
    reason: str = Field(min_length=8, max_length=4000)


class AssuranceArtifactGenerate(BaseModel):
    signature_evidence_id: str = Field(min_length=8, max_length=36)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _policy_dict(row: QualityAuditOutputPolicyRevision | None) -> dict[str, Any]:
    if row is None:
        return {"configured": False, "current": None}
    return {
        "configured": True,
        "current": {
            "id": row.id,
            "revision_no": row.revision_no,
            "artifact_policy": row.artifact_policy,
            "artifact_title": row.artifact_title,
            "artifact_statement": row.artifact_statement,
            "rationale": row.rationale,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


def _signature_dict(row: QualityAuditSignatureEvidence) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "report_revision_id": row.report_revision_id,
        "signer_user_id": row.signer_user_id,
        "method": row.method,
        "purpose": row.purpose,
        "artifact_sha256": row.artifact_sha256,
        "reason": row.reason,
        "signature_digest": row.signature_digest,
        "signed_at": row.signed_at.isoformat() if row.signed_at else None,
    }


def _artifact_dict(row: QualityAuditAssuranceArtifact) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "output_policy_revision_id": row.output_policy_revision_id,
        "artifact_type": row.artifact_type,
        "source_report_revision_id": row.source_report_revision_id,
        "signature_evidence_id": row.signature_evidence_id,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _latest_policy(db: Session, amo_id: str) -> QualityAuditOutputPolicyRevision | None:
    return db.query(QualityAuditOutputPolicyRevision).filter(
        QualityAuditOutputPolicyRevision.amo_id == amo_id,
    ).order_by(QualityAuditOutputPolicyRevision.revision_no.desc()).first()


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _issued_report(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> QualityAuditReportRevision:
    row = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.status == "ISSUED",
    ).order_by(QualityAuditReportRevision.revision_no.desc()).first()
    if row is None:
        raise HTTPException(status_code=409, detail="A governed ISSUED audit report is required before signature evidence can be recorded.")
    path = _safe_report_path(row.file_ref)
    if _sha256(path) != row.sha256:
        raise HTTPException(status_code=409, detail="The issued audit report no longer matches its governed checksum.")
    return row


def _signature_rate_policy() -> tuple[int, int]:
    max_raw = os.getenv("QMS_SIGNATURE_MAX_FAILURES", "").strip()
    window_raw = os.getenv("QMS_SIGNATURE_FAILURE_WINDOW_SECONDS", "").strip()
    if not max_raw or not window_raw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password re-auth signing is disabled until QMS_SIGNATURE_MAX_FAILURES and QMS_SIGNATURE_FAILURE_WINDOW_SECONDS are explicitly configured.",
        )
    try:
        maximum = int(max_raw)
        window_seconds = int(window_raw)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="QMS signature rate-limit policy is invalid.") from exc
    if maximum <= 0 or window_seconds <= 0:
        raise HTTPException(status_code=503, detail="QMS signature rate-limit policy must use positive values.")
    return maximum, window_seconds


def _verify_password_for_user(user: account_models.User, plain: str) -> bool:
    stored = getattr(user, "hashed_password", None) or getattr(user, "password_hash", None)
    if not stored:
        return False
    parameters = list(inspect.signature(verify_password).parameters)
    if parameters and "hash" in parameters[0].lower():
        return bool(verify_password(stored, plain))
    return bool(verify_password(plain, stored))


def _signature_digest(
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    report_revision_id: str,
    signer_user_id: str,
    report_sha256: str,
    reason: str,
    nonce: str,
    signed_at: datetime,
) -> str:
    canonical = "|".join([
        "QMS_AUDIT_SIGNATURE_V1",
        amo_id,
        str(audit_id),
        report_revision_id,
        signer_user_id,
        report_sha256,
        reason.strip(),
        nonce,
        signed_at.astimezone(timezone.utc).isoformat(),
    ]).encode("utf-8")
    key = SECRET_KEY.encode("utf-8") if isinstance(SECRET_KEY, str) else bytes(SECRET_KEY)
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _publish(row: audit_models.AuditEvent) -> None:
    try:
        occurred = row.occurred_at or row.created_at
        publish_event(EventEnvelope(
            id=str(row.id),
            type=f"{row.entity_type}.{row.action}".lower(),
            entityType=row.entity_type,
            entityId=row.entity_id,
            action=row.action,
            timestamp=occurred.isoformat() if occurred else "",
            actor={"userId": row.actor_user_id} if row.actor_user_id else None,
            metadata={"amoId": row.amo_id, **(row.metadata_json or {})},
        ))
    except Exception:
        return


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned[:96] or "audit"


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _render_assurance_pdf(
    path: Path,
    *,
    policy: QualityAuditOutputPolicyRevision,
    audit: models.QMSAudit,
    report: QualityAuditReportRevision,
    signature: QualityAuditSignatureEvidence,
    signer_label: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    width, height = A4
    margin = 52
    y = height - 62
    doc.setTitle(policy.artifact_title or policy.artifact_policy)
    doc.setFont("Helvetica-Bold", 16)
    for line in _wrap(policy.artifact_title or policy.artifact_policy.replace("_", " ").title(), 64):
        doc.drawString(margin, y, line)
        y -= 21
    y -= 8
    doc.setFont("Helvetica", 10)
    metadata_lines = [
        f"Audit: {audit.audit_ref} — {audit.title}",
        f"Source issued report: revision {report.revision_no} / SHA-256 {report.sha256}",
        f"Output policy: revision {policy.revision_no} / {policy.artifact_policy}",
        f"Electronic approval evidence: {signature.id}",
        f"Approved by: {signer_label}",
        f"Signed at: {signature.signed_at.astimezone(timezone.utc).isoformat()}",
    ]
    for line in metadata_lines:
        for wrapped in _wrap(line, 92):
            doc.drawString(margin, y, wrapped)
            y -= 14
        y -= 2
    y -= 10
    doc.setFont("Helvetica-Bold", 11)
    doc.drawString(margin, y, "Configured statement")
    y -= 18
    doc.setFont("Helvetica", 10)
    for line in _wrap(policy.artifact_statement or "", 96):
        if y < 70:
            doc.showPage()
            y = height - 62
            doc.setFont("Helvetica", 10)
        doc.drawString(margin, y, line)
        y -= 14
    y -= 18
    doc.setFont("Helvetica", 8)
    for line in _wrap(
        f"Integrity chain: report {report.sha256} · signature {signature.signature_digest} · policy revision {policy.id}",
        118,
    ):
        doc.drawString(margin, y, line)
        y -= 11
    doc.save()


def _safe_artifact_path(file_ref: str) -> Path:
    root = ARTIFACT_DIR.resolve()
    candidate = Path(file_ref).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Assurance artifact is outside controlled Quality storage.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Assurance artifact file is missing.")
    return candidate


@router.get("/audit-output-policy")
def get_audit_output_policy(
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _policy_dict(_latest_policy(db, ctx.amo_id))


@router.get("/audit-output-policy/revisions")
def list_audit_output_policy_revisions(
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = db.query(QualityAuditOutputPolicyRevision).filter(
        QualityAuditOutputPolicyRevision.amo_id == ctx.amo_id,
    ).order_by(QualityAuditOutputPolicyRevision.revision_no.desc()).limit(100).all()
    return {"items": [_policy_dict(row)["current"] for row in rows]}


@router.post("/audit-output-policy/revisions", status_code=status.HTTP_201_CREATED)
def create_audit_output_policy_revision(
    payload: OutputPolicyRevisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    latest = db.query(QualityAuditOutputPolicyRevision).filter(
        QualityAuditOutputPolicyRevision.amo_id == ctx.amo_id,
    ).order_by(QualityAuditOutputPolicyRevision.revision_no.desc()).with_for_update().first()
    row = QualityAuditOutputPolicyRevision(
        amo_id=ctx.amo_id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        artifact_policy=payload.artifact_policy,
        artifact_title=payload.artifact_title.strip() if payload.artifact_title else None,
        artifact_statement=payload.artifact_statement.strip() if payload.artifact_statement else None,
        rationale=payload.rationale.strip(),
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _policy_dict(row)["current"]


@router.get("/audits/{audit_id}/signature-evidence")
def list_audit_signature_evidence(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditSignatureEvidence).filter(
        QualityAuditSignatureEvidence.amo_id == ctx.amo_id,
        QualityAuditSignatureEvidence.audit_id == audit_id,
    ).order_by(QualityAuditSignatureEvidence.signed_at.desc()).limit(100).all()
    return {"items": [_signature_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/signature-evidence/password-reauth", status_code=status.HTTP_201_CREATED)
def sign_issued_report_with_password_reauth(
    audit_id: uuid.UUID,
    payload: PasswordReauthSignatureCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    maximum, window_seconds = _signature_rate_policy()
    now = _utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    failed = db.query(QualityAuditSignatureAttempt).filter(
        QualityAuditSignatureAttempt.amo_id == ctx.amo_id,
        QualityAuditSignatureAttempt.audit_id == audit_id,
        QualityAuditSignatureAttempt.signer_user_id == ctx.user_id,
        QualityAuditSignatureAttempt.method == "PASSWORD_REAUTH",
        QualityAuditSignatureAttempt.succeeded.is_(False),
        QualityAuditSignatureAttempt.created_at >= cutoff,
    ).count()
    if failed >= maximum:
        raise HTTPException(status_code=429, detail="Password re-auth signing is temporarily blocked by the configured failure policy.")

    user = db.query(account_models.User).filter(
        account_models.User.id == ctx.user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=403, detail="Active internal Quality identity is required to sign an audit report.")
    if not _verify_password_for_user(user, payload.password.get_secret_value()):
        db.add(QualityAuditSignatureAttempt(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            signer_user_id=ctx.user_id,
            method="PASSWORD_REAUTH",
            succeeded=False,
            failure_code="INVALID_PASSWORD",
        ))
        db.commit()
        raise HTTPException(status_code=401, detail="Password re-authentication failed.")

    report = _issued_report(db, amo_id=ctx.amo_id, audit_id=audit_id)
    nonce = secrets.token_hex(16)
    signed_at = now
    evidence = QualityAuditSignatureEvidence(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        report_revision_id=report.id,
        signer_user_id=ctx.user_id,
        method="PASSWORD_REAUTH",
        purpose="ISSUED_REPORT",
        artifact_sha256=report.sha256,
        reason=payload.reason.strip(),
        nonce=nonce,
        signed_at=signed_at,
        signature_digest=_signature_digest(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            report_revision_id=report.id,
            signer_user_id=ctx.user_id,
            report_sha256=report.sha256,
            reason=payload.reason,
            nonce=nonce,
            signed_at=signed_at,
        ),
    )
    db.add(QualityAuditSignatureAttempt(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        signer_user_id=ctx.user_id,
        method="PASSWORD_REAUTH",
        succeeded=True,
        failure_code=None,
    ))
    db.add(evidence)
    db.flush()
    event = audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type="qms.audit.signature_evidence",
        entity_id=evidence.id,
        action="SIGNED_PASSWORD_REAUTH",
        actor_user_id=ctx.user_id,
        after={"audit_id": str(audit_id), "report_revision_id": report.id, "artifact_sha256": report.sha256},
        metadata_json={"module": "quality", "auditId": str(audit_id), "reportRevisionId": report.id},
    )
    db.add(event)
    db.flush()
    db.commit()
    db.refresh(evidence)
    _publish(event)
    return _signature_dict(evidence)


@router.get("/audits/{audit_id}/assurance-artifacts")
def list_assurance_artifacts(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditAssuranceArtifact).filter(
        QualityAuditAssuranceArtifact.amo_id == ctx.amo_id,
        QualityAuditAssuranceArtifact.audit_id == audit_id,
    ).order_by(QualityAuditAssuranceArtifact.created_at.desc()).limit(100).all()
    return {"items": [_artifact_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/assurance-artifacts/generate", status_code=status.HTTP_201_CREATED)
def generate_assurance_artifact(
    audit_id: uuid.UUID,
    payload: AssuranceArtifactGenerate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    policy = _latest_policy(db, ctx.amo_id)
    if policy is None:
        raise HTTPException(status_code=409, detail="Audit output policy is not configured for this tenant.")
    if policy.artifact_policy not in {"APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"}:
        raise HTTPException(status_code=409, detail=f"Current audit output policy {policy.artifact_policy} does not permit a supplementary artifact.")
    if not policy.artifact_title or not policy.artifact_statement:
        raise HTTPException(status_code=409, detail="Configured supplementary artifact title/statement is incomplete.")

    closure = db.query(QualityAuditClosureState).filter(
        QualityAuditClosureState.amo_id == ctx.amo_id,
        QualityAuditClosureState.audit_id == audit_id,
    ).first()
    if closure is None or closure.execution_status != "CLOSED":
        raise HTTPException(status_code=409, detail="Audit execution must be formally closed before a supplementary assurance artifact is generated.")

    report = _issued_report(db, amo_id=ctx.amo_id, audit_id=audit_id)
    signature = db.query(QualityAuditSignatureEvidence).filter(
        QualityAuditSignatureEvidence.amo_id == ctx.amo_id,
        QualityAuditSignatureEvidence.audit_id == audit_id,
        QualityAuditSignatureEvidence.id == payload.signature_evidence_id,
        QualityAuditSignatureEvidence.report_revision_id == report.id,
        QualityAuditSignatureEvidence.artifact_sha256 == report.sha256,
    ).first()
    if signature is None:
        raise HTTPException(status_code=409, detail="Selected signature evidence does not match the current issued report revision and checksum.")

    artifact_type: SupplementaryArtifact = policy.artifact_policy  # type: ignore[assignment]
    existing = db.query(QualityAuditAssuranceArtifact).filter(
        QualityAuditAssuranceArtifact.amo_id == ctx.amo_id,
        QualityAuditAssuranceArtifact.audit_id == audit_id,
        QualityAuditAssuranceArtifact.artifact_type == artifact_type,
        QualityAuditAssuranceArtifact.source_report_revision_id == report.id,
        QualityAuditAssuranceArtifact.signature_evidence_id == signature.id,
    ).first()
    if existing is not None:
        return _artifact_dict(existing)

    signer = db.query(account_models.User).filter(
        account_models.User.id == signature.signer_user_id,
        account_models.User.amo_id == ctx.amo_id,
    ).first()
    signer_label = (
        getattr(signer, "full_name", None)
        or getattr(signer, "name", None)
        or getattr(signer, "email", None)
        or signature.signer_user_id
    )
    artifact_id = generate_user_id()
    filename = f"{_safe_name(audit.audit_ref or str(audit.id))}-{artifact_type.lower().replace('_', '-')}-{artifact_id[:8]}.pdf"
    path = (ARTIFACT_DIR / ctx.amo_id / str(audit_id) / filename).resolve()
    root = ARTIFACT_DIR.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Generated artifact path escaped controlled Quality storage.") from exc
    _render_assurance_pdf(
        path,
        policy=policy,
        audit=audit,
        report=report,
        signature=signature,
        signer_label=str(signer_label),
    )
    digest = _sha256(path)
    artifact = QualityAuditAssuranceArtifact(
        id=artifact_id,
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        output_policy_revision_id=policy.id,
        artifact_type=artifact_type,
        source_report_revision_id=report.id,
        signature_evidence_id=signature.id,
        file_ref=str(path),
        filename=filename,
        content_type="application/pdf",
        size_bytes=path.stat().st_size,
        sha256=digest,
        created_by_user_id=ctx.user_id,
    )
    db.add(artifact)
    event = audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type="qms.audit.assurance_artifact",
        entity_id=artifact.id,
        action="GENERATED",
        actor_user_id=ctx.user_id,
        after={
            "audit_id": str(audit_id),
            "artifact_type": artifact_type,
            "sha256": digest,
            "report_revision_id": report.id,
            "signature_evidence_id": signature.id,
            "output_policy_revision_id": policy.id,
        },
        metadata_json={"module": "quality", "auditId": str(audit_id)},
    )
    db.add(event)
    db.flush()
    db.commit()
    db.refresh(artifact)
    _publish(event)
    return _artifact_dict(artifact)


@router.get("/audits/{audit_id}/assurance-artifacts/{artifact_id}/download")
def download_assurance_artifact(
    audit_id: uuid.UUID,
    artifact_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> Response:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditAssuranceArtifact).filter(
        QualityAuditAssuranceArtifact.amo_id == ctx.amo_id,
        QualityAuditAssuranceArtifact.audit_id == audit_id,
        QualityAuditAssuranceArtifact.id == artifact_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assurance artifact not found.")
    path = _safe_artifact_path(row.file_ref)
    if _sha256(path) != row.sha256:
        raise HTTPException(status_code=409, detail="Stored assurance artifact no longer matches its governed checksum.")
    return FileResponse(path, media_type=row.content_type, filename=row.filename)
