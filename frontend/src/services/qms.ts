// Compatibility facade for the mature QMS service surface.
//
// qmsLegacy retains the existing API helpers unchanged. The explicit exports
// below replace compatibility calls that must be tenant-scoped and bounded by
// the canonical /api/maintenance/:amoCode/quality contract.
export * from "./qmsLegacy";
export { qmsResolveAudit } from "./qmsAuditResolveDirect";
export { qmsListAuditPersonnelOptions } from "./qmsAuditPersonnel";
