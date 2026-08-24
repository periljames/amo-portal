// Public QMS service surface. The explicit resolver uses the bounded,
// tenant-scoped endpoint instead of scanning the audit register client-side.
export * from "./qmsCore";
export * from "./qmsAuditPersonnel";
export { qmsResolveAudit } from "./qmsAuditResolveDirect";
