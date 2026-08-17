import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ShieldAlert, UserCheck } from "lucide-react";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsListAuditPersonnelOptions } from "../../../services/qms";
import {
  declareAuditIndependence,
  getAuditAssignmentEligibility,
  updateAuditAssignments,
  type AuditAssignmentAssessment,
  type AuditAssignmentEligibility,
  type AuditAssignmentRole,
} from "../../../services/qmsAuditAssignments";
import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";

type Props = { amoCode: string; auditKey: string };
type RoleField = "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id";
type AssignmentDraft = Record<RoleField, string>;
type DeclarationDraft = {
  userId: string;
  declaration: "INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW";
  relationship: string;
  rationale: string;
};

const ROLE_CONFIG: Array<{ field: RoleField; role: AuditAssignmentRole; label: string }> = [
  { field: "lead_auditor_user_id", role: "LEAD_AUDITOR", label: "Lead auditor" },
  { field: "observer_auditor_user_id", role: "OBSERVER_AUDITOR", label: "Observer auditor" },
  { field: "assistant_auditor_user_id", role: "ASSISTANT_AUDITOR", label: "Assistant auditor" },
];

const GATE_LABELS: Record<string, string> = {
  workforce_active: "active workforce record",
  active_privilege: "active Quality privilege",
  scope_authorized: "scope authorisation",
  training_current_verified: "current required training",
  capacity: "assignment capacity",
  independence: "audit-specific independence",
};

function assessmentFor(row: AuditAssignmentEligibility | undefined): AuditAssignmentAssessment | undefined {
  return row?.assessment || row?.assessments?.find((item) => item.eligible) || row?.assessments?.[0];
}

function failedGates(row: AuditAssignmentEligibility | undefined): string[] {
  const hardGates = assessmentFor(row)?.hard_gates || {};
  return Object.entries(hardGates)
    .filter(([, passed]) => !passed)
    .map(([gate]) => GATE_LABELS[gate] || gate.replaceAll("_", " "));
}

function eligibilitySummary(row: AuditAssignmentEligibility | undefined): string {
  if (!row) return "Select a person to evaluate governed eligibility.";
  if (!row.governance_configured) return "Eligible in explicit compatibility mode because this tenant has no active Quality privilege rule for the role yet.";
  if (row.eligible) return "Eligible · privilege, scope, training, independence and capacity gates are satisfied.";
  const gates = failedGates(row);
  return gates.length ? `Blocked · ${gates.join(" · ")}` : row.reason || "Assignment blocked by governed eligibility.";
}

const AuditAssignmentGovernancePanel: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [draft, setDraft] = useState<AssignmentDraft>({ lead_auditor_user_id: "", observer_auditor_user_id: "", assistant_auditor_user_id: "" });
  const [reason, setReason] = useState("Assign the audit team after privilege, training, independence and capacity verification.");
  const [declaration, setDeclaration] = useState<DeclarationDraft>({ userId: "", declaration: "INDEPENDENT", relationship: "", rationale: "No conflict of interest identified for this audit occurrence." });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-setup-assignment-audit", amoCode, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", amoCode],
    queryFn: () => qmsListAuditPersonnelOptions({ limit: 200 }),
    enabled: canManage,
    staleTime: 30_000,
  });

  useEffect(() => {
    const audit = auditQuery.data;
    if (!audit) return;
    setDraft({
      lead_auditor_user_id: audit.lead_auditor_user_id || "",
      observer_auditor_user_id: audit.observer_auditor_user_id || "",
      assistant_auditor_user_id: audit.assistant_auditor_user_id || "",
    });
  }, [auditQuery.data]);

  const eligibilityQueries = useQueries({
    queries: ROLE_CONFIG.map(({ field, role }) => ({
      queryKey: ["qms-audit-assignment-eligibility", amoCode, auditId, role, draft[field]],
      queryFn: ({ signal }: { signal: AbortSignal }) => getAuditAssignmentEligibility(amoCode, auditId, draft[field], role, signal),
      enabled: Boolean(auditId && draft[field]),
      staleTime: 1_500,
      retry: false,
    })),
  });

  const eligibilityByRole = useMemo(
    () => new Map(ROLE_CONFIG.map((config, index) => [config.role, eligibilityQueries[index]?.data])),
    [eligibilityQueries],
  );
  const allSelectedEligible = ROLE_CONFIG.every(({ field, role }) => !draft[field] || eligibilityByRole.get(role)?.eligible === true);
  const selectedIds = ROLE_CONFIG.map(({ field }) => draft[field]).filter(Boolean);
  const duplicateSelection = selectedIds.length !== new Set(selectedIds).size;

  const assignmentMutation = useMutation({
    mutationFn: () => updateAuditAssignments(amoCode, auditId, {
      lead_auditor_user_id: draft.lead_auditor_user_id || null,
      observer_auditor_user_id: draft.observer_auditor_user_id || null,
      assistant_auditor_user_id: draft.assistant_auditor_user_id || null,
      reason: reason.trim(),
    }),
    onSuccess: async () => {
      setError(null);
      setNotice("Audit team committed after the server re-ran the governed assignment gates.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-setup-assignment-audit", amoCode, auditKey] }),
        queryClient.invalidateQueries({ queryKey: ["qms-setup-audit-resolve", amoCode, auditKey] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-session-resolve", amoCode, auditKey] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      ]);
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Governed auditor assignment failed."),
  });

  const declarationMutation = useMutation({
    mutationFn: () => declareAuditIndependence(amoCode, auditId, {
      user_id: declaration.userId,
      declaration: declaration.declaration,
      relationship_to_subject: declaration.relationship.trim() || null,
      rationale: declaration.rationale.trim(),
    }),
    onSuccess: async () => {
      setError(null);
      setNotice("Audit-specific independence declaration recorded. Eligibility has been invalidated for re-evaluation.");
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-assignment-eligibility", amoCode, auditId] });
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Independence declaration could not be recorded."),
  });

  if (auditQuery.isLoading) return <article className="qms-occurrence-stage__card">Evaluating governed audit-team assignments…</article>;
  if (auditQuery.isError || !auditQuery.data) return <article className="qms-occurrence-stage__card" role="alert"><AlertTriangle size={16} /> Audit assignment context is unavailable.</article>;

  return (
    <article className="qms-occurrence-stage__card" aria-label="Governed audit team assignment">
      <header><UserCheck size={18} /><div><strong>Governed audit-team assignment</strong><small>People &amp; Privileges is authoritative for role privilege, training, audit-specific independence and workload capacity.</small></div></header>
      {error ? <div className="qms-occurrence-stage__message is-error" role="alert"><AlertTriangle size={15} /> {error}</div> : null}
      {notice ? <div className="qms-occurrence-stage__message" role="status"><CheckCircle2 size={15} /> {notice}</div> : null}

      <div className="qms-occurrence-stage__fields">
        {ROLE_CONFIG.map(({ field, role, label }) => {
          const assessment = eligibilityByRole.get(role);
          const independence = assessmentFor(assessment)?.independence;
          return (
            <label key={field}>
              <span>{label}</span>
              <select disabled={!canManage} value={draft[field]} onChange={(event) => setDraft((current) => ({ ...current, [field]: event.target.value }))}>
                <option value="">Unassigned</option>
                {(personnelQuery.data || []).map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>)}
              </select>
              <small className={assessment && !assessment.eligible ? "is-error" : ""}>{eligibilitySummary(assessment)}</small>
              {independence?.required ? <small>Independence: {independence.declaration || (independence.pending ? "pending" : independence.passed ? "independent" : "not satisfied")}</small> : null}
            </label>
          );
        })}
      </div>

      {duplicateSelection ? <div className="qms-occurrence-stage__message is-error"><ShieldAlert size={15} /> The same person cannot occupy multiple auditor roles on one occurrence.</div> : null}
      <label><span>Assignment decision reason</span><textarea rows={3} disabled={!canManage} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      {canManage ? <button type="button" className="is-primary" disabled={assignmentMutation.isPending || duplicateSelection || !allSelectedEligible || reason.trim().length < 8} onClick={() => assignmentMutation.mutate()}><UserCheck size={15} /> {assignmentMutation.isPending ? "Committing…" : "Commit governed assignments"}</button> : null}

      {canManage ? (
        <details className="qms-occurrence-stage__independence">
          <summary>Record audit-specific independence declaration</summary>
          <p>Record the declaration only after the named person has made it. Conflict or review-required declarations remain visible to the server gate and block assignment.</p>
          <div className="qms-occurrence-stage__fields">
            <label><span>Person</span><select value={declaration.userId} onChange={(event) => setDeclaration((current) => ({ ...current, userId: event.target.value }))}><option value="">Select person</option>{(personnelQuery.data || []).map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
            <label><span>Declaration</span><select value={declaration.declaration} onChange={(event) => setDeclaration((current) => ({ ...current, declaration: event.target.value as DeclarationDraft["declaration"] }))}><option value="INDEPENDENT">Independent</option><option value="CONFLICT">Conflict</option><option value="REQUIRES_REVIEW">Requires review</option></select></label>
          </div>
          <label><span>Relationship to audit subject</span><textarea rows={2} value={declaration.relationship} onChange={(event) => setDeclaration((current) => ({ ...current, relationship: event.target.value }))} placeholder="Required when a conflict exists" /></label>
          <label><span>Declaration rationale</span><textarea rows={3} value={declaration.rationale} onChange={(event) => setDeclaration((current) => ({ ...current, rationale: event.target.value }))} /></label>
          <button type="button" disabled={!declaration.userId || declaration.rationale.trim().length < 8 || declarationMutation.isPending || (declaration.declaration === "CONFLICT" && !declaration.relationship.trim())} onClick={() => declarationMutation.mutate()}>{declarationMutation.isPending ? "Recording…" : "Record declaration"}</button>
        </details>
      ) : null}
    </article>
  );
};

export default AuditAssignmentGovernancePanel;
