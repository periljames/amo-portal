import type { AuditProgramme } from "../../services/qmsAuditProgramme";

export type ProgrammeApprovalStage =
  | "PREPARATION"
  | "QUALITY_REVIEW"
  | "EXECUTIVE_APPROVAL"
  | "READY_TO_PUBLISH"
  | "PUBLISHED"
  | "COMPLETE";

export function programmeApprovalStage(programme: AuditProgramme): ProgrammeApprovalStage {
  if (programme.status === "DRAFT") return "PREPARATION";
  if (programme.status === "UNDER_REVIEW") {
    return programme.quality_reviewed_at ? "EXECUTIVE_APPROVAL" : "QUALITY_REVIEW";
  }
  if (programme.status === "APPROVED") return "READY_TO_PUBLISH";
  if (programme.status === "ACTIVE") return "PUBLISHED";
  return "COMPLETE";
}

export function programmeIsControlled(programme: AuditProgramme): boolean {
  return ["APPROVED", "ACTIVE", "SUPERSEDED", "CLOSED"].includes(programme.status);
}

export function programmeCanBeEdited(programme: AuditProgramme): boolean {
  return programme.status === "DRAFT";
}
