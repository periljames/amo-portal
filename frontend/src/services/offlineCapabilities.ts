export type OfflineCapability = "draft-safe" | "live-only" | "unsupported";

export type OfflineCapabilityRule = {
  id: string;
  method: string | "*";
  path: RegExp;
  capability: OfflineCapability;
  label: string;
  commandRouteKey?: (path: string) => string;
  validate?: (body: Record<string, unknown>) => boolean;
};

const QMS_FIELDWORK_MUTATION_PATH = /^\/api\/maintenance\/[^/]+\/quality\/audits\/[^/]+\/checklist-items\/[^/]+\/fieldwork-mutations\/?$/;
const QMS_FIELDWORK_FINDING_PATH = /^\/api\/maintenance\/[^/]+\/quality\/audits\/[^/]+\/checklist-items\/[^/]+\/fieldwork-findings\/?$/;
const CANONICAL_CHECKLIST_RESPONSES = new Set([
  "COMPLIANT",
  "NONCOMPLIANT",
  "OBSERVATION",
  "NOT_APPLICABLE",
  "NOT_VERIFIED",
]);
const FIELDWORK_FINDING_RESPONSES = new Set(["NONCOMPLIANT", "OBSERVATION"]);
const FIELDWORK_FINDING_LEVELS = new Set(["LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4"]);
const FIELDWORK_FINDING_SEVERITIES = new Set(["MINOR", "MAJOR", "CRITICAL"]);

function validFieldworkEnvelope(body: Record<string, unknown>, operation: string): boolean {
  return typeof body.client_mutation_id === "string"
    && body.client_mutation_id.trim().length > 8
    && typeof body.device_id === "string"
    && body.device_id.trim().length > 8
    && Number.isFinite(Number(body.device_sequence))
    && Number(body.device_sequence) >= 0
    && typeof body.client_timestamp === "string"
    && !Number.isNaN(Date.parse(body.client_timestamp))
    && Number.isFinite(Number(body.base_version))
    && Number(body.base_version) >= 0
    && body.operation === operation
    && typeof body.reason === "string"
    && body.reason.trim().length > 0;
}

function validChecklistFieldwork(body: Record<string, unknown>): boolean {
  return validFieldworkEnvelope(body, "CHECKLIST_UPDATE")
    && typeof body.canonical_response_status === "string"
    && CANONICAL_CHECKLIST_RESPONSES.has(body.canonical_response_status);
}

function validChecklistFinding(body: Record<string, unknown>): boolean {
  return validFieldworkEnvelope(body, "CREATE_FINDING")
    && typeof body.canonical_response_status === "string"
    && FIELDWORK_FINDING_RESPONSES.has(body.canonical_response_status)
    && typeof body.level === "string"
    && FIELDWORK_FINDING_LEVELS.has(body.level)
    && typeof body.severity === "string"
    && FIELDWORK_FINDING_SEVERITIES.has(body.severity)
    && typeof body.description === "string"
    && body.description.trim().length > 0;
}

/** Every mutation is classified; only reviewed, guarded drafts enter the outbox. */
export const OFFLINE_CAPABILITY_REGISTRY: readonly OfflineCapabilityRule[] = [
  {
    id: "qms-checklist-fieldwork-update",
    method: "POST",
    path: QMS_FIELDWORK_MUTATION_PATH,
    capability: "draft-safe",
    label: "QMS checklist fieldwork update",
    validate: validChecklistFieldwork,
  },
  {
    id: "qms-checklist-fieldwork-finding",
    method: "POST",
    path: QMS_FIELDWORK_FINDING_PATH,
    capability: "draft-safe",
    label: "QMS checklist finding draft",
    validate: validChecklistFinding,
  },
  {
    id: "roster-assignment-create", method: "POST",
    path: /^\/rostering\/versions\/([^/]+)\/assignments\/?$/,
    capability: "draft-safe", label: "roster draft assignment",
    commandRouteKey: (path) => `rostering.version.assignment.create:${path.split("/")[3]}`,
    validate: (body) => typeof body.source_reference_id === "string" && body.source_reference_id.length > 3,
  },
  {
    id: "roster-assignment-update", method: "PATCH",
    path: /^\/rostering\/assignments\/([^/]+)\/?$/,
    capability: "draft-safe", label: "roster draft edit",
    commandRouteKey: (path) => `rostering.assignment.update:${path.split("/")[3]}`,
    validate: (body) => Number.isFinite(Number(body.expected_state_revision)),
  },
  {
    id: "work-task-update", method: "PUT",
    path: /^\/work-orders\/tasks\/([^/]+)\/?$/,
    capability: "draft-safe", label: "task draft edit",
    commandRouteKey: (path) => `work.task.update:${path.split("/")[3]}`,
    validate: (body) => typeof body.last_known_updated_at === "string" && body.last_known_updated_at.length > 8,
  },
  {
    id: "attendance-event-create", method: "POST",
    path: /^\/workforce\/attendance-events\/?$/,
    capability: "draft-safe", label: "attendance event",
    commandRouteKey: () => "workforce.attendance.create",
    validate: (body) => typeof body.idempotency_key === "string" && body.idempotency_key.length > 3,
  },
  {
    id: "authoritative-or-destructive", method: "*",
    path: /(?:\/approve|\/reject|\/submit|\/publish|\/sign-off|\/payroll|\/permissions|\/attachments|\/upload|\/restore|\/merge)(?:\/|$)/,
    capability: "live-only", label: "authoritative action",
  },
  { id: "all-deletes", method: "DELETE", path: /^\//, capability: "live-only", label: "deletion" },
  { id: "unreviewed-mutation", method: "*", path: /^\//, capability: "unsupported", label: "unreviewed mutation" },
] as const;

function jsonBody(raw: string | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown> : {};
  } catch { return {}; }
}

function normalized(path: string): string {
  return path.split("?")[0].replace(/\/+$/, "") || "/";
}

export function classifyOfflineMutation(path: string, method: string): OfflineCapabilityRule {
  const normalizedMethod = method.toUpperCase();
  const normalizedPath = normalized(path);
  return OFFLINE_CAPABILITY_REGISTRY.find((rule) => (
    (rule.method === "*" || rule.method === normalizedMethod) && rule.path.test(normalizedPath)
  ))!;
}

export function offlineCommandRouteKey(path: string, method: string): string | null {
  const rule = classifyOfflineMutation(path, method);
  return rule.capability === "draft-safe" && rule.commandRouteKey
    ? rule.commandRouteKey(normalized(path)) : null;
}

export function assertOfflineReplayAllowed(path: string, method: string, rawBody?: string): void {
  const rule = classifyOfflineMutation(path, method);
  if (rule.capability === "live-only") {
    throw new Error(`This ${rule.label} requires a live server and was not queued.`);
  }
  if (rule.capability !== "draft-safe") {
    throw new Error("This action is not approved for offline replay. Reconnect before completing it.");
  }
  if (rule.validate && !rule.validate(jsonBody(rawBody))) {
    throw new Error(`This ${rule.label} is missing its idempotency or revision guard and cannot be queued safely.`);
  }
}
