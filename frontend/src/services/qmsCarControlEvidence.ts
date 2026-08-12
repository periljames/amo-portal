import { apiRequest, qmsPath } from "./apiClient";
import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import type { CARAttachmentOut } from "./qms";

function evidencePath(amoCode: string, carId: string, suffix = ""): string {
  return qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/control-loop/attachments${suffix}`);
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

export function listCarControlEvidence(amoCode: string, carId: string): Promise<CARAttachmentOut[]> {
  return apiRequest<CARAttachmentOut[]>(evidencePath(amoCode, carId), { cacheTtlMs: 2_000 });
}

export async function uploadCarControlEvidence(amoCode: string, carId: string, file: File): Promise<CARAttachmentOut> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${getApiBaseUrl()}${evidencePath(amoCode, carId)}`, {
    method: "POST",
    headers: requestHeaders(),
    body: formData,
    credentials: "include",
  });
  await assertResponse(response);
  return (await response.json()) as CARAttachmentOut;
}

export async function downloadCarControlEvidence(amoCode: string, carId: string, attachmentId: string): Promise<Blob> {
  const response = await fetch(
    `${getApiBaseUrl()}${evidencePath(amoCode, carId, `/${encodeURIComponent(attachmentId)}/download`)}`,
    {
      method: "GET",
      headers: requestHeaders(),
      credentials: "include",
    },
  );
  await assertResponse(response);
  return response.blob();
}

export async function deleteCarControlEvidence(amoCode: string, carId: string, attachmentId: string): Promise<void> {
  await apiRequest<void>(evidencePath(amoCode, carId, `/${encodeURIComponent(attachmentId)}`), { method: "DELETE" });
}
