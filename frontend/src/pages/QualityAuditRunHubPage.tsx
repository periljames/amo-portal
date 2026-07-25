import React, { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  ClipboardCheck,
  ClipboardList,
  Download,
  ExternalLink,
  FileCheck2,
  FileClock,
  FilePenLine,
  FilePlus2,
  FileSearch,
  FileText,
  Flag,
  FolderArchive,
  History,
  Lock,
  MailCheck,
  MessageSquare,
  PackageCheck,
  Paperclip,
  Plus,
  RefreshCcw,
  Save,
  Send,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UploadCloud,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import AuditPageShell from "../components/QMS/AuditPageShell";
import QualityChecklistPdfEditor from "../components/QMS/QualityChecklistPdfEditor";
import { getCachedUser, getContext } from "../services/auth";
import {
  downloadAuditEvidencePack,
  qmsCreateAuditChecklistItem,
  qmsCreateCar,
  qmsCreateFinding,
  qmsDeleteFinding,
  qmsFlagFindingForReview,
  qmsGetAuditRegister,
  qmsIssueAuditNotice,
  qmsListAuditChecklistItems,
  qmsListAuditFindingAttachments,
  qmsListCarAttachmentsBulk,
  qmsListCars,
  qmsResolveAudit,
  qmsReviewCarResponse,
  qmsUpdateAuditChecklistItem,
  qmsUpdateCar,
  qmsUpdateFinding,
  qmsUploadFindingAttachment,
  type CARAttachmentOut,
  type CAROut,
  type QMSAuditRegisterRowOut,
  type QMSFindingAttachmentOut,
  type QMSFindingOut,
  type QualityChecklistItemOut,
} from "../services/qms";
import {
  qmsAddCarAction,
  qmsListCarActions,
  qmsShareAuditReport,
  type CARActionOut,
} from "../services/qmsAuditHubActions";
import {
  qmsCloseAuditLifecycle,
  qmsCompleteAuditChecklist,
  qmsCompleteAuditFieldwork,
  qmsGetAuditWarRoomContext,
  qmsIssueReportVersion,
  qmsReviewAuditEvidence,
  qmsStartAuditLifecycle,
  qmsUploadChecklistSource,
  qmsUploadReportDraft,
  type QualityAuditActionItem,
  type QualityAuditDocument,
  type QualityAuditStage,
  type QualityAuditWarRoomContext,
} from "../services/qmsAuditLifecycle";
import {
  qmsDownloadLifecycleDocumentFile,
  qmsListAuditEvidenceReviews,
  qmsOpenAuthenticatedQualityPath,
  qmsOpenLifecycleDocument,
  qmsRecordReportDistribution,
} from "../services/qmsAuditLifecycleQueries";
import { saveDownloadedFile } from "../utils/downloads";
import "./qualityAudits/quality-audit-workbench-v2.css";

const TABS = ["war-room", "checklist", "findings", "cars", "evidence", "report", "closeout"] as const;
type WorkspaceTab = typeof TABS[number];

const TAB_LABELS: Record<WorkspaceTab, string> = {
  "war-room": "War room",
  checklist: "Checklist",
  findings: "Findings",
  cars: "CARs",
  evidence: "Evidence",
  report: "Report",
  closeout: "Closeout",
};

const TAB_TITLES: Record<WorkspaceTab, string> = {
  "war-room": "Pre-audit command room",
  checklist: "Controlled checklist",
  findings: "Fieldwork findings",
  cars: "Corrective action requests",
  evidence: "Evidence verification",
  report: "Controlled audit report",
  closeout: "Formal closeout",
};

const FINDING_LEVELS = [
  { value: "LEVEL_1", label: "Level 1 · Critical", severity: "CRITICAL", priority: "CRITICAL" },
  { value: "LEVEL_2", label: "Level 2 · Major", severity: "MAJOR", priority: "HIGH" },
  { value: "LEVEL_3", label: "Level 3 · Minor", severity: "MINOR", priority: "MEDIUM" },
  { value: "LEVEL_4", label: "Observation", severity: "MINOR", priority: "LOW" },
] as const;

type FindingLevel = typeof FINDING_LEVELS[number]["value"];

const REPORT_RECIPIENT_GROUPS = [
  ["accountable_manager", "Accountable Manager"],
  ["quality_manager", "Quality Manager"],
  ["department_heads", "Department Heads"],
  ["audited_department", "Audited department"],
  ["shop_personnel", "Shop personnel"],
  ["facility_personnel", "Facility personnel"],
] as const;

function safeTab(value: string | null): WorkspaceTab {
  return TABS.includes((value || "") as WorkspaceTab) ? value as WorkspaceTab : "war-room";
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not recorded";
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function dateTimeLabel(value?: string | null): string {
  if (!value) return "Not recorded";
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function bytesLabel(value?: number | null): string {
  const size = Number(value || 0);
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return size > 0 ? `${size} B` : "Size unavailable";
}

function referenceSlug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function buildFindingReference(auditRef: string, rows: QMSAuditRegisterRowOut[]): string {
  let maximum = 0;
  for (const row of rows) {
    const match = String(row.finding.finding_ref || "").match(/(?:F|FIND)[-\/]?(\d+)$/i);
    if (match) maximum = Math.max(maximum, Number(match[1]) || 0);
  }
  return `${auditRef}-F-${String(maximum + 1).padStart(3, "0")}`;
}

function stageStateLabel(stage: QualityAuditStage): string {
  switch (stage.state) {
    case "NOT_READY": return "Not ready";
    case "READY": return "Ready";
    case "IN_PROGRESS": return "In progress";
    case "BLOCKED": return "Blocked";
    case "COMPLETE": return "Complete";
    case "LOCKED": return stage.complete ? "Complete · locked" : "Locked";
    default: return stage.state;
  }
}

function actionStateIcon(state: QualityAuditActionItem["state"]): React.ReactNode {
  if (state === "COMPLETE") return <CheckCircle2 size={16} />;
  if (state === "BLOCKED") return <ShieldAlert size={16} />;
  if (state === "WARNING") return <AlertTriangle size={16} />;
  if (state === "READY") return <ArrowRight size={16} />;
  return <CircleDashed size={16} />;
}

function currentStage(context: QualityAuditWarRoomContext | undefined, tab: WorkspaceTab): QualityAuditStage | null {
  return context?.workflow.stages.find((stage) => stage.id === tab) ?? null;
}

function findingLevelLabel(value?: string | null): string {
  return FINDING_LEVELS.find((item) => item.value === value)?.label || value || "Finding";
}

function downloadNameForPack(reference: string): string {
  return `${reference.replace(/[^A-Za-z0-9._-]+/g, "-")}-evidence-pack.zip`;
}

type EvidenceItem = {
  key: string;
  entityType: "CHECKLIST_VERSION" | "FINDING_ATTACHMENT" | "CAR_ATTACHMENT";
  entityId: string;
  title: string;
  source: string;
  meta: string;
  open: () => Promise<void>;
};

const QualityAuditRunHubPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string; department?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const context = getContext();
  const currentUser = getCachedUser();
  const amoCode = params.amoCode || context.amoCode || "UNKNOWN";
  const department = params.department || "quality";
  const auditKey = params.auditId || "";
  const activeTab = safeTab(searchParams.get("tab"));

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [pdfEditorOpen, setPdfEditorOpen] = useState(false);
  const [checklistDraft, setChecklistDraft] = useState({ section: "", requirement_ref: "", prompt: "", objective_evidence: "" });
  const [findingForm, setFindingForm] = useState({
    level: "LEVEL_3" as FindingLevel,
    requirement_ref: "",
    description: "",
    objective_evidence: "",
    target_close_date: "",
    safety_sensitive: false,
  });
  const [findingFiles, setFindingFiles] = useState<File[]>([]);
  const findingFileInputRef = useRef<HTMLInputElement | null>(null);
  const [editingFindingId, setEditingFindingId] = useState<string | null>(null);
  const [findingEdit, setFindingEdit] = useState({
    level: "LEVEL_3" as FindingLevel,
    requirement_ref: "",
    description: "",
    objective_evidence: "",
    target_close_date: "",
    safety_sensitive: false,
  });
  const [selectedCarId, setSelectedCarId] = useState<string | null>(null);
  const [carMessage, setCarMessage] = useState("");
  const [reportIssueLabel, setReportIssueLabel] = useState("Issue 1");
  const [reportShareGroups, setReportShareGroups] = useState<string[]>(["quality_manager", "audited_department"]);

  const resolveQuery = useQuery({
    queryKey: ["qms-audit-resolve-v2", auditKey],
    queryFn: () => qmsResolveAudit(auditKey, { silent: true }),
    enabled: Boolean(auditKey),
    staleTime: 60_000,
  });

  const auditId = resolveQuery.data?.id || null;

  const warRoomQuery = useQuery({
    queryKey: ["qms-audit-lifecycle", auditId],
    queryFn: () => qmsGetAuditWarRoomContext(auditId!),
    enabled: Boolean(auditId),
    staleTime: 20_000,
    retry: 1,
  });

  const registerQuery = useQuery({
    queryKey: ["qms-audit-register-v2", auditId],
    queryFn: () => qmsGetAuditRegister({ audit_id: auditId!, limit: 250 }, { silent: true }),
    enabled: Boolean(auditId),
    staleTime: 20_000,
  });

  const checklistItemsQuery = useQuery({
    queryKey: ["qms-audit-checklist-items-v2", auditId],
    queryFn: () => qmsListAuditChecklistItems(auditId!),
    enabled: Boolean(auditId),
    staleTime: 20_000,
  });

  const carsQuery = useQuery({
    queryKey: ["qms-audit-cars-v2", auditId],
    queryFn: () => qmsListCars({ audit_id: auditId!, limit: 250 }, { silent: true }),
    enabled: Boolean(auditId),
    staleTime: 20_000,
  });

  const findingAttachmentsQuery = useQuery({
    queryKey: ["qms-audit-finding-attachments-v2", auditId],
    queryFn: () => qmsListAuditFindingAttachments(auditId!),
    enabled: Boolean(auditId),
    staleTime: 30_000,
  });

  const carIds = useMemo(() => (carsQuery.data || []).map((car) => car.id), [carsQuery.data]);
  const carAttachmentsQuery = useQuery({
    queryKey: ["qms-audit-car-attachments-v2", auditId, carIds.join(",")],
    queryFn: () => qmsListCarAttachmentsBulk({ car_ids: carIds }),
    enabled: Boolean(auditId) && carIds.length > 0,
    staleTime: 30_000,
  });

  const evidenceReviewsQuery = useQuery({
    queryKey: ["qms-audit-evidence-reviews-v2", auditId],
    queryFn: () => qmsListAuditEvidenceReviews(auditId!),
    enabled: Boolean(auditId),
    staleTime: 15_000,
  });

  const selectedCar = useMemo(() => {
    const rows = carsQuery.data || [];
    return rows.find((car) => car.id === selectedCarId) || rows[0] || null;
  }, [carsQuery.data, selectedCarId]);

  const carActionsQuery = useQuery({
    queryKey: ["qms-audit-car-actions-v2", selectedCar?.id],
    queryFn: () => qmsListCarActions(selectedCar!.id),
    enabled: activeTab === "cars" && Boolean(selectedCar?.id),
    staleTime: 0,
    refetchInterval: activeTab === "cars" && selectedCar?.id ? 5_000 : false,
  });

  const audit = warRoomQuery.data?.audit || resolveQuery.data || null;
  const workflow = warRoomQuery.data?.workflow;
  const findings = registerQuery.data?.rows || [];
  const checklistItems = checklistItemsQuery.data || [];
  const cars = carsQuery.data || [];
  const findingAttachments = findingAttachmentsQuery.data || [];
  const carAttachments = carAttachmentsQuery.data || [];
  const reviewMap = useMemo(() => new Map(
    (evidenceReviewsQuery.data || []).map((review) => [`${review.entity_type}:${review.entity_id}`, review]),
  ), [evidenceReviewsQuery.data]);

  const assignedUserIds = audit ? [audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].filter(Boolean) : [];
  const isAssigned = Boolean(currentUser?.id && assignedUserIds.includes(currentUser.id));
  const isQualityAdmin = Boolean(currentUser?.is_superuser || currentUser?.is_amo_admin || ["SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER"].includes(String(currentUser?.role || "").toUpperCase()));
  const canManageAudit = isAssigned || isQualityAdmin;

  const refreshAudit = async () => {
    if (!auditId) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["qms-audit-lifecycle", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-register-v2", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-checklist-items-v2", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-cars-v2", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-finding-attachments-v2", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-car-attachments-v2", auditId] }),
      queryClient.invalidateQueries({ queryKey: ["qms-audit-evidence-reviews-v2", auditId] }),
    ]);
  };

  const mutationOptions = {
    onError: (error: Error) => {
      setActionNotice(null);
      setActionError(error.message || "The Quality action could not be completed.");
    },
  };

  const startAuditMutation = useMutation({
    mutationFn: () => qmsStartAuditLifecycle(auditId!, "Opening brief confirmed in the audit War room."),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Opening brief recorded. The controlled checklist is now in progress.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const completeChecklistMutation = useMutation({
    mutationFn: () => qmsCompleteAuditChecklist(auditId!, "Checklist responses reviewed and checklist stage completed."),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Checklist stage completed. Fieldwork findings remain open until formally closed.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const completeFieldworkMutation = useMutation({
    mutationFn: () => qmsCompleteAuditFieldwork(auditId!, "Fieldwork completed and checklist exceptions dispositioned."),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Fieldwork completed. Review CAR issuance and supporting evidence.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const closeoutMutation = useMutation({
    mutationFn: () => qmsCloseAuditLifecycle(auditId!, "Closeout approved from the audit workspace."),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Audit closed and retained archive record generated.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const noticeMutation = useMutation({
    mutationFn: () => qmsIssueAuditNotice(auditId!, { stage: "manual" }),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Audit notice dispatched and recorded in the communication history.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const sourceUploadMutation = useMutation({
    mutationFn: (file: File) => qmsUploadChecklistSource(auditId!, file, { fillable: "UNKNOWN" }),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Controlled checklist source uploaded as a retained version.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const createChecklistItemMutation = useMutation({
    mutationFn: () => qmsCreateAuditChecklistItem(auditId!, {
      section: checklistDraft.section.trim() || null,
      requirement_ref: checklistDraft.requirement_ref.trim() || null,
      prompt: checklistDraft.prompt.trim(),
      objective_evidence: checklistDraft.objective_evidence.trim() || null,
      response_status: "PENDING",
      sort_order: checklistItems.length,
    }),
    onSuccess: async () => {
      setChecklistDraft({ section: "", requirement_ref: "", prompt: "", objective_evidence: "" });
      setActionError(null);
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const updateChecklistItemMutation = useMutation({
    mutationFn: ({ itemId, patch }: { itemId: string; patch: Partial<QualityChecklistItemOut> }) => qmsUpdateAuditChecklistItem(auditId!, itemId, patch),
    onSuccess: async () => {
      setActionError(null);
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const createFindingMutation = useMutation({
    mutationFn: async () => {
      const selectedLevel = FINDING_LEVELS.find((item) => item.value === findingForm.level) || FINDING_LEVELS[2];
      if (!findingForm.description.trim()) throw new Error("Finding statement is required.");
      const saved = await qmsCreateFinding(auditId!, {
        finding_ref: buildFindingReference(audit!.audit_ref, findings),
        finding_type: findingForm.level === "LEVEL_4" ? "OBSERVATION" : "NON_CONFORMITY",
        severity: selectedLevel.severity,
        level: findingForm.level,
        requirement_ref: findingForm.requirement_ref.trim() || null,
        description: findingForm.description.trim(),
        objective_evidence: findingForm.objective_evidence.trim() || null,
        safety_sensitive: findingForm.safety_sensitive,
        target_close_date: findingForm.level === "LEVEL_4" ? null : findingForm.target_close_date || null,
      });
      for (const file of findingFiles) await qmsUploadFindingAttachment(saved.id, file);
      return saved;
    },
    onSuccess: async () => {
      setFindingForm({ level: "LEVEL_3", requirement_ref: "", description: "", objective_evidence: "", target_close_date: "", safety_sensitive: false });
      setFindingFiles([]);
      if (findingFileInputRef.current) findingFileInputRef.current.value = "";
      setActionError(null);
      setActionNotice("Finding recorded with its supporting evidence.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const updateFindingMutation = useMutation({
    mutationFn: (row: QMSFindingOut) => {
      const selectedLevel = FINDING_LEVELS.find((item) => item.value === findingEdit.level) || FINDING_LEVELS[2];
      return qmsUpdateFinding(row.id, {
        finding_type: findingEdit.level === "LEVEL_4" ? "OBSERVATION" : "NON_CONFORMITY",
        severity: selectedLevel.severity,
        level: findingEdit.level,
        requirement_ref: findingEdit.requirement_ref.trim() || null,
        description: findingEdit.description.trim(),
        objective_evidence: findingEdit.objective_evidence.trim() || null,
        target_close_date: findingEdit.level === "LEVEL_4" ? null : findingEdit.target_close_date || null,
        safety_sensitive: findingEdit.safety_sensitive,
      }, auditId!);
    },
    onSuccess: async () => {
      setEditingFindingId(null);
      setActionError(null);
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const deleteFindingMutation = useMutation({
    mutationFn: (findingId: string) => qmsDeleteFinding(findingId, auditId!),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Finding removed from the active register.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const flagFindingMutation = useMutation({
    mutationFn: ({ findingId, reason }: { findingId: string; reason: string }) => qmsFlagFindingForReview(findingId, reason, auditId!),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Finding flagged for Quality review.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const issueCarMutation = useMutation({
    mutationFn: (row: QMSAuditRegisterRowOut) => {
      const level = FINDING_LEVELS.find((item) => item.value === row.finding.level) || FINDING_LEVELS[2];
      return qmsCreateCar({
        program: "QUALITY",
        title: `CAR for ${row.finding.finding_ref || "audit finding"}`,
        summary: [
          row.finding.description,
          row.finding.requirement_ref ? `Requirement: ${row.finding.requirement_ref}` : null,
          row.finding.objective_evidence ? `Objective evidence: ${row.finding.objective_evidence}` : null,
        ].filter(Boolean).join("\n\n"),
        priority: level.priority,
        due_date: row.finding.target_close_date || null,
        target_closure_date: row.finding.target_close_date || null,
        assigned_to_user_id: audit?.auditee_user_id || null,
        finding_id: row.finding.id,
        evidence_required: true,
      });
    },
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("CAR issued and linked to the finding.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const carReviewMutation = useMutation({
    mutationFn: ({ carId, decision, note }: { carId: string; decision: "accept" | "reject" | "evidence"; note?: string }) => qmsReviewCarResponse(carId, decision === "accept" ? {
      root_cause_status: "ACCEPTED",
      capa_status: "ACCEPTED",
      message: "Root cause and CAPA accepted by the auditor.",
    } : decision === "evidence" ? {
      root_cause_status: "ACCEPTED",
      capa_status: "NEEDS_EVIDENCE",
      capa_review_note: note || "Additional evidence is required.",
      message: note || "Additional evidence is required.",
    } : {
      root_cause_status: "REJECTED",
      capa_status: "REJECTED",
      root_cause_review_note: note || "Response rejected by the auditor.",
      capa_review_note: note || "Response rejected by the auditor.",
      message: note || "Response rejected by the auditor.",
    }),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("CAR review decision recorded.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const closeCarMutation = useMutation({
    mutationFn: (carId: string) => qmsUpdateCar(carId, { status: "CLOSED" }),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("CAR marked closed. Closeout will re-evaluate all gates.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const carMessageMutation = useMutation({
    mutationFn: () => qmsAddCarAction(selectedCar!.id, { message: carMessage.trim() }),
    onSuccess: async () => {
      setCarMessage("");
      setActionError(null);
      await carActionsQuery.refetch();
    },
    ...mutationOptions,
  });

  const evidenceReviewMutation = useMutation({
    mutationFn: ({ item, status }: { item: EvidenceItem; status: "PENDING" | "ACCEPTED" | "REJECTED" }) => {
      let note: string | undefined;
      if (status === "REJECTED") {
        note = window.prompt("Reason this evidence is rejected") || undefined;
        if (!note?.trim()) throw new Error("A rejection reason is required.");
      }
      return qmsReviewAuditEvidence(auditId!, {
        entity_type: item.entityType,
        entity_id: item.entityId,
        status,
        note,
      });
    },
    onSuccess: async () => {
      setActionError(null);
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const reportDraftMutation = useMutation({
    mutationFn: (file: File) => qmsUploadReportDraft(auditId!, file),
    onSuccess: async (record) => {
      setActionError(null);
      setActionNotice(`Report draft version ${record.version_number} uploaded. It is not yet issued.`);
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const reportIssueMutation = useMutation({
    mutationFn: (record: QualityAuditDocument) => qmsIssueReportVersion(auditId!, record.id, reportIssueLabel, "Controlled report issued from the audit workspace."),
    onSuccess: async () => {
      setActionError(null);
      setActionNotice("Controlled report version issued. Findings and checklist records are now read-only.");
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const reportShareMutation = useMutation({
    mutationFn: async (record: QualityAuditDocument) => {
      if (!reportShareGroups.length) throw new Error("Select at least one report recipient group.");
      const result = await qmsShareAuditReport(auditId!, {
        recipient_groups: reportShareGroups,
        message: `Issued audit report ${record.issue_label || ""} for ${audit!.audit_ref}. Review assigned corrective actions and closeout responsibilities.`,
      });
      await qmsRecordReportDistribution(auditId!, {
        version_id: record.id,
        status: result.shared > 0 ? "DISTRIBUTED" : "PARTIAL",
        recipient_groups: reportShareGroups,
        shared_count: result.shared,
      });
      return result;
    },
    onSuccess: async (result) => {
      setActionError(null);
      setActionNotice(`Issued report distributed to ${result.shared} recipient${result.shared === 1 ? "" : "s"}.`);
      await refreshAudit();
    },
    ...mutationOptions,
  });

  const exportPackMutation = useMutation({
    mutationFn: () => downloadAuditEvidencePack(auditId!),
    onSuccess: (blob) => {
      if (audit) saveDownloadedFile(blob, downloadNameForPack(audit.audit_ref));
      setActionError(null);
    },
    ...mutationOptions,
  });

  const setTab = (tab: WorkspaceTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
    setActionError(null);
    setActionNotice(null);
  };

  const activeStage = currentStage(warRoomQuery.data, activeTab);

  const runStageAction = (stage: QualityAuditStage) => {
    if (!stage.primary_action?.enabled) return;
    switch (stage.id) {
      case "war-room": startAuditMutation.mutate(); break;
      case "checklist": setTab("checklist"); break;
      case "findings": completeFieldworkMutation.mutate(); break;
      case "cars": setTab("cars"); break;
      case "evidence": setTab("evidence"); break;
      case "report": setTab("report"); break;
      case "closeout": closeoutMutation.mutate(); break;
      default: break;
    }
  };

  const evidenceItems = useMemo<EvidenceItem[]>(() => {
    const items: EvidenceItem[] = [];
    const checklistRecord = warRoomQuery.data?.checklist.current;
    if (checklistRecord) {
      items.push({
        key: `CHECKLIST_VERSION:${checklistRecord.id}`,
        entityType: "CHECKLIST_VERSION",
        entityId: checklistRecord.id,
        title: checklistRecord.filename,
        source: "Controlled checklist",
        meta: `Version ${checklistRecord.version_number} · ${bytesLabel(checklistRecord.size_bytes)}`,
        open: () => qmsOpenLifecycleDocument(checklistRecord),
      });
    }
    for (const attachment of findingAttachments) {
      const finding = findings.find((row) => row.finding.id === attachment.finding_id)?.finding;
      items.push({
        key: `FINDING_ATTACHMENT:${attachment.id}`,
        entityType: "FINDING_ATTACHMENT",
        entityId: attachment.id,
        title: attachment.filename,
        source: finding?.finding_ref ? `Finding ${finding.finding_ref}` : "Finding evidence",
        meta: `${bytesLabel(attachment.size_bytes)} · ${dateTimeLabel(attachment.uploaded_at)}`,
        open: () => qmsOpenAuthenticatedQualityPath(attachment.download_url),
      });
    }
    for (const attachment of carAttachments) {
      const car = cars.find((row) => row.id === attachment.car_id);
      items.push({
        key: `CAR_ATTACHMENT:${attachment.id}`,
        entityType: "CAR_ATTACHMENT",
        entityId: attachment.id,
        title: attachment.filename,
        source: car?.car_number ? `CAR ${car.car_number}` : "CAR evidence",
        meta: `${bytesLabel(attachment.size_bytes)} · ${dateTimeLabel(attachment.uploaded_at)}`,
        open: () => qmsOpenAuthenticatedQualityPath(attachment.download_url),
      });
    }
    return items;
  }, [carAttachments, cars, findingAttachments, findings, warRoomQuery.data?.checklist.current]);

  if (resolveQuery.isLoading || (auditId && warRoomQuery.isLoading)) {
    return (
      <AuditPageShell amoCode={amoCode} department={department} title="Audit workspace" subtitle="Loading controlled audit state" breadcrumbs={[]} suppressHeader>
        <div className="qa2-loading"><RefreshCcw className="is-spinning" size={24} /> Loading authoritative audit workspace…</div>
      </AuditPageShell>
    );
  }

  if (!audit || warRoomQuery.isError || !warRoomQuery.data) {
    return (
      <AuditPageShell amoCode={amoCode} department={department} title="Audit unavailable" subtitle="Authoritative workflow could not be loaded" breadcrumbs={[]} suppressHeader>
        <section className="qa2-integrity-error">
          <ShieldAlert size={30} />
          <div>
            <h2>Audit workspace is in safe read-only mode</h2>
            <p>{warRoomQuery.error instanceof Error ? warRoomQuery.error.message : "The audit could not be resolved or the lifecycle service is unavailable."}</p>
            <p>The portal will not invent completion values or permit workflow advancement.</p>
          </div>
          <button type="button" onClick={() => { void resolveQuery.refetch(); void warRoomQuery.refetch(); }}><RefreshCcw size={16} /> Retry</button>
        </section>
      </AuditPageShell>
    );
  }

  const checklistMetadata = warRoomQuery.data.checklist;
  const reportMetadata = warRoomQuery.data.report;
  const currentChecklist = checklistMetadata.current;
  const currentChecklistIsPdf = Boolean(currentChecklist && (currentChecklist.content_type.includes("pdf") || currentChecklist.filename.toLowerCase().endsWith(".pdf")));
  const reportStage = currentStage(warRoomQuery.data, "report");
  const closeoutStage = currentStage(warRoomQuery.data, "closeout");
  const findingsReadOnly = reportMetadata.issued !== null || audit.status === "CLOSED";

  const beginEditFinding = (finding: QMSFindingOut) => {
    setEditingFindingId(finding.id);
    setFindingEdit({
      level: (FINDING_LEVELS.some((item) => item.value === finding.level) ? finding.level : "LEVEL_3") as FindingLevel,
      requirement_ref: finding.requirement_ref || "",
      description: finding.description,
      objective_evidence: finding.objective_evidence || "",
      target_close_date: finding.target_close_date || "",
      safety_sensitive: finding.safety_sensitive,
    });
  };

  const renderWarRoom = () => {
    const previous = warRoomQuery.data.previous_audits[0] || null;
    return (
      <div className="qa2-war-room">
        <section className="qa2-command-strip">
          <div><span>Lifecycle</span><strong>{warRoomQuery.data.workflow.lifecycle_status.replaceAll("_", " ")}</strong></div>
          <div><span>Starts</span><strong>{dateLabel(audit.planned_start)}</strong></div>
          <div><span>Notice</span><strong>{warRoomQuery.data.notice_history.length ? "History available" : "Pending"}</strong></div>
          <div><span>Checklist</span><strong>{workflow?.checklist_complete ? "Complete" : workflow?.checklist_uploaded ? "Ready" : "Missing"}</strong></div>
          <div><span>Previous audit</span><strong>{previous ? "Available" : "None found"}</strong></div>
          {activeStage?.primary_action ? (
            <button type="button" className="qa2-primary-button" disabled={!activeStage.primary_action.enabled || !canManageAudit || startAuditMutation.isPending} onClick={() => runStageAction(activeStage)}>
              {startAuditMutation.isPending ? "Starting…" : activeStage.primary_action.label} <ArrowRight size={16} />
            </button>
          ) : <span className="qa2-command-complete"><CheckCircle2 size={17} /> Opening brief recorded</span>}
        </section>

        <div className="qa2-grid qa2-grid--war-room">
          <section className="qa2-panel qa2-panel--span-7">
            <header className="qa2-panel__header">
              <div><span>Audit brief</span><h3>What the team is auditing</h3></div>
              <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedule`)}><CalendarClock size={15} /> Open planner</button>
            </header>
            <dl className="qa2-brief-grid">
              <div><dt>Objective / title</dt><dd>{audit.title}</dd></div>
              <div><dt>Scope code</dt><dd>{audit.audit_scope_code || "Not assigned"}</dd></div>
              <div className="is-wide"><dt>Scope</dt><dd>{audit.scope || "Scope has not been written."}</dd></div>
              <div className="is-wide"><dt>Criteria</dt><dd>{audit.criteria || "Criteria and references have not been written."}</dd></div>
              <div><dt>Auditee</dt><dd>{audit.auditee_user_name || audit.auditee || audit.auditee_email || "Not assigned"}</dd></div>
              <div><dt>Audit type</dt><dd>{audit.kind.replaceAll("_", " ")}</dd></div>
              <div><dt>Planned dates</dt><dd>{dateLabel(audit.planned_start)} — {dateLabel(audit.planned_end)}</dd></div>
              <div><dt>Actual dates</dt><dd>{audit.actual_start ? `${dateLabel(audit.actual_start)} — ${audit.actual_end ? dateLabel(audit.actual_end) : "In progress"}` : "Not started"}</dd></div>
            </dl>
            {warRoomQuery.data.readiness.blockers.length ? (
              <div className="qa2-callout is-danger"><ShieldAlert size={18} /><div><strong>War room blockers</strong>{warRoomQuery.data.readiness.blockers.map((item) => <p key={item}>{item}</p>)}</div></div>
            ) : (
              <div className="qa2-callout is-success"><BadgeCheck size={18} /><div><strong>War room ready</strong><p>Required planning fields are present. Confirm the previous audit and communication record before starting.</p></div></div>
            )}
          </section>

          <section className="qa2-panel qa2-panel--span-5">
            <header className="qa2-panel__header">
              <div><span>Previous audit intelligence</span><h3>{previous ? previous.audit_ref : "No comparable audit"}</h3></div>
              {previous ? <em>{previous.match_reason}</em> : null}
            </header>
            {previous ? (
              <>
                <div className="qa2-previous-audit">
                  <strong>{previous.title}</strong>
                  <p>Closed / completed: {dateLabel(previous.actual_end)}</p>
                  <p>Lead auditor: {previous.lead_auditor_name || "Not recorded"}</p>
                  <div className="qa2-inline-kpis">
                    <div><strong>{previous.findings_total}</strong><span>Findings</span></div>
                    <div className={previous.open_carryovers ? "is-warning" : ""}><strong>{previous.open_carryovers}</strong><span>Carryovers</span></div>
                    <div className={previous.possible_repeat_findings ? "is-warning" : ""}><strong>{previous.possible_repeat_findings}</strong><span>Possible repeats</span></div>
                  </div>
                </div>
                <div className="qa2-button-row">
                  {previous.report.download_url ? <button type="button" className="qa2-primary-button" onClick={() => void qmsOpenAuthenticatedQualityPath(previous.report.download_url!)}><FileSearch size={15} /> View previous report</button> : null}
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/${referenceSlug(previous.audit_ref)}?tab=findings`)}><ExternalLink size={15} /> Compare findings</button>
                </div>
              </>
            ) : (
              <div className="qa2-empty"><History size={24} /><strong>No comparable issued audit report was found</strong><p>The lookup uses the same tenant, scope, auditee and most recent completed audits.</p></div>
            )}
          </section>

          <section className="qa2-panel qa2-panel--span-7">
            <header className="qa2-panel__header"><div><span>Auditor action queue</span><h3>Required preparation</h3></div></header>
            <div className="qa2-action-list">
              {warRoomQuery.data.action_queue.map((item) => (
                <article key={item.id} className={`qa2-action-row is-${item.state.toLowerCase()}`}>
                  <span>{actionStateIcon(item.state)}</span>
                  <div><strong>{item.label}</strong><p>{item.helper || "No additional instruction."}</p></div>
                  <small>{item.owner_label || "Audit team"}</small>
                  {item.action_path ? <button type="button" onClick={() => item.action_path!.startsWith("/quality/") ? void qmsOpenAuthenticatedQualityPath(item.action_path!) : setTab(item.action_path!.includes("checklist") ? "checklist" : "war-room")}><ChevronRight size={15} /></button> : null}
                </article>
              ))}
            </div>
          </section>

          <section className="qa2-panel qa2-panel--span-5">
            <header className="qa2-panel__header"><div><span>Team and communications</span><h3>Who is involved</h3></div><button type="button" disabled={!canManageAudit || noticeMutation.isPending} onClick={() => noticeMutation.mutate()}><MailCheck size={15} /> {noticeMutation.isPending ? "Sending…" : "Send notice"}</button></header>
            <div className="qa2-team-list">
              <div><span>Lead auditor</span><strong>{audit.lead_auditor_name || audit.lead_auditor_user_id || "Unassigned"}</strong></div>
              <div><span>Observer</span><strong>{audit.observer_auditor_name || audit.observer_auditor_user_id || "Not assigned"}</strong></div>
              <div><span>Assistant</span><strong>{audit.assistant_auditor_name || audit.assistant_auditor_user_id || "Not assigned"}</strong></div>
              <div><span>Auditee</span><strong>{audit.auditee_user_name || audit.auditee || audit.auditee_email || "Unassigned"}</strong></div>
            </div>
            <div className="qa2-timeline">
              {warRoomQuery.data.notice_history.length ? warRoomQuery.data.notice_history.slice(0, 8).map((event) => (
                <article key={event.id}><span /><div><strong>{event.label}</strong><p>{event.actor_name || "System"} · {dateTimeLabel(event.occurred_at)}</p>{event.detail ? <small>{event.detail}</small> : null}</div></article>
              )) : <div className="qa2-empty is-compact"><MessageSquare size={20} /><strong>No communication events recorded</strong></div>}
            </div>
          </section>

          {warRoomQuery.data.carryover_findings.length ? (
            <section className="qa2-panel qa2-panel--span-12">
              <header className="qa2-panel__header"><div><span>Carryover exposure</span><h3>Open items from the latest comparable audit</h3></div></header>
              <div className="qa2-table-scroll"><table className="qa2-table"><thead><tr><th>Finding</th><th>Level</th><th>Requirement</th><th>Description</th><th>CAR</th><th>Target</th></tr></thead><tbody>{warRoomQuery.data.carryover_findings.map((item) => <tr key={item.finding_id} className={item.overdue ? "is-overdue" : ""}><td>{item.finding_ref || "Finding"}</td><td>{findingLevelLabel(item.level)}</td><td>{item.requirement_ref || "—"}</td><td>{item.description}</td><td>{item.car_number || "Not linked"} {item.car_status ? `· ${item.car_status}` : ""}</td><td>{dateLabel(item.target_close_date)}</td></tr>)}</tbody></table></div>
            </section>
          ) : null}
        </div>
      </div>
    );
  };

  const renderChecklist = () => (
    <div className="qa2-checklist">
      <section className="qa2-panel qa2-document-command">
        <header className="qa2-panel__header">
          <div><span>Controlled checklist</span><h3>{currentChecklist?.filename || "No controlled source"}</h3></div>
          <div className="qa2-document-statuses">
            <em>{currentChecklist ? `Version ${currentChecklist.version_number}` : "No version"}</em>
            <em>{currentChecklist?.fillable === "YES" ? `${currentChecklist.field_count ?? 0} PDF fields` : "Fillability not confirmed"}</em>
            <em>{checklistMetadata.portal_item_count} portal notes</em>
            <em className={checklistMetadata.explicitly_completed ? "is-complete" : ""}>{checklistMetadata.explicitly_completed ? "Checklist complete" : "Checklist not completed"}</em>
          </div>
        </header>
        {checklistMetadata.read_only_reason ? <div className="qa2-callout is-warning"><Lock size={18} /><div><strong>Checklist locked</strong><p>{checklistMetadata.read_only_reason}</p></div></div> : null}
        <div className="qa2-document-toolbar">
          {currentChecklist ? <>
            <button type="button" onClick={() => void qmsOpenLifecycleDocument(currentChecklist)}><ExternalLink size={15} /> Open</button>
            {currentChecklistIsPdf ? <button type="button" className="qa2-primary-button" onClick={() => setPdfEditorOpen(true)}><FilePenLine size={15} /> {checklistMetadata.read_only ? "Review PDF form" : "Fill PDF form"}</button> : null}
            <button type="button" onClick={() => void qmsDownloadLifecycleDocumentFile(currentChecklist)}><Download size={15} /> Download</button>
          </> : null}
          <label className={`qa2-upload-button${checklistMetadata.read_only || !canManageAudit ? " is-disabled" : ""}`}>
            <UploadCloud size={15} /> {currentChecklist ? "Upload new source" : "Upload controlled source"}
            <input type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={checklistMetadata.read_only || !canManageAudit || sourceUploadMutation.isPending} onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) sourceUploadMutation.mutate(file);
              event.currentTarget.value = "";
            }} />
          </label>
          <button type="button" className="qa2-primary-button" disabled={!canManageAudit || checklistMetadata.read_only || checklistMetadata.explicitly_completed || completeChecklistMutation.isPending} onClick={() => completeChecklistMutation.mutate()}><ClipboardCheck size={15} /> {completeChecklistMutation.isPending ? "Completing…" : "Mark checklist complete"}</button>
        </div>
      </section>

      <div className="qa2-grid">
        <section className="qa2-panel qa2-panel--span-8">
          <header className="qa2-panel__header"><div><span>Portal audit notes</span><h3>Structured checklist responses</h3></div><em>{checklistMetadata.portal_completed_count}/{checklistMetadata.portal_item_count} answered</em></header>
          {!checklistMetadata.read_only && canManageAudit ? (
            <div className="qa2-checklist-add">
              <input value={checklistDraft.section} onChange={(event) => setChecklistDraft((current) => ({ ...current, section: event.target.value }))} placeholder="Section" />
              <input value={checklistDraft.requirement_ref} onChange={(event) => setChecklistDraft((current) => ({ ...current, requirement_ref: event.target.value }))} placeholder="Requirement / reference" />
              <textarea value={checklistDraft.prompt} onChange={(event) => setChecklistDraft((current) => ({ ...current, prompt: event.target.value }))} placeholder="Checklist question or audit prompt" />
              <textarea value={checklistDraft.objective_evidence} onChange={(event) => setChecklistDraft((current) => ({ ...current, objective_evidence: event.target.value }))} placeholder="Initial evidence note" />
              <button type="button" className="qa2-primary-button" disabled={!checklistDraft.prompt.trim() || createChecklistItemMutation.isPending} onClick={() => createChecklistItemMutation.mutate()}><Plus size={15} /> Add row</button>
            </div>
          ) : null}
          <div className="qa2-checklist-rows">
            {checklistItems.length ? checklistItems.map((item) => (
              <article key={item.id} className="qa2-checklist-row">
                <div className="qa2-checklist-row__identity"><small>{item.section || "General"}</small><strong>{item.requirement_ref || item.checklist_ref || "No requirement reference"}</strong></div>
                <label><span>Question / prompt</span><textarea defaultValue={item.prompt} disabled={checklistMetadata.read_only || !canManageAudit} onBlur={(event) => {
                  if (event.currentTarget.value.trim() !== item.prompt.trim()) updateChecklistItemMutation.mutate({ itemId: item.id, patch: { prompt: event.currentTarget.value.trim() } });
                }} /></label>
                <label><span>Objective evidence / response</span><textarea defaultValue={item.objective_evidence || ""} disabled={checklistMetadata.read_only || !canManageAudit} onBlur={(event) => {
                  if (event.currentTarget.value.trim() !== (item.objective_evidence || "").trim()) updateChecklistItemMutation.mutate({ itemId: item.id, patch: { objective_evidence: event.currentTarget.value.trim() || null } });
                }} /></label>
                <label className="qa2-status-control"><span>Status</span><select value={item.response_status} disabled={checklistMetadata.read_only || !canManageAudit} onChange={(event) => updateChecklistItemMutation.mutate({ itemId: item.id, patch: { response_status: event.target.value } })}><option value="PENDING">Pending</option><option value="COMPLIANT">Compliant</option><option value="NON_CONFORMING">Non-conforming</option><option value="OBSERVATION">Observation</option><option value="NOT_APPLICABLE">Not applicable</option></select></label>
              </article>
            )) : <div className="qa2-empty"><ClipboardList size={24} /><strong>No portal checklist rows</strong><p>Use PDF form fields as the primary response surface, or add structured notes when the source is not fillable.</p></div>}
          </div>
        </section>

        <section className="qa2-panel qa2-panel--span-4">
          <header className="qa2-panel__header"><div><span>Version history</span><h3>Retained checklist records</h3></div><History size={18} /></header>
          <div className="qa2-version-list">
            {checklistMetadata.versions.map((version) => (
              <article key={version.id} className={version.id === currentChecklist?.id ? "is-current" : ""}>
                <div><strong>Version {version.version_number}</strong><span>{version.lifecycle_status.replaceAll("_", " ")}</span></div>
                <p>{version.filename}</p>
                <small>{bytesLabel(version.size_bytes)} · {dateTimeLabel(version.created_at)}</small>
                <div className="qa2-button-row"><button type="button" onClick={() => void qmsOpenLifecycleDocument(version)}><ExternalLink size={14} /> Open</button><button type="button" onClick={() => void qmsDownloadLifecycleDocumentFile(version)}><Download size={14} /></button></div>
              </article>
            ))}
            {!checklistMetadata.versions.length ? <div className="qa2-empty is-compact"><FileClock size={20} /><strong>No retained checklist version</strong></div> : null}
          </div>
        </section>
      </div>
    </div>
  );

  const renderFindings = () => (
    <div className="qa2-findings">
      {findingsReadOnly ? <div className="qa2-callout is-warning"><Lock size={18} /><div><strong>Findings are read-only</strong><p>The controlled report has been issued or the audit is closed. Existing findings remain visible and retained.</p></div></div> : null}
      {!findingsReadOnly && canManageAudit ? (
        <section className="qa2-panel">
          <header className="qa2-panel__header"><div><span>Record fieldwork result</span><h3>{buildFindingReference(audit.audit_ref, findings)}</h3></div></header>
          <div className="qa2-finding-form">
            <label><span>Classification</span><select value={findingForm.level} onChange={(event) => setFindingForm((current) => ({ ...current, level: event.target.value as FindingLevel }))}>{FINDING_LEVELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label><span>Requirement / reference</span><input value={findingForm.requirement_ref} onChange={(event) => setFindingForm((current) => ({ ...current, requirement_ref: event.target.value }))} placeholder="MPM clause, regulation or checklist reference" /></label>
            <label><span>Target close date</span><input type="date" value={findingForm.target_close_date} disabled={findingForm.level === "LEVEL_4"} onChange={(event) => setFindingForm((current) => ({ ...current, target_close_date: event.target.value }))} /></label>
            <label className="is-wide"><span>Finding / observation statement</span><textarea value={findingForm.description} onChange={(event) => setFindingForm((current) => ({ ...current, description: event.target.value }))} placeholder="State the objective condition, requirement and gap without opinion." /></label>
            <label className="is-wide"><span>Objective evidence</span><textarea value={findingForm.objective_evidence} onChange={(event) => setFindingForm((current) => ({ ...current, objective_evidence: event.target.value }))} placeholder="Records checked, samples, interviews, dates, aircraft/component references and photos." /></label>
            <label className="qa2-checkbox"><input type="checkbox" checked={findingForm.safety_sensitive} onChange={(event) => setFindingForm((current) => ({ ...current, safety_sensitive: event.target.checked }))} /><span>Safety sensitive</span></label>
            <label className="qa2-upload-button"><Paperclip size={15} /> Attach evidence<input ref={findingFileInputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt" onChange={(event) => setFindingFiles(Array.from(event.currentTarget.files || []))} /></label>
            <span>{findingFiles.length ? `${findingFiles.length} file(s) selected` : "Evidence files are recommended for every non-conformity."}</span>
            <button type="button" className="qa2-primary-button" disabled={!findingForm.description.trim() || createFindingMutation.isPending} onClick={() => createFindingMutation.mutate()}><Save size={15} /> {createFindingMutation.isPending ? "Saving…" : "Record finding"}</button>
          </div>
        </section>
      ) : null}

      <section className="qa2-panel">
        <header className="qa2-panel__header"><div><span>Findings register</span><h3>{findings.length} recorded · {workflow?.findings_open || 0} open</h3></div>{activeStage?.state === "IN_PROGRESS" ? <button type="button" className="qa2-primary-button" disabled={!canManageAudit || completeFieldworkMutation.isPending} onClick={() => completeFieldworkMutation.mutate()}><CheckCircle2 size={15} /> Complete fieldwork</button> : null}</header>
        <div className="qa2-finding-list">
          {findings.map((row) => {
            const finding = row.finding;
            const isEditing = editingFindingId === finding.id;
            const attachmentCount = findingAttachments.filter((attachment) => attachment.finding_id === finding.id).length;
            return (
              <article key={finding.id} className="qa2-finding-row">
                <header><div><strong>{finding.finding_ref || "Finding"}</strong><span>{findingLevelLabel(finding.level)}</span>{finding.safety_sensitive ? <em>Safety sensitive</em> : null}</div><small>{finding.closed_at ? `Closed ${dateTimeLabel(finding.closed_at)}` : `Target ${dateLabel(finding.target_close_date)}`}</small></header>
                {isEditing ? (
                  <div className="qa2-finding-edit">
                    <select value={findingEdit.level} onChange={(event) => setFindingEdit((current) => ({ ...current, level: event.target.value as FindingLevel }))}>{FINDING_LEVELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
                    <input value={findingEdit.requirement_ref} onChange={(event) => setFindingEdit((current) => ({ ...current, requirement_ref: event.target.value }))} placeholder="Requirement" />
                    <textarea value={findingEdit.description} onChange={(event) => setFindingEdit((current) => ({ ...current, description: event.target.value }))} />
                    <textarea value={findingEdit.objective_evidence} onChange={(event) => setFindingEdit((current) => ({ ...current, objective_evidence: event.target.value }))} />
                    <input type="date" value={findingEdit.target_close_date} disabled={findingEdit.level === "LEVEL_4"} onChange={(event) => setFindingEdit((current) => ({ ...current, target_close_date: event.target.value }))} />
                    <div className="qa2-button-row"><button type="button" className="qa2-primary-button" disabled={!findingEdit.description.trim() || updateFindingMutation.isPending} onClick={() => updateFindingMutation.mutate(finding)}><Save size={14} /> Save</button><button type="button" onClick={() => setEditingFindingId(null)}><X size={14} /> Cancel</button></div>
                  </div>
                ) : (
                  <>
                    <p>{finding.description}</p>
                    <div className="qa2-finding-facts"><span><strong>Requirement:</strong> {finding.requirement_ref || "Not stated"}</span><span><strong>Evidence:</strong> {finding.objective_evidence || "No narrative evidence"}</span><span><strong>Files:</strong> {attachmentCount}</span><span><strong>Linked CARs:</strong> {row.linked_cars.length}</span></div>
                    <div className="qa2-button-row">
                      {!findingsReadOnly && canManageAudit ? <button type="button" onClick={() => beginEditFinding(finding)}><FilePenLine size={14} /> Edit</button> : null}
                      {!findingsReadOnly && canManageAudit && finding.level !== "LEVEL_4" && row.linked_cars.length === 0 ? <button type="button" className="qa2-primary-button" disabled={issueCarMutation.isPending} onClick={() => issueCarMutation.mutate(row)}><FilePlus2 size={14} /> Issue CAR</button> : null}
                      {canManageAudit ? <button type="button" onClick={() => { const reason = window.prompt("Reason for Quality review"); if (reason?.trim()) flagFindingMutation.mutate({ findingId: finding.id, reason }); }}><Flag size={14} /> Flag review</button> : null}
                      {!findingsReadOnly && canManageAudit && row.linked_cars.length === 0 ? <button type="button" className="is-danger" onClick={() => { if (window.confirm("Delete this finding?")) deleteFindingMutation.mutate(finding.id); }}><Trash2 size={14} /> Delete</button> : null}
                    </div>
                  </>
                )}
              </article>
            );
          })}
          {!findings.length ? <div className="qa2-empty"><FileCheck2 size={24} /><strong>No findings recorded</strong><p>Zero findings is not completion. Complete fieldwork explicitly after all checklist exceptions are dispositioned.</p></div> : null}
        </div>
      </section>
    </div>
  );

  const renderCars = () => (
    <div className="qa2-cars-layout">
      <section className="qa2-panel qa2-car-list-panel">
        <header className="qa2-panel__header"><div><span>Issued CARs</span><h3>{cars.length} total · {workflow?.cars_open || 0} open</h3></div></header>
        <div className="qa2-car-list">
          {cars.map((car) => <button type="button" key={car.id} className={selectedCar?.id === car.id ? "is-active" : ""} onClick={() => setSelectedCarId(car.id)}><div><strong>{car.car_number}</strong><span>{car.status.replaceAll("_", " ")}</span></div><p>{car.title}</p><small>Due {dateLabel(car.due_date)}</small></button>)}
          {!cars.length ? <div className="qa2-empty is-compact"><FileCheck2 size={20} /><strong>No CARs issued</strong><p>CARs are required only for Level 1-3 non-conformities.</p></div> : null}
        </div>
      </section>

      <section className="qa2-panel qa2-car-detail-panel">
        {selectedCar ? (
          <>
            <header className="qa2-panel__header"><div><span>{selectedCar.car_number}</span><h3>{selectedCar.title}</h3></div><em>{selectedCar.priority} · {selectedCar.status.replaceAll("_", " ")}</em></header>
            <p className="qa2-car-summary">{selectedCar.summary}</p>
            <dl className="qa2-car-facts"><div><dt>Due date</dt><dd>{dateLabel(selectedCar.due_date)}</dd></div><div><dt>Root cause</dt><dd>{selectedCar.root_cause_status || "Pending"}</dd></div><div><dt>CAPA</dt><dd>{selectedCar.capa_status || "Pending"}</dd></div><div><dt>Evidence</dt><dd>{selectedCar.evidence_verified_at ? "Verified" : selectedCar.evidence_received_at ? "Received" : "Pending"}</dd></div></dl>
            <div className="qa2-response-grid"><div><span>Containment</span><p>{selectedCar.containment_action || "Not submitted"}</p></div><div><span>Root cause</span><p>{selectedCar.root_cause || selectedCar.root_cause_text || "Not submitted"}</p></div><div><span>Corrective action</span><p>{selectedCar.corrective_action || selectedCar.capa_text || "Not submitted"}</p></div><div><span>Preventive action</span><p>{selectedCar.preventive_action || "Not submitted"}</p></div></div>
            <div className="qa2-button-row">
              {selectedCar.invite_token ? <button type="button" onClick={() => window.open(`/car-invite?token=${encodeURIComponent(selectedCar.invite_token)}`, "_blank", "noopener,noreferrer")}><ExternalLink size={14} /> Open auditee workspace</button> : null}
              {selectedCar.status !== "CLOSED" && canManageAudit ? <>
                <button type="button" className="qa2-primary-button" onClick={() => carReviewMutation.mutate({ carId: selectedCar.id, decision: "accept" })}><ShieldCheck size={14} /> Accept response</button>
                <button type="button" onClick={() => { const note = window.prompt("Evidence required"); if (note?.trim()) carReviewMutation.mutate({ carId: selectedCar.id, decision: "evidence", note }); }}><Paperclip size={14} /> Needs evidence</button>
                <button type="button" className="is-danger" onClick={() => { const note = window.prompt("Rejection reason"); if (note?.trim()) carReviewMutation.mutate({ carId: selectedCar.id, decision: "reject", note }); }}><X size={14} /> Reject</button>
                <button type="button" disabled={!selectedCar.evidence_verified_at || selectedCar.capa_status !== "ACCEPTED"} onClick={() => closeCarMutation.mutate(selectedCar.id)}><CheckCircle2 size={14} /> Close CAR</button>
              </> : null}
            </div>
            <section className="qa2-car-chat">
              <header><div><MessageSquare size={16} /><strong>CAR collaboration</strong></div><small>{carActionsQuery.data?.length || 0} events</small></header>
              <div className="qa2-car-messages">{(carActionsQuery.data || []).slice().reverse().map((message: CARActionOut) => <article key={message.id} className={message.actor_user_id === currentUser?.id ? "is-own" : message.action_type === "COMMENT" ? "" : "is-system"}><strong>{message.actor_user_id === currentUser?.id ? "You" : message.actor_name || "System"}</strong><p>{message.message}</p><small>{dateTimeLabel(message.created_at)}</small></article>)}</div>
              {selectedCar.status !== "CLOSED" ? <div className="qa2-chat-compose"><textarea value={carMessage} onChange={(event) => setCarMessage(event.target.value)} placeholder="Write a concise CAR update" /><button type="button" className="qa2-primary-button" disabled={!carMessage.trim() || carMessageMutation.isPending} onClick={() => carMessageMutation.mutate()}><Send size={15} /> Send</button></div> : <div className="qa2-callout is-muted"><Lock size={16} /><span>This CAR is closed. Collaboration history is retained read-only.</span></div>}
            </section>
          </>
        ) : <div className="qa2-empty"><FileCheck2 size={24} /><strong>Select a CAR to review</strong></div>}
      </section>
    </div>
  );

  const renderEvidence = () => (
    <div className="qa2-evidence">
      <section className="qa2-panel">
        <header className="qa2-panel__header"><div><span>Evidence inventory</span><h3>{evidenceItems.length} controlled item(s)</h3></div><button type="button" onClick={() => exportPackMutation.mutate()} disabled={exportPackMutation.isPending}><PackageCheck size={15} /> {exportPackMutation.isPending ? "Packaging…" : "Export evidence pack"}</button></header>
        <div className="qa2-inline-kpis qa2-inline-kpis--evidence"><div><strong>{workflow?.evidence_total || 0}</strong><span>Total evidence</span></div><div className={workflow?.evidence_pending ? "is-warning" : ""}><strong>{workflow?.evidence_pending || 0}</strong><span>Pending / rejected</span></div><div><strong>{findingAttachments.length}</strong><span>Finding files</span></div><div><strong>{carAttachments.length}</strong><span>CAR files</span></div></div>
        <div className="qa2-evidence-list">
          {evidenceItems.map((item) => {
            const review = reviewMap.get(item.key);
            const status = review?.status || "PENDING";
            return <article key={item.key} className={`is-${status.toLowerCase()}`}><div className="qa2-evidence-icon"><Paperclip size={17} /></div><div><strong>{item.title}</strong><span>{item.source}</span><small>{item.meta}</small>{review?.note ? <p>{review.note}</p> : null}</div><em>{status}</em><div className="qa2-button-row"><button type="button" onClick={() => void item.open()}><ExternalLink size={14} /> Open</button>{canManageAudit && audit.status !== "CLOSED" ? <><button type="button" className="is-success" disabled={evidenceReviewMutation.isPending} onClick={() => evidenceReviewMutation.mutate({ item, status: "ACCEPTED" })}><Check size={14} /> Accept</button><button type="button" className="is-danger" disabled={evidenceReviewMutation.isPending} onClick={() => evidenceReviewMutation.mutate({ item, status: "REJECTED" })}><X size={14} /> Reject</button></> : null}</div></article>;
          })}
          {!evidenceItems.length ? <div className="qa2-empty"><FolderArchive size={24} /><strong>No controlled evidence is available</strong><p>Checklist and supporting evidence must exist and be explicitly reviewed before the report can be issued.</p></div> : null}
        </div>
      </section>
    </div>
  );

  const renderReport = () => {
    const draft = reportMetadata.current_draft;
    const issued = reportMetadata.issued;
    return (
      <div className="qa2-report">
        <div className="qa2-grid">
          <section className="qa2-panel qa2-panel--span-7">
            <header className="qa2-panel__header"><div><span>Controlled report</span><h3>{issued ? "Issued report" : draft ? "Draft awaiting issue" : "No report draft"}</h3></div><em>{reportStage ? stageStateLabel(reportStage) : "Unknown"}</em></header>
            {reportMetadata.read_only_reason ? <div className="qa2-callout is-warning"><Lock size={18} /><div><strong>Report control</strong><p>{reportMetadata.read_only_reason}</p></div></div> : null}
            {(issued || draft) ? <article className="qa2-current-report"><FileText size={28} /><div><strong>{(issued || draft)!.filename}</strong><span>Version {(issued || draft)!.version_number} · {(issued || draft)!.lifecycle_status}</span><small>{bytesLabel((issued || draft)!.size_bytes)} · SHA-256 {(issued || draft)!.sha256.slice(0, 16)}…</small>{issued ? <p>Issued {dateTimeLabel(issued.issued_at)} · {issued.issue_label} · Distribution {issued.distribution_status?.replaceAll("_", " ")}</p> : <p>Uploaded {dateTimeLabel(draft!.created_at)}. Upload does not equal issue.</p>}</div><div className="qa2-button-row"><button type="button" onClick={() => void qmsOpenLifecycleDocument((issued || draft)!)}><ExternalLink size={14} /> Open</button><button type="button" onClick={() => void qmsDownloadLifecycleDocumentFile((issued || draft)!)}><Download size={14} /></button></div></article> : <div className="qa2-empty"><FilePlus2 size={24} /><strong>No report draft uploaded</strong><p>The report stage becomes ready only after required CAR issuance and evidence verification.</p></div>}
            {!issued && canManageAudit ? <div className="qa2-report-actions"><label className="qa2-upload-button"><UploadCloud size={15} /> Upload PDF draft<input type="file" accept="application/pdf,.pdf" disabled={reportDraftMutation.isPending || audit.status === "CLOSED"} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) reportDraftMutation.mutate(file); event.currentTarget.value = ""; }} /></label>{draft ? <><label><span>Issue / revision label</span><input value={reportIssueLabel} onChange={(event) => setReportIssueLabel(event.target.value)} /></label><button type="button" className="qa2-primary-button" disabled={!reportIssueLabel.trim() || reportIssueMutation.isPending || reportStage?.state === "NOT_READY" || reportStage?.state === "BLOCKED"} onClick={() => reportIssueMutation.mutate(draft)}><FileCheck2 size={15} /> {reportIssueMutation.isPending ? "Issuing…" : "Issue controlled report"}</button></> : null}</div> : null}
            {reportStage?.blockers.length ? <div className="qa2-callout is-danger"><ShieldAlert size={18} /><div><strong>Report blockers</strong>{reportStage.blockers.map((blocker) => <p key={blocker}>{blocker}</p>)}</div></div> : null}
          </section>

          <section className="qa2-panel qa2-panel--span-5">
            <header className="qa2-panel__header"><div><span>Distribution</span><h3>Issued-report recipients</h3></div><MailCheck size={18} /></header>
            <div className="qa2-recipient-groups">{REPORT_RECIPIENT_GROUPS.map(([value, label]) => <label key={value}><input type="checkbox" checked={reportShareGroups.includes(value)} disabled={!issued || audit.status === "CLOSED"} onChange={(event) => setReportShareGroups((current) => event.target.checked ? [...current, value] : current.filter((item) => item !== value))} /><span>{label}</span></label>)}</div>
            <button type="button" className="qa2-primary-button" disabled={!issued || !reportShareGroups.length || reportShareMutation.isPending} onClick={() => issued && reportShareMutation.mutate(issued)}><Send size={15} /> {reportShareMutation.isPending ? "Distributing…" : "Distribute issued report"}</button>
            <p className="qa2-muted">Distribution is recorded against the exact issued version. CAR action access remains separate from report read access.</p>
          </section>

          <section className="qa2-panel qa2-panel--span-12">
            <header className="qa2-panel__header"><div><span>Report version history</span><h3>Draft, issued and retained records</h3></div></header>
            <div className="qa2-version-table">{reportMetadata.versions.map((version) => <article key={version.id}><div><strong>Version {version.version_number}</strong><span>{version.lifecycle_status}</span></div><p>{version.filename}</p><small>{version.issue_label || "No issue label"} · {dateTimeLabel(version.issued_at || version.created_at)}</small><button type="button" onClick={() => void qmsOpenLifecycleDocument(version)}><ExternalLink size={14} /> Open</button></article>)}</div>
          </section>
        </div>
      </div>
    );
  };

  const renderCloseout = () => (
    <div className="qa2-closeout">
      <section className="qa2-panel">
        <header className="qa2-panel__header"><div><span>Closure decision</span><h3>{audit.status === "CLOSED" ? "Audit formally closed" : closeoutStage ? stageStateLabel(closeoutStage) : "Closure unavailable"}</h3></div>{audit.status === "CLOSED" ? <BadgeCheck size={22} /> : <Lock size={20} />}</header>
        <div className="qa2-closeout-matrix">{workflow!.stages.map((stage) => <article key={stage.id} className={`is-${stage.state.toLowerCase()}`}><span>{stage.complete ? <CheckCircle2 size={18} /> : stage.state === "BLOCKED" ? <ShieldAlert size={18} /> : <CircleDashed size={18} />}</span><div><strong>{stage.label}</strong><p>{stage.metric || stage.helper}</p></div><em>{stageStateLabel(stage)}</em></article>)}</div>
        {closeoutStage?.blockers.length ? <div className="qa2-callout is-danger"><ShieldAlert size={18} /><div><strong>Closeout blockers</strong>{closeoutStage.blockers.map((blocker) => <p key={blocker}>{blocker}</p>)}</div></div> : null}
        {audit.status !== "CLOSED" ? <div className="qa2-closeout-actions"><button type="button" onClick={() => exportPackMutation.mutate()} disabled={exportPackMutation.isPending}><PackageCheck size={15} /> Package evidence</button><button type="button" className="qa2-primary-button" disabled={!canManageAudit || closeoutStage?.state !== "READY" || closeoutMutation.isPending} onClick={() => closeoutMutation.mutate()}><ShieldCheck size={15} /> {closeoutMutation.isPending ? "Closing…" : "Approve and close audit"}</button></div> : <div className="qa2-callout is-success"><FolderArchive size={18} /><div><strong>Retained audit record</strong><p>All stages are locked. Use the evidence pack and version histories for future surveillance and repeat-finding review.</p></div></div>}
      </section>
    </div>
  );

  const renderActiveTab = () => {
    switch (activeTab) {
      case "war-room": return renderWarRoom();
      case "checklist": return renderChecklist();
      case "findings": return renderFindings();
      case "cars": return renderCars();
      case "evidence": return renderEvidence();
      case "report": return renderReport();
      case "closeout": return renderCloseout();
      default: return null;
    }
  };

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={audit.title}
      subtitle="Authoritative audit lifecycle"
      breadcrumbs={[
        { label: "Quality", onClick: () => navigate(`/maintenance/${amoCode}/quality`) },
        { label: "Audits", onClick: () => navigate(`/maintenance/${amoCode}/quality/audits`) },
        { label: audit.audit_ref },
      ]}
      suppressHeader
    >
      <div className="qa2-workbench">
        <aside className="qa2-context-rail">
          <div className="qa2-context-identity"><span>Audit control room</span><h2>{audit.title}</h2><p>{audit.audit_ref}</p></div>
          <dl>
            <div><dt>Status</dt><dd>{workflow!.lifecycle_status.replaceAll("_", " ")}</dd></div>
            <div><dt>Planned</dt><dd>{dateLabel(audit.planned_start)} — {dateLabel(audit.planned_end)}</dd></div>
            <div><dt>Actual</dt><dd>{audit.actual_start ? `${dateLabel(audit.actual_start)} — ${audit.actual_end ? dateLabel(audit.actual_end) : "In progress"}` : "Not started"}</dd></div>
            <div><dt>Auditee</dt><dd>{audit.auditee_user_name || audit.auditee || audit.auditee_email || "Unassigned"}</dd></div>
            <div><dt>Lead auditor</dt><dd>{audit.lead_auditor_name || audit.lead_auditor_user_id || "Unassigned"}</dd></div>
            <div><dt>Scope code</dt><dd>{audit.audit_scope_code || "Not assigned"}</dd></div>
            <div><dt>Type</dt><dd>{audit.kind.replaceAll("_", " ")}</dd></div>
          </dl>
          <div className="qa2-team-stack"><span>{(audit.lead_auditor_name || "L").slice(0, 1)}</span><span>{(audit.observer_auditor_name || "O").slice(0, 1)}</span><span>{(audit.assistant_auditor_name || "A").slice(0, 1)}</span><p>{assignedUserIds.length} assigned auditor{assignedUserIds.length === 1 ? "" : "s"}</p></div>
          <button type="button" className="qa2-rail-link" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/register`)}><BookOpenCheck size={15} /> Open audit register</button>
        </aside>

        <main className="qa2-main">
          <nav className="qa2-stepper" aria-label="Audit lifecycle">
            {workflow!.stages.map((stage, index) => (
              <button type="button" key={stage.id} className={`is-${stage.state.toLowerCase()}${activeTab === stage.id ? " is-active" : ""}`} onClick={() => setTab(stage.id)} title={[stage.helper, ...stage.blockers].filter(Boolean).join(" ")}>
                <span>{stage.complete ? <Check size={14} /> : index + 1}</span>
                <div><strong>{stage.label}</strong><small>{stageStateLabel(stage)}</small></div>
              </button>
            ))}
          </nav>

          <header className="qa2-stage-header">
            <div><span>Step {TABS.indexOf(activeTab) + 1} of {TABS.length} · {TAB_LABELS[activeTab]}</span><h1>{TAB_TITLES[activeTab]}</h1><p>{activeStage?.helper || "Controlled audit stage"}</p></div>
            <div className="qa2-stage-header__metric"><small>Stage state</small><strong>{activeStage ? stageStateLabel(activeStage) : "Unavailable"}</strong><span>{activeStage?.metric}</span></div>
            {activeStage?.primary_action ? <button type="button" className="qa2-primary-button" disabled={!canManageAudit || !activeStage.primary_action.enabled} onClick={() => runStageAction(activeStage)}>{activeStage.primary_action.label}<ArrowRight size={15} /></button> : null}
          </header>

          {actionError ? <div className="qa2-page-message is-error"><AlertTriangle size={18} /><span>{actionError}</span><button type="button" onClick={() => setActionError(null)}><X size={15} /></button></div> : null}
          {actionNotice ? <div className="qa2-page-message is-success"><CheckCircle2 size={18} /><span>{actionNotice}</span><button type="button" onClick={() => setActionNotice(null)}><X size={15} /></button></div> : null}

          <div className="qa2-stage-content">{renderActiveTab()}</div>
        </main>
      </div>

      {currentChecklist && currentChecklistIsPdf ? (
        <QualityChecklistPdfEditor
          auditId={audit.id}
          auditReference={audit.audit_ref}
          auditTitle={audit.title}
          documentRecord={currentChecklist}
          open={pdfEditorOpen}
          readOnly={checklistMetadata.read_only || !canManageAudit}
          readOnlyReason={checklistMetadata.read_only_reason}
          onClose={() => setPdfEditorOpen(false)}
          onSaved={async (_record, committed) => {
            setActionNotice(committed ? "Filled checklist committed as a retained controlled version." : "Filled checklist working draft saved; source version retained.");
            await refreshAudit();
          }}
        />
      ) : null}
    </AuditPageShell>
  );
};

export default QualityAuditRunHubPage;
