import { getCachedUser } from "../../services/auth";
import type { PdfReaderCapabilities } from "../../services/pdfReader";
import type { PdfWorkingCopyIdentity } from "./pdfWorkingCopyStore";

const CACHE_PREFIX = "amo-pdf-capabilities:v1";
const CACHE_MAX_AGE_MS = 30 * 60 * 1000;

type CachedCapabilities = {
  cachedAt: number;
  userId: string;
  capabilities: PdfReaderCapabilities;
};

function capabilityCacheKey(identity: PdfWorkingCopyIdentity): string {
  const userId = String(identity.userId || getCachedUser()?.id || "anonymous");
  return [
    CACHE_PREFIX,
    encodeURIComponent(userId),
    encodeURIComponent(identity.tenant.toLowerCase()),
    encodeURIComponent(identity.manualId),
    encodeURIComponent(identity.revisionId),
  ].join(":");
}

function validCapabilities(value: unknown): value is PdfReaderCapabilities {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<PdfReaderCapabilities>;
  return Boolean(
    String(candidate.source_sha256 || "").trim()
    && Number.isFinite(Number(candidate.page_count || 0))
    && typeof candidate.can_download_original === "boolean",
  );
}

export function readCachedPdfCapabilities(identity: PdfWorkingCopyIdentity): PdfReaderCapabilities | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(capabilityCacheKey(identity));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedCapabilities;
    const expectedUser = String(identity.userId || getCachedUser()?.id || "anonymous");
    if (
      parsed.userId !== expectedUser
      || Date.now() - Number(parsed.cachedAt || 0) > CACHE_MAX_AGE_MS
      || !validCapabilities(parsed.capabilities)
    ) {
      window.sessionStorage.removeItem(capabilityCacheKey(identity));
      return null;
    }
    return parsed.capabilities;
  } catch {
    return null;
  }
}

export function cachePdfCapabilities(
  identity: PdfWorkingCopyIdentity,
  capabilities: PdfReaderCapabilities,
): void {
  if (typeof window === "undefined" || !validCapabilities(capabilities)) return;
  try {
    const userId = String(identity.userId || getCachedUser()?.id || "anonymous");
    const payload: CachedCapabilities = {
      cachedAt: Date.now(),
      userId,
      capabilities,
    };
    window.sessionStorage.setItem(capabilityCacheKey(identity), JSON.stringify(payload));
  } catch {
    // Capability caching is an acceleration only; the live request remains authoritative.
  }
}

export function clearCachedPdfCapabilities(identity: PdfWorkingCopyIdentity): void {
  if (typeof window === "undefined") return;
  try { window.sessionStorage.removeItem(capabilityCacheKey(identity)); } catch { /* no-op */ }
}
