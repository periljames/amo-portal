import React, { useEffect, useMemo, useState } from "react";
import { savedTeamOptions } from "./auditSetupControls";
import { useAuditAuthorityOnline } from "./useSavedAuditTeam";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ShieldAlert, UserCheck } from "lucide-react";
import { Link } from "react-router-dom";

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
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { qmsPeopleWorkspacePath } from "../../../pages/qms/routes/qmsWorkspaceRegistry";

type Props = { amoCode: string; auditKey: string; onDirtyChange?: (dirty: boolean) => void };
type RoleField = "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id";
type AssignmentDraft = Record<RoleField, string>;
type DeclarationDraft = {
  userId: string;
  declaration: "" | "INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW";
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

const EMPTY_ASSIGNMENT: AssignmentDraft = {
  lead_auditor_user_id: "",
  observer_auditor_user_id: "",
  assistant_auditor_user_id: "",
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
  if (!row) return "Select a person.";
  if (!row.governance_configured) {
    if (row.mode === "CONFIGURATION_REQUIRED") {
      return row.reason || "Competence rules not configured.";
    }
    return "Eligible · compatibility mode (no privilege rule yet).";
  }
  if (row.eligible) return "Eligible";
  const gates = failedGates(row);
  return gates.length ? `Blocked · ${gates.join(" · ")}` : row.reason || "Blocked";
}

function privilegeTypeForRole(role: AuditAssignmentRole): "LEAD_AUDITOR" | "AUDITOR" {
  return role === "LEAD_AUDITOR" ? "LEAD_AUDITOR" : "AUDITOR";
}

const AuditAssignmentGovernancePanel: React.FC<Props> = ({ amoCode, auditKey, onDirtyChange }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const authorityOnline = useAuditAuthorityOnline();
  const [draftOverride, setDraftOverride] = useState<AssignmentDraft | null>(null);
  const [reason, setReason] = useState("Assign audit team after eligibility checks.");
  const [declaration, setDeclaration] = useState<DeclarationDraft>({
    userId: "",
    declaration: "",
    relationship: "",
    rationale: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const persistedDraft = useMemo<AssignmentDraft>(() => {
    const audit = auditQuery.data;
    if (!audit) return EMPTY_ASSIGNMENT;
    return {
      lead_auditor_user_id: audit.lead_auditor_user_id || "",
      observer_auditor_user_id: audit.observer_auditor_user_id || "",
      assistant_auditor_user_id: audit.assistant_auditor_user_id || "",
    };
  }, [auditQuery.data]);
  const draft = draftOverride ?? persistedDraft;
  const dirty = ROLE_CONFIG.some(({ field }) => draft[field] !== persistedDraft[field]);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  const updateDraft = (field: RoleField, value: string) => {
    setDraftOverride((current) => ({ ...(current ?? persistedDraft), [field]: value }));
  };

  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", amoCode],
    queryFn: () => qmsListAuditPersonnelOptions(amoCode, { limit: 200 }),
    enabled: canManage,
    staleTime: 30_000,
  });

  const eligibilityQueries = useQueries({
    queries: ROLE_CONFIG.map(({ field, role }) => ({
      queryKey: ["qms-audit-assignment-eligibility", amoCode, auditId, role, draft[field]],
      queryFn: ({ signal }: { signal: AbortSignal }) => getAuditAssignmentEligibility(amoCode, auditId, draft[field], role, signal),
      enabled: Boolean(auditId && draft[field]),
      staleTime: 30_000,
      refetchOnMount: "always" as const,
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
  const configurationGap = (() => {
    for (const { field, role } of ROLE_CONFIG) {
      if (!draft[field]) continue;
      const row = eligibilityByRole.get(role);
      if (row && !row.governance_configured && row.mode === "CONFIGURATION_REQUIRED") {
        return { role, reason: row.reason || "Competence rules not configured.", ruleType: privilegeTypeForRole(role) };
      }
    }
    return null;
  })();
  const peopleSetupPath = configurationGap
    ? qmsPeopleWorkspacePath(amoCode, { tab: "rules", action: "CREATE_RULE", ruleType: configurationGap.ruleType })
    : qmsPeopleWorkspacePath(amoCode, { tab: "privileges", action: "CREATE" });

  const assignmentMutation = useMutation({
    mutationFn: () => updateAuditAssignments(amoCode, auditId, {
      lead_auditor_user_id: draft.lead_auditor_user_id || null,
      observer_auditor_user_id: draft.observer_auditor_user_id || null,
      assistant_auditor_user_id: draft.assistant_auditor_user_id || null,
      reason: reason.trim(),
    }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(auditOccurrenceQueryKey(amoCode, auditKey), {
        ...auditQuery.data,
        lead_auditor_user_id: saved.lead_auditor_user_id,
        observer_auditor_user_id: saved.observer_auditor_user_id,
        assistant_auditor_user_id: saved.assistant_auditor_user_id,
      });
      setDraftOverride(null);
      setError(null);
      setNotice("Team saved.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: auditOccurrenceQueryKey(amoCode, auditKey) }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      ]);
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Governed auditor assignment failed."),
  });

  const declarationMutation = useMutation({
    mutationFn: () => {
      if (!declaration.userId || !declaration.declaration) throw new Error("Select a person and their declaration.");
      return declareAuditIndependence(amoCode, auditId, {
      user_id: declaration.userId,
      declaration: declaration.declaration,
      relationship_to_subject: declaration.relationship.trim() || null,
      rationale: declaration.rationale.trim(),
    });
    },
    onSuccess: async () => {
      setError(null);
      setNotice("Independence declaration recorded.");
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-assignment-eligibility", amoCode, auditId] });
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Independence declaration could not be recorded."),
  });

  if (auditQuery.isLoading) return <article className="qms-occurrence-stage__card">Evaluating governed audit-team assignments…</article>;
  if (!auditQuery.data) return <article className="qms-occurrence-stage__card" role="alert"><AlertTriangle size={16} /> Audit assignment context is unavailable.</article>;
  const people = savedTeamOptions(auditQuery.data, personnelQuery.data || []);
  const saveBlocked = !authorityOnline ? "Reconnect to verify and save assignments."
    : !draft.lead_auditor_user_id ? "A lead auditor is required. Observer and assistant are optional."
    : !dirty ? "No assignment changes to save."
    : duplicateSelection ? "Choose a different person for each role."
    : eligibilityQueries.some((query, index) => draft[ROLE_CONFIG[index].field] && query.isError) ? "Eligibility checks failed. Retry the affected check."
    : !allSelectedEligible ? "All selected auditors must pass eligibility and independence checks."
    : reason.trim().length < 8 ? "Enter a decision reason of at least 8 characters." : "";

  return (
    <article id="audit-occurrence-team" className="qms-occurrence-stage__card" aria-label="Audit team assignment">
      <header>
        <div>
          <strong>Team</strong>
        </div>
      </header>
      {error ? (
        <div className="qms-occurrence-stage__message is-error" role="alert">
          <AlertTriangle size={15} /> {error}
        </div>
      ) : null}
      {notice ? (
        <div className="qms-occurrence-stage__message" role="status">
          <CheckCircle2 size={15} /> {notice}
        </div>
      ) : null}

      {configurationGap ? (
        <div className="qms-occurrence-stage__message is-error" role="status">
          <ShieldAlert size={15} />
          <span>
            {configurationGap.reason}{" "}
            <Link to={peopleSetupPath}>Open People &amp; Privileges</Link>
            {" · "}
            <Link to={qmsPeopleWorkspacePath(amoCode, { tab: "privileges", action: "CREATE", ruleType: configurationGap.ruleType })}>
              Batch-authorize people
            </Link>
          </span>
        </div>
      ) : null}

      {personnelQuery.isError ? <div role="alert" className="qms-occurrence-stage__message is-error">
        The personnel directory could not be loaded. Saved assignments are retained.
        <button type="button" onClick={() => void personnelQuery.refetch()}>Retry directory</button>
      </div> : null}
      <p role="status">{dirty ? "Unsaved team changes" : "Showing saved team assignments"}</p>
      <div className="qms-occurrence-stage__fields">
        {ROLE_CONFIG.map(({ field, role, label }) => {
          const assessment = eligibilityByRole.get(role);
          const independence = assessmentFor(assessment)?.independence;
          return (
            <label key={field}>
              <span>{label} · {role === "LEAD_AUDITOR" ? "Required" : "Optional"}</span>
              <select disabled={!canManage || assignmentMutation.isPending || personnelQuery.isPending} value={draft[field]} onChange={(event) => updateDraft(field, event.target.value)}>
                <option value="">Unassigned</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
              <small className={assessment && !assessment.eligible ? "is-error" : ""}>{draft[field] && !assessment ? "Checking eligibility…" : eligibilitySummary(assessment)}</small>
              {eligibilityQueries[ROLE_CONFIG.findIndex((item) => item.field === field)]?.isError ? <button type="button" onClick={() => void eligibilityQueries[ROLE_CONFIG.findIndex((item) => item.field === field)].refetch()}>Retry eligibility</button> : null}
              {independence?.required ? (
                <small>
                  Independence:{" "}
                  {independence.declaration ||
                    (independence.pending ? "pending" : independence.passed ? "independent" : "not satisfied")}
                </small>
              ) : null}
            </label>
          );
        })}
      </div>

      {duplicateSelection ? (
        <div className="qms-occurrence-stage__message is-error">
          <ShieldAlert size={15} /> Same person cannot hold multiple auditor roles.
        </div>
      ) : null}
      <details><summary>Assignment note</summary><label>
        <span>Decision reason</span>
        <textarea rows={2} disabled={!canManage} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label></details>
      {canManage ? (
        <button
          type="button"
          className="is-primary"
          disabled={assignmentMutation.isPending || Boolean(saveBlocked)}
          aria-describedby="audit-team-save-help"
          onClick={() => assignmentMutation.mutate()}
        >
          <UserCheck size={15} /> {assignmentMutation.isPending ? "Saving…" : "Save team assignments"}
        </button>
      ) : null}

      <small id="audit-team-save-help">{saveBlocked || "Ready to save team changes."}</small>
      {dirty ? <button type="button" disabled={assignmentMutation.isPending} onClick={() => setDraftOverride(null)}>Discard team changes</button> : null}

      {canManage ? (
        <details className="qms-occurrence-stage__independence">
          <summary>Independence declaration</summary>
          <p>Record only after the person has declared. Conflict / review-required blocks assignment.</p>
          <div className="qms-occurrence-stage__fields">
            <label>
              <span>Person</span>
              <select
                value={declaration.userId}
                onChange={(event) => setDeclaration({ userId: event.target.value, declaration: "", relationship: "", rationale: "" })}
              >
                <option value="">Select person</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Declaration</span>
              <select
                disabled={!declaration.userId}
                value={declaration.declaration}
                onChange={(event) =>
                  setDeclaration((current) => ({
                    ...current,
                    declaration: event.target.value as DeclarationDraft["declaration"],
                  }))
                }
              >
                <option value="">Select declaration</option>
                <option value="INDEPENDENT">Independent</option>
                <option value="CONFLICT">Conflict</option>
                <option value="REQUIRES_REVIEW">Requires review</option>
              </select>
            </label>
          </div>
          <label>
            <span>Relationship</span>
            <textarea
              rows={2}
              value={declaration.relationship}
              onChange={(event) => setDeclaration((current) => ({ ...current, relationship: event.target.value }))}
              placeholder="Required when a conflict exists"
            />
          </label>
          <label>
            <span>Rationale</span>
            <textarea
              rows={2}
              value={declaration.rationale}
              onChange={(event) => setDeclaration((current) => ({ ...current, rationale: event.target.value }))}
            />
          </label>
          <button
            type="button"
            disabled={
              !declaration.userId ||
              !authorityOnline ||
              !declaration.declaration ||
              declaration.rationale.trim().length < 8 ||
              declarationMutation.isPending ||
              (declaration.declaration === "CONFLICT" && !declaration.relationship.trim())
            }
            onClick={() => declarationMutation.mutate()}
          >
            {declarationMutation.isPending ? "Recording…" : "Record declaration"}
          </button>
        </details>
      ) : null}
    </article>
  );
};

export default AuditAssignmentGovernancePanel;
