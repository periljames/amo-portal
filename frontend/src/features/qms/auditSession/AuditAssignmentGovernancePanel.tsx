import React, { useMemo, useState } from "react";
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
import { resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { qmsPeopleWorkspacePath } from "../../../pages/qms/routes/qmsWorkspaceRegistry";

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

const AuditAssignmentGovernancePanel: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [draftOverride, setDraftOverride] = useState<AssignmentDraft | null>(null);
  const [reason, setReason] = useState("Assign audit team after eligibility checks.");
  const [declaration, setDeclaration] = useState<DeclarationDraft>({
    userId: "",
    declaration: "INDEPENDENT",
    relationship: "",
    rationale: "No conflict of interest for this occurrence.",
  });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms-setup-assignment-audit", amoCode, auditKey],
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
  const configurationGap = useMemo(() => {
    for (const { field, role } of ROLE_CONFIG) {
      if (!draft[field]) continue;
      const row = eligibilityByRole.get(role);
      if (row && !row.governance_configured && row.mode === "CONFIGURATION_REQUIRED") {
        return { role, reason: row.reason || "Competence rules not configured.", ruleType: privilegeTypeForRole(role) };
      }
    }
    return null;
  }, [draft, eligibilityByRole]);
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
    onSuccess: async () => {
      setDraftOverride(null);
      setError(null);
      setNotice("Team assignments committed.");
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
      setNotice("Independence declaration recorded.");
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-assignment-eligibility", amoCode, auditId] });
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "Independence declaration could not be recorded."),
  });

  if (auditQuery.isLoading) return <article className="qms-occurrence-stage__card">Evaluating governed audit-team assignments…</article>;
  if (auditQuery.isError || !auditQuery.data) return <article className="qms-occurrence-stage__card" role="alert"><AlertTriangle size={16} /> Audit assignment context is unavailable.</article>;

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

      <div className="qms-occurrence-stage__fields">
        {ROLE_CONFIG.map(({ field, role, label }) => {
          const assessment = eligibilityByRole.get(role);
          const independence = assessmentFor(assessment)?.independence;
          return (
            <label key={field}>
              <span>{label}</span>
              <select disabled={!canManage} value={draft[field]} onChange={(event) => updateDraft(field, event.target.value)}>
                <option value="">Unassigned</option>
                {(personnelQuery.data || []).map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                    {person.role ? ` · ${person.role}` : ""}
                  </option>
                ))}
              </select>
              <small className={assessment && !assessment.eligible ? "is-error" : ""}>{eligibilitySummary(assessment)}</small>
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
      <label>
        <span>Decision reason</span>
        <textarea rows={2} disabled={!canManage} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {canManage ? (
        <button
          type="button"
          className="is-primary"
          disabled={assignmentMutation.isPending || duplicateSelection || !allSelectedEligible || reason.trim().length < 8}
          onClick={() => assignmentMutation.mutate()}
        >
          <UserCheck size={15} /> {assignmentMutation.isPending ? "Committing…" : "Commit team"}
        </button>
      ) : null}

      {canManage ? (
        <details className="qms-occurrence-stage__independence">
          <summary>Independence declaration</summary>
          <p>Record only after the person has declared. Conflict / review-required blocks assignment.</p>
          <div className="qms-occurrence-stage__fields">
            <label>
              <span>Person</span>
              <select
                value={declaration.userId}
                onChange={(event) => setDeclaration((current) => ({ ...current, userId: event.target.value }))}
              >
                <option value="">Select person</option>
                {(personnelQuery.data || []).map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Declaration</span>
              <select
                value={declaration.declaration}
                onChange={(event) =>
                  setDeclaration((current) => ({
                    ...current,
                    declaration: event.target.value as DeclarationDraft["declaration"],
                  }))
                }
              >
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