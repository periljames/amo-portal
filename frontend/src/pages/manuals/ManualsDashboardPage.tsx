import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getCachedUser } from "../../services/auth";
import {
  getMasterList,
  listManuals,
  previewDocxUpload,
  subscribeManualsUpdated,
  type ManualSummary,
  uploadDocxRevision,
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
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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

  const pendingTotal = useMemo(
    () => masterRows.reduce((acc, row) => acc + Number(row.pending_ack_count || 0), 0),
    [masterRows],
  );

  const handleSelectedFile = (selectedFile: File | null) => {
    setErrorMessage("");
    if (!selectedFile) {
      setFile(null);
      return;
    }
    const looksLikeDocx =
      selectedFile.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      selectedFile.name.toLowerCase().endsWith(".docx");
    if (!looksLikeDocx) {
      setFile(null);
      setErrorMessage("Please upload a DOCX file.");
      return;
    }
    setFile(selectedFile);
  };

  const inputClasses =
    "w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60";

  const handleSelectedFile = (selectedFile: File | null) => {
    setErrorMessage("");
    if (!selectedFile) {
      setFile(null);
      return;
    }
    const looksLikeDocx =
      selectedFile.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      selectedFile.name.toLowerCase().endsWith(".docx");
    if (!looksLikeDocx) {
      setFile(null);
      setErrorMessage("Please upload a DOCX file.");
      return;
    }
    setFile(selectedFile);
  };

  return (
    <ManualsPageLayout
      title="Manuals Dashboard"
      actions={
        <Link className="text-sm text-cyan-300 underline underline-offset-2" to={`${basePath}/master-list`}>
          View master list
        </Link>
      }
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4 text-sm">
          <div className="text-slate-400">Manuals</div>
          <div className="mt-1 text-2xl font-semibold text-slate-100">{manuals.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4 text-sm">
          <div className="text-slate-400">Pending acknowledgements</div>
          <div className="mt-1 text-2xl font-semibold text-slate-100">{pendingTotal}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4 text-sm">
          <div className="text-slate-400">Distribution owner</div>
          <div className="mt-1 font-semibold text-slate-100">Document Control Officer</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="space-y-4 rounded-lg border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold text-slate-100">Upload DOCX Revision</h2>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Manual Code</label>
              <input
                className={inputClasses}
                placeholder="e.g. MTM-001"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Manual Title</label>
              <input
                className={inputClasses}
                placeholder="Manual title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Issue Number</label>
              <input
                className={inputClasses}
                placeholder="Required"
                value={issue}
                onChange={(e) => setIssue(e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Revision Number</label>
              <input
                className={inputClasses}
                placeholder="e.g. 0"
                value={rev}
                onChange={(e) => setRev(e.target.value)}
                disabled={!canWrite}
              />
            </div>
            <div className="md:col-span-2">
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">DOCX File</label>
              <div
                className={`rounded-md border-2 border-dashed p-4 transition ${
                  isDragActive
                    ? "border-cyan-400/80 bg-cyan-400/10"
                    : "border-white/20 bg-slate-900/30"
                } ${!canWrite ? "opacity-60" : "cursor-pointer hover:border-cyan-300/60"}`}
                onClick={() => {
                  if (!canWrite) return;
                  fileInputRef.current?.click();
                }}
                onDragOver={(e) => {
                  if (!canWrite) return;
                  e.preventDefault();
                  setIsDragActive(true);
                }}
                onDragEnter={(e) => {
                  if (!canWrite) return;
                  e.preventDefault();
                  setIsDragActive(true);
                }}
                onDragLeave={(e) => {
                  if (!canWrite) return;
                  e.preventDefault();
                  setIsDragActive(false);
                }}
                onDrop={(e) => {
                  if (!canWrite) return;
                  e.preventDefault();
                  setIsDragActive(false);
                  handleSelectedFile(e.dataTransfer.files?.[0] || null);
                }}
              >
                <input
                  ref={fileInputRef}
                  className="hidden"
                  type="file"
                  accept=".docx"
                  onChange={(e) => handleSelectedFile(e.target.files?.[0] || null)}
                  disabled={!canWrite}
                />
                <p className="text-sm text-slate-100">
                  Drag and drop a DOCX here, or <span className="font-semibold text-cyan-300 underline">browse</span>
                </p>
                <p className="mt-1 text-xs text-slate-400">{file ? `Selected: ${file.name}` : "No file selected"}</p>
              </div>
            </div>
          </div>

          {!canWrite ? (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              Read-only role. Document Control Officer and quality roles can upload revisions.
            </p>
          ) : null}
          {errorMessage ? (
            <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{errorMessage}</p>
          ) : null}
          {statusMessage ? (
            <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{statusMessage}</p>
          ) : null}

          <div className="flex items-center gap-3">
            <button
              className="rounded-md bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
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

        <div className="rounded-lg border border-white/10 bg-white/[0.03] p-5">
          <h2 className="mb-3 text-lg font-semibold text-slate-100">Preview</h2>
          {previewLoading ? <p className="text-sm text-slate-300">Loading…</p> : null}
          {preview ? (
            <div className="space-y-2 text-sm">
              <div className="text-xs text-slate-400">{preview.filename}</div>
              <div className="font-medium text-slate-100">{preview.heading}</div>
              <div className="text-xs text-slate-400">{preview.paragraph_count} extracted lines</div>
              <div className="max-h-72 space-y-1 overflow-auto rounded-md border border-white/10 bg-slate-950/40 p-3 text-slate-200">
                {preview.sample.map((line, idx) => (
                  <p key={`${idx}-${line.slice(0, 8)}`}>{line}</p>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Select a DOCX file to show preview.</p>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
        <h2 className="mb-2 text-lg font-semibold text-slate-100">Manuals</h2>
        <ul className="space-y-2">
          {manuals.map((manual) => (
            <li
              key={manual.id}
              className="cursor-pointer rounded-md border border-white/10 bg-slate-950/30 p-3 transition hover:border-cyan-400/50 hover:bg-slate-950/50"
              onClick={() => navigate(`${basePath}/${manual.id}`)}
            >
              <div className="font-medium text-slate-100">
                {manual.code} — {manual.title}
              </div>
              <div className="text-xs text-slate-400">Status: {manual.status}</div>
            </li>
          ))}
        </ul>
      </div>
    </ManualsPageLayout>
  );
}
