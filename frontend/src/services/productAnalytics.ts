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

const MAX_ANALYTICS_IN_FLIGHT = 2;
let analyticsInFlight = 0;
const analyticsWaiters: Array<() => void> = [];

function safeMetadata(metadata?: Record<string, unknown>): Record<string, string> {
  const output: Record<string, string> = {};
  Object.entries(metadata || {}).forEach(([key, value]) => {
    if (!SAFE_METADATA_KEYS.has(key) || value == null || typeof value === "object") return;
    output[key] = String(value).slice(0, 128);
  });
  return output;
}

async function acquireAnalyticsSlot(): Promise<void> {
  if (analyticsInFlight < MAX_ANALYTICS_IN_FLIGHT) {
    analyticsInFlight += 1;
    return;
  }
  await new Promise<void>((resolve) => analyticsWaiters.push(resolve));
  analyticsInFlight += 1;
}

function releaseAnalyticsSlot(): void {
  analyticsInFlight = Math.max(0, analyticsInFlight - 1);
  analyticsWaiters.shift()?.();
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

  await acquireAnalyticsSlot();
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
  } finally {
    releaseAnalyticsSlot();
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
  const metadata = {
    workflow: input.workflow,
    source: input.source,
    feature: input.feature,
  };

  let operationPromise: Promise<T>;
  try {
    // Invoke the authoritative business operation first. Analytics is secondary
    // and must not become the first network side effect or alter domain request
    // ordering, mocking contracts, idempotency, or failure semantics.
    operationPromise = input.operation();
  } catch (error) {
    void emitProductEvent({
      event_type: "workflow_started",
      module: input.module,
      metadata,
    });
    void emitProductEvent({
      event_type: "workflow_failed",
      module: input.module,
      outcome: "FAILED",
      duration_ms: Date.now() - startedAt,
      metadata,
    });
    throw error;
  }

  void emitProductEvent({
    event_type: "workflow_started",
    module: input.module,
    metadata,
  });

  try {
    const result = await operationPromise;
    void emitProductEvent({
      event_type: "workflow_completed",
      module: input.module,
      outcome: "SUCCESS",
      duration_ms: Date.now() - startedAt,
      metadata,
    });
    return result;
  } catch (error) {
    void emitProductEvent({
      event_type: "workflow_failed",
      module: input.module,
      outcome: "FAILED",
      duration_ms: Date.now() - startedAt,
      metadata,
    });
    throw error;
  }
}
