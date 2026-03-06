export type ESignRequestStatus = "DRAFT" | "SENT" | "IN_PROGRESS" | "COMPLETED" | "EXPIRED" | "CANCELLED";

export type SignaturePolicyLevel =
  | "BASIC_APPROVAL"
  | "APPEARANCE_ONLY_ALLOWED"
  | "CRYPTO_REQUIRED"
  | "CRYPTO_AND_TIMESTAMP_REQUIRED";

export type VerifyResult = {
  valid: boolean;
  policy_code: string | null;
  policy_minimum_level: string | null;
  achieved_level: string | null;
  policy_compliant: boolean;
  finalized_with_fallback: boolean;
  downgrade_reason_code: string | null;
  storage_integrity_valid: boolean;
  signature_present: boolean;
  cryptographically_valid: boolean;
  timestamp_present: boolean;
  timestamp_valid: boolean | null;
  validation_status: string;
  validation_last_checked_at: string | null;
  title: string | null;
  request_status: ESignRequestStatus | null;
  signers: Array<{ display_name?: string | null; email?: string | null; status: string; approved_at?: string | null }>;
  document_sha256: string | null;
  artifact_sha256: string | null;
  appearance_applied: boolean;
  cryptographic_signature_applied: boolean;
};

export type RequestCreatePayload = {
  document_id: string;
  source_storage_ref: string;
  source_version_id?: string | null;
  title: string;
  message?: string | null;
  expires_at?: string | null;
  policy_code?: string | null;
  signers: Array<{ signer_type: "INTERNAL_USER" | "EXTERNAL_EMAIL"; user_id?: string | null; email?: string | null; display_name?: string | null; signing_order?: number }>;
  field_placements: Array<{ page: number; x: number; y: number }>;
};

export type RequestCreateResult = {
  request_id: string;
  doc_version_id: string;
  doc_hash: string;
  policy_code: string;
  policy_minimum_level: string;
};

export type SigningContext = {
  request_id: string;
  signer_id: string;
  status: string;
  title: string;
  doc_hash: string;
  placements: Array<{ page: number; x: number; y: number }>;
};

export type ArtifactValidation = {
  artifact_id: string;
  policy_code: string | null;
  policy_minimum_level: string | null;
  achieved_level: string | null;
  policy_compliant: boolean;
  finalized_with_fallback: boolean;
  storage_integrity_valid: boolean;
  signature_present: boolean;
  cryptographically_valid: boolean;
  timestamp_present: boolean;
  timestamp_valid: boolean | null;
  cryptographic_validation_status: string;
  certificate_subject: string | null;
  certificate_serial: string | null;
  signing_time: string | null;
  validation_summary: Record<string, unknown>;
  validation_last_checked_at: string | null;
};

export type ArtifactVerifyLink = {
  artifact_id: string;
  token_id: string;
  token_status: string;
  public_verify_url: string;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type ProviderReadiness = {
  configured_mode: string;
  health_ok: boolean;
  sign_endpoint_ok: boolean;
  validate_endpoint_ok: boolean;
  timestamp_capable: boolean | null;
  last_checked_at: string;
  supports_appearance_only: boolean;
  supports_crypto_required: boolean;
  supports_crypto_timestamp_required: boolean;
  blocking_issues: string[];
  warnings: string[];
};

export type TrustSummary = {
  total_requests: number;
  completed_requests: number;
  appearance_only_completions: number;
  crypto_signed_completions: number;
  timestamped_completions: number;
  fallback_count: number;
  policy_violation_count: number;
  validation_failure_count: number;
};

export type EvidenceBundle = {
  bundle_id: string;
  request_id: string;
  artifact_id: string | null;
  bundle_sha256: string;
  generated_at: string;
  format: string;
};

export type PolicyOverride = {
  id: string;
  override_type: string;
  justification: string;
  approved_by_user_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
  expires_at: string | null;
  is_active: boolean;
};


export type ArtifactAccess = {
  artifact_available: boolean;
  preview_allowed: boolean;
  download_allowed: boolean;
  public_preview_allowed: boolean;
  public_download_allowed: boolean;
  public_evidence_summary_allowed: boolean;
  watermark_public_downloads: boolean;
  require_auth_for_original_artifact: boolean;
  filename: string | null;
  content_type: string;
  size_bytes: number | null;
};

export type HashCompareResult = {
  compared_against: string;
  provided_sha256: string;
  expected_sha256: string;
  match: boolean;
  message: string;
};


export type WebAuthnCredential = {
  id: string;
  credential_id_masked: string;
  nickname: string | null;
  transports: string[];
  created_at: string;
  updated_at: string | null;
  last_used_at: string | null;
  is_active: boolean;
};

export type InboxItem = {
  signature_request_id: string;
  signer_id: string;
  intent_id: string | null;
  request_title: string;
  request_status: string;
  policy_code: string | null;
  policy_minimum_level: string | null;
  achieved_level: string | null;
  signer_status: string;
  expires_at: string | null;
  created_at: string;
  requested_by: string | null;
  doc_version_hash_short: string;
  sign_url: string;
};

export type InboxResponse = {
  items: InboxItem[];
  page: number;
  page_size: number;
  total: number;
};

export type InboxCount = {
  pending_count: number;
  expiring_soon_count: number;
};


export type ESignNotification = {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link_path: string;
  request_id: string | null;
  created_at: string;
  read_at: string | null;
  dismissed_at: string | null;
};

export type ESignNotificationCount = {
  unread_count: number;
};
