import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@tremor/react";
import { ShieldCheck } from "lucide-react";
import { useDropzone } from "react-dropzone";

import {
  getMasterList,
  getRevisionRead,
  getRevisionWorkflow,
  listManuals,
  listRevisions,
  previewDocxUpload,
  subscribeManualsUpdated,
  type ManualRevision,
  type ManualSummary,
  uploadDocxRevision,
} from "../../services/manuals";
import { getCachedUser } from "../../services/auth";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import DocumentReader from "./DocumentReader";
import "./manualsDashboard.css";

type PreviewPayload = {
  filename: string;
  heading: string;
  paragraph_count: number;
  sample: string[];
};

type MasterRow = { manual_id: string; pending_ack_count: number; current_status: string; current_revision: string | null };

const STORAGE_KEY = "manuals.dashboard.reader-state.v1";

function extractManualCode(source: string): string {
  const match = source.match(/[A-Z]{2,6}-\d{2,4}/i);
  return match ? match[0].toUpperCase() : "";
}

export function resolveNextRevisionId(previousRevisionId: string, revisions: Array<{ id: string }>): string {
  if (!revisions.length) return "";
  if (previousRevisionId && revisions.some((row) => row.id === previousRevisionId)) return previousRevisionId;
  return revisions[0].id;
}

function readPersistedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as { activeTab: number; mode: "section" | "continuous"; activeSectionId: string; scrollTop: number };
  } catch {
    return null;
  }
}

export default function ManualsDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useManualRouteContext();

  const persisted = typeof window !== "undefined" ? readPersistedState() : null;
  const [activeTab, setActiveTab] = useState(persisted?.activeTab ?? 0);

  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
  const [revisions, setRevisions] = useState<ManualRevision[]>([]);
  const [activeManualId, setActiveManualId] = useState<string>("");
  const [activeRevisionId, setActiveRevisionId] = useState<string>("");

  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [issue, setIssue] = useState("1");
  const [rev, setRev] = useState("0");
  const [changeLog, setChangeLog] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  const [readPayload, setReadPayload] = useState<any | null>(null);
  const [workflow, setWorkflow] = useState<any | null>(null);
  const [readerState, setReaderState] = useState({
    mode: persisted?.mode || ("section" as const),
    activeSectionId: persisted?.activeSectionId || "",
    scrollTop: persisted?.scrollTop || 0,
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ activeTab, ...readerState }));
  }, [activeTab, readerState]);

  const user = getCachedUser();
  const role = String((user as any)?.role || "");
  const canWrite = !!user?.is_superuser || !!user?.is_amo_admin || ["QUALITY_MANAGER", "QUALITY_INSPECTOR", "DOCUMENT_CONTROL_OFFICER"].includes(role);

  const refresh = () => {
    if (!tenant) return;
    listManuals(tenant)
      .then((data) => {
        setManuals(data);
        const first = data[0]?.id || "";
        setActiveManualId((prev) => prev || first);
      })
      .catch(() => setManuals([]));

    getMasterList(tenant)
      .then((rows) => setMasterRows(rows as MasterRow[]))
      .catch(() => setMasterRows([]));
  };

  useEffect(() => {
    refresh();
  }, [tenant]);

  useEffect(() => {
    if (!tenant) return;
    const unsubscribe = subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenant) refresh();
    });
    return unsubscribe;
  }, [tenant]);

  useEffect(() => {
    if (!tenant || !activeManualId) {
      setRevisions([]);
      return;
    }
    listRevisions(tenant, activeManualId)
      .then((rows) => {
        setRevisions(rows);
        setActiveRevisionId((prev) => resolveNextRevisionId(prev, rows));
      })
      .catch(() => setRevisions([]));
  }, [tenant, activeManualId]);

  useEffect(() => {
    if (!tenant || !activeManualId || !activeRevisionId) {
      setReadPayload(null);
      setWorkflow(null);
      return;
    }
    getRevisionRead(tenant, activeManualId, activeRevisionId).then(setReadPayload).catch(() => setReadPayload(null));
    getRevisionWorkflow(tenant, activeManualId, activeRevisionId).then(setWorkflow).catch(() => setWorkflow(null));
  }, [tenant, activeManualId, activeRevisionId]);

  const onFilePicked = async (picked: File | null) => {
    setErrorMessage("");
    setStatusMessage("");
    if (!tenant) {
      setErrorMessage("Tenant context is missing; cannot preview DOCX.");
      return;
    }
    if (!picked) {
      setFile(null);
      setPreview(null);
      return;
    }
    if (!picked.name.toLowerCase().endsWith(".docx")) {
      setErrorMessage("Please upload a DOCX file.");
      return;
    }

    setFile(picked);
    if (!code) setCode(extractManualCode(picked.name));

    setPreviewLoading(true);
    try {
      const payload = await previewDocxUpload(tenant, picked);
      setPreview(payload);
      if (!title) setTitle(payload.heading || picked.name.replace(/\.docx$/i, ""));
      if (!code) setCode(extractManualCode(`${picked.name} ${payload.heading}`));
      if (!issue) setIssue("1");
      setStatusMessage("Preview ready. You can upload this revision now.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Preview failed");
    } finally {
      setPreviewLoading(false);
    }
  };

  const dropzone = useDropzone({
    accept: {
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxFiles: 1,
    disabled: !canWrite,
    onDrop: (files) => void onFilePicked(files[0] || null),
  });

  const pendingAckCount = useMemo(() => {
    const row = masterRows.find((item) => item.manual_id === activeManualId);
    return Number(row?.pending_ack_count || 0);
  }, [activeManualId, masterRows]);

  const activeRevision = revisions.find((item) => item.id === activeRevisionId);

  const uploadNow = async () => {
    if (!tenant || !file) {
      setErrorMessage("Select and preview a DOCX file first.");
      return;
    }
    setUploading(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const out = await uploadDocxRevision(tenant, {
        code,
        title,
        issue_number: issue,
        rev_number: rev,
        file,
        manual_type: "GENERAL",
        owner_role: "Document Control Officer",
        change_log: changeLog,
      });
      setStatusMessage("Upload complete. Active revision updated.");
      setActiveManualId(out.manual_id);
      setActiveRevisionId(out.revision_id);
      setActiveTab(1);
      refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <ManualsPageLayout title="Manuals Document Management Reader" actions={<button className="manuals-link-btn" onClick={() => navigate(`${basePath}/master-list`)}>Master List</button>}>
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="manuals-top-tabs">
          <Tab>Library</Tab>
          <Tab>Reader</Tab>
          <Tab>Revision Management</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <div className="manuals-library-grid">
              <aside className="manuals-library-list">
                {manuals.map((manual) => (
                  <button key={manual.id} className={`manuals-manual-item ${manual.id === activeManualId ? "active" : ""}`} onClick={() => setActiveManualId(manual.id)}>
                    <strong>{manual.code}</strong>
                    <span>{manual.title}</span>
                  </button>
                ))}
              </aside>
              <section className="manuals-library-detail">
                <h3>Revision catalogue</h3>
                <div className="manuals-revision-list">
                  {revisions.map((item) => (
                    <button key={item.id} className={`manuals-revision-item ${item.id === activeRevisionId ? "active" : ""}`} onClick={() => setActiveRevisionId(item.id)}>
                      <span>Rev {item.rev_number}</span>
                      <small>{item.status_enum}</small>
                    </button>
                  ))}
                </div>
                <p className="manuals-muted">Pending acknowledgements: {pendingAckCount}</p>
              </section>
            </div>
          </TabPanel>

          <TabPanel>
            <DocumentReader
              file={file}
              fallbackSections={readPayload?.sections || []}
              fallbackBlocks={readPayload?.blocks || []}
              meta={{
                revisionNumber: activeRevision?.rev_number,
                issueNumber: activeRevision?.issue_number,
                approvalStatus: workflow?.status || activeRevision?.status_enum,
                pendingAcknowledgements: pendingAckCount,
              }}
              readerState={readerState}
              onReaderStateChange={(next) => setReaderState((prev) => ({ ...prev, ...next }))}
            />
          </TabPanel>

          <TabPanel>
            <div className="manuals-upload-grid">
              <div className="manuals-upload-panel">
                <h3 className="manuals-panel-title">Upload / Edit Revision</h3>
                <div className="manuals-form-grid">
                  <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Manual Code (e.g. MTM-001)" />
                  <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Manual Title" />
                  <input value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="Issue Number" />
                  <input value={rev} onChange={(e) => setRev(e.target.value)} placeholder="Revision Number" />
                </div>
                <textarea value={changeLog} onChange={(e) => setChangeLog(e.target.value)} rows={4} placeholder="Change log: summarize what changed in this revision" />

                <div {...dropzone.getRootProps()} className={`manuals-dropzone ${dropzone.isDragActive ? "drag" : ""}`}>
                  <input {...dropzone.getInputProps()} />
                  <p>{dropzone.isDragActive ? "Drop the DOCX file here" : "Drag & drop DOCX here, or click to browse"}</p>
                  <small>{file ? `Selected: ${file.name}` : "No file selected"}</small>
                </div>

                {errorMessage ? <p className="manuals-error">{errorMessage}</p> : null}
                {statusMessage ? <p className="manuals-success">{statusMessage}</p> : null}

                <button className="manuals-primary-btn" disabled={!canWrite || !file || !code || !title || !issue || !rev || uploading || previewLoading} onClick={uploadNow}>
                  {uploading ? "Uploading..." : "Upload Revision"}
                </button>
              </div>

              <div className="manuals-upload-preview">
                <h3 className="manuals-panel-title">Preview Metadata</h3>
                {previewLoading ? <p className="manuals-muted">Analyzing DOCX…</p> : null}
                {preview ? (
                  <>
                    <p><strong>Heading:</strong> {preview.heading}</p>
                    <p><strong>Paragraphs:</strong> {preview.paragraph_count}</p>
                    <ul>{preview.sample.slice(0, 6).map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}</ul>
                  </>
                ) : <p className="manuals-muted">Upload a DOCX to preview and auto-fill metadata.</p>}
                <p className="manuals-muted"><ShieldCheck size={14} style={{ display: "inline", marginRight: 6 }} />Section-first reader mode is optimized for very large manuals.</p>
              </div>
            </div>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </ManualsPageLayout>
  );
}
