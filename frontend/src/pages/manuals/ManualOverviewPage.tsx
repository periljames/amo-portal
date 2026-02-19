import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getManual, listRevisions, type ManualRevision, type ManualSummary } from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";

export default function ManualOverviewPage() {
  const { tenant, manualId, basePath } = useManualRouteContext();
  const [manual, setManual] = useState<ManualSummary | null>(null);
  const [revisions, setRevisions] = useState<ManualRevision[]>([]);

  useEffect(() => {
    if (!tenant || !manualId) return;
    getManual(tenant, manualId).then(setManual).catch(() => setManual(null));
    listRevisions(tenant, manualId).then(setRevisions).catch(() => setRevisions([]));
  }, [tenant, manualId]);

  const currentPublished = useMemo(
    () => revisions.find((r) => r.id === manual?.current_published_rev_id) || revisions.find((r) => r.status_enum === "PUBLISHED") || null,
    [manual?.current_published_rev_id, revisions],
  );

  return (
    <ManualsPageLayout title="Manual Overview">
      <div className="rounded border p-3 text-sm">
        <div><b>Code:</b> {manual?.code ?? "-"}</div>
        <div><b>Title:</b> {manual?.title ?? "-"}</div>
        <div><b>Type:</b> {manual?.manual_type ?? "-"}</div>
        <div><b>Current Published Revision:</b> {currentPublished?.rev_number ?? "None"}</div>
      </div>

      <div className="rounded border p-3">
        <h2 className="font-medium mb-2">Revisions</h2>
        <div className="space-y-2">
          {revisions.map((rev) => (
            <div key={rev.id} className="rounded border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span>Rev {rev.rev_number} · {rev.status_enum}</span>
                <span className="text-xs text-slate-500">{rev.effective_date || "No effective date"}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <Link className="underline" to={`${basePath}/${manualId}/rev/${rev.id}/read`}>Reader</Link>
                <Link className="underline" to={`${basePath}/${manualId}/rev/${rev.id}/diff`}>Diff</Link>
                <Link className="underline" to={`${basePath}/${manualId}/rev/${rev.id}/workflow`}>Workflow</Link>
                <Link className="underline" to={`${basePath}/${manualId}/rev/${rev.id}/exports`}>Exports</Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </ManualsPageLayout>
  );
}
