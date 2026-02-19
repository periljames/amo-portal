import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getMasterList, listManuals, uploadDocxRevision, type ManualSummary } from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";

export default function ManualsDashboardPage() {
  const { tenant, basePath } = useManualRouteContext();
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<any[]>([]);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [rev, setRev] = useState("0");
  const [issue, setIssue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ manual_id: string; revision_id: string } | null>(null);

  const refresh = () => {
    if (!tenant) return;
    listManuals(tenant).then(setManuals).catch(() => setManuals([]));
    getMasterList(tenant).then(setMasterRows).catch(() => setMasterRows([]));
  };

  useEffect(() => {
    refresh();
  }, [tenant]);

  const pendingTotal = useMemo(() => masterRows.reduce((acc, r) => acc + Number(r.pending_ack_count || 0), 0), [masterRows]);

  return (
    <ManualsPageLayout
      title="Manuals Dashboard"
      actions={<Link className="text-sm underline" to={`${basePath}/master-list`}>View master list</Link>}
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Manuals</div><div className="text-xl font-semibold">{manuals.length}</div></div>
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Pending acknowledgements</div><div className="text-xl font-semibold">{pendingTotal}</div></div>
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Reader type</div><div className="font-semibold">Structured HTML reader</div></div>
      </div>

      <div className="rounded border p-3 space-y-3">
        <h2 className="font-medium">Upload DOCX Revision</h2>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <input className="rounded border px-2 py-1 text-sm" placeholder="Manual code (e.g. MTM-001)" value={code} onChange={(e) => setCode(e.target.value)} />
          <input className="rounded border px-2 py-1 text-sm" placeholder="Manual title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input className="rounded border px-2 py-1 text-sm" placeholder="Revision number" value={rev} onChange={(e) => setRev(e.target.value)} />
          <input className="rounded border px-2 py-1 text-sm" placeholder="Issue number (optional)" value={issue} onChange={(e) => setIssue(e.target.value)} />
          <input className="rounded border px-2 py-1 text-sm md:col-span-2" type="file" accept=".docx" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </div>
        <div className="flex items-center gap-3">
          <button
            className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-60"
            disabled={uploading || !tenant || !code || !title || !rev || !file}
            onClick={async () => {
              if (!tenant || !file) return;
              setUploading(true);
              try {
                const out = await uploadDocxRevision(tenant, {
                  code,
                  title,
                  rev_number: rev,
                  issue_number: issue || undefined,
                  manual_type: "GENERAL",
                  owner_role: "Library",
                  file,
                });
                setUploadResult(out);
                setCode("");
                setTitle("");
                setRev("0");
                setIssue("");
                setFile(null);
                refresh();
              } finally {
                setUploading(false);
              }
            }}
          >
            {uploading ? "Uploading..." : "Upload DOCX"}
          </button>
          {uploadResult ? (
            <Link className="text-sm underline" to={`${basePath}/${uploadResult.manual_id}/rev/${uploadResult.revision_id}/read`}>
              Open reader for uploaded revision
            </Link>
          ) : null}
        </div>
      </div>

      <div className="rounded border p-3">
        <h2 className="mb-2 font-medium">Manuals</h2>
        <ul className="space-y-2">
          {manuals.map((manual) => (
            <li key={manual.id} className="rounded border p-3">
              <Link className="font-medium underline" to={`${basePath}/${manual.id}`}>{manual.code} — {manual.title}</Link>
              <div className="text-xs text-slate-600">Status: {manual.status}</div>
            </li>
          ))}
        </ul>
      </div>
    </ManualsPageLayout>
  );
}
