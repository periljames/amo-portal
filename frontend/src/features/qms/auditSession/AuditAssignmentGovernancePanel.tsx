import React, { useEffect, useMemo, useState } from "react";
import { savedTeamOptions } from "./auditSetupControls";
import { useAuditAuthorityOnline } from "./useSavedAuditTeam";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, HelpCircle, ShieldAlert, UserCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { qmsListAuditPersonnelOptions } from "../../../services/qms";
import { personDisplay } from "../../../utils/personDisplay";
import {
  getAuditAssignmentEligibility,
  updateAuditAssignments,
  type AuditAssignmentAssessment,
  type AuditAssignmentEligibility,
  type AuditAssignmentIndependence,
  type AuditAssignmentRole,
} from "../../../services/qmsAuditAssignments";
import { getQmsIndependencePolicy, type QmsIndependencePolicy } from "../../../services/qmsPeople";
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { qmsPeopleWorkspacePath } from "../../../pages/qms/routes/qmsWorkspaceRegistry";

type Props = { amoCode: string; auditKey: string; onDirtyChange?: (dirty: boolean) => void };
type RoleField = "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id";
type AssignmentDraft = Record<RoleField, string>;

const ROLE_CONFIG: Array<{ field: RoleField; role: AuditAssignmentRole; label: string }> = [
  { field: "lead_auditor_user_id", role: "LEAD_AUDITOR", label: "Lead Auditor" },
  { field: "observer_auditor_user_id", role: "OBSERVER_AUDITOR", label: "Observer / Trainee Auditor" },
  { field: "assistant_auditor_user_id", role: "ASSISTANT_AUDITOR", label: "Assistant Auditor" },
];

const GATE_LABELS: Record<string, string> = {
  workforce_active: "active workforce record",
  active_privilege: "current Quality authorization",
  scope_authorized: "scope authorisation",
  training_current_verified: "required training is not currently verified",
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
  if (!row) return "";
  if (!row.governance_configured) {
    if (row.mode === "CONFIGURATION_REQUIRED") {
      return row.reason || "Competence rules not configured.";
    }
    return "";
  }
  if (row.eligible) return "";
  const gates = failedGates(row);
  return gates.length ? `Blocked · ${gates.join(" · ")}` : row.reason || "Blocked";
}

function privilegeTypeForRole(role: AuditAssignmentRole): "LEAD_AUDITOR" | "AUDITOR" {
  return role === "LEAD_AUDITOR" ? "LEAD_AUDITOR" : "AUDITOR";
}

function IndependenceStatus({ independence }: { independence?: AuditAssignmentIndependence | null }) {
  if (!independence?.required) return null;
  const conflicts = independence.conflicts || [];
  const remediations = independence.remediations || [];
  const blocked = independence.passed === false;
  const pending = Boolean(independence.pending) && !blocked;
  // Stay silent when clear — no “all clear” copy or future-integration commentary.
  if (!blocked && !pending && !conflicts.length) return null;

  return (
    <div
      className={`qms-occurrence-stage__independence-status ${blocked ? "is-blocked" : "is-pending"}`}
      role={blocked ? "alert" : "status"}
    >
      <small>
        {blocked
          ? "Independence conflict — assignment blocked"
          : "Independence check pending"}
      </small>
      {blocked && independence.message ? <small>{independence.message}</small> : null}
      {conflicts.length ? (
        <ul>
          {conflicts.map((item) => (
            <li key={`${item.code}-${item.title}`}>
              <strong>{item.title || item.code}</strong>
              {item.message ? <span> — {item.message}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {blocked && remediations.length ? (
        <ul className="qms-occurrence-stage__independence-remediations">
          {remediations.map((item) => (
            <li key={item.code}>
              <strong>{item.label}</strong>
              {item.detail ? <span> — {item.detail}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

const AuditAssignmentGovernancePanel: React.FC<Props> = ({ amoCode, auditKey, onDirtyChange }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const authorityOnline = useAuditAuthorityOnline();
  const [draftOverride, setDraftOverride] = useState<AssignmentDraft | null>(null);
  const [reason, setReason] = useState("Assign audit team after eligibility checks.");
  const [showRules, setShowRules] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const policyQuery = useQuery({
    queryKey: ["qms-independence-policy", amoCode],
    queryFn: ({ signal }) => getQmsIndependencePolicy(amoCode, signal),
    staleTime: 60_000,
  });
  const policy: QmsIndependencePolicy | undefined = policyQuery.data;

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
      enabled: Boolean(authorityOnline && auditId && draft[field]),
      staleTime: 5 * 60_000,
      gcTime: 24 * 60 * 60_000,
      refetchOnMount: authorityOnline ? ("always" as const) : false,
      refetchOnReconnect: true,
      networkMode: "online" as const,
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
    ? qmsPeopleWorkspacePath(amoCode, { tab: "administration", action: "CREATE_RULE", ruleType: configurationGap.ruleType })
    : qmsPeopleWorkspacePath(amoCode, { tab: "people", action: "CREATE" });

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

  if (auditQuery.isLoading) return <article className="qms-occurrence-stage__card">Evaluating governed audit-team assignments…</article>;
  if (!auditQuery.data) return <article className="qms-occurrence-stage__card" role="alert"><AlertTriangle size={16} /> Audit assignment context is unavailable.</article>;
  const people = savedTeamOptions(auditQuery.data, personnelQuery.data || []);
  const saveBlocked = !authorityOnline
    ? dirty
      ? "Reconnect to save assignment changes."
      : ""
    : !draft.lead_auditor_user_id
      ? "A lead auditor is required. Observer and assistant are optional."
      : !dirty
        ? "No assignment changes to save."
        : duplicateSelection
          ? "Choose a different person for each role."
          : eligibilityQueries.some(
                (query, index) =>
                  draft[ROLE_CONFIG[index].field] && query.isError && !query.data,
              )
            ? "Eligibility checks failed. Retry the affected check."
            : !allSelectedEligible
              ? "All selected auditors must pass eligibility and independence checks."
              : reason.trim().length < 8
                ? "Enter a decision reason of at least 8 characters."
                : "";

  return (
    <article id="audit-occurrence-team" className="qms-occurrence-stage__card qms-audit-team-panel" aria-label="Audit team assignment">
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
            <Link to={peopleSetupPath}>Open People &amp; Authorization Control</Link>
          </span>
        </div>
      ) : null}

      {personnelQuery.isError ? (
        <div role="alert" className="qms-occurrence-stage__message is-error">
          Personnel directory unavailable.
          <button type="button" onClick={() => void personnelQuery.refetch()}>
            Retry
          </button>
        </div>
      ) : null}

      {dirty ? (
        <p className="qms-audit-team-panel__status" role="status">
          Unsaved team changes
        </p>
      ) : null}

      <div className="qms-occurrence-stage__fields">
        {ROLE_CONFIG.map(({ field, role, label }) => {
          const assessment = eligibilityByRole.get(role);
          const independence = assessmentFor(assessment)?.independence;
          const eligibilityQuery =
            eligibilityQueries[ROLE_CONFIG.findIndex((item) => item.field === field)];
          const summary = eligibilitySummary(assessment);
          const checking = Boolean(draft[field] && !assessment && !eligibilityQuery?.isError);
          return (
            <label key={field} className="qms-audit-team-panel__role">
              <span>
                {label}
                <em>{role === "LEAD_AUDITOR" ? "Required" : "Optional"}</em>
              </span>
              <select
                disabled={
                  !canManage ||
                  assignmentMutation.isPending ||
                  personnelQuery.isPending
                }
                value={draft[field]}
                onChange={(event) => updateDraft(field, event.target.value)}
              >
                <option value="">Unassigned</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {personDisplay(person.full_name)}
                  </option>
                ))}
              </select>
              {checking ? <small>Checking…</small> : null}
              {summary ? (
                <small className="is-error">{summary}</small>
              ) : null}
              {eligibilityQuery?.isError ? (
                <button
                  type="button"
                  className="qms-audit-team-panel__retry"
                  onClick={() => void eligibilityQuery.refetch()}
                >
                  Retry check
                </button>
              ) : null}
              <IndependenceStatus independence={independence} />
            </label>
          );
        })}
      </div>

      {duplicateSelection ? (
        <div className="qms-occurrence-stage__message is-error">
          <ShieldAlert size={15} /> Same person cannot hold multiple auditor roles.
        </div>
      ) : null}

      {canManage ? (
        <div className="qms-audit-team-panel__footer">
          <details className="qms-audit-team-panel__note">
            <summary>Assignment note</summary>
            <label>
              <span>Decision reason</span>
              <textarea
                rows={2}
                disabled={!canManage}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          </details>
          <div className="qms-audit-team-panel__actions">
            {dirty ? (
              <button
                type="button"
                className="is-secondary"
                disabled={assignmentMutation.isPending}
                onClick={() => setDraftOverride(null)}
              >
                Discard
              </button>
            ) : null}
            <button
              type="button"
              className="is-primary"
              disabled={assignmentMutation.isPending || Boolean(saveBlocked)}
              title={saveBlocked || undefined}
              onClick={() => assignmentMutation.mutate()}
            >
              <UserCheck size={15} />{" "}
              {assignmentMutation.isPending ? "Saving…" : "Save team"}
            </button>
          </div>
          {saveBlocked && dirty ? (
            <small className="qms-audit-team-panel__help" id="audit-team-save-help">
              {saveBlocked}
            </small>
          ) : null}
        </div>
      ) : null}

      <button
        type="button"
        className="qms-occurrence-stage__icon-button qms-audit-team-panel__rules"
        aria-label="Independence rules"
        title="Independence rules"
        onClick={() => setShowRules(true)}
      >
        <HelpCircle size={15} aria-hidden="true" />
      </button>

      {showRules ? (
        <div
          className="upsell-modal__backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Independence rules"
          onClick={(event) => {
            if (event.target === event.currentTarget) setShowRules(false);
          }}
        >
          <section className="upsell-modal" onClick={(event) => event.stopPropagation()}>
            <header className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">System policy</p>
                <h3 className="upsell-modal__title">Independence rules</h3>
              </div>
              <button
                type="button"
                className="upsell-modal__close"
                onClick={() => setShowRules(false)}
                aria-label="Close"
              >
                ×
              </button>
            </header>
            <div className="upsell-modal__body">
              <p>
                Independence is enforced by the portal. Issues appear only when a
                selected auditor conflicts with the audit subject.
              </p>
              <ul>
                {(policy?.rules || []).map((rule) => (
                  <li key={rule.code}>
                    <strong>{rule.title}</strong>
                    <small>{rule.standard}</small>
                    <span>{rule.summary}</span>
                  </li>
                ))}
              </ul>
              <h4>Remediation options</h4>
              <ul>
                {(policy?.remediations || []).map((item) => (
                  <li key={item.code}>
                    <strong>{item.label}</strong>
                    <span>{item.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
            <footer>
              <button type="button" onClick={() => setShowRules(false)}>
                Close
              </button>
              <Link to={qmsPeopleWorkspacePath(amoCode, { tab: "privileges" })}>
                Open People &amp; Authorization Control
              </Link>
            </footer>
          </section>
        </div>
      ) : null}
    </article>
  );
};

export default AuditAssignmentGovernancePanel;
