import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Copy,
  DownloadCloud,
  HardDrive,
  History,
  Link2,
  Plus,
  Search,
  ShieldAlert,
  Trash2,
  UploadCloud,
  UserPlus,
  UserX,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import ControlledDocumentUploadDialog from "../../../components/documentControl/ControlledDocumentUploadDialog";
import { useToast } from "../../../components/feedback/ToastProvider";
import {
  createAuditPreparationRevision,
  getAuditPreparationReadiness,
  issueAuditPreparationRevision,
  listAuditActivity,
  listAuditPreparationRevisions,
} from "../../../services/qmsAuditGovernance";
import {
  bindCurrentDmsChecklist,
  createRealtimeAuditChecklist,
  listChecklistBindings,
  listCurrentDmsChecklists,
  uploadDmsChecklistFromAudit,
  type ChecklistBinding,
  type ChecklistCanonicalStatus,
  type ChecklistResponseOption,
  type ChecklistTemplateItem,
} from "../../../services/qmsChecklistTemplates";
import {
  addAuditApplicabilityFact,
  getAuditApplicabilityContext,
  removeAuditApplicabilityFact,
} from "../../../services/qmsChecklistExecutionGovernance";
import {
  createExternalAuditParticipant,
  listExternalAuditParticipants,
  revokeExternalAuditParticipant,
  type ExternalParticipantType,
} from "../../../services/qmsAuditExternalAccess";
import {
  createGovernedAuditDocumentRequest,
  listCanonicalDocumentControlDocuments,
  listGovernedAuditDocumentRequests,
  updateGovernedAuditDocumentRequest,
  type CanonicalDocumentControlDocument,
  type GovernedAuditDocumentRequest,
} from "../../../services/qmsAuditOccurrenceCompletion";
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { getAuditPreparationContext } from "../../../services/qmsAuditPreparationContext";
import {
  auditOfflinePackStatus,
  prepareAuditOfflinePack,
  removeAuditOfflinePack,
  type AuditOfflinePackStatus,
} from "../../../services/qmsAuditOfflinePack";
import { getAuditSession } from "../../../services/qmsAuditSession";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditOccurrenceLoadDetail, auditPrerequisiteLoadDetail } from "./auditStageLoadErrorMessages";
import { auditSessionPath, isAtLeastLiveStage } from "./auditSessionRoutes";
import { AUDIT_PREPARE_TOOLBAR_ID } from "./OccurrenceToolbarPortal";
import "../../../styles/qms-audit-prepare-workspace.css";

type Props = { amoCode: string; auditKey: string };

const preparationRecordSourceTypes = new Set(["QMS_AUDIT", "QUALITY_AUDIT_CHECKLIST_ITEM", "QUALITY_AUDIT_DOCUMENT_REQUEST", "QUALITY_AUDIT_CHECKLIST_BINDING"]);
const controlledDocumentSources = (sources: unknown[]) => {
  const documents = new Map<string, unknown>();
  let recordCount = 0;
  for (const source of sources) {
    const reference = source && typeof source === "object" && !Array.isArray(source) ? source as Record<string, unknown> : {};
    if (preparationRecordSourceTypes.has(String(reference.source_type || ""))) { recordCount += 1; continue; }
    const key = reference.document_id && reference.revision_id ? `${reference.document_id}:${reference.revision_id}` : JSON.stringify(source);
    documents.set(key ?? String(source), source);
  }
  return { documents: [...documents.values()], recordCount };
};

const ControlledSourceReference: React.FC<{ source: unknown; index: number }> = ({ source, index }) => {
  const reference = source && typeof source === "object" && !Array.isArray(source) ? source as Record<string, unknown> : {};
  const value = (...keys: string[]) => keys.map((key) => reference[key]).map((item) => typeof item === "string" ? item.trim() : typeof item === "number" && Number.isFinite(item) ? String(item) : "").find(Boolean);
  const title = typeof source === "string" ? source : value("document_title", "title", "source_title") || `Controlled reference ${index + 1}`;
  const code = value("document_code", "doc_code", "reference_ref");
  const revision = value("revision_number", "rev_no");
  const issue = value("issue_number", "issue_no");
  const hash = value("source_sha256", "content_sha256", "sha256");
  const route = value("source_route");
  return <article className="qms-audit-prepare__reference-card">
    <div><strong>{code ? `${code} · ${title}` : title}</strong><small>{[issue ? `Issue ${issue}` : null, revision ? `Rev ${revision}` : null, value("revision_status"), value("source_type")].filter(Boolean).join(" · ") || "Retained audit source"}</small></div>
    {value("source_filename") ? <p>{value("source_filename")}</p> : null}
    {route?.startsWith("/") && !route.startsWith("//") ? <Link to={route}>Open source <ArrowRight size={14} aria-hidden /></Link> : null}
    {hash ? <details><summary>File verification</summary><small>SHA-256 identifies the exact source file retained for this audit.</small><code>{hash}</code></details> : null}
  </article>;
};

type NewRequest = {
  title: string;
  description: string;
  dueDate: string;
  requestType: GovernedAuditDocumentRequest["request_type"];
  linkedCriterion: string;
  responsibleParty: string;
  checklistItemIds: string[];
  isRequired: boolean;
  requirementStage: GovernedAuditDocumentRequest["requirement_stage"];
  sourceMode: GovernedAuditDocumentRequest["source_mode"];
  controlledDocumentId: string;
};

type ChecklistComposerItem = {
  id: string;
  section: string;
  checklistRef: string;
  requirementRef: string;
  prompt: string;
  expectedEvidence: string;
  guidance: string;
  evidenceContext: "GENERAL" | "CAPABILITY_SCOPE" | "PERSONNEL_AUTHORIZATION" | "CONTRACT_SCOPE" | "TECHNICAL_DATA" | "RECORD_RETENTION" | "TOOLING_CALIBRATION" | "FACILITY";
  auditMethod: "" | "RECORD_REVIEW" | "INTERVIEW" | "OBSERVATION" | "SAMPLE" | "TEST";
  samplingRequirement: string;
  evidenceTypes: string;
  evidenceRequiredWhen: ChecklistCanonicalStatus[];
  notesRequiredWhen: ChecklistCanonicalStatus[];
  naJustificationRequired: boolean;
  responseType: "COMPLIANCE" | "YES_NO_NA" | "CUSTOM";
  responseOptions: ChecklistResponseOption[];
  applicability: string;
  applicabilityReason: string;
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
  responsibleParty: "",
  checklistItemIds: [],
  isRequired: true,
  requirementStage: "REQUIRED_BEFORE_FIELDWORK",
  sourceMode: "UPLOAD_OR_CONTROLLED",
  controlledDocumentId: "",
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

function customResponseOptions(): ChecklistResponseOption[] {
  return [
    { value: "YES", label: "Yes", canonical_status: "COMPLIANT" },
    { value: "NO", label: "No", canonical_status: "NONCOMPLIANT" },
    { value: "N/A", label: "N/A", canonical_status: "NOT_APPLICABLE" },
    { value: "U", label: "U", canonical_status: "" },
    { value: "S", label: "S", canonical_status: "" },
  ];
}

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
    guidance: "",
    evidenceContext: "GENERAL",
    auditMethod: "",
    samplingRequirement: "",
    evidenceTypes: "",
    evidenceRequiredWhen: [],
    notesRequiredWhen: [],
    naJustificationRequired: false,
    responseType: "COMPLIANCE",
    responseOptions: [],
    applicability: "APPLICABLE",
    applicabilityReason: "",
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
  const { pushToast } = useToast();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [showParticipantForm, setShowParticipantForm] = useState(false);
  const [newRequest, setNewRequest] = useState<NewRequest>(emptyRequest);
  const [participantDraft, setParticipantDraft] = useState<ExternalParticipantDraft>(emptyExternalParticipant);
  const [oneTimeAccessUrl, setOneTimeAccessUrl] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState<string | null>(null);
  const [localSuccess, setLocalSuccess] = useState<string | null>(null);
  const [checklistMode, setChecklistMode] = useState<"LIBRARY" | "CREATE">("LIBRARY");
  const [checklistSearch, setChecklistSearch] = useState("");
  const [selectedDmsChecklistId, setSelectedDmsChecklistId] = useState<string | null>(null);
  const [checklistDocumentType, setChecklistDocumentType] = useState<"CHECKLIST" | "FORM">("CHECKLIST");
  const [dmsResponseType, setDmsResponseType] = useState<"" | "COMPLIANCE" | "YES_NO_NA" | "CUSTOM">("");
  const [dmsResponseOptions, setDmsResponseOptions] = useState<ChecklistResponseOption[]>([]);
  const [checklistUploadOpen, setChecklistUploadOpen] = useState(false);
  const [checklistReason, setChecklistReason] = useState("Selected for this audit during governed preparation.");
  const [allowExistingItems, setAllowExistingItems] = useState(false);
  const [checklistTitle, setChecklistTitle] = useState("Audit fieldwork checklist");
  const [checklistDescription, setChecklistDescription] = useState("");
  const [checklistItems, setChecklistItems] = useState<ChecklistComposerItem[]>([emptyChecklistItem()]);
  const [checklistDmsSearch, setChecklistDmsSearch] = useState("");
  const [checklistDmsDocumentId, setChecklistDmsDocumentId] = useState("");
  const [requestDmsSearch, setRequestDmsSearch] = useState("");
  const [composerSearch, setComposerSearch] = useState("");
  const [composerSection, setComposerSection] = useState("ALL");
  const [composerFilter, setComposerFilter] = useState<"ALL" | "INCOMPLETE" | "EVIDENCE_REQUIRED" | "APPLICABILITY_RULE">("ALL");
  const [applicabilitySearch, setApplicabilitySearch] = useState("");
  const [applicabilityReason, setApplicabilityReason] = useState("Selected as governed applicability context for this audit scope.");

  useEffect(() => {
    if (localError) pushToast({ title: "Preparation action needs attention", message: localError, variant: "error" });
  }, [localError, pushToast]);
  useEffect(() => {
    if (localSuccess) pushToast({ title: "Audit preparation updated", message: localSuccess, variant: "success" });
  }, [localSuccess, pushToast]);

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
  const applicabilityQuery = useQuery({
    queryKey: ["qms-audit-applicability-context", amoCode, auditId],
    queryFn: ({ signal }) => getAuditApplicabilityContext(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const fullBindingsQuery = useQuery({
    queryKey: ["qms", "prepare-checklist-bindings", amoCode, auditId],
    queryFn: ({ signal }) => listChecklistBindings(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 3_000,
  });
  const controlledDocumentsQuery = useQuery({
    queryKey: ["qms-canonical-document-control-documents", amoCode, auditId],
    queryFn: ({ signal }) => listCanonicalDocumentControlDocuments(amoCode, auditId, signal),
    enabled: Boolean(auditId && canManage),
    staleTime: 30_000,
  });
  const dmsChecklistsQuery = useQuery({
    queryKey: ["qms-current-dms-checklists", amoCode, auditId, checklistSearch, checklistDocumentType],
    queryFn: ({ signal }) => listCurrentDmsChecklists(amoCode, auditId, { q: checklistSearch, documentType: checklistDocumentType }, signal),
    enabled: Boolean(auditId && canManage),
    staleTime: 5_000,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });
  const preparationRevisionsQuery = useQuery({
    queryKey: ["qms-audit-preparation-revisions", amoCode, auditId],
    queryFn: ({ signal }) => listAuditPreparationRevisions(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const readinessQuery = useQuery({
    queryKey: ["qms-audit-preparation-readiness", amoCode, auditId],
    queryFn: ({ signal }) => getAuditPreparationReadiness(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });
  const activityQuery = useQuery({
    queryKey: ["qms-audit-activity", amoCode, auditId],
    queryFn: ({ signal }) => listAuditActivity(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const offlinePackQuery = useQuery({
    queryKey: ["qms-audit-offline-pack-status", amoCode, auditId],
    queryFn: () => auditOfflinePackStatus(amoCode, auditId),
    enabled: Boolean(auditId),
    staleTime: 1_000,
  });
  const candidateDmsChecklistId = selectedDmsChecklistId ?? dmsChecklistsQuery.data?.recommendation?.document_id ?? "";
  const effectiveDmsChecklistId = (dmsChecklistsQuery.data?.items || []).some((item) => item.document_id === candidateDmsChecklistId)
    ? candidateDmsChecklistId : "";

  const refresh = async () => {
    // Cancel older reads, then reconcile every preparation indicator from the server.
    // Never seed the authoritative preparation/readiness caches from mutation payloads.
    await queryClient.cancelQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] });
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["qms-audit-preparation-context", amoCode, auditId],
        refetchType: "active",
      }),
      queryClient.invalidateQueries({ queryKey: ["qms-governed-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-external-participants", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-revisions", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-readiness", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-applicability-context", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "prepare-checklist-bindings", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-activity", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-current-dms-checklists", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-execution", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-checklist", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-bindings", amoCode, auditId] }),
    ]);
  };

  const confirmChecklistBinding = async (binding: ChecklistBinding): Promise<boolean> => {
    const bindingQueryKey = ["qms", "prepare-checklist-bindings", amoCode, auditId] as const;
    await Promise.all([
      queryClient.cancelQueries({ queryKey: ["qms-audit-preparation-context", amoCode, auditId] }),
      queryClient.cancelQueries({ queryKey: bindingQueryKey }),
    ]);

    // Checklist binding authority is the immutable binding table used by the
    // preparation/fieldwork backend. The aggregate context is a secondary projection
    // and must never erase or veto a binding already confirmed by canonical authority.
    const bindingsConfirmation = await listChecklistBindings(amoCode, auditId);
    const confirmed = Boolean(bindingsConfirmation.items?.some((item) => item.id === binding.id));
    if (!confirmed) return false;
    queryClient.setQueryData(bindingQueryKey, bindingsConfirmation);

    try {
      const contextConfirmation = await getAuditPreparationContext(amoCode, auditId);
      queryClient.setQueryData(["qms-audit-preparation-context", amoCode, auditId], contextConfirmation);
    } catch {
      void queryClient.invalidateQueries({
        queryKey: ["qms-audit-preparation-context", amoCode, auditId],
        refetchType: "active",
      });
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-governed-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-document-requests", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-external-participants", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-revisions", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-preparation-readiness", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-activity", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-current-dms-checklists", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-execution", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-checklist", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-bindings", amoCode, auditId] }),
    ]);
    return true;
  };
  const createMutation = useMutation({
    mutationFn: () => createGovernedAuditDocumentRequest(amoCode, auditId, {
      title: newRequest.title.trim(),
      description: newRequest.description.trim() || null,
      due_date: newRequest.dueDate || null,
      request_type: newRequest.requestType,
      linked_criterion: newRequest.linkedCriterion.trim() || null,
      responsible_party: newRequest.responsibleParty.trim() || null,
      checklist_item_ids: newRequest.checklistItemIds,
      is_required: newRequest.requirementStage !== "REQUESTED_NOT_BLOCKING",
      requirement_stage: newRequest.requirementStage,
      source_mode: newRequest.sourceMode,
      controlled_source_system: "DOCUMENT_CONTROL",
      controlled_document_id: null,
      controlled_revision_id: null,
      canonical_document_id: newRequest.sourceMode !== "UPLOAD" && newRequest.controlledDocumentId ? newRequest.controlledDocumentId : null,
      canonical_revision_id: null,
    }),
    onSuccess: async () => {
      setNewRequest(emptyRequest);
      setLocalSuccess("Document request created.");
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
      setLocalSuccess(`Document request ${statusLabel(updated.status).toLowerCase()}.`);
      setReviewNotes((current) => ({ ...current, [updated.id]: "" }));
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Document review decision failed."),
  });

  const participantMutation = useMutation({
    mutationFn: () => {
      const expiry = new Date(participantDraft.expiresAt);
      if (!Number.isFinite(expiry.getTime()) || expiry.getTime() <= Date.now()) {
        throw new Error("Choose an access expiry date and time in the future.");
      }
      return createExternalAuditParticipant(amoCode, auditId, {
        email: participantDraft.email.trim(),
        display_name: participantDraft.displayName.trim(),
        organisation: participantDraft.organisation.trim() || null,
        participant_type: participantDraft.participantType,
        role: participantDraft.role.trim(),
        permissions: participantPermissions(participantDraft),
        assurance_level: participantDraft.assuranceLevel,
        expires_at: expiry.toISOString(),
      });
    },
    onSuccess: async (participant) => {
      const relative = participant.access_url || null;
      setOneTimeAccessUrl(relative ? `${window.location.origin}${relative}` : null);
      setParticipantDraft(emptyExternalParticipant);
      setLocalSuccess("Participant access created. Copy the invitation link shown below.");
      setShowParticipantForm(false);
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "External participant could not be invited."),
  });

  const revokeMutation = useMutation({
    mutationFn: (participantId: string) => revokeExternalAuditParticipant(amoCode, auditId, participantId),
    onSuccess: async () => {
      setLocalSuccess("Participant access revoked.");
      setLocalError(null);
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "External participant access could not be revoked."),
  });

  const applyChecklistMutation = useMutation({
    mutationFn: () => bindCurrentDmsChecklist(
      amoCode,
      auditId,
      effectiveDmsChecklistId,
      checklistReason.trim(),
      allowExistingItems,
      dmsResponseType,
      dmsResponseType === "CUSTOM" ? dmsResponseOptions : [],
    ),
    onSuccess: async (binding) => {
      setLocalError(null);
      setLocalSuccess(null);
      try {
        const confirmed = await confirmChecklistBinding(binding);
        if (!confirmed) {
          setLocalError("The checklist was saved, but Prepare has not confirmed the authoritative fieldwork binding yet. Refresh and verify the checklist shows as bound before issuing preparation.");
          return;
        }
        setSelectedDmsChecklistId("");
        setChecklistReason("Selected for this audit during governed preparation.");
        setAllowExistingItems(false);
        setDmsResponseType("");
        setDmsResponseOptions([]);
        setLocalSuccess("The current effective DMS checklist is bound to fieldwork.");
      } catch (error) {
        setLocalSuccess(null);
        setLocalError(error instanceof Error
          ? `The checklist was saved, but Prepare could not verify the authoritative binding: ${error.message}`
          : "The checklist was saved, but Prepare could not verify the authoritative binding. Refresh before continuing.");
      }
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
        guidance: item.guidance.trim() || null,
        evidence_context: item.evidenceContext,
        audit_method: item.auditMethod || null,
        sampling_requirement: item.samplingRequirement.trim() || null,
        evidence_types: item.evidenceTypes.split(",").map((value) => value.trim()).filter(Boolean),
        evidence_required_when: item.evidenceRequiredWhen,
        notes_required_when: item.notesRequiredWhen,
        na_justification_required: item.naJustificationRequired,
        conditional_logic: {},
        response_type: item.responseType,
        response_options: item.responseType === "CUSTOM" ? item.responseOptions : [],
        applicability: item.applicability.trim() || "APPLICABLE",
        applicability_reason: item.applicabilityReason.trim() || null,
        mandatory: item.mandatory,
        finding_trigger: "ADVERSE_RESPONSE",
        sort_order: index,
      })),
      canonical_document_id: checklistDmsDocumentId || null,
      canonical_revision_id: null,
      allow_existing_items: allowExistingItems,
    }),
    onSuccess: async (binding) => {
      setLocalError(null);
      setLocalSuccess(null);
      try {
        const confirmed = await confirmChecklistBinding(binding);
        if (!confirmed) {
          setLocalError("The checklist was created, but Prepare has not confirmed the authoritative fieldwork binding yet. Refresh and verify the checklist shows as bound before issuing preparation.");
          return;
        }
        setChecklistTitle("Audit fieldwork checklist");
        setChecklistDescription("");
        setChecklistReason("Created for this audit during governed preparation.");
        setChecklistItems([emptyChecklistItem()]);
        setChecklistDmsDocumentId("");
        setAllowExistingItems(false);
        setLocalSuccess("Checklist created and bound to fieldwork.");
      } catch (error) {
        setLocalSuccess(null);
        setLocalError(error instanceof Error
          ? `The checklist was created, but Prepare could not verify the authoritative binding: ${error.message}`
          : "The checklist was created, but Prepare could not verify the authoritative binding. Refresh before continuing.");
      }
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "The realtime checklist could not be created."),
  });

  const issuePreparationMutation = useMutation({
    mutationFn: async () => {
      const latest = preparationRevisionsQuery.data?.items?.[0];
      const draft = latest?.status === "DRAFT"
        ? latest
        : await createAuditPreparationRevision(amoCode, auditId, {
            reason: "Issue the current governed audit preparation for fieldwork.",
          });
      return issueAuditPreparationRevision(
        amoCode,
        auditId,
        draft.id,
        "Current scope, checklist and required evidence are confirmed for fieldwork.",
      );
    },
    onSuccess: async () => {
      setLocalError(null);
      setLocalSuccess("Preparation issued. Resolve any remaining pre-fieldwork evidence requests, then open Fieldwork.");
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Audit preparation could not be issued."),
  });

  const offlinePackMutation = useMutation({
    mutationFn: () => prepareAuditOfflinePack(amoCode, auditId),
    onSuccess: ({ status }) => {
      queryClient.setQueryData<AuditOfflinePackStatus>(
        ["qms-audit-offline-pack-status", amoCode, auditId],
        status,
      );
      setLocalError(null);
      setLocalSuccess(`Offline audit package ready on this device · ${status.checklistItems} checklist item(s) · ${status.evidenceRecords} evidence record(s) · ${status.offlineReferences} controlled reference(s).`);
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "The audit could not be prepared for offline fieldwork."),
  });

  const removeOfflinePackMutation = useMutation({
    mutationFn: () => removeAuditOfflinePack(auditId),
    onSuccess: () => {
      queryClient.setQueryData<AuditOfflinePackStatus>(
        ["qms-audit-offline-pack-status", amoCode, auditId],
        { ready: false, storedAt: null, verifiedAt: null, workPackageSha256: null, checklistItems: 0, evidenceRecords: 0, offlineReferences: 0, expiresAt: null },
      );
      setLocalError(null);
      setLocalSuccess("The controlled offline audit package was removed from this device.");
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "The offline audit package could not be removed."),
  });

  const addApplicabilityMutation = useMutation({
    mutationFn: (ruleId: string) => addAuditApplicabilityFact(
      amoCode,
      auditId,
      ruleId,
      applicabilityReason.trim(),
    ),
    onSuccess: async () => {
      setLocalError(null);
      setLocalSuccess("Governed applicability context added. Preparation will be re-fingerprinted before issue.");
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Applicability context could not be added."),
  });
  const removeApplicabilityMutation = useMutation({
    mutationFn: (factId: string) => removeAuditApplicabilityFact(amoCode, auditId, factId),
    onSuccess: async () => {
      setLocalError(null);
      setLocalSuccess("Applicability context removed. Preparation will be re-fingerprinted before issue.");
      await refresh();
    },
    onError: (error) => setLocalError(error instanceof Error ? error.message : "Applicability context could not be removed."),
  });

  const requests = useMemo(() => requestsQuery.data?.items || [], [requestsQuery.data?.items]);
  const participants = participantsQuery.data?.items || [];
  const context = contextQuery.data;
  const documents = controlledDocumentsQuery.data?.items || [];
  const applicabilityFacts = applicabilityQuery.data?.items || [];
  const applicabilityRules = (applicabilityQuery.data?.available_rules || []).filter((rule) => {
    const needle = applicabilitySearch.trim().toLowerCase();
    if (!needle) return true;
    return [rule.document_code, rule.document_title, rule.target_type, rule.target_id, rule.target_value, rule.source]
      .some((value) => String(value || "").toLowerCase().includes(needle));
  });
  const filterDocuments = (search: string): CanonicalDocumentControlDocument[] => {
    const needle = search.trim().toLowerCase();
    if (!needle) return documents;
    return documents.filter((document) =>
      [document.code, document.title, document.manual_type, document.status].some((value) => value?.toLowerCase().includes(needle)),
    );
  };
  const requestDocuments = filterDocuments(requestDmsSearch);
  const checklistDocuments = filterDocuments(checklistDmsSearch);
  const dmsChecklists = dmsChecklistsQuery.data?.items || [];
  const selectedDmsChecklist = dmsChecklists.find((item) => item.document_id === effectiveDmsChecklistId) || null;
  const selectedRealtimeDocument = documents.find((document) => document.id === checklistDmsDocumentId) || null;
  const selectedRequestDocument = documents.find((document) => document.id === newRequest.controlledDocumentId) || null;
  const requestChecklistOptions = (fullBindingsQuery.data?.items || []).flatMap((binding) =>
    binding.instantiated_item_ids.map((itemId, index) => {
      const item = binding.item_snapshot[index];
      return {
        id: itemId,
        label: item?.checklist_ref || item?.requirement_ref || item?.prompt || `Checklist item ${index + 1}`,
        section: item?.section || null,
      };
    }),
  );
  const dmsResponseSchemeValid = Boolean(
    dmsResponseType
    && (dmsResponseType !== "CUSTOM"
      || (dmsResponseOptions.length >= 2
        && dmsResponseOptions.every((option) => option.value.trim() && option.label.trim() && option.canonical_status))),
  );
  const composerSections = Array.from(new Set(
    checklistItems.map((item) => item.section.trim()).filter(Boolean),
  )).sort((left, right) => left.localeCompare(right));
  const visibleComposerItems = checklistItems.filter((item) => {
    const needle = composerSearch.trim().toLowerCase();
    const matchesSearch = !needle || [
      item.section,
      item.checklistRef,
      item.requirementRef,
      item.prompt,
      item.expectedEvidence,
      item.guidance,
      item.samplingRequirement,
    ].some((value) => value.toLowerCase().includes(needle));
    if (!matchesSearch) return false;
    if (composerSection !== "ALL" && item.section.trim() !== composerSection) return false;
    if (composerFilter === "INCOMPLETE") return !item.prompt.trim() || (item.mandatory && !item.requirementRef.trim());
    if (composerFilter === "EVIDENCE_REQUIRED") return item.evidenceRequiredWhen.length > 0 || Boolean(item.expectedEvidence.trim());
    if (composerFilter === "APPLICABILITY_RULE") return Boolean(item.applicability.trim()) && item.applicability.trim().toUpperCase() !== "APPLICABLE";
    return true;
  });
  const preparedComposerCount = checklistItems.filter((item) =>
    item.prompt.trim() && (!item.mandatory || item.requirementRef.trim())
  ).length;

  const realtimeChecklistValid = Boolean(
    checklistTitle.trim().length >= 3 &&
    checklistReason.trim().length >= 8 &&
    checklistItems.length &&
    checklistItems.every((item) =>
      item.prompt.trim()
      && (item.responseType !== "CUSTOM"
        || (item.responseOptions.length >= 2
          && item.responseOptions.every((option) =>
            option.value.trim()
            && option.label.trim()
            && option.canonical_status
          )))
    ) &&
    (!checklistDmsDocumentId || Boolean(documents.find((document) => document.id === checklistDmsDocumentId)?.current_revision)),
  );
  const readiness = readinessQuery.data;
  const dependentQueriesLoading =
    Boolean(auditId) &&
    (contextQuery.isLoading ||
      contextQuery.isPending ||
      requestsQuery.isLoading ||
      requestsQuery.isPending ||
      participantsQuery.isLoading ||
      participantsQuery.isPending ||
      sessionQuery.isLoading ||
      sessionQuery.isPending ||
      applicabilityQuery.isLoading ||
      applicabilityQuery.isPending ||
      fullBindingsQuery.isLoading ||
      fullBindingsQuery.isPending ||
      preparationRevisionsQuery.isLoading ||
      preparationRevisionsQuery.isPending ||
      readinessQuery.isLoading ||
      readinessQuery.isPending);

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
  const prerequisiteError = contextQuery.error || requestsQuery.error || participantsQuery.error || sessionQuery.error || applicabilityQuery.error || fullBindingsQuery.error || preparationRevisionsQuery.error || readinessQuery.error;
  if (prerequisiteError) {
    return (
      <AuditStageLoadError
        className="qms-occurrence-stage qms-occurrence-stage--error"
        title="Preparation could not be loaded"
        detail={auditPrerequisiteLoadDetail(
          prerequisiteError,
          "The governed preparation context is not available yet. Complete and save the audit Setup stage, then retry preparation.",
        )}
        onRetry={() => {
          void contextQuery.refetch();
          void requestsQuery.refetch();
          void participantsQuery.refetch();
          void sessionQuery.refetch();
          void applicabilityQuery.refetch();
          void fullBindingsQuery.refetch();
          void preparationRevisionsQuery.refetch();
          void readinessQuery.refetch();
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
        title="Preparation context unavailable"
        detail="The audit preparation data could not be loaded. Retry to retrieve the saved audit and preparation records."
        onRetry={() => void contextQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "setup")}
        exitLabel="Back to Setup"
      />
    );
  }

  const samplingPlan = (fullBindingsQuery.data?.items || []).flatMap((binding) =>
    binding.item_snapshot.flatMap((item, index) => item.sampling_requirement?.trim()
      ? [{
          key: `${binding.id}:${index}`,
          section: item.section || "Checklist",
          reference: item.checklist_ref || item.requirement_ref || `Item ${index + 1}`,
          requirement: item.sampling_requirement,
          method: item.audit_method || null,
        }]
      : [])
  );
  const meetingPlan = context.opening_meeting_records || [];
  const controlledReferences = controlledDocumentSources(context.regulatory_and_manual_basis.source_references);
  const prepRevision = context.controlled_preparation?.latest_revision;
  const offlinePackStatus = offlinePackQuery.data;
  const bindings = fullBindingsQuery.data?.items || [];
  const checklistBindings = bindings.length;
  const readinessWarning = Boolean(readiness && !readiness.issue_ready);
  const fieldworkOpen = Boolean(readiness?.fieldwork_ready) && isAtLeastLiveStage(sessionQuery.data?.current_stage_id);
  const stageBlocked = !fieldworkOpen;
  const canEditFrozenPreparation = canManage && !isAtLeastLiveStage(sessionQuery.data?.current_stage_id) && !auditQuery.data.actual_start && !auditQuery.data.actual_end;
  const preparationReady = Boolean(readiness?.issue_ready);
  const needsPreparationIssue = !readiness?.checks.some((check) => check.code === "CONTROLLED_PREPARATION" && check.complete);
  const waitingForFieldworkEvidence = preparationReady && !needsPreparationIssue && !readiness?.fieldwork_ready;

  return (
    <section className="qms-occurrence-stage qms-audit-prepare-stage" aria-label="Pre-audit preparation workspace" id="audit-occurrence-prepare">
      <div className="qms-audit-prepare-stage__toolbar">
        <div className="qms-audit-prepare-stage__intro">
          <h2 className="qms-audit-prepare-stage__title">Prepare</h2>
          <p className="qms-audit-prepare-stage__helper">Request evidence, invite participants, and confirm readiness before fieldwork.</p>
          <div id={AUDIT_PREPARE_TOOLBAR_ID} className="qms-audit-prepare-toolbar" />
          <div className="qms-audit-prepare-stage__status" role="status" aria-label="Preparation readiness">
            <span className={`qms-audit-prepare-stage__readiness-chip${readinessWarning ? " is-warning" : ""}`}>
              Readiness {readiness?.percent ?? 0}%
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
      {localSuccess ? <div className="qms-occurrence-stage__message is-success" role="status"><CheckCircle2 size={16} /> {localSuccess}</div> : null}
      {stageBlocked ? (
        <div className={`qms-audit-prepare-stage__release${preparationReady ? " is-ready" : ""}`}>
          <div><ShieldAlert size={16} aria-hidden /><span><strong>{waitingForFieldworkEvidence ? "Preparation issued · evidence still required" : preparationReady ? "Ready to issue preparation" : "Preparation is incomplete"}</strong><small>{waitingForFieldworkEvidence ? readiness?.fieldwork_blockers?.[0]?.reason : preparationReady ? "Issue the current snapshot. Fieldwork opens when its evidence requirements are satisfied." : readiness?.issue_blockers?.[0]?.reason || "Resolve the identified preparation blockers before issue."}</small></span></div>
          {waitingForFieldworkEvidence ? <a href="#audit-preparation-requests">Review evidence requests</a> : canManage && needsPreparationIssue ? <button type="button" className="is-primary" disabled={!preparationReady || preparationRevisionsQuery.isPending || issuePreparationMutation.isPending} onClick={() => issuePreparationMutation.mutate()}>{issuePreparationMutation.isPending ? "Issuing…" : "Issue preparation"}</button> : null}
        </div>
      ) : null}
      {readinessWarning ? (
        <p className="qms-audit-prepare-stage__notice is-warning">
          <ShieldAlert size={14} aria-hidden /> {readiness?.issue_blockers.map((blocker) => blocker.reason).join(" · ") || "Preparation blockers remain."}
        </p>
      ) : null}
      {fieldworkOpen ? (
        <p className="qms-audit-prepare-stage__notice is-info">
          <ShieldAlert size={14} aria-hidden /> The issued checklist baseline is locked while fieldwork is active. Return the audit through the governed preparation lifecycle before changing checklist scope or questions.
        </p>
      ) : null}

      <nav className="qms-audit-prepare__navigation" aria-label="Preparation sections">
        <a href="#audit-preparation-readiness">Readiness <span>{readiness?.complete_count}/{readiness?.total_count}</span></a>
        <a href="#audit-preparation-checklists">Checklist <span>{checklistBindings}</span></a>
        <a href="#audit-preparation-requests">Evidence requests <span>{requests.length}</span></a>
        <a href="#audit-preparation-participants">Auditee access <span>{participants.length}</span></a>
        <a href="#audit-occurrence-activity">Activity</a>
      </nav>

      <section className="qms-audit-prepare__offline-pack" aria-label="Offline fieldwork package">
        <div className="qms-audit-prepare__offline-pack-copy">
          <DownloadCloud size={18} aria-hidden />
          <span>
            <strong>{offlinePackStatus?.ready ? "Offline package ready" : "Make audit available offline"}</strong>
            <small>
              {offlinePackStatus?.ready
                ? `${offlinePackStatus.checklistItems} checklist item(s) · ${offlinePackStatus.evidenceRecords} governed evidence record(s) · ${offlinePackStatus.offlineReferences} controlled reference(s) · verified ${offlinePackStatus.verifiedAt ? new Date(offlinePackStatus.verifiedAt).toLocaleString() : "on this device"}`
                : prepRevision?.status === "ISSUED"
                  ? "Encrypt the issued work package and current fieldwork baseline on this device before unreliable or no-connectivity work."
                  : "Issue preparation first. Draft preparation is not an offline fieldwork authority."}
            </small>
            {offlinePackStatus?.workPackageSha256 ? <small className="qms-audit-prepare__offline-pack-hash">Work package SHA-256 · {offlinePackStatus.workPackageSha256}</small> : null}
          </span>
        </div>
        <div className="qms-audit-prepare__offline-pack-actions">
          {offlinePackStatus?.ready ? <span className="qms-audit-prepare__offline-pack-device"><HardDrive size={14} aria-hidden /> Stored securely on this device</span> : null}
          <button
            type="button"
            className="is-primary"
            disabled={!readiness?.fieldwork_ready || prepRevision?.status !== "ISSUED" || offlinePackMutation.isPending}
            onClick={() => offlinePackMutation.mutate()}
          >
            {offlinePackMutation.isPending ? "Preparing…" : offlinePackStatus?.ready ? "Refresh offline package" : "Make available offline"}
          </button>
          {offlinePackStatus?.ready ? <button type="button" disabled={removeOfflinePackMutation.isPending} onClick={() => removeOfflinePackMutation.mutate()}>{removeOfflinePackMutation.isPending ? "Removing…" : "Remove offline copy"}</button> : null}
        </div>
      </section>

      <div className="qms-audit-prepare-stage__stack">
        <section className="qms-audit-prepare-stage__section qms-audit-prepare__basis">
          <header><div><h3>Audit basis</h3></div></header>
          <dl>
            <div><dt>Scope</dt><dd>{context.regulatory_and_manual_basis?.audit_scope || auditQuery.data.scope || "—"}</dd></div>
            <div><dt>Objectives</dt><dd>{auditQuery.data.objectives || "—"}</dd></div>
            <div><dt>Criteria</dt><dd>{context.regulatory_and_manual_basis?.audit_criteria || auditQuery.data.criteria || "—"}</dd></div>
            <div><dt>Checklists</dt><dd>{checklistBindings} revision(s)</dd></div>
            <div><dt>Prep revision</dt><dd>{prepRevision ? `Rev ${prepRevision.revision_no} · ${prepRevision.status}` : "Not issued"}</dd></div>
          </dl>
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__intelligence">
          <header>
            <div>
              <h3>Preparation intelligence</h3>
              <p>Authoritative history, open corrective action exposure and source context assembled for this audit.</p>
            </div>
            <span className="qms-audit-prepare-stage__meta-chip">As of {new Date(context.as_of).toLocaleString()}</span>
          </header>
          <div className="qms-audit-prepare__intelligence-grid">
            <article><strong>{context.prior_audit_history.items.length}</strong><span>Comparable prior audits</span><small>{context.prior_audit_history.matching_basis}</small></article>
            <article><strong>{context.prior_findings.total}</strong><span>Prior findings</span><small>{Object.entries(context.prior_findings.classification_counts || {}).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`).join(" · ") || "No prior finding classification counts"}</small></article>
            <article><strong>{context.car_exposure.open_count}</strong><span>Open CAR / CAPA exposure</span><small>{context.car_exposure.total} related corrective action record(s) reviewed</small></article>
            <article><strong>{context.cross_source_assurance_pressure.factors.length}</strong><span>Preparation context factors</span><small>{context.cross_source_assurance_pressure.statement}</small></article>
          </div>
          {context.prior_findings.items.length ? (
            <div className="qms-audit-prepare__prior-findings" aria-label="Relevant prior findings">
              <strong>Relevant prior findings</strong>
              <ul>
                {context.prior_findings.items.slice(0, 12).map((finding) => (
                  <li key={finding.id}>
                    <span><strong>{finding.finding_ref || "Finding"}</strong>{finding.requirement_ref ? <small>{finding.requirement_ref}</small> : null}</span>
                    <p>{finding.description || "No finding description recorded."}</p>
                    <small>{[finding.classification, finding.severity, finding.status].filter(Boolean).join(" · ") || "Status not recorded"}</small>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {context.cross_source_assurance_pressure.factors.length ? <div className="qms-audit-prepare__factor-list" aria-label="Preparation context factors">{context.cross_source_assurance_pressure.factors.map((factor) => <div key={factor.code}><span><strong>{factor.label}</strong><small>{factor.source}</small></span><span>{String(factor.value ?? "—")}</span><small>{factor.rationale}</small></div>)}</div> : null}
          {context.data_quality.warnings.length ? <div className="qms-audit-prepare-stage__notice is-warning"><AlertTriangle size={14} aria-hidden /><span>{context.data_quality.warnings.map((warning) => warning.message).join(" · ")}</span></div> : null}
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__readiness" id="audit-preparation-readiness">
          <header>
            <div><h3>Readiness</h3><p>Deterministic checks from persisted setup, checklist and document-request state.</p></div>
            <span className="qms-audit-prepare-stage__meta-chip">{readiness?.complete_count || 0}/{readiness?.total_count || 0} complete</span>
          </header>
          <div className="qms-audit-prepare__readiness-list">
            {readiness?.checks.map((check) => <div key={check.code} className={check.complete ? "is-complete" : "is-blocked"}>{check.complete ? <CheckCircle2 size={15} aria-hidden /> : <AlertTriangle size={15} aria-hidden />}<span>{check.label}</span></div>)}
          </div>
          {readiness?.fieldwork_blockers.length ? <ul className="qms-audit-prepare__blocker-list">{readiness.fieldwork_blockers.map((blocker, index) => <li key={`${blocker.type}-${index}`}>{blocker.reason}</li>)}</ul> : <p className="qms-audit-prepare-stage__notice is-info"><CheckCircle2 size={14} aria-hidden /> No fieldwork readiness blockers remain.</p>}
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__fieldwork-plan">
          <header>
            <div><h3>Fieldwork plan</h3><p>Governed agenda/interviews and checklist sampling requirements available before entering Live Audit.</p></div>
            <span className="qms-audit-prepare-stage__meta-chip">{meetingPlan.length} meeting(s) · {samplingPlan.length} sampling instruction(s)</span>
          </header>
          <div className="qms-audit-prepare__fieldwork-plan-grid">
            <article>
              <h4>Agenda / interviews</h4>
              {!meetingPlan.length ? <p className="qms-audit-prepare__empty">No opening, closing, follow-up or other audit meeting is currently scheduled.</p> : (
                <ul>{meetingPlan.map((meeting, index) => {
                  const type = String(meeting.meeting_type || "MEETING").replaceAll("_", " ");
                  const start = String(meeting.scheduled_start || meeting.scheduled_at || "");
                  const end = String(meeting.scheduled_end || "");
                  return <li key={String(meeting.id || index)}><strong>{type}</strong><span>{start ? new Date(start).toLocaleString() : "Time not recorded"}{end ? ` – ${new Date(end).toLocaleString()}` : ""}</span><small>{String(meeting.auditee_department || "Auditee / department not specified")} · Auditor {String(meeting.auditor_user_id || auditQuery.data.lead_auditor_user_id || "not assigned")}</small>{meeting.agenda ? <p>{String(meeting.agenda)}</p> : null}<small>{String(meeting.location || meeting.conference_url || meeting.status || "Planned audit coordination")}</small></li>;
                })}</ul>
              )}
            </article>
            <article>
              <h4>Sampling plan</h4>
              {fullBindingsQuery.isLoading ? <p className="qms-audit-prepare__empty">Loading frozen checklist sampling requirements…</p> : fullBindingsQuery.isError ? <p className="qms-audit-prepare-stage__notice is-warning" role="alert">Sampling requirements could not be loaded from the current checklist binding.</p> : !samplingPlan.length ? <p className="qms-audit-prepare__empty">No explicit sampling requirement is defined in the bound checklist revision.</p> : (
                <ul>{samplingPlan.map((sample) => <li key={sample.key}><strong>{sample.reference}</strong><span>{sample.requirement}</span><small>{sample.section}{sample.method ? ` · ${sample.method.replaceAll("_", " ")}` : ""}</small></li>)}</ul>
              )}
            </article>
          </div>
        </section>
        <section className="qms-audit-prepare-stage__section qms-audit-prepare__applicability">
          <header>
            <div><h3>Applicability context</h3><p>Select only governed DMS applicability rules that define the actual aircraft, capability, authorization, location, role, work package or other audited scope.</p></div>
            <span className="qms-audit-prepare-stage__meta-chip">{applicabilityFacts.length} selected</span>
          </header>
          {fieldworkOpen ? <p className="qms-audit-prepare-stage__notice is-info"><ShieldAlert size={14} aria-hidden /> Applicability context is frozen for the active fieldwork package. Return the audit through the governed preparation lifecycle before changing scope inputs.</p> : null}
          {applicabilityFacts.length ? <div className="qms-audit-prepare__applicability-selected">
            {applicabilityFacts.map((fact) => <article key={fact.id}>
              <div><strong>{fact.target_type.replaceAll("_", " ")}</strong><span>{fact.target_value || fact.target_id || "Governed target"}</span><small>{fact.rule_type} · {fact.source}</small><p>{fact.reason}</p></div>
              {canEditFrozenPreparation ? <button type="button" onClick={() => removeApplicabilityMutation.mutate(fact.id)} disabled={removeApplicabilityMutation.isPending} aria-label="Remove applicability context"><Trash2 size={15} /></button> : null}
            </article>)}
          </div> : <p className="qms-audit-prepare__empty">No governed applicability context is selected. Scoped documentary evidence will remain unverified rather than being assumed applicable or N/A.</p>}
          {canEditFrozenPreparation ? <div className="qms-audit-prepare__applicability-picker">
            <label><span>Search governed rules</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={applicabilitySearch} onChange={(event) => setApplicabilitySearch(event.target.value)} placeholder="Aircraft, base, department, authorization, work package…" /></div></label>
            <label className="is-wide"><span>Selection basis</span><input value={applicabilityReason} onChange={(event) => setApplicabilityReason(event.target.value)} placeholder="Why this governed target belongs to this audit scope" /></label>
            <div className="qms-audit-prepare__applicability-rules is-wide">
              {applicabilityRules.length ? applicabilityRules.slice(0, 60).map((rule) => <article key={rule.id} className={rule.selected ? "is-selected" : ""}>
                <div><strong>{rule.document_code} · {rule.target_type.replaceAll("_", " ")}</strong><span>{rule.target_value || rule.target_id || rule.document_title}</span><small>{rule.rule_type} · Rev {rule.current_revision} · {rule.source}</small></div>
                <button type="button" disabled={rule.selected || addApplicabilityMutation.isPending || applicabilityReason.trim().length < 8} onClick={() => addApplicabilityMutation.mutate(rule.id)}>{rule.selected ? "Selected" : "Add to audit"}</button>
              </article>) : <p className="qms-audit-prepare__empty">No current-published governed DMS applicability rules match this search.</p>}
            </div>
          </div> : null}
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__references">
          <header><div><h3>Controlled references</h3><p>Approved source documents retained with this audit preparation.</p></div><span className="qms-audit-prepare-stage__meta-chip">{controlledReferences.documents.length} source(s)</span></header>
          {controlledReferences.documents.length ? <div className="qms-audit-prepare__reference-list">{controlledReferences.documents.map((source, index) => <ControlledSourceReference key={index} source={source} index={index} />)}</div> : <p className="qms-audit-prepare__empty">No controlled source document has been captured yet.</p>}
          {controlledReferences.recordCount > 0 ? <p className="qms-audit-prepare__empty">{controlledReferences.recordCount} audit, checklist and request references are retained in the preparation history.</p> : null}
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__checklists" id="audit-preparation-checklists">
          <header>
            <div>
              <h3>Fieldwork checklist</h3>
              <p>Select a current DMS checklist, or create the audit questions here.</p>
            </div>
            <span className="qms-audit-prepare-stage__meta-chip">{checklistBindings} bound</span>
          </header>

          {bindings.length ? (
            <div className="qms-audit-prepare__binding-list" aria-label="Bound checklist revisions">
              {bindings.map((binding) => (
                <article key={binding.id}>
                  <ClipboardList size={16} aria-hidden />
                  <div><strong>{binding.template_code} · Rev {binding.revision_no}</strong><small>{binding.application_reason}</small></div>
                </article>
              ))}
            </div>
          ) : <p className="qms-audit-prepare__empty">No fieldwork checklist is bound. Fieldwork cannot open until one is selected or created.</p>}

          {canEditFrozenPreparation ? <>
            <div className="qms-audit-prepare__mode" role="tablist" aria-label="Checklist source">
              <button type="button" role="tab" aria-selected={checklistMode === "LIBRARY"} className={checklistMode === "LIBRARY" ? "is-active" : ""} onClick={() => setChecklistMode("LIBRARY")}>Use DMS checklist</button>
              <button type="button" role="tab" aria-selected={checklistMode === "CREATE"} className={checklistMode === "CREATE" ? "is-active" : ""} onClick={() => setChecklistMode("CREATE")}>Create in realtime</button>
            </div>

            {checklistMode === "LIBRARY" ? (
              <form className="qms-audit-prepare__checklist-form" onSubmit={(event) => { event.preventDefault(); setLocalError(null); setLocalSuccess(null); if (!effectiveDmsChecklistId) { setLocalError("Select a current effective DMS checklist first."); return; } if (!dmsResponseSchemeValid) { setLocalError("Define the source checklist response scheme before binding it. The portal will not infer YES/NO/N/A, U or S from the document text."); return; } if (checklistReason.trim().length < 8) { setLocalError("Enter a selection reason of at least 8 characters."); return; } applyChecklistMutation.mutate(); }}>
                <label><span>Document type</span><select value={checklistDocumentType} onChange={(event) => { setChecklistDocumentType(event.target.value as "CHECKLIST" | "FORM"); setSelectedDmsChecklistId(""); }}><option value="CHECKLIST">Checklist</option><option value="FORM">Form</option></select></label>
                <label><span>Search DMS</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={checklistSearch} onChange={(event) => setChecklistSearch(event.target.value)} placeholder="Document code or title" /></div></label>
                <label className="is-wide"><span>Current controlled document</span><select required value={effectiveDmsChecklistId} onChange={(event) => setSelectedDmsChecklistId(event.target.value)}><option value="">Select the current effective {checklistDocumentType.toLowerCase()}</option>{dmsChecklists.map((item) => <option key={item.document_id} value={item.document_id}>{item.code} · {item.title} · Rev {item.current_revision.revision_number}</option>)}</select></label>
                {dmsChecklistsQuery.data?.recommendation ? <p className="qms-audit-prepare-stage__notice is-info is-wide"><CheckCircle2 size={14} /> Suggested from a similar audit: {dmsChecklistsQuery.data.recommendation.code} · {dmsChecklistsQuery.data.recommendation.title} ({dmsChecklistsQuery.data.recommendation.reason || "previously used for this audit context"}).</p> : null}
                {selectedDmsChecklist ? <div className="qms-audit-prepare__current-revision is-wide"><strong>Current effective revision</strong><span>Issue {selectedDmsChecklist.current_revision.issue_number || "—"} · Rev {selectedDmsChecklist.current_revision.revision_number}{selectedDmsChecklist.current_revision.effective_date ? ` · effective ${selectedDmsChecklist.current_revision.effective_date}` : ""}</span><small>{selectedDmsChecklist.hierarchy_path || "DMS controlled-document library"}</small></div> : null}
                <fieldset className="qms-audit-prepare__response-options is-wide">
                  <legend>Source response scheme</legend>
                  <p>Select the response vocabulary defined by the controlled source. This is a governed mapping, not a conversion of the source document.</p>
                  <label><span>Response vocabulary</span><select required value={dmsResponseType} onChange={(event) => {
                    const responseType = event.target.value as typeof dmsResponseType;
                    setDmsResponseType(responseType);
                    setDmsResponseOptions(responseType === "CUSTOM" ? customResponseOptions() : []);
                  }}><option value="">Select source scheme</option><option value="YES_NO_NA">YES / NO / N/A</option><option value="COMPLIANCE">Compliance / NCR / Observation / N/A / Not verified</option><option value="CUSTOM">Custom source vocabulary (including U / S where defined)</option></select></label>
                  {dmsResponseType === "CUSTOM" ? <div className="qms-audit-prepare__response-options-list">{dmsResponseOptions.map((option, optionIndex) => <div key={`dms-response-${optionIndex}`} className="qms-audit-prepare__response-option"><label><span>Source value</span><input value={option.value} onChange={(event) => setDmsResponseOptions((current) => current.map((candidate, index) => index === optionIndex ? { ...candidate, value: event.target.value } : candidate))} /></label><label><span>Display label</span><input value={option.label} onChange={(event) => setDmsResponseOptions((current) => current.map((candidate, index) => index === optionIndex ? { ...candidate, label: event.target.value } : candidate))} /></label><label><span>Workflow meaning</span><select value={option.canonical_status} onChange={(event) => setDmsResponseOptions((current) => current.map((candidate, index) => index === optionIndex ? { ...candidate, canonical_status: event.target.value as ChecklistResponseOption["canonical_status"] } : candidate))}><option value="">Select meaning</option><option value="COMPLIANT">Compliant</option><option value="NONCOMPLIANT">Noncompliant</option><option value="OBSERVATION">Observation</option><option value="NOT_APPLICABLE">Not applicable</option><option value="NOT_VERIFIED">Not verified / incomplete</option></select></label><button type="button" aria-label={`Remove source response ${option.label || option.value || optionIndex + 1}`} disabled={dmsResponseOptions.length <= 2} onClick={() => setDmsResponseOptions((current) => current.filter((_, index) => index !== optionIndex))}><Trash2 size={14} /></button></div>)}<button type="button" onClick={() => setDmsResponseOptions((current) => [...current, { value: "", label: "", canonical_status: "" }])}><Plus size={14} /> Add source response</button></div> : null}
                </fieldset>
                <label className="qms-audit-prepare__check is-wide"><input type="checkbox" checked={allowExistingItems} onChange={(event) => setAllowExistingItems(event.target.checked)} /> Add to the existing checklist</label>
                {dmsChecklistsQuery.error ? <p className="qms-audit-prepare-stage__notice is-warning is-wide"><AlertTriangle size={14} /> The DMS checklist library could not be loaded. You can upload a controlled checklist or create this audit’s questions in realtime.</p> : null}
                {!dmsChecklistsQuery.isLoading && !dmsChecklists.length ? <p className="qms-audit-prepare-stage__notice is-warning is-wide"><AlertTriangle size={14} /> No current effective {checklistDocumentType.toLowerCase()} is available in DMS. Upload one here or create the questions in realtime.</p> : null}
                {dmsChecklistsQuery.data?.pending?.length ? <section className="qms-audit-prepare__pending-dms is-wide" aria-label="Awaiting DMS approval">
                  <header><strong>Awaiting DMS approval ({dmsChecklistsQuery.data.pending.length})</strong><button type="button" disabled={dmsChecklistsQuery.isFetching} onClick={() => void dmsChecklistsQuery.refetch()}>Refresh status</button></header>
                  <p>Status refreshes automatically. Approved, effective documents appear in the selector above.</p>
                  {dmsChecklistsQuery.data.pending.map((item) => <article key={item.workflow_id}>
                    <div><strong>{item.code} · {item.title}</strong><span>{item.state.replaceAll("_", " ")}</span><small>{item.state === "DRAFT" ? "Registered · awaiting submission for technical review" : item.state === "CORRECTIONS_REQUIRED" ? "Changes requested · open the workflow for review comments" : "Review in progress · open the workflow for decisions and remaining steps"}</small></div>
                    <Link to={item.review_url}>Review document <ArrowRight size={14} /></Link>
                  </article>)}
                </section> : null}
                <footer><button type="button" onClick={() => { if (!dmsResponseSchemeValid) { setLocalError("Define the source response scheme before uploading and binding a controlled checklist."); return; } setChecklistUploadOpen(true); }}><UploadCloud size={14} /> Upload to DMS</button><button type="submit" className="is-primary" disabled={!dmsResponseSchemeValid || applyChecklistMutation.isPending || createChecklistMutation.isPending}>{applyChecklistMutation.isPending ? "Applying…" : "Use current revision"}</button></footer>
              </form>
            ) : (
              <form className="qms-audit-prepare__checklist-form" onSubmit={(event) => { event.preventDefault(); setLocalError(null); setLocalSuccess(null); if (!realtimeChecklistValid) { setLocalError("Enter a title, reason and every checklist question. Custom response schemes require at least two source values and an explicit workflow meaning for every value; ambiguous abbreviations are never inferred. Any selected DMS source must have a current effective revision."); return; } createChecklistMutation.mutate(); }}>
                <label><span>Checklist title</span><input required minLength={3} value={checklistTitle} onChange={(event) => setChecklistTitle(event.target.value)} /></label>
                <label><span>Creation reason</span><input required minLength={8} value={checklistReason} onChange={(event) => setChecklistReason(event.target.value)} /></label>
                <label className="is-wide"><span>Description</span><textarea rows={2} value={checklistDescription} onChange={(event) => setChecklistDescription(event.target.value)} placeholder="Audit-specific purpose and coverage" /></label>

                <fieldset className="qms-audit-prepare__dms-source is-wide">
                  <legend>Optional controlled DMS source</legend>
                  <p>Link the controlled source used to construct these questions. QMS records its current effective revision automatically.</p>
                  <label><span>Search DMS</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={checklistDmsSearch} onChange={(event) => setChecklistDmsSearch(event.target.value)} placeholder="Document code, title or type" /></div></label>
                  <label><span>Controlled document</span><select value={checklistDmsDocumentId} onChange={(event) => setChecklistDmsDocumentId(event.target.value)}><option value="">No DMS source</option>{checklistDocuments.map((document) => <option key={document.id} value={document.id}>{document.code} · {document.title} · {statusLabel(document.status)}</option>)}</select></label>
                  <div className="qms-audit-prepare__current-revision"><strong>Revision applied automatically</strong>{selectedRealtimeDocument?.current_revision ? <span>Issue {selectedRealtimeDocument.current_revision.issue_number || "—"} · Rev {selectedRealtimeDocument.current_revision.revision_number} · {statusLabel(selectedRealtimeDocument.current_revision.status)}</span> : <span>{checklistDmsDocumentId ? "This document has no current effective revision." : "Select a controlled source if applicable."}</span>}</div>
                </fieldset>

                <div className="qms-audit-prepare__composer is-wide">
                  <header><div><strong>Checklist questions</strong><small>{preparedComposerCount}/{checklistItems.length} prepared · questions remain editable until governed preparation is issued.</small></div><button type="button" onClick={() => setChecklistItems((current) => [...current, emptyChecklistItem()])}><Plus size={14} /> Add question</button></header>
                  <div className="qms-audit-prepare__composer-tools" aria-label="Checklist preparation navigation">
                    <label className="is-wide"><span>Search questions</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={composerSearch} onChange={(event) => setComposerSearch(event.target.value)} placeholder="Question, section, reference, evidence or guidance" /></div></label>
                    <label><span>Section</span><select value={composerSection} onChange={(event) => setComposerSection(event.target.value)}><option value="ALL">All sections</option>{composerSections.map((section) => <option key={section} value={section}>{section}</option>)}</select></label>
                    <label><span>Filter</span><select value={composerFilter} onChange={(event) => setComposerFilter(event.target.value as typeof composerFilter)}><option value="ALL">All questions</option><option value="INCOMPLETE">Incomplete preparation</option><option value="EVIDENCE_REQUIRED">Evidence expected / required</option><option value="APPLICABILITY_RULE">Applicability rule set</option></select></label>
                  </div>
                  {!visibleComposerItems.length ? <p className="qms-audit-prepare__empty">No checklist questions match the current preparation filters.</p> : null}
                  {visibleComposerItems.map((item) => {
                    const index = checklistItems.findIndex((candidate) => candidate.id === item.id);
                    return (
                    <article key={item.id}>
                      <div className="qms-audit-prepare__composer-number">{index + 1}</div>
                      <div className="qms-audit-prepare__composer-fields">
                        <label className="is-wide"><span>Question / verification step</span><textarea required rows={2} value={item.prompt} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, prompt: event.target.value } : entry))} /></label>
                        <label><span>Section</span><input value={item.section} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, section: event.target.value } : entry))} /></label>
                        <label><span>Checklist reference</span><input value={item.checklistRef} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, checklistRef: event.target.value } : entry))} /></label>
                        <label><span>Requirement / manual reference</span><input value={item.requirementRef} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, requirementRef: event.target.value } : entry))} /></label>
                        <label><span>Expected objective evidence</span><input value={item.expectedEvidence} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, expectedEvidence: event.target.value } : entry))} /></label>
                        <label><span>Audit method</span><select value={item.auditMethod} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, auditMethod: event.target.value as ChecklistComposerItem["auditMethod"] } : entry))}><option value="">Not specified</option><option value="RECORD_REVIEW">Record review</option><option value="INTERVIEW">Interview</option><option value="OBSERVATION">Observation</option><option value="SAMPLE">Sample</option><option value="TEST">Test</option></select></label>
                        <label><span>Evidence authority context</span><select value={item.evidenceContext} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, evidenceContext: event.target.value as ChecklistComposerItem["evidenceContext"] } : entry))}>
                          <option value="GENERAL">General — no precedence applied</option>
                          <option value="CAPABILITY_SCOPE">Capability / approval scope</option>
                          <option value="PERSONNEL_AUTHORIZATION">Personnel authorization</option>
                          <option value="CONTRACT_SCOPE">Contract / subcontract scope</option>
                          <option value="TECHNICAL_DATA">Technical data</option>
                          <option value="RECORD_RETENTION">Record retention</option>
                          <option value="TOOLING_CALIBRATION">Tooling / calibration</option>
                          <option value="FACILITY">Facility / approved location</option>
                        </select><small>Controls context-specific evidence ranking only; it does not make the compliance decision.</small></label>
                        <label className="is-wide"><span>Auditor guidance</span><textarea rows={2} value={item.guidance} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, guidance: event.target.value } : entry))} placeholder="Optional fieldwork guidance without changing the requirement itself" /></label>
                        <label><span>Sampling requirement</span><input value={item.samplingRequirement} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, samplingRequirement: event.target.value } : entry))} placeholder="e.g. 5 records across relevant work areas" /></label>
                        <label><span>Applicability rule</span><input value={item.applicability} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, applicability: event.target.value } : entry))} placeholder="APPLICABLE or the governed applicability rule" /></label><label><span>Applicability reason</span><input value={item.applicabilityReason} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, applicabilityReason: event.target.value } : entry))} placeholder="Controlled rationale when applicability is restricted or N/A" /></label>
                        <label><span>Permitted evidence types</span><input value={item.evidenceTypes} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, evidenceTypes: event.target.value } : entry))} placeholder="PHOTO, DOCUMENT, RECORD_REF" /></label>
                        <fieldset className="qms-audit-prepare__response-rules is-wide"><legend>Response rules</legend>
                          <label><input type="checkbox" checked={item.naJustificationRequired} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, naJustificationRequired: event.target.checked } : entry))} /> Require a reason when marked N/A</label>
                          <label><input type="checkbox" checked={item.notesRequiredWhen.includes("NONCOMPLIANT")} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, notesRequiredWhen: event.target.checked ? Array.from(new Set([...entry.notesRequiredWhen, "NONCOMPLIANT", "OBSERVATION"])) : entry.notesRequiredWhen.filter((value) => !["NONCOMPLIANT", "OBSERVATION"].includes(value)) } : entry))} /> Require notes for adverse responses</label>
                          <label><input type="checkbox" checked={item.evidenceRequiredWhen.includes("NONCOMPLIANT")} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, evidenceRequiredWhen: event.target.checked ? Array.from(new Set([...entry.evidenceRequiredWhen, "NONCOMPLIANT", "OBSERVATION"])) : entry.evidenceRequiredWhen.filter((value) => !["NONCOMPLIANT", "OBSERVATION"].includes(value)) } : entry))} /> Require governed evidence for adverse responses</label>
                        </fieldset>
                        <label><span>Source response scheme</span><select value={item.responseType} onChange={(event) => {
                          const responseType = event.target.value as ChecklistComposerItem["responseType"];
                          setChecklistItems((current) => current.map((entry) => entry.id === item.id
                            ? { ...entry, responseType, responseOptions: responseType === "CUSTOM" ? customResponseOptions() : [] }
                            : entry));
                        }}><option value="COMPLIANCE">Compliance / NCR / Observation / N/A / Not verified</option><option value="YES_NO_NA">YES / NO / N/A</option><option value="CUSTOM">Custom governed source vocabulary</option></select></label>
                        {item.responseType === "CUSTOM" ? <fieldset className="qms-audit-prepare__response-options is-wide"><legend>Custom source responses</legend><p>Map every source value explicitly. The portal will not infer ambiguous abbreviations such as U or S.</p>{item.responseOptions.map((option, optionIndex) => <div key={`${item.id}-response-${optionIndex}`} className="qms-audit-prepare__response-option"><label><span>Value</span><input value={option.value} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, responseOptions: entry.responseOptions.map((candidate, index) => index === optionIndex ? { ...candidate, value: event.target.value } : candidate) } : entry))} /></label><label><span>Label</span><input value={option.label} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, responseOptions: entry.responseOptions.map((candidate, index) => index === optionIndex ? { ...candidate, label: event.target.value } : candidate) } : entry))} /></label><label><span>Workflow meaning</span><select value={option.canonical_status} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, responseOptions: entry.responseOptions.map((candidate, index) => index === optionIndex ? { ...candidate, canonical_status: event.target.value as ChecklistResponseOption["canonical_status"] } : candidate) } : entry))}><option value="">Select meaning</option><option value="COMPLIANT">Compliant</option><option value="NONCOMPLIANT">Noncompliant</option><option value="OBSERVATION">Observation</option><option value="NOT_APPLICABLE">Not applicable</option><option value="NOT_VERIFIED">Not verified / incomplete</option></select></label><button type="button" aria-label={`Remove response ${option.label || option.value || optionIndex + 1}`} disabled={item.responseOptions.length <= 2} onClick={() => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, responseOptions: entry.responseOptions.filter((_, index) => index !== optionIndex) } : entry))}><Trash2 size={14} /></button></div>)}<button type="button" onClick={() => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, responseOptions: [...entry.responseOptions, { value: "", label: "", canonical_status: "" }] } : entry))}><Plus size={14} /> Add response</button></fieldset> : null}
                        <label className="qms-audit-prepare__check is-wide"><input type="checkbox" checked={item.mandatory} onChange={(event) => setChecklistItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, mandatory: event.target.checked } : entry))} /> Mandatory fieldwork item</label>
                      </div>
                      <button type="button" aria-label={`Remove checklist question ${index + 1}`} disabled={checklistItems.length === 1} onClick={() => setChecklistItems((current) => current.filter((entry) => entry.id !== item.id))}><Trash2 size={15} /></button>
                    </article>
                    );
                  })}
                </div>
                <label className="qms-audit-prepare__check is-wide"><input type="checkbox" checked={allowExistingItems} onChange={(event) => setAllowExistingItems(event.target.checked)} /> Append these questions to the existing live checklist</label>
                {controlledDocumentsQuery.error ? <p className="qms-audit-prepare-stage__notice is-warning is-wide"><AlertTriangle size={14} /> DMS search is unavailable. Remove the DMS selection to create an audit-specific checklist without a controlled source link.</p> : null}
                <footer><button type="submit" className="is-primary" disabled={createChecklistMutation.isPending || applyChecklistMutation.isPending}>{createChecklistMutation.isPending ? "Creating and issuing…" : "Create, issue and bind checklist"}</button></footer>
              </form>
            )}
          </> : null}
        </section>

        <section className="qms-audit-prepare-stage__section" id="audit-preparation-requests">
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
                <label><span>Responsible party</span><input value={newRequest.responsibleParty} onChange={(event) => setNewRequest((current) => ({ ...current, responsibleParty: event.target.value }))} placeholder="Auditee, department or process owner" /></label>
                <label><span>Associated checklist items</span><select multiple size={Math.min(5, Math.max(2, requestChecklistOptions.length || 2))} value={newRequest.checklistItemIds} onChange={(event) => setNewRequest((current) => ({ ...current, checklistItemIds: Array.from(event.currentTarget.selectedOptions, (option) => option.value) }))}>{requestChecklistOptions.map((option) => <option key={option.id} value={option.id}>{option.section ? `${option.section} · ` : ""}{option.label}</option>)}</select><small>Use Ctrl/Cmd or touch multi-select where supported. Selected IDs are validated against this audit on the server.</small></label>
                <label><span>Submission source</span><select value={newRequest.sourceMode} onChange={(event) => setNewRequest((current) => ({ ...current, sourceMode: event.target.value as NewRequest["sourceMode"], controlledDocumentId: "" }))}><option value="UPLOAD_OR_CONTROLLED">Upload or controlled DMS record</option><option value="UPLOAD">Upload only</option><option value="CONTROLLED_DMS">Controlled DMS record only</option></select></label>
                <label><span>Workflow requirement</span><select value={newRequest.requirementStage} onChange={(event) => setNewRequest((current) => ({ ...current, requirementStage: event.target.value as NewRequest["requirementStage"], isRequired: event.target.value !== "REQUESTED_NOT_BLOCKING" }))}><option value="REQUIRED_BEFORE_ISSUE">Required before preparation issue</option><option value="REQUIRED_BEFORE_FIELDWORK">Required before fieldwork</option><option value="REQUIRED_DURING_FIELDWORK">Required during fieldwork</option><option value="REQUESTED_NOT_BLOCKING">Requested · not blocking</option></select></label>
                {newRequest.sourceMode !== "UPLOAD" ? <>
                  <label className="is-wide"><span>Search controlled DMS</span><div className="qms-audit-prepare__search"><Search size={15} aria-hidden /><input value={requestDmsSearch} onChange={(event) => setRequestDmsSearch(event.target.value)} placeholder="Document code, title or type" /></div></label>
                  <label><span>Controlled document</span><select value={newRequest.controlledDocumentId} onChange={(event) => setNewRequest((current) => ({ ...current, controlledDocumentId: event.target.value }))}><option value="">No preselected document</option>{requestDocuments.map((document) => <option key={document.id} value={document.id}>{document.code} · {document.title} · {statusLabel(document.status)}</option>)}</select></label>
                  <div className="qms-audit-prepare__current-revision"><strong>Current effective revision</strong>{selectedRequestDocument?.current_revision ? <span>Issue {selectedRequestDocument.current_revision.issue_number || "—"} · Rev {selectedRequestDocument.current_revision.revision_number} · {statusLabel(selectedRequestDocument.current_revision.status)}</span> : <span>{newRequest.controlledDocumentId ? "This document has no current effective revision." : "Resolved automatically when a document is selected."}</span>}</div>
                </> : null}
                {(newRequest.sourceMode === "CONTROLLED_DMS" || newRequest.controlledDocumentId) && !selectedRequestDocument?.current_revision ? <p className="qms-audit-prepare-stage__notice is-warning is-wide" role="status">Select a controlled document with a current effective revision before creating this request, or choose Upload only.</p> : null}
                <footer><button type="button" onClick={() => { setShowRequestForm(false); setNewRequest(emptyRequest); }}>Cancel</button><button type="submit" className="is-primary" disabled={createMutation.isPending || (newRequest.sourceMode === "CONTROLLED_DMS" && !selectedRequestDocument?.current_revision) || Boolean(newRequest.controlledDocumentId && !selectedRequestDocument?.current_revision)}>{createMutation.isPending ? "Creating…" : "Create governed request"}</button></footer>
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
                    {request.responsible_party ? <small>Responsible: {request.responsible_party}</small> : null}
                    {request.checklist_item_ids?.length ? <small>Linked to {request.checklist_item_ids.length} checklist item(s)</small> : null}
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

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__participants" id="audit-preparation-participants">
          <header>
            <div><h3>External participants</h3></div>
            {canManage ? <button type="button" onClick={() => setShowParticipantForm((value) => !value)}><UserPlus size={15} /> Invite</button> : null}
          </header>

            {oneTimeAccessUrl ? <div className="qms-audit-prepare__one-time-link" role="status"><div><strong>Invitation link ready</strong><small>Copy now — the token is shown once.</small></div><button type="button" onClick={() => { void navigator.clipboard.writeText(oneTimeAccessUrl).then(() => pushToast({ title: "Invitation link copied", variant: "success" })).catch(() => setLocalError("The invitation link could not be copied. Allow clipboard access and try again.")); }}><Copy size={14} /> Copy link</button></div> : null}

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
              <footer><button type="button" onClick={() => setShowParticipantForm(false)}>Cancel</button><button type="submit" className="is-primary" disabled={participantMutation.isPending}>{participantMutation.isPending ? "Creating access…" : "Create invitation"}</button></footer>
            </form> : null}

            <div className="qms-audit-prepare__participant-list">
              {!participants.length ? <p className="qms-audit-prepare__empty">No external participants are assigned to this audit.</p> : participants.map((participant) => <article key={participant.id}><div><span>{participant.participant_type.replaceAll("_", " ")}</span><strong>{participant.display_name || participant.email || "External participant"}</strong><small>{participant.organisation || "No organisation"} · {participant.role} · {participant.assurance_level || "EMAIL_LINK"}</small><small>{participant.permissions.join(" · ")}</small><small>Expires {new Date(participant.expires_at).toLocaleString()} · {participant.status}</small></div>{canManage && participant.status !== "REVOKED" ? <button type="button" onClick={() => revokeMutation.mutate(participant.id)} disabled={revokeMutation.isPending}><UserX size={14} /> Revoke</button> : null}</article>)}
            </div>
        </section>

        <section className="qms-audit-prepare-stage__section qms-audit-prepare__activity" id="audit-occurrence-activity">
          <header>
            <div><h3><History size={16} /> Activity / audit trail</h3><p>Append-only preparation and audit-domain events for this occurrence.</p></div>
            <button type="button" onClick={() => void activityQuery.refetch()} disabled={activityQuery.isFetching}>Refresh</button>
          </header>
          {activityQuery.isLoading ? <p className="qms-audit-prepare__empty">Loading audit activity…</p> : null}
          {activityQuery.isError ? <p className="qms-audit-prepare-stage__notice is-warning" role="alert">Audit activity could not be loaded. Retry without leaving this audit.</p> : null}
          {!activityQuery.isLoading && !activityQuery.isError && !(activityQuery.data?.items.length) ? <p className="qms-audit-prepare__empty">No recorded audit activity is available yet.</p> : null}
          {activityQuery.data?.items.length ? (
            <ol className="qms-audit-prepare__activity-list">
              {activityQuery.data.items.slice(0, 100).map((event) => (
                <li key={event.id}>
                  <div><strong>{event.action.replaceAll("_", " ")}</strong><small>{event.entity_type} · {new Date(event.occurred_at).toLocaleString()}</small></div>
                  <p>{event.reason || "Recorded governed audit event."}</p>
                  <small>Actor {event.actor_user_id || "system / external participant"} · Record {event.id}</small>
                </li>
              ))}
            </ol>
          ) : null}
        </section>
      </div>
      <ControlledDocumentUploadDialog
        tenant={amoCode.toLowerCase()}
        open={checklistUploadOpen}
        defaultDocumentType="CHECKLIST"
        allowedTypes={["CHECKLIST", "FORM"]}
        heading="Upload checklist or form to DMS"
        submitLabel="Register draft in DMS"
        allowApprovedIntake
        onClose={() => setChecklistUploadOpen(false)}
        submitIntake={async (payload) => {
          const uploaded = await uploadDmsChecklistFromAudit(amoCode, auditId, payload);
          return {
            manual_id: uploaded.document.id,
            revision_id: uploaded.document.revision_id,
            status: uploaded.document.revision_status,
            source_type: payload.file.name.toLowerCase().endsWith(".pdf") ? "PDF" : "DOCX",
          };
        }}
        onUploaded={async (result) => {
          setLocalError(null);
          if (result.approved_intake === true) {
            const binding = await bindCurrentDmsChecklist(
              amoCode,
              auditId,
              result.manual_id,
              "Approved DMS checklist uploaded and selected during audit preparation.",
              allowExistingItems,
              dmsResponseType,
              dmsResponseType === "CUSTOM" ? dmsResponseOptions : [],
            );
            setLocalSuccess(null);
            try {
              const confirmed = await confirmChecklistBinding(binding);
              if (!confirmed) {
                throw new Error("Prepare has not confirmed the authoritative fieldwork binding yet. Refresh and verify it shows as bound before issuing preparation.");
              }
              setAllowExistingItems(false);
              setLocalSuccess("The approved checklist is now current in DMS and populated for this audit.");
              return;
            } catch (error) {
              setLocalSuccess(null);
              const message = error instanceof Error
                ? `The approved checklist was saved, but Prepare could not verify the authoritative binding: ${error.message}`
                : "The approved checklist was saved, but Prepare could not verify the authoritative binding. Refresh before continuing.";
              setLocalError(message);
              throw error instanceof Error ? error : new Error(message);
            }
          }
          setLocalSuccess("The checklist was registered as a DMS draft. Track it under Awaiting DMS approval below; open Review document to advance its workflow.");
          await refresh();
        }}
      />
    </section>
  );
};

export default AuditPrepareWorkspace;
