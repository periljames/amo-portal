from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import Base
from amodb.user_id import generate_user_id

from . import models
from .audit_closing_assurance_models import QualityAuditAssuranceArtifact, QualityAuditSignatureEvidence
from .audit_live_completion_models import QualityAuditVerificationToken
from .audit_report_composition import _storage_root
from .audit_report_governance_models import QualityAuditReportRevision
from .router import AUDIT_REPORT_DIR


class QualityAuthoritySubmissionAttestation(Base):
    __tablename__ = "quality_authority_submission_attestations"
    __table_args__ = (
        Index("ix_quality_authority_attestation_audit", "amo_id", "audit_id"),
        Index(
            "uq_quality_authority_attestation_current",
            "amo_id",
            "audit_id",
            "report_revision_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False)
    report_revision_id = Column(String(36), ForeignKey("quality_audit_report_revisions.id", ondelete="RESTRICT"), nullable=False)
    report_sha256 = Column(String(64), nullable=False)
    rationale = Column(Text, nullable=False)
    attested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    attested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    pack_filename = Column(String(255), nullable=True)
    pack_content_type = Column(String(128), nullable=True)
    pack_size_bytes = Column(Integer, nullable=True)
    pack_sha256 = Column(String(64), nullable=True)
    pack_storage_ref = Column(String(1024), nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)


_ASSURANCE_ROOT = (AUDIT_REPORT_DIR.parent / "assurance_artifacts").resolve()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _controlled_file(file_ref: str | None, roots: tuple[Path, ...], *, label: str) -> Path:
    if not file_ref:
        raise HTTPException(status_code=409, detail=f"The governed {label} file reference is missing.")
    candidate = Path(file_ref).resolve()
    allowed = False
    for root_value in roots:
        root = root_value.resolve()
        if candidate == root or root in candidate.parents:
            allowed = True
            break
    if not allowed:
        raise HTTPException(status_code=409, detail=f"The governed {label} is outside controlled Quality storage.")
    if not candidate.is_file():
        raise HTTPException(status_code=409, detail=f"The governed {label} file is missing.")
    return candidate


def resolve_issued_report_file(row: QualityAuditReportRevision) -> Path:
    path = _controlled_file(
        row.file_ref,
        (AUDIT_REPORT_DIR.resolve(), _storage_root().resolve()),
        label="issued audit report",
    )
    if path.read_bytes()[:5] != b"%PDF-":
        raise HTTPException(status_code=409, detail="The issued audit report is not a valid PDF artifact.")
    if sha256_path(path) != row.sha256:
        raise HTTPException(status_code=409, detail="The issued audit report no longer matches its governed checksum.")
    return path


def resolve_authority_pack(storage_ref: str | None, expected_sha256: str | None = None) -> Path:
    root = _storage_root().resolve()
    path = _controlled_file(
        str(root / str(storage_ref)) if storage_ref else None,
        (root,),
        label="Authority submission pack",
    )
    if expected_sha256 and sha256_path(path) != expected_sha256:
        raise HTTPException(status_code=409, detail="The Authority submission pack no longer matches its governed checksum.")
    return path


def _zip_bytes(entries: list[tuple[str, bytes]], manifest: dict[str, Any]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for filename, content in [*entries, ("manifest.json", json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"))]:
            info = zipfile.ZipInfo(filename=filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)
    return output.getvalue()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._") or "audit"


def build_authority_pack_zip(
    db: Session,
    amo_id: str,
    audit_id: uuid.UUID,
    actor_user_id: str,
) -> QualityAuthoritySubmissionAttestation:
    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")

    report = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.status == "ISSUED",
    ).order_by(QualityAuditReportRevision.revision_no.desc()).first()
    if report is None:
        raise HTTPException(status_code=409, detail="An ISSUED audit report is required before an Authority submission pack can be generated.")
    report_path = resolve_issued_report_file(report)

    attestation = db.query(QualityAuthoritySubmissionAttestation).filter(
        QualityAuthoritySubmissionAttestation.amo_id == amo_id,
        QualityAuthoritySubmissionAttestation.audit_id == audit_id,
        QualityAuthoritySubmissionAttestation.report_revision_id == report.id,
        QualityAuthoritySubmissionAttestation.superseded_at.is_(None),
    ).order_by(QualityAuthoritySubmissionAttestation.attested_at.desc()).with_for_update().first()
    if attestation is None:
        raise HTTPException(status_code=409, detail="A current Accountable Executive attestation is required before an Authority submission pack can be generated.")
    if attestation.report_sha256 != report.sha256:
        raise HTTPException(status_code=409, detail="The current attestation does not match the issued audit report checksum.")

    assurance = db.query(QualityAuditAssuranceArtifact).filter(
        QualityAuditAssuranceArtifact.amo_id == amo_id,
        QualityAuditAssuranceArtifact.audit_id == audit_id,
        QualityAuditAssuranceArtifact.source_report_revision_id == report.id,
    ).order_by(QualityAuditAssuranceArtifact.created_at.desc()).first()
    signature_query = db.query(QualityAuditSignatureEvidence).filter(
        QualityAuditSignatureEvidence.amo_id == amo_id,
        QualityAuditSignatureEvidence.audit_id == audit_id,
        QualityAuditSignatureEvidence.report_revision_id == report.id,
        QualityAuditSignatureEvidence.artifact_sha256 == report.sha256,
    )
    if assurance is not None:
        signature_query = signature_query.filter(QualityAuditSignatureEvidence.id == assurance.signature_evidence_id)
    signature = signature_query.order_by(QualityAuditSignatureEvidence.signed_at.desc()).first()

    now = datetime.now(timezone.utc)
    live_token = db.query(QualityAuditVerificationToken.id).filter(
        QualityAuditVerificationToken.amo_id == amo_id,
        QualityAuditVerificationToken.audit_id == audit_id,
        QualityAuditVerificationToken.report_revision_id == report.id,
        QualityAuditVerificationToken.revoked_at.is_(None),
        QualityAuditVerificationToken.expires_at > now,
    ).first()
    attester = db.query(account_models.User).filter(
        account_models.User.id == attestation.attested_by_user_id,
        account_models.User.amo_id == amo_id,
    ).first()
    attester_label = (
        getattr(attester, "full_name", None)
        or getattr(attester, "email", None)
        or attestation.attested_by_user_id
    )

    entries = [(f"issued-report-r{report.revision_no}.pdf", report_path.read_bytes())]
    if assurance is not None:
        assurance_path = _controlled_file(assurance.file_ref, (_ASSURANCE_ROOT,), label="assurance artifact")
        if assurance_path.read_bytes()[:5] != b"%PDF-":
            raise HTTPException(status_code=409, detail="The governed assurance artifact is not a valid PDF artifact.")
        if sha256_path(assurance_path) != assurance.sha256:
            raise HTTPException(status_code=409, detail="The governed assurance artifact no longer matches its checksum.")
        entries.append((f"assurance-output-{_safe_name(assurance.artifact_type).lower()}.pdf", assurance_path.read_bytes()))

    manifest = {
        "audit_ref": audit.audit_ref,
        "revision_no": report.revision_no,
        "report_sha256": report.sha256,
        "signature_ceremony_sha256": signature.ceremony_sha256 if signature is not None else None,
        "attested_by": str(attester_label),
        "attested_at": attestation.attested_at.isoformat(),
        "verification_path_template": "/verify/{token}" if live_token is not None else None,
    }
    payload = _zip_bytes(entries, manifest)
    pack_sha256 = hashlib.sha256(payload).hexdigest()
    filename = f"{_safe_name(audit.audit_ref or str(audit.id))}-authority-pack-r{report.revision_no}-{pack_sha256[:12]}.zip"
    root = _storage_root().resolve()
    target_dir = (root / amo_id / str(audit_id) / "authority-packs").resolve()
    if root not in target_dir.parents:
        raise HTTPException(status_code=409, detail="Authority pack destination escaped controlled Quality storage.")
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / filename
    temporary = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
    previous = attestation.pack_storage_ref
    try:
        temporary.write_bytes(payload)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    attestation.pack_filename = filename
    attestation.pack_content_type = "application/zip"
    attestation.pack_size_bytes = len(payload)
    attestation.pack_sha256 = pack_sha256
    attestation.pack_storage_ref = str(destination.relative_to(root))
    db.add(attestation)
    db.flush()

    if previous and previous != attestation.pack_storage_ref:
        try:
            resolve_authority_pack(previous).unlink(missing_ok=True)
        except HTTPException:
            pass
    return attestation
