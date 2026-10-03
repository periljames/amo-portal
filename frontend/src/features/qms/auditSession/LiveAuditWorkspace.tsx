import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CloudOff,
  Cloud,
  CircleSlash2,
  ClipboardCheck,
  Eye,
  FileWarning,
  Filter,
  MessageSquareText,
  Search,
  ShieldAlert,
  RefreshCw,
  Users,
  X,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiClientError } from "../../../services/apiClient";
import { isOfflineQueuedError } from "../../../services/offlineHttp";
import { listOfflineMutations } from "../../../services/offlinePersistence";
import { qmsListFindings } from "../../../services/qms";
import { projectOfflineFindings, readAuditOfflinePack } from "../../../services/qmsAuditOfflinePack";
import {
  createAtomicChecklistFinding,
  getChecklistEvidenceCandidates,
  listChecklistExecutionGovernance,
  mutateChecklistFieldwork,
  type CanonicalChecklistResponse,
  type ChecklistAssessmentState,
  type ChecklistExecutionGovernanceRow,
  type DocumentaryStatus,
  type FieldVerificationStatus,
  type ImplementationStatus,
  type EvidenceCandidate,
  type FieldworkFindingLevel,
  type FieldworkFindingSeverity,
} from "../../../services/qmsChecklistExecutionGovernance";
import {
  listChecklistBindings,
  type ChecklistResponseOption,
  type ChecklistTemplateItem,
} from "../../../services/qmsChecklistTemplates";
import { heartbeatAuditPresence, listAuditPresence } from "../../../services/qmsAuditPresence";
import { auditOccurrenceQueryKey, resolveAuditOccurrence } from "../../../services/qmsAuditOccurrenceResolver";
import { getPortalConnectivity, onPortalConnectivityChange } from "../../../services/portalConnectivity";
import { completeAuditFieldwork, getAuditSession } from "../../../services/qmsAuditSession";
import { listExternalFindingDraftsForQuality } from "../../../services/qmsExternalFindingDraftReview";
import LiveAuditEvidenceStrip from "./LiveAuditEvidenceStrip";
import { AuditStageLoadError } from "./AuditStageLoadError";
import { auditOccurrenceLoadDetail, auditPrerequisiteLoadDetail } from "./auditStageLoadErrorMessages";
import { auditSessionPath, isAtLeastLiveStage } from "./auditSessionRoutes";
import { canCompleteAuditFieldwork, canExecuteAssignedAudit } from "./qmsAuditActionGates";
import "../../../styles/qms-live-audit-workspace.css";

const DEFAULT_RESPONSE_OPTIONS: ChecklistResponseOption[] = [
  { value: "COMPLIANT", label: "Compliant", canonical_status: "COMPLIANT" },
  { value: "NONCOMPLIANT", label: "NCR", canonical_status: "NONCOMPLIANT" },
  { value: "OBSERVATION", label: "Observation", canonical_status: "OBSERVATION" },
  { value: "NOT_APPLICABLE", label: "N/A", canonical_status: "NOT_APPLICABLE" },
  { value: "NOT_VERIFIED", label: "Not verified", canonical_status: "NOT_VERIFIED" },
];

function fallbackResponseOptions(responseType?: string | null): ChecklistResponseOption[] {
  switch ((responseType || "COMPLIANCE").toUpperCase()) {
    case "YES_NO_NA":
      return [
        { value: "YES", label: "Yes", canonical_status: "COMPLIANT" },
        { value: "NO", label: "No", canonical_status: "NONCOMPLIANT" },
        { value: "N/A", label: "N/A", canonical_status: "NOT_APPLICABLE" },
      ];
    case "COMPLIANT_NONCOMPLIANT_NA":
      return DEFAULT_RESPONSE_OPTIONS.filter((item) => ["COMPLIANT", "NONCOMPLIANT", "NOT_APPLICABLE"].includes(item.canonical_status));
    case "COMPLIANCE":
    case "COMPLIANT_NONCOMPLIANT_OBSERVATION_NA_NOT_VERIFIED":
      return DEFAULT_RESPONSE_OPTIONS;
    default:
      return [];
  }
}

function responseIcon(status: CanonicalChecklistResponse): React.ComponentType<{ size?: number }> {
  if (status === "COMPLIANT") return CheckCircle2;
  if (status === "NONCOMPLIANT") return FileWarning;
  if (status === "OBSERVATION") return MessageSquareText;
  if (status === "NOT_APPLICABLE") return CircleSlash2;
  return ShieldAlert;
}

type Props = { amoCode: string; auditKey: string };
type NonconformityLevel = "LEVEL_1" | "LEVEL_2" | "LEVEL_3";
type LiveChecklistSourceContext = ChecklistTemplateItem & {
  templateCode: string;
  revisionNo: number;
  contentSha256: string;
};

type FindingDraft = {
  mode: "NONCOMPLIANT" | "OBSERVATION";
  responseValue: string;
  item: ChecklistExecutionGovernanceRow;
  level: NonconformityLevel | "";
  statement: string;
  objectiveEvidence: string;
};

type FieldworkUpdateInput = {
  item: ChecklistExecutionGovernanceRow;
  response: CanonicalChecklistResponse;
  responseValue: string;
  auditorNotes: string;
  sampledItemInformation: string;
  assessment: ChecklistAssessmentState;
};

const NONCONFORMITY_LEVELS: Array<{ value: NonconformityLevel; label: string; severity: FieldworkFindingSeverity }> = [
  { value: "LEVEL_1", label: "Level 1 · Critical", severity: "CRITICAL" },
  { value: "LEVEL_2", label: "Level 2 · Major", severity: "MAJOR" },
  { value: "LEVEL_3", label: "Level 3 · Minor", severity: "MINOR" },
];

function findingClassification(draft: FindingDraft): { severity: FieldworkFindingSeverity; level: FieldworkFindingLevel } {
  if (draft.mode === "OBSERVATION") return { severity: "MINOR", level: "LEVEL_4" };
  const selected = NONCONFORMITY_LEVELS.find((candidate) => candidate.value === draft.level);
  if (!selected) throw new Error("Select the governed non-conformity classification before creating the finding.");
  return { severity: selected.severity, level: selected.value };
}

function statusLabel(value: string | null | undefined): string {
  return (value || "NOT_VERIFIED").replaceAll("_", " ");
}

function emptyAssessment(): ChecklistAssessmentState {
  return {
    applicability: "UNVERIFIED",
    applicability_reason: null,
    applicability_basis: [],
    documentary_status: "UNVERIFIED",
    implementation_status: "UNVERIFIED",
    field_verification_status: "UNVERIFIED",
    evidence_ids: [],
    document_revision_ids: [],
    regulation_refs: [],
    procedure_refs: [],
    conflicts: [],
    missing_evidence: [],
    fieldwork_requirements: [],
    ai_analysis: null,
    human_decision: null,
    human_override_reason: null,
  };
}

function assessmentIntegrityError(assessment: ChecklistAssessmentState): string | null {
  if (assessment.applicability === "NOT_APPLICABLE" && (
    !assessment.applicability_reason?.trim() || !assessment.applicability_basis.length
  )) {
    return "N/A requires an explicit governed applicability reason and preserved basis.";
  }
  if (assessment.documentary_status === "CONFLICT" && !assessment.conflicts.length) {
    return "Documentary status Conflict requires preserved competing controlled statements.";
  }
  if (
    assessment.field_verification_status === "FIELD_VERIFICATION_REQUIRED"
    && !assessment.fieldwork_requirements.length
  ) {
    return "Field verification required must identify the inspection, observation, interview, test or sample still required.";
  }
  return null;
}

function conflictSourceLabel(value: unknown): string {
  if (!value || typeof value !== "object") return "Controlled source";
  const row = value as Record<string, unknown>;
  return String(row.reference || row.evidence_id || "Controlled source");
}

function conflictClause(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  return String((value as Record<string, unknown>).clause || "");
}

function normalisedAssessment(
  item: ChecklistExecutionGovernanceRow,
  response: CanonicalChecklistResponse,
  draft?: ChecklistAssessmentState,
): ChecklistAssessmentState {
  const base = draft || item.assessment || emptyAssessment();
  const applicability = response === "NOT_APPLICABLE"
    ? base.applicability
    : base.applicability === "NOT_APPLICABLE" ? "UNVERIFIED" : base.applicability;
  return {
    ...base,
    applicability,
    applicability_reason: applicability === "NOT_APPLICABLE" ? base.applicability_reason : null,
    applicability_basis: applicability === "NOT_APPLICABLE" ? base.applicability_basis : [],
    human_decision: response,
  };
}

function csvValues(value: string): string[] {
  return Array.from(new Set(value.split(",").map((entry) => entry.trim()).filter(Boolean)));
}

function lineValues(value: string): string[] {
  return Array.from(new Set(value.split("\n").map((entry) => entry.trim()).filter(Boolean)));
}

function fieldworkConflictMessage(error: unknown): string | null {
  if (!(error instanceof ApiClientError) || error.status !== 409) return null;
  const body = error.body as { detail?: unknown } | null;
  const detail = body?.detail && typeof body.detail === "object" ? body.detail as Record<string, unknown> : null;
  if (!detail) return error.message;
  const code = String(detail.code || "");
  if (code === "FIELDWORK_VERSION_CONFLICT") {
    const serverVersion = detail.server_version;
    return `Conflict detected: another auditor or device changed this checklist item${typeof serverVersion === "number" ? ` to version ${serverVersion}` : ""}. Refresh and review the server record before retrying; the portal will not silently overwrite it.`;
  }
  if (code === "FIELDWORK_IDEMPOTENCY_CONFLICT") return "The same offline mutation identifier was received with different content. The portal rejected it to prevent duplicate or ambiguous fieldwork.";
  if (code === "FIELDWORK_FINDING_ALREADY_LINKED") return "This checklist item already has a governed finding. Review the existing finding instead of creating a duplicate.";
  return typeof detail.message === "string" ? detail.message : error.message;
}

const LiveAuditWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});
  const [sampleDrafts, setSampleDrafts] = useState<Record<string, string>>({});
  const [assessmentDrafts, setAssessmentDrafts] = useState<Record<string, ChecklistAssessmentState>>({});
  const [findingDraft, setFindingDraft] = useState<FindingDraft | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [checklistSearch, setChecklistSearch] = useState("");
  const [checklistFilter, setChecklistFilter] = useState<"ALL" | "UNANSWERED" | "FINDINGS" | "EVIDENCE_REQUIRED">("ALL");
  const [connectivity, setConnectivity] = useState(() => getPortalConnectivity().state);

  const auditQuery = useQuery({
    queryKey: auditOccurrenceQueryKey(amoCode, auditKey),
    queryFn: ({ signal }) => resolveAuditOccurrence(amoCode, auditKey, signal),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const fieldworkComplete = Boolean(auditQuery.data?.actual_end);
  const canExecute = canExecuteAssignedAudit(auditQuery.data) && !fieldworkComplete;
  const canCompleteFieldwork = canCompleteAuditFieldwork(auditQuery.data) && !fieldworkComplete;
  const sessionQuery = useQuery({
    queryKey: ["qms", "audit-session", amoCode, auditId],
    queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const isLiveStage = Boolean(sessionQuery.data && isAtLeastLiveStage(sessionQuery.data.current_stage_id));
  const fieldworkEnabled = Boolean(auditId) && isLiveStage;

  const checklistQuery = useQuery({
    queryKey: ["qms", "live-audit-checklist", amoCode, auditId],
    queryFn: ({ signal }) => listChecklistExecutionGovernance(amoCode, auditId, signal),
    enabled: fieldworkEnabled,
    staleTime: 1_500,
  });

  useEffect(() => {
    const hash = location.hash.replace(/^#/, "");
    if (!hash) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`audit-occurrence-${hash}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location.hash, checklistQuery.isSuccess]);
  const bindingsQuery = useQuery({
    queryKey: ["qms", "live-audit-bindings", amoCode, auditId],
    queryFn: ({ signal }) => listChecklistBindings(amoCode, auditId, signal),
    enabled: fieldworkEnabled,
    staleTime: 30_000,
  });
  const findingsQuery = useQuery({
    queryKey: ["qms", "live-audit-findings", auditId],
    queryFn: async () => {
      const offline = async () => {
        const pack = await readAuditOfflinePack(amoCode, auditId);
        return pack ? projectOfflineFindings(pack) : null;
      };
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        const local = await offline();
        if (local) return local;
      }
      try {
        return await qmsListFindings(auditId, amoCode);
      } catch (error) {
        const message = error instanceof Error ? error.message.toLowerCase() : "";
        if (!message.includes("offline") && !message.includes("could not be reached") && !message.includes("cached copy")) throw error;
        const local = await offline();
        if (local) return local;
        throw error;
      }
    },
    enabled: fieldworkEnabled,
    staleTime: 2_000,
  });
  const externalDraftsQuery = useQuery({
    queryKey: ["qms", "external-finding-drafts", amoCode, auditId],
    queryFn: ({ signal }) => listExternalFindingDraftsForQuality(amoCode, auditId, signal),
    enabled: fieldworkEnabled,
    staleTime: 1_500,
  });
  const presenceQuery = useQuery({
    queryKey: ["qms", "audit-presence", amoCode, auditId],
    queryFn: ({ signal }) => listAuditPresence(amoCode, auditId, signal),
    enabled: fieldworkEnabled,
    staleTime: 3_000,
    refetchInterval: 15_000,
  });
  const outboxQuery = useQuery({
    queryKey: ["qms", "live-audit-outbox", auditId],
    queryFn: async () => {
      const auditMarker = `/audits/${encodeURIComponent(auditId)}/`;
      const entries = await listOfflineMutations();
      return entries.filter((entry) => entry.entityType === "qms-audit-checklist-item" && entry.path.includes(auditMarker));
    },
    enabled: fieldworkEnabled,
    staleTime: 500,
    refetchInterval: 2_000,
  });

  useEffect(() => onPortalConnectivityChange((snapshot) => setConnectivity(snapshot.state)), []);

  useEffect(() => {
    if (!fieldworkEnabled) return undefined;
    let cancelled = false;
    const beat = async () => {
      try {
        await heartbeatAuditPresence(amoCode, auditId, "live");
        if (!cancelled) void presenceQuery.refetch();
      } catch {
        // Presence is a collaboration projection and must never block fieldwork.
      }
    };
    void beat();
    const timer = window.setInterval(() => void beat(), 20_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [amoCode, auditId, fieldworkEnabled]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = useMemo(() => checklistQuery.data?.items ?? [], [checklistQuery.data?.items]);
  const sourceContextByItemId = useMemo(() => {
    const map = new Map<string, LiveChecklistSourceContext>();
    for (const binding of bindingsQuery.data?.items || []) {
      binding.instantiated_item_ids.forEach((itemId, index) => {
        const snapshot = binding.item_snapshot[index];
        if (!snapshot) return;
        map.set(itemId, {
          ...snapshot,
          templateCode: binding.template_code,
          revisionNo: binding.revision_no,
          contentSha256: binding.content_sha256,
        });
      });
    }
    return map;
  }, [bindingsQuery.data?.items]);
  const visibleItems = useMemo(() => {
    const term = checklistSearch.trim().toLowerCase();
    return items.filter((item) => {
      const source = sourceContextByItemId.get(item.checklist_item_id);
      const matchesSearch = !term || [
        item.checklist_ref,
        item.requirement_ref,
        item.prompt,
        item.section,
        source?.regulatory_source_ref,
        source?.manual_source_ref,
      ].some((value) => String(value || "").toLowerCase().includes(term));
      if (!matchesSearch) return false;
      if (checklistFilter === "UNANSWERED") return item.canonical_response_status === "NOT_VERIFIED";
      if (checklistFilter === "FINDINGS") return Boolean(item.finding_id) || item.canonical_response_status === "NONCOMPLIANT" || item.canonical_response_status === "OBSERVATION";
      if (checklistFilter === "EVIDENCE_REQUIRED") return Boolean(source?.expected_evidence?.trim()) || Boolean(source?.evidence_required_when?.length);
      return true;
    });
  }, [checklistFilter, checklistSearch, items, sourceContextByItemId]);
  const effectiveSelectedId = useMemo(() => {
    if (!visibleItems.length) return null;
    if (selectedId && visibleItems.some((item) => item.checklist_item_id === selectedId)) return selectedId;
    return (visibleItems.find((item) => item.canonical_response_status === "NOT_VERIFIED") || visibleItems[0]).checklist_item_id;
  }, [selectedId, visibleItems]);
  const selectedIndex = effectiveSelectedId ? visibleItems.findIndex((item) => item.checklist_item_id === effectiveSelectedId) : -1;
  const selected = selectedIndex >= 0 ? visibleItems[selectedIndex] : null;
  const selectedSource = selected ? sourceContextByItemId.get(selected.checklist_item_id) || null : null;
  const selectedResponseOptions = useMemo(
    () => selectedSource?.response_options?.length
      ? selectedSource.response_options
      : fallbackResponseOptions(selectedSource?.response_type),
    [selectedSource],
  );
  const notes = selected ? noteDrafts[selected.checklist_item_id] ?? selected.auditor_notes ?? "" : "";
  const sampledItems = selected ? sampleDrafts[selected.checklist_item_id] ?? selected.sampled_item_information ?? "" : "";
  const assessment = selected ? assessmentDrafts[selected.checklist_item_id] ?? selected.assessment ?? emptyAssessment() : null;
  const evidenceCandidatesQuery = useQuery({
    queryKey: ["qms", "checklist-evidence-candidates", amoCode, auditId, selected?.checklist_item_id || ""],
    queryFn: ({ signal }) => getChecklistEvidenceCandidates(amoCode, auditId, selected!.checklist_item_id, signal),
    enabled: Boolean(fieldworkEnabled && selected?.checklist_item_id && connectivity !== "OFFLINE"),
    staleTime: 30_000,
    retry: 1,
  });
  const evidenceCandidates = evidenceCandidatesQuery.data?.items || [];
  const updateAssessmentDraft = (changes: Partial<ChecklistAssessmentState>) => {
    if (!selected || !assessment) return;
    setAssessmentDrafts((current) => ({
      ...current,
      [selected.checklist_item_id]: { ...assessment, ...changes },
    }));
  };
  const toggleDocumentaryCandidate = (candidate: EvidenceCandidate, checked: boolean) => {
    if (!selected || !assessment) return;
    const candidateIds = new Set(evidenceCandidates.map((item) => item.evidence_id));
    const retainedNonCandidateIds = assessment.evidence_ids.filter((id) => !candidateIds.has(id));
    const selectedCandidateIds = new Set(
      assessment.evidence_ids.filter((id) => candidateIds.has(id)),
    );
    if (checked) selectedCandidateIds.add(candidate.evidence_id);
    else selectedCandidateIds.delete(candidate.evidence_id);
    const selectedCandidateRows = evidenceCandidates.filter((item) => selectedCandidateIds.has(item.evidence_id));
    setAssessmentDrafts((current) => ({
      ...current,
      [selected.checklist_item_id]: {
        ...assessment,
        evidence_ids: [...retainedNonCandidateIds, ...Array.from(selectedCandidateIds)],
        document_revision_ids: Array.from(new Set(selectedCandidateRows.map((item) => item.revision_id).filter(Boolean))),
      },
    }));
  };
  const unsavedDraftCount = useMemo(() => {
    const ids = new Set([
      ...Object.keys(noteDrafts),
      ...Object.keys(sampleDrafts),
      ...Object.keys(assessmentDrafts),
    ]);
    return ids.size;
  }, [assessmentDrafts, noteDrafts, sampleDrafts]);

  const outboxEntries = useMemo(() => outboxQuery.data ?? [], [outboxQuery.data]);
  const outbox = useMemo(() => ({
    queued: outboxEntries.filter((entry) => entry.status === "queued" || entry.status === "syncing").length,
    conflicts: outboxEntries.filter((entry) => entry.status === "conflict").length,
    failed: outboxEntries.filter((entry) => entry.status === "failed").length,
  }), [outboxEntries]);
  const presence = presenceQuery.data?.items || [];
  const auditeePresence = presence.filter((entry) => entry.actor_type === "AUDITEE_GUEST");
  const auditTeamPresence = presence.filter((entry) => entry.actor_type !== "AUDITEE_GUEST");

  const refreshFieldwork = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-checklist", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "live-audit-findings", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "checklist-evidence-candidates", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "external-finding-drafts", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms", "audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-session", amoCode, auditId] }),
      queryClient.invalidateQueries({ queryKey: auditOccurrenceQueryKey(amoCode, auditKey) }),
    ]);
  };

  const updateMutation = useMutation({
    mutationFn: ({ item, response, responseValue, auditorNotes, sampledItemInformation, assessment: assessmentState }: FieldworkUpdateInput) => {
      const normalized = normalisedAssessment(item, response, assessmentState);
      const integrityError = assessmentIntegrityError(normalized);
      if (integrityError) throw new Error(integrityError);
      return mutateChecklistFieldwork(amoCode, auditId, item, {
        canonical_response_status: response,
        response_value: responseValue,
        auditor_notes: auditorNotes.trim() || null,
        sampled_item_information: sampledItemInformation.trim() || null,
        evidence_references: item.evidence_references || [],
        assessment: normalized,
        reason: "Live audit fieldwork checklist update.",
      });
    },
    onSuccess: async (_result, variables) => {
      setLocalError(null);
      setSyncNotice("Saved to the authoritative audit record.");
      setNoteDrafts((current) => { const next = { ...current }; delete next[variables.item.checklist_item_id]; return next; });
      setSampleDrafts((current) => { const next = { ...current }; delete next[variables.item.checklist_item_id]; return next; });
      setAssessmentDrafts((current) => { const next = { ...current }; delete next[variables.item.checklist_item_id]; return next; });
      await refreshFieldwork();
      void outboxQuery.refetch();
    },
    onError: (error) => {
      if (isOfflineQueuedError(error)) {
        setLocalError(null);
        setSyncNotice("Saved securely on this device · pending ordered sync. The authoritative audit state will not change until the server accepts the mutation.");
        void outboxQuery.refetch();
        return;
      }
      setSyncNotice(null);
      setLocalError(fieldworkConflictMessage(error) || (error instanceof Error ? error.message : "Checklist update failed."));
      void outboxQuery.refetch();
    },
  });

  const findingMutation = useMutation({
    mutationFn: async (draft: FindingDraft) => {
      const classification = findingClassification(draft);
      const auditorNotes = noteDrafts[draft.item.checklist_item_id] ?? draft.item.auditor_notes ?? "";
      const normalized = normalisedAssessment(
        draft.item,
        draft.mode,
        assessmentDrafts[draft.item.checklist_item_id] ?? draft.item.assessment ?? emptyAssessment(),
      );
      const integrityError = assessmentIntegrityError(normalized);
      if (integrityError) throw new Error(integrityError);
      return createAtomicChecklistFinding(amoCode, auditId, draft.item, {
        canonical_response_status: draft.mode,
        response_value: draft.responseValue,
        severity: classification.severity,
        level: classification.level,
        requirement_ref: draft.item.requirement_ref || draft.item.checklist_ref || null,
        description: draft.statement.trim(),
        objective_evidence: draft.objectiveEvidence.trim() || draft.item.objective_evidence || null,
        safety_sensitive: false,
        auditor_notes: auditorNotes.trim() || null,
        sampled_item_information: sampleDrafts[draft.item.checklist_item_id] ?? draft.item.sampled_item_information ?? null,
        evidence_references: draft.item.evidence_references || [],
        assessment: normalized,
        reason: `Live audit fieldwork ${draft.mode === "NONCOMPLIANT" ? "non-conformity" : "observation"} recorded atomically with the governed checklist response.`,
      });
    },
    onSuccess: async (_result, draft) => {
      setFindingDraft(null);
      setLocalError(null);
      setSyncNotice("Finding, checklist response and governed CAR/task consequences committed as one authoritative transaction.");
      setNoteDrafts((current) => { const next = { ...current }; delete next[draft.item.checklist_item_id]; return next; });
      setSampleDrafts((current) => { const next = { ...current }; delete next[draft.item.checklist_item_id]; return next; });
      setAssessmentDrafts((current) => { const next = { ...current }; delete next[draft.item.checklist_item_id]; return next; });
      await refreshFieldwork();
      void outboxQuery.refetch();
    },
    onError: (error) => {
      if (isOfflineQueuedError(error)) {
        setFindingDraft(null);
        setLocalError(null);
        setSyncNotice("Finding captured securely on this device as one atomic intent · pending ordered sync. No server finding, CAR or checklist response exists until the complete transaction is accepted.");
        void outboxQuery.refetch();
        return;
      }
      setSyncNotice(null);
      setLocalError(fieldworkConflictMessage(error) || (error instanceof Error ? error.message : "Finding creation failed."));
      void outboxQuery.refetch();
    },
  });

  const counts = useMemo(() => {
    const base: Record<CanonicalChecklistResponse, number> = { COMPLIANT: 0, NONCOMPLIANT: 0, OBSERVATION: 0, NOT_APPLICABLE: 0, NOT_VERIFIED: 0 };
    items.forEach((item) => { const status = (item.canonical_response_status || "NOT_VERIFIED") as CanonicalChecklistResponse; if (status in base) base[status] += 1; else base.NOT_VERIFIED += 1; });
    return base;
  }, [items]);
  const completed = items.length - counts.NOT_VERIFIED;
  // Empty checklist must not read as 100% complete.
  const percent = items.length ? Math.round((completed / items.length) * 100) : null;
  const findings = findingsQuery.data || [];
  const completionBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (!items.length) blockers.push("No governed checklist is bound");
    if (unsavedDraftCount) blockers.push(`${unsavedDraftCount} checklist item${unsavedDraftCount === 1 ? " has" : "s have"} unsaved fieldwork changes`);
    if (counts.NOT_VERIFIED) blockers.push(`${counts.NOT_VERIFIED} checklist item${counts.NOT_VERIFIED === 1 ? " is" : "s are"} not verified`);
    const structuredOpen = items.filter((item) => {
      if (item.canonical_response_status === "NOT_VERIFIED") return false;
      const structured = item.assessment || emptyAssessment();
      if (item.canonical_response_status === "NOT_APPLICABLE") {
        return structured.applicability !== "NOT_APPLICABLE"
          || !structured.applicability_reason?.trim()
          || !structured.applicability_basis.length;
      }
      return structured.documentary_status === "UNVERIFIED"
        || structured.implementation_status === "UNVERIFIED"
        || structured.field_verification_status === "UNVERIFIED"
        || structured.field_verification_status === "NOT_VERIFIED"
        || structured.field_verification_status === "FIELD_VERIFICATION_REQUIRED"
        || structured.missing_evidence.length > 0
        || (structured.documentary_status === "CONFLICT"
          && item.canonical_response_status === "COMPLIANT"
          && !structured.human_override_reason?.trim());
    }).length;
    if (structuredOpen) blockers.push(`${structuredOpen} resolved checklist item${structuredOpen === 1 ? " has" : "s have"} incomplete compliance evidence/verification state`);
    const unlinkedAdverse = items.filter((item) => ["NONCOMPLIANT", "OBSERVATION"].includes(item.canonical_response_status) && !item.finding_id).length;
    if (unlinkedAdverse) blockers.push(`${unlinkedAdverse} adverse response${unlinkedAdverse === 1 ? " has" : "s have"} no governed finding`);
    const unresolvedExternalDrafts = (externalDraftsQuery.data?.items || []).filter((draft) => ["CREATED", "SUBMITTED", "RETURNED"].includes(draft.status)).length;
    if (externalDraftsQuery.isError) blockers.push("External finding-draft status could not be verified");
    else if (unresolvedExternalDrafts) blockers.push(`${unresolvedExternalDrafts} external finding draft${unresolvedExternalDrafts === 1 ? " requires" : "s require"} promotion or withdrawal`);
    if (outbox.queued) blockers.push(`${outbox.queued} offline change${outbox.queued === 1 ? " is" : "s are"} pending sync`);
    if (outbox.conflicts) blockers.push(`${outbox.conflicts} sync conflict${outbox.conflicts === 1 ? " requires" : "s require"} review`);
    if (outbox.failed) blockers.push(`${outbox.failed} failed sync change${outbox.failed === 1 ? " requires" : "s require"} review`);
    return blockers;
  }, [counts.NOT_VERIFIED, externalDraftsQuery.data?.items, externalDraftsQuery.isError, items, outbox.conflicts, outbox.failed, outbox.queued, unsavedDraftCount]);
  const completeMutation = useMutation({
    mutationFn: () => completeAuditFieldwork(amoCode, auditId),
    onSuccess: async () => {
      setLocalError(null);
      setSyncNotice("Fieldwork completed. Checklist execution is now read-only and the audit has advanced to Closing.");
      await refreshFieldwork();
      navigate(auditSessionPath(amoCode, auditKey, "closing"));
    },
    onError: (error) => {
      setSyncNotice(null);
      setLocalError(fieldworkConflictMessage(error) || (error instanceof Error ? error.message : "Fieldwork could not be completed."));
    },
  });

  const move = (offset: number) => {
    if (!visibleItems.length || selectedIndex < 0) return;
    const nextIndex = Math.min(visibleItems.length - 1, Math.max(0, selectedIndex + offset));
    setSelectedId(visibleItems[nextIndex].checklist_item_id);
  };

  const responseRequirementError = (
    item: ChecklistExecutionGovernanceRow,
    source: LiveChecklistSourceContext | null,
    response: CanonicalChecklistResponse,
    auditorNotes: string,
  ): string | null => {
    if (!source) return null;
    const notePresent = Boolean(auditorNotes.trim());
    if (response === "NOT_APPLICABLE" && source.na_justification_required && !notePresent) {
      return "This governed checklist item requires an auditor reason before it can be marked N/A.";
    }
    if ((source.notes_required_when || []).includes(response) && !notePresent) {
      return `Auditor notes are required before recording ${statusLabel(response).toLowerCase()}.`;
    }
    if ((source.evidence_required_when || []).includes(response) && !(item.evidence_references || []).length) {
      return "Governed evidence is required for this response. Attach and synchronize the evidence before finalizing the checklist outcome.";
    }
    return null;
  };

  const saveCurrentAssessment = () => {
    if (!selected || !assessment || !canExecute) return;
    setSyncNotice(null);
    setLocalError(null);
    updateMutation.mutate({
      item: selected,
      response: selected.canonical_response_status,
      responseValue: selected.response_value || selected.canonical_response_status,
      auditorNotes: notes,
      sampledItemInformation: sampledItems,
      assessment,
    });
  };

  const selectResponse = (item: ChecklistExecutionGovernanceRow, option: ChecklistResponseOption) => {
    if (!canExecute) return;
    setSyncNotice(null);
    const response = option.canonical_status as CanonicalChecklistResponse;
    const source = sourceContextByItemId.get(item.checklist_item_id) || null;
    const auditorNotes = noteDrafts[item.checklist_item_id] ?? item.auditor_notes ?? "";
    const requirementError = responseRequirementError(item, source, response, auditorNotes);
    if (requirementError) {
      setLocalError(requirementError);
      return;
    }
    setLocalError(null);
    if (response === "NONCOMPLIANT" || response === "OBSERVATION") {
      setFindingDraft({
        mode: response,
        responseValue: option.value,
        item,
        level: "",
        statement: "",
        objectiveEvidence: item.objective_evidence || "",
      });
      return;
    }
    const assessmentState = assessmentDrafts[item.checklist_item_id] ?? item.assessment ?? emptyAssessment();
    if (response === "NOT_APPLICABLE" && (
      assessmentState.applicability !== "NOT_APPLICABLE"
      || !assessmentState.applicability_reason?.trim()
      || !assessmentState.applicability_basis.length
    )) {
      setLocalError("N/A requires an explicit governed applicability basis. Review the applicability recommendation/evidence panel before recording N/A.");
      return;
    }
    updateMutation.mutate({
      item,
      response,
      responseValue: option.value,
      auditorNotes: notes,
      sampledItemInformation: sampledItems,
      assessment: assessmentState,
    });
  };

  if (auditQuery.isLoading) {
    return <div className="qms-live-audit-focus qms-live-audit-focus--loading">Preparing live audit workspace…</div>;
  }
  if (auditQuery.isError || !auditQuery.data) {
    return (
      <AuditStageLoadError
        className="qms-live-audit-focus qms-live-audit-focus--error"
        title="Audit occurrence unavailable"
        detail={auditOccurrenceLoadDetail(auditQuery.error)}
        onRetry={() => void auditQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "prepare")}
        exitLabel="Back to Prepare"
        secondaryHref={auditSessionPath(amoCode, auditKey, "setup")}
        secondaryLabel="Open Setup"
      />
    );
  }
  if (sessionQuery.isLoading || sessionQuery.isPending) {
    return <div className="qms-live-audit-focus qms-live-audit-focus--loading">Verifying audit lifecycle stage…</div>;
  }
  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <AuditStageLoadError
        className="qms-live-audit-focus qms-live-audit-focus--error"
        title="Audit session unavailable"
        detail={auditOccurrenceLoadDetail(sessionQuery.error)}
        onRetry={() => void sessionQuery.refetch()}
        exitHref={auditSessionPath(amoCode, auditKey, "prepare")}
        exitLabel="Back to Prepare"
        secondaryHref={auditSessionPath(amoCode, auditKey, "setup")}
        secondaryLabel="Open Setup"
      />
    );
  }
  if (!isLiveStage) {
    return (
      <AuditStageLoadError
        className="qms-live-audit-focus qms-live-audit-focus--error"
        title="Prepare the audit before fieldwork"
        detail={`Fieldwork requires the authoritative Fieldwork stage (or later). Current stage: ${sessionQuery.data.current_stage_label}. Complete preparation and advance the lifecycle before checklist execution, presence, or findings load.`}
        exitHref={auditSessionPath(amoCode, auditKey, "prepare")}
        exitLabel="Back to Prepare"
        secondaryHref={auditSessionPath(amoCode, auditKey, "setup")}
        secondaryLabel="Open Setup"
      />
    );
  }
  if (checklistQuery.isLoading || bindingsQuery.isLoading) {
    return <div className="qms-live-audit-focus qms-live-audit-focus--loading">Preparing live audit workspace…</div>;
  }
  const prerequisiteError = checklistQuery.error || bindingsQuery.error;
  if (prerequisiteError) {
    return (
      <AuditStageLoadError
        className="qms-live-audit-focus qms-live-audit-focus--error"
        title="Prepare the audit before fieldwork"
        detail={auditPrerequisiteLoadDetail(
          prerequisiteError,
          "Fieldwork is not initialized yet. Complete preparation and apply the governed checklist before opening Fieldwork.",
        )}
        onRetry={() => {
          void checklistQuery.refetch();
          void bindingsQuery.refetch();
        }}
        exitHref={auditSessionPath(amoCode, auditKey, "prepare")}
        exitLabel="Back to Prepare"
        secondaryHref={auditSessionPath(amoCode, auditKey, "setup")}
        secondaryLabel="Open Setup"
      />
    );
  }

  return (
    <div className="qms-live-audit-focus" role="region" aria-label="Live audit fieldwork workspace">
      <header className="qms-live-audit-focus__header">
        <div>
          <h2>Fieldwork</h2>
          <p className="qms-live-audit-focus__helper">Record checklist responses, findings, and evidence.</p>
        </div>
        <div className="qms-live-audit-focus__header-meta" role="status" aria-live="polite" aria-label="Fieldwork connectivity and synchronization status">
          <span>{canExecute ? "Auditor" : "Read-only"}</span>
          <span>{sessionQuery.data ? `Stage: ${sessionQuery.data.current_stage_label}` : "Verifying lifecycle…"}</span>
          <span>
            {items.length
              ? `${completed}/${items.length} complete · ${percent}%`
              : "No checklist items · Not applicable"}
          </span>
          <span><Users size={13} /> {presence.length} active</span>
          <span className="qms-live-audit-focus__connection" data-state={connectivity}>
            {connectivity === "ONLINE" ? <Cloud size={13} /> : connectivity === "RECOVERING" ? <RefreshCw size={13} /> : <CloudOff size={13} />}
            {connectivity === "ONLINE" ? "ONLINE" : connectivity === "RECOVERING" ? "SYNCING / RECOVERING" : "OFFLINE"}
          </span>
          {unsavedDraftCount ? <span>UNSAVED · {unsavedDraftCount}</span> : null}
          {outbox.conflicts ? (
            <span>CONFLICT · {outbox.conflicts} require review</span>
          ) : outbox.failed ? (
            <span>SYNC ERROR · {outbox.failed} failed</span>
          ) : outbox.queued ? (
            <span>PENDING CHANGES · {outbox.queued}</span>
          ) : (
            <span>SYNCED · no pending changes</span>
          )}
          {fieldworkComplete ? (
            <Link className="qms-live-audit-focus__closing-link is-primary" to={auditSessionPath(amoCode, auditKey, "closing")}><ClipboardCheck size={16} /> Open Closing</Link>
          ) : (
            <button type="button" className="qms-live-audit-focus__closing-link is-primary" disabled={!canCompleteFieldwork || completionBlockers.length > 0 || completeMutation.isPending} title={completionBlockers.join("; ")} onClick={() => completeMutation.mutate()}><ClipboardCheck size={16} /> {completeMutation.isPending ? "Completing…" : "Complete Fieldwork"}</button>
          )}
          <Link to={auditSessionPath(amoCode, auditKey, "prepare")}><X size={16} /> Back to Prepare</Link>
        </div>
      </header>

      {fieldworkComplete ? <div className="qms-live-audit-focus__sync-notice" role="status">Fieldwork is complete. This workspace is read-only; reopen the governed lifecycle before recording further work.</div> : null}
      {localError ? <div className="qms-live-audit-focus__error" role="alert"><AlertTriangle size={16} /> {localError}</div> : null}
      {syncNotice ? <div className="qms-live-audit-focus__sync-notice" role="status">{syncNotice}</div> : null}
      {!fieldworkComplete && completionBlockers.length ? <div className="qms-live-audit-focus__sync-notice" role="status">Closing remains locked: {completionBlockers.join("; ")}.</div> : null}

      <div className="qms-live-audit-focus__body">
        <aside id="audit-occurrence-checklist" className="qms-live-audit-focus__sections" aria-label="Checklist questions">
          <div className="qms-live-audit-focus__progress">
            <span style={{ width: `${percent ?? 0}%` }} />
          </div>
          <h2 className="qms-live-audit-focus__sections-title">Checklist</h2>
          <div className="qms-live-audit-focus__tools">
            <label>
              <Search size={14} aria-hidden="true" />
              <span className="sr-only">Search checklist</span>
              <input value={checklistSearch} onChange={(event) => setChecklistSearch(event.target.value)} placeholder="Search checklist" />
            </label>
            <label>
              <Filter size={14} aria-hidden="true" />
              <span className="sr-only">Filter checklist</span>
              <select value={checklistFilter} onChange={(event) => setChecklistFilter(event.target.value as typeof checklistFilter)}>
                <option value="ALL">All items</option>
                <option value="UNANSWERED">Unanswered</option>
                <option value="FINDINGS">Findings / observations</option>
                <option value="EVIDENCE_REQUIRED">Evidence required</option>
              </select>
            </label>
          </div>
          <div className="qms-live-audit-focus__question-list">
            {visibleItems.map((item, index) => (
              <button type="button" key={item.checklist_item_id} className={item.checklist_item_id === selected?.checklist_item_id ? "is-selected" : ""} onClick={() => setSelectedId(item.checklist_item_id)}>
                <span>{index + 1}</span>
                <div><strong>{item.checklist_ref || item.requirement_ref || `Question ${index + 1}`}</strong><small>{item.prompt}</small><span>{item.section || "General"}</span></div>
                <em data-status={item.canonical_response_status}>{statusLabel(item.canonical_response_status)}</em>
              </button>
            ))}
            {!visibleItems.length ? <p className="qms-live-audit-focus__empty-filter">No checklist items match the current search/filter.</p> : null}
          </div>
        </aside>

        <main className="qms-live-audit-focus__question">
          {selected ? (
            <>
              <div className="qms-live-audit-focus__question-head"><div><span>{selected.section || "Checklist"}</span><h2>{selected.prompt}</h2></div><span>{selectedIndex + 1} / {visibleItems.length}</span></div>
              <dl className="qms-live-audit-focus__references">
                <div><dt>Checklist ref</dt><dd>{selected.checklist_ref || selectedSource?.checklist_ref || "—"}</dd></div>
                <div><dt>Requirement</dt><dd>{selected.requirement_ref || selectedSource?.requirement_ref || "—"}</dd></div>
                <div><dt>Regulatory source</dt><dd>{selectedSource?.regulatory_source_ref || "—"}</dd></div>
                <div><dt>Manual source</dt><dd>{selectedSource?.manual_source_ref || "—"}</dd></div>
                <div><dt>Frozen checklist</dt><dd>{selectedSource ? `${selectedSource.templateCode} Rev ${selectedSource.revisionNo}` : "No governed binding lineage"}</dd></div>
                <div><dt>Current</dt><dd>{statusLabel(selected.canonical_response_status)} · v{selected.entity_version}</dd></div>
              </dl>
              <section className="qms-live-audit-focus__expected-evidence" aria-label="Expected evidence">
                <h3>Verification plan</h3>
                <p>{selectedSource?.expected_evidence || "No expected-evidence statement was defined in the applied checklist revision."}</p>
                {selectedSource?.guidance ? <p><strong>Guidance:</strong> {selectedSource.guidance}</p> : null}
                <small>
                  {selectedSource?.mandatory === false ? "Optional verification item" : "Mandatory verification item"}
                  {selectedSource?.audit_method ? ` · method: ${statusLabel(selectedSource.audit_method)}` : ""}
                  {selectedSource?.sampling_requirement ? ` · sample: ${selectedSource.sampling_requirement}` : ""}
                  {selectedSource?.finding_trigger && selectedSource.finding_trigger !== "NONE" ? ` · governed finding trigger: ${statusLabel(selectedSource.finding_trigger)}` : ""}
                </small>
                {(selectedSource?.na_justification_required || (selectedSource?.notes_required_when || []).length || (selectedSource?.evidence_required_when || []).length) ? (
                  <small>
                    Rules:
                    {selectedSource?.na_justification_required ? " N/A reason required." : ""}
                    {(selectedSource?.notes_required_when || []).length ? ` Notes required for ${selectedSource?.notes_required_when?.map(statusLabel).join(", ")}.` : ""}
                    {(selectedSource?.evidence_required_when || []).length ? ` Evidence required for ${selectedSource?.evidence_required_when?.map(statusLabel).join(", ")}.` : ""}
                  </small>
                ) : null}
              </section>

              <section className="qms-live-audit-focus__compliance" aria-label="Compliance evidence analysis">
                <header>
                  <div><span>Compliance intelligence</span><h3>Evidence, applicability and verification</h3></div>
                  <small>{evidenceCandidatesQuery.data?.evidence_context || selectedSource?.evidence_context || "GENERAL"} · {evidenceCandidatesQuery.data?.retrieval_mode || (connectivity === "OFFLINE" ? "OFFLINE / FROZEN" : "Loading")}</small>
                </header>

                {connectivity === "OFFLINE" ? <p className="qms-live-audit-focus__intelligence-note">Controlled-source search is unavailable offline. The frozen checklist, saved structured assessment and downloaded evidence remain available; reconnect before adding new documentary sources.</p> : null}
                {evidenceCandidatesQuery.data?.applicability_context?.length ? (
                  <div className="qms-live-audit-focus__scope-context" aria-label="Frozen audit applicability context">
                    <strong>Audit scope context</strong>
                    <div>{evidenceCandidatesQuery.data.applicability_context.map((fact) => (
                      <span key={fact.id} title={fact.reason}>
                        {statusLabel(fact.target_type)} · {fact.target_value || fact.target_id || "Governed target"}
                      </span>
                    ))}</div>
                    <small>Frozen during Prepare and used only to evaluate governed applicability rules for this audit.</small>
                  </div>
                ) : null}
                {evidenceCandidatesQuery.isLoading ? <p className="qms-live-audit-focus__intelligence-note">Searching current-approved controlled sources…</p> : null}
                {evidenceCandidatesQuery.isError ? <p className="qms-live-audit-focus__intelligence-warning">Controlled-source retrieval could not be verified. Do not infer documentary compliance from the search failure.</p> : null}

                {assessment ? <>
                  {evidenceCandidatesQuery.data ? <div className="qms-live-audit-focus__recommendations">
                    <article data-status={evidenceCandidatesQuery.data.applicability_recommendation.status}>
                      <span>Applicability recommendation</span>
                      <strong>{statusLabel(evidenceCandidatesQuery.data.applicability_recommendation.status)}</strong>
                      <p>{evidenceCandidatesQuery.data.applicability_recommendation.reason}</p>
                      {canExecute && evidenceCandidatesQuery.data.applicability_recommendation.status !== "UNVERIFIED" ? <button type="button" onClick={() => updateAssessmentDraft({
                        applicability: evidenceCandidatesQuery.data!.applicability_recommendation.status,
                        applicability_reason: evidenceCandidatesQuery.data!.applicability_recommendation.status === "NOT_APPLICABLE"
                          ? evidenceCandidatesQuery.data!.applicability_recommendation.reason
                          : null,
                        applicability_basis: evidenceCandidatesQuery.data!.applicability_recommendation.basis,
                      })}>Use governed basis</button> : null}
                    </article>
                    <article data-status={evidenceCandidatesQuery.data.documentary_recommendation}>
                      <span>Documentary recommendation</span>
                      <strong>{statusLabel(evidenceCandidatesQuery.data.documentary_recommendation)}</strong>
                      <p>This recommendation describes the controlled documentary basis only. It does not decide implementation, field verification or the final audit response.</p>
                      {canExecute ? <button type="button" onClick={() => updateAssessmentDraft({
                        documentary_status: evidenceCandidatesQuery.data!.documentary_recommendation,
                        conflicts: evidenceCandidatesQuery.data!.conflicts,
                      })}>Use documentary recommendation</button> : null}
                    </article>
                    <article data-status={evidenceCandidatesQuery.data.conflicts.length ? "CONFLICT" : "UNVERIFIED"}>
                      <span>Document conflict check</span>
                      <strong>{String(evidenceCandidatesQuery.data.conflicts.length)} {evidenceCandidatesQuery.data.conflicts.length === 1 ? "conflict" : "conflicts"}</strong>
                      <p>{evidenceCandidatesQuery.data.conflicts.length ? "Competing requirements are preserved; no source was silently selected as the winner." : "No deterministic conflict was found in this retrieved set; that does not prove no contradiction exists elsewhere."}</p>
                      {canExecute && evidenceCandidatesQuery.data.conflicts.length ? <button type="button" onClick={() => updateAssessmentDraft({
                        documentary_status: "CONFLICT",
                        conflicts: evidenceCandidatesQuery.data!.conflicts,
                      })}>Preserve conflicts in assessment</button> : null}
                    </article>
                  </div> : null}

                  <div className="qms-live-audit-focus__assessment-grid">
                    <label><span>Applicability</span><select disabled={!canExecute} value={assessment.applicability} onChange={(event) => {
                      const value = event.target.value as ChecklistAssessmentState["applicability"];
                      updateAssessmentDraft({
                        applicability: value,
                        applicability_reason: value === "NOT_APPLICABLE" ? assessment.applicability_reason : null,
                        applicability_basis: value === "NOT_APPLICABLE" ? assessment.applicability_basis : [],
                      });
                    }}><option value="UNVERIFIED">Unverified</option><option value="APPLICABLE">Applicable</option><option value="NOT_APPLICABLE">Not applicable</option></select></label>
                    <label><span>Documentary status</span><select disabled={!canExecute} value={assessment.documentary_status} onChange={(event) => updateAssessmentDraft({ documentary_status: event.target.value as DocumentaryStatus })}>
                      <option value="UNVERIFIED">Unverified</option><option value="DOCUMENTED">Documented</option><option value="PARTIALLY_DOCUMENTED">Partially documented</option><option value="NOT_DOCUMENTED">Not documented</option><option value="NOT_EVIDENCED">Not evidenced</option><option value="CONFLICT">Conflict</option>
                    </select></label>
                    <label><span>Implementation status</span><select disabled={!canExecute} value={assessment.implementation_status} onChange={(event) => updateAssessmentDraft({ implementation_status: event.target.value as ImplementationStatus })}>
                      <option value="UNVERIFIED">Unverified</option><option value="OBJECTIVE_EVIDENCE_AVAILABLE">Objective evidence available</option><option value="VERIFIED">Verified</option><option value="NOT_VERIFIED">Not verified</option><option value="NOT_EVIDENCED">Not evidenced</option>
                    </select></label>
                    <label><span>Field verification</span><select disabled={!canExecute} value={assessment.field_verification_status} onChange={(event) => updateAssessmentDraft({ field_verification_status: event.target.value as FieldVerificationStatus })}>
                      <option value="UNVERIFIED">Unverified</option><option value="FIELD_VERIFICATION_REQUIRED">Field verification required</option><option value="VERIFIED">Verified</option><option value="NOT_VERIFIED">Not verified</option><option value="NOT_APPLICABLE">Not applicable</option>
                    </select></label>
                  </div>

                  {assessment.applicability === "NOT_APPLICABLE" ? <div className="qms-live-audit-focus__na-basis">
                    <strong>N/A basis</strong>
                    <p>{assessment.applicability_reason || "No governed reason has been preserved yet."}</p>
                    <small>{assessment.applicability_basis.length ? String(assessment.applicability_basis.length) + " governed basis record(s) preserved." : "N/A cannot be finalized until a governed basis is preserved."}</small>
                  </div> : null}

                  <div className="qms-live-audit-focus__candidate-list">
                    <header><strong>Current-approved documentary candidates</strong><span>{evidenceCandidates.length}</span></header>
                    {!evidenceCandidates.length && !evidenceCandidatesQuery.isLoading ? <p>No current-approved controlled source was retrieved for this question.</p> : null}
                    {evidenceCandidates.map((candidate) => {
                      const checked = assessment.evidence_ids.includes(candidate.evidence_id);
                      const outsideScope = candidate.applicability.status === "NOT_APPLICABLE";
                      return <article key={candidate.evidence_id} className={checked ? "is-selected" : ""}>
                        <label>
                          <input type="checkbox" checked={checked} disabled={!canExecute || outsideScope} onChange={(event) => toggleDocumentaryCandidate(candidate, event.target.checked)} />
                          <div><strong>{candidate.document_code || candidate.document_title || "Controlled source"}{candidate.heading ? " · " + candidate.heading : ""}</strong><span>Rev {candidate.revision || "—"}{candidate.page_number ? " · page " + candidate.page_number : ""}</span><small>{candidate.evidence_role ? statusLabel(candidate.evidence_role) : "Unclassified evidence role"}{candidate.authority_priority != null ? " · authority " + candidate.authority_priority : ""} · {statusLabel(candidate.applicability.status)}</small></div>
                        </label>
                        {candidate.snippet ? <p>{candidate.snippet}</p> : null}
                        <footer><span>{candidate.retrieval_channels.join(" + ") || "CONTROLLED"}</span>{candidate.reader_url ? <a href={candidate.reader_url} target="_blank" rel="noreferrer">Open source</a> : null}</footer>
                      </article>;
                    })}
                  </div>

                  {evidenceCandidatesQuery.data?.authority_policy && Object.keys(evidenceCandidatesQuery.data.authority_policy).length ? <div className="qms-live-audit-focus__authority-policy">
                    <strong>Evidence precedence for this question</strong>
                    <ol>{Object.entries(evidenceCandidatesQuery.data.authority_policy).sort((left, right) => right[1] - left[1]).map(([role, priority]) => <li key={role}><span>{statusLabel(role)}</span><b>{priority}</b></li>)}</ol>
                    <small>This ranking is context-specific evidence precedence, not a universal legal hierarchy.</small>
                  </div> : null}

                  {evidenceCandidatesQuery.data?.conflicts.length ? <div className="qms-live-audit-focus__document-conflicts">
                    <strong>Competing controlled statements</strong>
                    {evidenceCandidatesQuery.data.conflicts.map((conflict, index) => {
                      const sources = Array.isArray(conflict.sources) ? conflict.sources : [];
                      return <article key={index}>
                        <header><span>{statusLabel(String(conflict.detector || "DOCUMENT_CONFLICT"))}</span><b>{String(conflict.confidence || "REVIEW")}</b></header>
                        {sources.map((source, sourceIndex) => <div key={sourceIndex}><strong>{conflictSourceLabel(source)}</strong>{conflictClause(source) ? <p>{conflictClause(source)}</p> : null}</div>)}
                        <small>Auditor review required. No source is silently selected as the winner.</small>
                      </article>;
                    })}
                  </div> : null}

                  {evidenceCandidatesQuery.data?.limitations.length ? <div className="qms-live-audit-focus__intelligence-limitations">
                    <strong>Verification limits</strong>
                    <ul>{evidenceCandidatesQuery.data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div> : null}

                  <div className="qms-live-audit-focus__assessment-notes">
                    <label><span>Regulation references</span><input readOnly={!canExecute} value={assessment.regulation_refs.join(", ")} onChange={(event) => updateAssessmentDraft({ regulation_refs: csvValues(event.target.value) })} placeholder="Only references supported by the frozen checklist or selected current source" /></label>
                    <label><span>Procedure / manual references</span><input readOnly={!canExecute} value={assessment.procedure_refs.join(", ")} onChange={(event) => updateAssessmentDraft({ procedure_refs: csvValues(event.target.value) })} placeholder="e.g. MPM 2.5.8" /></label>
                    <label><span>Missing evidence</span><textarea readOnly={!canExecute} rows={2} value={assessment.missing_evidence.join("\n")} onChange={(event) => updateAssessmentDraft({ missing_evidence: lineValues(event.target.value) })} placeholder="One missing evidence item per line" /></label>
                    <label><span>Fieldwork requirements</span><textarea readOnly={!canExecute} rows={2} value={assessment.fieldwork_requirements.join("\n")} onChange={(event) => {
                      const requirements = lineValues(event.target.value);
                      updateAssessmentDraft({
                        fieldwork_requirements: requirements,
                        field_verification_status: requirements.length && assessment.field_verification_status === "UNVERIFIED" ? "FIELD_VERIFICATION_REQUIRED" : assessment.field_verification_status,
                      });
                    }} placeholder="Inspection, observation, interview or sample still required" /></label>
                    <label className="is-wide"><span>Auditor decision / override rationale</span><textarea readOnly={!canExecute} rows={2} value={assessment.human_override_reason || ""} onChange={(event) => updateAssessmentDraft({ human_override_reason: event.target.value || null })} placeholder="Required by local procedure where the final human decision differs from the evidence recommendation." /></label>
                  </div>
                  {assessment.ai_analysis?.conclusion ? <div className="qms-live-audit-focus__ai-analysis"><strong>Structured AI assistance</strong><p>{assessment.ai_analysis.conclusion}</p><small>{assessment.ai_analysis.confidence_basis || "No confidence basis recorded."}</small></div> : null}
                  {canExecute ? <div className="qms-live-audit-focus__assessment-actions">
                    <button type="button" disabled={updateMutation.isPending} onClick={saveCurrentAssessment}>
                      {updateMutation.isPending ? "Saving…" : "Save assessment"}
                    </button>
                    <small>Saves the evidence basis and verification state without changing the current checklist outcome.</small>
                  </div> : null}
                </> : null}
              </section>

              <div className="qms-live-audit-focus__responses" aria-label="Checklist response">
                {selectedResponseOptions.length ? selectedResponseOptions.map((option) => {
                  const canonical = option.canonical_status as CanonicalChecklistResponse;
                  const Icon = responseIcon(canonical);
                  const active = selected.response_value
                    ? selected.response_value === option.value
                    : selected.canonical_response_status === canonical;
                  return <button type="button" key={option.value} className={active ? "is-active" : ""} disabled={!canExecute || updateMutation.isPending || findingMutation.isPending} onClick={() => selectResponse(selected, option)}><Icon size={17} /> {option.label}</button>;
                }) : <span role="alert">This checklist item has no governed response options. Return to preparation and issue a corrected checklist revision.</span>}
              </div>

              {selectedSource?.sampling_requirement || selectedSource?.audit_method === "SAMPLE" ? <label className="qms-live-audit-focus__notes"><span>Sampled items / records</span><textarea readOnly={!canExecute} value={sampledItems} onChange={(event) => setSampleDrafts((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} rows={3} placeholder="Record the sampled records, serials, work packs, dates or other sample identifiers." /></label> : null}
              <label className="qms-live-audit-focus__notes"><span>Auditor note</span><textarea readOnly={!canExecute} value={notes} onChange={(event) => setNoteDrafts((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} rows={5} placeholder="Record objective, attributable fieldwork notes." /></label>
              <div className="qms-live-audit-focus__note-actions"><button type="button" disabled={!canExecute || updateMutation.isPending} onClick={saveCurrentAssessment}>{updateMutation.isPending ? "Saving…" : "Save notes & assessment"}</button></div>

              <div id="audit-occurrence-evidence">
                <LiveAuditEvidenceStrip
                  amoCode={amoCode}
                  auditId={auditId}
                  item={selected}
                  canManage={canExecute}
                  selectedAssessmentEvidenceIds={assessment?.evidence_ids || []}
                  onAssessmentEvidenceChange={(artifactId, checked) => {
                    if (!assessment) return;
                    const nextIds = new Set(assessment.evidence_ids);
                    if (checked) nextIds.add(artifactId);
                    else nextIds.delete(artifactId);
                    updateAssessmentDraft({ evidence_ids: Array.from(nextIds) });
                  }}
                  onChanged={refreshFieldwork}
                  onError={setLocalError}
                  onNotice={setSyncNotice}
                />
              </div>

              <footer className="qms-live-audit-focus__nav"><button type="button" onClick={() => move(-1)} disabled={selectedIndex <= 0}><ArrowLeft size={16} /> Previous</button><button type="button" onClick={() => move(1)} disabled={selectedIndex < 0 || selectedIndex >= visibleItems.length - 1}>Next <ArrowRight size={16} /></button></footer>
            </>
          ) : <div className="qms-live-audit-focus__empty">
            <strong>No governed checklist is available for fieldwork.</strong>
            <p>Return to Prepare, bind or create the controlled checklist, resolve readiness blockers, and issue preparation before continuing.</p>
            <Link to={auditSessionPath(amoCode, auditKey, "prepare")}>Open Prepare</Link>
          </div>}
        </main>

        <aside className="qms-live-audit-focus__summary">
          <section>
            <span>Progress</span>
            <strong>{percent != null ? `${percent}%` : "N/A"}</strong>
            <small>
              {items.length ? `${completed} of ${items.length} questions resolved` : "No required checklist items"}
            </small>
          </section>
          <section className="qms-live-audit-focus__stats"><div><strong>{counts.COMPLIANT}</strong><span>Compliant</span></div><div><strong>{counts.NONCOMPLIANT}</strong><span>NCR</span></div><div><strong>{counts.OBSERVATION}</strong><span>Observations</span></div><div><strong>{counts.NOT_VERIFIED}</strong><span>Pending</span></div></section>
          <section><span>Device sync</span><strong>{outbox.queued + outbox.conflicts + outbox.failed}</strong><small>{outbox.queued} pending · {outbox.conflicts} conflict · {outbox.failed} failed. Conflicts require review; they are never silently overwritten.</small></section>
          <section className="qms-live-audit-focus__presence">
            <span><Users size={14} /> Audit team live</span>
            <strong>{auditTeamPresence.length}</strong>
            <ul>{auditTeamPresence.slice(0, 8).map((entry) => <li key={entry.id}><b>{entry.display_name}</b><small>{entry.role || statusLabel(entry.actor_type)}{entry.route ? ` · ${entry.route}` : ""}</small></li>)}</ul>
          </section>
          <section className="qms-live-audit-focus__presence">
            <span><Eye size={14} /> Auditee viewing</span>
            <strong>{auditeePresence.length}</strong>
            <small>{auditeePresence.length ? auditeePresence.map((entry) => entry.display_name).join(", ") : "No auditee guest with progress/presence scope is currently active."}</small>
          </section>
          <section id="audit-occurrence-findings"><span>Findings</span><strong>{findings.length}</strong><ul>{findings.slice(0, 6).map((finding) => <li key={finding.id}><b>{finding.finding_ref || finding.level}{finding.closed_at ? " · Closed" : ""}</b><small>{finding.description}</small></li>)}</ul></section>
          <section className="qms-live-audit-focus__sharing"><span>Auditee live view</span><strong>Released-data boundary active</strong><small>Auditees receive only server-released findings and permitted progress/evidence projections; private checklist notes remain internal.</small></section>
        </aside>
      </div>

      {findingDraft ? (
        <div className="qms-live-audit-finding-backdrop" role="presentation">
          <section className="qms-live-audit-finding" role="dialog" aria-modal="true" aria-label="Raise finding">
            <header><div><span>{findingDraft.mode === "NONCOMPLIANT" ? "NON-CONFORMITY" : "OBSERVATION"}</span><h2>Raise finding from checklist</h2></div><button type="button" onClick={() => setFindingDraft(null)} aria-label="Close finding composer"><X size={18} /></button></header>
            <dl><div><dt>Requirement</dt><dd>{findingDraft.item.requirement_ref || findingDraft.item.checklist_ref || "—"}</dd></div></dl>
            {findingDraft.mode === "NONCOMPLIANT" ? <label><span>Classification</span><select value={findingDraft.level} onChange={(event) => setFindingDraft((current) => current ? { ...current, level: event.target.value as NonconformityLevel } : current)}><option value="">Select governed level</option>{NONCONFORMITY_LEVELS.map((level) => <option key={level.value} value={level.value}>{level.label}</option>)}</select></label> : null}
            <label><span>Finding statement</span><textarea rows={5} value={findingDraft.statement} onChange={(event) => setFindingDraft((current) => current ? { ...current, statement: event.target.value } : current)} /></label>
            <label><span>Objective evidence</span><textarea rows={4} value={findingDraft.objectiveEvidence} onChange={(event) => setFindingDraft((current) => current ? { ...current, objectiveEvidence: event.target.value } : current)} /></label>
            <p>{findingDraft.mode === "NONCOMPLIANT" ? "Select the applicable governed finding level. The workspace does not infer severity from the checklist response." : "This creates a governed observation linked to the exact checklist item."}</p>
            <footer><button type="button" onClick={() => setFindingDraft(null)}>Cancel</button><button type="button" className="is-primary" disabled={findingDraft.statement.trim().length < 8 || (findingDraft.mode === "NONCOMPLIANT" && !findingDraft.level) || findingMutation.isPending} onClick={() => findingMutation.mutate(findingDraft)}>{findingMutation.isPending ? "Creating…" : "Create finding"}</button></footer>
          </section>
        </div>
      ) : null}
    </div>
  );
};

export default LiveAuditWorkspace;