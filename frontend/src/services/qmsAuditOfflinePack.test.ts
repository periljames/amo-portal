import { describe, expect, it } from "vitest";

import {
  projectOfflineAuditSession,
  projectOfflineChecklistBindings,
  projectOfflineChecklistExecution,
  type AuditOfflinePack,
} from "./qmsAuditOfflinePack";

function pack(): AuditOfflinePack {
  return {
    schema: "QMS_AUDIT_OFFLINE_PACK_V1",
    generated_at: "2026-10-01T04:00:00Z",
    audit_id: "audit-1",
    fieldwork_state: {
      authorized: true,
      blocker: null,
      audit_status: "IN_PROGRESS",
      actual_start: "2026-10-01",
      actual_end: null,
      captured_at: "2026-10-01T04:00:00Z",
    },
    work_package: {
      id: "package-1",
      audit_id: "audit-1",
      preparation_revision_id: "prep-1",
      revision_no: 2,
      package_snapshot: {
        schema: "QMS_AUDIT_WORK_PACKAGE_V1",
        audit: { id: "audit-1", audit_ref: "QAR/MO/26/001", title: "AMO audit" },
        preparation: {},
        checklist_snapshot: [{
          id: "item-1",
          section: "Stores",
          checklist_ref: "Q7.10",
          requirement_ref: "MPM 4.7",
          prompt: "Verify incoming inspection traceability.",
          response_status: "PENDING",
        }],
        checklist_bindings: [{
          id: "binding-1",
          template_id: "template-1",
          template_revision_id: "revision-2",
          template_code: "SL/QMS/29",
          revision_no: 2,
          content_sha256: "a".repeat(64),
          item_snapshot: [{
            section: "Stores",
            checklist_ref: "Q7.10",
            requirement_ref: "MPM 4.7",
            prompt: "Verify incoming inspection traceability.",
            response_type: "YES_NO_NA",
            response_options: [
              { value: "YES", label: "Yes", canonical_status: "COMPLIANT" },
              { value: "NO", label: "No", canonical_status: "NONCOMPLIANT" },
              { value: "N/A", label: "N/A", canonical_status: "NOT_APPLICABLE" },
            ],
            applicability: "APPLICABLE",
            sort_order: 0,
          }],
          source_references: [],
          instantiated_item_ids: ["item-1"],
          application_reason: "Governed audit preparation.",
          applied_at: "2026-10-01T03:00:00Z",
        }],
        document_request_definitions: [],
        source_references: [],
        prior_audits: [],
        prior_findings: [],
        prior_cars: [],
        meetings: [],
      },
      content_sha256: "b".repeat(64),
      offline_expires_at: "2026-10-03T18:00:00Z",
      supersedes_work_package_id: null,
      issued_by_user_id: "quality-user-1",
      issued_at: "2026-10-01T03:30:00Z",
      created_at: "2026-10-01T03:30:00Z",
    },
    execution: [{
      checklist_item_id: "item-1",
      canonical_response_status: "NONCOMPLIANT",
      response_value: "NO",
      auditor_notes: "Traceability identifier missing.",
      evidence_references: [],
      entity_version: 4,
      updated_at: "2026-10-01T04:05:00Z",
    }],
    findings: [],
    evidence: [],
    sync_contract: {
      server_authoritative: true,
      conflict_strategy: "BASE_VERSION",
      idempotency: "CLIENT_MUTATION_ID",
      binary_evidence_state: "SEPARATE_DURABLE_QUEUE",
    },
  };
}

describe("QMS downloaded audit work package projections", () => {
  it("restores the frozen checklist binding and source response scheme", () => {
    const projected = projectOfflineChecklistBindings(pack());
    expect(projected.items).toHaveLength(1);
    expect(projected.items[0].template_code).toBe("SL/QMS/29");
    expect(projected.items[0].item_snapshot[0].response_options?.map((row) => row.value)).toEqual(["YES", "NO", "N/A"]);
  });

  it("restores the latest captured execution state without inventing a server save", () => {
    const projected = projectOfflineChecklistExecution(pack());
    expect(projected.items[0]).toMatchObject({
      checklist_item_id: "item-1",
      canonical_response_status: "NONCOMPLIANT",
      response_value: "NO",
      entity_version: 4,
      auditor_notes: "Traceability identifier missing.",
    });
  });

  it("restores live-stage navigation from a downloaded authorized fieldwork pack", () => {
    const projected = projectOfflineAuditSession(pack());
    expect(projected.current_stage_id).toBe("live");
    expect(projected.preparation_issued).toBe(true);
    expect(projected.execution_status).toBe("IN_PROGRESS");
  });
});
