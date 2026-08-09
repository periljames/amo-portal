import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  UserRoundCheck,
  X,
} from "lucide-react";

import {
  createQmsPrivilege,
  decideQmsPrivilege,
  declareQmsIndependence,
  getQmsEligibility,
  getQmsPeopleSummary,
  listQmsPrivilegeRules,
  listQmsPrivileges,
  type QmsEligibility,
  type QmsPeopleSummary,
  type QmsPrivilege,
  type QmsPrivilegeDecision,
  type QmsPrivilegeRule,
} from "../../services/qmsPeople";
import "../../styles/qms-people.css";

type Props = { amoCode: string };
type ActionMode = "NONE" | "CREATE" | "DECISION" | "ELIGIBILITY" | "INDEPENDENCE";

const EMPTY_SUMMARY: QmsPeopleSummary = {
  active_privileges: 0,
  expiring_within_60_days: 0,
  suspended_privileges: 0,
  independence_exceptions: 0,
};

function messageFromError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "The People & Privileges operation could not be completed.";
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

function shortIdentifier(value: string): string {
  if (value.length <= 24) return value;
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
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

  const [eligibility, setEligibility] = useState<QmsEligibility | null>(null);
  const [eligibilityUserId, setEligibilityUserId] = useState("");
  const [eligibilityRule, setEligibilityRule] = useState("");
  const [eligibilityContextType, setEligibilityContextType] = useState("");
  const [eligibilityContextId, setEligibilityContextId] = useState("");
  const [checking, setChecking] = useState(false);

  const [selectedSnapshot, setSelectedSnapshot] = useState<QmsEligibility | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

  const [indUserId, setIndUserId] = useState("");
  const [indContextType, setIndContextType] = useState<"AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER">("AUDIT_SCHEDULE");
  const [indContextId, setIndContextId] = useState("");
  const [indDeclaration, setIndDeclaration] = useState<"INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW">("INDEPENDENT");
  const [indRelationship, setIndRelationship] = useState("");
  const [indRationale, setIndRationale] = useState("");
  const [declaring, setDeclaring] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const [nextSummary, ruleResponse, privilegeResponse] = await Promise.all([
        getQmsPeopleSummary(amoCode, signal),
        listQmsPrivilegeRules(amoCode, signal),
        listQmsPrivileges(amoCode, {}, signal),
      ]);
      setSummary(nextSummary);
      setRules(ruleResponse.items);
      setPrivileges(privilegeResponse.items);
      setRuleId((value) => value || ruleResponse.items[0]?.id || "");
      setEligibilityRule((value) => value || ruleResponse.items[0]?.privilege_code || "");
      setSelectedId((value) => value && privilegeResponse.items.some((item) => item.id === value)
        ? value
        : privilegeResponse.items[0]?.id || "");
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError")) setError(messageFromError(nextError));
    } finally {
      setLoading(false);
    }
  }, [amoCode]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const selected = privileges.find((item) => item.id === selectedId) || null;

  useEffect(() => {
    if (!selected) {
      setSelectedSnapshot(null);
      return;
    }
    const controller = new AbortController();
    setSnapshotLoading(true);
    setSelectedSnapshot(null);
    void getQmsEligibility(amoCode, {
      userId: selected.user_id,
      privilegeCode: selected.privilege_code,
    }, controller.signal)
      .then((snapshot) => setSelectedSnapshot(snapshot))
      .catch((nextError) => {
        if (!(nextError instanceof DOMException && nextError.name === "AbortError")) setSelectedSnapshot(null);
      })
      .finally(() => setSnapshotLoading(false));
    return () => controller.abort();
  }, [amoCode, selected?.privilege_code, selected?.user_id]);

  const visiblePrivileges = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return privileges.filter((item) => {
      if (statusFilter !== "ALL" && item.status !== statusFilter) return false;
      if (!needle) return true;
      return [item.user_id, item.privilege_code, item.scope_key]
        .some((value) => value.toLowerCase().includes(needle));
    });
  }, [privileges, search, statusFilter]);

  function openAction(mode: ActionMode) {
    setError("");
    setEligibility(null);
    if (selected) {
      if (mode === "ELIGIBILITY") {
        setEligibilityUserId(selected.user_id);
        setEligibilityRule(selected.privilege_code);
      }
      if (mode === "INDEPENDENCE") setIndUserId(selected.user_id);
    }
    setActionMode(mode);
  }

  async function submitDraft(event: FormEvent) {
    event.preventDefault();
    if (!ruleId || !userId.trim()) return;
    setCreating(true);
    setError("");
    try {
      const created = await createQmsPrivilege(amoCode, {
        rule_id: ruleId,
        user_id: userId.trim(),
        scope_key: scopeKey.trim() || "GLOBAL",
      });
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
    if (!selected || decisionReason.trim().length < 8) return;
    setDeciding(true);
    setError("");
    try {
      await decideQmsPrivilege(amoCode, selected.id, {
        decision_type: decisionType,
        rationale: decisionReason.trim(),
        effective_from: effectiveFrom || undefined,
        expires_on: expiresOn || undefined,
      });
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

  async function submitEligibility(event: FormEvent) {
    event.preventDefault();
    if (!eligibilityUserId.trim() || !eligibilityRule) return;
    setChecking(true);
    setError("");
    try {
      setEligibility(await getQmsEligibility(amoCode, {
        userId: eligibilityUserId.trim(),
        privilegeCode: eligibilityRule,
        contextType: eligibilityContextType || undefined,
        contextId: eligibilityContextId.trim() || undefined,
      }));
    } catch (nextError) {
      setEligibility(null);
      setError(messageFromError(nextError));
    } finally {
      setChecking(false);
    }
  }

  async function submitIndependence(event: FormEvent) {
    event.preventDefault();
    if (!indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8) return;
    setDeclaring(true);
    setError("");
    try {
      await declareQmsIndependence(amoCode, {
        user_id: indUserId.trim(),
        context_type: indContextType,
        context_id: indContextId.trim(),
        declaration: indDeclaration,
        relationship_to_subject: indRelationship.trim() || undefined,
        rationale: indRationale.trim(),
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

  return (
    <main className="qms-people" aria-label="People and Privileges">
      <header className="qms-people__hero">
        <div>
          <span>People & Privileges</span>
          <h1>Quality authorization board</h1>
          <p>See who is authorized, expiring, suspended or conflicted, then perform governed decisions in context. Training, Workforce and Rostering remain the authoritative sources for competence and availability.</p>
        </div>
        <div className="qms-people__hero-actions">
          <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
          <button type="button" className="is-primary" onClick={() => openAction("CREATE")}><Plus size={16} aria-hidden="true" /> New privilege</button>
        </div>
      </header>

      {error ? <div className="qms-people__error" role="alert"><AlertTriangle size={18} aria-hidden="true" /> {error}</div> : null}

      <section className="qms-people__metrics" aria-label="Privilege exposure summary">
        <article><strong>{summary.active_privileges}</strong><span>Active privileges</span><small>Current internal Quality authorizations</small></article>
        <article><strong>{summary.expiring_within_60_days}</strong><span>Expiring within 60 days</span><small>Review before authorization lapses</small></article>
        <article><strong>{summary.suspended_privileges}</strong><span>Suspended</span><small>Unavailable for governed assignments</small></article>
        <article className={summary.independence_exceptions ? "is-attention" : ""}><strong>{summary.independence_exceptions}</strong><span>Independence exceptions</span><small>Conflict or review states requiring attention</small></article>
      </section>

      <section className="qms-people__workspace">
        <section className="qms-people__panel qms-people__register">
          <div className="qms-people__panel-head">
            <div><span>Authorization register</span><h2>People and current privileges</h2></div>
            <div className="qms-people__filters">
              <label className="qms-people__search"><Search size={15} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search person, privilege or scope" /></label>
              <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}><option value="ALL">All</option><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option><option value="SUSPENDED">Suspended</option><option value="REVOKED">Revoked</option><option value="EXPIRED">Expired</option></select></label>
            </div>
          </div>
          <div className="qms-people__table-wrap">
            <table>
              <thead><tr><th>Person</th><th>Privilege</th><th>Scope</th><th>Status</th><th>Expiry</th></tr></thead>
              <tbody>
                {visiblePrivileges.length ? visiblePrivileges.map((item) => (
                  <tr key={item.id} className={item.id === selectedId ? "is-selected" : ""} onClick={() => setSelectedId(item.id)}>
                    <td><button type="button" className="qms-people__row-button" onClick={() => setSelectedId(item.id)}><strong>{shortIdentifier(item.user_id)}</strong><small>Authoritative user identifier</small></button></td>
                    <td><strong>{humanise(item.privilege_code)}</strong><small>{item.decisions?.length || 0} recorded decision(s)</small></td>
                    <td>{humanise(item.scope_key)}</td>
                    <td><span className={`qms-people__status qms-people__status--${item.status.toLowerCase()}`}>{humanise(item.status)}</span></td>
                    <td>{dateLabel(item.expires_on)}</td>
                  </tr>
                )) : <tr><td colSpan={5}>{loading ? "Loading governed privileges…" : "No privileges match this view."}</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="qms-people__detail" aria-label="Selected person and privilege">
          {selected ? (
            <>
              <div className="qms-people__detail-head">
                <span>Selected authorization</span>
                <h2>{selectedName}</h2>
                <p>{selectedSnapshot?.person.email || selected.user_id}</p>
                <div className="qms-people__detail-badges"><span className={`qms-people__status qms-people__status--${selected.status.toLowerCase()}`}>{humanise(selected.status)}</span><span>{humanise(selected.privilege_code)}</span></div>
              </div>

              <dl className="qms-people__facts">
                <div><dt>Scope</dt><dd>{humanise(selected.scope_key)}</dd></div>
                <div><dt>Effective</dt><dd>{dateLabel(selected.effective_from)}</dd></div>
                <div><dt>Expiry</dt><dd>{dateLabel(selected.expires_on)}</dd></div>
                <div><dt>Decision history</dt><dd>{selected.decisions?.length || 0} event(s)</dd></div>
              </dl>

              <section className="qms-people__eligibility-summary">
                <header><div><span>Current eligibility posture</span><h3>{snapshotLoading ? "Checking authoritative gates…" : selectedSnapshot ? (selectedSnapshot.eligible ? "Eligible" : "Blocked") : "Eligibility unavailable"}</h3></div>{selectedSnapshot?.eligible ? <CheckCircle2 size={20} /> : <ShieldCheck size={20} />}</header>
                {selectedSnapshot ? (
                  <>
                    <div className="qms-people__gate-grid">{Object.entries(selectedSnapshot.hard_gates).map(([gate, passed]) => <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>)}</div>
                    {selectedSnapshot.training.missing.length ? <p>Missing verified/current training: {selectedSnapshot.training.missing.join(", ")}</p> : <p>Required training evidence is satisfied for this privilege check.</p>}
                  </>
                ) : <p>Select a governed action to perform a task-specific eligibility check.</p>}
              </section>

              <div className="qms-people__detail-actions">
                <button type="button" className="is-primary" onClick={() => openAction("ELIGIBILITY")}><CheckCircle2 size={16} /> Check assignment</button>
                <button type="button" onClick={() => openAction("DECISION")}><ShieldCheck size={16} /> Change privilege</button>
                <button type="button" onClick={() => openAction("INDEPENDENCE")}><UserRoundCheck size={16} /> Independence</button>
              </div>

              <section className="qms-people__history">
                <header><span>Decision history</span><h3>Immutable authorization record</h3></header>
                {selected.decisions?.length ? selected.decisions.slice().reverse().map((decision) => (
                  <article key={decision.id}><div><strong>{humanise(decision.decision_type)}</strong><span>{humanise(decision.resulting_status)}</span></div><p>{decision.rationale}</p><small>{new Date(decision.decided_at).toLocaleString()}</small></article>
                )) : <p className="qms-people__empty">No authorization decision has been recorded yet.</p>}
              </section>
            </>
          ) : (
            <div className="qms-people__placeholder"><UserRoundCheck size={30} /><strong>Select a person or privilege</strong><p>The selected authorization, eligibility posture and governed actions will appear here.</p></div>
          )}
        </aside>
      </section>

      {actionMode !== "NONE" ? (
        <div className="qms-people__drawer-layer" role="dialog" aria-modal="true" aria-label="People and privileges governed action">
          <section className="qms-people__drawer">
            <header>
              <div><span>Governed action</span><h2>{actionMode === "CREATE" ? "Create privilege draft" : actionMode === "DECISION" ? "Record privilege decision" : actionMode === "ELIGIBILITY" ? "Check task eligibility" : "Declare independence state"}</h2></div>
              <button type="button" className="qms-people__icon-button" onClick={() => setActionMode("NONE")} aria-label="Close action"><X size={18} /></button>
            </header>

            {actionMode === "CREATE" ? (
              <form onSubmit={submitDraft} className="qms-people__form">
                <label>Person identifier<span>Use the authoritative Workforce user identifier.</span><input value={userId} onChange={(event) => setUserId(event.target.value)} required placeholder="User ID" /></label>
                <label>Privilege rule<select value={ruleId} onChange={(event) => setRuleId(event.target.value)} required>{rules.map((rule) => <option key={rule.id} value={rule.id}>{rule.title} · {rule.privilege_code}</option>)}</select></label>
                <label>Scope<input value={scopeKey} onChange={(event) => setScopeKey(event.target.value)} placeholder="GLOBAL" /></label>
                <footer><button type="button" onClick={() => setActionMode("NONE")}>Cancel</button><button type="submit" className="is-primary" disabled={creating || !ruleId || !userId.trim()}>{creating ? "Creating…" : "Create governed draft"}</button></footer>
              </form>
            ) : null}

            {actionMode === "DECISION" && selected ? (
              <form onSubmit={submitDecision} className="qms-people__form">
                <div className="qms-people__context-card"><strong>{selectedName}</strong><span>{humanise(selected.privilege_code)} · {humanise(selected.scope_key)}</span></div>
                <label>Decision<select value={decisionType} onChange={(event) => setDecisionType(event.target.value as QmsPrivilegeDecision["decision_type"])}><option value="GRANT">Grant</option><option value="RENEW">Renew</option><option value="SUSPEND">Suspend</option><option value="REINSTATE">Reinstate</option><option value="REVOKE">Revoke</option><option value="EXPIRE">Expire</option><option value="REJECT">Reject</option></select></label>
                <div className="qms-people__dates"><label>Effective<input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label>Expiry<input type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} /></label></div>
                <label>Decision rationale<textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} minLength={8} rows={5} required placeholder="Record the evidence-backed reason for this decision." /></label>
                <footer><button type="button" onClick={() => setActionMode("NONE")}>Cancel</button><button type="submit" className="is-primary" disabled={deciding || decisionReason.trim().length < 8}>{deciding ? "Recording…" : "Record immutable decision"}</button></footer>
              </form>
            ) : null}

            {actionMode === "ELIGIBILITY" ? (
              <form onSubmit={submitEligibility} className="qms-people__form">
                <label>Person identifier<input value={eligibilityUserId} onChange={(event) => setEligibilityUserId(event.target.value)} required /></label>
                <label>Privilege<select value={eligibilityRule} onChange={(event) => setEligibilityRule(event.target.value)} required>{rules.map((rule) => <option key={rule.id} value={rule.privilege_code}>{rule.title}</option>)}</select></label>
                <label>Assignment context<select value={eligibilityContextType} onChange={(event) => setEligibilityContextType(event.target.value)}><option value="">No assignment context</option><option value="AUDIT">Audit</option><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option></select></label>
                <label>Context ID<input value={eligibilityContextId} onChange={(event) => setEligibilityContextId(event.target.value)} placeholder="Optional governed record ID" /></label>
                {eligibility ? <div className={`qms-people__eligibility ${eligibility.eligible ? "is-eligible" : "is-blocked"}`}><strong>{eligibility.eligible ? "Eligible" : "Blocked"}</strong><span>{eligibility.person.full_name || eligibility.person.user_id}</span><div className="qms-people__gate-grid">{Object.entries(eligibility.hard_gates).map(([gate, passed]) => <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>)}</div>{eligibility.training.missing.length ? <p>Missing verified/current training: {eligibility.training.missing.join(", ")}</p> : null}</div> : null}
                <footer><button type="button" onClick={() => setActionMode("NONE")}>Close</button><button type="submit" className="is-primary" disabled={checking || !eligibilityUserId.trim() || !eligibilityRule}>{checking ? "Checking…" : "Evaluate authoritative gates"}</button></footer>
              </form>
            ) : null}

            {actionMode === "INDEPENDENCE" ? (
              <form onSubmit={submitIndependence} className="qms-people__form">
                <label>Person identifier<input value={indUserId} onChange={(event) => setIndUserId(event.target.value)} required /></label>
                <label>Context<select value={indContextType} onChange={(event) => setIndContextType(event.target.value as typeof indContextType)}><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="AUDIT">Audit</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option><option value="OTHER">Other</option></select></label>
                <label>Context ID<input value={indContextId} onChange={(event) => setIndContextId(event.target.value)} required /></label>
                <label>Declaration<select value={indDeclaration} onChange={(event) => setIndDeclaration(event.target.value as typeof indDeclaration)}><option value="INDEPENDENT">Independent</option><option value="REQUIRES_REVIEW">Requires review</option><option value="CONFLICT">Conflict</option></select></label>
                <label>Relationship to subject<input value={indRelationship} onChange={(event) => setIndRelationship(event.target.value)} /></label>
                <label>Rationale<textarea value={indRationale} onChange={(event) => setIndRationale(event.target.value)} minLength={8} rows={5} required /></label>
                <footer><button type="button" onClick={() => setActionMode("NONE")}>Cancel</button><button type="submit" className="is-primary" disabled={declaring || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8}>{declaring ? "Recording…" : "Record immutable declaration"}</button></footer>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
};

export default QmsPeoplePage;
