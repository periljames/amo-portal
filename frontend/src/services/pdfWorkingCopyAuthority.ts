const authoritativeChecksums = new Map<string, string>();

function authorityKey(tenant: string, manualId: string, revisionId: string): string {
  return [tenant.toLowerCase(), manualId, revisionId].map(encodeURIComponent).join(":");
}

export function registerAuthoritativePdfSource(
  tenant: string,
  manualId: string,
  revisionId: string,
  sourceSha256: string | null | undefined,
): void {
  const checksum = String(sourceSha256 || "").trim().toLowerCase();
  const key = authorityKey(tenant, manualId, revisionId);
  if (checksum) authoritativeChecksums.set(key, checksum);
  else authoritativeChecksums.delete(key);
}

export function authoritativePdfSourceChecksum(
  tenant: string,
  manualId: string,
  revisionId: string,
): string | null {
  return authoritativeChecksums.get(authorityKey(tenant, manualId, revisionId)) || null;
}
