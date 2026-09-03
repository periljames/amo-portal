import { describe, expect, it } from "vitest";
import type { CAROut, QMSFindingOut } from "../../services/qms";
import {
  DEFAULT_FINDING_LIFECYCLE,
  findingLifecycleLabel,
  findingLifecycleView,
  findingNextAction,
  parseFindingLifecycleView,
  toRegisterWorkflowStage,
} from "./findingLifecycle";

const finding = { id: "f-1", closed_at: null } as QMSFindingOut;
const car = (status: CAROut["status"]) => ({ id: `car-${status}`, status } as CAROut);

describe("finding lifecycle projection", () => {
  it("defaults the register to All so Live-raised OPEN CARs stay visible", () => {
    expect(DEFAULT_FINDING_LIFECYCLE).toBe("all");
    expect(parseFindingLifecycleView(null)).toBe("all");
    expect(parseFindingLifecycleView("with_auditee")).toBe("with_auditee");
    expect(toRegisterWorkflowStage("all")).toBeUndefined();
    expect(toRegisterWorkflowStage("with_auditee")).toBe("with_auditee");
  });

  it("keeps unlinked findings in RCA/CAP (needs_review)", () => {
    expect(findingLifecycleView(finding, [])).toBe("needs_review");
    expect(findingLifecycleLabel("needs_review")).toBe("RCA/CAP");
    expect(findingNextAction("needs_review", false)).toBe("Create corrective action");
  });

  it.each([
    ["OPEN", "with_auditee", "Awaiting response"],
    ["ESCALATED", "with_auditee", "Awaiting response"],
    ["IN_PROGRESS", "implementation", "Implementation"],
    ["PENDING_VERIFICATION", "effectiveness", "Effectiveness"],
    ["CLOSED", "closed", "Closed"],
  ] as const)("maps %s corrective actions to %s (%s)", (status, expected, label) => {
    expect(findingLifecycleView(finding, [car(status)])).toBe(expected);
    expect(findingLifecycleLabel(expected)).toBe(label);
  });

  it("treats a closed finding as closed regardless of CAR state", () => {
    expect(findingLifecycleView({ ...finding, closed_at: "2026-08-25T00:00:00Z" }, [car("OPEN")])).toBe("closed");
  });

  it("documents that OPEN CARs are not Needs review / RCA/CAP", () => {
    expect(findingLifecycleView(finding, [car("OPEN")])).not.toBe("needs_review");
    expect(findingLifecycleView(finding, [car("OPEN")])).toBe("with_auditee");
  });
});
