import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileDiff,
  ListFilter,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getRevisionComparison,
  getRevisionDiff,
  getRevisionWorkflow,
  listRevisions,
  type ManualComparisonPayload,
  type ManualRevision,
  type ManualWorkflowPayload,
} from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import "./revisionIntelligence.css";

type DiffMode = "all" | "changes";
type ComparisonLine = ManualComparisonPayload["current_lines"][number];

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString([], { dateStyle: "medium" });
}

function displayRevision(revision?: ManualRevision | null): string {
  if (!revision) return "Not available";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.rev_number}`;
}

function changedOnly(lines: ComparisonLine[], mode: DiffMode): ComparisonLine[] {
  return mode === "changes" ? lines.filter((line) => line.kind !== "same") : lines;
}

export default function ManualDiffPage() {
  const { tenant, manualId, revId, basePath } = useManualRouteContext();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Record<string, number | string | null>>({});
  const [comparison, setComparison] = useState<ManualComparisonPayload | null>(null);
  const [workflow, setWorkflow] = useState<ManualWorkflowPayload | null>(null);
  const [revisions, setRevisions] = useState<ManualRevision[]>([]);
  const [mode, setMode] = useState<DiffMode>("changes");
  const [changeIndex, setChangeIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const changeRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    if (!tenant || !manualId || !revId) {
      setLoading(false);
      setError("The revision comparison route is incomplete.");
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      getRevisionDiff(tenant, manualId, revId).catch(() => null),
      getRevisionComparison(tenant, manualId, revId).catch(() => null),
      getRevisionWorkflow(tenant, manualId, revId).catch(() => null),
      listRevisions(tenant, manualId).catch(() => []),
    ]).then(([diff, nextComparison, nextWorkflow, nextRevisions]) => {
      if (!active) return;
      setSummary(diff?.summary_json || {});
      setComparison(nextComparison);
      setWorkflow(nextWorkflow);
      setRevisions(nextRevisions);
    }).catch((caught: unknown) => {
      if (!active) return;
      setError(caught instanceof Error ? caught.message : "Revision intelligence could not be loaded.");
    }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [manualId, revId, tenant]);

  const currentRevision = useMemo(
    () => revisions.find((revision) => revision.id === revId) || null,
    [revId, revisions],
  );
  const baselineRevision = useMemo(
    () => revisions.find((revision) => revision.id === comparison?.baseline_revision_id) || null,
    [comparison?.baseline_revision_id, revisions],
  );
  const currentLines = useMemo(() => comparison?.current_lines || [], [comparison]);
  const baselineLines = useMemo(() => comparison?.baseline_lines || [], [comparison]);
  const visibleCurrentLines = useMemo(() => changedOnly(currentLines, mode), [currentLines, mode]);
  const visibleBaselineLines = useMemo(() => changedOnly(baselineLines, mode), [baselineLines, mode]);
  const changeLines = useMemo(() => currentLines.filter((line) => line.kind !== "same"), [currentLines]);
  const changedPages = useMemo(
    () => [...new Set((workflow?.quick_review?.changed_pages || []).map((page) => String(page).trim()).filter(Boolean))],
    [workflow?.quick_review?.changed_pages],
  );
  const highlights = useMemo(
    () => (workflow?.quick_review?.change_highlights || []).filter(Boolean),
    [workflow?.quick_review?.change_highlights],
  );
  const comparisonAvailable = Boolean(comparison?.baseline_revision_id && (currentLines.length || baselineLines.length));

  useEffect(() => {
    setChangeIndex((current) => Math.min(current, Math.max(0, changeLines.length - 1)));
  }, [changeLines.length]);

  const moveChange = (direction: -1 | 1) => {
    if (!changeLines.length) return;
    const next = (changeIndex + direction + changeLines.length) % changeLines.length;
    setChangeIndex(next);
    const line = changeLines[next];
    const visibleIndex = visibleCurrentLines.findIndex((candidate) => candidate === line);
    if (visibleIndex >= 0) {
      window.requestAnimationFrame(() => changeRefs.current[visibleIndex]?.scrollIntoView({ behavior: "smooth", block: "center" }));
    }
  };

  const openReader = (page?: string) => {
    if (!manualId || !revId) return;
    const suffix = page && /^\d+$/.test(page) ? `?page=${encodeURIComponent(page)}` : "";
    navigate(`${basePath}/${manualId}/rev/${revId}/read${suffix}`);
  };

  return (
    <ManualsPageLayout title="Revision Intelligence" subtitle="Evidence-backed comparison of the selected controlled revision against its authoritative baseline.">
      <section className="revision-intelligence__toolbar manuals-pane" aria-label="Revision comparison controls">
        <button type="button" className="manuals-button" onClick={() => navigate(-1)}><ArrowLeft size={15} /> Back</button>
        <div className="revision-intelligence__mode" role="group" aria-label="Comparison visibility">
          <button type="button" className={mode === "changes" ? "active" : ""} onClick={() => setMode("changes")}><ListFilter size={14} /> Changed content only</button>
          <button type="button" className={mode === "all" ? "active" : ""} onClick={() => setMode("all")}><FileDiff size={14} /> All indexed content</button>
        </div>
        <div className="revision-intelligence__change-nav" role="group" aria-label="Change navigation">
          <button type="button" disabled={!changeLines.length} onClick={() => moveChange(-1)}><ChevronLeft size={14} /> Previous change</button>
          <span>{changeLines.length ? `Change ${changeIndex + 1} of ${changeLines.length}` : "No indexed text changes"}</span>
          <button type="button" disabled={!changeLines.length} onClick={() => moveChange(1)}>Next change <ChevronRight size={14} /></button>
        </div>
      </section>

      {loading ? <section className="manuals-pane revision-intelligence__state">Loading authoritative revision evidence…</section> : null}
      {error ? <section className="manuals-pane revision-intelligence__state revision-intelligence__state--error"><TriangleAlert size={18} /> {error}</section> : null}

      {!loading ? <>
        <section className="manuals-pane revision-intelligence__identity">
          <div>
            <small>Selected revision</small>
            <strong>{displayRevision(currentRevision)}</strong>
            <span>{formatDate(currentRevision?.effective_date)}</span>
          </div>
          <div>
            <small>Baseline</small>
            <strong>{displayRevision(baselineRevision)}</strong>
            <span>{baselineRevision ? formatDate(baselineRevision.effective_date) : "No baseline revision"}</span>
          </div>
          <div>
            <small>Authority reference</small>
            <strong>{workflow?.authority_approval_ref || "Not recorded"}</strong>
            <span>{workflow?.current_stage?.replaceAll("_", " ") || workflow?.status || "Workflow not loaded"}</span>
          </div>
          <button type="button" className="manuals-button manuals-button--primary" onClick={() => openReader()}><RotateCcw size={15} /> Open selected revision</button>
        </section>

        <section className="manuals-pane">
          <div className="manuals-summary-grid manuals-summary-grid--4">
            <div className="manuals-summary-card"><span>Changed sections</span><strong>{summary.changed_sections || workflow?.quick_review?.changed_sections || 0}</strong></div>
            <div className="manuals-summary-card"><span>Changed blocks</span><strong>{summary.changed_blocks || workflow?.quick_review?.changed_blocks || 0}</strong></div>
            <div className="manuals-summary-card"><span>Additions</span><strong>{summary.added || workflow?.quick_review?.added || 0}</strong></div>
            <div className="manuals-summary-card"><span>Deletions</span><strong>{summary.removed || workflow?.quick_review?.removed || 0}</strong></div>
          </div>
        </section>

        <section className="manuals-pane revision-intelligence__evidence">
          <div>
            <strong>Changed pages</strong>
            {changedPages.length ? <div className="revision-intelligence__pages">{changedPages.map((page) => <button type="button" key={page} onClick={() => openReader(page)}>Page {page}</button>)}</div> : <p>No reliable changed-page index is recorded for this revision.</p>}
          </div>
          <div>
            <strong>Revision highlights</strong>
            {highlights.length ? <ul>{highlights.map((highlight, index) => <li key={`${highlight}-${index}`}>{highlight}</li>)}</ul> : <p>No structured revision highlights are recorded.</p>}
          </div>
        </section>

        {!comparisonAvailable ? <section className="manuals-pane revision-intelligence__unavailable" role="status">
          <TriangleAlert size={18} />
          <div><strong>Automated comparison is unavailable for these revisions.</strong><p>The source material does not currently provide a reliable aligned baseline. Review the recorded revision metadata and source files instead of relying on a manufactured diff.</p></div>
        </section> : <section className="manuals-shell-grid manuals-shell-grid--comparison revision-intelligence__comparison" data-mode={mode}>
          <section className="manuals-pane">
            <div className="manuals-pane__header"><div><strong>Baseline · {displayRevision(baselineRevision)}</strong><p className="manuals-muted">Removed content is highlighted where indexed comparison is reliable.</p></div></div>
            <div className="manuals-diff-list">
              {visibleBaselineLines.map((line, index) => <div key={`${line.line}-${index}`} className={`manuals-diff-line manuals-diff-line--${line.kind}`}>{line.line}</div>)}
              {!visibleBaselineLines.length ? <div className="manuals-empty-cell">No baseline lines match the selected comparison mode.</div> : null}
            </div>
          </section>

          <section className="manuals-pane">
            <div className="manuals-pane__header"><div><strong>Selected revision · {displayRevision(currentRevision)}</strong><p className="manuals-muted">Added and modified indexed content remains traceable to this controlled revision.</p></div></div>
            <div className="manuals-diff-list">
              {visibleCurrentLines.map((line, index) => <div ref={(element) => { changeRefs.current[index] = element; }} key={`${line.line}-${index}`} className={`manuals-diff-line manuals-diff-line--${line.kind}`}>{line.line}</div>)}
              {!visibleCurrentLines.length ? <div className="manuals-empty-cell">No current-revision lines match the selected comparison mode.</div> : null}
            </div>
          </section>
        </section>}
      </> : null}
    </ManualsPageLayout>
  );
}