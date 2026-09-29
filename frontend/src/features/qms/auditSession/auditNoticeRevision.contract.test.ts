import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const workspace = readFileSync(
  fileURLToPath(new URL("./AuditSetupWorkspace.tsx", import.meta.url)),
  "utf8",
);
const governance = readFileSync(
  fileURLToPath(new URL("../../../components/QMS/QualityAuditGovernancePanelHost.tsx", import.meta.url)),
  "utf8",
);
const service = readFileSync(
  fileURLToPath(new URL("../../../services/qmsAuditGovernance.ts", import.meta.url)),
  "utf8",
);

describe("audit notice revision governance", () => {
  it("requires a reason when the saved audit schedule changes", () => {
    expect(workspace).toContain("definitionScheduleChanged");
    expect(workspace).toContain("reschedule_reason:");
    expect(workspace).toContain("Reason for rescheduling");
    expect(workspace).toContain("rescheduleReason.trim().length >= 8");
  });

  it("prompts for a new controlled notice rather than regenerating a stale artifact", () => {
    expect(workspace).toContain("latestNotice?.requires_revision");
    expect(workspace).toContain("The saved notice no longer matches the current audit setup.");
    expect(workspace).toContain("Create revised notice N");
    expect(workspace).toContain("reviseNoticeMutation.mutate(latestNotice)");
  });

  it("exposes retained notice and reschedule history with stable notice identifiers", () => {
    expect(service).toContain("notice_reference?: string | null");
    expect(service).toContain("reschedule_history: AuditRescheduleHistoryItem[]");
    expect(workspace).toContain("Full notice & reschedule history");
    expect(workspace).toContain("Controlled notice history");
    expect(workspace).toContain("Audit reschedule history");
    expect(workspace).toContain("Lifecycle events");
  });

  it("uses the current active applicable policy when creating a revised notice", () => {
    expect(workspace).toContain("policiesQuery.data?.items.find");
    expect(workspace).toContain("policy_id: policy?.id");
    expect(workspace).not.toContain("policy_id: row.policy_id || undefined");
  });

  it("keeps historical notice artifacts view-only across both QMS notice surfaces", () => {
    expect(workspace).toContain("previewedNotice.is_latest !== false");
    expect(governance).toContain("latestNotice && !latestNotice.requires_revision");
    expect(governance).toContain("Create a revised notice before any further approval, generation or delivery.");
  });
});
