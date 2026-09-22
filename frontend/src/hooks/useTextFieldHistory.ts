import { useCallback, useEffect, useMemo, useState } from "react";

const HISTORY_LIMIT = 12;
const HISTORY_VERSION = "v2";

export type FieldHistoryAreaScope = string;

function normalizeTenant(amoCode: string): string {
  return String(amoCode || "")
    .trim()
    .toUpperCase() || "UNKNOWN";
}

function normalizeAreaScope(areaScope?: string | null): string {
  const value = String(areaScope || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_-]+/g, "_");
  return value || "GENERAL";
}

/** Storage key: tenant first, then audit-area bucket, then field. */
export function fieldHistoryStorageKey(
  amoCode: string,
  fieldKey: string,
  areaScope?: string | null,
): string {
  return [
    "amo-portal",
    "qms-field-history",
    HISTORY_VERSION,
    normalizeTenant(amoCode),
    normalizeAreaScope(areaScope),
    String(fieldKey || "field")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-") || "field",
  ].join(":");
}

/** Bucket history by auditable entity type (STATION vs AIRCRAFT, etc.). */
export function fieldHistoryAreaFromEntity(
  entityType?: string | null,
): FieldHistoryAreaScope {
  return normalizeAreaScope(entityType || "GENERAL");
}

function readHistory(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .slice(0, HISTORY_LIMIT);
  } catch {
    return [];
  }
}

function writeHistory(key: string, values: string[]): void {
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify(values.slice(0, HISTORY_LIMIT)),
    );
  } catch {
    // Ignore quota / private-mode failures.
  }
}

/** Split multi-line values into individual history entries. */
export function historyEntriesFromValue(value: string): string[] {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function mergeFieldHistory(
  existing: string[],
  incoming: string[],
  limit = HISTORY_LIMIT,
): string[] {
  const next: string[] = [];
  const seen = new Set<string>();
  for (const value of [...incoming, ...existing]) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized.toLowerCase())) continue;
    seen.add(normalized.toLowerCase());
    next.push(normalized);
    if (next.length >= limit) break;
  }
  return next;
}

/** Prefer lines used more often within the same area. */
export function rankHistoryByFrequency(
  entries: string[],
  limit = HISTORY_LIMIT,
): string[] {
  const counts = new Map<string, { value: string; count: number }>();
  for (const raw of entries) {
    const trimmed = String(raw || "").trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    const existing = counts.get(key);
    if (existing) existing.count += 1;
    else counts.set(key, { value: trimmed, count: 1 });
  }
  return Array.from(counts.values())
    .sort(
      (left, right) =>
        right.count - left.count || left.value.localeCompare(right.value),
    )
    .slice(0, limit)
    .map((row) => row.value);
}

export type UseTextFieldHistoryOptions = {
  /** Audit-area bucket (entity type). Use "PROGRAMME" for programme-level fields. */
  areaScope?: string | null;
  /** Extra lines from the same area (e.g. current programme items). */
  areaSeeds?: string[];
  /** When false, do not read/write until an area is selected. */
  enabled?: boolean;
};

/**
 * Tenant + audit-area scoped text history.
 * Aircraft suggestions never appear on Line station (and vice versa).
 */
export function useTextFieldHistory(
  amoCode: string,
  fieldKey: string,
  options: UseTextFieldHistoryOptions = {},
) {
  const areaScope = options.areaScope ?? "GENERAL";
  const enabled = options.enabled !== false;
  const key = useMemo(
    () => fieldHistoryStorageKey(amoCode, fieldKey, areaScope),
    [amoCode, areaScope, fieldKey],
  );
  const listId = useMemo(
    () =>
      `qms-field-history-${normalizeTenant(amoCode)}-${normalizeAreaScope(areaScope)}-${String(fieldKey).replace(/[^a-z0-9_-]+/gi, "-")}`.toLowerCase(),
    [amoCode, areaScope, fieldKey],
  );
  const [stored, setStored] = useState<string[]>(() =>
    typeof window === "undefined" || !enabled ? [] : readHistory(key),
  );

  useEffect(() => {
    if (!enabled) {
      setStored([]);
      return;
    }
    setStored(readHistory(key));
  }, [enabled, key]);

  const optionsList = useMemo(() => {
    if (!enabled) return [];
    return rankHistoryByFrequency([
      ...(options.areaSeeds || []),
      ...stored,
    ]);
  }, [enabled, options.areaSeeds, stored]);

  const remember = useCallback(
    (value: string) => {
      if (!enabled) return;
      const incoming = historyEntriesFromValue(value);
      if (!incoming.length) return;
      setStored((current) => {
        const merged = mergeFieldHistory(current, incoming);
        writeHistory(key, merged);
        return merged;
      });
    },
    [enabled, key],
  );

  return { options: optionsList, listId, remember, areaScope: normalizeAreaScope(areaScope) };
}
