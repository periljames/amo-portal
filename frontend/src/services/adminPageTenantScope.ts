const ADMIN_PAGE_TENANT_SCOPE_KEY = "amoportal:admin-page-tenant-scope:v1";

export type AdminPageTenantScopeAttempt = {
  sequence: number;
  amo_id: string;
};

type AdminPageTenantScopeRecord = {
  user_id: string;
  amo_id: string;
};

let latestAttemptSequence = 0;

function sessionStore(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function normalise(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function payloadRecord(payload: unknown): Record<string, unknown> {
  if (typeof payload === "string") {
    try {
      const parsed = JSON.parse(payload) as unknown;
      return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
    } catch {
      return {};
    }
  }
  return payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
}

function contextMismatchError(message: string): Error {
  const error = new Error(message) as Error & { status?: number; code?: string };
  error.name = "AdminPageTenantScopeMismatchError";
  error.status = 409;
  error.code = "ADMIN_PAGE_TENANT_SCOPE_MISMATCH";
  return error;
}

/**
 * Capture the AMO chosen by this tab before the context request is sent.
 * Clearing the prior binding makes base operations fail closed while a switch
 * is pending. The sequence prevents older responses from replacing a newer
 * page selection when context requests complete out of order.
 */
export function beginAdminPageTenantScope(payload: unknown): AdminPageTenantScopeAttempt | null {
  const amoId = normalise(payloadRecord(payload).active_amo_id);
  if (!amoId) return null;
  const sequence = ++latestAttemptSequence;
  sessionStore()?.removeItem(ADMIN_PAGE_TENANT_SCOPE_KEY);
  return { sequence, amo_id: amoId };
}

/** Bind this tab only when the latest response confirms the requested AMO. */
export function completeAdminPageTenantScope(
  attempt: AdminPageTenantScopeAttempt | null,
  context: unknown,
): void {
  if (!attempt || attempt.sequence !== latestAttemptSequence) return;
  const store = sessionStore();
  if (!store) return;

  const record = context && typeof context === "object"
    ? context as Record<string, unknown>
    : {};
  const userId = normalise(record.user_id);
  const activeAmoId = normalise(record.active_amo_id);
  if (!userId || activeAmoId !== attempt.amo_id) {
    store.removeItem(ADMIN_PAGE_TENANT_SCOPE_KEY);
    throw contextMismatchError(
      "The server did not confirm the AMO selected by this setup page. Refresh the page before continuing.",
    );
  }

  const value: AdminPageTenantScopeRecord = {
    user_id: userId,
    amo_id: attempt.amo_id,
  };
  store.setItem(ADMIN_PAGE_TENANT_SCOPE_KEY, JSON.stringify(value));
}

/** Read only the AMO selected by this tab for the currently authenticated user. */
export function readAdminPageTenantScope(userId: string): string | null {
  const store = sessionStore();
  const expectedUserId = normalise(userId);
  if (!store || !expectedUserId) return null;
  try {
    const raw = store.getItem(ADMIN_PAGE_TENANT_SCOPE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AdminPageTenantScopeRecord>;
    if (normalise(parsed.user_id) !== expectedUserId) return null;
    return normalise(parsed.amo_id) || null;
  } catch {
    return null;
  }
}

export function clearAdminPageTenantScope(): void {
  sessionStore()?.removeItem(ADMIN_PAGE_TENANT_SCOPE_KEY);
}
