"""Portal-side typed Microsoft 365 Document Control integration (no Office editing SDK).""";
import { getApiBaseUrl } from "./config";
import { authHeaders } from "./auth";
import { portalFetch } from "./offlineHttp";

export type MicrosoftConnection = {
  configured: boolean;
  connected: boolean;
  status: string;
  microsoft_user_name?: string | null;
  microsoft_tenant_id?: string | null;
  can_configure: boolean;
  last_connected_at?: string | null;
  last_error?: string | null;
};

export type MicrosoftLinkedFile = {
  manual_id: string;
  item_name: string;
  web_url: string;
  observed_etag: string;
  modified_at?: string | null;
  size?: number | null;
  last_imported_etag?: string | null;
  last_imported_revision_id?: string | null;
  newer_version_available: boolean;
  imported: boolean;
};

export type MicrosoftLinkState = { linked: boolean; file: MicrosoftLinkedFile | null };

function route(tenant: string, path: string): string {
  return "/doc-control/workspace/t/" + encodeURIComponent(tenant) + path;
}

async function request<T>(path: string, method = "GET", payload?: object): Promise<T> {
  const response = await portalFetch(getApiBaseUrl() + path, {
    method,
    headers: {
      ...authHeaders(),
      ...(payload ? { "Content-Type": "application/json" } : {}),
    },
    ...(payload ? { body: JSON.stringify(payload) } : {}),
    credentials: "same-origin",
  });
  if (!response.ok) {
    let reason = "Microsoft 365 request failed (" + response.status + ")";
    try {
      const body = await response.json();
      reason = typeof body.detail === "string" ? body.detail : body.detail?.message || reason;
    } catch { /* preserve HTTP status */ }
    throw new Error(reason);
  }
  return response.json() as Promise<T>;
}

export function microsoftConnection(tenant: string): Promise<MicrosoftConnection> {
  return request(route(tenant, "/microsoft365/connection"));
}
export function startMicrosoftConnection(tenant: string): Promise<{ authorization_url: string }> {
  return request(route(tenant, "/microsoft365/connect"), "POST");
}
export function disconnectMicrosoft(tenant: string): Promise<{ status: string }> {
  return request(route(tenant, "/microsoft365/connection"), "DELETE");
}
function fileRoute(tenant: string, manualId: string): string {
  return route(tenant, "/documents/" + encodeURIComponent(manualId) + "/microsoft365");
}
export function getMicrosoftDocument(tenant: string, manualId: string): Promise<MicrosoftLinkState> {
  return request(fileRoute(tenant, manualId));
}
export function linkMicrosoftDocument(tenant: string, manualId: string, shareUrl: string): Promise<MicrosoftLinkState> {
  return request(fileRoute(tenant, manualId), "POST", { share_url: shareUrl });
}
export function checkMicrosoftDocument(tenant: string, manualId: string): Promise<MicrosoftLinkState> {
  return request(fileRoute(tenant, manualId) + "/check-updates", "POST");
}
export function unlinkMicrosoftDocument(tenant: string, manualId: string): Promise<MicrosoftLinkState> {
  return request(fileRoute(tenant, manualId), "DELETE");
}
export function importMicrosoftDocument(
  tenant: string, manualId: string,
  revisionNumber: string, issueNumber: string, expectedEtag: string,
): Promise<{ manual_id: string; revision_id: string; source_sha256: string }> {
  return request(fileRoute(tenant, manualId) + "/import", "POST", {
    revision_number: revisionNumber,
    issue_number: issueNumber,
    expected_etag: expectedEtag,
  });
}
