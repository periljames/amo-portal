import React, { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Bot,
  BrainCircuit,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  ExternalLink,
  FileCheck2,
  GitBranch,
  History,
  Link2,
  LoaderCircle,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TestTube2,
  UsersRound,
  X,
} from "lucide-react";

import { getCachedUser } from "../../services/auth";
import {
  createAssuranceControl,
  decideControlApproval,
  decideQualityInsight,
  getAssuranceControls,
  getAssuranceEvents,
  getAssuranceEvidenceGraph,
  getEvidenceSourceCatalog,
  getManagementReviewPack,
  getQualityExcellenceOverview,
  getQualityInsights,
  linkAssuranceEvidence,
  rebuildQualityInsights,
  reconcileAssuranceEvidence,
  recordControlTest,
  searchEvidenceSources,
  type AssuranceControl,
  type AssuranceControlCreate,
  type ControlApprovalStatus,
  type ControlCriticality,
  type ControlTestResult,
  type EvidenceStatus,
  type InsightStatus,
  type RiskLevel,
  type SourceSearchItem,
} from "../../services/qualityExcellence";
import "../../styles/quality-excellence-cockpit.css";
import "../../styles/quality-excellence-wiring.css";


type HubView = "readiness" | "controls" | "evidence" | "intelligence";
type DrawerMode = "create" | "evidence" | "test" | null;

const HUB_VIEWS = new Set<HubView>(["readiness", "controls", "evidence", "intelligence"]);

const DEFAULT_CONTROL: AssuranceControlCreate = {
  control_code: "",
  title: "",
  description: "",
  control_objective: "",
  test_method: "",
  framework: "KCAR PART 145",
  clause_reference: "",
  process_area: "",
  owner_user_id: null,
  criticality: "HIGH",
  status: "DRAFT",
  approval_status: "DRAFT",
  test_frequency_days: 365,
  evidence_expectation: "",
  last_tested_at: null,
  next_test_due: null,
};

const DEFAULT_TEST = {
  result: "PASS" as ControlTestResult,
  method: "",
  notes: "",
  next_test_due: "",
};

function activeHub(search: string): HubView {
  const raw = new URLSearchParams(search).get("hub") as HubView | null;
  return raw && HUB_VIEWS.has(raw) ? raw : "readiness";
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

function formatDate(value: string | null | undefined, fallback = "Not scheduled"): string {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(parsed);
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Not yet";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function labelFromKey(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function scoreTone(score: number): string {
  if (score >= 85) return "strong";
  if (score >= 70) return "watch";
  if (score >= 50) return "risk";
  return "critical";
}

function riskRank(level: RiskLevel): number {
  return { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }[level];
}

function SeverityBadge({ level }: { level: RiskLevel | ControlCriticality }) {
  return <span className={`qew-severity qew-severity--${level.toLowerCase()}`}>{level}</span>;
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`qew-status qew-status--${status.toLowerCase().replaceAll("_", "-")}`}>{status.replaceAll("_", " ")}</span>;
}

function ReadinessGauge({ score, band }: { score: number; band: string }) {
  const tone = scoreTone(score);
  return (
    <div className={`qew-gauge qew-gauge--${tone}`} aria-label={`Operational readiness ${score} percent, ${band}`}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r="51" pathLength="100" className="qew-gauge__track" />
        <circle cx="60" cy="60" r="51" pathLength="100" className="qew-gauge__value" strokeDasharray={`${score} ${100 - score}`} />
      </svg>
      <span><strong>{score}</strong><small>{band.replaceAll("_", " ")}</small></span>
    </div>
  );
}

const QualityExcellenceCockpit: React.FC<{ amoCode: string }> = ({ amoCode }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = getCachedUser();
  const role = String(user?.role || "").toUpperCase();
  const canManage = Boolean(user?.is_superuser || user?.is_amo_admin || role === "QUALITY_MANAGER" || role === "AMO_ADMIN");
  const view = activeHub(location.search);

  const [feedback, setFeedback] = useState<string | null>(null);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>(null);
  const [selectedControl, setSelectedControl] = useState<AssuranceControl | null>(null);
  const [controlForm, setControlForm] = useState<AssuranceControlCreate>(DEFAULT_CONTROL);
  const [controlQuery, setControlQuery] = useState("");
  const [approvalFilter, setApprovalFilter] = useState<ControlApprovalStatus | "ALL">("ALL");
  const [sourceType, setSourceType] = useState("DOCUMENT");
  const [sourceQuery, setSourceQuery] = useState("");
  const [selectedSource, setSelectedSource] = useState<SourceSearchItem | null>(null);
  const [relationship, setRelationship] = useState("EVIDENCES");
  const [evidenceStatus, setEvidenceStatus] = useState<EvidenceStatus>("LINKED");
  const [evidenceNotes, setEvidenceNotes] = useState("");
  const [testForm, setTestForm] = useState(DEFAULT_TEST);

  const overviewQuery = useQuery({
    queryKey: ["qms-excellence-overview", amoCode],
    queryFn: () => getQualityExcellenceOverview(amoCode),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
  });

  const controlsQuery = useQuery({
    queryKey: ["qms-excellence-controls", amoCode],
    queryFn: () => getAssuranceControls(amoCode),
    staleTime: 12_000,
  });

  const graphQuery = useQuery({
    queryKey: ["qms-excellence-graph", amoCode],
    queryFn: () => getAssuranceEvidenceGraph(amoCode),
    enabled: view === "evidence" || drawerMode === "evidence",
    staleTime: 10_000,
  });

  const sourceCatalogQuery = useQuery({
    queryKey: ["qms-excellence-source-catalog", amoCode],
    queryFn: () => getEvidenceSourceCatalog(amoCode),
    enabled: view === "evidence" || drawerMode === "evidence",
    staleTime: 60_000,
  });

  const sourceSearchQuery = useQuery({
    queryKey: ["qms-excellence-source-search", amoCode, sourceType, sourceQuery],
    queryFn: () => searchEvidenceSources(amoCode, sourceType, sourceQuery),
    enabled: drawerMode === "evidence" && sourceType.length > 1,
    staleTime: 5_000,
  });

  const eventsQuery = useQuery({
    queryKey: ["qms-excellence-events", amoCode],
    queryFn: () => getAssuranceEvents(amoCode),
    enabled: view === "evidence",
    staleTime: 5_000,
  });

  const managementPackQuery = useQuery({
    queryKey: ["qms-excellence-management-pack", amoCode],
    queryFn: () => getManagementReviewPack(amoCode),
    enabled: view === "readiness",
    staleTime: 10_000,
  });

  const insightsQuery = useQuery({
    queryKey: ["qms-excellence-insights", amoCode],
    queryFn: () => getQualityInsights(amoCode),
    enabled: view === "intelligence",
    staleTime: 10_000,
  });

  const invalidateAssurance = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-excellence-overview", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-excellence-controls", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-excellence-graph", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-excellence-events", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-excellence-management-pack", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-excellence-insights", amoCode] }),
    ]);
  };

  const createControlMutation = useMutation({
    mutationFn: () => createAssuranceControl(amoCode, {
      ...controlForm,
      control_code: controlForm.control_code.trim(),
      title: controlForm.title.trim(),
      description: controlForm.description?.trim() || null,
      control_objective: controlForm.control_objective?.trim() || null,
      test_method: controlForm.test_method?.trim() || null,
      framework: controlForm.framework.trim(),
      clause_reference: controlForm.clause_reference?.trim() || null,
      process_area: controlForm.process_area.trim(),
      evidence_expectation: controlForm.evidence_expectation?.trim() || null,
    }),
    onSuccess: async () => {
      setFeedback("Control created as a governed draft. Define evidence and submit it for approval.");
      setControlForm(DEFAULT_CONTROL);
      setDrawerMode(null);
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "The control could not be created.")),
  });

  const approvalMutation = useMutation({
    mutationFn: ({ control, status }: { control: AssuranceControl; status: Exclude<ControlApprovalStatus, "DRAFT"> }) =>
      decideControlApproval(amoCode, control.id, status),
    onSuccess: async (_, variables) => {
      setFeedback(`Control ${variables.status.replaceAll("_", " ").toLowerCase()} and recorded in its approval history.`);
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "The control approval decision could not be recorded.")),
  });

  const evidenceMutation = useMutation({
    mutationFn: () => {
      if (!selectedControl || !selectedSource) throw new Error("Select a control and an authoritative source record.");
      return linkAssuranceEvidence(amoCode, selectedControl.id, {
        source_type: sourceType,
        source_id: selectedSource.id,
        relationship,
        label: selectedSource.label,
        evidence_status: evidenceStatus,
        valid_until: selectedSource.valid_until,
        notes: evidenceNotes.trim() || null,
      });
    },
    onSuccess: async () => {
      setFeedback("Authoritative evidence linked and validated against the tenant source record.");
      setSelectedSource(null);
      setSourceQuery("");
      setEvidenceNotes("");
      setDrawerMode(null);
      setSelectedControl(null);
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "The evidence relationship could not be linked.")),
  });

  const testMutation = useMutation({
    mutationFn: () => {
      if (!selectedControl) throw new Error("Select a control to test.");
      return recordControlTest(amoCode, selectedControl.id, {
        result: testForm.result,
        method: testForm.method.trim() || selectedControl.test_method,
        notes: testForm.notes.trim() || null,
        next_test_due: testForm.next_test_due || null,
        evidence_summary: {
          verified_evidence: selectedControl.verified_evidence_count,
          total_evidence: selectedControl.evidence_count,
          control_version: selectedControl.version_no,
        },
      });
    },
    onSuccess: async () => {
      setFeedback("Operating-effectiveness test recorded. The next test date and readiness picture were updated.");
      setTestForm(DEFAULT_TEST);
      setDrawerMode(null);
      setSelectedControl(null);
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "The control test could not be recorded.")),
  });

  const reconcileMutation = useMutation({
    mutationFn: () => reconcileAssuranceEvidence(amoCode),
    onSuccess: async (result) => {
      setFeedback(`${result.reviewed} evidence relationships reviewed; ${result.changed} updated and ${result.events_processed} source events reconciled.`);
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "Evidence reconciliation failed.")),
  });

  const rebuildMutation = useMutation({
    mutationFn: () => rebuildQualityInsights(amoCode),
    onSuccess: async (result) => {
      setFeedback(`${result.generated} recommendation${result.generated === 1 ? "" : "s"} generated; ${result.skipped_existing} existing item${result.skipped_existing === 1 ? "" : "s"} retained.`);
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "Quality intelligence could not be rebuilt.")),
  });

  const decisionMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: InsightStatus }) => decideQualityInsight(amoCode, id, status),
    onSuccess: async () => {
      setFeedback("Human decision recorded in the quality intelligence register.");
      await invalidateAssurance();
    },
    onError: (error) => setFeedback(errorMessage(error, "The intelligence decision could not be recorded.")),
  });

  const setView = (next: HubView) => {
    navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality${next === "readiness" ? "" : `?hub=${next}`}`);
    setDrawerMode(null);
    setSelectedControl(null);
  };

  const openDrawer = (mode: Exclude<DrawerMode, null>, control?: AssuranceControl) => {
    setSelectedControl(control || null);
    setDrawerMode(mode);
    setSelectedSource(null);
    setSourceQuery("");
    setEvidenceNotes("");
    setTestForm({ ...DEFAULT_TEST, method: control?.test_method || "" });
  };

  const controls = useMemo(() => {
    const needle = controlQuery.trim().toLowerCase();
    return (controlsQuery.data?.items || []).filter((control) => {
      const matchesFilter = approvalFilter === "ALL" || control.approval_status === approvalFilter;
      const matchesQuery = !needle || [control.control_code, control.title, control.framework, control.process_area, control.clause_reference || ""].some((value) => value.toLowerCase().includes(needle));
      return matchesFilter && matchesQuery;
    });
  }, [approvalFilter, controlQuery, controlsQuery.data?.items]);

  const insightItems = useMemo(
    () => [...(insightsQuery.data?.items || [])].sort((a, b) => riskRank(a.risk_level) - riskRank(b.risk_level)),
    [insightsQuery.data?.items],
  );

  const overview = overviewQuery.data;
  const graph = graphQuery.data;
  const catalogue = sourceCatalogQuery.data?.items || [];
  const sourceItems = sourceSearchQuery.data?.items || [];
  const activeSource = catalogue.find((item) => item.source_type === sourceType);

  return (
    <main className="qew-page" aria-label="Quality continuous assurance control centre">
      <header className="qew-header">
        <div className="qew-header__identity">
          <p><ShieldCheck size={16} /> Continuous assurance</p>
          <h1>Quality Control Centre</h1>
          <span>Live control health across audits, CAPA, documents, competence, suppliers, calibration, risk, change and authority commitments.</span>
        </div>
        <div className="qew-header__actions">
          <span className="qew-freshness"><Activity size={14} /> {overview ? `Updated ${formatDateTime(overview.as_of)}` : "Loading live sources"}</span>
          <button type="button" onClick={() => void invalidateAssurance()}><RefreshCw size={16} /> Refresh</button>
          <button type="button" className="is-primary" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/week`)}><Plus size={16} /> Schedule audit</button>
        </div>
      </header>

      <nav className="qew-tabs" aria-label="Quality Control Centre views">
        <button type="button" className={view === "readiness" ? "is-active" : ""} onClick={() => setView("readiness")}><Activity size={16} /> Readiness</button>
        <button type="button" className={view === "controls" ? "is-active" : ""} onClick={() => setView("controls")}><Target size={16} /> Controls</button>
        <button type="button" className={view === "evidence" ? "is-active" : ""} onClick={() => setView("evidence")}><GitBranch size={16} /> Evidence & events</button>
        <button type="button" className={view === "intelligence" ? "is-active" : ""} onClick={() => setView("intelligence")}><BrainCircuit size={16} /> Intelligence</button>
      </nav>

      {feedback ? (
        <div className="qew-feedback" role="status"><CheckCircle2 size={17} /><span>{feedback}</span><button type="button" aria-label="Dismiss message" onClick={() => setFeedback(null)}><X size={15} /></button></div>
      ) : null}

      {overviewQuery.isLoading && !overview ? <div className="qew-loading"><LoaderCircle size={22} className="is-spinning" /> Building the live assurance picture…</div> : null}
      {overviewQuery.error ? <div className="qew-alert qew-alert--danger" role="alert"><AlertTriangle size={19} /><span>{errorMessage(overviewQuery.error, "The assurance overview could not be loaded.")}</span></div> : null}

      {view === "readiness" && overview ? (
        <div className="qew-readiness">
          <section className={`qew-posture qew-posture--${scoreTone(overview.readiness.score)}`}>
            <div className="qew-posture__copy">
              <p>Current assurance posture</p>
              <h2>{overview.readiness.band.replaceAll("_", " ")}</h2>
              <span>{overview.readiness.disclaimer}</span>
              <div className="qew-posture__actions">
                <button type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/findings/new`)}>New finding</button>
                <button type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/cars/new`)}>New CAR</button>
                <button type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/management-review/dashboard`)}>Management review <ArrowRight size={14} /></button>
              </div>
            </div>
            <ReadinessGauge score={overview.readiness.score} band={overview.readiness.band} />
          </section>

          <section className="qew-dimension-grid" aria-label="Assurance readiness dimensions">
            {overview.readiness.dimensions.map((dimension) => (
              <article key={dimension.id}>
                <span><strong>{dimension.label}</strong><em>{dimension.score}%</em></span>
                <div><i style={{ width: `${dimension.score}%` }} /></div>
                <small>{Math.round(dimension.weight * 100)}% weighting</small>
              </article>
            ))}
          </section>

          <div className="qew-two-column">
            <section className="qew-panel qew-panel--priority">
              <header><div><p>Action lane</p><h2>What requires intervention</h2></div><span>{overview.priority_queue.length} signals</span></header>
              {overview.priority_queue.length ? (
                <div className="qew-priority-list">
                  {overview.priority_queue.map((item) => (
                    <button key={item.id} type="button" onClick={() => navigate(item.path)}>
                      <span className="qew-priority-list__count">{item.count}</span>
                      <span><strong>{item.label}</strong><small>{item.why}</small></span>
                      <SeverityBadge level={item.severity} />
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              ) : <div className="qew-empty"><CheckCircle2 size={24} /><strong>No urgent assurance exposure</strong><span>Continue scheduled surveillance and operating-effectiveness testing.</span></div>}
            </section>

            <section className="qew-panel qew-panel--forecast">
              <header><div><p>Next 30 days</p><h2>Workload forecast</h2></div><StatusBadge status={overview.forecast.band} /></header>
              <strong className="qew-forecast-number">{overview.forecast.commitments_due_30_days}</strong>
              <p>{overview.forecast.explanation}</p>
              <div className="qew-forecast-metrics">
                {["audits_due_30", "cars_due_30", "controls_due", "supplier_approvals_due_30", "calibrations_due_30"].map((key) => (
                  <div key={key}><span>{labelFromKey(key)}</span><strong>{overview.metrics[key] || 0}</strong></div>
                ))}
              </div>
            </section>
          </div>

          <section className="qew-panel">
            <header><div><p>Cross-module health</p><h2>Authoritative operational indicators</h2></div><span>{overview.source_coverage?.available || 0} evidence source types</span></header>
            <div className="qew-health-grid">
              {[
                ["overdue_cars", "Overdue CARs", ClipboardCheck],
                ["expired_training", "Expired competence", UsersRound],
                ["expired_supplier_approvals", "Expired supplier approvals", BadgeCheck],
                ["overdue_calibrations", "Overdue calibration", TestTube2],
                ["critical_risks", "Critical risks", ShieldAlert],
                ["pending_changes", "Pending changes", History],
                ["open_regulator_findings", "Regulator findings", FileCheck2],
                ["invalid_evidence", "Invalid evidence", Link2],
              ].map(([key, label, Icon]) => {
                const MetricIcon = Icon as React.ComponentType<{ size?: number }>;
                return <article key={String(key)}><MetricIcon size={19} /><span><strong>{overview.metrics[String(key)] || 0}</strong><small>{String(label)}</small></span></article>;
              })}
            </div>
          </section>

          <section className="qew-panel qew-management-pack">
            <header><div><p>Management-review pack</p><h2>Decision-ready briefing</h2></div><FileCheck2 size={20} /></header>
            {managementPackQuery.isLoading ? <div className="qew-loading"><LoaderCircle size={18} className="is-spinning" /> Preparing management-review inputs…</div> : null}
            {managementPackQuery.data ? (
              <div className="qew-management-pack__body">
                <ol>{managementPackQuery.data.executive_summary.map((line) => <li key={line}>{line}</li>)}</ol>
                <div>
                  {managementPackQuery.data.decisions_required.slice(0, 4).map((decision) => (
                    <button type="button" key={decision.title} onClick={() => navigate(decision.path)}>
                      <span><strong>{decision.title}</strong><small>{decision.reason}</small></span><SeverityBadge level={decision.severity} /><ArrowRight size={15} />
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          {overview.warnings.length ? (
            <section className="qew-alert qew-alert--warning">
              <AlertTriangle size={19} />
              <div><strong>{overview.warnings.length} source check{overview.warnings.length === 1 ? "" : "s"} need attention</strong><span>Available records are shown, but missing sources are not treated as proof that no exposure exists.</span></div>
              <details><summary>Technical detail</summary><pre>{JSON.stringify(overview.warnings, null, 2)}</pre></details>
            </section>
          ) : null}
        </div>
      ) : null}

      {view === "controls" ? (
        <section className="qew-controls">
          <div className="qew-section-heading">
            <div><p>Control lifecycle</p><h2>Versioned control library</h2><span>Draft, approve, evidence, test, revise and retire durable controls without losing history.</span></div>
            {canManage ? <button type="button" className="is-primary" onClick={() => openDrawer("create")}><Plus size={15} /> New control</button> : <span className="qew-readonly"><LockKeyhole size={13} /> Read only</span>}
          </div>
          <div className="qew-toolbar">
            <label className="qew-search"><Search size={16} /><input value={controlQuery} onChange={(event) => setControlQuery(event.target.value)} placeholder="Search code, clause, framework or process" /></label>
            <label><span>Approval</span><select value={approvalFilter} onChange={(event) => setApprovalFilter(event.target.value as ControlApprovalStatus | "ALL")}><option value="ALL">All states</option><option value="DRAFT">Draft</option><option value="PENDING_APPROVAL">Pending approval</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="RETIRED">Retired</option></select></label>
            <span>{controls.length} of {controlsQuery.data?.total || 0} controls</span>
          </div>
          {controlsQuery.isLoading ? <div className="qew-loading"><LoaderCircle size={20} className="is-spinning" /> Loading control library…</div> : null}
          {!controlsQuery.isLoading && !controls.length ? <div className="qew-empty"><Target size={25} /><strong>No controls match this view</strong><span>Create the critical regulatory and exposition controls first.</span></div> : null}
          <div className="qew-control-table" role="table" aria-label="Continuous assurance controls">
            {controls.map((control) => (
              <article key={control.id} role="row">
                <div className="qew-control-table__identity"><span>{control.control_code} · v{control.version_no}</span><strong>{control.title}</strong><small>{control.framework}{control.clause_reference ? ` · ${control.clause_reference}` : ""}</small></div>
                <div><small>Process</small><strong>{control.process_area}</strong><span>{control.owner_user_id || "Owner not assigned"}</span></div>
                <div><small>Evidence</small><strong>{control.verified_evidence_count}/{control.evidence_count} verified</strong><span>{control.evidence_expectation || "Expectation not defined"}</span></div>
                <div><small>Test status</small><strong>{control.latest_test_result || "Not tested"}</strong><span>{formatDate(control.next_test_due)}</span></div>
                <div className="qew-control-table__status"><SeverityBadge level={control.criticality} /><StatusBadge status={control.approval_status} /><StatusBadge status={control.due_state} /></div>
                <div className="qew-control-table__actions">
                  {canManage ? <>
                    <button type="button" onClick={() => openDrawer("evidence", control)}><Link2 size={14} /> Evidence</button>
                    {control.approval_status === "APPROVED"
            ? <button type="button" onClick={() => openDrawer("test", control)}><TestTube2 size={14} /> Test</button>
            : <span className="qew-control-table__test-guard"><LockKeyhole size={13} /> Approve before testing</span>}
                    {control.approval_status === "DRAFT" || control.approval_status === "REJECTED" ? <button type="button" onClick={() => approvalMutation.mutate({ control, status: "PENDING_APPROVAL" })}>Submit</button> : null}
                    {control.approval_status === "PENDING_APPROVAL" ? <button type="button" className="is-primary" onClick={() => approvalMutation.mutate({ control, status: "APPROVED" })}><Check size={14} /> Approve</button> : null}
                  </> : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {view === "evidence" ? (
        <section className="qew-evidence">
          <div className="qew-section-heading">
            <div><p>Evidence provenance</p><h2>Validated evidence graph</h2><span>Every relationship resolves to an authoritative tenant record and refreshes when that source changes.</span></div>
            {canManage ? <button type="button" className="is-primary" onClick={() => reconcileMutation.mutate()} disabled={reconcileMutation.isPending}><RefreshCw size={15} className={reconcileMutation.isPending ? "is-spinning" : ""} /> Reconcile now</button> : null}
          </div>
          <div className="qew-summary-strip">
            <article><Target size={18} /><span><strong>{graph?.summary.controls || 0}</strong><small>Controls</small></span></article>
            <article><Link2 size={18} /><span><strong>{graph?.summary.relationships || 0}</strong><small>Relationships</small></span></article>
            <article><BadgeCheck size={18} /><span><strong>{graph?.summary.verified_relationships || 0}</strong><small>Verified</small></span></article>
            <article><ShieldAlert size={18} /><span><strong>{graph?.summary.invalid_relationships || 0}</strong><small>Invalid</small></span></article>
            <article><AlertTriangle size={18} /><span><strong>{graph?.summary.controls_without_evidence || 0}</strong><small>Unsupported controls</small></span></article>
          </div>

          <section className="qew-panel">
            <header><div><p>Connected sources</p><h2>Authoritative evidence catalogue</h2></div><span>{catalogue.filter((item) => item.available).length}/{catalogue.length} available</span></header>
            <div className="qew-source-catalogue">
              {catalogue.map((item) => <article key={item.source_type} className={item.available ? "" : "is-unavailable"}><span>{item.label}</span><strong>{item.source_type.replaceAll("_", " ")}</strong><small>{item.description}</small><em>{item.available ? "Connected" : "Source unavailable"}</em></article>)}
            </div>
          </section>

          <div className="qew-two-column qew-two-column--evidence">
            <section className="qew-panel">
              <header><div><p>Relationships</p><h2>Control-to-source traceability</h2></div><GitBranch size={20} /></header>
              {graphQuery.isLoading ? <div className="qew-loading"><LoaderCircle size={18} className="is-spinning" /> Loading evidence relationships…</div> : null}
              <div className="qew-evidence-list">
                {graph?.edges.map((edge) => {
                  const control = graph.nodes.find((node) => node.id === edge.from);
                  const source = graph.nodes.find((node) => node.id === edge.to);
                  return (
                    <article key={edge.id}>
                      <div><span>{control?.label || edge.from}</span><strong>{edge.relationship.replaceAll("_", " ")}</strong><span>{source?.label || edge.to}</span></div>
                      <div><StatusBadge status={edge.status} /><small>Synced {formatDateTime(edge.last_synced_at)}</small>{edge.source_route ? <button type="button" onClick={() => navigate(edge.source_route || "")}><ExternalLink size={13} /> Open source</button> : null}</div>
                      {edge.invalidation_reason ? <p><AlertTriangle size={14} /> {edge.invalidation_reason}</p> : null}
                    </article>
                  );
                })}
                {!graphQuery.isLoading && !graph?.edges.length ? <div className="qew-empty"><Link2 size={24} /><strong>No evidence relationships</strong><span>Open a control and select an authoritative source record.</span></div> : null}
              </div>
            </section>

            <section className="qew-panel">
              <header><div><p>Assurance event stream</p><h2>Recent authoritative changes</h2></div><Activity size={20} /></header>
              <div className="qew-event-list">
                {eventsQuery.data?.items.slice(0, 20).map((event) => (
                  <article key={event.id}><span className={`qew-event-type qew-event-type--${event.event_type.toLowerCase()}`}>{event.event_type}</span><div><strong>{event.source_type.replaceAll("_", " ")}</strong><small>{event.source_id} · {event.changed_fields.length ? event.changed_fields.join(", ") : "record lifecycle"}</small></div><StatusBadge status={event.processing_status} /><time>{formatDateTime(event.occurred_at)}</time></article>
                ))}
                {!eventsQuery.isLoading && !eventsQuery.data?.items.length ? <div className="qew-empty"><Activity size={23} /><strong>No assurance events yet</strong><span>Changes to connected QMS records will appear here automatically.</span></div> : null}
              </div>
            </section>
          </div>
        </section>
      ) : null}

      {view === "intelligence" ? (
        <section className="qew-intelligence">
          <div className="qew-section-heading">
            <div><p>Decision support</p><h2>Human-governed intelligence</h2><span>Recommendations can rank and explain exposure, but never alter regulated records without a named user decision.</span></div>
            {canManage ? <button type="button" className="is-primary" onClick={() => rebuildMutation.mutate()} disabled={rebuildMutation.isPending}><Sparkles size={15} /> Rebuild recommendations</button> : <span className="qew-readonly"><LockKeyhole size={13} /> Read only</span>}
          </div>
          <div className="qew-governance-banner"><Bot size={21} /><div><strong>Advisory by design</strong><span>Source fingerprints prevent duplicate recommendations. Acceptance, dismissal and implementation remain attributable human decisions.</span></div></div>
          {insightsQuery.isLoading ? <div className="qew-loading"><LoaderCircle size={20} className="is-spinning" /> Loading intelligence review…</div> : null}
          <div className="qew-insight-grid">
            {insightItems.map((insight) => (
              <article key={insight.id}>
                <header><div><small>{insight.insight_type.replaceAll("_", " ")}</small><h3>{insight.title}</h3></div><SeverityBadge level={insight.risk_level} /></header>
                <p>{insight.rationale}</p>
                {insight.recommendation ? <div className="qew-recommendation"><BrainCircuit size={16} /><span>{insight.recommendation}</span></div> : null}
                <footer><span><StatusBadge status={insight.status} /> {insight.created_by.replaceAll("_", " ")}</span>{canManage && insight.status === "PROPOSED" ? <span><button type="button" onClick={() => decisionMutation.mutate({ id: insight.id, status: "DISMISSED" })}>Dismiss</button><button type="button" className="is-primary" onClick={() => decisionMutation.mutate({ id: insight.id, status: "ACCEPTED" })}><Check size={14} /> Accept</button></span> : null}</footer>
              </article>
            ))}
            {!insightsQuery.isLoading && !insightItems.length ? <div className="qew-empty"><BrainCircuit size={25} /><strong>No recommendations awaiting review</strong><span>Rebuild the deterministic analysis after evidence reconciliation or major QMS changes.</span></div> : null}
          </div>
        </section>
      ) : null}

      {drawerMode ? (
        <div className="qew-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDrawerMode(null); }}>
          <aside className="qew-drawer" role="dialog" aria-modal="true" aria-label={drawerMode === "create" ? "Create assurance control" : drawerMode === "evidence" ? "Link authoritative evidence" : "Record control test"}>
            <header><div><p>{drawerMode === "create" ? "Control lifecycle" : drawerMode === "evidence" ? "Evidence provenance" : "Operating effectiveness"}</p><h2>{drawerMode === "create" ? "Create governed control" : drawerMode === "evidence" ? "Link authoritative evidence" : "Record control test"}</h2>{selectedControl ? <span>{selectedControl.control_code} · {selectedControl.title}</span> : null}</div><button type="button" aria-label="Close panel" onClick={() => setDrawerMode(null)}><X size={18} /></button></header>

            {drawerMode === "create" ? (
              <div className="qew-form">
                <div className="qew-form__split"><label><span>Control code</span><input value={controlForm.control_code} onChange={(event) => setControlForm((current) => ({ ...current, control_code: event.target.value }))} placeholder="145.A.65-C01" /></label><label><span>Criticality</span><select value={controlForm.criticality} onChange={(event) => setControlForm((current) => ({ ...current, criticality: event.target.value as ControlCriticality }))}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label></div>
                <label><span>Control title</span><input value={controlForm.title} onChange={(event) => setControlForm((current) => ({ ...current, title: event.target.value }))} placeholder="Independent quality audit programme" /></label>
                <div className="qew-form__split"><label><span>Framework</span><input value={controlForm.framework} onChange={(event) => setControlForm((current) => ({ ...current, framework: event.target.value }))} /></label><label><span>Clause</span><input value={controlForm.clause_reference || ""} onChange={(event) => setControlForm((current) => ({ ...current, clause_reference: event.target.value }))} placeholder="145.A.65(c)" /></label></div>
                <label><span>Process area</span><input value={controlForm.process_area} onChange={(event) => setControlForm((current) => ({ ...current, process_area: event.target.value }))} placeholder="Quality assurance" /></label>
                <label><span>Control objective</span><textarea value={controlForm.control_objective || ""} onChange={(event) => setControlForm((current) => ({ ...current, control_objective: event.target.value }))} placeholder="State the outcome that must remain effective." /></label>
                <label><span>Expected evidence</span><textarea value={controlForm.evidence_expectation || ""} onChange={(event) => setControlForm((current) => ({ ...current, evidence_expectation: event.target.value }))} placeholder="Approved programme, independent reports, finding closure and management follow-up." /></label>
                <label><span>Test method</span><textarea value={controlForm.test_method || ""} onChange={(event) => setControlForm((current) => ({ ...current, test_method: event.target.value }))} placeholder="Sample the programme, verify independence, inspect reports and trace overdue follow-up." /></label>
                <div className="qew-form__split"><label><span>Test frequency</span><select value={controlForm.test_frequency_days} onChange={(event) => setControlForm((current) => ({ ...current, test_frequency_days: Number(event.target.value) }))}><option value={30}>Monthly</option><option value={90}>Quarterly</option><option value={180}>Six monthly</option><option value={365}>Annual</option><option value={730}>Two yearly</option></select></label><label><span>First test due</span><input type="date" value={controlForm.next_test_due || ""} onChange={(event) => setControlForm((current) => ({ ...current, next_test_due: event.target.value || null }))} /></label></div>
                <label><span>Description</span><textarea value={controlForm.description || ""} onChange={(event) => setControlForm((current) => ({ ...current, description: event.target.value }))} /></label>
                <button type="button" className="is-primary qew-form__submit" disabled={!controlForm.control_code.trim() || !controlForm.title.trim() || !controlForm.process_area.trim() || createControlMutation.isPending} onClick={() => createControlMutation.mutate()}>{createControlMutation.isPending ? <LoaderCircle size={16} className="is-spinning" /> : <Check size={16} />} Create draft control</button>
              </div>
            ) : null}

            {drawerMode === "evidence" && selectedControl ? (
              <div className="qew-form qew-source-picker">
                <label><span>Authoritative source</span><select value={sourceType} onChange={(event) => { setSourceType(event.target.value); setSelectedSource(null); }}>{catalogue.filter((item) => item.available).map((item) => <option key={item.source_type} value={item.source_type}>{item.label}</option>)}</select><small>{activeSource?.description || "Select the governed record type."}</small></label>
                <label className="qew-search"><Search size={16} /><input value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} placeholder={`Search ${activeSource?.label.toLowerCase() || "records"}`} /></label>
                <div className="qew-source-results">
                  {sourceSearchQuery.isLoading ? <div className="qew-loading"><LoaderCircle size={17} className="is-spinning" /> Searching authoritative records…</div> : null}
                  {sourceItems.map((item) => <button key={item.id} type="button" className={selectedSource?.id === item.id ? "is-selected" : ""} onClick={() => setSelectedSource(item)}><span><strong>{item.label}</strong><small>{item.status || "No status"}{item.valid_until ? ` · valid to ${formatDate(item.valid_until)}` : ""}</small></span>{selectedSource?.id === item.id ? <CheckCircle2 size={17} /> : <ChevronRight size={16} />}</button>)}
                  {!sourceSearchQuery.isLoading && !sourceItems.length ? <div className="qew-empty"><Search size={22} /><strong>No source records found</strong><span>Change the search text or confirm that this QMS source is populated.</span></div> : null}
                </div>
                <div className="qew-form__split"><label><span>Relationship</span><select value={relationship} onChange={(event) => setRelationship(event.target.value)}><option value="EVIDENCES">Evidences</option><option value="TESTS">Tests</option><option value="IMPLEMENTS">Implements</option><option value="REMEDIATES">Remediates</option><option value="QUALIFIES">Qualifies</option></select></label><label><span>Initial state</span><select value={evidenceStatus} onChange={(event) => setEvidenceStatus(event.target.value as EvidenceStatus)}><option value="LINKED">Linked</option><option value="VERIFIED">Verified</option></select></label></div>
                <label><span>Verification note</span><textarea value={evidenceNotes} onChange={(event) => setEvidenceNotes(event.target.value)} placeholder="Why this record proves the control and what was checked." /></label>
                {selectedSource ? <div className="qew-selected-source"><BadgeCheck size={18} /><span><strong>{selectedSource.label}</strong><small>{selectedSource.route}</small></span></div> : null}
                <button type="button" className="is-primary qew-form__submit" disabled={!selectedSource || evidenceMutation.isPending} onClick={() => evidenceMutation.mutate()}>{evidenceMutation.isPending ? <LoaderCircle size={16} className="is-spinning" /> : <Link2 size={16} />} Validate and link evidence</button>
              </div>
            ) : null}

            {drawerMode === "test" && selectedControl ? (
              <div className="qew-form">
                <div className="qew-test-context"><Target size={18} /><span><strong>{selectedControl.verified_evidence_count}/{selectedControl.evidence_count} evidence records verified</strong><small>Control version {selectedControl.version_no} · approval {selectedControl.approval_status.replaceAll("_", " ").toLowerCase()}</small></span></div>
                <label><span>Test result</span><select value={testForm.result} onChange={(event) => setTestForm((current) => ({ ...current, result: event.target.value as ControlTestResult }))}><option value="PASS">Pass</option><option value="PARTIAL">Partial</option><option value="FAIL">Fail</option><option value="NOT_TESTED">Not tested</option></select></label>
                <label><span>Method applied</span><textarea value={testForm.method} onChange={(event) => setTestForm((current) => ({ ...current, method: event.target.value }))} placeholder="Describe the sample, records and operating-effectiveness checks." /></label>
                <label><span>Test conclusion</span><textarea value={testForm.notes} onChange={(event) => setTestForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Record observed effectiveness, exceptions and required follow-up." /></label>
                <label><span>Next test due</span><input type="date" value={testForm.next_test_due} onChange={(event) => setTestForm((current) => ({ ...current, next_test_due: event.target.value }))} /></label>
                <button type="button" className="is-primary qew-form__submit" disabled={testMutation.isPending} onClick={() => testMutation.mutate()}>{testMutation.isPending ? <LoaderCircle size={16} className="is-spinning" /> : <TestTube2 size={16} />} Record test result</button>
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}
    </main>
  );
};

export default QualityExcellenceCockpit;
