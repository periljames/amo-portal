// src/services/amoAssets.ts

import { getApiBaseUrl } from "./config";
import { authHeaders, getToken, handleAuthFailure } from "./auth";

export type AmoAssetRead = {
  amo_id: string;
  crs_logo_filename?: string | null;
  crs_logo_content_type?: string | null;
  crs_logo_uploaded_at?: string | null;
  crs_template_filename?: string | null;
  crs_template_content_type?: string | null;
  crs_template_uploaded_at?: string | null;
};

function buildAuthHeader(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function withAmoId(path: string, amoId?: string | null): string {
  if (!amoId) return path;
  const sp = new URLSearchParams({ amo_id: amoId });
  return `${path}?${sp.toString()}`;
}

export async function getAmoAssets(amoId?: string | null): Promise<AmoAssetRead> {
  const res = await fetch(
    withAmoId(`${getApiBaseUrl()}/accounts/amo-assets/me`, amoId),
    {
    method: "GET",
    headers: authHeaders(),
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  return (await res.json()) as AmoAssetRead;
}

export async function uploadAmoLogo(file: File, amoId?: string | null): Promise<AmoAssetRead> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(
    withAmoId(`${getApiBaseUrl()}/accounts/amo-assets/logo`, amoId),
    {
    method: "POST",
    headers: buildAuthHeader(),
    body: form,
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

function buildSpeed(
  loadedBytes: number,
  totalBytes: number | undefined,
  startedAt: number
): TransferProgress {
  const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0.001);
  const megaBytesPerSecond = loadedBytes / (1024 * 1024) / elapsedSeconds;
  const megaBitsPerSecond = megaBytesPerSecond * 8;
  const percent = totalBytes ? Math.min((loadedBytes / totalBytes) * 100, 100) : undefined;
  return {
    loadedBytes,
    totalBytes,
    percent,
    megaBytesPerSecond,
    megaBitsPerSecond,
  };
}

function uploadAmoAsset(
  file: File,
  kind: "logo" | "template",
  amoId?: string | null,
  onProgress?: (progress: TransferProgress) => void
): Promise<AmoAssetRead> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(
    withAmoId(`${getApiBaseUrl()}/accounts/amo-assets/template`, amoId),
    {
    method: "POST",
    headers: buildAuthHeader(),
    body: form,
  });
}

export function uploadAmoLogo(
  file: File,
  amoId?: string | null,
  onProgress?: (progress: TransferProgress) => void
): Promise<AmoAssetRead> {
  return uploadAmoAsset(file, "logo", amoId, onProgress);
}

export function uploadAmoTemplate(
  file: File,
  amoId?: string | null,
  onProgress?: (progress: TransferProgress) => void
): Promise<AmoAssetRead> {
  return uploadAmoAsset(file, "template", amoId, onProgress);
}

export async function downloadAmoAsset(
  kind: "logo" | "template",
  amoId?: string | null,
  onProgress?: (progress: TransferProgress) => void
): Promise<Blob> {
  const res = await fetch(
    withAmoId(`${getApiBaseUrl()}/accounts/amo-assets/${kind}`, amoId),
    {
    method: "GET",
    headers: buildAuthHeader(),
  });
}
