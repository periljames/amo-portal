import React, { useCallback, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams, SelectionChangedEvent } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { BookOpen, CheckCircle2, Download, FilePlus2, History, ListChecks, PanelRightClose, PanelRightOpen, Pencil, Plus, Search, ShieldAlert, Sparkles, Trash2, Upload } from "lucide-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

import ControlledDocumentUploadDialog from "../documentControl/ControlledDocumentUploadDialog";
import { listIntegratedLibrary, type IntegratedLibraryItem } from "../../services/documentLibrary";
import { fetchPublicationBlob } from "../../services/publications";
import {
  applyChecklistRevision,
  createChecklistRevision,
  createChecklistTemplate,
  generateChecklistDraft,
  getChecklistTemplate,
  issueChecklistRevision,
  listChecklistBindings,
  listChecklistTemplates,
  type ChecklistFindingTrigger,
  type ChecklistTemplateItem,
  type ChecklistAIDraft,
} from "../../services/qmsChecklistTemplates";
import { resolveAuditOccurrence } from "../../services/qmsAuditOccurrenceResolver";
import { saveDownloadedFile } from "../../utils/downloads";
import "../../styles/qms-checklist-templates.css";

type Props = { amoCode?: string; auditKey?: string | null; activeTab?: string | null };
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Checklist governance action could not be completed.";
}

const QualityChecklistTemplateHost: React.FC<Props> = ({ amoCode = "", auditKey, activeTab }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const libraryRoute = /\/(?:quality|qms)\/audits\/checklists(?:\/|$)/i.test(location.pathname);
  const auditChecklist = Boolean(auditKey && (activeTab === "checklist" || new URLSearchParams(location.search).get("tab") === "checklist"));
  const shouldRender = libraryRoute || auditChecklist;
  const pathnameAmo = location.pathname.match(/^\/maintenance\/([^/]+)\//i)?.[1];
  const resolvedAmo = amoCode || (pathnameAmo ? decodeURIComponent(pathnameAmo) : "");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [templateDraft, setTemplateDraft] = useState<TemplateDraft>({ template_code: "", title: "", description: "", category: "", audit_kind: "INTERNAL" });
  const [revisionReason, setRevisionReason] = useState("Controlled checklist revision for audit use.");
  const [items, setItems] = useState<ChecklistTemplateItem[]>([{ ...EMPTY_ITEM }]);
  const [applyReason, setApplyReason] = useState("Apply this issued checklist revision to the audit.");
  const [allowExisting, setAllowExisting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [librarySearch, setLibrarySearch] = useState("");
  const [libraryType, setLibraryType] = useState<"ALL" | "CHECKLIST" | "FORM">("ALL");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [splitPercent, setSplitPercent] = useState(50);
  const [selectedCriteria, setSelectedCriteria] = useState<IntegratedLibraryItem[]>([]);
  const [aiTitle, setAiTitle] = useState("");
  const [aiKind, setAiKind] = useState("INTERNAL");
  const [aiFocus, setAiFocus] = useState("");
  const [aiItemCount, setAiItemCount] = useState(20);
  const [aiResult, setAiResult] = useState<ChecklistAIDraft | null>(null);
  const workspaceOpen = libraryRoute || open;

  const templatesQuery = useQuery({
    queryKey: ["qms-checklist-templates", resolvedAmo],
    queryFn: ({ signal }) => listChecklistTemplates(resolvedAmo, signal),
    enabled: Boolean(workspaceOpen && shouldRender && resolvedAmo),
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
  const selectedTemplateId = templateId || templates[0]?.id || "";
  const templateQuery = useQuery({
    queryKey: ["qms-checklist-template", resolvedAmo, selectedTemplateId],
    queryFn: ({ signal }) => getChecklistTemplate(resolvedAmo, selectedTemplateId, signal),
    enabled: Boolean(workspaceOpen && selectedTemplateId),
  });
  const auditQuery = useQuery({
    queryKey: ["qms-checklist-audit-resolve", resolvedAmo, auditKey],
    queryFn: ({ signal }) => resolveAuditOccurrence(resolvedAmo, String(auditKey), signal),
    enabled: Boolean(open && auditChecklist && auditKey && resolvedAmo),
  });
  const auditId = auditQuery.data?.id || "";
  const bindingsQuery = useQuery({
    queryKey: ["qms-checklist-bindings", resolvedAmo, auditId],
    queryFn: ({ signal }) => listChecklistBindings(resolvedAmo, auditId, signal),
    enabled: Boolean(open && auditId),
  });

  const revisions = useMemo(() => templateQuery.data?.revisions || [], [templateQuery.data?.revisions]);
  const latestDraft = revisions.find((row) => row.status === "DRAFT");
  const latestIssued = useMemo(
    () => revisions.filter((row) => row.status === "ISSUED").sort((a, b) => b.revision_no - a.revision_no)[0],
    [revisions],
  );

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-checklist-templates", resolvedAmo] }),
      queryClient.invalidateQueries({ queryKey: ["qms-checklist-template", resolvedAmo, selectedTemplateId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-checklist-bindings", resolvedAmo, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-context", auditKey] }),
    ]);
  };

  const createTemplateMutation = useMutation({
    mutationFn: () => createChecklistTemplate(resolvedAmo, templateDraft),
    onSuccess: async (row) => {
      setTemplateId(row.id);
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
  const applyMutation = useMutation({
    mutationFn: () => latestIssued && auditId ? applyChecklistRevision(resolvedAmo, auditId, latestIssued.id, applyReason, allowExisting) : Promise.reject(new Error("An issued revision and resolved audit are required.")),
    onSuccess: async (row) => {
      setSuccess(`Revision ${row.revision_no} applied to ${row.instantiated_item_ids.length} checklist item(s).`);
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
      setEditorOpen(true);
      setAiOpen(false);
      setSuccess(`${created.template_code} draft revision ${revision.revision_no} saved for auditor review.`);
      await refresh();
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
  const criteriaRows = useMemo(() => (criteriaQuery.data?.items || []).filter((row) => (
    CRITERIA_TYPES.has(row.library.node_type) && row.read_target.kind === "PUBLISHED" && Boolean(row.read_target.revision_id)
  )), [criteriaQuery.data?.items]);

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
      flex: 1.7,
      minWidth: 220,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__stack"><strong>{data.code}</strong><span>{data.title}</span></div> : null,
    },
    {
      headerName: "Type / hierarchy",
      flex: 1.15,
      minWidth: 150,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__stack"><strong>{data.library.node_type.replaceAll("_", " ")}</strong><span>{data.library.structure_path || "Top-level controlled document"}</span></div> : null,
    },
    {
      headerName: "Current control",
      flex: 0.9,
      minWidth: 135,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__stack"><strong>{data.current_revision ? `Rev ${data.current_revision.revision_number}` : "No issued revision"}</strong><span>{data.read_target.control_status || data.workflow?.state || data.status}</span></div> : null,
    },
    { headerName: "Owner", valueGetter: ({ data }) => data?.profile.owner_department || data?.owner_role || "—", flex: 0.75, minWidth: 115 },
    {
      headerName: "Actions",
      pinned: "right",
      width: 132,
      minWidth: 132,
      maxWidth: 132,
      sortable: false,
      cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__actions">
        <button type="button" title="Read current revision" aria-label={`Read ${data.code}`} disabled={!data.read_target.revision_id} onClick={() => data.read_target.revision_id && navigate(`/maintenance/${encodeURIComponent(resolvedAmo)}/publications/${encodeURIComponent(data.id)}/rev/${encodeURIComponent(data.read_target.revision_id)}/read`)}><BookOpen size={15} /></button>
        <button type="button" title="Download source" aria-label={`Download ${data.code}`} disabled={!data.read_target.revision_id} onClick={() => void downloadDmsSource(data)}><Download size={15} /></button>
        <button type="button" title="Open Document Control workspace" aria-label={`Modify ${data.code}`} onClick={() => navigate(`/maintenance/${encodeURIComponent(resolvedAmo)}/document-control/library/${encodeURIComponent(data.id)}`)}><Pencil size={15} /></button>
      </div> : null,
    },
  ], [downloadDmsSource, navigate, resolvedAmo]);
  const templateColumns = useMemo<ColDef<(typeof templates)[number]>[]>(() => [
    { headerName: "Structured template", field: "template_code", flex: 0.75, minWidth: 130 },
    { headerName: "Title", field: "title", flex: 1.8, minWidth: 210 },
    { headerName: "Audit / category", flex: 1, minWidth: 150, valueGetter: ({ data }) => `${data?.audit_kind || "ALL"} · ${String(data?.category || "GENERAL").replaceAll("_", " ")}` },
    { headerName: "Status", field: "status", flex: 0.6, minWidth: 90 },
    { headerName: "", pinned: "right", width: 50, minWidth: 50, maxWidth: 50, sortable: false, cellRenderer: ({ data }: ICellRendererParams<(typeof templates)[number]>) => data ? <button className="qms-checklist-library__icon" type="button" title="Edit template" aria-label={`Edit ${data.template_code}`} onClick={() => { setTemplateId(data.id); setEditorOpen(true); }}><Pencil size={15} /></button> : null },
  ], []);
  const criteriaColumns = useMemo<ColDef<IntegratedLibraryItem>[]>(() => [
    { headerName: "Criteria", checkboxSelection: true, headerCheckboxSelection: true, flex: 1.4, minWidth: 190, cellRenderer: ({ data }: ICellRendererParams<IntegratedLibraryItem>) => data ? <div className="qms-checklist-library__stack"><strong>{data.code}</strong><span>{data.title}</span></div> : null },
    { headerName: "Type", valueGetter: ({ data }) => data?.library.node_type.replaceAll("_", " ") || "", flex: 0.7, minWidth: 110 },
    { headerName: "Current", valueGetter: ({ data }) => data?.current_revision ? `Rev ${data.current_revision.revision_number}` : "—", width: 90, minWidth: 90 },
  ], []);
  const aiItemColumns = useMemo<ColDef<ChecklistTemplateItem>[]>(() => [
    { headerName: "Section", field: "section", flex: 0.65, minWidth: 100 },
    { headerName: "Verification prompt", field: "prompt", flex: 1.8, minWidth: 210, wrapText: true, autoHeight: true },
    { headerName: "Requirement", field: "requirement_ref", flex: 0.8, minWidth: 115 },
  ], []);

  const beginResize = (event: React.PointerEvent<HTMLDivElement>) => {
    const container = event.currentTarget.parentElement;
    if (!container) return;
    event.preventDefault();
    const move = (pointer: PointerEvent) => {
      const bounds = container.getBoundingClientRect();
      const percent = ((pointer.clientX - bounds.left) / bounds.width) * 100;
      setSplitPercent(Math.min(70, Math.max(32, percent)));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  };

  if (!shouldRender || !resolvedAmo) return null;
  const pending = createTemplateMutation.isPending || createRevisionMutation.isPending || issueMutation.isPending || applyMutation.isPending || generateMutation.isPending || saveAiDraftMutation.isPending;
  const validItems = items.length > 0 && items.every((item) => item.prompt.trim().length >= 3);
  const patchItem = (index: number, patch: Partial<ChecklistTemplateItem>) => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));

  const body = (
    <div className="qms-checklist-template-body">
      {error ? <div className="qms-checklist-template-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
      {success ? <div className="qms-checklist-template-success"><CheckCircle2 size={16} /> {success}</div> : null}

      <section className="qms-checklist-template-card">
        <header><FilePlus2 size={16} /><strong>Create template</strong></header>
        <div className="qms-checklist-template-group">
          <div className="qms-checklist-template-grid"><label>Code<input value={templateDraft.template_code} onChange={(event) => setTemplateDraft({ ...templateDraft, template_code: event.target.value })} title={templateDraft.template_code || undefined} /></label><label>Audit kind<select value={templateDraft.audit_kind} onChange={(event) => setTemplateDraft({ ...templateDraft, audit_kind: event.target.value })}>{AUDIT_KIND_OPTIONS.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label></div>
          <label>Title<input value={templateDraft.title} onChange={(event) => setTemplateDraft({ ...templateDraft, title: event.target.value })} title={templateDraft.title || undefined} /></label>
          <div className="qms-checklist-template-grid"><label>Category<select value={templateDraft.category} onChange={(event) => setTemplateDraft({ ...templateDraft, category: event.target.value })}><option value="">General</option>{CATEGORY_OPTIONS.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label><label>Description<input value={templateDraft.description} onChange={(event) => setTemplateDraft({ ...templateDraft, description: event.target.value })} title={templateDraft.description || undefined} /></label></div>
        </div>
        <button type="button" onClick={() => createTemplateMutation.mutate()} disabled={pending || templateDraft.template_code.trim().length < 2 || templateDraft.title.trim().length < 3}>Create template</button>
      </section>

      <section className="qms-checklist-template-card">
        <header><ListChecks size={16} /><strong>Revision editor</strong></header>
        <div className="qms-checklist-template-group">
          <label>Template<select value={selectedTemplateId} onChange={(event) => { setTemplateId(event.target.value); setSuccess(""); }} title={templates.find((row) => row.id === selectedTemplateId)?.title || undefined}><option value="">Select template</option>{templates.map((row) => <option key={row.id} value={row.id} title={`${row.template_code} · ${row.title}`}>{row.template_code} · {row.title}</option>)}</select></label>
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

      {selectedTemplateId ? <section className="qms-checklist-template-card">
        <header><History size={16} /><strong>Revision history</strong></header>
        {revisions.length ? <ol>{revisions.slice().sort((a, b) => b.revision_no - a.revision_no).map((row) => <li key={row.id}><strong title={row.change_reason || undefined}>Rev {row.revision_no} · {row.status}</strong><span>{row.items.length} item(s) · {row.items.filter((item) => item.mandatory ?? true).length} mandatory</span><small title={row.change_reason || undefined}>{row.change_reason}</small></li>)}</ol> : <p className="qms-checklist-template-empty">No revisions are recorded for the selected template.</p>}
      </section> : null}

      {auditChecklist ? <section className="qms-checklist-template-card">
        <header><ListChecks size={16} /><strong>Apply to this audit</strong></header>
        <p title={auditQuery.data ? `${auditQuery.data.audit_ref} · ${auditQuery.data.title}` : undefined}>{auditQuery.data ? `${auditQuery.data.audit_ref} · ${auditQuery.data.title}` : "Resolving audit…"}</p>
        <p>{latestIssued ? `Latest issued revision: ${templateQuery.data?.template_code} Rev ${latestIssued.revision_no}` : "Select a template with an issued revision."}</p>
        <label>Application reason<textarea rows={2} value={applyReason} onChange={(event) => setApplyReason(event.target.value)} /></label>
        <label className="qms-checklist-template-checkbox"><input type="checkbox" checked={allowExisting} onChange={(event) => setAllowExisting(event.target.checked)} /> Append to an audit that already has checklist rows</label>
        <button type="button" className="is-primary" onClick={() => applyMutation.mutate()} disabled={pending || !auditId || !latestIssued || applyReason.trim().length < 8}>Apply issued revision to audit</button>
        {bindingsQuery.data?.items.length ? <ul>{bindingsQuery.data.items.map((row) => <li key={row.id}><strong>{row.template_code} Rev {row.revision_no}</strong><span>{row.instantiated_item_ids.length} checklist row(s)</span><small title={row.application_reason || undefined}>{row.application_reason}</small></li>)}</ul> : <p className="qms-checklist-template-empty">No checklist revision has been applied to this audit yet.</p>}
      </section> : null}
    </div>
  );

  if (libraryRoute) {
    return (
      <section className="qms-checklist-template-page qms-checklist-template-page--assurance qms-checklist-library" aria-label="Audit checklist library">
        <header className="qms-checklist-template-page__header qms-checklist-template-page__header--dense">
          <div>
            <span>Audit Assurance</span>
            <h1>Checklist library</h1>
            <p>Current DMS-controlled checklists and editable fieldwork templates in one workspace.</p>
          </div>
          <div className="qms-checklist-library__header-actions">
            <button type="button" onClick={() => setUploadOpen(true)}><Upload size={15} /> Upload controlled checklist</button>
            <button type="button" className="is-ai" onClick={() => { setAiOpen((value) => !value); setEditorOpen(false); }}><Sparkles size={15} /> Create with AI</button>
            <button type="button" onClick={() => { setEditorOpen(true); setAiOpen(false); }}><Plus size={15} /> Blank template</button>
          </div>
        </header>
        {error ? <div className="qms-checklist-template-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
        {success ? <div className="qms-checklist-template-success" role="status"><CheckCircle2 size={16} /> {success}</div> : null}

        <div className={`qms-checklist-library__split${aiOpen ? " is-open" : ""}`} style={aiOpen ? { gridTemplateColumns: `${splitPercent}% 8px minmax(0, 1fr)` } : undefined}>
          <main className="qms-checklist-library__main">
            <section className="qms-checklist-library__section">
              <header><div><h2>DMS controlled checklists</h2><p>Only the current effective revision is offered to an audit; draft control remains in Document Control.</p></div><span>{dmsRows.length} document{dmsRows.length === 1 ? "" : "s"}</span></header>
              <div className="qms-checklist-library__toolbar">
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

          {aiOpen ? <>
            <div className="qms-checklist-library__resizer" role="separator" aria-orientation="vertical" aria-label="Resize AI checklist workspace" tabIndex={0} onPointerDown={beginResize} />
            <aside className="qms-checklist-ai" aria-label="AI checklist drafting">
              <header><div><span><Sparkles size={15} /> AI ASSISTED</span><h2>Build from controlled criteria</h2><p>The server uses current readable DMS revisions. Review every generated item before issue.</p></div><button type="button" onClick={() => setAiOpen(false)} aria-label="Close AI assistant"><PanelRightClose size={18} /></button></header>
              <div className="qms-checklist-ai__fields">
                <label>Checklist title<input value={aiTitle} onChange={(event) => setAiTitle(event.target.value)} placeholder="e.g. Line maintenance compliance audit" /></label>
                <label>Audit type<select value={aiKind} onChange={(event) => setAiKind(event.target.value)}>{AUDIT_KIND_OPTIONS.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
                <label>Questions<select value={aiItemCount} onChange={(event) => setAiItemCount(Number(event.target.value))}><option value={10}>10 focused</option><option value={20}>20 standard</option><option value={30}>30 detailed</option><option value={50}>50 comprehensive</option></select></label>
                <label className="is-wide">Focus (optional)<textarea rows={2} value={aiFocus} onChange={(event) => setAiFocus(event.target.value)} placeholder="Specific department, process or risk to emphasize" /></label>
              </div>
              <div className="qms-checklist-ai__criteria-head"><strong>1. Select current criteria</strong><span>{selectedCriteria.length} selected</span></div>
              <div className="qms-checklist-ai__criteria-grid ag-theme-alpine">
                <AgGridReact<IntegratedLibraryItem> rowData={criteriaRows} columnDefs={criteriaColumns} defaultColDef={{ resizable: true, sortable: true, suppressMovable: true }} getRowId={({ data }) => data.id} rowSelection="multiple" suppressRowClickSelection headerHeight={34} rowHeight={44} loading={criteriaQuery.isLoading} animateRows={false} onSelectionChanged={(event: SelectionChangedEvent<IntegratedLibraryItem>) => setSelectedCriteria(event.api.getSelectedRows())} overlayNoRowsTemplate='<span class="qms-checklist-library__empty">No current indexed criteria documents are available.</span>' />
              </div>
              <button type="button" className="qms-checklist-ai__generate" disabled={generateMutation.isPending || selectedCriteria.length === 0 || aiTitle.trim().length < 3} onClick={() => generateMutation.mutate()}><Sparkles size={15} /> {generateMutation.isPending ? "Drafting…" : "2. Draft checklist"}</button>
              {aiResult ? <section className="qms-checklist-ai__result"><header><div><strong>{aiResult.draft.title}</strong><span>{aiResult.draft.items.length} questions · {aiResult.model}</span></div><button type="button" disabled={saveAiDraftMutation.isPending} onClick={() => saveAiDraftMutation.mutate()}>{saveAiDraftMutation.isPending ? "Saving…" : "Save editable draft"}</button></header><div className="qms-checklist-ai__preview-grid ag-theme-alpine"><AgGridReact<ChecklistTemplateItem> rowData={aiResult.draft.items} columnDefs={aiItemColumns} defaultColDef={{ resizable: true, suppressMovable: true }} getRowId={({ data }) => String(data.sort_order)} rowHeight={52} headerHeight={32} animateRows={false} suppressCellFocus /></div></section> : null}
            </aside>
          </> : null}
        </div>

        {editorOpen ? <aside className="qms-checklist-template-panel qms-checklist-template-panel--library" aria-label="Checklist template editor"><header><div><span>Structured checklist</span><strong>Create, revise and issue</strong></div><button type="button" onClick={() => setEditorOpen(false)} aria-label="Close checklist editor"><PanelRightClose size={18} /></button></header>{body}</aside> : null}
        <ControlledDocumentUploadDialog tenant={resolvedAmo} open={uploadOpen} defaultDocumentType="CHECKLIST" allowedTypes={["CHECKLIST", "FORM"]} heading="Upload checklist to Document Control" submitLabel="Register controlled draft" onClose={() => setUploadOpen(false)} onUploaded={async () => { setSuccess("Checklist registered as a controlled DMS draft. Complete its approval workflow before audit use."); await Promise.all([queryClient.invalidateQueries({ queryKey: ["qms-dms-checklist-library", resolvedAmo] }), queryClient.invalidateQueries({ queryKey: ["qms-ai-criteria-library", resolvedAmo] })]); }} />
      </section>
    );
  }

  return <>
    <button className="qms-checklist-template-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-checklist-template-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Checklist templates
    </button>
    {open ? <aside id="qms-checklist-template-panel" className="qms-checklist-template-panel" aria-label="Checklist templates and revisions">
      <header><div><span>Checklist governance</span><strong>Templates · revisions · audit binding</strong></div><button type="button" onClick={() => setOpen(false)} aria-label="Close checklist governance"><PanelRightClose size={18} /></button></header>
      {body}
    </aside> : null}
  </>;
};

export default QualityChecklistTemplateHost;
