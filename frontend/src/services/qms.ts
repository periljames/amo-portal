// Compatibility facade for the mature QMS service surface.
//
// qmsLegacy retains the existing API helpers unchanged. The explicit resolver
// export below replaces only the old client-side audit-register scan with the
// bounded tenant-scoped resolver endpoint.
export * from "./qmsLegacy";
export { qmsResolveAudit } from "./qmsAuditResolveDirect";
