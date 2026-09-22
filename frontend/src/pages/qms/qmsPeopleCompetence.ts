import type { QmsEligibility } from "../../services/qmsPeople";

export type CompetenceCode = "QMS-INIT" | "QMS-REF" | "QMS-ADMIN";

export type CompetenceChip = {
  label: CompetenceCode;
  tone: "pass" | "block" | "muted";
  detail: string;
};

type TrainingSnapshot = QmsEligibility["training"] | undefined;

const COMPETENCE_DUE_SOON_DAYS = 90;

function compactCourseToken(value: unknown): string {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "");
}

function recordMatchesCompetenceCode(row: Record<string, unknown>, code: string): boolean {
  const wanted = code.toUpperCase();
  const direct = String(row.course_code || "").toUpperCase();
  if (direct === wanted) return true;
  const source = String(row.source_course_code || "").toUpperCase();
  if (source === wanted) return true;
  const compactWanted = compactCourseToken(wanted);
  return (
    compactCourseToken(direct) === compactWanted
    || compactCourseToken(source) === compactWanted
    || compactCourseToken(row.course_name).includes(compactWanted)
  );
}

export function competenceRecordForCode(
  code: string,
  training: TrainingSnapshot,
): Record<string, unknown> | null {
  if (!training) return null;
  if (code === "QMS-ADMIN" && training.admin?.record) {
    return training.admin.record;
  }
  const pools = [
    ...(training.tracked_records || []),
    ...(training.records || []),
    ...(training.expired_records || []),
  ];
  return pools.find((row) => recordMatchesCompetenceCode(row, code)) || null;
}

export function formatCompetenceDate(value?: string | null): string | null {
  if (!value) return null;
  const raw = String(value).slice(0, 10);
  const parsed = new Date(`${raw}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function competenceDaysUntil(record: Record<string, unknown> | null): number | null {
  if (!record) return null;
  const direct = record.days_until_expiry;
  if (typeof direct === "number" && Number.isFinite(direct)) return direct;
  const until = record.valid_until ? String(record.valid_until).slice(0, 10) : null;
  if (!until) return null;
  const expiry = new Date(`${until}T00:00:00`);
  if (Number.isNaN(expiry.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((expiry.getTime() - today.getTime()) / 86400000);
}

function dueSoonLabel(daysUntil: number | null): string | null {
  if (daysUntil == null || daysUntil < 0 || daysUntil >= COMPETENCE_DUE_SOON_DAYS) return null;
  return daysUntil === 0 ? "due today" : `${daysUntil} day${daysUntil === 1 ? "" : "s"} to due`;
}

function evidenceDetail(
  completed: string | null,
  until: string | null,
  soon: string | null,
  verification: string,
  fallback: string,
): string {
  if (until && soon) return `${until} · ${soon}`;
  if (until) return `expires ${until}`;
  if (completed) return `completed ${completed}`;
  if (verification === "PENDING") return "pending verify";
  if (verification && verification !== "NONE") return verification.toLowerCase().replaceAll("_", " ");
  return fallback;
}

/**
 * People competence chips must reflect Training evidence first.
 * Rule defaults require AND of configured courses; chip display still shows each
 * code’s own evidence (completed / expires / missing).
 * Do not label a code "required · not completed" when a completion/expiry row exists,
 * or when the rule already passes via an alternate OR branch.
 */
export function competenceChipStatus(code: CompetenceCode, training: TrainingSnapshot): CompetenceChip {
  if (!training) return { label: code, tone: "muted", detail: "unavailable" };

  const record = competenceRecordForCode(code, training);
  const completed = formatCompetenceDate(record?.completion_date ? String(record.completion_date) : null);
  const until = formatCompetenceDate(record?.valid_until ? String(record.valid_until) : null);
  const daysUntil = competenceDaysUntil(record);
  const trainingStatus = String(record?.training_status || "").toUpperCase();
  const verification = String(record?.verification_status || "").toUpperCase();
  const recordStatus = String(record?.record_status || "").toUpperCase();
  const soon = dueSoonLabel(daysUntil);

  const currencyPassed = Boolean(training.passed || training.currency_passed);
  const satisfied = (training.satisfied || []).includes(code);
  const listedMissing = (training.missing || []).includes(code);
  const listedRequired = (training.required || []).includes(code);
  const expired =
    (training.expired || []).includes(code)
    || recordStatus === "EXPIRED"
    || trainingStatus === "OVERDUE"
    || (daysUntil != null && daysUntil < 0);
  const hasEvidence = Boolean(
    record
    && (
      completed
      || until
      || verification === "VERIFIED"
      || verification === "PENDING"
      || recordStatus === "READY"
      || recordStatus === "PENDING"
    ),
  );
  const rejected = verification === "REJECTED";

  if (code === "QMS-ADMIN") {
    const status = String(training.admin?.status || "none");
    if (status === "current" || (satisfied && !expired && !rejected)) {
      return {
        label: code,
        tone: "pass",
        detail: evidenceDetail(completed, until, soon, verification, "current"),
      };
    }
    if (status === "expired" || expired) {
      return { label: code, tone: "block", detail: until ? `expired ${until}` : "expired" };
    }
    if (hasEvidence && !rejected) {
      return {
        label: code,
        tone: "muted",
        detail: evidenceDetail(completed, until, soon, verification, "on file"),
      };
    }
    if (rejected) return { label: code, tone: "block", detail: "rejected" };
    return { label: code, tone: "muted", detail: "not held" };
  }

  // QMS-INIT / QMS-REF — currency any-of
  if (satisfied || (hasEvidence && !expired && !rejected)) {
    const tone: CompetenceChip["tone"] =
      satisfied || verification === "VERIFIED" || verification === ""
        ? "pass"
        : "muted";
    return {
      label: code,
      tone,
      detail: evidenceDetail(
        completed,
        until,
        soon,
        verification,
        satisfied ? "current" : "on file",
      ),
    };
  }

  if (expired) {
    return {
      label: code,
      tone: "block",
      detail: until ? `expired ${until}` : completed ? `completed ${completed} · expired` : "expired",
    };
  }

  if (hasEvidence) {
    return {
      label: code,
      tone: "muted",
      detail: evidenceDetail(completed, until, soon, verification, "on file"),
    };
  }

  if (rejected) return { label: code, tone: "block", detail: "rejected" };

  // Hard gap only when this code is still a currency miss (not satisfied via alternate).
  if (listedMissing && listedRequired && !currencyPassed) {
    return { label: code, tone: "block", detail: "required · not completed" };
  }

  // Currency already met via the other course — this one is simply not held.
  if (currencyPassed || (listedMissing && !listedRequired)) {
    return { label: code, tone: "muted", detail: "not held" };
  }

  if (listedMissing) {
    return { label: code, tone: "block", detail: "required · not completed" };
  }

  return { label: code, tone: "muted", detail: "not recorded" };
}

/** Soonest course valid_until among current satisfied competence records (YYYY-MM-DD). */
export function earliestCompetenceValidUntil(
  training: TrainingSnapshot,
  asOf = new Date(),
): string | null {
  if (!training) return null;
  const asOfKey = `${asOf.getFullYear()}-${String(asOf.getMonth() + 1).padStart(2, "0")}-${String(asOf.getDate()).padStart(2, "0")}`;
  const satisfied = new Set(
    (training.satisfied || []).map((code) => String(code || "").trim().toUpperCase()).filter(Boolean),
  );
  const rows = [
    ...(Array.isArray(training.records) ? training.records : []),
    ...(Array.isArray(training.tracked_records) ? training.tracked_records : []),
  ];
  let earliest: string | null = null;
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const record = row as Record<string, unknown>;
    const code = String(record.course_code || "").trim().toUpperCase();
    if (satisfied.size && code && !satisfied.has(code)) continue;
    const until = record.valid_until ? String(record.valid_until).slice(0, 10) : "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(until) || until < asOfKey) continue;
    const dedupe = code || String(record.record_id || until);
    if (seen.has(dedupe)) continue;
    seen.add(dedupe);
    if (!earliest || until < earliest) earliest = until;
  }
  return earliest;
}

/** Cap a requested privilege expiry to the governing course calendar day. */
export function capPrivilegeExpiresOn(
  requested: string | null | undefined,
  training: TrainingSnapshot,
  asOf = new Date(),
): string | null {
  const courseCap = earliestCompetenceValidUntil(training, asOf);
  const requestedKey = requested ? String(requested).slice(0, 10) : "";
  if (!courseCap) return requestedKey || null;
  if (!requestedKey) return courseCap;
  return requestedKey < courseCap ? requestedKey : courseCap;
}
