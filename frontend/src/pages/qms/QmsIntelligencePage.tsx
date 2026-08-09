import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CalendarClock,
  Network,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";

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
  type QmsRiskPlanningFactor,
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

function humanise(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function factorValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Intl.NumberFormat().format(value);
  if (typeof value === "object") {
    try {
      const serialized = JSON.stringify(value);
      return serialized.length > 90 ? `${serialized.slice(0, 87)}…` : serialized;
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function sourceDateLabel(value?: string | null): string {
  if (!value) return "Date not supplied";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function priorityTone(item: QmsRiskPlanningContext["items"][number]): "danger" | "warning" | "primary" | "neutral" {
  if (item.mandatory_surveillance) return "danger";
  if (["CRITICAL", "HIGH"].includes(item.risk_classification) || ["CRITICAL", "HIGH"].includes(item.regulatory_criticality)) return "warning";
  if (item.factors.some((factor) => factor.hard_requirement)) return "warning";
  if (item.factors.length) return "primary";
  return "neutral";
}

const FactorCard: React.FC<{ factor: QmsRiskPlanningFactor }> = ({ factor }) => (
  <article className={`qms-intelligence__factor ${factor.hard_requirement ? "is-hard" : ""}`}>
    <div>
      <span>{factor.hard_requirement ? "Mandatory factor" : "Planning factor"}</span>
      <strong>{factor.label}</strong>
    </div>
    <b>{factorValue(factor.value)}</b>
    <p>{factor.rationale}</p>
    <footer>
      <span>{factor.source_record || factor.source}</span>
      <span>{sourceDateLabel(factor.source_date)}</span>
      {factor.planning_weight != null ? <span>Weight {factor.planning_weight}</span> : null}
    </footer>
  </article>
);

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

  const priorities = useMemo(
    () => [...(riskContext?.items || [])].sort((left, right) => left.planning_order - right.planning_order),
    [riskContext?.items],
  );
  const mandatoryCount = priorities.filter((item) => item.mandatory_surveillance || item.factors.some((factor) => factor.hard_requirement)).length;
  const highPriorityCount = priorities.filter((item) => ["CRITICAL", "HIGH"].includes(item.risk_classification) || ["CRITICAL", "HIGH"].includes(item.regulatory_criticality)).length;
  const sourceChangeCount = priorities.filter((item) => item.factors.some((factor) => ["NEW_CAPABILITY", "NEW_AIRCRAFT_TYPE", "DIRECT_NEW_CAPABILITY", "DIRECT_NEW_AIRCRAFT_TYPE"].includes(factor.code))).length;
  const blockerCount = twin?.blockers.length ?? 0;

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
          <span>Quality Intelligence</span>
          <h1>Surveillance priorities & assurance impact</h1>
          <p>See where Quality should focus next and why. Every planning factor is deterministic, source-attributed and reviewable; no predictive compliance probability is generated.</p>
        </div>
        <div className="qms-intelligence__actions">
          <button type="button" onClick={() => void configureAndEvaluate()} disabled={busy}><ScanSearch size={16} aria-hidden="true" /> {busy ? "Evaluating…" : "Evaluate signals"}</button>
          <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
        </div>
      </header>

      {error ? <div className="qms-intelligence__error" role="alert"><AlertTriangle size={18} aria-hidden="true" /> {error}</div> : null}
      {riskContext?.source_warnings.length ? (
        <div className="qms-intelligence__warning" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <div><strong>{riskContext.source_warnings.length} authoritative source warning(s)</strong><span>Unavailable source data is surfaced explicitly and is never treated as zero exposure.</span></div>
        </div>
      ) : null}

      <section className="qms-intelligence__metrics" aria-label="Surveillance posture">
        <article className={mandatoryCount ? "is-danger" : ""}><strong>{mandatoryCount}</strong><span>Mandatory / hard surveillance</span><small>Cannot be averaged away by lower-weight factors</small></article>
        <article className={highPriorityCount ? "is-warning" : ""}><strong>{highPriorityCount}</strong><span>High-priority universe items</span><small>High or critical governed risk / regulatory criticality</small></article>
        <article><strong>{sourceChangeCount}</strong><span>Capability / aircraft-type changes</span><small>Only explicit governed Mission scope is counted</small></article>
        <article className={blockerCount ? "is-warning" : ""}><strong>{blockerCount}</strong><span>Approval-impact blockers</span><small>{twin?.assurance_state ? humanise(twin.assurance_state) : "Digital twin unresolved"}</small></article>
      </section>

      <section className="qms-intelligence__panel qms-intelligence__priority-panel">
        <header>
          <div><span>Risk-based audit planning</span><h2>Surveillance priorities</h2><p>{riskContext?.method.statement || "Deterministic planning context is loading."}</p></div>
          <div className="qms-intelligence__as-of"><CalendarClock size={16} /><span>As of</span><strong>{sourceDateLabel(riskContext?.as_of)}</strong></div>
        </header>

        {priorities.length ? (
          <div className="qms-intelligence__priority-list">
            {priorities.map((item, index) => {
              const tone = priorityTone(item);
              const headlineFactors = item.factors.slice(0, 4);
              return (
                <article key={item.universe_item_id} className={`qms-intelligence__priority is-${tone}`}>
                  <div className="qms-intelligence__priority-rank">{index + 1}</div>
                  <div className="qms-intelligence__priority-body">
                    <header>
                      <div>
                        <span>{humanise(item.entity_type)} · {humanise(item.source_owner_module)}</span>
                        <h3>{item.label}</h3>
                      </div>
                      <div className="qms-intelligence__priority-badges">
                        {item.mandatory_surveillance ? <span className="is-hard">Mandatory</span> : null}
                        <span>{humanise(item.risk_classification)} risk</span>
                        <span>{humanise(item.regulatory_criticality)} criticality</span>
                      </div>
                    </header>
                    <div className="qms-intelligence__priority-summary">
                      {headlineFactors.length ? headlineFactors.map((factor) => <span key={factor.code} className={factor.hard_requirement ? "is-hard" : ""}><strong>{factor.label}</strong>{factorValue(factor.value)}</span>) : <span><strong>No active pressure factors</strong>Universe item remains in governed planning order.</span>}
                    </div>
                    <p>{item.method}</p>
                    <footer>
                      <span>Planning order {item.planning_order}</span>
                      <span>{item.programme_states.length ? item.programme_states.map(humanise).join(" · ") : "No programme state"}</span>
                      {item.source_route ? <a href={item.source_route}>Open authoritative source <ArrowRight size={14} /></a> : <span>Source route unavailable</span>}
                    </footer>
                    {item.factors.length ? (
                      <details className="qms-intelligence__factor-disclosure">
                        <summary>Review {item.factors.length} source-attributed factor{item.factors.length === 1 ? "" : "s"}</summary>
                        <div>{item.factors.map((factor) => <FactorCard key={`${item.universe_item_id}-${factor.code}`} factor={factor} />)}</div>
                      </details>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : <div className="qms-intelligence__empty">{loading ? "Loading governed surveillance priorities…" : "No active Audit Universe items are configured for risk-based planning."}</div>}
      </section>

      {riskContext?.global_factors.length ? (
        <section className="qms-intelligence__panel">
          <header><div><span>Cross-system pressure</span><h2>Global assurance factors</h2><p>Signals that affect the planning posture beyond a single Audit Universe item.</p></div><BarChart3 size={20} aria-hidden="true" /></header>
          <div className="qms-intelligence__global-factors">{riskContext.global_factors.map((factor) => <FactorCard key={factor.code} factor={factor} />)}</div>
        </section>
      ) : null}

      <section className="qms-intelligence__support-grid">
        <article className="qms-intelligence__panel">
          <header><div><span>Deterministic signals</span><h2>Human review queue</h2><p>{overview?.method.statement || "Signals use deterministic source calculations only."}</p></div><BarChart3 size={20} aria-hidden="true" /></header>
          <div className="qms-intelligence__signals">
            {signals.length ? signals.map((signal) => <div key={signal.id}><strong>{humanise(signal.metric)}</strong><span>{humanise(signal.severity)} · observed {signal.observed_value ?? signal.value} {signal.operator} {signal.threshold}</span><p>{signal.explanation}</p></div>) : <p>{loading ? "Loading signals…" : rules.length ? "No triggered observations are open." : "No signal rules configured yet."}</p>}
          </div>
          <footer>{rules.length} configured rule(s)</footer>
        </article>

        <article className="qms-intelligence__panel">
          <header><div><span>Approval Digital Twin</span><h2>{twin?.assurance_state ? humanise(twin.assurance_state) : "Unresolved"}</h2><p>{twin?.explanation || "Evidence-support state is not a regulatory compliance declaration."}</p></div><ShieldCheck size={20} aria-hidden="true" /></header>
          <div className="qms-intelligence__state-grid">{["SUPPORTED", "UNSUPPORTED", "STALE", "UNRESOLVED", "BLOCKED"].map((state) => <div key={state}><strong>{twin?.state_counts[state] ?? graphState[state] ?? 0}</strong><span>{humanise(state)}</span></div>)}</div>
          <div className="qms-intelligence__blockers">{twin?.blockers.length ? twin.blockers.slice(0, 10).map((item) => <div key={item.id}><strong>{item.title}</strong><span>{humanise(item.support_state)} · {humanise(item.node_type)}</span><p>{item.state_reason}</p>{item.source_route ? <a href={item.source_route}>Open authoritative source</a> : null}</div>) : <p>No unsupported, stale, unresolved or blocked graph nodes are recorded.</p>}</div>
        </article>
      </section>

      {overview?.targeted_surveillance.length ? (
        <details className="qms-intelligence__disclosure">
          <summary><div><span>Programme-specific view</span><strong>Targeted surveillance calculation</strong><small>Additional programme-specific ordering retained for auditability.</small></div><ScanSearch size={19} /></summary>
          <div className="qms-intelligence__targeted-list">{overview.targeted_surveillance.map((item) => <article key={item.universe_item_id}><div><strong>{item.label}</strong><span>{humanise(item.entity_type)} · {humanise(item.source_owner_module)}</span></div><p>{item.explanation}</p><div>{item.factors.map((factor) => <span key={factor.code} className={factor.hard_requirement ? "is-hard" : ""}>{factor.hard_requirement ? "Mandatory · " : ""}{factor.label}: {factorValue(factor.value)}</span>)}</div>{item.source_route ? <a href={item.source_route}>Authoritative source</a> : null}</article>)}</div>
        </details>
      ) : null}

      <details className="qms-intelligence__disclosure">
        <summary><div><span>Regulatory impact graph</span><strong>Source-attributed support nodes</strong><small>Detailed technical evidence-support graph for investigation and auditability.</small></div><Network size={19} /></summary>
        <div className="qms-intelligence__table-wrap"><table><thead><tr><th>Node</th><th>Type</th><th>Support state</th><th>Authoritative owner</th><th>Reason</th></tr></thead><tbody>{nodes.length ? nodes.map((node) => <tr key={node.id}><td>{node.source_route ? <a href={node.source_route}>{node.title}</a> : node.title}</td><td>{humanise(node.node_type)}</td><td><strong>{humanise(node.support_state)}</strong></td><td>{humanise(node.source_owner_module)} · {humanise(node.source_type)}</td><td>{node.state_reason}</td></tr>) : <tr><td colSpan={5}>{loading ? "Loading approval graph…" : "No approval-impact nodes have been registered."}</td></tr>}</tbody></table></div>
      </details>
    </main>
  );
};

export default QmsIntelligencePage;
