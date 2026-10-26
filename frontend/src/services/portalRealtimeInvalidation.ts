const MODULE_MARKERS: Record<string, readonly string[]> = {
  quality: ["qms", "quality", "audit", "finding", "car", "capa", "assurance"],
  training: ["training", "qualification", "competency"],
  rostering: ["rostering", "roster", "workforce", "attendance"],
  workforce: ["workforce", "attendance", "timesheet", "leave", "rostering", "roster"],
  work: ["work", "task", "work-order", "work-orders", "maintenance", "planning", "production", "crs"],
  tasks: ["tasks", "task", "personal-task"],
  fleet: ["fleet", "aircraft", "utilisation", "utilization"],
  documents: ["document", "documents", "doc-control", "manual", "manuals", "dms"],
  doc_control: ["document", "documents", "doc-control", "manual", "manuals", "dms"],
  records: ["records", "technical-records"],
  technical_records: ["records", "technical-records"],
  reliability: ["reliability", "ehm", "engine", "octm"],
  stores: ["stores", "inventory", "stock", "part", "parts", "procurement"],
  inventory: ["stores", "inventory", "stock", "part", "parts"],
  procurement: ["procurement", "inventory", "purchase", "supplier"],
  finance: ["finance", "billing", "invoice", "invoices"],
  accounts: ["accounts", "admin", "user", "users", "access", "permissions"],
};

function words(value: string): string[] {
  return value.replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2").replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase().split(/[^a-z0-9-]+/).filter(Boolean);
}

export function realtimeQueryMarkers(event: { type: string; entityType: string; metadata?: Record<string, unknown> }): string[] {
  const tokens = words(`${event.metadata?.module || ""} ${event.type} ${event.entityType}`);
  const matches = Object.entries(MODULE_MARKERS).filter(([module, markers]) =>
    tokens.includes(module) || (module.includes("_") && words(module).every((part) => tokens.includes(part)))
    || markers.some((marker) => tokens.includes(marker)));
  return [...new Set(matches.flatMap(([, markers]) => [...markers]))];
}

export function queryMatchesRealtimeMarkers(key: readonly unknown[], markers: readonly string[]): boolean {
  // DMS approval/revision events also change the controlled-document selectors
  // and evidence authority shown in QMS, without changing frozen fieldwork rows.
  if (markers.includes("documents") && key.some((part) => typeof part === "string" && [
    "qms-current-dms-checklists", "qms-canonical-document-control-documents",
    "qms-audit-preparation-context", "qms-audit-preparation-readiness",
    "qms-governed-audit-document-requests", "qms-audit-applicability-context", "checklist-evidence-candidates",
  ].includes(part))) return true;
  // Query names commonly have a module prefix: qms-audit, training-person, etc.
  return key.some((part) => typeof part === "string" && markers.some((marker) =>
    part.toLowerCase() === marker || part.toLowerCase().startsWith(`${marker}-`)
    || part.toLowerCase().startsWith(`${marker}/`)));
}
