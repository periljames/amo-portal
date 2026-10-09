import { describe, expect, it } from "vitest";
import { requireAuditContract } from "./qmsAuditWorkflowContract";

describe("audit workflow responses", () => {
  it("rejects a generic register response instead of treating it as an empty findings list", () => {
    expect(() => requireAuditContract({ module: "audits", table: "qms_audit_findings", items: [] }, "findings"))
      .toThrow("could not be verified");
    expect(requireAuditContract([], "findings")).toEqual([]);
  });

  it("accepts untouched checklist items at version zero and rejects malformed evidence arrays", () => {
    const item = {
      checklist_item_id: "item-1", audit_id: "audit-1", prompt: "Verify traceability",
      canonical_response_status: "NOT_VERIFIED", entity_version: 0, evidence_references: [], events: [],
      assessment: {
        applicability: "UNVERIFIED", applicability_basis: [], documentary_status: "UNVERIFIED",
        implementation_status: "UNVERIFIED", field_verification_status: "UNVERIFIED",
        evidence_ids: [], document_revision_ids: [], regulation_refs: [], procedure_refs: [],
        conflicts: [], missing_evidence: [], fieldwork_requirements: [], ai_analysis: null,
      },
    };
    const response = { items: [item], canonical_response_values: ["NOT_VERIFIED"] };
    expect(requireAuditContract(response, "checklist")).toBe(response);
    expect(() => requireAuditContract({ ...response, items: [{ ...item, assessment: { ...item.assessment, evidence_ids: {} } }] }, "checklist"))
      .toThrow("could not be verified");
  });
});
