import { getCachedUser, getContext } from "./auth";
import { apiJson, jsonBody } from "./typedApi";

const ROOT_KEY = "_contextual_guidance";
const PREFERENCES_PATH = "/workforce/planner-preferences";

type GuidanceMap = Record<string, Record<string, string>>;
type PlannerPreferenceLite = {
  filters_json?: Record<string, unknown> | null;
};

function getPlannerPreferencesLite(): Promise<PlannerPreferenceLite> {
  return apiJson(PREFERENCES_PATH, {
    offline: { cacheTtlMs: 30 * 60_000 },
  });
}

function updatePlannerPreferencesLite(
  payload: Pick<PlannerPreferenceLite, "filters_json">,
): Promise<PlannerPreferenceLite> {
  return apiJson(PREFERENCES_PATH, {
    method: "PATCH",
    body: jsonBody(payload),
  });
}

function localKey(topic: string, version: number): string {
  const user = getCachedUser();
  const context = getContext();
  const tenantId = user?.amo_id || context.amoCode || context.amoSlug || "tenant";
  const userId = user?.id || "anonymous";
  return `amo_portal_help_seen:${tenantId}:${userId}:${topic}:v${version}`;
}

function parseGuidance(filters: Record<string, unknown> | null | undefined): GuidanceMap {
  const value = filters?.[ROOT_KEY];
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as GuidanceMap;
}

export function localGuidanceAcknowledged(topic: string, version: number): boolean {
  if (typeof window === "undefined") return false;
  try {
    return Boolean(window.localStorage.getItem(localKey(topic, version)));
  } catch {
    return false;
  }
}

export async function guidanceAcknowledged(topic: string, version: number): Promise<boolean> {
  try {
    const preference = await getPlannerPreferencesLite();
    const guidance = parseGuidance(preference.filters_json);
    return Boolean(guidance[topic]?.[String(version)]);
  } catch {
    return localGuidanceAcknowledged(topic, version);
  }
}

export async function acknowledgeGuidance(topic: string, version: number): Promise<void> {
  const acknowledgedAt = new Date().toISOString();
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(localKey(topic, version), acknowledgedAt);
    } catch {
      // Local fallback is best effort.
    }
  }

  try {
    const preference = await getPlannerPreferencesLite();
    const filters = { ...(preference.filters_json || {}) } as Record<string, unknown>;
    const guidance = { ...parseGuidance(filters) };
    guidance[topic] = { ...(guidance[topic] || {}), [String(version)]: acknowledgedAt };
    filters[ROOT_KEY] = guidance;
    await updatePlannerPreferencesLite({ filters_json: filters });
  } catch {
    // The local acknowledgement remains available and can be synchronised later.
  }
}
