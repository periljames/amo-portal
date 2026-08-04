import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  BrainCircuit,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  GitBranch,
  Link2,
  LoaderCircle,
  Plus,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  UsersRound,
  X,
} from "lucide-react";

import {
  createAssuranceControl,
  decideQualityInsight,
  getAssuranceControls,
  getAssuranceEvidenceGraph,
  getQualityExcellenceOverview,
  getQualityInsights,
  rebuildQualityInsights,
  type AssuranceControlCreate,
  type ControlCriticality,
  type InsightStatus,
  type RiskLevel,
} from "../../services/qualityExcellence";
import "../../styles/quality-excellence-cockpit.css";


type HubView = "readiness" | "controls" | "evidence" | "intelligence";

const HUB_VIEWS = new Set<HubView>(["readiness", "controls", "evidence", "intelligence"]);

const DEFAULT_CONTROL: AssuranceControlCreate = {
  control_code: "",
  title: "",
  description: "",
  framework: "KCAR PART 145",
  clause_reference: "",
  process_area: "",
  owner_user_id: null,
  criticality: "HIGH",
  status: "ACTIVE",
  test_frequency_days: 365,
  evidence_expectation: "",
  last_tested_at: null,
  next_test_due: null,
};

function parseAmoCode(pathname: string): string | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)\/quality\/?$/i);
  return match ? decodeURIComponent(match[1]) : null;
}

function activeHub(search: string): HubView {
  const raw = new URLSearchParams(search).get("hub") as HubView | null;
  return raw && HUB_VIEWS.has(raw) ? raw : "readiness";
}

function riskRank(level: RiskLevel): number {
  return { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }[level];
}

function scoreTone(score: number): string {
  if (score >= 85) return "strong";
  if (score >= 70) return "watch";
  if (score >= 50) return "risk";
  return "critical";
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Not scheduled";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(parsed);
}

function metricLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function ReadinessGauge({ score, band }: { score: number; band: string }) {
  const tone = scoreTone(score);
  return (
    <div className={`qe-readiness-gauge qe-readiness-gauge--${tone}`} aria-label={`Operational readiness ${score} percent, ${band}`}>
      <svg viewBox="0 0 120 120" role="img" aria-hidden="true">
        <circle cx="60" cy="60" r="50" pathLength="100" className="qe-readiness-gauge__track" />
        <circle
          cx="60"
          cy="60"
          r="50"
          pathLength="100"
          className="qe-readiness-gauge__value"
          strokeDasharray={`${score} ${100 - score}`}
        />
      </svg>
      <span>
        <strong>{score}</strong>
        <small>{band.replaceAll("_", " ")}</small>
      </span>
    </div>
  );
}

function SeverityBadge({ level }: { level: RiskLevel | ControlCriticality }) {
  return <span className={`qe-severity qe-severity--${level.toLowerCase()}`}>{level}</span>;
}

const QualityExcellenceCockpit: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const amoCode = useMemo(() => parseAmoCode(location.pathname), [location.pathname]);
  const view = activeHub(location.search);
  const [mountTarget, setMountTarget] = useState<HTMLElement | null>(null);
  const [controlForm, setControlForm] = useState<AssuranceControlCreate>(DEFAULT_CONTROL);
  const [showControlForm, setShowControlForm] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!amoCode) {
      setMountTarget(null);
      return;
    }
    let activeHost: HTMLDivElement | null = null;
    const syncMount = () => {
      const main = document.querySelector<HTMLElement>(".tenant-shell__main");
      if (!main) return;
      let host = main.querySelector<HTMLDivElement>(":scope > .quality-excellence-host");
      if (!host) {
        host = document.createElement("div");
        host.className = "quality-excellence-host";
        const contextHost = main.querySelector(":scope > .quality-context-bar-host");
        if (contextHost?.nextSibling) main.insertBefore(host, contextHost.nextSibling);
        else main.prepend(host);
      }
      activeHost = host;
      setMountTarget((current) => current === host ? current : host);
    };
    syncMount();
    const observer = new MutationObserver(syncMount);
    observer.observe(document.body, { childList: true, subtree: true });
    document.documentElement.classList.add("quality-excellence-active");
    return () => {
      observer.disconnect();
      activeHost?.remove();
      document.documentElement.classList.remove("quality-excellence-active");
    };
  }, [amoCode]);

  const overviewQuery = useQuery({
    queryKey: ["qms-excellence-overview", amoCode],
    queryFn: () => getQualityExcellenceOverview(amoCode || ""),
    enabled: Boolean(amoCode),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  });

  const controlsQuery = useQuery({
    queryKey: ["qms-excellence-controls", amoCode],
    queryFn: () => getAssuranceControls(amoCode || ""),
    enabled: Boolean(amoCode) && (view === "controls" || view === "evidence"),
    staleTime: 20_000,
  });

  const graphQuery = useQuery({
    queryKey: ["qms-excellence-graph", amoCode],
    queryFn: () => getAssuranceEvidenceGraph(amoCode || ""),
    enabled: Boolean(amoCode) && view === "evidence",
    staleTime: 20_000,
  });

  const insightsQuery = useQuery({
    queryKey: ["qms-excellence-insights", amoCode],
    queryFn: () => getQualityInsights(amoCode || ""),
    enabled: Boolean(amoCode) && view === "intelligence",
    staleTime: 15_000,
  });

  const createControlMutation = useMutation({
    mutationFn: () => createAssuranceControl(amoCode || "", {
      ...controlForm,
      control_code: controlForm.control_code.trim(),
      title: controlForm.title.trim(),
      framework: controlForm.framework.trim(),
      clause_reference: controlForm.clause_reference?.trim() || null,
      process_area: controlForm.process_area.trim(),
      description: controlForm.description?.trim() || null,
      evidence_expectation: controlForm.evidence_expectation?.trim() || null,
    }),
    onSuccess: async () => {
      setFeedback("Assurance control created and added to the continuous control library.");
      setControlForm(DEFAULT_CONTROL);
      setShowControlForm(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-controls", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-overview", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-graph", amoCode] }),
      ]);
    },
    onError: (error: Error) => setFeedback(error.message || "The control could not be created."),
  });

  const rebuildMutation = useMutation({
    mutationFn: () => rebuildQualityInsights(amoCode || ""),
    onSuccess: async (result) => {
      setFeedback(`${result.generated} recommendation${result.generated === 1 ? "" : "s"} added; ${result.skipped_existing} existing item${result.skipped_existing === 1 ? "" : "s"} retained.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-insights", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-overview", amoCode] }),
      ]);
    },
    onError: (error: Error) => setFeedback(error.message || "Quality intelligence could not be rebuilt."),
  });

  const decisionMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: InsightStatus }) => decideQualityInsight(amoCode || "", id, status),
    onSuccess: async () => {
      setFeedback("Human decision recorded in the quality intelligence register.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-insights", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-excellence-overview", amoCode] }),
      ]);
    },
    onError: (error: Error) => setFeedback(error.message || "The review decision could not be recorded."),
  });

  const setView = (next: HubView) => {
    if (!amoCode) return;
    navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality${next === "readiness" ? "" : `?hub=${next}`}`);
  };

  if (!amoCode || !mountTarget) return null;

  const overview = overviewQuery.data;
  const loading = overviewQuery.isLoading;
  const error = overviewQuery.error instanceof Error ? overviewQuery.error.message : null;

  const briefing = overview
    ? [
        `${overview.readiness.score}% operational readiness (${overview.readiness.band.replaceAll("_", " ").toLowerCase()}).`,
        `${overview.forecast.commitments_due_30_days} audit, CAR or control-test commitments fall due within 30 days.`,
        overview.priority_queue.length
          ? `${overview.priority_queue[0].count} ${overview.priority_queue[0].label.toLowerCase()} currently require the highest attention.`
          : "No critical action queue items are currently open.",
      ]
    : [];

  const evidenceByControl = useMemo(() => {
    const graph = graphQuery.data;
    if (!graph) return new Map<string, Array<{ label: string; status: string; type?: string }>>();
    const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));
    const grouped = new Map<string, Array<{ label: string; status: string; type?: string }>>();
    graph.edges.forEach((edge) => {
      const node = nodeMap.get(edge.to);
      const items = grouped.get(edge.from) || [];
      items.push({ label: node?.label || edge.to, status: edge.status, type: node?.type });
      grouped.set(edge.from, items);
    });
    return grouped;
  }, [graphQuery.data]);

  const insightItems = [...(insightsQuery.data?.items || [])].sort(
    (a, b) => riskRank(a.risk_level) - riskRank(b.risk_level),
  );

  const content = (
    <main className="qe-cockpit" aria-label="Quality continuous assurance control centre">
      <header className="qe-cockpit__header">
        <div>
          <p><ShieldCheck size={16} /> Continuous assurance</p>
          <h1>Quality Control Centre</h1>
          <span>One operational picture across audits, corrective actions, controlled documents, competence and durable regulatory controls.</span>
        </div>
        <div className="qe-cockpit__header-actions">
          <button
            type="button"
            onClick={() => {
              void overviewQuery.refetch();
              if (view === "controls") void controlsQuery.refetch();
              if (view === "evidence") void graphQuery.refetch();
              if (view === "intelligence") void insightsQuery.refetch();
            }}
          >
            <RefreshCw size={16} /> Refresh evidence
          </button>
          <button type="button" className="is-primary" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/plan?view=calendar&create=1`)}>
            <Plus size={16} /> Schedule audit
          </button>
        </div>
      </header>

      <nav className="qe-cockpit__tabs" aria-label="Quality control centre views">
        <button type="button" className={view === "readiness" ? "is-active" : ""} onClick={() => setView("readiness")}>
          <Activity size={16} /> Readiness
        </button>
        <button type="button" className={view === "controls" ? "is-active" : ""} onClick={() => setView("controls")}>
          <Target size={16} /> Control library
        </button>
        <button type="button" className={view === "evidence" ? "is-active" : ""} onClick={() => setView("evidence")}>
          <GitBranch size={16} /> Evidence graph
        </button>
        <button type="button" className={view === "intelligence" ? "is-active" : ""} onClick={() => setView("intelligence")}>
          <BrainCircuit size={16} /> Intelligence review
        </button>
      </nav>

      {feedback ? (
        <div className="qe-feedback" role="status">
          <CheckCircle2 size={17} />
          <span>{feedback}</span>
          <button type="button" aria-label="Dismiss message" onClick={() => setFeedback(null)}><X size={15} /></button>
        </div>
      ) : null}

      {loading ? <div className="qe-loading"><LoaderCircle size={24} className="is-spinning" /> Building the assurance picture…</div> : null}
      {error ? <div className="qe-error" role="alert"><AlertTriangle size={20} /><span>{error}</span></div> : null}

      {overview && view === "readiness" ? (
        <div className="qe-readiness-layout">
          <section className="qe-readiness-summary" aria-labelledby="qe-readiness-title">
            <div className="qe-readiness-summary__headline">
              <div>
                <p>Operational readiness</p>
                <h2 id="qe-readiness-title">Current assurance posture</h2>
              </div>
              <ReadinessGauge score={overview.readiness.score} band={overview.readiness.band} />
            </div>
            <div className="qe-dimensions">
              {overview.readiness.dimensions.map((dimension) => (
                <div key={dimension.id} className="qe-dimension">
                  <span><strong>{dimension.label}</strong><em>{dimension.score}%</em></span>
                  <div><i style={{ width: `${dimension.score}%` }} /></div>
                </div>
              ))}
            </div>
            <p className="qe-disclaimer"><Scale size={14} /> {overview.readiness.disclaimer}</p>
          </section>

          <section className="qe-priority-lane" aria-labelledby="qe-priority-title">
            <div className="qe-section-heading">
              <div>
                <p>Action lane</p>
                <h2 id="qe-priority-title">What needs attention now</h2>
              </div>
              <span>{overview.priority_queue.length} active signals</span>
            </div>
            {overview.priority_queue.length ? (
              <div className="qe-priority-list">
                {overview.priority_queue.map((item) => (
                  <button key={item.id} type="button" onClick={() => navigate(item.path)}>
                    <span className="qe-priority-list__count">{item.count}</span>
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.why}</small>
                    </span>
                    <SeverityBadge level={item.severity} />
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="qe-empty"><CheckCircle2 size={22} /><strong>No immediate pressure signals</strong><span>Continue routine surveillance and verify controls on schedule.</span></div>
            )}
          </section>

          <section className="qe-forecast" aria-labelledby="qe-forecast-title">
            <div className="qe-section-heading">
              <div>
                <p>30-day forecast</p>
                <h2 id="qe-forecast-title">Assurance workload</h2>
              </div>
              <span className={`qe-forecast__band qe-forecast__band--${overview.forecast.band.toLowerCase()}`}>{overview.forecast.band}</span>
            </div>
            <strong className="qe-forecast__number">{overview.forecast.commitments_due_30_days}</strong>
            <p>{overview.forecast.explanation}</p>
            <div className="qe-metric-strip">
              {[
                "audits_due_30",
                "cars_due_30",
                "controls_due",
                "expired_training",
              ].map((key) => (
                <div key={key}><span>{metricLabel(key)}</span><strong>{overview.metrics[key] || 0}</strong></div>
              ))}
            </div>
          </section>

          <section className="qe-briefing" aria-labelledby="qe-briefing-title">
            <div className="qe-section-heading">
              <div>
                <p>Management review briefing</p>
                <h2 id="qe-briefing-title">Evidence-based summary</h2>
              </div>
              <FileCheck2 size={20} />
            </div>
            <ol>{briefing.map((line) => <li key={line}>{line}</li>)}</ol>
            <button type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/management-review/dashboard`)}>
              Open management review <ArrowRight size={15} />
            </button>
          </section>

          <section className="qe-capability-row" aria-label="Advanced assurance capabilities">
            {overview.capabilities.map((capability, index) => {
              const icons = [Target, GitBranch, Bot];
              const Icon = icons[index] || Sparkles;
              return (
                <button key={capability.id} type="button" onClick={() => navigate(capability.path)}>
                  <Icon size={20} />
                  <span><strong>{capability.label}</strong><small>{capability.description}</small></span>
                  <ArrowRight size={16} />
                </button>
              );
            })}
          </section>

          {overview.warnings.length ? (
            <section className="qe-source-warnings" aria-label="Incomplete data sources">
              <AlertTriangle size={18} />
              <span><strong>Some sources could not be read.</strong> Readiness deductions were calculated from available authoritative data only.</span>
              <details><summary>Technical detail</summary><pre>{JSON.stringify(overview.warnings, null, 2)}</pre></details>
            </section>
          ) : null}
        </div>
      ) : null}

      {view === "controls" ? (
        <div className="qe-controls-layout">
          <section className="qe-controls-register">
            <div className="qe-section-heading">
              <div>
                <p>Durable compliance controls</p>
                <h2>Control library</h2>
              </div>
              <button type="button" className="is-primary" onClick={() => setShowControlForm((current) => !current)}>
                <Plus size={15} /> New control
              </button>
            </div>
            <p className="qe-section-lead">Use one control across multiple audits and frameworks. Link the proof once, retest it on cadence, and see where assurance is ageing.</p>
            {controlsQuery.isLoading ? <div className="qe-loading"><LoaderCircle size={20} className="is-spinning" /> Loading controls…</div> : null}
            {!controlsQuery.isLoading && !(controlsQuery.data?.items.length) ? (
              <div className="qe-empty"><Target size={24} /><strong>No continuous controls yet</strong><span>Create critical regulatory and exposition controls first, then connect current evidence.</span></div>
            ) : null}
            <div className="qe-control-table" role="table" aria-label="Assurance controls">
              {controlsQuery.data?.items.map((control) => (
                <article key={control.id} role="row">
                  <div className="qe-control-table__identity">
                    <span>{control.control_code}</span>
                    <strong>{control.title}</strong>
                    <small>{control.framework}{control.clause_reference ? ` · ${control.clause_reference}` : ""}</small>
                  </div>
                  <div><small>Process</small><strong>{control.process_area}</strong></div>
                  <div><small>Evidence</small><strong>{control.verified_evidence_count}/{control.evidence_count} verified</strong></div>
                  <div><small>Next test</small><strong>{formatDate(control.next_test_due)}</strong></div>
                  <div className="qe-control-table__state">
                    <SeverityBadge level={control.criticality} />
                    <span className={`qe-due-state qe-due-state--${control.due_state.toLowerCase()}`}>{control.due_state.replaceAll("_", " ")}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>

          {showControlForm ? (
            <aside className="qe-control-form" aria-label="Create assurance control">
              <div className="qe-section-heading">
                <div><p>Control twin</p><h2>Create control</h2></div>
                <button type="button" aria-label="Close control form" onClick={() => setShowControlForm(false)}><X size={17} /></button>
              </div>
              <label><span>Control code</span><input value={controlForm.control_code} onChange={(event) => setControlForm((current) => ({ ...current, control_code: event.target.value }))} placeholder="145.A.65-C01" /></label>
              <label><span>Title</span><input value={controlForm.title} onChange={(event) => setControlForm((current) => ({ ...current, title: event.target.value }))} placeholder="Independent quality audit programme" /></label>
              <div className="qe-control-form__split">
                <label><span>Framework</span><input value={controlForm.framework} onChange={(event) => setControlForm((current) => ({ ...current, framework: event.target.value }))} /></label>
                <label><span>Clause</span><input value={controlForm.clause_reference || ""} onChange={(event) => setControlForm((current) => ({ ...current, clause_reference: event.target.value }))} placeholder="145.A.65(c)" /></label>
              </div>
              <label><span>Process area</span><input value={controlForm.process_area} onChange={(event) => setControlForm((current) => ({ ...current, process_area: event.target.value }))} placeholder="Quality assurance" /></label>
              <div className="qe-control-form__split">
                <label><span>Criticality</span><select value={controlForm.criticality} onChange={(event) => setControlForm((current) => ({ ...current, criticality: event.target.value as ControlCriticality }))}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
                <label><span>Test frequency</span><select value={controlForm.test_frequency_days} onChange={(event) => setControlForm((current) => ({ ...current, test_frequency_days: Number(event.target.value) }))}><option value={30}>Monthly</option><option value={90}>Quarterly</option><option value={180}>Six monthly</option><option value={365}>Annual</option><option value={730}>Two yearly</option></select></label>
              </div>
              <label><span>Next test due</span><input type="date" value={controlForm.next_test_due || ""} onChange={(event) => setControlForm((current) => ({ ...current, next_test_due: event.target.value || null }))} /></label>
              <label><span>Evidence expectation</span><textarea value={controlForm.evidence_expectation || ""} onChange={(event) => setControlForm((current) => ({ ...current, evidence_expectation: event.target.value }))} placeholder="Approved audit programme, completed audit reports, auditor independence and closure evidence." /></label>
              <label><span>Description</span><textarea value={controlForm.description || ""} onChange={(event) => setControlForm((current) => ({ ...current, description: event.target.value }))} /></label>
              <button
                type="button"
                className="is-primary qe-control-form__submit"
                disabled={!controlForm.control_code.trim() || !controlForm.title.trim() || !controlForm.process_area.trim() || createControlMutation.isPending}
                onClick={() => createControlMutation.mutate()}
              >
                {createControlMutation.isPending ? <LoaderCircle size={16} className="is-spinning" /> : <Check size={16} />}
                Create governed control
              </button>
            </aside>
          ) : null}
        </div>
      ) : null}

      {view === "evidence" ? (
        <div className="qe-evidence-layout">
          <section className="qe-evidence-summary">
            <div className="qe-section-heading"><div><p>Assurance traceability</p><h2>Evidence graph</h2></div><GitBranch size={22} /></div>
            <p className="qe-section-lead">The graph shows the proof behind each durable control. Evidence can come from audits, documents, CARs, training, suppliers, calibration or any governed portal record.</p>
            <div className="qe-metric-strip qe-metric-strip--four">
              <div><span>Controls</span><strong>{graphQuery.data?.summary.controls || 0}</strong></div>
              <div><span>Evidence records</span><strong>{graphQuery.data?.summary.evidence_records || 0}</strong></div>
              <div><span>Relationships</span><strong>{graphQuery.data?.summary.relationships || 0}</strong></div>
              <div><span>Without evidence</span><strong>{graphQuery.data?.summary.controls_without_evidence || 0}</strong></div>
            </div>
          </section>
          {graphQuery.isLoading ? <div className="qe-loading"><LoaderCircle size={20} className="is-spinning" /> Building evidence relationships…</div> : null}
          <section className="qe-evidence-map" aria-label="Control evidence relationships">
            {controlsQuery.data?.items.map((control) => {
              const evidence = evidenceByControl.get(`control:${control.id}`) || [];
              return (
                <article key={control.id}>
                  <div className="qe-evidence-map__control">
                    <Target size={18} />
                    <span><small>{control.control_code} · {control.framework}</small><strong>{control.title}</strong></span>
                    <SeverityBadge level={control.criticality} />
                  </div>
                  <div className="qe-evidence-map__edges" aria-label={`${control.title} evidence`}>
                    {evidence.length ? evidence.map((item) => (
                      <span key={`${item.type}:${item.label}`} className={`qe-evidence-chip qe-evidence-chip--${item.status.toLowerCase()}`}>
                        <Link2 size={13} /> {item.label}<em>{item.status}</em>
                      </span>
                    )) : <span className="qe-evidence-chip qe-evidence-chip--missing"><AlertTriangle size={13} /> No evidence linked</span>}
                  </div>
                </article>
              );
            })}
          </section>
        </div>
      ) : null}

      {view === "intelligence" ? (
        <div className="qe-intelligence-layout">
          <section className="qe-intelligence-guardrail">
            <div className="qe-section-heading"><div><p>Human-in-the-loop</p><h2>Quality intelligence review</h2></div><Bot size={22} /></div>
            <p>Rules or future AI services may detect patterns and draft recommendations, but they cannot approve audits, close findings, alter CARs or modify controlled documents. A named user must decide every recommendation.</p>
            <div className="qe-guardrail-steps">
              <span><Sparkles size={16} /><strong>1. Detect</strong><small>Read authoritative tenant data.</small></span>
              <span><BrainCircuit size={16} /><strong>2. Propose</strong><small>Explain rationale and source fingerprint.</small></span>
              <span><UsersRound size={16} /><strong>3. Decide</strong><small>Human accepts, dismisses or implements.</small></span>
              <span><ClipboardCheck size={16} /><strong>4. Audit</strong><small>Retain the decision trail.</small></span>
            </div>
            <button type="button" className="is-primary" disabled={rebuildMutation.isPending} onClick={() => rebuildMutation.mutate()}>
              {rebuildMutation.isPending ? <LoaderCircle size={16} className="is-spinning" /> : <BrainCircuit size={16} />}
              Rebuild recommendations
            </button>
          </section>

          <section className="qe-insight-queue">
            <div className="qe-section-heading"><div><p>Review queue</p><h2>Recommendations awaiting accountability</h2></div><span>{insightsQuery.data?.total || 0} records</span></div>
            {insightsQuery.isLoading ? <div className="qe-loading"><LoaderCircle size={20} className="is-spinning" /> Loading intelligence register…</div> : null}
            {!insightsQuery.isLoading && !insightItems.length ? <div className="qe-empty"><CheckCircle2 size={24} /><strong>No intelligence items recorded</strong><span>Run the rules engine to create explainable, reviewable recommendations from current QMS pressure signals.</span></div> : null}
            <div className="qe-insight-list">
              {insightItems.map((item) => (
                <article key={item.id} className={`qe-insight qe-insight--${item.status.toLowerCase()}`}>
                  <div className="qe-insight__heading">
                    <SeverityBadge level={item.risk_level} />
                    <span><small>{item.insight_type.replaceAll("_", " ")} · {item.created_by}</small><strong>{item.title}</strong></span>
                    <em>{item.status}</em>
                  </div>
                  <p>{item.rationale}</p>
                  {item.recommendation ? <blockquote>{item.recommendation}</blockquote> : null}
                  {item.status === "PROPOSED" ? (
                    <div className="qe-insight__actions">
                      <button type="button" onClick={() => decisionMutation.mutate({ id: item.id, status: "ACCEPTED" })}><Check size={15} /> Accept for action</button>
                      <button type="button" onClick={() => decisionMutation.mutate({ id: item.id, status: "DISMISSED" })}><X size={15} /> Dismiss</button>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );

  return createPortal(content, mountTarget);
};

export default QualityExcellenceCockpit;
