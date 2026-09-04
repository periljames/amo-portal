import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Copy,
  Link2,
  Plus,
  Search,
  ShieldAlert,
  Trash2,
  UserPlus,
  UserX,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import {
  applyChecklistRevision,
  createRealtimeAuditChecklist,
  getChecklistTemplate,
  listChecklistTemplates,
  type ChecklistTemplateItem,
} from "../../../services/qmsChecklistTemplates";
import {
  createExternalAuditParticipant,
  listExternalAuditParticipants,
  revokeExternalAuditParticipant,
  type ExternalParticipantType,
} from "../../../services/qmsAuditExternalAccess";
import {
  createGovernedAuditDocumentRequest,
  listCanonicalDocumentControlDocuments,
  listCanonicalDocumentControlRevisions,
  listGovernedAuditDocumentRequests,
  updateGovernedAuditDocumentRequest,
  type CanonicalDocumentControlDocument,
  type GovernedAuditDocumentRequest,
} from "../../../services/qmsAuditOccurrenceCompletion";
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { getAuditPreparationContext } from "../../../services/qmsAuditPreparationContext";
import { getAuditSession } from "../../../services/qmsAuditSession";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditOccurrenceLoadDetail, auditPrerequisiteLoadDetail } from "./auditStageLoadErrorMessages";
import { auditSessionPath, isAtLeastLiveStage } from "./auditSessionRoutes";
import { AUDIT_PREPARE_TOOLBAR_ID } from "./OccurrenceToolbarPortal";
import "../../../styles/qms-audit-prepare-workspace.css";

type Props = { amoCode: string; auditKey: string };

type NewRequest = {
  title: string;
  description: string;
  dueDate: string;
  requestType: GovernedAuditDocumentRequest["request_type"];
  linkedCriterion: string;
  isRequired: boolean;
  sourceMode: GovernedAuditDocumentRequest["source_mode"];
  controlledDocumentId: string;
  controlledRevisionId: string;
};

type ChecklistComposerItem = {
  id: string;
  section: string;
  checklistRef: string;
  requirementRef: string;
  prompt: string;
  expectedEvidence: string;
  mandatory: boolean;
};

type ExternalParticipantDraft = {
  participantType: ExternalParticipantType;
  displayName: string;
  email: string;
  organisation: string;
  role: string;
  assuranceLevel: "EMAIL_LINK" | "PASSKEY";
  expiresAt: string;
  readProgress: boolean;
  readReleasedEvidence: boolean;
  executeChecklist: boolean;
  createEvidence: boolean;
  draftFinding: boolean;
};

const emptyRequest: NewRequest = {
  title: "",
  description: "",
  dueDate: "",
  requestType: "DOCUMENT",
  linkedCriterion: "",
  isRequired: true,
  sourceMode: "UPLOAD_OR_CONTROLLED",
  controlledDocumentId: "",
  controlledRevisionId: "",
};

const emptyExternalParticipant: ExternalParticipantDraft = {
  participantType: "AUDITEE_GUEST",
  displayName: "",
  email: "",
  organisation: "",
  role: "AUDITEE",
  assuranceLevel: "EMAIL_LINK",
  expiresAt: "",
  readProgress: false,
  readReleasedEvidence: false,
  executeChecklist: false,
  createEvidence: false,
  draftFinding: false,
};

function emptyChecklistItem(): ChecklistComposerItem {
  return {
    id: typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    section: "",
    checklistRef: "",
    requirementRef: "",
    prompt: "",
    expectedEvidence: "",
    mandatory: true,
  };
}

function statusLabel(status: string) {
  return status.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function participantPermissions(draft: ExternalParticipantDraft): string[] {
  if (draft.participantType === "AUDITEE_GUEST") {
    return [
      "audit:read_summary",
      "audit:read_released_findings",
      "audit:document_submit",
      "audit:acknowledge",
      "car:respond",
      ...(draft.readProgress ? ["audit:read_progress"] : []),
      ...(draft.readReleasedEvidence ? ["audit:read_released_evidence"] : []),
    ];
  }
  return [
    "audit:read_assigned",
    "audit:read_summary",
    ...(draft.readProgress ? ["audit:read_progress"] : []),
    ...(draft.executeChecklist ? ["audit:checklist_execute"] : []),
    ...(draft.createEvidence ? ["audit:evidence_create"] : []),
    ...(draft.draftFinding ? ["audit:finding_draft"] : []),
  ];
}

const AuditPrepareWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [showParticipantForm, setShowParticipantForm] = useState(false);
  const [newRequest, setNewRequest] = useState<NewRequest>(emptyRequest);
  const [participantDraft, setParticipantDraft] = useState<ExternalParticipantDraft>(emptyExternalParticipant);
  const [oneTimeAccessUrl, setOneTimeAccessUrl] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState<string | null>(null);
  const [checklistMode, setChecklistMode] = useState<"LIBRARY" | "CREATE">("LIBRARY");
  const [checklistSearch, setChecklistSearch] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedTemplateRevisionId, setSelectedTemplateRevisionId] = useState("");
  const [checklistReason, setChecklistReason] = useState("Selected for this audit during governed preparation.");
  const [allowExistingItems, setAllowExistingItems] = useState(false);
  const [checklistTitle, setChecklistTitle] = useState("Audit fieldwork checklist");
  const [checklistDescription, setChecklistDescription] = useState("");
  const [checklistItems, setChecklistItems] = useState<ChecklistComposerItem[]>([emptyChecklistItem()]);
  const [checklistDmsSearch, setChecklistDmsSearch] = useState("");
  const [checklistDmsDocumentId, setChecklistDmsDocumentId] = useState("");
  const [checklistDmsRevisionId, setChecklistDmsRevisionId] = useState("");
  const [requestDmsSearch, setRequestDmsSearch] = useState("");

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const contextQuery = useQuery({
    queryKey: ["qms-audit-preparation-context", amoCode, auditId],
    queryFn: ({ signal }) => getAuditPreparationContext(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 3_000,
  });
  const requestsQuery = useQuery({
    queryKey: ["qms-governed-audit-document-requests", amoCode, auditId],
    queryFn: ({ signal }) => listGovernedAuditDocumentRequests(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const participantsQuery = useQuery({
    queryKey: ["qms-audit-external-participants", amoCode, auditId],
    queryFn: ({ signal }) => listExternalAuditParticipants(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const sessionQuery = useQuery({
    queryKey: ["qms-audit-session", amoCode, auditId],
    queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const controlledDocumentsQuery = useQuery({
    queryKey: ["qms-canonical-document-control-documents", amoCode, auditId],
    queryFn: ({ signal }) => listCanonicalDocumentControlDocuments(amoCode, auditId, signal),
    enabled: Boolean(auditId && canManage),
    staleTime: 30_000,
  });
  const requestControlledRevisionsQuery = useQuery({
    queryKey: ["qms-canonical-document-control-revisions", amoCode, auditId, newRequest.controlledDocumentId],
    queryFn: ({ signal }) => listCanonicalDocumentControlRevisions(amoCode, auditId, newRequest.controlledDocumentId, signal),
    enabled: Boolean(showRequestForm && newRequest.sourceMode !== "UPLOAD" && newRequest.controlledDocumentId),
    staleTime: 10_000,
  });
  const checklistControlledRevisionsQuery = useQuery({
    queryKey: ["qms-canonical-document-control-revisions", amoCode, auditId, checklistDmsDocumentId],
    queryFn: ({ signal }) => listCanonicalDocumentControlRevisions(amoCode, auditId, checklistDmsDocumentId, signal),
    enabled: Boolean(auditId && checklistMode === "CREATE" && checklistDmsDocumentId),
    staleTime: 10_000,
  });
  const templatesQuery = useQuery({
    queryKey: ["qms-audit-checklist-templates", amoCode],
    queryFn: ({ signal }) => listChecklistTemplates(amoCode, signal),
    enabled: Boolean(auditId && canManage),
    staleTime: 10_000,
  });
  const selectedTemplateQuery = useQuery({
    queryKey: ["qms-audit-checklist-template", amoCode, selectedTemplateId],
    queryFn: ({ signal }) => getChecklistTemplate(amoCode, selectedTemplateId, signal),
    enabled: Boolean(selectedTemplateId),
    staleTime: 5_000,
  });

  const issuedTemplateRevisions = useMemo(
    () => (selectedTemplateQuery.data?.revisions || []).filter((revision) => revision.status === "ISSUED"),
    [selectedTemplateQuery.data?.revisions],
  );
  const effectiveTemplateRevisionId = selectedTemplateRevisionId || issuedTemplateRevisions[0]?.id || "";

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-governed-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-external-participants", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-templates", amoCode] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-execution", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-checklist", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-bindings", amoCode, auditId] }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: () => createGovernedAuditDocumentRequest(amoCode, auditId, {
      title: newRequest.title.trim(),
      description: newRequest.description.trim() || null,
      due_date: newRequest.dueDate || null,
      request_type: newRequest.requestType,
      linked_criterion: newRequest.linkedCriterion.trim() || null,
      is_required: newRequest.isRequired,
      source_mode: newRequest.sourceMode,
      controlled_source_system: "DOCUMENT_CONTROL",
      controlled_document_id: null,
      controlled_revision_id: null,
      canonical_document_id: newRequest.sourceMode !== "UPLOAD" && newRequest.controlledDocumentId ? newRequest.controlledDocumentId : null,
      canonical_revision_id: newRequest.sourceMode !== "UPLOAD" && newRequest.controlledRevisionId ? newRequest.controlledRevisionId : null,
    }),
    onSuccess: async () => {
      setNewRequest(emptyRequest);
      setShowRequestForm(false);
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Document request could not be created."),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ request, status }: { request: GovernedAuditDocumentRequest; status: "ACCEPTED" | "REJECTED" | "WAIVED" }) =>
      updateGovernedAuditDocumentRequest(amoCode, auditId, request.id, {
        status,
        review_note: reviewNotes[request.id]?.trim() || null,
      }),
    onSuccess: async (updated) => {
      setReviewNotes((current) => ({ ...current, [updated.id]: "" }));
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Document review decision failed."),
  });

  const participantMutation = useMutation({
    mutationFn: () => createExternalAuditParticipant(amoCode, auditId, {
      email: participantDraft.email.trim(),
      display_name: participantDraft.displayName.trim(),
      organisation: participantDraft.organisation.trim() || null,
      participant_type: participantDraft.participantType,
      role: participantDraft.role.trim(),
      permissions: participantPermissions(participantDraft),
      assurance_level: participantDraft.assuranceLevel,
      expires_at: new Date(participantDraft.expiresAt).toISOString(),
    }),
    onSuccess: async (participant) => {
      const relative = participant.access_url || null;
      setOneTimeAccessUrl(relative ? `${window.location.origin}${relative}` : null);
      setParticipantDraft(emptyExternalParticipant);
      setShowParticipantForm(false);
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "External participant could not be invited."),
  });

  const revokeMutation = useMutation({
    mutationFn: (participantId: string) => revokeExternalAuditParticipant(amoCode, auditId, participantId),
    onSuccess: async () => {
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "External participant access could not be revoked."),
  });

  const applyChecklistMutation = useMutation({
    mutationFn: () => applyChecklistRevision(
      amoCode,
      auditId,
      effectiveTemplateRevisionId,
      checklistReason.trim(),
      allowExistingItems,
    ),
    onSuccess: async () => {
      setLocalError(null);
      setSelectedTemplateId("");
      setSelectedTemplateRevisionId("");
      setChecklistReason("Selected for this audit during governed preparation.");
      setAllowExistingItems(false);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "The controlled checklist revision could not be applied."),
  });

  const createChecklistMutation = useMutation({
    mutationFn: () => createRealtimeAuditChecklist(amoCode, auditId, {
      title: checklistTitle.trim(),
      description: checklistDescription.trim() || null,
      reason: checklistReason.trim(),
      items: checklistItems.map((item, index): ChecklistTemplateItem => ({
        section: item.section.trim() || null,
        checklist_ref: item.checklistRef.trim() || null,
        requirement_ref: item.requirementRef.trim() || null,
        prompt: item.prompt.trim(),
        expected_evidence: item.expectedEvidence.trim() || null,
        response_type: "COMPLIANCE",
        applicability: "APPLICABLE",
        mandatory: item.mandatory,
        finding_trigger: "ADVERSE_RESPONSE",
        sort_order: index,
      })),
      canonical_document_id: checklistDmsDocumentId || null,
      canonical_revision_id: checklistDmsRevisionId || null,
      allow_existing_items: allowExistingItems,
    }),
    onSuccess: async () => {
      setLocalError(null);
      setChecklistTitle("Audit fieldwork checklist");
      setChecklistDescription("");
      setChecklistReason("Created for this audit during governed preparation.");
      setChecklistItems([emptyChecklistItem()]);
      setChecklistDmsDocumentId("");
      setChecklistDmsRevisionId("");
      setAllowExistingItems(false);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "The realtime checklist could not be created."),
  });

  const requests = useMemo(() => requestsQuery.data?.items || [], [requestsQuery.data?.items]);
  const participants = participantsQuery.data?.items || [];
  const context = contextQuery.data;
  const documents = controlledDocumentsQuery.data?.items || [];
  const filterDocuments = (search: string): CanonicalDocumentControlDocument[] => {
    const needle = search.trim().toLowerCase();
    if (!needle) return documents;
    return documents.filter((document) =>
      [document.code, document.title, document.manual_type, document.status].some((value) => value?.toLowerCase().includes(needle)),
    );
  };
  const requestDocuments = filterDocuments(requestDmsSearch);
  const checklistDocuments = filterDocuments(checklistDmsSearch);
  const requestRevisions = requestControlledRevisionsQuery.data?.items || [];
  const checklistRevisions = checklistControlledRevisionsQuery.data?.items || [];
  const templates = templatesQuery.data?.items || [];
  const filteredTemplates = templates.filter((template) => {
    const needle = checklistSearch.trim().toLowerCase();
    return !needle || [template.template_code, template.title, template.description, template.category]
      .some((value) => value?.toLowerCase().includes(needle));
  });
  const realtimeChecklistValid = Boolean(
    checklistTitle.trim().length >= 3 &&
    checklistReason.trim().length >= 8 &&
    checklistItems.length &&
    checklistItems.every((item) => item.prompt.trim()) &&
    (!checklistDmsDocumentId || checklistDmsRevisionId),
  );
  const readiness = useMemo(() => {
    const required = requests.filter((request) => request.is_required && request.status !== "WAIVED");
    const accepted = required.filter((request) => request.status === "ACCEPTED").length;
    const total = required.length;
    // 0 required must never read as 100% success — that invents readiness.
    if (!total) {
      return {
        accepted: 0,
        total: 0,
        percent: null as number | null,
        label: "Not applicable",
        detail: "No required requests",
      };
    }
    const percent = Math.round((accepted / total) * 100);
    return {
      accepted,
      total,
      percent,
      label: `${percent}%`,
      detail: `${accepted} of ${total} required requests accepted`,
    };
  }, [requests]);
  const dependentQueriesLoading =
    Boolean(auditId) &&
    (contextQuery.isLoading ||
      contextQuery.isPending ||
      requestsQuery.isLoading ||
      requestsQuery.isPending ||
      participantsQuery.isLoading ||
      participantsQuery.isPending ||
      sessionQuery.isLoading ||
      sessionQuery.isPending);

  if (auditQuery.isLoading || auditQuery.isPending || dependentQueriesLoading) {
    return <div className="qms-occurrence-stage qms-occurrence-stage--loading">Loading preparation workspace…</div>;
  }

  if (auditQuery.error || !auditQuery.data) {
    return (
      <AuditStageLoadError
        className="qms-occurrence-stage qms-occurrence-stage--error"
        title="Audit occurrence unavailable"
        detail={auditOccurrenceLoadDetail(auditQuery.error)}
        onRetry={() => void auditQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "setup")}
        exitLabel="Back to Setup"
        secondaryHref={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits`}
        secondaryLabel="Audits overview"
      />
    );
  }
  const prerequisiteError = contextQuery.error || requestsQuery.error || participantsQuery.error || sessionQuery.error;
  if (prerequisiteError) {
    return (
      <AuditStageLoadError
        className="qms-occurrence-stage qms-occurrence-stage--error"
        title="Complete audit setup before preparation"
        detail={auditPrerequisiteLoadDetail(
          prerequisiteError,
          "The governed preparation context is not available yet. Complete and save the audit Setup stage, then retry preparation.",
        )}
        onRetry={() => {
          void contextQuery.refetch();
          void requestsQuery.refetch();
          void participantsQuery.refetch();
          void sessionQuery.refetch();
        }}
        exitHref={auditSessionPath(amoCode, auditKey, "setup")}
        exitLabel="Back to Setup"
      />
    );
  }
  if (!context) {
    return (
      <AuditStageLoadError
        className="qms-occurrence-stage qms-occurrence-stage--error"
        title="Complete audit setup before preparation"
        detail="The governed preparation context is not available yet. Complete and save the audit Setup stage, then retry preparation."
        onRetry={() => void contextQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "setup")}
        exitLabel="Back to Setup"
      />
    );
  }

  const prepRevision = context.controlled_preparation?.latest_revision;
  const bindings = context.controlled_preparation?.checklist_bindings || [];
  const checklistBindings = bindings.length;
  const readinessWarning = readiness.percent != null && readiness.percent < 100;
  const fieldworkOpen = isAtLeastLiveStage(sessionQuery.data?.current_stage_id);
  const stageBlocked = !fieldworkOpen;

  return (
    <section className="qms-occurrence-stage qms-audit-prepare-stage" aria-label="Pre-audit preparation workspace" id="audit-occurrence-prepare">
      <div className="qms-audit-prepare-stage__toolbar">
        <div className="qms-audit-prepare-stage__intro">
          <h2 className="qms-audit-prepare-stage__title">Prepare</h2>
          <p className="qms-audit-prepare-stage__helper">Request evidence, invite participants, and confirm readiness before fieldwork.</p>
          <div id={AUDIT_PREPARE_TOOLBAR_ID} className="qms-audit-prepare-toolbar" />
          <div className="qms-audit-prepare-stage__status" role="status" aria-label="Preparation readiness">
            <span className={`qms-audit-prepare-stage__readiness-chip${readinessWarning ? " is-warning" : ""}`}>
              Evidence {readiness.label}
            </span>
            <span className="qms-audit-prepare-stage__meta-chip">{checklistBindings} checklist(s)</span>
            {prepRevision ? <span className="qms-audit-prepare-stage__meta-chip">Prep {prepRevision.status}</span> : null}
          </div>
        </div>
        <div className="qms-audit-prepare-stage__toolbar-actions">
          {fieldworkOpen ? (
            <Link className="qms-occurrence-stage__next" to={auditSessionPath(amoCode, auditKey, "live")}>
              Open Fieldwork <ArrowRight size={16} aria-hidden />
            </Link>
          ) : (
            <span className="qms-occurrence-stage__next is-disabled" aria-disabled="true" title="Issue governed preparation before entering fieldwork">
              Continue to Fieldwork <ArrowRight size={16} aria-hidden />
            </span>
          )}
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits`}>Exit</Link>
        </div>
      </div>

      {localError ? <div className="qms-occurrence-stage__message is-error" role="alert"><AlertTriangle size={16} /> {localError}</div> : null}
      {stageBlocked ? (
        <p className="qms-audit-prepare-stage__notice is-warning">
          <ShieldAlert size={14} aria-hidden /> Fieldwork unlocks after at least one checklist is bound and the governed preparation revision is issued.
        </p>
      ) : null}
      {readinessWarning ? (
        <p className="qms-audit-prepare-stage__notice is-warning">
          <ShieldAlert size={14} aria-hidden /> {readiness.detail}
        </p>
      ) : null}

      <div className="qms-audit-prepare-stage__stack">
        <section className="qms-audit-prepare-stage__section qms-audit-prepare__basis">
          <header><div><h3>Audit basis</h3></div></header>
          <dl>
            <div><dt>Scope</dt><dd>{context.regulatory_and_manual_basis?.audit_scope || auditQuery.data.scope || "—"}</dd></div>
            <div><dt>Criteria</dt><dd>{context.regulatory_and_manual_basis?.audit_criteria || auditQuery.data.criteria || "—"}</dd></div>
            <div><dt>Checklists</dt><dd>{checklistBindings} revision(s)</dd></div>
            <div><dt>Prep revision</dt><dd>{prepRevision ? `Rev ${prepRevision.revision_no} · ${prepRevision.status}` : "Not issued"}</dd></div>
          </dl>
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__checklists">
          <header>
            <div>
              <h3>Fieldwork checklist</h3>
              <p>Select an issued checklist, search an exact DMS revision, or build audit questions now.</p>
            </div>
            <span className="qms-audit-prepare-stage__meta-chip">{checklistBindings} bound</span>
          </header>

          {bindings.length ? (
            <div className="qms-audit-prepare__binding-list" aria-label="Bound checklist revisions">
              {bindings.map((binding) => (
                <article key={binding.id}>
                  <ClipboardList size={16} aria-hidden />
                  <div><strong>{binding.template_code} · Rev {binding.revision_no}</strong><small>{binding.application_reason} · SHA {binding.content_sha256.slice(0, 12)}…</small></div>
                </article>
              ))}
            </div>
          ) : <p className="qms-audit-prepare__empty">No fieldwork checklist is bound. Fieldwork cannot open until one is selected or created.</p>}

          {canManage ? <>
            <div className="qms-audit-prepare__mode" role="tablist" aria-label="Checklist source">
              <button type="button" role="tab" aria-selected={checklistMode === "LIBRARY"} className={checklistMode === "LIBRARY" ? "is-active" : ""} onClick={() => setChecklistMode("LIBRARY")}>Use issued checklist</button>
              <button type="button" role="tab" aria-selected={checklistMode === "CREATE"} className={checklistMode === "CREATE" ? "is-active" : ""} onClick={() => setChecklistMode("CREATE")}>Create in realtime</button>
            </div>

            {checklistMode === "LIBRARY" ? (
              <form className="qms-audit-prepare__checklist-form" onSubmit={(event) => { event.preventDefault(); applyChecklistMutation.mutate(); }}>
                <label className="is-wide"><span>Search issued forms and checklists</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={checklistSearch} onChange={(event) => setChecklistSearch(event.target.value)} placeholder="Code, title, category or description" /></div></label>
                <label><span>Checklist</span><select value={selectedTemplateId} onChange={(event) => { setSelectedTemplateId(event.target.value); setSelectedTemplateRevisionId(""); }}><option value="">Select an issued checklist</option>{filteredTemplates.map((template) => <option key={template.id} value={template.id}>{template.template_code} · {template.title}</option>)}</select></label>
                <label><span>Issued revision</span><select disabled={!selectedTemplateId || selectedTemplateQuery.isLoading} value={effectiveTemplateRevisionId} onChange={(event) => setSelectedTemplateRevisionId(event.target.value)}><option value="">Select exact revision</option>{issuedTemplateRevisions.map((revision) => <option key={revision.id} value={revision.id}>Rev {revision.revision_no} · {revision.items.length} items · SHA {revision.content_sha256.slice(0, 10)}…</option>)}</select></label>
                <label className="is-wide"><span>Application reason</span><input required minLength={8} value={checklistReason} onChange={(event) => setChecklistReason(event.target.value)} /></label>
                <label className="qms-audit-prepare__check is-wide"><input type="checkbox" checked={allowExistingItems} onChange={(event) => setAllowExistingItems(event.target.checked)} /> Add to the existing live checklist instead of replacing an empty checklist</label>
                {templatesQuery.error ? <p className="qms-audit-prepare-stage__notice is-warning is-wide"><AlertTriangle size={14} /> Issued checklist library could not be loaded. You can still create this audit’s checklist in realtime.</p> : null}
                <footer><button type="submit" className="is-primary" disabled={!effectiveTemplateRevisionId || checklistReason.trim().length < 8 || applyChecklistMutation.isPending}>{applyChecklistMutation.isPending ? "Applying…" : "Bind issued revision"}</button></footer>
              </form>
            ) : (
              <form className="qms-audit-prepare__checklist-form" onSubmit={(event) => { event.preventDefault(); createChecklistMutation.mutate(); }}>
                <label><span>Checklist title</span><input required minLength={3} value={checklistTitle} onChange={(event) => setChecklistTitle(event.target.value)} /></label>
                <label><span>Creation reason</span><input required minLength={8} value={checklistReason} onChange={(event) => setChecklistReason(event.target.value)} /></label>
                <label className="is-wide"><span>Description</span><textarea rows={2} value={checklistDescription} onChange={(event) => setChecklistDescription(event.target.value)} placeholder="Audit-specific purpose and coverage" /></label>

                <fieldset className="qms-audit-prepare__dms-source is-wide">
                  <legend>Optional controlled DMS source</legend>
                  <p>Link the exact uploaded form, checklist or manual revision used to construct these questions.</p>
                  <label><span>Search DMS</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={checklistDmsSearch} onChange={(event) => setChecklistDmsSearch(event.target.value)} placeholder="Document code, title or type" /></div></label>
                  <label><span>Controlled document</span><select value={checklistDmsDocumentId} onChange={(event) => { setChecklistDmsDocumentId(event.target.value); setChecklistDmsRevisionId(""); }}><option value="">No DMS source</option>{checklistDocuments.map((document) => <option key={document.id} value={document.id}>{document.code} · {document.title} · {statusLabel(document.status)}</option>)}</select></label>
                  <label><span>Exact controlled revision</span><select disabled={!checklistDmsDocumentId} value={checklistDmsRevisionId} onChange={(event) => setChecklistDmsRevisionId(event.target.value)}><option value="">{checklistDmsDocumentId ? "Select exact revision" : "Select a document first"}</option>{checklistRevisions.map((revision) => <option key={revision.id} value={revision.id}>Issue {revision.issue_number || "—"} · Rev {revision.revision_number} · {statusLabel(revision.status)}{revision.source_sha256 ? ` · ${revision.source_sha256.slice(0, 10)}…` : ""}</option>)}</select></label>
                </fieldset>

                <div className="qms-audit-prepare__composer is-wide">
                  <header><div><strong>Checklist questions</strong><small>Questions remain editable here; after preparation is issued they become governed fieldwork rows.</small></div><button type="button" onClick={() => setChecklistItems((current) => [...current, emptyChecklistItem()])}><Plus size={14} /> Add question</button></header>
                  {checklistItems.map((item, index) => (
                    <article key={item.id}>
                      <div className="qms-audit-prepare__composer-number">{index + 1}</div>
                      <div className="qms-audit-prepare__composer-fields">
                        <label className="is-wide"><span>Question / verification step</span><textarea required rows={2} value={item.prompt} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, prompt: event.target.value } : entry))} /></label>
                        <label><span>Section</span><input value={item.section} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, section: event.target.value } : entry))} /></label>
                        <label><span>Checklist reference</span><input value={item.checklistRef} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, checklistRef: event.target.value } : entry))} /></label>
                        <label><span>Requirement / manual reference</span><input value={item.requirementRef} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, requirementRef: event.target.value } : entry))} /></label>
                        <label><span>Expected objective evidence</span><input value={item.expectedEvidence} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, expectedEvidence: event.target.value } : entry))} /></label>
                        <label className="qms-audit-prepare__check is-wide"><input type="checkbox" checked={item.mandatory} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, mandatory: event.target.checked } : entry))} /> Mandatory fieldwork item</label>
                      </div>
                      <button type="button" aria-label={`Remove checklist question ${index + 1}`} disabled={checklistItems.length === 1} onClick={() => setChecklistItems((current) => current.filter((entry) => entry.id !== item.id))}><Trash2 size={15} /></button>
                    </article>
                  ))}
                </div>
                <label className="qms-audit-prepare__check is-wide"><input type="checkbox" checked={allowExistingItems} onChange={(event) => setAllowExistingItems(event.target.checked)} /> Append these questions to the existing live checklist</label>
                {controlledDocumentsQuery.error ? <p className="qms-audit-prepare-stage__notice is-warning is-wide"><AlertTriangle size={14} /> DMS search is unavailable. Remove the DMS selection to create an audit-specific checklist without a controlled source link.</p> : null}
                <footer><button type="submit" className="is-primary" disabled={!realtimeChecklistValid || createChecklistMutation.isPending}>{createChecklistMutation.isPending ? "Creating and issuing…" : "Create, issue and bind checklist"}</button></footer>
              </form>
            )}
          </> : null}
        </section>

        <section className="qms-audit-prepare-stage__section">
          <header>
            <div><h3>Document requests</h3></div>
            {canManage ? <button type="button" onClick={() => setShowRequestForm((value) => !value)}><Plus size={15} /> New request</button> : null}
          </header>

            {showRequestForm ? (
              <form className="qms-audit-prepare__request-form" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(); }}>
                <label><span>Request type</span><select value={newRequest.requestType} onChange={(event) => setNewRequest((current) => ({ ...current, requestType: event.target.value as NewRequest["requestType"] }))}><option>DOCUMENT</option><option>RECORD</option><option>MANUAL</option><option>FORM</option><option>CERTIFICATE</option><option>REGISTER</option><option>OTHER</option></select></label>
                <label><span>Due date</span><input type="date" value={newRequest.dueDate} onChange={(event) => setNewRequest((current) => ({ ...current, dueDate: event.target.value }))} /></label>
                <label className="is-wide"><span>Request title</span><input required minLength={2} value={newRequest.title} onChange={(event) => setNewRequest((current) => ({ ...current, title: event.target.value }))} /></label>
                <label className="is-wide"><span>Purpose / records required</span><textarea rows={3} value={newRequest.description} onChange={(event) => setNewRequest((current) => ({ ...current, description: event.target.value }))} /></label>
                <label className="is-wide"><span>Linked criterion / requirement</span><textarea rows={2} value={newRequest.linkedCriterion} onChange={(event) => setNewRequest((current) => ({ ...current, linkedCriterion: event.target.value }))} placeholder="Exact regulation, manual paragraph, procedure or checklist criterion this evidence supports" /></label>
                <label><span>Submission source</span><select value={newRequest.sourceMode} onChange={(event) => setNewRequest((current) => ({ ...current, sourceMode: event.target.value as NewRequest["sourceMode"], controlledDocumentId: "", controlledRevisionId: "" }))}><option value="UPLOAD_OR_CONTROLLED">Upload or controlled DMS record</option><option value="UPLOAD">Upload only</option><option value="CONTROLLED_DMS">Controlled DMS record only</option></select></label>
                <label className="qms-audit-prepare__check"><input type="checkbox" checked={newRequest.isRequired} onChange={(event) => setNewRequest((current) => ({ ...current, isRequired: event.target.checked }))} /> Required before fieldwork</label>
                {newRequest.sourceMode !== "UPLOAD" ? <>
                  <label className="is-wide"><span>Search controlled DMS</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={requestDmsSearch} onChange={(event) => setRequestDmsSearch(event.target.value)} placeholder="Document code, title or type" /></div></label>
                  <label><span>Controlled document</span><select value={newRequest.controlledDocumentId} onChange={(event) => setNewRequest((current) => ({ ...current, controlledDocumentId: event.target.value, controlledRevisionId: "" }))}><option value="">No preselected document</option>{requestDocuments.map((document) => <option key={document.id} value={document.id}>{document.code} · {document.title} · {statusLabel(document.status)}</option>)}</select></label>
                  <label><span>Exact controlled revision</span><select disabled={!newRequest.controlledDocumentId} value={newRequest.controlledRevisionId} onChange={(event) => setNewRequest((current) => ({ ...current, controlledRevisionId: event.target.value }))}><option value="">{newRequest.controlledDocumentId ? "Select exact revision" : "Select a document first"}</option>{requestRevisions.map((revision) => <option key={revision.id} value={revision.id}>Issue {revision.issue_number || "—"} · Rev {revision.revision_number} · {statusLabel(revision.status)}{revision.source_sha256 ? ` · ${revision.source_sha256.slice(0, 10)}…` : ""}</option>)}</select></label>
                </> : null}
                <footer><button type="button" onClick={() => { setShowRequestForm(false); setNewRequest(emptyRequest); }}>Cancel</button><button type="submit" className="is-primary" disabled={createMutation.isPending || (newRequest.sourceMode === "CONTROLLED_DMS" && (!newRequest.controlledDocumentId || !newRequest.controlledRevisionId)) || Boolean(newRequest.controlledDocumentId && !newRequest.controlledRevisionId)}>{createMutation.isPending ? "Creating…" : "Create governed request"}</button></footer>
              </form>
            ) : null}

            <div className="qms-audit-prepare__request-list">
              {!requests.length ? <p className="qms-audit-prepare__empty">No pre-audit document requests have been recorded.</p> : null}
              {requests.map((request) => (
                <article key={request.id} data-status={request.status}>
                  <div className="qms-audit-prepare__request-main">
                    <span className="qms-audit-prepare__status">{statusLabel(request.status)}</span>
                    <strong>{request.title}</strong>
                    <p>{request.description || "No additional instructions."}</p>
                    <small>{request.request_type.replaceAll("_", " ")} · {request.is_required ? "Required" : "Optional"} · {request.source_mode.replaceAll("_", " ")}</small>
                    {request.linked_criterion ? <blockquote><strong>Criterion:</strong> {request.linked_criterion}</blockquote> : null}
                    <small>Due {request.due_date || "not specified"}{request.uploaded_at ? ` · submitted ${new Date(request.uploaded_at).toLocaleString()}` : ""}</small>
                    {request.canonical_document_id ? <code><Link2 size={13} /> DMS document {request.canonical_document_id}{request.canonical_revision_id ? ` · revision ${request.canonical_revision_id}` : ""}</code> : null}
                    {request.review_note ? <blockquote>{request.review_note}</blockquote> : null}
                  </div>
                  {canManage && ["UPLOADED", "REJECTED"].includes(request.status) ? (
                    <div className="qms-audit-prepare__review">
                      <textarea rows={2} value={reviewNotes[request.id] || ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [request.id]: event.target.value }))} placeholder="Review note / return instructions" />
                      <div><button type="button" onClick={() => reviewMutation.mutate({ request, status: "REJECTED" })} disabled={reviewMutation.isPending}>Return / reject</button><button type="button" className="is-primary" onClick={() => reviewMutation.mutate({ request, status: "ACCEPTED" })} disabled={reviewMutation.isPending}><CheckCircle2 size={14} /> Accept</button></div>
                    </div>
                  ) : null}
                  {canManage && request.status === "REQUESTED" && !request.is_required ? <button type="button" onClick={() => reviewMutation.mutate({ request, status: "WAIVED" })} disabled={reviewMutation.isPending}>Waive optional request</button> : null}
                </article>
              ))}
            </div>
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__participants">
          <header>
            <div><h3>External participants</h3></div>
            {canManage ? <button type="button" onClick={() => setShowParticipantForm((value) => !value)}><UserPlus size={15} /> Invite</button> : null}
          </header>

            {oneTimeAccessUrl ? <div className="qms-audit-prepare__one-time-link" role="status"><div><strong>Invitation link ready</strong><small>Copy now — the token is shown once.</small></div><button type="button" onClick={() => void navigator.clipboard.writeText(oneTimeAccessUrl)}><Copy size={14} /> Copy link</button></div> : null}

            {showParticipantForm ? <form className="qms-audit-prepare__participant-form" onSubmit={(event) => { event.preventDefault(); participantMutation.mutate(); }}>
              <label><span>Participant type</span><select value={participantDraft.participantType} onChange={(event) => { const participantType = event.target.value as ExternalParticipantType; setParticipantDraft((current) => ({ ...current, participantType, role: participantType === "AUDITEE_GUEST" ? "AUDITEE" : "AUDITOR", assuranceLevel: participantType === "AUDITEE_GUEST" ? "EMAIL_LINK" : current.assuranceLevel })); }}><option value="AUDITEE_GUEST">Auditee guest</option><option value="EXTERNAL_AUDITOR">External auditor</option></select></label>
              <label><span>Role</span><input required value={participantDraft.role} onChange={(event) => setParticipantDraft((current) => ({ ...current, role: event.target.value }))} /></label>
              <label><span>Full name</span><input required minLength={2} value={participantDraft.displayName} onChange={(event) => setParticipantDraft((current) => ({ ...current, displayName: event.target.value }))} /></label>
              <label><span>Email</span><input required type="email" value={participantDraft.email} onChange={(event) => setParticipantDraft((current) => ({ ...current, email: event.target.value }))} /></label>
              <label><span>Organisation</span><input value={participantDraft.organisation} onChange={(event) => setParticipantDraft((current) => ({ ...current, organisation: event.target.value }))} /></label>
              <label><span>Access expires</span><input required type="datetime-local" value={participantDraft.expiresAt} onChange={(event) => setParticipantDraft((current) => ({ ...current, expiresAt: event.target.value }))} /></label>
              <label><span>Identity assurance</span><select value={participantDraft.assuranceLevel} onChange={(event) => setParticipantDraft((current) => ({ ...current, assuranceLevel: event.target.value as ExternalParticipantDraft["assuranceLevel"] }))}><option value="EMAIL_LINK">Email link</option>{participantDraft.participantType === "EXTERNAL_AUDITOR" ? <option value="PASSKEY">Passkey required</option> : null}</select></label>
              <fieldset className="is-wide"><legend>Scoped access</legend><label><input type="checkbox" checked={participantDraft.readProgress} onChange={(event) => setParticipantDraft((current) => ({ ...current, readProgress: event.target.checked }))} /> View fieldwork progress</label>{participantDraft.participantType === "AUDITEE_GUEST" ? <label><input type="checkbox" checked={participantDraft.readReleasedEvidence} onChange={(event) => setParticipantDraft((current) => ({ ...current, readReleasedEvidence: event.target.checked }))} /> View evidence explicitly released with findings</label> : <><label><input type="checkbox" checked={participantDraft.executeChecklist} onChange={(event) => setParticipantDraft((current) => ({ ...current, executeChecklist: event.target.checked }))} /> Execute assigned checklist</label><label><input type="checkbox" checked={participantDraft.createEvidence} onChange={(event) => setParticipantDraft((current) => ({ ...current, createEvidence: event.target.checked }))} /> Add audit evidence</label><label><input type="checkbox" checked={participantDraft.draftFinding} onChange={(event) => setParticipantDraft((current) => ({ ...current, draftFinding: event.target.checked }))} /> Draft findings</label></>}</fieldset>
              <p className="is-wide">Auditees use email-link access. External auditors may require a passkey when configured.</p>
              <footer><button type="button" onClick={() => setShowParticipantForm(false)}>Cancel</button><button type="submit" className="is-primary" disabled={!participantDraft.expiresAt || participantMutation.isPending}>{participantMutation.isPending ? "Creating access…" : "Create invitation"}</button></footer>
            </form> : null}

            <div className="qms-audit-prepare__participant-list">
              {!participants.length ? <p className="qms-audit-prepare__empty">No external participants are assigned to this audit.</p> : participants.map((participant) => <article key={participant.id}><div><span>{participant.participant_type.replaceAll("_", " ")}</span><strong>{participant.display_name || participant.email || "External participant"}</strong><small>{participant.organisation || "No organisation"} · {participant.role} · {participant.assurance_level || "EMAIL_LINK"}</small><small>{participant.permissions.join(" · ")}</small><small>Expires {new Date(participant.expires_at).toLocaleString()} · {participant.status}</small></div>{canManage && participant.status !== "REVOKED" ? <button type="button" onClick={() => revokeMutation.mutate(participant.id)} disabled={revokeMutation.isPending}><UserX size={14} /> Revoke</button> : null}</article>)}
            </div>
        </section>
      </div>
    </section>
  );
};

export default AuditPrepareWorkspace;
