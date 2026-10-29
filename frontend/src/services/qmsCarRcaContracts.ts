import { z } from "zod";

const document = z.object({
  version: z.number(), problem_statement: z.string(),
  investigations: z.array(z.object({ id: z.string(), method: z.string(), nodes: z.array(z.object({
    id: z.string(), statement: z.string(), entry_type: z.string(), evidence_references: z.array(z.string()),
  }).passthrough()), context: z.record(z.string(), z.unknown()) }).passthrough()),
  conclusion: z.string(), supported_cause_ids: z.array(z.string()),
  conclusion_evidence_references: z.array(z.string()),
}).passthrough();
const snapshot = z.object({ form: z.record(z.string(), z.string()), investigation: document }).passthrough();
const action = z.object({
  id: z.string(), car_id: z.string(), action_number: z.string(), kind: z.string(),
  description: z.string(), state: z.string(), cause_node_ids: z.array(z.string()),
  evidence_references: z.array(z.string()),
}).passthrough();
const projection = z.object({
  car_id: z.string(), revision: z.number().int().nonnegative(), draft: snapshot,
  submitted_revision: z.number().nullable(), submitted_snapshot: snapshot.nullable(),
  submitted_at: z.string().nullable(), actions: z.array(action),
  action_events: z.array(z.object({ id: z.string() }).passthrough()),
  retained_responses: z.array(z.object({ id: z.string() }).passthrough()),
  history: z.array(z.object({ id: z.string() }).passthrough()),
}).passthrough();
const invite = z.object({
  expires_at: z.string().nullable(), revoked_at: z.string().nullable(), reason: z.string(),
}).passthrough();
const pareto = z.array(z.object({
  id: z.string(), car_id: z.string(), created_at: z.string(), sample_size: z.number(),
  filters: z.object({ start: z.string(), end: z.string(), group_by: z.string() }).passthrough(),
  categories: z.array(z.object({ category: z.string(), count: z.number(), share_percent: z.number(), cumulative_percent: z.number() }).passthrough()),
  source_references: z.array(z.object({ id: z.string() }).passthrough()),
}).passthrough());

function validate<T>(schema: z.ZodType, value: T, label: string): T {
  if (!schema.safeParse(value).success) {
    throw new Error(`The server returned an invalid ${label} response. Retry after the portal update; no controlled record has been loaded.`);
  }
  return value;
}

export const validateCarRcaProjection = <T,>(value: T): T => validate(projection, value, "CAR investigation");
export const validateCarInviteAccess = <T,>(value: T): T => validate(invite, value, "invitation access");
export const validateCarParetoSnapshots = <T,>(value: T): T => validate(pareto, value, "Pareto snapshots");
