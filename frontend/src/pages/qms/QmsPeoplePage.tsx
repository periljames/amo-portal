import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Plus, RefreshCw, Search, ShieldCheck, UserRoundCheck, X } from "lucide-react";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { clearQmsApiResponseCache } from "../../services/apiClient";
import {
  createQmsPrivilege,
  decideQmsPrivilege,
  declareQmsIndependence,
  getQmsEligibility,
  getQmsPeopleSummary,
  listQmsPrivilegeRules,
  listQmsPrivileges,
  preflightQmsAuditorAssignment,
  type QmsAuditorAssignmentAssessment,
  type QmsAuditorAssignmentRole,
  type QmsAuditorEligibilityPreflight,
  type QmsEligibility,
  type QmsPeopleSummary,
  type QmsPrivilege,
  type QmsPrivilegeDecision,
  type QmsPrivilegeRule,
} from "../../services/qmsPeople";
import "../../styles/qms-people.css";

type Props = { amoCode: string };
type ActionMode = "NONE" | "CREATE" | "DECISION" | "AUDIT_ASSIGNMENT" | "INDEPENDENCE";
type AssignmentContextType = "AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER" | "";
type AssignmentSubmission = {
  selected_privilege_id: string;
  selected_privilege_code: string;
  selected_scope_key: string;
  user_id: string;
  assignment_role: QmsAuditorAssignmentRole;
  assignment_date: string;
  assignment_scope_key: string;
  context_type: AssignmentContextType;
  context_id: string;
};

const EMPTY_SUMMARY: QmsPeopleSummary = { active_privileges: 0, expiring_within_60_days: 0, suspended_privileges: 0, independence_exceptions: 0 };

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "The People & Privileges operation could not be completed.";
}

function humanise(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function localDateKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function shortIdentifier(value: string): string {
  if (value.length <= 24) return value;
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

function bindEligibilityToPrivilege(snapshot: QmsEligibility, privilege: QmsPrivilege): QmsEligibility {
  const selectedPrivilegeMatches = privilege.status === "ACTIVE" && snapshot.active_privilege?.id === privilege.id;
  return {
    ...snapshot,
    eligible: snapshot.eligible && selectedPrivilegeMatches,
    hard_gates: { ...snapshot.hard_gates, selected_privilege_active: selectedPrivilegeMatches },
  };
}

function selectedAssignmentAssessment(
  result: QmsAuditorEligibilityPreflight | null,
  rule: QmsPrivilegeRule | null,
): QmsAuditorAssignmentAssessment | null {
  if (!result || !rule) return null;
  if (result.assessment?.rule_id === rule.id) return result.assessment;
  return result.assessments.find((assessment) => assessment.rule_id === rule.id) || null;
}

const QmsPeoplePage: React.FC<Props> = ({ amoCode }) => {
  const [summary, setSummary] = useState<QmsPeopleSummary>(EMPTY_SUMMARY);
  const [rules, setRules] = useState<QmsPrivilegeRule[]>([]);
  const [privileges, setPrivileges] = useState<QmsPrivilege[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<QmsPrivilege["status"] | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [actionMode, setActionMode] = useState<ActionMode>("NONE");

  const [ruleId, setRuleId] = useState("");
  const [userId, setUserId] = useState("");
  const [scopeKey, setScopeKey] = useState("GLOBAL");
  const [creating, setCreating] = useState(false);

  const [selectedId, setSelectedId] = useState("");
  const [decisionType, setDecisionType] = useState<QmsPrivilegeDecision["decision_type"]>("GRANT");
  const [decisionReason, setDecisionReason] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [deciding, setDeciding] = useState(false);

  const [selectedSnapshot, setSelectedSnapshot] = useState<QmsEligibility | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotRevision, setSnapshotRevision] = useState(0);

  const [assignmentResult, setAssignmentResult] = useState<QmsAuditorEligibilityPreflight | null>(null);
  const [assignmentResultInput, setAssignmentResultInput] = useState<AssignmentSubmission | null>(null);
  const [assignmentRole, setAssignmentRole] = useState<QmsAuditorAssignmentRole>("OBSERVER_AUDITOR");
  const [assignmentDate, setAssignmentDate] = useState(localDateKey());
  const [assignmentScopeKey, setAssignmentScopeKey] = useState("");
  const [assignmentContextType, setAssignmentContextType] = useState<AssignmentContextType>("");
  const [assignmentContextId, setAssignmentContextId] = useState("");
  const [checkingAssignment, setCheckingAssignment] = useState(false);
  const assignmentRequestRevision = useRef(0);

  const [indUserId, setIndUserId] = useState("");
  const [indContextType, setIndContextType] = useState<"AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER">("AUDIT_SCHEDULE");
  const [indContextId, setIndContextId] = useState("");
  const [indDeclaration, setIndDeclaration] = useState<"INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW">("INDEPENDENT");
  const [indRelationship, setIndRelationship] = useState("");
  const [indRationale, setIndRationale] = useState("");
  const [declaring, setDeclaring] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!signal) clearQmsApiResponseCache();
    setLoading(true);
    setError("");
    try {
      const [nextSummary, ruleResponse, privilegeResponse] = await Promise.all([
        getQmsPeopleSummary(amoCode, signal),
        listQmsPrivilegeRules(amoCode, signal),
        listQmsPrivileges(amoCode, {}, signal),
      ]);
      if (signal?.aborted) return;
      setSummary(nextSummary);
      setRules(ruleResponse.items);
      setPrivileges(privilegeResponse.items);
      setSnapshotRevision((value) => value + 1);
      setRuleId((value) => value || ruleResponse.items[0]?.id || "");
      setSelectedId((value) => value && privilegeResponse.items.some((item) => item.id === value) ? value : privilegeResponse.items[0]?.id || "");
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError")) setError(messageFromError(nextError));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [amoCode]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const selected = privileges.find((item) => item.id === selectedId) || null;
  const selectedRule = selected ? rules.find((rule) => rule.id === selected.rule_id) || null : null;
  const selectedIsAuditorPrivilege = selectedRule?.privilege_type === "AUDITOR" || selectedRule?.privilege_type === "LEAD_AUDITOR";
  const canManagePrivileges = hasQmsRolePermission("qms.training.manage");
  const canManageAuditGovernance = hasQmsRolePermission("qms.audit.manage");
  const canRunAuditPreflight = selectedIsAuditorPrivilege && canManageAuditGovernance;
  const assignmentContextRequired = Boolean(selectedRule?.independence_required);
  const assignmentInputComplete = Boolean(
    selected
    && selectedRule
    && assignmentDate
    && assignmentScopeKey.trim()
    && (!assignmentContextRequired || (assignmentContextType && assignmentContextId.trim())),
  );

  const invalidateAssignmentResult = useCallback(() => {
    assignmentRequestRevision.current += 1;
    setAssignmentResult(null);
    setAssignmentResultInput(null);
  }, []);

  useEffect(() => {
    invalidateAssignmentResult();
    setCheckingAssignment(false);
    setAssignmentRole(selectedRule?.privilege_type === "LEAD_AUDITOR" ? "LEAD_AUDITOR" : "OBSERVER_AUDITOR");
    setAssignmentDate(localDateKey());
    setAssignmentScopeKey(selected?.scope_key && !["GLOBAL", "*"].includes(selected.scope_key.toUpperCase()) ? selected.scope_key : "");
    setAssignmentContextType("");
    setAssignmentContextId("");
  }, [invalidateAssignmentResult, selected?.id, selected?.scope_key, selectedRule?.privilege_type]);

  useEffect(() => {
    if (!selected) {
      setSelectedSnapshot(null);
      return;
    }
    const controller = new AbortController();
    setSnapshotLoading(true);
    setSelectedSnapshot(null);
    void getQmsEligibility(amoCode, { userId: selected.user_id, privilegeCode: selected.privilege_code }, controller.signal)
      .then((snapshot) => {
        if (!controller.signal.aborted) setSelectedSnapshot(bindEligibilityToPrivilege(snapshot, selected));
      })
      .catch((nextError) => {
        if (!(nextError instanceof DOMException && nextError.name === "AbortError")) setSelectedSnapshot(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setSnapshotLoading(false);
      });
    return () => controller.abort();
  }, [amoCode, selected, snapshotRevision]);

  const visiblePrivileges = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return privileges.filter((item) => {
      if (statusFilter !== "ALL" && item.status !== statusFilter) return false;
      if (!needle) return true;
      return [item.user_id, item.privilege_code, item.scope_key].some((value) => value.toLowerCase().includes(needle));
    });
  }, [privileges, search, statusFilter]);

  const assignmentResultAppliesToSelection = Boolean(
    assignmentResult
    && assignmentResultInput
    && selected
    && assignmentResultInput.selected_privilege_id === selected.id,
  );
  const assignmentAssessment = assignmentResultAppliesToSelection ? selectedAssignmentAssessment(assignmentResult, selectedRule) : null;
  const assignmentUsesSelectedPrivilege = Boolean(selected && assignmentAssessment?.active_privilege?.id === selected.id);
  const assignmentEligible = Boolean(assignmentResultAppliesToSelection && assignmentResult?.eligible && assignmentAssessment?.eligible && assignmentUsesSelectedPrivilege);

  function openAction(mode: ActionMode) {
    if ((mode === "CREATE" || mode === "DECISION") && !canManagePrivileges) return;
    if ((mode === "AUDIT_ASSIGNMENT" || mode === "INDEPENDENCE") && !canManageAuditGovernance) return;
    setError("");
    if (mode === "AUDIT_ASSIGNMENT") invalidateAssignmentResult();
    if (selected && mode === "INDEPENDENCE") setIndUserId(selected.user_id);
    setActionMode(mode);
  }

  function closeAction() {
    if (actionMode === "AUDIT_ASSIGNMENT") {
      invalidateAssignmentResult();
      setCheckingAssignment(false);
    }
    setActionMode("NONE");
  }

  async function submitDraft(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges || !ruleId || !userId.trim()) return;
    setCreating(true);
    setError("");
    try {
      const created = await createQmsPrivilege(amoCode, { rule_id: ruleId, user_id: userId.trim(), scope_key: scopeKey.trim() || "GLOBAL" });
      setUserId("");
      setScopeKey("GLOBAL");
      await load();
      setSelectedId(created.id);
      setActionMode("NONE");
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setCreating(false);
    }
  }

  async function submitDecision(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges || !selected || decisionReason.trim().length < 8) return;
    setDeciding(true);
    setError("");
    try {
      await decideQmsPrivilege(amoCode, selected.id, { decision_type: decisionType, rationale: decisionReason.trim(), effective_from: effectiveFrom || undefined, expires_on: expiresOn || undefined });
      setDecisionReason("");
      setEffectiveFrom("");
      setExpiresOn("");
      await load();
      setActionMode("NONE");
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setDeciding(false);
    }
  }

  async function submitAuditAssignment(event: FormEvent) {
    event.preventDefault();
    if (!selected || !selectedRule || !canRunAuditPreflight || !assignmentInputComplete || checkingAssignment) return;

    const submitted: AssignmentSubmission = {
      selected_privilege_id: selected.id,
      selected_privilege_code: selected.privilege_code,
      selected_scope_key: selected.scope_key,
      user_id: selected.user_id,
      assignment_role: assignmentRole,
      assignment_date: assignmentDate,
      assignment_scope_key: assignmentScopeKey.trim(),
      context_type: assignmentContextType,
      context_id: assignmentContextId.trim(),
    };
    const requestRevision = assignmentRequestRevision.current + 1;
    assignmentRequestRevision.current = requestRevision;
    setAssignmentResult(null);
    setAssignmentResultInput(null);
    setCheckingAssignment(true);
    setError("");

    try {
      const result = await preflightQmsAuditorAssignment(amoCode, {
        user_id: submitted.user_id,
        assignment_role: submitted.assignment_role,
        assignment_date: submitted.assignment_date,
        assignment_scope_key: submitted.assignment_scope_key,
        context_type: submitted.context_type || undefined,
        context_id: submitted.context_id || undefined,
        enforce_independence: true,
      });
      if (assignmentRequestRevision.current !== requestRevision) return;
      setAssignmentResultInput(submitted);
      setAssignmentResult(result);
    } catch (nextError) {
      if (assignmentRequestRevision.current !== requestRevision) return;
      setAssignmentResult(null);
      setAssignmentResultInput(null);
      setError(messageFromError(nextError));
    } finally {
      if (assignmentRequestRevision.current === requestRevision) setCheckingAssignment(false);
    }
  }

  async function submitIndependence(event: FormEvent) {
    event.preventDefault();
    if (!canManageAuditGovernance || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8) return;
    setDeclaring(true);
    setError("");
    try {
      await declareQmsIndependence(amoCode, {
        user_id: indUserId.trim(), context_type: indContextType, context_id: indContextId.trim(), declaration: indDeclaration,
        relationship_to_subject: indRelationship.trim() || undefined, rationale: indRationale.trim(),
      });
      setIndRationale("");
      setIndRelationship("");
      await load();
      setActionMode("NONE");
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setDeclaring(false);
    }
  }

  const selectedName = selectedSnapshot?.person.full_name || selected?.user_id || "No person selected";
  const readinessLabel = snapshotLoading ? "Checking authoritative gates…" : !selectedSnapshot ? "Readiness unavailable" : selectedSnapshot.eligible ? "Ready" : "Blocked";

  return (
    <main className="qms-people" aria-label="People and Privileges">
      <header className="qms-people__hero">
        <div><span>People & Privileges</span><h1>Quality authorization board</h1><p>See who is authorized, expiring, suspended or conflicted, then perform governed decisions in context. Training, Workforce and Rostering remain the authoritative sources for competence and availability.</p></div>
        <div className="qms-people__hero-actions"><button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>{canManagePrivileges ? <button type="button" className="is-primary" onClick={() => openAction("CREATE")}><Plus size={16} aria-hidden="true" /> New privilege</button> : null}</div>
      </header>
      {error ? <div className="qms-people__error" role="alert"><AlertTriangle size={18} aria-hidden="true" /> {error}</div> : null}
      <section className="qms-people__metrics" aria-label="Privilege exposure summary"><article><strong>{summary.active_privileges}</strong><span>Active privileges</span><small>Current internal Quality authorizations</small></article><article><strong>{summary.expiring_within_60_days}</strong><span>Expiring within 60 days</span><small>Review before authorization lapses</small></article><article><strong>{summary.suspended_privileges}</strong><span>Suspended</span><small>Unavailable for governed assignments</small></article><article className={summary.independence_exceptions ? "is-attention" : ""}><strong>{summary.independence_exceptions}</strong><span>Independence exceptions</span><small>Conflict or review states requiring attention</small></article></section>

      <section className="qms-people__workspace">
        <section className="qms-people__panel qms-people__register">
          <div className="qms-people__panel-head"><div><span>Authorization register</span><h2>People and current privileges</h2></div><div className="qms-people__filters"><label className="qms-people__search"><Search size={15} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search person, privilege or scope" /></label><label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}><option value="ALL">All</option><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option><option value="SUSPENDED">Suspended</option><option value="REVOKED">Revoked</option><option value="EXPIRED">Expired</option></select></label></div></div>
          <div className="qms-people__table-wrap"><table><thead><tr><th>Person</th><th>Privilege</th><th>Scope</th><th>Status</th><th>Expiry</th></tr></thead><tbody>{visiblePrivileges.length ? visiblePrivileges.map((item) => <tr key={item.id} className={item.id === selectedId ? "is-selected" : ""} onClick={() => setSelectedId(item.id)}><td><button type="button" className="qms-people__row-button" onClick={() => setSelectedId(item.id)}><strong>{shortIdentifier(item.user_id)}</strong><small>Authoritative user identifier</small></button></td><td><strong>{humanise(item.privilege_code)}</strong><small>{item.decisions?.length || 0} recorded decision(s)</small></td><td>{humanise(item.scope_key)}</td><td><span className={`qms-people__status qms-people__status--${item.status.toLowerCase()}`}>{humanise(item.status)}</span></td><td>{dateLabel(item.expires_on)}</td></tr>) : <tr><td colSpan={5}>{loading ? "Loading governed privileges…" : "No privileges match this view."}</td></tr>}</tbody></table></div>
        </section>

        <aside className="qms-people__detail" aria-label="Selected person and privilege">{selected ? <><div className="qms-people__detail-head"><span>Selected authorization</span><h2>{selectedName}</h2><p>{selectedSnapshot?.person.email || selected.user_id}</p><div className="qms-people__detail-badges"><span className={`qms-people__status qms-people__status--${selected.status.toLowerCase()}`}>{humanise(selected.status)}</span><span>{humanise(selected.privilege_code)}</span></div></div><dl className="qms-people__facts"><div><dt>Scope</dt><dd>{humanise(selected.scope_key)}</dd></div><div><dt>Effective</dt><dd>{dateLabel(selected.effective_from)}</dd></div><div><dt>Expiry</dt><dd>{dateLabel(selected.expires_on)}</dd></div><div><dt>Decision history</dt><dd>{selected.decisions?.length || 0} event(s)</dd></div></dl><section className="qms-people__eligibility-summary"><header><div><span>Current authorization readiness</span><h3>{readinessLabel}</h3></div>{selectedSnapshot?.eligible ? <CheckCircle2 size={20} /> : <ShieldCheck size={20} />}</header>{selectedSnapshot ? <><div className="qms-people__gate-grid">{Object.entries(selectedSnapshot.hard_gates).map(([gate, passed]) => <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>)}</div>{selectedSnapshot.training.missing.length ? <p>Missing verified/current training: {selectedSnapshot.training.missing.join(", ")}</p> : <p>Required training evidence is satisfied for this selected authorization.</p>}{selectedIsAuditorPrivilege ? <p>Audit assignment scope, role, date, capacity and independence are verified separately by the governed Planner assignment preflight.</p> : null}</> : <p>Authoritative readiness evidence is unavailable for this selected authorization.</p>}</section><div className="qms-people__detail-actions">{canRunAuditPreflight ? <button type="button" className="is-primary" onClick={() => openAction("AUDIT_ASSIGNMENT")}><CheckCircle2 size={16} /> Check audit assignment</button> : null}{canManagePrivileges ? <button type="button" onClick={() => openAction("DECISION")}><ShieldCheck size={16} /> Change privilege</button> : null}{canManageAuditGovernance ? <button type="button" onClick={() => openAction("INDEPENDENCE")}><UserRoundCheck size={16} /> Independence</button> : null}</div><section className="qms-people__history"><header><span>Decision history</span><h3>Immutable authorization record</h3></header>{selected.decisions?.length ? selected.decisions.slice().reverse().map((decision) => <article key={decision.id}><div><strong>{humanise(decision.decision_type)}</strong><span>{humanise(decision.resulting_status)}</span></div><p>{decision.rationale}</p><small>{new Date(decision.decided_at).toLocaleString()}</small></article>) : <p className="qms-people__empty">No authorization decision has been recorded yet.</p>}</section></> : <div className="qms-people__placeholder"><UserRoundCheck size={30} /><strong>Select a person or privilege</strong><p>The selected authorization, readiness posture and governed actions will appear here.</p></div>}</aside>
      </section>

      {actionMode !== "NONE" ? <div className="qms-people__drawer-layer" role="dialog" aria-modal="true" aria-label="People and privileges governed action"><section className="qms-people__drawer"><header><div><span>Governed action</span><h2>{actionMode === "CREATE" ? "Create privilege draft" : actionMode === "DECISION" ? "Record privilege decision" : actionMode === "AUDIT_ASSIGNMENT" ? "Check governed audit assignment" : "Declare independence state"}</h2></div><button type="button" className="qms-people__icon-button" onClick={closeAction} aria-label="Close action"><X size={18} /></button></header>
        {actionMode === "CREATE" && canManagePrivileges ? <form onSubmit={submitDraft} className="qms-people__form"><label>Person identifier<span>Use the authoritative Workforce user identifier.</span><input value={userId} onChange={(event) => setUserId(event.target.value)} required placeholder="User ID" /></label><label>Privilege rule<select value={ruleId} onChange={(event) => setRuleId(event.target.value)} required>{rules.map((rule) => <option key={rule.id} value={rule.id}>{rule.title} · {rule.privilege_code}</option>)}</select></label><label>Scope<input value={scopeKey} onChange={(event) => setScopeKey(event.target.value)} placeholder="GLOBAL" /></label><footer><button type="button" onClick={closeAction}>Cancel</button><button type="submit" className="is-primary" disabled={creating || !ruleId || !userId.trim()}>{creating ? "Creating…" : "Create governed draft"}</button></footer></form> : null}
        {actionMode === "DECISION" && selected && canManagePrivileges ? <form onSubmit={submitDecision} className="qms-people__form"><div className="qms-people__context-card"><strong>{selectedName}</strong><span>{humanise(selected.privilege_code)} · {humanise(selected.scope_key)}</span></div><label>Decision<select value={decisionType} onChange={(event) => setDecisionType(event.target.value as QmsPrivilegeDecision["decision_type"])}><option value="GRANT">Grant</option><option value="RENEW">Renew</option><option value="SUSPEND">Suspend</option><option value="REINSTATE">Reinstate</option><option value="REVOKE">Revoke</option><option value="EXPIRE">Expire</option><option value="REJECT">Reject</option></select></label><div className="qms-people__dates"><label>Effective<input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label>Expiry<input type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} /></label></div><label>Decision rationale<textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} minLength={8} rows={5} required placeholder="Record the evidence-backed reason for this decision." /></label><footer><button type="button" onClick={closeAction}>Cancel</button><button type="submit" className="is-primary" disabled={deciding || decisionReason.trim().length < 8}>{deciding ? "Recording…" : "Record immutable decision"}</button></footer></form> : null}
        {actionMode === "AUDIT_ASSIGNMENT" && selected && selectedRule && canRunAuditPreflight ? <form onSubmit={submitAuditAssignment} className="qms-people__form"><div className="qms-people__context-card"><strong>{selectedName}</strong><span>{humanise(selected.privilege_code)} · selected authorization {humanise(selected.scope_key)}</span></div><label>Assignment role<select value={assignmentRole} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentRole(event.target.value as QmsAuditorAssignmentRole); }}>{selectedRule.privilege_type === "LEAD_AUDITOR" ? <option value="LEAD_AUDITOR">Lead auditor</option> : <><option value="OBSERVER_AUDITOR">Observer auditor</option><option value="ASSISTANT_AUDITOR">Assistant auditor</option></>}</select></label><label>Assignment date<input type="date" value={assignmentDate} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentDate(event.target.value); }} required /></label><label>Assignment scope code<span>Enter the actual audit/programme scope being assigned; this is checked against the selected privilege scope.</span><input value={assignmentScopeKey} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentScopeKey(event.target.value); }} required placeholder="e.g. LINE_MAINTENANCE" /></label><label>Assignment context<select value={assignmentContextType} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentContextType(event.target.value as AssignmentContextType); }} required={assignmentContextRequired}><option value="">{assignmentContextRequired ? "Select governed context" : "No context required"}</option><option value="AUDIT">Audit</option><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option><option value="OTHER">Other</option></select></label><label>Context ID<span>{assignmentContextRequired ? "Required so independence is verified against this assignment." : "Optional governed assignment record."}</span><input value={assignmentContextId} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentContextId(event.target.value); }} required={assignmentContextRequired} placeholder={assignmentContextRequired ? "Required governed record ID" : "Optional governed record ID"} /></label>{assignmentResultAppliesToSelection && assignmentResult && assignmentResultInput ? <div className={`qms-people__eligibility ${assignmentEligible ? "is-eligible" : "is-blocked"}`}><strong>{assignmentEligible ? "Eligible for this assignment" : "Blocked for this assignment"}</strong><span>{humanise(assignmentResultInput.assignment_role)} · {assignmentResultInput.assignment_date} · {humanise(assignmentResultInput.assignment_scope_key)}</span>{assignmentResultInput.context_type ? <p>Checked context: {humanise(assignmentResultInput.context_type)} · {assignmentResultInput.context_id || "No context identifier"}</p> : null}{assignmentAssessment ? <div className="qms-people__gate-grid">{Object.entries(assignmentAssessment.hard_gates).map(([gate, passed]) => <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>)}</div> : null}{!assignmentUsesSelectedPrivilege ? <p>The governed assignment guard did not use this selected authorization. Choose the authorization whose scope is actually being relied on.</p> : null}{assignmentResult.reason ? <p>{assignmentResult.reason}</p> : null}{assignmentAssessment?.independence.message ? <p>{assignmentAssessment.independence.message}</p> : null}</div> : null}<footer><button type="button" onClick={closeAction}>Close</button><button type="submit" className="is-primary" disabled={checkingAssignment || !assignmentInputComplete}>{checkingAssignment ? "Checking…" : "Run governed assignment preflight"}</button></footer></form> : null}
        {actionMode === "INDEPENDENCE" && canManageAuditGovernance ? <form onSubmit={submitIndependence} className="qms-people__form"><label>Person identifier<input value={indUserId} onChange={(event) => setIndUserId(event.target.value)} required /></label><label>Context<select value={indContextType} onChange={(event) => setIndContextType(event.target.value as typeof indContextType)}><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="AUDIT">Audit</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option><option value="OTHER">Other</option></select></label><label>Context ID<input value={indContextId} onChange={(event) => setIndContextId(event.target.value)} required /></label><label>Declaration<select value={indDeclaration} onChange={(event) => setIndDeclaration(event.target.value as typeof indDeclaration)}><option value="INDEPENDENT">Independent</option><option value="REQUIRES_REVIEW">Requires review</option><option value="CONFLICT">Conflict</option></select></label><label>Relationship to subject<input value={indRelationship} onChange={(event) => setIndRelationship(event.target.value)} /></label><label>Rationale<textarea value={indRationale} onChange={(event) => setIndRationale(event.target.value)} minLength={8} rows={5} required /></label><footer><button type="button" onClick={closeAction}>Cancel</button><button type="submit" className="is-primary" disabled={declaring || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8}>{declaring ? "Recording…" : "Record immutable declaration"}</button></footer></form> : null}
      </section></div> : null}
    </main>
  );
};

export default QmsPeoplePage;
