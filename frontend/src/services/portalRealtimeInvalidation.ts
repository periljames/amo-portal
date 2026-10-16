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
  return value.toLowerCase().split(/[^a-z0-9-]+/).filter(Boolean);
}

export function realtimeQueryMarkers(event: { type: string; entityType: string; metadata?: Record<string, unknown> }): string[] {
  const tokens = words(`${event.metadata?.module || ""} ${event.type} ${event.entityType}`);
  const matches = Object.entries(MODULE_MARKERS).filter(([module, markers]) =>
    tokens.includes(module) || markers.some((marker) => tokens.includes(marker)));
  return [...new Set(matches.flatMap(([, markers]) => [...markers]))];
}

export function queryMatchesRealtimeMarkers(key: readonly unknown[], markers: readonly string[]): boolean {
  // Query names commonly have a module prefix: qms-audit, training-person, etc.
  return key.some((part) => typeof part === "string" && markers.some((marker) =>
    part.toLowerCase() === marker || part.toLowerCase().startsWith(`${marker}-`)
    || part.toLowerCase().startsWith(`${marker}/`)));
}
