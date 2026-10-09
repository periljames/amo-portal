import { describe, expect, it } from "vitest";

import {
  projectOfflineAuditSession,
  projectOfflineChecklistBindings,
  projectOfflineChecklistExecution,
  projectOfflineEvidence,
  projectOfflineFindings,
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
      assessment: {
        applicability: "APPLICABLE",
        applicability_reason: null,
        applicability_basis: [],
        documentary_status: "DOCUMENTED",
        implementation_status: "OBJECTIVE_EVIDENCE_AVAILABLE",
        field_verification_status: "VERIFIED",
        evidence_ids: ["section:rev-1:section-1"],
        document_revision_ids: ["rev-1"],
        regulation_refs: [],
        procedure_refs: ["MPM 4.7"],
        conflicts: [],
        missing_evidence: [],
        fieldwork_requirements: [],
        ai_analysis: null,
        human_decision: "NONCOMPLIANT",
        human_override_reason: null,
      },
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
    const responseOptions = projected.items[0].item_snapshot[0].response_options as Array<{ value: string }>;
    expect(responseOptions.map((row) => row.value)).toEqual(["YES", "NO", "N/A"]);
  });

  it("restores the latest captured execution state without inventing a server save", () => {
    const projected = projectOfflineChecklistExecution(pack());
    expect(projected.items[0]).toMatchObject({
      checklist_item_id: "item-1",
      canonical_response_status: "NONCOMPLIANT",
      response_value: "NO",
      entity_version: 4,
      auditor_notes: "Traceability identifier missing.",
      assessment: {
        applicability: "APPLICABLE",
        documentary_status: "DOCUMENTED",
        implementation_status: "OBJECTIVE_EVIDENCE_AVAILABLE",
        field_verification_status: "VERIFIED",
        procedure_refs: ["MPM 4.7"],
        human_decision: "NONCOMPLIANT",
      },
    });
  });

  it("restores findings and evidence metadata after an offline restart", () => {
    const downloaded = pack();
    downloaded.findings = [{
      id: "finding-1",
      audit_id: "audit-1",
      finding_ref: "F-001",
      finding_type: "NON_CONFORMITY",
      severity: "MAJOR",
      level: "LEVEL_2",
      requirement_ref: "MPM 4.7",
      description: "Traceability identifier missing.",
      objective_evidence: "Incoming inspection record.",
      safety_sensitive: false,
      entity_version: 2,
      created_at: "2026-10-01T04:06:00Z",
    }];
    downloaded.evidence = [{
      id: "evidence-1",
      checklist_item_id: "item-1",
      finding_id: "finding-1",
      evidence_request_id: null,
      source_type: "INTERNAL_USER",
      filename: "incoming-record.pdf",
      content_type: "application/pdf",
      size_bytes: 4096,
      sha256: "c".repeat(64),
      description: "Sample incoming record.",
      source_device_id: "device-1",
      captured_at: "2026-10-01T04:07:00Z",
      offline_upload_state: "SYNCED",
      server_processing_state: "AVAILABLE",
      uploaded_by_user_id: "quality-user-1",
      uploaded_by_participant_id: null,
      created_at: "2026-10-01T04:07:00Z",
    }];

    expect(projectOfflineFindings(downloaded)[0]).toMatchObject({
      id: "finding-1",
      audit_id: "audit-1",
      description: "Traceability identifier missing.",
    });
    expect(projectOfflineEvidence(downloaded, "item-1", null)[0]).toMatchObject({
      id: "evidence-1",
      audit_id: "audit-1",
      filename: "incoming-record.pdf",
      sha256: "c".repeat(64),
    });
  });

  it("restores live-stage navigation from a downloaded authorized fieldwork pack", () => {
    const projected = projectOfflineAuditSession(pack());
    expect(projected.current_stage_id).toBe("live");
    expect(projected.preparation_issued).toBe(true);
    expect(projected.execution_status).toBe("IN_PROGRESS");
  });
});
