import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  FileSearch,
  FolderTree,
  Link2,
  RefreshCw,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlDashboard,
  type DocumentControlDashboard,
} from "../../services/documentControl";
import {
  getDocumentControlMyWork,
  type DocumentControlMyWorkItem,
} from "../../services/documentControlHome";
import {
  getGovernanceDashboard,
  startGovernanceBackfill,
  type GovernanceDashboard,
} from "../../services/documentGovernance";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentGovernance.css";
import "./dmsHome.css";

const ICONS: Record<string, typeof ShieldCheck> = {
  ownership: ShieldCheck,
  relationships: Link2,
  indexing: FileSearch,
  structure: FolderTree,
  superseded: AlertTriangle,
};

const LIBRARY_QUEUE_FILTERS: Record<string, Record<string, string>> = {
  ownership: { unresolved_ownership: "true" },
  relationships: { unresolved_relationships: "true" },
  indexing: { indexing_status: "FAILED" },
  structure: { structure_status: "ORPHANED" },
  superseded: { superseded_referenced: "true" },
};

function formatDate(value?: string | null): string {
  if (!value) return "No due date";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function statusKind(value?: string | null): "success" | "warning" | "danger" | "info" | "neutral" {
  const status = String(value || "").toUpperCase();
  if (["CURRENT", "COMPLETED", "ACKNOWLEDGED", "READY"].includes(status)) return "success";
  if (["OVERDUE", "FAILED", "BLOCKED", "SUPERSEDED", "RECALLED"].includes(status)) return "danger";
  if (["PENDING", "DUE", "OPEN", "CORRECTIONS_REQUIRED"].includes(status)) return "warning";
  if (["ACTION", "TECHNICAL_REVIEW", "QUALITY_REVIEW", "ACCOUNTABLE_MANAGER_APPROVAL", "AUTHORITY_SUBMITTED", "NEW_REVISION_REQUIRES_ASSESSMENT", "DISPOSITION_REQUESTED", "APPROVED"].includes(status)) return "info";
  return "neutral";
}

function workKindLabel(kind: DocumentControlMyWorkItem["kind"]): string {
  if (kind === "CHANGE_REQUEST") return "Change request";
  if (kind === "PERIODIC_REVIEW") return "Periodic review";
  if (kind === "ACKNOWLEDGEMENT") return "Acknowledgement";
  if (kind === "AUTHORITY_ACTION") return "Authority response";
  if (kind === "TEMPORARY_REVISION") return "Temporary revision";
  if (kind === "CONTROLLED_COPY") return "Controlled copy custody";
  if (kind === "EXTERNAL_SOURCE_ACTION") return "External technical data";
  if (kind === "RETENTION_APPROVAL") return "Retention approval";
  if (kind === "RETENTION_EXECUTION") return "Retention execution";
  return "Workflow decision";
}

export default function DocumentGovernanceDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [dashboard, setDashboard] = useState<DocumentControlDashboard | null>(null);
  const [governance, setGovernance] = useState<GovernanceDashboard | null>(null);
  const [myWork, setMyWork] = useState<DocumentControlMyWorkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [secondaryError, setSecondaryError] = useState("");
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    setSecondaryError("");
    try {
      const summary = await getDocumentControlDashboard(tenant);
      setDashboard(summary);

      const requests: Array<Promise<unknown>> = [getDocumentControlMyWork(tenant)];
      if (summary.capabilities.control) requests.push(getGovernanceDashboard(tenant));
      const results = await Promise.allSettled(requests);

      const workResult = results[0];
      if (workResult.status === "fulfilled") {
        setMyWork((workResult.value as Awaited<ReturnType<typeof getDocumentControlMyWork>>).items);
      } else {
        setMyWork([]);
        setSecondaryError("Your assigned Document Control work could not be refreshed.");
      }

      if (summary.capabilities.control) {
        const governanceResult = results[1];
        if (governanceResult?.status === "fulfilled") {
          setGovernance(governanceResult.value as GovernanceDashboard);
        } else {
          setGovernance(null);
          setSecondaryError((current) => current || "Governance exceptions could not be refreshed.");
        }
      } else {
        setGovernance(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document Control Home could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => { void load(); }, [load]);

  const runDryCheck = async () => {
    if (!dashboard?.capabilities.control) return;
    setRunning(true);
    setSecondaryError("");
    try {
      await startGovernanceBackfill(tenant, true);
      const refreshed = await getGovernanceDashboard(tenant);
      setGovernance(refreshed);
    } catch (caught) {
      setSecondaryError(caught instanceof Error ? caught.message : "The governance reconciliation dry run failed.");
    } finally {
      setRunning(false);
    }
  };

  const exceptionQueues = useMemo(
    () => (governance?.queues || []).filter((queue) => queue.count > 0),
    [governance?.queues],
  );

  const dueSoon = useMemo(() => {
    if (!dashboard?.capabilities.control) return [];
    const metrics = dashboard.metrics as DocumentControlDashboard["metrics"] & Record<string, number>;
    return [
      { id: "acks", label: "Overdue acknowledgements", count: metrics.overdue_acknowledgements || 0, path: `${basePath}/distribution`, tone: "danger" as const },
      { id: "tr", label: "Temporary revisions expiring in 30 days", count: metrics.temporary_revisions_expiring_30_days || 0, path: `${basePath}/changes?view=temporary-revisions`, tone: "warning" as const },
      { id: "reviews", label: "Periodic reviews due in 60 days", count: metrics.reviews_due_60_days || 0, path: `${basePath}/compliance?view=reviews`, tone: "warning" as const },
      { id: "external", label: "External-source currency checks due", count: metrics.external_currency_checks_due || 0, path: `${basePath}/compliance?view=external-sources`, tone: "warning" as const },
    ].filter((item) => item.count > 0);
  }, [basePath, dashboard]);

  const canControl = Boolean(dashboard?.capabilities.control);

  return (
    <DocumentControlShell
      title="Document Control"
      eyebrow="HOME / MY WORK"
      subtitle="Your assigned document work, real control exceptions and time-bound obligations in one operational view."
      canControl={canControl}
      actions={<>
        <button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/library`)}><BookOpen size={15} /> Open library</button>
        <button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={15} /> Refresh</button>
      </>}
    >
      {loading ? <DocumentControlLoading label="Loading your Document Control work…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && dashboard ? (
        <div className="dms-home" data-testid="document-control-home">
          {secondaryError ? <div className="dms-home__notice" role="alert"><AlertTriangle size={16} /><span>{secondaryError}</span><button type="button" onClick={() => void load()}>Retry</button></div> : null}

          <DocumentControlSection
            title="My Work"
            description="Only obligations attributable to you through direct ownership, recipient/custody assignment, authority submission, confirmed document responsibility or a named retention/disposition role."
            actions={<span className="dms-home__count">{myWork.length}</span>}
          >
            {myWork.length ? (
              <div className="dc-table-wrap dms-home__table-wrap">
                <table className="dc-table dms-home__table">
                  <thead><tr><th>Task</th><th>Document</th><th>Status</th><th>Due</th><th>Action</th></tr></thead>
                  <tbody>{myWork.map((item) => (
                    <tr key={item.id}>
                      <td><strong>{item.title}</strong><small>{workKindLabel(item.kind)}</small></td>
                      <td><strong>{item.document.code}</strong><small>{item.document.title}</small></td>
                      <td><DocumentControlStatus status={item.priority || item.status} kind={statusKind(item.priority || item.status)} /><small>{item.status.replaceAll("_", " ")}</small></td>
                      <td>{formatDate(item.due_at)}</td>
                      <td><button type="button" className="dc-button dc-button--primary" onClick={() => navigate(item.target_path)}>{item.action_label} <ArrowRight size={14} /></button></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <DocumentControlEmpty icon={CheckCircle2} title="No assigned work needs action" message="There is currently no change, review, acknowledgement, workflow decision, authority response, temporary revision, external-source assessment, controlled-copy custody or retention/disposition action attributable to you." />}
          </DocumentControlSection>

          {canControl ? (
            <DocumentControlSection
              title="Exceptions"
              description="Control gaps that require resolution. Healthy zero-exception categories stay out of the way."
              actions={<button type="button" className="dc-button" onClick={() => void runDryCheck()} disabled={running}><RefreshCw size={14} /> {running ? "Checking…" : "Recheck governance"}</button>}
            >
              {exceptionQueues.length ? <div className="dms-home__exception-list">{exceptionQueues.map((queue) => {
                const Icon = ICONS[queue.id] || AlertTriangle;
                const params = new URLSearchParams({ ...queue.filter, ...(LIBRARY_QUEUE_FILTERS[queue.id] || {}) });
                return <button key={queue.id} type="button" onClick={() => navigate(`${basePath}/library?${params.toString()}`)}><Icon size={16} /><span><strong>{queue.count}</strong>{queue.label}</span><ArrowRight size={14} /></button>;
              })}</div> : <DocumentControlEmpty icon={CheckCircle2} title="No governance exceptions" message="Ownership, structure, relationship, indexing and superseded-reference queues currently have no unresolved items." />}
            </DocumentControlSection>
          ) : null}

          {canControl ? (
            <DocumentControlSection title="Due Soon" description="Time-bound Document Control obligations that already exist in the authoritative records.">
              {dueSoon.length ? <div className="dms-home__due-list">{dueSoon.map((item) => <button key={item.id} type="button" onClick={() => navigate(item.path)}><CalendarClock size={16} /><span>{item.label}</span><DocumentControlStatus status={String(item.count)} kind={item.tone} /><ArrowRight size={14} /></button>)}</div> : <DocumentControlEmpty icon={CheckCircle2} title="No due-soon exceptions" message="No overdue acknowledgement, near-expiry temporary revision, due review or external-source check is currently reported." />}
            </DocumentControlSection>
          ) : null}

          {canControl ? (
            <DocumentControlSection title="Recent Changes" description="Latest retained Document Control audit activity.">
              {dashboard.recent_activity.length ? <div className="dms-home__activity">{dashboard.recent_activity.slice(0, 8).map((item) => <article key={item.id}><span><strong>{item.action.replaceAll("_", " ")}</strong><small>{item.entity_type} · {item.entity_id}</small></span><time>{formatDate(item.at)}</time></article>)}</div> : <DocumentControlEmpty icon={CheckCircle2} title="No recent retained activity" message="No recent controlled action is available in the current audit window." />}
            </DocumentControlSection>
          ) : null}

          <DocumentControlSection title="Quick Actions" description="Go directly to the operational workspace for the job you need to do.">
            <div className="dms-home__quick-actions">
              <button type="button" onClick={() => navigate(`${basePath}/library`)}><BookOpen size={16} /><span><strong>Find or read a document</strong><small>Search the controlled library</small></span><ArrowRight size={14} /></button>
              {canControl ? <button type="button" onClick={() => navigate(`${basePath}/changes`)}><ClipboardList size={16} /><span><strong>Manage changes</strong><small>Revision and authority lifecycle</small></span><ArrowRight size={14} /></button> : null}
              {canControl ? <button type="button" onClick={() => navigate(`${basePath}/distribution`)}><Send size={16} /><span><strong>Control distribution</strong><small>Acknowledgements and copy custody</small></span><ArrowRight size={14} /></button> : null}
              {canControl ? <button type="button" onClick={() => navigate(`${basePath}/compliance`)}><ShieldCheck size={16} /><span><strong>Review compliance</strong><small>Reviews, currency and relationships</small></span><ArrowRight size={14} /></button> : null}
            </div>
          </DocumentControlSection>
        </div>
      ) : null}
    </DocumentControlShell>
  );
}
