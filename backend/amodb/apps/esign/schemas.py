from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FieldPlacement(BaseModel):
    page: int = 1
    x: float
    y: float


class SignerIn(BaseModel):
    signer_type: str
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    signing_order: int = 1


class RequestCreateIn(BaseModel):
    document_id: str
    source_storage_ref: str
    source_version_id: str | None = None
    title: str
    message: str | None = None
    expires_at: datetime | None = None
    policy_code: str | None = None
    signers: list[SignerIn] = Field(default_factory=list)
    field_placements: list[FieldPlacement] = Field(default_factory=list)


class RequestCreateOut(BaseModel):
    request_id: str
    doc_version_id: str
    doc_hash: str
    policy_code: str
    policy_minimum_level: str


class SendRequestOut(BaseModel):
    id: str
    status: str
    sent_at: datetime | None = None


class PublicKeyOptionsOut(BaseModel):
    options: dict[str, Any]


class WebAuthnRegistrationVerifyIn(BaseModel):
    credential: dict[str, Any]


class WebAuthnAssertionOptionsIn(BaseModel):
    intent_id: str | None = None


class WebAuthnAssertionVerifyIn(BaseModel):
    credential: dict[str, Any]




class WebAuthnCredentialOut(BaseModel):
    id: str
    credential_id_masked: str
    nickname: str | None = None
    transports: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None
    last_used_at: datetime | None = None
    is_active: bool


class WebAuthnCredentialPatchIn(BaseModel):
    nickname: str | None = None

class SigningContextOut(BaseModel):
    request_id: str
    signer_id: str
    status: str
    title: str
    doc_hash: str
    placements: list[FieldPlacement]


class VerifyOut(BaseModel):
    valid: bool
    policy_code: str | None = None
    policy_minimum_level: str | None = None
    achieved_level: str | None = None
    policy_compliant: bool
    finalized_with_fallback: bool
    downgrade_reason_code: str | None = None
    storage_integrity_valid: bool
    signature_present: bool
    cryptographically_valid: bool
    timestamp_present: bool
    timestamp_valid: bool | None = None
    validation_status: str = "NOT_RUN"
    validation_last_checked_at: datetime | None = None
    title: str | None = None
    request_status: str | None = None
    signers: list[dict[str, Any]] = Field(default_factory=list)
    document_sha256: str | None = None
    artifact_sha256: str | None = None
    appearance_applied: bool = False
    cryptographic_signature_applied: bool = False


class ArtifactValidationOut(BaseModel):
    artifact_id: str
    policy_code: str | None = None
    policy_minimum_level: str | None = None
    achieved_level: str | None = None
    policy_compliant: bool
    finalized_with_fallback: bool
    storage_integrity_valid: bool
    signature_present: bool
    cryptographically_valid: bool
    timestamp_present: bool
    timestamp_valid: bool | None = None
    cryptographic_validation_status: str
    certificate_subject: str | None = None
    certificate_serial: str | None = None
    signing_time: datetime | None = None
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    validation_last_checked_at: datetime | None = None


class ArtifactVerifyLinkOut(BaseModel):
    artifact_id: str
    token_id: str
    token_status: str
    public_verify_url: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime




class ArtifactAccessOut(BaseModel):
    artifact_available: bool
    preview_allowed: bool
    download_allowed: bool
    public_preview_allowed: bool
    public_download_allowed: bool
    public_evidence_summary_allowed: bool
    watermark_public_downloads: bool
    require_auth_for_original_artifact: bool
    filename: str | None = None
    content_type: str = "application/pdf"
    size_bytes: int | None = None


class HashCompareIn(BaseModel):
    provided_sha256: str | None = None
    file_base64: str | None = None
    compare_against: str = "artifact"


class HashCompareOut(BaseModel):
    compared_against: str
    provided_sha256: str
    expected_sha256: str
    match: bool
    message: str

class ProviderHealthOut(BaseModel):
    mode: str
    provider: str
    ok: bool
    message: str


class ProviderReadinessOut(BaseModel):
    configured_mode: str
    health_ok: bool
    sign_endpoint_ok: bool
    validate_endpoint_ok: bool
    timestamp_capable: bool | None = None
    last_checked_at: datetime
    supports_appearance_only: bool
    supports_crypto_required: bool
    supports_crypto_timestamp_required: bool
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PolicyOverrideIn(BaseModel):
    override_type: str
    justification: str
    approved_by_user_id: str | None = None
    expires_at: datetime | None = None


class PolicyOverrideOut(BaseModel):
    id: str
    override_type: str
    justification: str
    approved_by_user_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool


class EvidenceBundleOut(BaseModel):
    bundle_id: str
    request_id: str
    artifact_id: str | None = None
    bundle_sha256: str
    generated_at: datetime
    format: str


class TrustSummaryOut(BaseModel):
    total_requests: int
    completed_requests: int
    appearance_only_completions: int
    crypto_signed_completions: int
    timestamped_completions: int
    fallback_count: int
    policy_violation_count: int
    validation_failure_count: int


class RegistrationOptionsIn(BaseModel):
    display_name: str | None = None


class InboxItemOut(BaseModel):
    signature_request_id: str
    signer_id: str
    intent_id: str | None = None
    request_title: str
    request_status: str
    policy_code: str | None = None
    policy_minimum_level: str | None = None
    achieved_level: str | None = None
    signer_status: str
    expires_at: datetime | None = None
    created_at: datetime
    requested_by: str | None = None
    doc_version_hash_short: str
    sign_url: str


class InboxOut(BaseModel):
    items: list[InboxItemOut] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class InboxCountOut(BaseModel):
    pending_count: int
    expiring_soon_count: int
