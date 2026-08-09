import { getToken } from "./auth";

const ALLOWED_EVENTS = new Set([
  "module_opened",
  "workflow_started",
  "workflow_completed",
  "workflow_failed",
  "report_generated",
  "search_used",
  "export_used",
  "ai_assist_used",
  "bulk_action_used",
  "approval_completed",
]);

const SAFE_METADATA_KEYS = new Set([
  "source",
  "workflow",
  "feature",
  "route_name",
  "document_type",
  "aircraft_family",
  "result_code",
  "entry_point",
]);

function safeMetadata(metadata?: Record<string, unknown>): Record<string, string> {
  const output: Record<string, string> = {};
  Object.entries(metadata || {}).forEach(([key, value]) => {
    if (!SAFE_METADATA_KEYS.has(key) || value == null || typeof value === "object") return;
    output[key] = String(value).slice(0, 128);
  });
  return output;
}

export async function emitProductEvent(input: {
  event_type: string;
  module: string;
  outcome?: "SUCCESS" | "FAILED" | "CANCELLED" | "UNKNOWN";
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}): Promise<boolean> {
  const token = getToken();
  if (!token || !ALLOWED_EVENTS.has(input.event_type)) return false;
  try {
    const response = await fetch("/platform/product-events", {
      method: "POST",
      credentials: "include",
      keepalive: true,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        event_type: input.event_type,
        module: input.module.toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").slice(0, 64),
        outcome: input.outcome || "UNKNOWN",
        duration_ms: input.duration_ms == null ? undefined : Math.max(0, Math.min(86_400_000, Math.round(input.duration_ms))),
        metadata: safeMetadata(input.metadata),
      }),
    });
    return response.ok;
  } catch {
    // Product analytics is deliberately fail-open. It must never block portal work.
    return false;
  }
}

export async function trackProductWorkflow<T>(input: {
  module: string;
  workflow: string;
  source?: string;
  feature?: string;
  operation: () => Promise<T>;
}): Promise<T> {
  const startedAt = Date.now();
  void emitProductEvent({
    event_type: "workflow_started",
    module: input.module,
    metadata: {
      workflow: input.workflow,
      source: input.source,
      feature: input.feature,
    },
  });

  try {
    const result = await input.operation();
    void emitProductEvent({
      event_type: "workflow_completed",
      module: input.module,
      outcome: "SUCCESS",
      duration_ms: Date.now() - startedAt,
      metadata: {
        workflow: input.workflow,
        source: input.source,
        feature: input.feature,
      },
    });
    return result;
  } catch (error) {
    void emitProductEvent({
      event_type: "workflow_failed",
      module: input.module,
      outcome: "FAILED",
      duration_ms: Date.now() - startedAt,
      metadata: {
        workflow: input.workflow,
        source: input.source,
        feature: input.feature,
      },
    });
    throw error;
  }
}
