import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const live = readFileSync(new URL("./LiveAuditWorkspace.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../../styles/qms-live-audit-workspace.css", import.meta.url), "utf8");

describe("paper-familiar QMS Fieldwork table", () => {
  it("shows multiple questions and response choices together, retaining advanced details on demand", () => {
    expect(live).toContain('aria-label="Checklist assessment table"');
    expect(live).toContain('className="qms-live-audit-focus__matrix-table"');
    expect(live).toContain("visibleItems.map((item, index)");
    expect(live).toContain("choices.map((option)");
    expect(live).toContain("selectResponse(item, option)");
    expect(live).toContain("selected && detailOpen");
    expect(live).toContain("<LiveAuditEvidenceStrip");
    expect(live).toContain('className="qms-live-audit-focus__compliance"');
    expect(live).not.toContain('className="qms-live-audit-focus__compliance" aria-label="Compliance evidence analysis" open');
    expect(styles).toContain(".qms-live-audit-focus__matrix-table");
  });

  it("continues offline after a durable queued save without claiming server confirmation", () => {
    const start = live.indexOf("const saveAndNext = async () => {");
    const end = live.indexOf("const selectResponse =", start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const handler = live.slice(start, end);
    expect(handler).toContain("await updateMutation.mutateAsync");
    expect(handler).toContain("if (isOfflineQueuedError(error)) selectItem(nextItemId)");
    expect(live).toContain("localAnswers");
    expect(live).toContain("server-confirmed");
    expect(live).toContain("syncFieldworkNow");
    expect(live).toContain("prepareAuditOfflinePack");
    expect(live).toContain("onOfflineSyncComplete");
  });

  it("retains existing governed backend control, evidence and release safeguards", () => {
    for (const marker of [
      "createAtomicChecklistFinding",
      "assessmentIntegrityError",
      "N/A requires an applicability basis",
      "applicability_recommendation",
      "documentary_recommendation",
      "Current-approved documentary candidates",
      "Competing controlled statements",
      "LiveAuditEvidenceStrip",
      "FIELDWORK_VERSION_CONFLICT",
      "completionBlockers",
      "canExecuteAssignedAudit",
      "canCompleteAuditFieldwork",
      "Released-data boundary active",
    ]) expect(live).toContain(marker);
  });

  it("retains search, filtering, stable numbering and accessible expanded details", () => {
    expect(live).toContain("itemNumberById");
    expect(live).toContain('value="VERIFIED"');
    expect(live).toContain("setChecklistSearch");
    expect(live).toContain("aria-expanded={expanded}");
    expect(live).toContain("Frozen checklist question differs from the execution question");
    expect(styles).toContain(":focus-visible");
  });
});
