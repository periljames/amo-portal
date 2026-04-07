const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isUuidLike(value: string): boolean {
  return UUID_RE.test(value.trim());
}

export function toAuditReferenceSlug(reference: string): string {
  return reference
    .trim()
    .replace(/[\s/]+/g, "-")
    .replace(/[^a-zA-Z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .toUpperCase();
}

export function buildAuditWorkspacePath(params: {
  amoCode: string;
  department: string;
  auditRef: string;
}): string {
  return `/maintenance/${params.amoCode}/${params.department}/qms/audits/${toAuditReferenceSlug(params.auditRef)}`;
}
