import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck, UserRoundCheck } from "lucide-react";

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

const QmsPeoplePage: React.FC<Props> = ({ amoCode }) => {
  const [summary, setSummary] = useState<QmsPeopleSummary>(EMPTY_SUMMARY);
  const [rules, setRules] = useState<QmsPrivilegeRule[]>([]);
  const [privileges, setPrivileges] = useState<QmsPrivilege[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<QmsPrivilege["status"] | "ALL">("ALL");

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

  const visiblePrivileges = useMemo(
    () => statusFilter === "ALL" ? privileges : privileges.filter((item) => item.status === statusFilter),
    [privileges, statusFilter],
  );
  const selected = privileges.find((item) => item.id === selectedId) || null;

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
      setSelectedId(created.id);
      setUserId("");
      setScopeKey("GLOBAL");
      await load();
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
      await load();
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
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setDeclaring(false);
    }
  }

  return (
    <main className="qms-people" aria-label="People and Privileges">
      <header className="qms-people__hero">
        <div>
          <span>People & Privileges</span>
          <h1>Authorization board</h1>
          <p>Quality decisions are governed here. Training, Workforce and Rostering remain the authoritative sources for competence and availability.</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
      </header>

      {error ? <div className="qms-people__error" role="alert"><AlertTriangle size={17} aria-hidden="true" /> {error}</div> : null}

      <section className="qms-people__metrics" aria-label="Privilege exposure summary">
        <article><strong>{summary.active_privileges}</strong><span>Active privileges</span></article>
        <article><strong>{summary.expiring_within_60_days}</strong><span>Expire within 60 days</span></article>
        <article><strong>{summary.suspended_privileges}</strong><span>Suspended</span></article>
        <article><strong>{summary.independence_exceptions}</strong><span>Independence exceptions</span></article>
      </section>

      <section className="qms-people__panel">
        <div className="qms-people__panel-head">
          <div><span>Governed register</span><h2>Current internal privileges</h2></div>
          <label>Status <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}><option value="ALL">All</option><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option><option value="SUSPENDED">Suspended</option><option value="REVOKED">Revoked</option><option value="EXPIRED">Expired</option></select></label>
        </div>
        <div className="qms-people__table-wrap">
          <table>
            <thead><tr><th>Person</th><th>Privilege</th><th>Scope</th><th>Status</th><th>Effective</th><th>Expiry</th><th>History</th></tr></thead>
            <tbody>
              {visiblePrivileges.length ? visiblePrivileges.map((item) => (
                <tr key={item.id} className={item.id === selectedId ? "is-selected" : ""} onClick={() => setSelectedId(item.id)}>
                  <td><button type="button" className="qms-people__row-button" onClick={() => setSelectedId(item.id)}>{item.user_id}</button></td>
                  <td>{item.privilege_code}</td><td>{item.scope_key}</td><td><span className={`qms-people__status qms-people__status--${item.status.toLowerCase()}`}>{item.status}</span></td>
                  <td>{item.effective_from || "—"}</td><td>{item.expires_on || "—"}</td><td>{item.decisions?.length || 0}</td>
                </tr>
              )) : <tr><td colSpan={7}>{loading ? "Loading governed privileges…" : "No privileges match this view."}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="qms-people__grid">
        <section className="qms-people__panel">
          <div className="qms-people__panel-head"><div><span>Authorization</span><h2>Create privilege draft</h2></div><UserRoundCheck size={20} aria-hidden="true" /></div>
          <form onSubmit={submitDraft} className="qms-people__form">
            <label htmlFor="people-user-id">Person user ID</label><input id="people-user-id" value={userId} onChange={(event) => setUserId(event.target.value)} required />
            <label htmlFor="people-rule">Privilege rule</label><select id="people-rule" value={ruleId} onChange={(event) => setRuleId(event.target.value)} required>{rules.map((rule) => <option key={rule.id} value={rule.id}>{rule.title} · {rule.privilege_code}</option>)}</select>
            <label htmlFor="people-scope">Scope key</label><input id="people-scope" value={scopeKey} onChange={(event) => setScopeKey(event.target.value)} />
            <button type="submit" disabled={creating || !ruleId || !userId.trim()}>{creating ? "Creating…" : "Create governed draft"}</button>
          </form>
        </section>

        <section className="qms-people__panel">
          <div className="qms-people__panel-head"><div><span>Immutable decision</span><h2>{selected ? selected.privilege_code : "Select a privilege"}</h2></div><ShieldCheck size={20} aria-hidden="true" /></div>
          <form onSubmit={submitDecision} className="qms-people__form">
            <label htmlFor="people-decision">Decision</label><select id="people-decision" value={decisionType} onChange={(event) => setDecisionType(event.target.value as QmsPrivilegeDecision["decision_type"])} disabled={!selected}><option value="GRANT">Grant</option><option value="RENEW">Renew</option><option value="SUSPEND">Suspend</option><option value="REINSTATE">Reinstate</option><option value="REVOKE">Revoke</option><option value="EXPIRE">Expire</option><option value="REJECT">Reject</option></select>
            <div className="qms-people__dates"><label htmlFor="people-effective">Effective<input id="people-effective" type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} disabled={!selected} /></label><label htmlFor="people-expiry">Expiry<input id="people-expiry" type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} disabled={!selected} /></label></div>
            <label htmlFor="people-rationale">Decision rationale</label><textarea id="people-rationale" value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} minLength={8} rows={4} disabled={!selected} required />
            <button type="submit" disabled={!selected || deciding || decisionReason.trim().length < 8}>{deciding ? "Recording…" : "Record immutable decision"}</button>
          </form>
        </section>
      </div>

      <div className="qms-people__grid">
        <section className="qms-people__panel">
          <div className="qms-people__panel-head"><div><span>Hard gates</span><h2>Check task eligibility</h2></div><CheckCircle2 size={20} aria-hidden="true" /></div>
          <form onSubmit={submitEligibility} className="qms-people__form">
            <label htmlFor="eligibility-user">Person user ID</label><input id="eligibility-user" value={eligibilityUserId} onChange={(event) => setEligibilityUserId(event.target.value)} required />
            <label htmlFor="eligibility-rule">Privilege</label><select id="eligibility-rule" value={eligibilityRule} onChange={(event) => setEligibilityRule(event.target.value)} required>{rules.map((rule) => <option key={rule.id} value={rule.privilege_code}>{rule.title}</option>)}</select>
            <label htmlFor="eligibility-context-type">Assignment context</label><select id="eligibility-context-type" value={eligibilityContextType} onChange={(event) => setEligibilityContextType(event.target.value)}><option value="">No assignment context</option><option value="AUDIT">Audit</option><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option></select>
            <label htmlFor="eligibility-context-id">Context ID</label><input id="eligibility-context-id" value={eligibilityContextId} onChange={(event) => setEligibilityContextId(event.target.value)} />
            <button type="submit" disabled={checking || !eligibilityUserId.trim() || !eligibilityRule}>{checking ? "Checking…" : "Evaluate authoritative gates"}</button>
          </form>
          {eligibility ? <div className={`qms-people__eligibility ${eligibility.eligible ? "is-eligible" : "is-blocked"}`}><strong>{eligibility.eligible ? "Eligible" : "Blocked"}</strong><span>{eligibility.person.full_name || eligibility.person.user_id}</span><ul>{Object.entries(eligibility.hard_gates).map(([gate, passed]) => <li key={gate}>{passed ? "PASS" : "BLOCK"} · {gate.replaceAll("_", " ")}</li>)}</ul>{eligibility.training.missing.length ? <p>Missing verified/current training: {eligibility.training.missing.join(", ")}</p> : null}</div> : null}
        </section>

        <section className="qms-people__panel">
          <div className="qms-people__panel-head"><div><span>Independence</span><h2>Declare assignment conflict state</h2></div><ShieldCheck size={20} aria-hidden="true" /></div>
          <form onSubmit={submitIndependence} className="qms-people__form">
            <label htmlFor="ind-user">Person user ID</label><input id="ind-user" value={indUserId} onChange={(event) => setIndUserId(event.target.value)} required />
            <label htmlFor="ind-context">Context</label><select id="ind-context" value={indContextType} onChange={(event) => setIndContextType(event.target.value as typeof indContextType)}><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="AUDIT">Audit</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option><option value="OTHER">Other</option></select>
            <label htmlFor="ind-context-id">Context ID</label><input id="ind-context-id" value={indContextId} onChange={(event) => setIndContextId(event.target.value)} required />
            <label htmlFor="ind-declaration">Declaration</label><select id="ind-declaration" value={indDeclaration} onChange={(event) => setIndDeclaration(event.target.value as typeof indDeclaration)}><option value="INDEPENDENT">Independent</option><option value="REQUIRES_REVIEW">Requires review</option><option value="CONFLICT">Conflict</option></select>
            <label htmlFor="ind-relationship">Relationship to subject</label><input id="ind-relationship" value={indRelationship} onChange={(event) => setIndRelationship(event.target.value)} />
            <label htmlFor="ind-rationale">Rationale</label><textarea id="ind-rationale" value={indRationale} onChange={(event) => setIndRationale(event.target.value)} minLength={8} rows={4} required />
            <button type="submit" disabled={declaring || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8}>{declaring ? "Recording…" : "Record immutable declaration"}</button>
          </form>
        </section>
      </div>
    </main>
  );
};

export default QmsPeoplePage;
