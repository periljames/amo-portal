// src/services/amoAssets.ts

import { API_BASE_URL } from "./config";
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
  const res = await fetch(withAmoId(`${API_BASE_URL}/accounts/amo-assets/me`, amoId), {
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

  const res = await fetch(withAmoId(`${API_BASE_URL}/accounts/amo-assets/logo`, amoId), {
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

  return (await res.json()) as AmoAssetRead;
}

export async function uploadAmoTemplate(file: File, amoId?: string | null): Promise<AmoAssetRead> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(withAmoId(`${API_BASE_URL}/accounts/amo-assets/template`, amoId), {
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

  return (await res.json()) as AmoAssetRead;
}

export async function downloadAmoAsset(
  kind: "logo" | "template",
  amoId?: string | null
): Promise<Blob> {
  const res = await fetch(withAmoId(`${API_BASE_URL}/accounts/amo-assets/${kind}`, amoId), {
    method: "GET",
    headers: buildAuthHeader(),
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  return await res.blob();
}
