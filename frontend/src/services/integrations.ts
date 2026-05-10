import { apiGet, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";

export type IntegrationConfigStatus = "ACTIVE" | "DISABLED";

export type IntegrationConfig = {
  id: string;
  amo_id: string;
  integration_key: string;
  display_name: string;
  status: IntegrationConfigStatus;
  enabled: boolean;
  base_url?: string | null;
  signing_secret?: string | null;
  allowed_ips?: string | null;
  credentials_json?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type IntegrationConfigCreate = {
  integration_key: string;
  display_name: string;
  status?: IntegrationConfigStatus;
  enabled?: boolean;
  base_url?: string | null;
  signing_secret?: string | null;
  allowed_ips?: string | null;
  credentials_json?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
};

export type IntegrationConfigUpdate = Partial<IntegrationConfigCreate>;

export type IntegrationOutboundEvent = {
  id: string;
  amo_id: string;
  integration_id: string;
  event_type: string;
  payload_json: Record<string, unknown>;
  status: string;
  attempt_count: number;
  next_attempt_at?: string | null;
  last_error?: string | null;
  idempotency_key?: string | null;
  created_at: string;
};

function randomKey() {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `idem-${Date.now()}`;
}

export async function listIntegrationConfigs(): Promise<IntegrationConfig[]> {
  return apiGet<IntegrationConfig[]>("/integrations/configs", { headers: authHeaders() });
}

export async function createIntegrationConfig(payload: IntegrationConfigCreate): Promise<IntegrationConfig> {
  return apiPost<IntegrationConfig>("/integrations/configs", payload, {
    headers: {
      ...authHeaders(),
      "Idempotency-Key": randomKey(),
    },
  });
}

export async function updateIntegrationConfig(configId: string, payload: IntegrationConfigUpdate): Promise<IntegrationConfig> {
  return apiPut<IntegrationConfig>(`/integrations/configs/${encodeURIComponent(configId)}`, payload, {
    headers: {
      ...authHeaders(),
      "Idempotency-Key": randomKey(),
    },
  });
}

export async function listIntegrationOutbox(limit = 50): Promise<IntegrationOutboundEvent[]> {
  return apiGet<IntegrationOutboundEvent[]>(`/integrations/outbox?limit=${Math.max(1, Math.min(limit, 500))}`, { headers: authHeaders() });
}
