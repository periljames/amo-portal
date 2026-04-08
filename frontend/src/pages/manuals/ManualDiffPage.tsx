import { useEffect, useMemo, useState } from "react";
import { getRevisionComparison, getRevisionDiff, type ManualComparisonPayload } from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";

export default function ManualDiffPage() {
  const { tenant, manualId, revId } = useManualRouteContext();
  const [summary, setSummary] = useState<Record<string, number | string | null>>({});
  const [comparison, setComparison] = useState<ManualComparisonPayload | null>(null);

  useEffect(() => {
    if (!tenant || !manualId || !revId) return;
    getRevisionDiff(tenant, manualId, revId).then((value) => setSummary(value.summary_json || {})).catch(() => setSummary({}));
    getRevisionComparison(tenant, manualId, revId).then(setComparison).catch(() => setComparison(null));
  }, [tenant, manualId, revId]);

  const currentLines = useMemo(() => comparison?.current_lines || [], [comparison]);
  const baselineLines = useMemo(() => comparison?.baseline_lines || [], [comparison]);

  return (
    <ManualsPageLayout title="Revision Comparison" subtitle="Red-line view for Head of Quality sign-off before endorsement and KCAA submission.">
      <section className="manuals-pane">
        <div className="manuals-summary-grid manuals-summary-grid--4">
          <div className="manuals-summary-card"><span>Changed sections</span><strong>{summary.changed_sections || 0}</strong></div>
          <div className="manuals-summary-card"><span>Changed blocks</span><strong>{summary.changed_blocks || 0}</strong></div>
          <div className="manuals-summary-card"><span>Additions</span><strong>{summary.added || 0}</strong></div>
          <div className="manuals-summary-card"><span>Deletions</span><strong>{summary.removed || 0}</strong></div>
        </div>
      </section>

      <section className="manuals-shell-grid manuals-shell-grid--comparison">
        <section className="manuals-pane">
          <div className="manuals-pane__header">
            <div>
              <strong>Baseline</strong>
              <p className="manuals-muted">Revision {comparison?.baseline_revision_id || "None"}</p>
            </div>
          </div>
          <div className="manuals-diff-list">
            {baselineLines.map((line, index) => (
              <div key={`${line.line}-${index}`} className={`manuals-diff-line manuals-diff-line--${line.kind}`}>
                {line.line}
              </div>
            ))}
            {!baselineLines.length ? <div className="manuals-empty-cell">No baseline revision exists yet.</div> : null}
          </div>
        </section>

        <section className="manuals-pane">
          <div className="manuals-pane__header">
            <div>
              <strong>Current revision</strong>
              <p className="manuals-muted">Green additions. Red lines indicate removed legacy text.</p>
            </div>
          </div>
          <div className="manuals-diff-list">
            {currentLines.map((line, index) => (
              <div key={`${line.line}-${index}`} className={`manuals-diff-line manuals-diff-line--${line.kind}`}>
                {line.line}
              </div>
            ))}
            {!currentLines.length ? <div className="manuals-empty-cell">No diff lines have been indexed yet.</div> : null}
          </div>
        </section>
      </section>
    </ManualsPageLayout>
  );
}
