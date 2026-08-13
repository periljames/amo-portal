import { apiRequest, qmsPath } from "./apiClient";
import { getContext, getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import type { CARAttachmentOut } from "./qms";

export {
  downloadCarEvidencePack,
  qmsGetCarInvite,
  qmsListCarResponses,
} from "./qms";
export type {
  CARAssignee,
  CARAttachmentOut,
  CARResponseOut,
} from "./qms";

function activeAmoCode(): string {
  const context = getContext();
  const value = context.amoSlug || context.amoCode;
  if (!value) throw new Error("No active AMO context is available for governed CAR evidence.");
  return value;
}

function evidencePath(carId: string, suffix = ""): string {
  return qmsPath(activeAmoCode(), `/cars/${encodeURIComponent(carId)}/control-loop/attachments${suffix}`);
}

function requestHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function assertResponse(response: Response): Promise<void> {
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`QMS API ${response.status}: ${text || response.statusText}`);
  }
}

export function qmsListCarAttachments(carId: string): Promise<CARAttachmentOut[]> {
  return apiRequest<CARAttachmentOut[]>(evidencePath(carId), { cacheTtlMs: 2_000 });
}

export async function qmsUploadCarAttachment(carId: string, file: File): Promise<CARAttachmentOut> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${getApiBaseUrl()}${evidencePath(carId)}`, {
    method: "POST",
    headers: requestHeaders(),
    body: formData,
    credentials: "include",
  });
  await assertResponse(response);
  return (await response.json()) as CARAttachmentOut;
}

export async function qmsDownloadCarAttachmentBlob(carId: string, attachmentId: string): Promise<Blob> {
  const response = await fetch(
    `${getApiBaseUrl()}${evidencePath(carId, `/${encodeURIComponent(attachmentId)}/download`)}`,
    {
      method: "GET",
      headers: requestHeaders(),
      credentials: "include",
    },
  );
  await assertResponse(response);
  return response.blob();
}

export async function qmsDeleteCarAttachment(carId: string, attachmentId: string): Promise<void> {
  await apiRequest<void>(evidencePath(carId, `/${encodeURIComponent(attachmentId)}`), { method: "DELETE" });
}
