import { ApiClientError } from "../../services/apiClient";

export function settingsError(cause: unknown, fallback: string): string {
  const message = cause instanceof Error ? cause.message : fallback;
  if (cause instanceof ApiClientError) {
    if (cause.status === 401) return "Your session has expired. Sign in again before saving. Your entries are still on this page.";
    if (cause.status === 403) return "You no longer have permission to change these settings. Your entries are retained.";
    if (cause.transportFailure || cause.status >= 500) return "The server could not confirm the change. Your entries are retained. Check your connection, then review the current values before retrying.";
  }
  return message;
}
