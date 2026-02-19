import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getMasterList, listManuals, type ManualSummary } from "../../services/manuals";
import { useManualRouteContext } from "./context";

export default function ManualsDashboardPage() {
  const { tenant, basePath } = useManualRouteContext();
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<any[]>([]);

  useEffect(() => {
    if (!tenant) return;
    listManuals(tenant).then(setManuals).catch(() => setManuals([]));
    getMasterList(tenant).then(setMasterRows).catch(() => setMasterRows([]));
  }, [tenant]);

  const pendingTotal = useMemo(() => masterRows.reduce((acc, r) => acc + Number(r.pending_ack_count || 0), 0), [masterRows]);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Manuals Dashboard</h1>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Manuals</div><div className="text-xl font-semibold">{manuals.length}</div></div>
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Pending acknowledgements</div><div className="text-xl font-semibold">{pendingTotal}</div></div>
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Reader type</div><div className="font-semibold">Structured HTML reader</div></div>
      </div>

      <div className="rounded border p-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-medium">Manuals</h2>
          <Link className="text-sm underline" to={`${basePath}/master-list`}>View master list</Link>
        </div>
        <ul className="space-y-2">
          {manuals.map((manual) => (
            <li key={manual.id} className="rounded border p-3">
              <Link className="font-medium underline" to={`${basePath}/${manual.id}`}>{manual.code} — {manual.title}</Link>
              <div className="text-xs text-slate-600">Status: {manual.status}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
