import { apiRequest, qualityPath } from "./apiClient";

export type QmsMailIdentity = {
  tenant_name: string;
  shared_domain: string;
  shared_sender: string;
  custom_domains: string[];
  from_name: string;
  from_email: string;
  reply_to: string;
  effective_reply_to: string;
  reply_mode: "CUSTOM" | "QUALITY_ROLES";
  sender_mode: "SHARED" | "CUSTOM";
  enabled: boolean;
  has_override: boolean;
  can_manage: boolean;
  provider_status: string;
  sending_mode: string;
  ready: boolean;
  status_detail: string;
  reply_note: string;
};

export type QmsMailIdentityUpdate = {
  from_name: string;
  from_email: string;
  reply_to: string;
  enabled: boolean;
  reason: string;
};

export type QmsMailTestResult = {
  email_log_id: string;
  status: string;
  delivery_status: string;
  provider_message_id: string | null;
  detail: string;
};

export const qmsMailIdentityApi = {
  get: (amoCode: string) =>
    apiRequest<QmsMailIdentity>(qualityPath(amoCode, "/mail-identity"), { cacheTtlMs: 0, headers: { "X-AMO-Silent-Error": "1" } }),
  save: (amoCode: string, change: QmsMailIdentityUpdate) =>
    apiRequest<QmsMailIdentity>(qualityPath(amoCode, "/mail-identity"), {
      method: "PUT",
      headers: { "X-AMO-Silent-Error": "1" },
      body: JSON.stringify(change),
      cacheTtlMs: 0,
    }),
  test: (amoCode: string) =>
    apiRequest<QmsMailTestResult>(qualityPath(amoCode, "/mail-identity/test"), {
      method: "POST",
      headers: { "X-AMO-Silent-Error": "1" },
      cacheTtlMs: 0,
    }),
};
