import { z } from "zod";

const blocker = z.object({ type: z.string(), reason: z.string() }).passthrough();
const readiness = z.object({
  issue_ready: z.boolean(),
  fieldwork_ready: z.boolean(),
  checks: z.array(z.object({ code: z.string(), label: z.string(), complete: z.boolean() })),
  issue_blockers: z.array(blocker),
  fieldwork_blockers: z.array(blocker),
  complete_count: z.number(),
  total_count: z.number(),
  percent: z.number(),
  source_fingerprint: z.string(),
}).passthrough();

const context = z.object({
  audit: z.object({ id: z.string(), title: z.string() }).passthrough(),
  prior_audit_history: z.object({ items: z.array(z.unknown()) }).passthrough(),
  prior_findings: z.object({ items: z.array(z.unknown()), total: z.number() }).passthrough(),
  car_exposure: z.object({ items: z.array(z.unknown()), open_count: z.number(), total: z.number() }).passthrough(),
  current_findings: z.array(z.unknown()),
  document_requests: z.array(z.unknown()),
  opening_meeting_records: z.array(z.unknown()),
  controlled_preparation: z.object({ checklist_bindings: z.array(z.unknown()), source_references: z.array(z.unknown()) }).passthrough(),
  source_lineage: z.object({ items: z.array(z.unknown()) }).passthrough(),
  cross_source_assurance_pressure: z.object({ factors: z.array(z.unknown()) }).passthrough(),
  regulatory_and_manual_basis: z.object({ source_references: z.array(z.unknown()) }).passthrough(),
  data_quality: z.object({ warnings: z.array(z.unknown()) }).passthrough(),
}).passthrough();

const activity = z.object({ items: z.array(z.object({ id: z.string(), action: z.string(), entity_type: z.string(), occurred_at: z.string() }).passthrough()) });

export function requirePreparationContract<T>(data: T, kind: "readiness" | "context" | "activity"): T {
  if (!({ readiness, context, activity }[kind]).safeParse(data).success) {
    throw new Error(`Audit preparation ${kind} could not be verified. Reload or retry preparation; if the issue persists, contact Quality support.`);
  }
  return data;
}
