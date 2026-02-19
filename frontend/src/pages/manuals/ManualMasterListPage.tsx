import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMasterList } from "../../services/manuals";
import { useManualRouteContext } from "./context";

export default function ManualMasterListPage() {
  const { tenant, basePath } = useManualRouteContext();
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    if (!tenant) return;
    getMasterList(tenant).then(setRows).catch(() => setRows([]));
  }, [tenant]);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Manual Master List</h1>
      <div className="overflow-x-auto rounded border">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="p-2">Code</th>
              <th className="p-2">Title</th>
              <th className="p-2">Current Revision</th>
              <th className="p-2">Status</th>
              <th className="p-2">Pending Acks</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.manual_id} className="border-t">
                <td className="p-2"><Link className="underline" to={`${basePath}/${row.manual_id}`}>{row.code}</Link></td>
                <td className="p-2">{row.title}</td>
                <td className="p-2">{row.current_revision || "-"}</td>
                <td className="p-2">{row.current_status}</td>
                <td className="p-2">{row.pending_ack_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
