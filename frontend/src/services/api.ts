// src/services/api.ts

// Base URL for the FastAPI backend
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

async function request<T>(
  method: HttpMethod,
  path: string,
  body?: BodyInit,
  init: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    method,
    body,
    ...init,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  return (await res.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body?: BodyInit,
  init: RequestInit = {}
): Promise<T> {
  return request<T>("POST", path, body, init);
}

export async function apiGet<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  return request<T>("GET", path, undefined, init);
}
