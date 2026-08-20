import { apiRequest, clearQmsApiResponseCache, qmsPath } from "./apiClient";

export type ProviderKind =
  | "SUPPLIER"
  | "CONTRACTOR"
  | "SUBCONTRACTOR"
  | "SERVICE_PROVIDER"
  | "CONSULTANT"
  | "LABORATORY"
  | "CALIBRATION_PROVIDER"
  | "OTHER";

export type ProviderStatus =
  | "PROSPECTIVE"
  | "UNDER_REVIEW"
  | "CONDITIONALLY_APPROVED"
  | "APPROVED"
  | "RESTRICTED"
  | "SUSPENDED"
  | "EXPIRED"
  | "REJECTED"
  | "ARCHIVED";

export type ProviderRisk = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ContractStatus = "DRAFT" | "ACTIVE" | "SUSPENDED" | "EXPIRED" | "TERMINATED" | "SUPERSEDED";
export type EvidenceStatus = "PENDING" | "VERIFIED" | "EXPIRED" | "REJECTED" | "SUPERSEDED";

export type ProviderGovernanceSummary = {
  total: number;
  approved: number;
  suspended: number;
  review_due: number;
  required_contract_missing: number;
  contracts_expiring: number;
  evidence_expiring: number;
};

export type ProviderListItem = {
  id: number;
  supplier_code: string;
  legal_name: string;
  trading_name?: string | null;
  status: ProviderStatus;
  risk_level: ProviderRisk;
  provider_kind: ProviderKind;
  contract_required: boolean;
  oversight_owner_user_id?: string | null;
  next_review_due_on?: string | null;
  governance_version: number;
  active_scope_count: number;
  active_contract_count: number;
  verified_evidence_count: number;
  review_due: boolean;
  contract_gap: boolean;
};

export type ProviderContract = {
  id: string;
  supplier_id: number;
  contract_number: string;
  title: string;
  status: ContractStatus;
  effective_status: ContractStatus;
  scope_text: string;
  effective_on?: string | null;
  expires_on?: string | null;
  termination_notice_days?: number | null;
  renewal_terms?: string | null;
  controlled_document_id?: string | null;
  controlled_document_revision?: string | null;
  owner_user_id?: string | null;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  transition_reason?: string | null;
  version: number;
};

export type ProviderEvidence = {
  id: string;
  supplier_id: number;
  contract_id?: string | null;
  evidence_type: string;
  source_system: string;
  source_id: string;
  title: string;
  status: EvidenceStatus;
  effective_status: EvidenceStatus;
  valid_from?: string | null;
  valid_until?: string | null;
  verified_by_user_id?: string | null;
  verified_at?: string | null;
  notes?: string | null;
};

export type ProviderApprovalScope = {
  id: number;
  site_code: string;
  category: string;
  product_family: string;
  manufacturer?: string | null;
  authority: string;
  approval_number?: string | null;
  status: string;
  effective_on?: string | null;
  expires_on?: string | null;
  restrictions?: string | null;
  incoming_inspection_level?: string | null;
  evidence_reference?: string | null;
  qms_evaluation_id?: string | null;
  qms_audit_id?: string | null;
};

export type ProviderDetail = ProviderListItem & {
  supplier_type?: string | null;
  qms_supplier_id?: string | null;
  email?: string | null;
  phone?: string | null;
  website?: string | null;
  country?: string | null;
  physical_address?: string | null;
  quality_contact_name?: string | null;
  quality_contact_email?: string | null;
  notes?: string | null;
  approved_at?: string | null;
  suspended_at?: string | null;
  suspension_reason?: string | null;
  profile_id?: string | null;
  review_interval_days?: number | null;
  last_reviewed_on?: string | null;
  scope_summary?: string | null;
  quality_requirements?: string | null;
  approval_scopes: ProviderApprovalScope[];
  contracts: ProviderContract[];
  evidence: ProviderEvidence[];
  allowed_transitions: ProviderStatus[];
};

export type ProviderListResponse = {
  items: ProviderListItem[];
  total: number;
  limit: number;
  offset: number;
};

function write<T>(amoCode: string, suffix: string, method: "POST" | "PATCH", body: unknown): Promise<T> {
  clearQmsApiResponseCache();
  return apiRequest<T>(qmsPath(amoCode, suffix), {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getProviderGovernanceSummary(amoCode: string): Promise<ProviderGovernanceSummary> {
  return apiRequest<ProviderGovernanceSummary>(qmsPath(amoCode, "/suppliers/governance"));
}

export function getExternalProviders(
  amoCode: string,
  filters: { search?: string; status?: string; providerKind?: string; riskLevel?: string } = {},
): Promise<ProviderListResponse> {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  if (filters.providerKind) params.set("provider_kind", filters.providerKind);
  if (filters.riskLevel) params.set("risk_level", filters.riskLevel);
  const query = params.toString();
  return apiRequest<ProviderListResponse>(qmsPath(amoCode, `/suppliers/providers${query ? `?${query}` : ""}`));
}

export function getExternalProvider(amoCode: string, providerId: number): Promise<ProviderDetail> {
  return apiRequest<ProviderDetail>(qmsPath(amoCode, `/suppliers/providers/${providerId}`));
}

export function createExternalProvider(amoCode: string, body: unknown): Promise<ProviderDetail> {
  return write<ProviderDetail>(amoCode, "/suppliers/providers", "POST", body);
}

export function updateExternalProviderProfile(amoCode: string, providerId: number, body: unknown): Promise<ProviderDetail> {
  return write<ProviderDetail>(amoCode, `/suppliers/providers/${providerId}/profile`, "PATCH", body);
}

export function transitionExternalProvider(amoCode: string, providerId: number, body: unknown): Promise<ProviderDetail> {
  return write<ProviderDetail>(amoCode, `/suppliers/providers/${providerId}/transition`, "POST", body);
}

export function createProviderContract(amoCode: string, providerId: number, body: unknown): Promise<ProviderContract> {
  return write<ProviderContract>(amoCode, `/suppliers/providers/${providerId}/contracts`, "POST", body);
}

export function transitionProviderContract(
  amoCode: string,
  providerId: number,
  contractId: string,
  body: unknown,
): Promise<ProviderContract> {
  return write<ProviderContract>(amoCode, `/suppliers/providers/${providerId}/contracts/${encodeURIComponent(contractId)}/transition`, "POST", body);
}

export function createProviderEvidence(amoCode: string, providerId: number, body: unknown): Promise<ProviderEvidence> {
  return write<ProviderEvidence>(amoCode, `/suppliers/providers/${providerId}/evidence`, "POST", body);
}

export function decideProviderEvidence(
  amoCode: string,
  providerId: number,
  evidenceId: string,
  body: unknown,
): Promise<ProviderEvidence> {
  return write<ProviderEvidence>(amoCode, `/suppliers/providers/${providerId}/evidence/${encodeURIComponent(evidenceId)}/decision`, "POST", body);
}
