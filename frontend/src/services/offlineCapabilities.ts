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

/** Every mutation is classified; only reviewed, guarded drafts enter the outbox. */
export const OFFLINE_CAPABILITY_REGISTRY: readonly OfflineCapabilityRule[] = [
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
