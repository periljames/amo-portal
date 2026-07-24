import { useEffect, useMemo, useState, type ReactNode } from "react";
import { BookOpen, ClipboardList, FileClock, FileText, Search, Send, ShieldCheck } from "lucide-react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getMasterList, listManuals, type ManualSummary } from "../services/manuals";
import "./docControlPublicationsBridge.css";

type MasterRow = {
  manual_id: string;
  current_revision: string | null;
  current_status: string;
  current_issue_number?: string | null;
  source_type?: string | null;
  source_filename?: string | null;
  pending_ack_count: number;
};

type LayoutProps = {
  title: string;
  subtitle: string;
  actions?: ReactNode;
  children: ReactNode;
};

function useDocumentControlContext() {
  const params = useParams<{ amoCode?: string; department?: string; docId?: string }>();
  const amoCode = params.amoCode || "";
  return {
    amoCode,
    department: params.department || "document-control",
    docId: params.docId || "",
    basePath: `/maintenance/${amoCode}/document-control`,
    publicationsPath: `/maintenance/${amoCode}/publications`,
  };
}

function DocumentControlLayout({ title, subtitle, actions, children }: LayoutProps) {
  const { amoCode } = useDocumentControlContext();
  const content = (
    <div className="doc-publications-page">
      <header className="doc-publications-header">
        <div><p>Controlled records</p><h1>{title}</h1><span>{subtitle}</span></div>
        {actions ? <div>{actions}</div> : null}
      </header>
      {children}
    </div>
  );
  if (!amoCode) return content;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="document-control">{content}</DepartmentLayout>;
}

function usePublicationRegister(amoCode: string) {
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [master, setMaster] = useState<MasterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!amoCode) return;
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      listManuals(amoCode),
      getMasterList(amoCode),
    ])
      .then(([manualRows, masterRows]) => {
        if (!active) return;
        setManuals(manualRows);
        setMaster(masterRows as MasterRow[]);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "The controlled publication register could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [amoCode]);

  return { manuals, master, loading, error };
}

export function DocControlDashboardPage() {
  const navigate = useNavigate();
  const { amoCode, basePath, publicationsPath } = useDocumentControlContext();
  const { manuals, master, loading, error } = usePublicationRegister(amoCode);
  const published = manuals.filter((manual) => manual.current_published_rev_id).length;
  const pendingAcknowledgements = master.reduce((sum, row) => sum + Number(row.pending_ack_count || 0), 0);

  const modules = [
    { title: "Publications library", description: "Search and read the current controlled issue in the Kenya Law-style reader.", icon: BookOpen, path: publicationsPath, metric: `${manuals.length} titles` },
    { title: "Drafts", description: "Prepare revision content before review and approval.", icon: FileClock, path: `${basePath}/drafts`, metric: `${Math.max(0, manuals.length - published)} unpublished` },
    { title: "Change proposals", description: "Raise, assess, and route amendments from reader feedback.", icon: ClipboardList, path: `${basePath}/change-proposals`, metric: "Controlled workflow" },
    { title: "Distribution", description: "Record controlled issue distribution and acknowledgement.", icon: Send, path: `${basePath}/distribution`, metric: `${pendingAcknowledgements} pending acks` },
    { title: "Reviews", description: "Track scheduled reviews and continued applicability.", icon: ShieldCheck, path: `${basePath}/reviews`, metric: "Review programme" },
  ];

  return (
    <DocumentControlLayout
      title="Document Control"
      subtitle="The publication library and document-control workflows now resolve to the same records, revision IDs, source files, and reader."
      actions={<button type="button" className="doc-publications-primary" onClick={() => navigate(publicationsPath)}>Open Publications</button>}
    >
      <section className="doc-publications-metrics">
        <div><strong>{loading ? "—" : manuals.length}</strong><span>Controlled titles</span></div>
        <div><strong>{loading ? "—" : published}</strong><span>Published revisions</span></div>
        <div><strong>{loading ? "—" : pendingAcknowledgements}</strong><span>Pending acknowledgements</span></div>
      </section>
      {error ? <div className="doc-publications-error" role="alert">{error}</div> : null}
      <section className="doc-publications-modules">
        {modules.map((module) => {
          const Icon = module.icon;
          return (
            <button type="button" key={module.title} onClick={() => navigate(module.path)}>
              <Icon size={19} />
              <span><strong>{module.title}</strong><small>{module.description}</small></span>
              <em>{module.metric}</em>
            </button>
          );
        })}
      </section>
    </DocumentControlLayout>
  );
}

export function DocControlLibraryPage() {
  const navigate = useNavigate();
  const { amoCode, publicationsPath } = useDocumentControlContext();
  const { manuals, master, loading, error } = usePublicationRegister(amoCode);
  const [query, setQuery] = useState("");
  const masterById = useMemo(() => new Map(master.map((row) => [row.manual_id, row])), [master]);
  const rows = useMemo(() => manuals
    .map((manual) => ({ manual, record: masterById.get(manual.id) }))
    .filter(({ manual, record }) => {
      const needle = query.trim().toLowerCase();
      if (!needle) return true;
      return [manual.code, manual.title, manual.manual_type, record?.current_status, record?.source_filename]
        .some((value) => String(value || "").toLowerCase().includes(needle));
    }), [manuals, masterById, query]);

  const open = (manual: ManualSummary) => {
    if (manual.current_published_rev_id) {
      navigate(`${publicationsPath}/${manual.id}/rev/${manual.current_published_rev_id}/read`);
    } else {
      navigate(`${publicationsPath}/${manual.id}`);
    }
  };

  return (
    <DocumentControlLayout
      title="Controlled Publications Library"
      subtitle="This is the same live register used by Publications. Placeholder document-detail pages and revision-label routing have been removed."
      actions={<button type="button" className="doc-publications-primary" onClick={() => navigate(publicationsPath)}>Upload or manage publications</button>}
    >
      <div className="doc-publications-toolbar">
        <label><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, code, format, or status" /></label>
      </div>
      {error ? <div className="doc-publications-error" role="alert">{error}</div> : null}
      <div className="doc-publications-table-wrap">
        <table className="doc-publications-table">
          <thead><tr><th>Code</th><th>Publication</th><th>Current issue</th><th>Format</th><th>Status</th><th /></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={6}>Loading controlled records…</td></tr> : null}
            {!loading && rows.map(({ manual, record }) => (
              <tr key={manual.id}>
                <td><strong>{manual.code}</strong></td>
                <td><span>{manual.title}</span><small>{manual.manual_type}</small></td>
                <td><span>Issue {record?.current_issue_number || "—"}</span><small>Rev {record?.current_revision || "—"}</small></td>
                <td><span>{record?.source_type || "—"}</span><small>{record?.source_filename || "No source recorded"}</small></td>
                <td><span>{String(record?.current_status || manual.status || "Unknown").replaceAll("_", " ")}</span>{record?.pending_ack_count ? <small>{record.pending_ack_count} acknowledgements pending</small> : null}</td>
                <td><button type="button" onClick={() => open(manual)}><FileText size={15} /> {manual.current_published_rev_id ? "Read current issue" : "View record"}</button></td>
              </tr>
            ))}
            {!loading && !rows.length ? <tr><td colSpan={6}>No controlled publication matches the current search.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </DocumentControlLayout>
  );
}

export function DocControlDocumentDetailPage() {
  const { amoCode, docId, publicationsPath } = useDocumentControlContext();
  const { manuals, loading, error } = usePublicationRegister(amoCode);
  const manual = manuals.find((item) => item.id === docId || item.code.toLowerCase() === docId.toLowerCase());

  if (!loading && manual?.current_published_rev_id) {
    return <Navigate to={`${publicationsPath}/${manual.id}/rev/${manual.current_published_rev_id}/read`} replace />;
  }

  if (!loading && manual) {
    return <Navigate to={`${publicationsPath}/${manual.id}`} replace />;
  }

  return (
    <DocumentControlLayout title="Opening publication" subtitle="Resolving the document-control record against the Publications register.">
      <div className="doc-publications-resolving">
        {loading ? "Loading controlled publication…" : error || "No publication record matches this document identifier."}
      </div>
    </DocumentControlLayout>
  );
}
