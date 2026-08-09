import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, Network, RefreshCw, ScanSearch, ShieldCheck } from "lucide-react";

import {
  configureQmsSignalDefaults,
  evaluateQmsSignals,
  getQmsApprovalGraph,
  getQmsApprovalTwin,
  getQmsAuditRiskPlanningContext,
  getQmsIntelligenceOverview,
  listQmsSignalRules,
  listQmsSignals,
  type QmsApprovalTwin,
  type QmsIntelligenceOverview,
  type QmsRequirementNode,
  type QmsRiskPlanningContext,
  type QmsSignalObservation,
  type QmsSignalRule,
} from "../../services/qmsIntelligence";
import "../../styles/qms-intelligence.css";

type Props = { amoCode: string };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Quality Intelligence could not be loaded.";
}

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

const QmsIntelligencePage: React.FC<Props> = ({ amoCode }) => {
  const [overview, setOverview] = useState<QmsIntelligenceOverview | null>(null);
  const [riskContext, setRiskContext] = useState<QmsRiskPlanningContext | null>(null);
  const [rules, setRules] = useState<QmsSignalRule[]>([]);
  const [signals, setSignals] = useState<QmsSignalObservation[]>([]);
  const [twin, setTwin] = useState<QmsApprovalTwin | null>(null);
  const [nodes, setNodes] = useState<QmsRequirementNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextRiskContext, ruleResponse, signalResponse, nextTwin, graph] = await Promise.all([
        getQmsIntelligenceOverview(amoCode, signal),
        getQmsAuditRiskPlanningContext(amoCode, signal),
        listQmsSignalRules(amoCode, signal),
        listQmsSignals(amoCode, signal),
        getQmsApprovalTwin(amoCode, signal),
        getQmsApprovalGraph(amoCode, signal),
      ]);
      setOverview(nextOverview);
      setRiskContext(nextRiskContext);
      setRules(ruleResponse.items);
      setSignals(signalResponse.items);
      setTwin(nextTwin);
      setNodes(graph.nodes);
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError")) setError(errorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }, [amoCode]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const graphState = useMemo(() => {
    const counts: Record<string, number> = {};
    nodes.forEach((node) => { counts[node.support_state] = (counts[node.support_state] || 0) + 1; });
    return counts;
  }, [nodes]);

  async function configureAndEvaluate() {
    setBusy(true);
    setError("");
    try {
      await configureQmsSignalDefaults(amoCode);
      await evaluateQmsSignals(amoCode);
      await load();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="qms-intelligence" aria-label="Quality Intelligence workspace">
      <header className="qms-intelligence__hero">
        <div>
          <span>Intelligence</span>
          <h1>Assurance signals & approval impact</h1>
          <p>Transparent calculations, source-backed surveillance factors and an evidence-support digital twin. No predictive compliance score is generated.</p>
        </div>
        <div className="qms-intelligence__actions">
          <button type="button" onClick={() => void configureAndEvaluate()} disabled={busy}>{busy ? "Evaluating…" : "Configure & evaluate signals"}</button>
          <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
        </div>
      </header>

      {error ? <div className="qms-intelligence__error" role="alert"><AlertTriangle size={17} aria-hidden="true" /> {error}</div> : null}
      {riskContext?.source_warnings.length ? (
        <div className="qms-intelligence__error" role="status">
          <AlertTriangle size={17} aria-hidden="true" />
          {riskContext.source_warnings.length} authoritative source warning(s). Missing source data is surfaced rather than treated as zero exposure.
        </div>
      ) : null}

      <section className="qms-intelligence__metrics" aria-label="Assurance operating metrics">
        <article><strong>{pct(overview?.programme.completion.value ?? null)}</strong><span>Programme completion</span><small>{overview?.programme.completion.numerator ?? 0}/{overview?.programme.completion.denominator ?? 0} governed requirements</small></article>
        <article><strong>{overview?.assurance.open_cases ?? 0}</strong><span>Open assurance cases</span><small>{overview?.assurance.overdue_cases ?? 0} past due</small></article>
        <article><strong>{riskContext?.reliability.high_critical_events_90d ?? 0}</strong><span>High/critical reliability events</span><small>authoritative 90-day event ledger</small></article>
        <article><strong>{overview?.people.expiring_within_60_days ?? 0}</strong><span>Privileges expiring ≤60d</span><small>{overview?.people.active_privileges ?? 0} active privileges</small></article>
      </section>

      <section className="qms-intelligence__grid">
        <article className="qms-intelligence__panel">
          <header><div><span>Deterministic signals</span><h2>Human review queue</h2></div><BarChart3 size={20} aria-hidden="true" /></header>
          <p className="qms-intelligence__note">{overview?.method.statement || "Signals use deterministic source calculations only."}</p>
          <div className="qms-intelligence__signals">
            {signals.length ? signals.map((signal) => <div key={signal.id}><strong>{signal.metric.replaceAll("_", " ")}</strong><span>{signal.severity} · observed {signal.observed_value ?? signal.value} {signal.operator} {signal.threshold}</span><p>{signal.explanation}</p></div>) : <p>{loading ? "Loading signals…" : rules.length ? "No triggered observations are open." : "No signal rules configured yet."}</p>}
          </div>
          <footer>{rules.length} configured rule(s)</footer>
        </article>

        <article className="qms-intelligence__panel">
          <header><div><span>Approval Digital Twin</span><h2>{twin?.assurance_state || "UNRESOLVED"}</h2></div><ShieldCheck size={20} aria-hidden="true" /></header>
          <p className="qms-intelligence__note">{twin?.explanation || "Evidence-support state is not a regulatory compliance declaration."}</p>
          <div className="qms-intelligence__state-grid">{["SUPPORTED", "UNSUPPORTED", "STALE", "UNRESOLVED", "BLOCKED"].map((state) => <div key={state}><strong>{twin?.state_counts[state] ?? graphState[state] ?? 0}</strong><span>{state}</span></div>)}</div>
          <div className="qms-intelligence__blockers">{twin?.blockers.length ? twin.blockers.slice(0, 10).map((item) => <div key={item.id}><strong>{item.title}</strong><span>{item.support_state} · {item.node_type}</span><p>{item.state_reason}</p>{item.source_route ? <a href={item.source_route}>Open authoritative source</a> : null}</div>) : <p>No unsupported/stale/unresolved/blocked graph nodes are recorded.</p>}</div>
        </article>
      </section>

      <section className="qms-intelligence__panel">
        <header><div><span>Risk-based audit planning</span><h2>Cross-source assurance pressure</h2></div><ScanSearch size={20} aria-hidden="true" /></header>
        <p className="qms-intelligence__note">{riskContext?.method.statement || "Loading source-attributed planning context…"}</p>
        {riskContext?.global_factors.length ? (
          <div className="qms-intelligence__factor-list" aria-label="Global assurance pressures">
            {riskContext.global_factors.map((factor) => <span key={factor.code}>{factor.label}: {String(factor.value)} · {factor.source}</span>)}
          </div>
        ) : null}
        <div className="qms-intelligence__surveillance">
          {riskContext?.items.length ? riskContext.items.map((item) => <article key={item.universe_item_id}>
            <div><strong>{item.label}</strong><span>{item.entity_type} · {item.source_owner_module}</span></div>
            <div className="qms-intelligence__factor-list">{item.factors.map((factor) => <span key={`${item.universe_item_id}-${factor.code}`} className={factor.hard_requirement ? "is-hard" : ""}>{factor.hard_requirement ? "HARD · " : ""}{factor.label}: {String(factor.value)}</span>)}</div>
            <p>{item.method}</p>
            {item.source_route ? <a href={item.source_route}>Authoritative source</a> : null}
          </article>) : <p>{loading ? "Loading cross-source risk context…" : "No active Audit Universe items are configured."}</p>}
        </div>
        {riskContext?.source_warnings.length ? <details><summary>Source availability warnings</summary><ul>{riskContext.source_warnings.map((warning, index) => <li key={`${warning.source}-${index}`}><strong>{warning.source}</strong>: {warning.message}</li>)}</ul></details> : null}
      </section>

      <section className="qms-intelligence__panel">
        <header><div><span>Targeted surveillance</span><h2>Programme-specific attention order</h2></div><ScanSearch size={20} aria-hidden="true" /></header>
        <div className="qms-intelligence__surveillance">
          {overview?.targeted_surveillance.length ? overview.targeted_surveillance.map((item) => <article key={item.universe_item_id}><div><strong>{item.label}</strong><span>{item.entity_type} · {item.source_owner_module}</span></div><div className="qms-intelligence__factor-list">{item.factors.map((factor) => <span key={factor.code} className={factor.hard_requirement ? "is-hard" : ""}>{factor.hard_requirement ? "HARD · " : ""}{factor.label}: {String(factor.value)}</span>)}</div><p>{item.explanation}</p>{item.source_route ? <a href={item.source_route}>Authoritative source</a> : null}</article>) : <p>{loading ? "Loading surveillance factors…" : "No governed surveillance factor currently requires ranked attention."}</p>}
        </div>
      </section>

      <section className="qms-intelligence__panel">
        <header><div><span>Regulatory impact graph</span><h2>Source-attributed support nodes</h2></div><Network size={20} aria-hidden="true" /></header>
        <div className="qms-intelligence__table-wrap"><table><thead><tr><th>Node</th><th>Type</th><th>Support state</th><th>Authoritative owner</th><th>Reason</th></tr></thead><tbody>{nodes.length ? nodes.map((node) => <tr key={node.id}><td>{node.source_route ? <a href={node.source_route}>{node.title}</a> : node.title}</td><td>{node.node_type}</td><td><strong>{node.support_state}</strong></td><td>{node.source_owner_module} · {node.source_type}</td><td>{node.state_reason}</td></tr>) : <tr><td colSpan={5}>{loading ? "Loading approval graph…" : "No approval-impact nodes have been registered."}</td></tr>}</tbody></table></div>
      </section>
    </main>
  );
};

export default QmsIntelligencePage;
