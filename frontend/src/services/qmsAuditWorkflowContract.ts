import { z } from "zod";

const stageId = z.enum(["setup", "prepare", "live", "closing", "follow-up", "archive"]);
const readiness = z.object({ ready: z.boolean(), blockers: z.array(z.object({ type: z.string(), reason: z.string() }).passthrough()) }).passthrough();
const report = z.object({ id: z.string(), audit_id: z.string(), revision_no: z.number().int().positive(), status: z.enum(["DRAFT", "INTERNAL_REVIEW", "APPROVED", "ISSUED", "SUPERSEDED", "CANCELLED"]), sha256: z.string(), filename: z.string() }).passthrough();
const contracts = {
  session: z.object({
    audit_id: z.string(), current_stage_id: stageId, current_stage_label: z.string(),
    stages: z.array(z.object({ id: stageId, complete: z.boolean(), active: z.boolean() }).passthrough()).length(6).refine((stages) => new Set(stages.map((stage) => stage.id)).size === 6),
    preparation_issued: z.boolean(), execution_status: z.string(), follow_up_status: z.string(), archive_count: z.number(),
  }).passthrough(),
  closure: z.object({ audit_id: z.string(), execution_status: z.enum(["OPEN", "CLOSED"]), follow_up_status: z.enum(["OPEN", "COMPLETE"]), execution_readiness: readiness, follow_up_readiness: readiness, events: z.array(z.unknown()) }).passthrough(),
  report,
  reports: z.object({ items: z.array(report) }).passthrough(),
};

export function requireAuditContract<T>(data: T, kind: keyof typeof contracts): T {
  if (!contracts[kind].safeParse(data).success) {
    throw new Error("Audit workflow data could not be verified. Retry to load the current saved record.");
  }
  return data;
}
