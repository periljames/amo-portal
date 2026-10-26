import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const live = readFileSync(new URL("./LiveAuditWorkspace.tsx", import.meta.url), "utf8");
const table = readFileSync(new URL("./AuditChecklistTable.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../../styles/qms-live-audit-workspace.css", import.meta.url), "utf8");

describe("paper-familiar QMS Fieldwork table", () => {
  it("shows multiple questions and response choices together, retaining advanced details on demand", () => {
    expect(live).toContain('aria-label="Checklist assessment table"');
    expect(table).toContain('className="qms-live-audit-focus__matrix-table audit-checklist-table"');
    expect(table).toContain("props.items.map((item, index)");
    expect(table).toContain("columns.map((column)");
    expect(table).toContain("actions.current.onResponse(item, option)");
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
    expect(readFileSync(new URL("./AuditFieldworkHeader.tsx", import.meta.url), "utf8")).not.toContain("server-confirmed");
    expect(live).toContain("syncFieldworkNow");
    expect(live).toContain("prepareAuditOfflinePack");
    expect(live).toContain("onOfflineSyncComplete");
  });

  it("retains existing governed backend control, evidence and release safeguards", () => {
    for (const marker of [
      "createAtomicChecklistFinding",
      "assessmentIntegrityError",
      "N/A requires an explicit governed applicability basis",
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
    expect(readFileSync(new URL("./AuditChecklistToolbar.tsx", import.meta.url), "utf8")).toContain('value="VERIFIED"');
    expect(live).toContain("setChecklistSearch");
    expect(table).toContain("aria-expanded={expanded}");
    expect(live).toContain("Frozen checklist question differs from the execution question");
    expect(styles).toContain(":focus-visible");
  });
});
