import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, FileSearch, FolderTree, Link2, RefreshCw, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getGovernanceDashboard, startGovernanceBackfill, type GovernanceDashboard } from "../../services/documentGovernance";
import DocumentControlShell, { DocumentControlError, DocumentControlLoading } from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentGovernance.css";

const ICONS: Record<string, typeof ShieldCheck> = {
  ownership: ShieldCheck,
  relationships: Link2,
  indexing: FileSearch,
  structure: FolderTree,
  superseded: AlertTriangle,
};

// Keep the dashboard-to-library handoff explicit. These are public URL-backed
// work-queue contracts consumed by the integrated company library and should not
// depend on a backend label or implementation detail changing over time.
const LIBRARY_QUEUE_FILTERS: Record<string, Record<string, string>> = {
  ownership: { unresolved_ownership: "true" },
  relationships: { unresolved_relationships: "true" },
  indexing: { indexing_status: "FAILED" },
  structure: { structure_status: "ORPHANED" },
  superseded: { superseded_referenced: "true" },
};

export default function DocumentGovernanceDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [data, setData] = useState<GovernanceDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      setData(await getGovernanceDashboard(tenant));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The governance work queues could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => { void load(); }, [load]);

  const runDryCheck = async () => {
    setRunning(true);
    setError("");
    try {
      await startGovernanceBackfill(tenant, true);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The reconciliation dry run failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <DocumentControlShell
      title="Document Control work queues"
      eyebrow="CONTROLLED INFORMATION"
      subtitle="Resolve ownership, structure, relationship and indexing risks from records that can be reconciled to the controlled library."
      canControl
      actions={<button type="button" className="dc-button" onClick={() => void runDryCheck()} disabled={running}><RefreshCw size={15} /> {running ? "Checking…" : "Run reconciliation dry check"}</button>}
    >
      {loading ? <DocumentControlLoading label="Loading governed work queues…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && !error && data ? (
        <div className="dgov-dashboard" data-testid="document-governance-dashboard">
          <section className="dgov-queue-grid" aria-label="Actionable governance queues">
            {data.queues.map((queue) => {
              const Icon = ICONS[queue.id] || AlertTriangle;
              const params = new URLSearchParams({
                ...queue.filter,
                ...(LIBRARY_QUEUE_FILTERS[queue.id] || {}),
              });
              return (
                <button key={queue.id} type="button" className="dgov-queue" onClick={() => navigate(`${basePath}/library?${params.toString()}`)}>
                  <span className="dgov-queue__icon"><Icon size={19} /></span>
                  <span><strong>{queue.count}</strong><small>{queue.label}</small></span>
                  <ArrowRight size={17} aria-hidden="true" />
                </button>
              );
            })}
          </section>
          <section className="dgov-guidance">
            <div><ShieldCheck size={20} /><span><strong>Human authority remains final.</strong> Detected ownership and links stay proposed until an authorized controller confirms or rejects them.</span></div>
            <button type="button" className="dc-button dc-button--primary" onClick={() => navigate(`${basePath}/library`)}>Open controlled library <ArrowRight size={15} /></button>
          </section>
        </div>
      ) : null}
    </DocumentControlShell>
  );
}
