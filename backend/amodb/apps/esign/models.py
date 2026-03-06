from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import ARRAY

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SignatureRequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class SignerType(str, enum.Enum):
    INTERNAL_USER = "INTERNAL_USER"
    EXTERNAL_EMAIL = "EXTERNAL_EMAIL"


class SignerStatus(str, enum.Enum):
    PENDING = "PENDING"
    VIEWED = "VIEWED"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


class SigningIntentStatus(str, enum.Enum):
    CREATED = "CREATED"
    CHALLENGE_ISSUED = "CHALLENGE_ISSUED"
    APPROVED = "APPROVED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"


class WebAuthnOwnerType(str, enum.Enum):
    USER = "USER"
    EXTERNAL_SIGNER = "EXTERNAL_SIGNER"


class ChallengeType(str, enum.Enum):
    REGISTRATION = "REGISTRATION"
    ASSERTION = "ASSERTION"


class CryptoValidationStatus(str, enum.Enum):
    NOT_RUN = "NOT_RUN"
    VALID = "VALID"
    INVALID = "INVALID"
    ERROR = "ERROR"


class ValidationResultSource(str, enum.Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"


class ProviderDirection(str, enum.Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    CALLBACK = "CALLBACK"
    ERROR = "ERROR"


class ProviderEventType(str, enum.Enum):
    SIGN_ATTEMPT = "SIGN_ATTEMPT"
    SIGN_SUCCESS = "SIGN_SUCCESS"
    SIGN_FAILURE = "SIGN_FAILURE"
    VALIDATE_ATTEMPT = "VALIDATE_ATTEMPT"
    VALIDATE_SUCCESS = "VALIDATE_SUCCESS"
    VALIDATE_FAILURE = "VALIDATE_FAILURE"
    HEALTHCHECK = "HEALTHCHECK"


class SignaturePolicyLevel(str, enum.Enum):
    BASIC_APPROVAL = "BASIC_APPROVAL"
    APPEARANCE_ONLY_ALLOWED = "APPEARANCE_ONLY_ALLOWED"
    CRYPTO_REQUIRED = "CRYPTO_REQUIRED"
    CRYPTO_AND_TIMESTAMP_REQUIRED = "CRYPTO_AND_TIMESTAMP_REQUIRED"


class OverrideType(str, enum.Enum):
    ALLOW_FALLBACK = "ALLOW_FALLBACK"
    BYPASS_PROVIDER_HEALTHCHECK = "BYPASS_PROVIDER_HEALTHCHECK"
    ACCEPT_NO_TIMESTAMP = "ACCEPT_NO_TIMESTAMP"


class EvidenceFormat(str, enum.Enum):
    ZIP = "ZIP"
    JSON = "JSON"


class NotificationType(str, enum.Enum):
    SIGNATURE_REQUESTED = "SIGNATURE_REQUESTED"
    REMINDER = "REMINDER"
    REQUEST_CANCELLED = "REQUEST_CANCELLED"
    REQUEST_COMPLETED = "REQUEST_COMPLETED"


class ESignDocumentVersion(Base):
    __tablename__ = "esign_document_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(64), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    storage_ref = Column(Text, nullable=False)
    content_sha256 = Column(String(64), nullable=False, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ESignSignaturePolicy(Base):
    __tablename__ = "esign_signature_policies"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_code = Column(String(64), nullable=False)
    display_name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    minimum_level = Column(String(48), nullable=False, default=SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value)
    allow_fallback_to_appearance = Column(Boolean, nullable=False, default=False)
    require_provider_health_before_send = Column(Boolean, nullable=False, default=False)
    require_provider_health_before_finalization = Column(Boolean, nullable=False, default=True)
    require_timestamp = Column(Boolean, nullable=False, default=False)
    require_revalidation_on_verify = Column(Boolean, nullable=False, default=False)
    revalidation_ttl_minutes = Column(Integer, nullable=True)
    allow_private_artifact_preview = Column(Boolean, nullable=False, default=True)
    allow_private_artifact_download = Column(Boolean, nullable=False, default=True)
    allow_public_artifact_access = Column(Boolean, nullable=False, default=False)
    allow_public_artifact_download = Column(Boolean, nullable=False, default=False)
    allow_public_evidence_summary_download = Column(Boolean, nullable=False, default=False)
    watermark_public_downloads = Column(Boolean, nullable=False, default=True)
    require_auth_for_original_artifact = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ESignSignatureRequest(Base):
    __tablename__ = "esign_signature_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_version_id = Column(String(36), ForeignKey("esign_document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id = Column(String(36), ForeignKey("esign_signature_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    achieved_level = Column(String(48), nullable=True)
    downgrade_reason_code = Column(String(128), nullable=True)
    finalized_with_fallback = Column(Boolean, nullable=False, default=False)
    status = Column(String(32), nullable=False, default=SignatureRequestStatus.DRAFT.value, index=True)
    title = Column(Text, nullable=False)
    message = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ESignSigner(Base):
    __tablename__ = "esign_signers"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    signature_request_id = Column(String(36), ForeignKey("esign_signature_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_type = Column(String(32), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(255), nullable=True)
    display_name = Column(Text, nullable=True)
    signing_order = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default=SignerStatus.PENDING.value, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    declined_at = Column(DateTime(timezone=True), nullable=True)


class ESignSigningIntent(Base):
    __tablename__ = "esign_signing_intents"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_id = Column(String(36), ForeignKey("esign_signers.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_version_id = Column(String(36), ForeignKey("esign_document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    intent_sha256 = Column(String(64), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default=SigningIntentStatus.CREATED.value, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


class ESignWebAuthnCredential(Base):
    __tablename__ = "esign_webauthn_credentials"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_type = Column(String(32), nullable=False)
    owner_id = Column(String(36), nullable=False, index=True)
    credential_id = Column(LargeBinary, nullable=False, unique=True)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(BigInteger, nullable=False, default=0)
    transports = Column(ARRAY(String), nullable=True)
    aaguid = Column(String(36), nullable=True)
    attestation_format = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    nickname = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class ESignSignedArtifact(Base):
    __tablename__ = "esign_signed_artifacts"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    signature_request_id = Column(String(36), ForeignKey("esign_signature_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_version_id = Column(String(36), ForeignKey("esign_document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_ref = Column(Text, nullable=False)
    signed_content_sha256 = Column(String(64), nullable=False, index=True)
    appearance_applied = Column(Boolean, nullable=False, default=True)
    cryptographic_signature_applied = Column(Boolean, nullable=False, default=False)
    signing_provider = Column(Text, nullable=True)
    cryptographic_validation_status = Column(String(16), nullable=False, default=CryptoValidationStatus.NOT_RUN.value)
    certificate_subject = Column(Text, nullable=True)
    certificate_serial = Column(Text, nullable=True)
    signing_time = Column(DateTime(timezone=True), nullable=True)
    timestamp_applied = Column(Boolean, nullable=False, default=False)
    timestamp_valid = Column(Boolean, nullable=True)
    validation_last_checked_at = Column(DateTime(timezone=True), nullable=True)
    validation_last_result_source = Column(String(8), nullable=False, default=ValidationResultSource.LIVE.value)
    validation_error_count = Column(Integer, nullable=False, default=0)
    validation_summary_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ESignVerificationToken(Base):
    __tablename__ = "esign_verification_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id = Column(String(36), ForeignKey("esign_signed_artifacts.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class ESignProviderEvent(Base):
    __tablename__ = "esign_provider_events"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id = Column(String(36), ForeignKey("esign_signed_artifacts.id", ondelete="SET NULL"), nullable=True, index=True)
    request_id = Column(String(36), ForeignKey("esign_signature_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_name = Column(Text, nullable=False)
    direction = Column(String(16), nullable=False)
    event_type = Column(String(32), nullable=False)
    http_status = Column(Integer, nullable=True)
    correlation_id = Column(Text, nullable=True)
    sanitized_payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ESignPolicyOverride(Base):
    __tablename__ = "esign_policy_overrides"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = Column(String(36), ForeignKey("esign_signature_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    override_type = Column(String(48), nullable=False)
    justification = Column(Text, nullable=False)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class ESignEvidenceBundle(Base):
    __tablename__ = "esign_evidence_bundles"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = Column(String(36), ForeignKey("esign_signature_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id = Column(String(36), ForeignKey("esign_signed_artifacts.id", ondelete="SET NULL"), nullable=True, index=True)
    storage_ref = Column(Text, nullable=False)
    bundle_sha256 = Column(String(64), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    format = Column(String(8), nullable=False, default=EvidenceFormat.ZIP.value)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)




class ESignNotification(Base):
    __tablename__ = "esign_notifications"
    __table_args__ = (
        Index("ix_esign_notifications_tenant_user_read", "tenant_id", "user_id", "read_at"),
        Index("ix_esign_notifications_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(48), nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=True)
    link_path = Column(Text, nullable=False)
    request_id = Column(String(36), ForeignKey("esign_signature_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

class ESignWebAuthnChallenge(Base):
    __tablename__ = "esign_webauthn_challenges"
    __table_args__ = (
        Index("ix_esign_webauthn_challenges_tenant_owner", "tenant_id", "owner_id", "challenge_type"),
        Index("ix_esign_webauthn_challenges_lookup", "tenant_id", "owner_id", "challenge_hash", "challenge_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(String(36), nullable=False, index=True)
    challenge_type = Column(String(32), nullable=False)
    challenge = Column(String(512), nullable=False, index=True)
    challenge_hash = Column(String(64), nullable=False, index=True)
    intent_id = Column(String(36), nullable=True, index=True)
    request_json = Column(JSON, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ESignSignerSession(Base):
    __tablename__ = "esign_signer_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_id = Column(String(36), ForeignKey("esign_signers.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
