import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getCachedUser } from "../../services/auth";
import {
  getMasterList,
  listManuals,
  previewDocxUpload,
  uploadDocxRevision,
  subscribeManualsUpdated,
  type ManualSummary,
} from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";

type PreviewPayload = {
  filename: string;
  heading: string;
  paragraph_count: number;
  sample: string[];
};

export default function ManualsDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useManualRouteContext();
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<any[]>([]);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [issue, setIssue] = useState("");
  const [rev, setRev] = useState("0");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");

  const user = getCachedUser();
  const role = String((user as any)?.role || "");
  const canWrite =
    !!user?.is_superuser ||
    !!user?.is_amo_admin ||
    role === "QUALITY_MANAGER" ||
    role === "QUALITY_INSPECTOR" ||
    role === "DOCUMENT_CONTROL_OFFICER" ||
    role !== "VIEW_ONLY";

  const refresh = () => {
    if (!tenant) return;
    listManuals(tenant).then(setManuals).catch(() => setManuals([]));
    getMasterList(tenant).then(setMasterRows).catch(() => setMasterRows([]));
  };

  useEffect(() => {
    refresh();
  }, [tenant]);


  useEffect(() => {
    if (!tenant) return;
    const unsubscribe = subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenant) refresh();
    });
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      unsubscribe();
      window.removeEventListener("focus", onFocus);
    };
  }, [tenant]);

  useEffect(() => {
    if (!tenant || !file) {
      setPreview(null);
      return;
    }
    setPreviewLoading(true);
    setErrorMessage("");
    previewDocxUpload(tenant, file)
      .then(setPreview)
      .catch((e) => setErrorMessage(e instanceof Error ? e.message : "Preview failed"))
      .finally(() => setPreviewLoading(false));
  }, [tenant, file]);

  const pendingTotal = useMemo(() => masterRows.reduce((acc, r) => acc + Number(r.pending_ack_count || 0), 0), [masterRows]);

  return (
    <ManualsPageLayout
      title="Manuals Dashboard"
      actions={<Link className="text-sm underline" to={`${basePath}/master-list`}>View master list</Link>}
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Manuals</div><div className="text-xl font-semibold">{manuals.length}</div></div>
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Pending acknowledgements</div><div className="text-xl font-semibold">{pendingTotal}</div></div>
        <div className="rounded border p-3 text-sm"><div className="text-slate-500">Distribution owner</div><div className="font-semibold">Document Control Officer</div></div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded border p-4 space-y-3">
          <h2 className="font-medium">Upload DOCX Revision</h2>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <label className="text-xs text-slate-500">Manual Code</label>
            <label className="text-xs text-slate-500">Manual Title</label>
            <input className="rounded border px-3 py-2 text-sm" placeholder="e.g. MTM-001" value={code} onChange={(e) => setCode(e.target.value)} disabled={!canWrite} />
            <input className="rounded border px-3 py-2 text-sm" placeholder="Manual title" value={title} onChange={(e) => setTitle(e.target.value)} disabled={!canWrite} />
            <label className="text-xs text-slate-500">Issue Number</label>
            <label className="text-xs text-slate-500">Revision Number</label>
            <input className="rounded border px-3 py-2 text-sm" placeholder="Required" value={issue} onChange={(e) => setIssue(e.target.value)} disabled={!canWrite} />
            <input className="rounded border px-3 py-2 text-sm" placeholder="e.g. 0" value={rev} onChange={(e) => setRev(e.target.value)} disabled={!canWrite} />
            <label className="text-xs text-slate-500 md:col-span-2">DOCX File</label>
            <input className="rounded border px-3 py-2 text-sm md:col-span-2" type="file" accept=".docx" onChange={(e) => setFile(e.target.files?.[0] || null)} disabled={!canWrite} />
          </div>

          {!canWrite ? <p className="text-xs text-amber-600">Read-only role. Document Control Officer and quality roles can upload revisions.</p> : null}
          {errorMessage ? <p className="text-xs text-rose-600">{errorMessage}</p> : null}
          {statusMessage ? <p className="text-xs text-emerald-600">{statusMessage}</p> : null}

          <div className="flex items-center gap-3">
            <button
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-60"
              disabled={uploading || !canWrite || !tenant || !code || !title || !issue || !rev || !file}
              onClick={async () => {
                if (!tenant || !file) return;
                setUploading(true);
                setErrorMessage("");
                setStatusMessage("");
                try {
                  const out = await uploadDocxRevision(tenant, {
                    code,
                    title,
                    issue_number: issue,
                    rev_number: rev,
                    manual_type: "GENERAL",
                    owner_role: "Document Control Officer",
                    file,
                  });
                  setStatusMessage("Upload successful. Opening manual revision…");
                  refresh();
                  navigate(`${basePath}/${out.manual_id}/rev/${out.revision_id}/read`);
                } catch (e) {
                  setErrorMessage(e instanceof Error ? e.message : "Upload failed");
                } finally {
                  setUploading(false);
                }
              }}
            >
              {uploading ? "Uploading..." : "Upload DOCX"}
            </button>
          </div>
        </div>

        <div className="rounded border p-4">
          {previewLoading ? <p className="text-sm">Loading…</p> : null}
          {preview ? (
            <div className="space-y-2 text-sm">
              <div className="text-xs text-slate-500">{preview.filename}</div>
              <div className="font-medium">{preview.heading}</div>
              <div className="text-xs text-slate-500">{preview.paragraph_count} extracted lines</div>
              <div className="max-h-72 overflow-auto rounded border p-2">
                {preview.sample.map((line, idx) => (
                  <p key={`${idx}-${line.slice(0, 8)}`} className="mb-1">{line}</p>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Select a DOCX file to show preview.</p>
          )}
        </div>
      </div>

      <div className="rounded border p-3">
        <h2 className="mb-2 font-medium">Manuals</h2>
        <ul className="space-y-2">
          {manuals.map((manual) => (
            <li
              key={manual.id}
              className="cursor-pointer rounded border p-3 transition hover:bg-slate-50"
              onClick={() => navigate(`${basePath}/${manual.id}`)}
            >
              <div className="font-medium">{manual.code} — {manual.title}</div>
              <div className="text-xs text-slate-600">Status: {manual.status}</div>
            </li>
          ))}
        </ul>
      </div>
    </ManualsPageLayout>
  );
}
