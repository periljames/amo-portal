// src/services/auth.ts
import { apiPost, API_BASE_URL } from "./api";
import type { TokenResponse } from "../types/auth";

const TOKEN_KEY = "amo_portal_token";
const AMO_KEY = "amo_code";
const DEPT_KEY = "amo_department";
const USER_KEY = "amo_current_user";

// shape of /users/me from backend
export type PortalUser = {
  id: number;
  email: string;
  full_name: string;
  role: string;
};

// ---- token helpers ----
export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// ---- context (AMO + department) ----
export function setContext(amoCode: string, department: string) {
  localStorage.setItem(AMO_KEY, amoCode);
  localStorage.setItem(DEPT_KEY, department);
}

export function getContext(): { amoCode: string | null; department: string | null } {
  return {
    amoCode: localStorage.getItem(AMO_KEY),
    department: localStorage.getItem(DEPT_KEY),
  };
}

export function clearContext() {
  localStorage.removeItem(AMO_KEY);
  localStorage.removeItem(DEPT_KEY);
}

// ---- current user cache ----
export function cacheCurrentUser(user: PortalUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getCachedUser(): PortalUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PortalUser;
  } catch {
    return null;
  }
}

export function clearCachedUser() {
  localStorage.removeItem(USER_KEY);
}

// ---- auth helpers ----
export function isAuthenticated(): boolean {
  return !!getToken();
}

export async function login(email: string, password: string): Promise<void> {
  const formData = new URLSearchParams();
  formData.append("username", email.trim());
  formData.append("password", password);
  formData.append("grant_type", "password");
  formData.append("scope", "");
  formData.append("client_id", "");
  formData.append("client_secret", "");

  const data = await apiPost<TokenResponse>("/auth/token", formData, {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });

  saveToken(data.access_token);
}

// hit /users/me with bearer token to get name/role
export async function fetchCurrentUser(): Promise<PortalUser> {
  const token = getToken();
  if (!token) {
    throw new Error("No auth token");
  }

  const res = await fetch(`${API_BASE_URL}/users/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  const user = (await res.json()) as PortalUser;
  cacheCurrentUser(user);
  return user;
}

export function logout() {
  clearToken();
  clearContext();
  clearCachedUser();
}
