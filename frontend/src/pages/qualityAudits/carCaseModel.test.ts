import { describe, expect, it } from "vitest";
import type { CAROut } from "../../services/qms";
import { carHasReview, carNextAction, caseDate } from "./carCaseModel";

describe("CAR case next action",()=>{
  it.each([
    [{status:"OPEN"},"Auditee response",false],
    [{status:"PENDING_VERIFICATION",root_cause_status:"SUBMITTED",capa_status:"SUBMITTED"},"Quality review",true],
    [{status:"PENDING_VERIFICATION",root_cause_status:"ACCEPTED",capa_status:"ACCEPTED"},"Effectiveness review",false],
    [{status:"IN_PROGRESS",submitted_at:"2026-10-18",capa_status:"NEEDS_EVIDENCE"},"Auditee revision",false],
    [{status:"IN_PROGRESS",submitted_at:"2026-10-18",capa_status:"ACCEPTED"},"Implementation",false],
    [{status:"CLOSED",root_cause_status:"SUBMITTED"},"Closed",false],
    [{status:"CANCELLED"},"Cancelled",false],
    [{status:"ESCALATED"},"Executive review",false],
  ] as const)("shows %s as %s",(input,label,review)=>{
    expect(carNextAction(input as CAROut)).toBe(label);
    expect(carHasReview(input as CAROut)).toBe(review);
  });
  it("keeps absent dates distinct from a real recorded date",()=>{
    expect(caseDate(null)).toBe("Not set");
    expect(caseDate("invalid")).toBe("Not set");
    expect(caseDate("2026-10-18")).toContain("2026");
    expect(caseDate("2027-01-16")).toContain("16");
  });
});
