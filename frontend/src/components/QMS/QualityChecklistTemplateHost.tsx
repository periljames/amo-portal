import React, { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FilePlus2, History, ListChecks, PanelRightClose, PanelRightOpen, Plus, ShieldAlert, Trash2 } from "lucide-react";

import { qmsResolveAudit } from "../../services/qms";
import {
  applyChecklistRevision,
  createChecklistRevision,
  createChecklistTemplate,
  getChecklistTemplate,
  issueChecklistRevision,
  listChecklistBindings,
  listChecklistTemplates,
  type ChecklistFindingTrigger,
  type ChecklistTemplateItem,
} from "../../services/qmsChecklistTemplates";
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Checklist governance action could not be completed.";
}

const QualityChecklistTemplateHost: React.FC<Props> = ({ amoCode = "", auditKey, activeTab }) => {
  const location = useLocation();
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
  const workspaceOpen = libraryRoute || open;

  const templatesQuery = useQuery({
    queryKey: ["qms-checklist-templates", resolvedAmo],
    queryFn: ({ signal }) => listChecklistTemplates(resolvedAmo, signal),
    enabled: Boolean(workspaceOpen && shouldRender && resolvedAmo),
  });
  const templates = templatesQuery.data?.items || [];
  const selectedTemplateId = templateId || templates[0]?.id || "";
  const templateQuery = useQuery({
    queryKey: ["qms-checklist-template", resolvedAmo, selectedTemplateId],
    queryFn: ({ signal }) => getChecklistTemplate(resolvedAmo, selectedTemplateId, signal),
    enabled: Boolean(workspaceOpen && selectedTemplateId),
  });
  const auditQuery = useQuery({
    queryKey: ["qms-checklist-audit-resolve", auditKey],
    queryFn: () => qmsResolveAudit(String(auditKey)),
    enabled: Boolean(open && auditChecklist && auditKey),
  });
  const auditId = auditQuery.data?.id || "";
  const bindingsQuery = useQuery({
    queryKey: ["qms-checklist-bindings", resolvedAmo, auditId],
    queryFn: ({ signal }) => listChecklistBindings(resolvedAmo, auditId, signal),
    enabled: Boolean(open && auditId),
  });

  const revisions = templateQuery.data?.revisions || [];
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

  if (!shouldRender || !resolvedAmo) return null;
  const pending = createTemplateMutation.isPending || createRevisionMutation.isPending || issueMutation.isPending || applyMutation.isPending;
  const validItems = items.length > 0 && items.every((item) => item.prompt.trim().length >= 3);
  const patchItem = (index: number, patch: Partial<ChecklistTemplateItem>) => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));

  const body = (
    <div className="qms-checklist-template-body">
      {error ? <div className="qms-checklist-template-error" role="alert"><ShieldAlert size={16} /> {error}</div> : null}
      {success ? <div className="qms-checklist-template-success"><CheckCircle2 size={16} /> {success}</div> : null}

      <section className="qms-checklist-template-card">
        <header><FilePlus2 size={16} /><strong>Create template</strong></header>
        <div className="qms-checklist-template-group">
          <div className="qms-checklist-template-grid"><label>Code<input value={templateDraft.template_code} onChange={(event) => setTemplateDraft({ ...templateDraft, template_code: event.target.value })} title={templateDraft.template_code || undefined} /></label><label>Audit kind<input value={templateDraft.audit_kind} onChange={(event) => setTemplateDraft({ ...templateDraft, audit_kind: event.target.value })} /></label></div>
          <label>Title<input value={templateDraft.title} onChange={(event) => setTemplateDraft({ ...templateDraft, title: event.target.value })} title={templateDraft.title || undefined} /></label>
          <div className="qms-checklist-template-grid"><label>Category<input value={templateDraft.category} onChange={(event) => setTemplateDraft({ ...templateDraft, category: event.target.value })} /></label><label>Description<input value={templateDraft.description} onChange={(event) => setTemplateDraft({ ...templateDraft, description: event.target.value })} title={templateDraft.description || undefined} /></label></div>
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
            <div className="qms-checklist-template-grid"><label>Section<input value={item.section || ""} onChange={(event) => patchItem(index, { section: event.target.value })} /></label><label>Category<input value={item.category || ""} onChange={(event) => patchItem(index, { category: event.target.value })} /></label></div>
            <label>Question / verification prompt<textarea rows={2} value={item.prompt} onChange={(event) => patchItem(index, { prompt: event.target.value })} title={item.prompt || undefined} /></label>
          </div>
          <div className="qms-checklist-template-group qms-checklist-template-group--refs">
            <div className="qms-checklist-template-grid"><label>Requirement ref<input value={item.requirement_ref || ""} onChange={(event) => patchItem(index, { requirement_ref: event.target.value })} title={item.requirement_ref || undefined} /></label><label>Checklist ref<input value={item.checklist_ref || ""} onChange={(event) => patchItem(index, { checklist_ref: event.target.value })} title={item.checklist_ref || undefined} /></label></div>
            <div className="qms-checklist-template-grid"><label>Regulatory source<input value={item.regulatory_source_ref || ""} onChange={(event) => patchItem(index, { regulatory_source_ref: event.target.value })} title={item.regulatory_source_ref || undefined} /></label><label>Manual source<input value={item.manual_source_ref || ""} onChange={(event) => patchItem(index, { manual_source_ref: event.target.value })} title={item.manual_source_ref || undefined} /></label></div>
            <label>Expected evidence<textarea rows={2} value={item.expected_evidence || ""} onChange={(event) => patchItem(index, { expected_evidence: event.target.value })} title={item.expected_evidence || undefined} /></label>
          </div>
          <div className="qms-checklist-template-group qms-checklist-template-group--response">
            <div className="qms-checklist-template-grid"><label>Response type<select value={item.response_type} onChange={(event) => patchItem(index, { response_type: event.target.value })}><option value="COMPLIANT_NONCOMPLIANT_OBSERVATION_NA_NOT_VERIFIED">Compliance / observation / N/A / not verified</option><option value="COMPLIANT_NONCOMPLIANT_NA">Compliant / Noncompliant / N/A</option><option value="YES_NO_NA">Yes / No / N/A</option><option value="TEXT">Text evidence</option></select></label><label>Applicability<input value={item.applicability} onChange={(event) => patchItem(index, { applicability: event.target.value })} /></label></div>
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
      <section className="qms-checklist-template-page qms-checklist-template-page--assurance" aria-label="Audit checklist templates">
        <header className="qms-checklist-template-page__header qms-checklist-template-page__header--dense">
          <div>
            <span>Audit Assurance</span>
            <h1>Checklist library</h1>
            <p>Controlled templates for preparation and fieldwork — same chrome density as Programme / Register.</p>
          </div>
        </header>
        {body}
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