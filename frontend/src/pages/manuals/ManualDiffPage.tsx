import { useEffect, useMemo, useState } from "react";
import { getRevisionDiff, getRevisionRead } from "../../services/manuals";
import { useManualRouteContext } from "./context";

export default function ManualDiffPage() {
  const { tenant, manualId, revId } = useManualRouteContext();
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [changes, setChanges] = useState<Array<{ index: number; text: string }>>([]);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (!tenant || !manualId || !revId) return;
    getRevisionDiff(tenant, manualId, revId).then((v) => setSummary(v.summary_json || {})).catch(() => setSummary({}));
    getRevisionRead(tenant, manualId, revId)
      .then((v) => setChanges(v.blocks.slice(0, Math.max(1, Number(v.blocks.length))).map((b, i) => ({ index: i + 1, text: b.text }))))
      .catch(() => setChanges([]));
  }, [tenant, manualId, revId]);

  const active = useMemo(() => changes[cursor] || null, [changes, cursor]);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Revision Diff</h1>
      <div className="rounded border p-3 text-sm">
        <div>Changed sections: {summary.changed_sections || 0}</div>
        <div>Changed blocks: {summary.changed_blocks || 0}</div>
        <div>Added: {summary.added || 0} · Removed: {summary.removed || 0}</div>
      </div>

      <div className="flex gap-2">
        <button className="rounded border px-3 py-1 text-sm" onClick={() => setCursor((c) => Math.max(0, c - 1))}>Previous change</button>
        <button className="rounded border px-3 py-1 text-sm" onClick={() => setCursor((c) => Math.min(changes.length - 1, c + 1))}>Next change</button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="rounded border p-3">
          <h2 className="font-medium mb-2">Baseline</h2>
          <p className="text-sm text-slate-500">Baseline revision comparison is scaffolded for block-level diff indexing.</p>
        </div>
        <div className="rounded border p-3">
          <h2 className="font-medium mb-2">Current change focus</h2>
          {active ? <p className="text-sm">#{active.index} — {active.text}</p> : <p className="text-sm text-slate-500">No changes indexed.</p>}
        </div>
      </div>
    </div>
  );
}
