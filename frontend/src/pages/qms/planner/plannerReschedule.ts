export type PlannerAvailableSlot = {
  start_time: string;
  end_time: string;
  label: string;
};

export type PlannerScheduleConflict = {
  subject_type: string;
  subject_id: string;
  title: string;
  start_date: string;
  end_date: string;
  start_time?: string | null;
  end_time?: string | null;
  location?: string | null;
  conflicting_user_ids: string[];
  reason: string;
};

export type PlannerStaleScheduleDetail = {
  code: "SCHEDULE_STALE";
  message: string;
  expected_old_date: string;
  current_date: string;
  trace_id?: string;
};

export type PlannerConflictDetail = {
  code: "SCHEDULE_CONFLICT";
  message: string;
  conflicts: PlannerScheduleConflict[];
  available_slots: PlannerAvailableSlot[];
  proposed_start_time?: string | null;
  proposed_end_time?: string | null;
  trace_id?: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function parseJsonObject(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    return asRecord(JSON.parse(trimmed));
  } catch {
    return null;
  }
}

function extractDetailCandidate(error: unknown): Record<string, unknown> | null {
  const body = asRecord((error as { body?: unknown } | null)?.body);
  const fromBody = asRecord(body?.detail) ?? (typeof body?.code === "string" ? body : null);
  if (fromBody) return fromBody;

  const direct = asRecord((error as { detail?: unknown })?.detail);
  if (direct) return direct;

  const message = typeof (error as { message?: unknown })?.message === "string" ? (error as { message: string }).message : "";
  if (!message) return null;
  const colonIdx = message.indexOf("{");
  if (colonIdx >= 0) {
    const parsed = parseJsonObject(message.slice(colonIdx));
    const nested = asRecord(parsed?.detail);
    if (nested) return nested;
    if (typeof parsed?.code === "string") return parsed;
  }
  return null;
}

function asConflict(value: unknown): PlannerScheduleConflict | null {
  const row = asRecord(value);
  if (!row || typeof row.title !== "string") return null;
  const conflicting = Array.isArray(row.conflicting_user_ids)
    ? row.conflicting_user_ids.filter((item): item is string => typeof item === "string")
    : [];
  return {
    subject_type: String(row.subject_type || ""),
    subject_id: String(row.subject_id || ""),
    title: row.title,
    start_date: String(row.start_date || ""),
    end_date: String(row.end_date || row.start_date || ""),
    start_time: typeof row.start_time === "string" ? row.start_time : null,
    end_time: typeof row.end_time === "string" ? row.end_time : null,
    location: typeof row.location === "string" ? row.location : null,
    conflicting_user_ids: conflicting,
    reason: typeof row.reason === "string" ? row.reason : "Personnel overlap.",
  };
}

function asSlot(value: unknown): PlannerAvailableSlot | null {
  const row = asRecord(value);
  if (!row || typeof row.start_time !== "string" || typeof row.end_time !== "string") return null;
  return {
    start_time: row.start_time,
    end_time: row.end_time,
    label: typeof row.label === "string" ? row.label : `${row.start_time} – ${row.end_time}`,
  };
}

export function parseStaleScheduleDetail(error: unknown): PlannerStaleScheduleDetail | null {
  const candidate = extractDetailCandidate(error);
  if (!candidate) return null;
  const isStale =
    candidate.code === "SCHEDULE_STALE"
    || (typeof candidate.message === "string" && /schedule changed after the planner loaded/i.test(candidate.message));
  if (!isStale) return null;
  const current = typeof candidate.current_date === "string" ? candidate.current_date : "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(current)) return null;
  return {
    code: "SCHEDULE_STALE",
    message: typeof candidate.message === "string" ? candidate.message : "The schedule changed. Refreshing the planner.",
    expected_old_date: typeof candidate.expected_old_date === "string" ? candidate.expected_old_date : "",
    current_date: current,
    trace_id: typeof candidate.trace_id === "string" ? candidate.trace_id : undefined,
  };
}

export function parseScheduleConflictDetail(error: unknown): PlannerConflictDetail | null {
  const candidate = extractDetailCandidate(error);
  if (!candidate || candidate.code !== "SCHEDULE_CONFLICT") return null;
  const conflicts = Array.isArray(candidate.conflicts)
    ? candidate.conflicts.map(asConflict).filter((item): item is PlannerScheduleConflict => Boolean(item))
    : [];
  const available_slots = Array.isArray(candidate.available_slots)
    ? candidate.available_slots.map(asSlot).filter((item): item is PlannerAvailableSlot => Boolean(item))
    : [];
  return {
    code: "SCHEDULE_CONFLICT",
    message: typeof candidate.message === "string"
      ? candidate.message
      : "This move overlaps another audit for the same team member.",
    conflicts,
    available_slots,
    proposed_start_time: typeof candidate.proposed_start_time === "string" ? candidate.proposed_start_time : null,
    proposed_end_time: typeof candidate.proposed_end_time === "string" ? candidate.proposed_end_time : null,
    trace_id: typeof candidate.trace_id === "string" ? candidate.trace_id : undefined,
  };
}
