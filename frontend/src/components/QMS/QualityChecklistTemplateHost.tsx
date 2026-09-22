import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { BookOpen, CheckCircle2, Download, FilePlus2, History, ListChecks, PanelRightClose, Pencil, Plus, Search, ShieldAlert, Sparkles, Trash2, Upload, X } from "lucide-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

import { hasQmsRolePermission } from "../../app/routeGuards";
import ControlledDocumentUploadDialog from "../documentControl/ControlledDocumentUploadDialog";
import { deleteDocument } from "../../services/documentLifecycle";
import { listIntegratedLibrary, type IntegratedLibraryItem } from "../../services/documentLibrary";
import { fetchPublicationBlob } from "../../services/publications";
import {
  createChecklistRevision,
  createChecklistTemplate,
  generateChecklistDraft,
  getChecklistTemplate,
  issueChecklistRevision,
  listChecklistTemplates,
  retireChecklistTemplate,
  type ChecklistFindingTrigger,
  type ChecklistTemplateItem,
  type ChecklistAIDraft,
} from "../../services/qmsChecklistTemplates";
import { saveDownloadedFile } from "../../utils/downloads";
import "../../styles/qms-checklist-templates.css";

type Props = { amoCode?: string };
type TemplateDraft = { template_code: string; title: string; description: string; category: string; audit_kind: string };

const EMPTY_ITEM: ChecklistTemplateItem = {
  section: "General",
  category: "Compliance",
  checklist_ref: "",
  requirement_ref: "",
  regulatory_source_ref: "",
  manual_source_ref: "",
  prompt: "",
  expected_evidence: "",
  response_type: "COMPLIANT_NONCOMPLIANT_OBSERVATION_NA_NOT_VERIFIED",
  applicability: "ALL",
  mandatory: true,
  finding_trigger: "NONCOMPLIANT",
  sort_order: 10,
};

const FINDING_TRIGGER_OPTIONS: Array<{ value: ChecklistFindingTrigger; label: string }> = [
  { value: "NONE", label: "No governed trigger" },
  { value: "NONCOMPLIANT", label: "Noncompliant response" },
  { value: "OBSERVATION", label: "Observation response" },
  { value: "ADVERSE_RESPONSE", label: "Noncompliant or observation" },
];

const AUDIT_KIND_OPTIONS = ["INTERNAL", "EXTERNAL", "SUPPLIER", "REGULATORY", "PROCESS", "PRODUCT"];
const CATEGORY_OPTIONS = ["QUALITY_SYSTEM", "MAINTENANCE", "AIRWORTHINESS", "TRAINING", "FACILITIES", "TOOLS_EQUIPMENT", "SUPPLIER", "DOCUMENT_CONTROL", "SAFETY"];
const ITEM_SECTION_OPTIONS = ["General", "Governance", "Personnel", "Facilities", "Procedures", "Records", "Technical data", "Tools and equipment", "Safety", "Compliance"];
const ITEM_CATEGORY_OPTIONS = ["Compliance", "Airworthiness", "Maintenance", "Personnel", "Facilities", "Documentation", "Safety", "Quality system"];
const CRITERIA_TYPES = new Set(["MANUAL", "REGULATION", "POLICY", "PROCEDURE", "WORK_INSTRUCTION", "FORM", "CHECKLIST", "EXTERNAL_DOCUMENT"]);
const CRITERIA_EMPTY_COPY = "No readable controlled criteria yet. Publish or approve a manual/procedure/checklist in Document Control, or upload one here.";

function hasReadableCriteriaRevision(row: IntegratedLibraryItem): boolean {
  return Boolean(row.read_target?.revision_id || row.current_revision?.id);
}

function isCriteriaCandidate(row: IntegratedLibraryItem): boolean {
  return CRITERIA_TYPES.has(row.library.node_type) && hasReadableCriteriaRevision(row);
}

function criteriaRevisionLabel(row: IntegratedLibraryItem): string {
  if (row.current_revision) return `Rev ${row.current_revision.revision_number}`;
  if (row.read_target?.control_status === "CONTROLLED_DRAFT") return "Controlled draft";
  if (row.read_target?.label) return row.read_target.label;
  return row.read_target?.kind || "Readable revision";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Checklist governance action could not be completed.";
}

const QualityChecklistTemplateHost: React.FC<Props> = ({ amoCode = "" }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const libraryRoute = /\/(?:quality|qms)\/audits\/checklists(?:\/|$)/i.test(location.pathname);
  const pathnameAmo = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1];
  const resolvedAmo = amoCode || (pathnameAmo ? decodeURIComponent(pathnameAmo) : "");
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [templateId, setTemplateId] = useState("");
  const [templateDraft, setTemplateDraft] = useState<TemplateDraft>({ template_code: "", title: "", description: "", category: "", audit_kind: "INTERNAL" });
  const [revisionReason, setRevisionReason] = useState("Controlled checklist revision for audit use.");
  const [items, setItems] = useState<ChecklistTemplateItem[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [librarySearch, setLibrarySearch] = useState("");
  const [libraryType, setLibraryType] = useState<"ALL" | "CHECKLIST" | "FORM">("ALL");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [selectedCriteria, setSelectedCriteria] = useState<IntegratedLibraryItem[]>([]);
  const [criteriaSearch, setCriteriaSearch] = useState("");
  const [aiTitle, setAiTitle] = useState("");
  const [aiKind, setAiKind] = useState("INTERNAL");
  const [aiFocus, setAiFocus] = useState("");
  const [aiItemCount, setAiItemCount] = useState(20);
  const [aiResult, setAiResult] = useState<ChecklistAIDraft | null>(null);

  useEffect(() => {
    if (!aiOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAiOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [aiOpen]);

  const templatesQuery = useQuery({
    queryKey: ["qms-checklist-templates", resolvedAmo],
    queryFn: ({ signal }) => listChecklistTemplates(resolvedAmo, signal),
    enabled: Boolean(libraryRoute && resolvedAmo),
  });
  const dmsChecklistQuery = useQuery({
    queryKey: ["qms-dms-checklist-library", resolvedAmo],
    queryFn: async () => {
      const [checklists, forms] = await Promise.all([
        listIntegratedLibrary(resolvedAmo, { nodeType: "CHECKLIST", status: "ACTIVE", perPage: 100 }),
        listIntegratedLibrary(resolvedAmo, { nodeType: "FORM", status: "ACTIVE", perPage: 100 }),
      ]);
      const rows = [...checklists.items, ...forms.items];
      return [...new Map(rows.map((row) => [row.id, row])).values()];
    },
    enabled: Boolean(libraryRoute && resolvedAmo),
    staleTime: 10_000,
  });
  const criteriaQuery = useQuery({
    queryKey: ["qms-ai-criteria-library", resolvedAmo],
    queryFn: () => listIntegratedLibrary(resolvedAmo, { status: "ACTIVE", perPage: 100, sort: "type" }),
    enabled: Boolean(libraryRoute && aiOpen && resolvedAmo),
    staleTime: 10_000,
  });
  const templates = templatesQuery.data?.items || [];
  const selectedTemplateId = templateId;
  const templateQuery = useQuery({
    queryKey: ["qms-checklist-template", resolvedAmo, selectedTemplateId],
    queryFn: ({ signal }) => getChecklistTemplate(resolvedAmo, selectedTemplateId, signal),
    enabled: Boolean(libraryRoute && selectedTemplateId),
  });

  const revisions = useMemo(() => templateQuery.data?.revisions || [], [templateQuery.data?.revisions]);
  const latestDraft = revisions.find((row) => row.status === "DRAFT");

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-checklist-templates", resolvedAmo] }),
      queryClient.invalidateQueries({ queryKey: ["qms-checklist-template", resolvedAmo, selectedTemplateId] }),
    ]);
  };

  const openBlankEditor = () => {
    setTemplateId("");
    setCreatingTemplate(true);
    setItems([]);
    setTemplateDraft({ template_code: "", title: "", description: "", category: "", audit_kind: "INTERNAL" });
    setEditorOpen(true);
    setAiOpen(false);
    setSuccess("");
    setError("");
  };

  const openExistingEditor = (id: string) => {
    setTemplateId(id);
    setCreatingTemplate(false);
    setItems([{ ...EMPTY_ITEM }]);
    setEditorOpen(true);
    setAiOpen(false);
    setSuccess("");
    setError("");
  };

  const createTemplateMutation = useMutation({
    mutationFn: () => createChecklistTemplate(resolvedAmo, templateDraft),
    onSuccess: async (row) => {
      setTemplateId(row.id);
      setCreatingTemplate(false);
      setItems([{ ...EMPTY_ITEM }]);
      setTemplateDraft({ template_code: "", title: "", description: "", category: "", audit_kind: "INTERNAL" });
      setSuccess(`Template ${row.template_code} created.`);
      setError("");
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });
  const createRevisionMutation = useMutation({
    mutationFn: () => createChecklistRevision(resolvedAmo, selectedTemplateId, { reason: revisionReason, items }),
    onSuccess: async (row) => {
      setSuccess(`Draft revision ${row.revision_no} created with ${row.items.length} checklist item(s).`);
      setError("");
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });
  const issueMutation = useMutation({
    mutationFn: () => latestDraft ? issueChecklistRevision(resolvedAmo, selectedTemplateId, latestDraft.id, revisionReason) : Promise.reject(new Error("No draft revision is available to issue.")),
    onSuccess: async (row) => {
      setSuccess(`Checklist revision ${row.revision_no} issued.`);
      setError("");
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });
  const generateMutation = useMutation({
    mutationFn: () => generateChecklistDraft(resolvedAmo, {
      source_document_ids: selectedCriteria.map((row) => row.id),
      title: aiTitle.trim(),
      audit_kind: aiKind,
      focus: aiFocus.trim() || undefined,
      max_items: aiItemCount,
    }),
    onSuccess: (result) => {
      setAiResult(result);
      setError("");
      setSuccess(`${result.draft.items.length} editable checklist items drafted with ${result.model}.`);
    },
    onError: (cause) => setError(errorMessage(cause)),
  });
  const saveAiDraftMutation = useMutation({
    mutationFn: async () => {
      if (!aiResult) throw new Error("Generate a checklist draft first.");
      const created = await createChecklistTemplate(resolvedAmo, {
        template_code: `AI-${Date.now().toString(36).toUpperCase()}`,
        title: aiResult.draft.title,
        description: aiResult.draft.description,
        category: aiResult.draft.category,
        audit_kind: aiResult.draft.audit_kind,
      });
      const revision = await createChecklistRevision(resolvedAmo, created.id, {
        reason: "AI-assisted draft created from current controlled DMS criteria for auditor review.",
        items: aiResult.draft.items,
        source_references: aiResult.draft.source_references,
      });
      return { created, revision };
    },
    onSuccess: async ({ created, revision }) => {
      setTemplateId(created.id);
      setCreatingTemplate(false);
      setItems(aiResult?.draft.items?.length ? aiResult.draft.items.map((item) => ({ ...item })) : [{ ...EMPTY_ITEM }]);
      setEditorOpen(true);
      setAiOpen(false);
      setSuccess(`${created.template_code} draft revision ${revision.revision_no} saved for auditor review.`);
      await refresh();
    },
    onError: (cause) => setError(errorMessage(cause)),
  });
  const deleteDmsMutation = useMutation({
    mutationFn: (row: IntegratedLibraryItem) => deleteDocument(resolvedAmo, row.id),
    onSuccess: async (_, row) => {
      setSuccess(`Deleted draft document ${row.code}.`);
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-dms-checklist-library", resolvedAmo] }),
        queryClient.invalidateQueries({ queryKey: ["qms-ai-criteria-library", resolvedAmo] }),
      ]);
    },
    onError: (cause) => setError(errorMessage(cause)),
  });
  const retireTemplateMutation = useMutation({
    mutationFn: (row: (typeof templates)[number]) => retireChecklistTemplate(resolvedAmo, row.id),
    onSuccess: async (_, row) => {
      if (templateId === row.id) {
        setTemplateId("");
        setEditorOpen(false);
        setCreatingTemplate(false);
      }
      setSuccess(`Retired template ${row.template_code}.`);
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["qms-checklist-templates", resolvedAmo] });
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  const dmsRows = useMemo(() => {
    const needle = librarySearch.trim().toLowerCase();
    return (dmsChecklistQuery.data || []).filter((row) => {
      if (libraryType !== "ALL" && row.library.node_type !== libraryType) return false;
      if (!needle) return true;
      return [row.code, row.title, row.library.structure_path, row.profile.owner_department]
        .filter(Boolean).join(" ").toLowerCase().includes(needle);
    });
  }, [dmsChecklistQuery.data, librarySearch, libraryType]);
  const criteriaRows = useMemo(() => {
    const fromCriteria = (criteriaQuery.data?.items || []).filter(isCriteriaCandidate);
    const source = fromCriteria.length
      ? fromCriteria
      : (dmsChecklistQuery.data || []).filter(isCriteriaCandidate);
    const needle = criteriaSearch.trim().toLowerCase();
    if (!needle) return source;
    return source.filter((row) => (
      [row.code, row.title, row.library.node_type, row.read_target?.control_status, row.read_target?.label]
        .filter(Boolean).join(" ").toLowerCase().includes(needle)
    ));
  }, [criteriaQuery.data?.items, criteriaSearch, dmsChecklistQuery.data]);

  const toggleCriteria = useCallback((row: IntegratedLibraryItem) => {
    setSelectedCriteria((current) => (
      current.some((item) => item.id === row.id)
        ? current.filter((item) => item.id !== row.id)
        : [...current, row]
    ));
  }, []);

  const confirmDeleteDms = useCallback((row: IntegratedLibraryItem) => {
    if (!window.confirm(`Permanently delete draft document ${row.code}? Only never-published drafts can be deleted.`)) return;
    deleteDmsMutation.mutate(row);
  }, [deleteDmsMutation]);

  const confirmRetireTemplate = useCallback((row: (typeof templates)[number]) => {
    if (!window.confirm(`Retire structured template ${row.template_code}? It will no longer appear in the active library.`)) return;
    retireTemplateMutation.mutate(row);
  }, [retireTemplateMutation]);

  const downloadDmsSource = useCallback(async (row: IntegratedLibraryItem) => {
    const revisionId = row.read_target.revision_id || row.current_revision?.id;
    if (!revisionId) return;
    try {
      const downloaded = await fetchPublicationBlob(`/manuals/t/${encodeURIComponent(resolvedAmo.toLowerCase())}/${encodeURIComponent(row.id)}/rev/${encodeURIComponent(revisionId)}/source`);
      saveDownloadedFile(downloaded.blob, downloaded.filename || row.current_revision?.source_filename || `${row.code}-current`);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [resolvedAmo]);

  const dmsColumns = useMemo<ColDef<IntegratedLibraryItem>[]>(() => [
    {
      headerName: "Controlled document",
      flex: 2.2,
      minWidth: 240,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? (
        <div className="qms-checklist-library__stack">
          <strong>{data.code}</strong>
          <span>{data.title}</span>
        </div>
      ) : null,
    },
    {
      headerName: "Current control",
      flex: 1,
      minWidth: 140,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__stack"><strong>{data.current_revision ? `Rev ${data.current_revision.revision_number}` : "No issued revision"}</strong><span>{data.read_target.control_status || data.workflow?.state || data.status}</span></div> : null,
    },
    { headerName: "Owner", valueGetter: ({ data }) => data?.profile.owner_department || data?.owner_role || "—", flex: 0.85, minWidth: 115 },
    {
      headerName: "Actions",
      pinned: "right",
      width: canManage ? 168 : 132,
      minWidth: canManage ? 168 : 132,
      maxWidth: canManage ? 168 : 132,
      sortable: false,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__actions">
        <button type="button" title="Read current revision" aria-label={`Read ${data.code}`} disabled={!data.read_target.revision_id} onClick={() => data.read_target.revision_id && navigate(`/maintenance/${encodeURIComponent(resolvedAmo)}/publications/${encodeURIComponent(data.id)}/rev/${encodeURIComponent(data.read_target.revision_id)}/read`)}><BookOpen size={15} /></button>
        <button type="button" title="Download source" aria-label={`Download ${data.code}`} disabled={!data.read_target.revision_id} onClick={() => void downloadDmsSource(data)}><Download size={15} /></button>
        <button type="button" title="Open Document Control workspace" aria-label={`Modify ${data.code}`} onClick={() => navigate(`/maintenance/${encodeURIComponent(resolvedAmo)}/document-control/library/${encodeURIComponent(data.id)}`)}><Pencil size={15} /></button>
        {canManage ? <button type="button" className="is-danger" title="Delete draft document" aria-label={`Delete ${data.code}`} disabled={deleteDmsMutation.isPending} onClick={() => confirmDeleteDms(data)}><Trash2 size={15} /></button> : null}
      </div> : null,
    },
  ], [canManage, confirmDeleteDms, deleteDmsMutation.isPending, downloadDmsSource, navigate, resolvedAmo]);
  const templateColumns = useMemo<ColDef<(typeof templates)[number]>[]>(() => [
    { headerName: "Structured template", field: "template_code", flex: 0.75, minWidth: 130 },
    { headerName: "Title", field: "title", flex: 1.8, minWidth: 210 },
    { headerName: "Audit / category", flex: 1, minWidth: 150, valueGetter: ({ data }) => `${data?.audit_kind || "ALL"} · ${String(data?.category || "GENERAL").replaceAll("_", " ")}` },
    { headerName: "Status", field: "status", flex: 0.6, minWidth: 90 },
    {
      headerName: "Actions",
      pinned: "right",
      width: canManage ? 92 : 50,
      minWidth: canManage ? 92 : 50,
      maxWidth: canManage ? 92 : 50,
      sortable: false,
      cellRenderer: ({ data }: ICellRendererParams<(typeof templates)[number]>) => (
        data && canManage
          ? <div className="qms-checklist-library__actions">
            <button className="qms-checklist-library__icon" type="button" title="Edit template" aria-label={`Edit ${data.template_code}`} onClick={() => openExistingEditor(data.id)}><Pencil size={15} /></button>
            <button type="button" className="is-danger" title="Retire template" aria-label={`Retire ${data.template_code}`} disabled={retireTemplateMutation.isPending} onClick={() => confirmRetireTemplate(data)}><Trash2 size={15} /></button>
          </div>
          : null
      ),
    },
  ], [canManage, confirmRetireTemplate, retireTemplateMutation.isPending]);

  if (!libraryRoute || !resolvedAmo) return null;

  const pending = createTemplateMutation.isPending || createRevisionMutation.isPending || issueMutation.isPending || generateMutation.isPending || saveAiDraftMutation.isPending || deleteDmsMutation.isPending || retireTemplateMutation.isPending;
  const validItems = items.length > 0 && items.every((item) => item.prompt.trim().length >= 3);
  const patchItem = (index: number, patch: Partial<ChecklistTemplateItem>) => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  const showCreateForm = creatingTemplate || !selectedTemplateId;
  const showRevisionEditor = Boolean(selectedTemplateId);
  const auditsWorkspaceHref = `/maintenance/${encodeURIComponent(resolvedAmo)}/quality/audits/workspace`;
  const selectedCriteriaIds = new Set(selectedCriteria.map((row) => row.id));

  return (
    <section className="qms-checklist-template-page qms-checklist-template-page--assurance qms-checklist-library" aria-label="Audit checklist library">
      <div className="qms-checklist-library__toolbar">
        <p className="qms-checklist-library__bind-note">
          Apply checklists to an audit from Prepare.{" "}
          <Link to={auditsWorkspaceHref}>Open audits workspace</Link>
        </p>
        {canManage ? (
          <div className="qms-checklist-library__header-actions">
            <button type="button" onClick={() => setUploadOpen(true)}><Upload size={15} /> Upload controlled checklist</button>
            <button type="button" className="is-ai" onClick={() => { setAiOpen(true); setEditorOpen(false); }}><Sparkles size={15} /> Create with AI</button>
            <button type="button" onClick={openBlankEditor}><Plus size={15} /> Blank template</button>
          </div>
        ) : null}
      </div>

      {error ? <div className="qms-checklist-template-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
      {success ? <div className="qms-checklist-template-success" role="status"><CheckCircle2 size={16} /> {success}</div> : null}

      <main className="qms-checklist-library__main">
        <section className="qms-checklist-library__section">
          <header><div><h2>DMS controlled checklists</h2><p>Only the current effective revision is offered to an audit; draft control remains in Document Control.</p></div><span>{dmsRows.length} document{dmsRows.length === 1 ? "" : "s"}</span></header>
          <div className="qms-checklist-library__filters">
            <label><Search size={14} /><input value={librarySearch} onChange={(event) => setLibrarySearch(event.target.value)} placeholder="Search code, title, hierarchy or owner" /></label>
            <select value={libraryType} onChange={(event) => setLibraryType(event.target.value as typeof libraryType)} aria-label="Document type"><option value="ALL">All checklist documents</option><option value="CHECKLIST">Checklists</option><option value="FORM">Forms</option></select>
          </div>
          <div className="qms-checklist-library__grid ag-theme-alpine">
            <AgGridReact<IntegratedLibraryItem> rowData={dmsRows} columnDefs={dmsColumns} defaultColDef={{ resizable: true, sortable: true, suppressMovable: true }} getRowId={({ data }) => data.id} rowHeight={48} headerHeight={34} loading={dmsChecklistQuery.isLoading} animateRows={false} suppressCellFocus overlayNoRowsTemplate='<span class="qms-checklist-library__empty">No controlled checklist documents match this view.</span>' />
          </div>
        </section>

        <section className="qms-checklist-library__section qms-checklist-library__section--templates">
          <header><div><h2>Structured fieldwork templates</h2><p>Editable audit questions with governed revision history and DMS source references.</p></div><span>{templates.length} template{templates.length === 1 ? "" : "s"}</span></header>
          <div className="qms-checklist-library__template-grid ag-theme-alpine">
            <AgGridReact rowData={templates} columnDefs={templateColumns} defaultColDef={{ resizable: true, sortable: true, suppressMovable: true }} getRowId={({ data }) => data.id} rowHeight={38} headerHeight={34} domLayout="autoHeight" loading={templatesQuery.isLoading} animateRows={false} suppressCellFocus overlayNoRowsTemplate='<span class="qms-checklist-library__empty">Create a blank template or draft one from controlled criteria.</span>' />
          </div>
        </section>
      </main>

      {aiOpen && canManage ? (
        <div className="qms-checklist-ai-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAiOpen(false); }}>
          <aside className="qms-checklist-ai qms-checklist-ai--overlay" role="dialog" aria-modal="true" aria-label="AI checklist drafting">
            <header>
              <div>
                <span><Sparkles size={15} /> AI ASSISTED</span>
                <h2>Build from controlled criteria</h2>
                <p>The server uses current readable DMS revisions. Review every generated item before issue.</p>
              </div>
              <button type="button" onClick={() => setAiOpen(false)} aria-label="Close AI assistant"><X size={18} /></button>
            </header>

            <div className="qms-checklist-ai__step">
              <strong>1. Checklist setup</strong>
              <div className="qms-checklist-ai__fields">
                <label>Checklist title<input value={aiTitle} onChange={(event) => setAiTitle(event.target.value)} placeholder="e.g. Line maintenance compliance audit" /></label>
                <label>Audit type<select value={aiKind} onChange={(event) => setAiKind(event.target.value)}>{AUDIT_KIND_OPTIONS.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
                <label>Questions<select value={aiItemCount} onChange={(event) => setAiItemCount(Number(event.target.value))}><option value={10}>10 focused</option><option value={20}>20 standard</option><option value={30}>30 detailed</option><option value={50}>50 comprehensive</option></select></label>
                <label className="is-wide">Focus (optional)<textarea rows={2} value={aiFocus} onChange={(event) => setAiFocus(event.target.value)} placeholder="Specific department, process or risk to emphasize" /></label>
              </div>
            </div>

            <div className="qms-checklist-ai__step">
              <div className="qms-checklist-ai__criteria-head">
                <strong>2. Select criteria</strong>
                <span>{selectedCriteria.length} selected</span>
              </div>
              <label className="qms-checklist-ai__criteria-search">
                <Search size={14} />
                <input value={criteriaSearch} onChange={(event) => setCriteriaSearch(event.target.value)} placeholder="Filter by code, title or type" aria-label="Filter criteria documents" />
              </label>
              <div className="qms-checklist-ai__criteria-list" role="listbox" aria-label="Readable controlled criteria" aria-multiselectable="true">
                {criteriaQuery.isLoading && !criteriaRows.length ? (
                  <p className="qms-checklist-ai__empty">Loading criteria…</p>
                ) : criteriaRows.length ? criteriaRows.map((row) => {
                  const selected = selectedCriteriaIds.has(row.id);
                  return (
                    <button
                      key={row.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`qms-checklist-ai__criteria-row${selected ? " is-selected" : ""}`}
                      onClick={() => toggleCriteria(row)}
                    >
                      <span className="qms-checklist-ai__criteria-check" aria-hidden="true">{selected ? <CheckCircle2 size={16} /> : null}</span>
                      <span className="qms-checklist-library__stack">
                        <strong>{row.code}</strong>
                        <span>{row.title}</span>
                      </span>
                      <span className="qms-checklist-ai__criteria-meta">
                        <em>{row.library.node_type.replaceAll("_", " ")}</em>
                        <small>{criteriaRevisionLabel(row)}</small>
                      </span>
                    </button>
                  );
                }) : (
                  <p className="qms-checklist-ai__empty">{CRITERIA_EMPTY_COPY}</p>
                )}
              </div>
            </div>

            <button type="button" className="qms-checklist-ai__generate" disabled={generateMutation.isPending || selectedCriteria.length === 0 || aiTitle.trim().length < 3} onClick={() => generateMutation.mutate()}>
              <Sparkles size={15} /> {generateMutation.isPending ? "Drafting…" : "3. Draft checklist"}
            </button>

            {aiResult ? (
              <section className="qms-checklist-ai__result">
                <header>
                  <div>
                    <strong>{aiResult.draft.title}</strong>
                    <span>{aiResult.draft.items.length} questions · {aiResult.model}</span>
                  </div>
                  <button type="button" disabled={saveAiDraftMutation.isPending} onClick={() => saveAiDraftMutation.mutate()}>
                    {saveAiDraftMutation.isPending ? "Saving…" : "Save editable draft"}
                  </button>
                </header>
                <ol className="qms-checklist-ai__preview-list">
                  {aiResult.draft.items.map((item, index) => (
                    <li key={`${item.sort_order}-${index}`}>
                      <strong>{item.section || "General"} · {item.requirement_ref || "Requirement"}</strong>
                      <span>{item.prompt}</span>
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}

      {editorOpen && canManage ? (
        <aside className="qms-checklist-template-panel qms-checklist-template-panel--library" aria-label="Checklist template editor">
          <header>
            <div>
              <span>Structured checklist</span>
              <strong>{showRevisionEditor ? "Revise and issue" : "Create template"}</strong>
            </div>
            <button type="button" onClick={() => { setEditorOpen(false); setCreatingTemplate(false); }} aria-label="Close checklist editor"><PanelRightClose size={18} /></button>
          </header>
          <div className="qms-checklist-template-body">
            {error ? <div className="qms-checklist-template-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
            {success ? <div className="qms-checklist-template-success"><CheckCircle2 size={16} /> {success}</div> : null}

            {showCreateForm ? (
              <section className="qms-checklist-template-card">
                <header><FilePlus2 size={16} /><strong>Create template</strong></header>
                <div className="qms-checklist-template-group">
                  <div className="qms-checklist-template-grid"><label>Code<input value={templateDraft.template_code} onChange={(event) => setTemplateDraft({ ...templateDraft, template_code: event.target.value })} title={templateDraft.template_code || undefined} /></label><label>Audit kind<select value={templateDraft.audit_kind} onChange={(event) => setTemplateDraft({ ...templateDraft, audit_kind: event.target.value })}>{AUDIT_KIND_OPTIONS.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label></div>
                  <label>Title<input value={templateDraft.title} onChange={(event) => setTemplateDraft({ ...templateDraft, title: event.target.value })} title={templateDraft.title || undefined} /></label>
                  <div className="qms-checklist-template-grid"><label>Category<select value={templateDraft.category} onChange={(event) => setTemplateDraft({ ...templateDraft, category: event.target.value })}><option value="">General</option>{CATEGORY_OPTIONS.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label><label>Description<input value={templateDraft.description} onChange={(event) => setTemplateDraft({ ...templateDraft, description: event.target.value })} title={templateDraft.description || undefined} /></label></div>
                </div>
                <button type="button" onClick={() => createTemplateMutation.mutate()} disabled={pending || templateDraft.template_code.trim().length < 2 || templateDraft.title.trim().length < 3}>Create template</button>
              </section>
            ) : null}

            {showRevisionEditor ? (
              <section className="qms-checklist-template-card">
                <header><ListChecks size={16} /><strong>Revision editor</strong></header>
                <div className="qms-checklist-template-group">
                  <label>Template<select value={selectedTemplateId} onChange={(event) => { setTemplateId(event.target.value); setCreatingTemplate(false); if (event.target.value) setItems((current) => current.length ? current : [{ ...EMPTY_ITEM }]); setSuccess(""); }} title={templates.find((row) => row.id === selectedTemplateId)?.title || undefined}><option value="">Select template</option>{templates.map((row) => <option key={row.id} value={row.id} title={`${row.template_code} · ${row.title}`}>{row.template_code} · {row.title}</option>)}</select></label>
                  <label>Revision reason<textarea rows={2} value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} /></label>
                </div>
                {!templates.length ? <p className="qms-checklist-template-empty">No templates yet — create one to start a revision.</p> : null}
                <div className="qms-checklist-template-items">{items.map((item, index) => <article key={index}>
                  <header><strong title={item.prompt || undefined}>Item {index + 1}</strong><button type="button" onClick={() => setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))} disabled={items.length === 1} aria-label={`Remove checklist item ${index + 1}`}><Trash2 size={14} /></button></header>
                  <div className="qms-checklist-template-group">
                    <div className="qms-checklist-template-grid"><label>Section<select value={item.section || "General"} onChange={(event) => patchItem(index, { section: event.target.value })}>{ITEM_SECTION_OPTIONS.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label>Category<select value={item.category || "Compliance"} onChange={(event) => patchItem(index, { category: event.target.value })}>{ITEM_CATEGORY_OPTIONS.map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div>
                    <label>Question / verification prompt<textarea rows={2} value={item.prompt} onChange={(event) => patchItem(index, { prompt: event.target.value })} title={item.prompt || undefined} /></label>
                  </div>
                  <div className="qms-checklist-template-group qms-checklist-template-group--refs">
                    <div className="qms-checklist-template-grid"><label>Requirement ref<input value={item.requirement_ref || ""} onChange={(event) => patchItem(index, { requirement_ref: event.target.value })} title={item.requirement_ref || undefined} /></label><label>Checklist ref<input value={item.checklist_ref || ""} onChange={(event) => patchItem(index, { checklist_ref: event.target.value })} title={item.checklist_ref || undefined} /></label></div>
                    <div className="qms-checklist-template-grid"><label>Regulatory source<input value={item.regulatory_source_ref || ""} onChange={(event) => patchItem(index, { regulatory_source_ref: event.target.value })} title={item.regulatory_source_ref || undefined} /></label><label>Manual source<input value={item.manual_source_ref || ""} onChange={(event) => patchItem(index, { manual_source_ref: event.target.value })} title={item.manual_source_ref || undefined} /></label></div>
                    <label>Expected evidence<textarea rows={2} value={item.expected_evidence || ""} onChange={(event) => patchItem(index, { expected_evidence: event.target.value })} title={item.expected_evidence || undefined} /></label>
                  </div>
                  <div className="qms-checklist-template-group qms-checklist-template-group--response">
                    <div className="qms-checklist-template-grid"><label>Response type<select value={item.response_type} onChange={(event) => patchItem(index, { response_type: event.target.value })}><option value="COMPLIANT_NONCOMPLIANT_OBSERVATION_NA_NOT_VERIFIED">Compliance / observation / N/A / not verified</option><option value="COMPLIANT_NONCOMPLIANT_NA">Compliant / Noncompliant / N/A</option><option value="YES_NO_NA">Yes / No / N/A</option><option value="TEXT">Text evidence</option></select></label><label>Applicability<select value={item.applicability} onChange={(event) => patchItem(index, { applicability: event.target.value })}><option value="ALL">All audit scopes</option><option value="APPLICABLE">Applicable requirements</option><option value="CONDITIONAL">Conditional</option></select></label></div>
                    <div className="qms-checklist-template-grid">
                      <label className="qms-checklist-template-checkbox"><input type="checkbox" checked={item.mandatory ?? true} onChange={(event) => patchItem(index, { mandatory: event.target.checked })} /> Mandatory item</label>
                      <label>Finding trigger<select value={item.finding_trigger || "NONE"} onChange={(event) => patchItem(index, { finding_trigger: event.target.value as ChecklistFindingTrigger })}>{FINDING_TRIGGER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
                    </div>
                  </div>
                </article>)}</div>
                <div className="qms-checklist-template-actions"><button type="button" onClick={() => setItems((current) => [...current, { ...EMPTY_ITEM, sort_order: (current.length + 1) * 10 }])}><Plus size={15} /> Add item</button><button type="button" className="is-primary" onClick={() => createRevisionMutation.mutate()} disabled={pending || !selectedTemplateId || !validItems || revisionReason.trim().length < 8}>Create draft revision</button>{latestDraft ? <button type="button" className="is-primary" onClick={() => issueMutation.mutate()} disabled={pending || revisionReason.trim().length < 8}>Issue revision {latestDraft.revision_no}</button> : null}</div>
              </section>
            ) : null}

            {selectedTemplateId ? <section className="qms-checklist-template-card">
              <header><History size={16} /><strong>Revision history</strong></header>
              {revisions.length ? <ol>{revisions.slice().sort((a, b) => b.revision_no - a.revision_no).map((row) => <li key={row.id}><strong title={row.change_reason || undefined}>Rev {row.revision_no} · {row.status}</strong><span>{row.items.length} item(s) · {row.items.filter((item) => item.mandatory ?? true).length} mandatory</span><small title={row.change_reason || undefined}>{row.change_reason}</small></li>)}</ol> : <p className="qms-checklist-template-empty">No revisions are recorded for the selected template.</p>}
            </section> : null}
          </div>
        </aside>
      ) : null}

      <ControlledDocumentUploadDialog tenant={resolvedAmo} open={uploadOpen} defaultDocumentType="CHECKLIST" allowedTypes={["CHECKLIST", "FORM"]} heading="Upload checklist to Document Control" submitLabel="Register controlled draft" onClose={() => setUploadOpen(false)} onUploaded={async () => { setSuccess("Checklist registered as a controlled DMS draft. Complete its approval workflow before audit use."); await Promise.all([queryClient.invalidateQueries({ queryKey: ["qms-dms-checklist-library", resolvedAmo] }), queryClient.invalidateQueries({ queryKey: ["qms-ai-criteria-library", resolvedAmo] })]); }} />
    </section>
  );
};

export default QualityChecklistTemplateHost;
