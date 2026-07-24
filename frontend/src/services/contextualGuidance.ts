import { getPlannerPreferences, updatePlannerPreferences } from "./workforce";

const ROOT_KEY = "_contextual_guidance";

type GuidanceMap = Record<string, Record<string, string>>;

function localKey(topic: string, version: number): string {
  return `amo_portal_help_seen:${topic}:v${version}`;
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
    const preference = await getPlannerPreferences();
    const guidance = parseGuidance(preference.filters_json as Record<string, unknown> | null | undefined);
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
    const preference = await getPlannerPreferences();
    const filters = { ...(preference.filters_json || {}) } as Record<string, unknown>;
    const guidance = { ...parseGuidance(filters) };
    guidance[topic] = { ...(guidance[topic] || {}), [String(version)]: acknowledgedAt };
    filters[ROOT_KEY] = guidance;
    await updatePlannerPreferences({ filters_json: filters });
  } catch {
    // The local acknowledgement remains available and can be synchronised later.
  }
}
