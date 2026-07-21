import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Bold,
  Building2,
  CalendarClock,
  Check,
  CheckCircle2,
  CheckCheck,
  CircleDashed,
  ClipboardList,
  Download,
  Eye,
  FileText,
  FolderKanban,
  HelpCircle,
  Italic,
  List,
  ListOrdered,
  Lock,
  MessageSquare,
  Send,
  Share2,
  ChevronLeft,
  ChevronRight,
  MailCheck,
  PackageCheck,
  PanelRightOpen,
  Paperclip,
  Plus,
  Save,
  ShieldAlert,
  TimerReset,
  Trash2,
  UploadCloud,
  X,
  Users,
} from "lucide-react";
import AuditPageShell from "../components/QMS/AuditPageShell";
import "./qualityAudits/quality-audit-dashboard.css";
import { getCachedUser, getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import {
  downloadAuditEvidencePack,
  qmsCloseAudit,
  qmsGetAuditRegister,
  qmsGetAuditWorkflow,
  qmsIssueAuditNotice,
  qmsResolveAudit,
  qmsListAuditPersonnelOptions,
  qmsListCars,
  qmsResolveAuditeeBrand,
  type QMSAuditeeBrandOut,
  type QMSPersonOption,
  type QualityChecklistItemOut,
  qmsListCarAttachmentsBulk,
  qmsListAuditChecklistItems,
  qmsCreateAuditChecklistItem,
  qmsUpdateAuditChecklistItem,
  qmsCreateFinding,
  qmsUpdateFinding,
  qmsDeleteFinding,
  qmsFlagFindingForReview,
  qmsCreateCar,
  qmsReviewCarResponse,
  qmsListCarResponses,
  qmsListCarExtensionRequests,
  qmsForwardCarExtensionRequest,
  qmsListAuditFindingAttachments,
  qmsUploadFindingAttachment,
  qmsUploadAuditChecklist,
  qmsUploadAuditReport,
  qmsDownloadAuditChecklist,
  qmsDownloadAuditReport,
} from "../services/qms";
import {
  qmsAddCarAction,
  qmsListCarActions,
  qmsRequestCarAccess,
  qmsShareAuditReport,
  type CARActionOut,
} from "../services/qmsAuditHubActions";
import { saveDownloadedFile } from "../utils/downloads";
import { buildAuditWorkspacePath, isUuidLike, toAuditReferenceSlug } from "../utils/auditSlug";

const TABS = ["war-room", "checklist", "findings", "report", "cars", "evidence", "closeout"] as const;
type WorkspaceTab = typeof TABS[number];

const tabLabels: Record<WorkspaceTab, string> = {
  "war-room": "War room",
  checklist: "Checklist",
  findings: "Findings",
  cars: "CARs",
  evidence: "Evidence",
  report: "Report",
  closeout: "Closeout",
};

const tabMeta: Record<WorkspaceTab, { title: string; summary: string }> = {
  "war-room": {
    title: "Live coordination hub",
    summary: "Coordinate the team, notices, and readiness from a single command surface.",
  },
  checklist: {
    title: "Checklist control",
    summary: "Prepare the audit pack and keep the working checklist aligned to the approved plan.",
  },
  findings: {
    title: "Fieldwork findings",
    summary: "Capture observations, classify non-conformities, and convert them into actionable follow-ups.",
  },
  cars: {
    title: "Corrective action requests",
    summary: "Track open CARs, monitor response quality, and move actions toward verified closure.",
  },
  evidence: {
    title: "Evidence library",
    summary: "Consolidate supporting records, uploaded files, and linked CAR evidence for this audit.",
  },
  report: {
    title: "Audit report",
    summary: "Upload the issued report and keep the formal closure package complete and accessible.",
  },
  closeout: {
    title: "Closure readiness",
    summary: "Verify that all required conditions pass before the audit is formally closed out.",
  },
};

const safeTab = (value: string | null): WorkspaceTab => (TABS.includes((value ?? "") as WorkspaceTab) ? (value as WorkspaceTab) : "war-room");
const dateFmt = (value: string | null | undefined) => (value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");
const dateTimeFmt = (value: string | null | undefined) => (value ? new Date(value).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

const REPORT_SHARE_GROUP_LABELS: Record<string, string> = {
  accountable_manager: "Accountable Manager",
  quality_manager: "Quality Manager",
  department_heads: "Department Heads",
  audited_department: "Audited department personnel",
  shop_personnel: "Shop personnel",
  facility_personnel: "Facility personnel",
};

function chatActionTone(kind: "sent" | "received") {
  if (typeof window === "undefined") return;
  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = kind === "sent" ? 720 : 520;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(kind === "sent" ? 0.08 : 0.06, ctx.currentTime + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.16);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.18);
    setTimeout(() => void ctx.close().catch(() => undefined), 260);
  } catch {
    // Audio feedback is best-effort and may be blocked by browser settings.
  }
}

function chatActionClass(action: CARActionOut, currentUserId?: string | null): string {
  const type = String(action.action_type || "").toUpperCase();
  const hasActor = Boolean(action.actor_user_id);
  const actorName = String(action.actor_name || "").trim().toLowerCase();
  const message = String(action.message || "").trim().toLowerCase();
  const isSystemName = !actorName || actorName === "system" || actorName === "system update";
  const looksLikeSystemEvent = type !== "COMMENT" || message.startsWith("status changed") || message.startsWith("car created") || message.includes("workflow") || message.includes("verified") || message.includes("closed");
  if (hasActor && action.actor_user_id === currentUserId) return "is-own";
  if (!hasActor && isSystemName && looksLikeSystemEvent) return "is-system";
  return "is-other";
}

function chatActorLabel(action: CARActionOut, currentUserId?: string | null): string {
  const type = String(action.action_type || "").toUpperCase();
  const actorName = String(action.actor_name || "").trim();
  if (action.actor_user_id && action.actor_user_id === currentUserId) return "You";
  if (actorName && actorName.toLowerCase() !== "system") return actorName;
  if (type === "COMMENT") return "Auditee / responder";
  return "System";
}

function normalizeChatDeliveryStatus(status?: string | null): "sending" | "sent" | "delivered" | "read" | "failed" {
  const value = String(status || "").trim().toUpperCase();
  if (!value || value === "SENT" || value === "SERVER_ACK" || value === "POSTED" || value === "DELIVERED") return "sent";
  if (value === "SENDING" || value === "PENDING") return "sending";
  if (value === "RECIPIENT_DELIVERED" || value === "DELIVERY_ACK" || value === "DELIVERED_TO_RECIPIENT") return "delivered";
  if (value === "READ" || value === "SEEN" || value === "READ_BY_RECIPIENT" || value === "READ_BY_AUDITEE") return "read";
  if (value === "FAILED" || value === "ERROR") return "failed";
  return "sent";
}

function chatDeliveryMeta(status?: string | null): { label: string; className: string; icon: "clock" | "check" | "checks" } {
  const normalized = normalizeChatDeliveryStatus(status);
  if (normalized === "sending") return { label: "Sending", className: "is-sending", icon: "clock" };
  if (normalized === "delivered") return { label: "Delivered", className: "is-delivered", icon: "checks" };
  if (normalized === "read") return { label: "Read", className: "is-read", icon: "checks" };
  if (normalized === "failed") return { label: "Failed", className: "is-failed", icon: "clock" };
  return { label: "Sent", className: "is-sent", icon: "check" };
}

const CHECKLIST_FILE_ACCEPT = ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const FINDING_EVIDENCE_FILE_ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.doc,.docx,.xls,.xlsx,application/pdf,image/png,image/jpeg,image/webp,text/plain,text/csv,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";


function lowerFileMeta(name?: string | null, type?: string | null): string {
  return `${name || ""} ${type || ""}`.toLowerCase();
}

function isPdfChecklist(name?: string | null, type?: string | null): boolean {
  const value = lowerFileMeta(name, type);
  return value.includes("application/pdf") || value.endsWith(".pdf") || value.includes(".pdf");
}

function isWordChecklist(name?: string | null, type?: string | null): boolean {
  const value = lowerFileMeta(name, type);
  return value.includes("wordprocessingml") || value.includes("msword") || value.endsWith(".docx") || value.endsWith(".doc") || value.includes(".docx") || value.includes(".doc ");
}

function displayChecklistName(fileRef: string | null | undefined): string {
  const raw = (fileRef || "").trim();
  if (!raw) return "Committed checklist";
  const basename = raw.split(/[\/]+/).filter(Boolean).pop() || raw;
  const withoutPrefix = basename.replace(/^[a-f0-9]{32}[_-]+/i, "").replace(/^[a-f0-9]{8,64}[_-]+/i, "");
  return withoutPrefix.trim() || "Committed checklist";
}

const findingLevelOptions = [
  { value: "LEVEL_1", label: "Level 1 · Critical", type: "NON_CONFORMITY", severity: "CRITICAL", note: "Immediate CAPA required." },
  { value: "LEVEL_2", label: "Level 2 · Major", type: "NON_CONFORMITY", severity: "MAJOR", note: "CAPA required." },
  { value: "LEVEL_3", label: "Level 3 · Minor", type: "NON_CONFORMITY", severity: "MINOR", note: "CAPA required where accepted." },
  { value: "LEVEL_4", label: "Observation", type: "OBSERVATION", severity: "MINOR", note: "Monitored only; repeated unresolved observations may be escalated to Level 3." },
] as const;

type FindingLevelValue = typeof findingLevelOptions[number]["value"];

function bytesLabel(size: number): string {
  if (!Number.isFinite(size)) return "—";
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return `${size} B`;
}

function buildNextFindingReference(auditRef: string | null | undefined, rows: Array<{ finding?: { finding_ref?: string | null } }>): string {
  const prefix = (auditRef || "QAR").trim();
  let max = 0;
  rows.forEach((row) => {
    const value = row.finding?.finding_ref || "";
    const match = value.match(/(?:F|FIND)[-\/]?(\d+)$/i);
    if (match) max = Math.max(max, Number(match[1]) || 0);
  });
  return `${prefix}-F-${String(max + 1).padStart(3, "0")}`;
}

function checklistItemStatusLabel(status?: string | null): string {
  switch (status) {
    case "COMPLIANT": return "Compliant";
    case "NON_CONFORMING": return "NCR";
    case "OBSERVATION": return "Observation";
    case "NOT_APPLICABLE": return "N/A";
    default: return "Pending";
  }
}

function formatRelative(days: number): string {
  if (days === 0) return "today";
  if (days > 0) return `in ${days} day${days === 1 ? "" : "s"}`;
  const overdue = Math.abs(days);
  return `${overdue} day${overdue === 1 ? "" : "s"} overdue`;
}

function buildScheduleCard(audit: { audit_ref: string; status: string; planned_start: string | null; planned_end: string | null } | null, now: Date) {
  if (!audit) return { tone: "muted", label: "Schedule", value: "Not available", meta: "This audit has no schedule attached." };
  if (audit.status === "IN_PROGRESS") {
    return { tone: "progress", label: "Schedule", value: "In progress", meta: `${dateFmt(audit.planned_start)} → ${dateFmt(audit.planned_end)}` };
  }
  const start = audit.planned_start ? new Date(audit.planned_start) : null;
  const end = audit.planned_end ? new Date(audit.planned_end) : start;
  if (start && !Number.isNaN(start.getTime())) {
    const startDays = Math.ceil((start.getTime() - now.getTime()) / 86_400_000);
    if (startDays >= 0) {
      return { tone: "planned", label: "Schedule", value: `Starts ${dateFmt(audit.planned_start)}`, meta: formatRelative(startDays) };
    }
  }
  if (end && !Number.isNaN(end.getTime()) && audit.status !== "CLOSED") {
    const endDays = Math.ceil((end.getTime() - now.getTime()) / 86_400_000);
    if (endDays < 0) {
      return { tone: "overdue", label: "Schedule", value: `Was due ${dateFmt(audit.planned_end || audit.planned_start)}`, meta: formatRelative(endDays) };
    }
  }
  return { tone: "muted", label: "Schedule", value: `Scheduled ${dateFmt(audit.planned_start)}`, meta: `${dateFmt(audit.planned_start)} → ${dateFmt(audit.planned_end)}` };
}


function buildFallbackWorkflow(audit: any) {
  const stages = [
    {
      id: "war-room",
      label: "War room",
      complete: Boolean(audit.planned_start && audit.planned_end && audit.lead_auditor_user_id && (audit.auditee || audit.auditee_email || audit.auditee_user_id)),
      helper: "Schedule, lead auditor, and auditee are set.",
      metric: audit.audit_ref,
    },
    {
      id: "checklist",
      label: "Checklist",
      complete: Boolean(audit.checklist_file_ref),
      helper: "Upload a controlled checklist file or create checklist rows in the portal.",
      metric: audit.checklist_file_ref ? "File uploaded" : "Checklist pending",
    },
    { id: "findings", label: "Findings", complete: Boolean(audit.actual_start || audit.actual_end), helper: "Fieldwork has started or findings are captured.", metric: audit.actual_start || "Pending" },
    { id: "report", label: "Report", complete: Boolean(audit.report_file_ref), helper: "Issued report is uploaded and locks new findings.", metric: audit.report_file_ref ? "Uploaded" : "Pending" },
    { id: "cars", label: "CARs", complete: true, helper: "Open CAR status is checked when CAR data is available.", metric: "No open CARs" },
    { id: "evidence", label: "Evidence", complete: Boolean(audit.checklist_file_ref || audit.report_file_ref), helper: "Checklist, report, or CAR attachments are available as evidence.", metric: audit.checklist_file_ref || audit.report_file_ref ? "Evidence present" : "Evidence pending" },
    { id: "closeout", label: "Closeout", complete: audit.status === "CLOSED", helper: "Audit register status is closed.", metric: audit.status },
  ];
  const current = stages.find((stage) => !stage.complete) ?? stages[stages.length - 1];
  const completed = stages.filter((stage) => stage.complete).length;
  return {
    audit_id: audit.id,
    current_stage_id: current.id,
    current_stage_label: current.label,
    percent_complete: Math.round((completed / TABS.length) * 100),
    findings_total: 0,
    findings_open: 0,
    cars_total: 0,
    cars_open: 0,
    checklist_uploaded: Boolean(audit.checklist_file_ref),
    report_uploaded: Boolean(audit.report_file_ref),
    acknowledged_by_name: null,
    acknowledged_by_email: null,
    created_at: audit.created_at ?? null,
    stages: stages.map((stage) => ({ ...stage, active: stage.id === current.id })),
  };
}


function hueFromString(value?: string | null): number {
  const input = (value || "Quality").trim();
  let hash = 0;
  for (let index = 0; index < input.length; index += 1) hash = ((hash << 5) - hash + input.charCodeAt(index)) | 0;
  return Math.abs(hash) % 360;
}

function initialsForName(value?: string | null): string {
  const cleaned = (value || "").trim();
  if (!cleaned) return "--";
  return cleaned.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || cleaned.slice(0, 2).toUpperCase();
}

function storedAvatarUrl(...keys: Array<string | null | undefined>): string | null {
  if (typeof window === "undefined") return null;
  for (const key of keys) {
    const clean = (key || "").trim();
    if (!clean) continue;
    const direct = window.localStorage.getItem(`amo_portal_profile_avatar:${clean}`);
    if (direct) return direct;
    const profile = window.localStorage.getItem(`profile_avatar:${clean}`);
    if (profile) return profile;
  }
  return null;
}

function personLookupKeys(person: QMSPersonOption): string[] {
  return [person.id, person.staff_code, person.email]
    .map((value) => (value || "").trim())
    .filter(Boolean);
}

type AuditPersonLike = Partial<QMSPersonOption> & { full_name?: string | null };

function looksLikeTechnicalIdentifier(value?: string | null): boolean {
  const clean = (value || "").trim();
  if (!clean) return false;
  const compact = clean.replace(/\s+/g, "");
  return (
    isUuidLike(clean)
    || /^ID[-_A-Z0-9]{4,}$/i.test(compact)
    || /^[a-f0-9]{24,64}$/i.test(compact)
    || (/^[A-Z0-9_-]{8,}$/.test(compact) && !clean.includes("@"))
  );
}

function presentablePersonLabel(value?: string | null): string | null {
  const clean = (value || "").trim();
  if (!clean || looksLikeTechnicalIdentifier(clean)) return null;
  return clean;
}

function displayPersonName(value?: string | null, person?: AuditPersonLike | null, fallback = "Not assigned", nameHint?: string | null): string {
  return (
    presentablePersonLabel(nameHint)
    || presentablePersonLabel(person?.full_name)
    || presentablePersonLabel(person?.email)
    || presentablePersonLabel(value)
    || fallback
  );
}

const WorkspaceAvatar: React.FC<{ person?: AuditPersonLike | null; fallback?: string | null; size?: "md" | "lg" }> = ({ person, fallback, size = "md" }) => {
  const src = person?.avatar_url || storedAvatarUrl(person?.id, person?.staff_code, person?.email);
  const name = displayPersonName(null, person, fallback || "Auditor");
  return <span className={`qa-person-avatar qa-person-avatar--${size}`} title={name}>{src ? <img src={src} alt={name} /> : <span>{initialsForName(name)}</span>}</span>;
};

const CompanyLogoMark: React.FC<{ brand?: QMSAuditeeBrandOut | null; label: string }> = ({ brand, label }) => {
  const candidates = useMemo(() => {
    const urls = [brand?.logo_url, ...(brand?.logo_urls ?? [])].filter(Boolean) as string[];
    return Array.from(new Set(urls));
  }, [brand?.logo_url, brand?.logo_urls]);
  const [index, setIndex] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const candidateKey = candidates.join("|");

  useEffect(() => {
    setIndex(0);
    setLoaded(false);
  }, [candidateKey]);

  const src = candidates[index] ?? null;
  const canTryAnother = index < candidates.length - 1;

  return (
    <span
      className={`audit-company-mark audit-company-mark--lg${src ? "" : " is-fallback"}${src && !loaded ? " is-loading" : ""}`}
      title={brand?.domain ? `${label} · ${brand.domain}` : label}
      aria-label={`${label} logo`}
    >
      {src ? (
        <img
          key={src}
          src={src}
          alt={`${label} logo`}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setLoaded(true)}
          onError={() => {
            setLoaded(false);
            if (canTryAnother) setIndex((current) => current + 1);
            else setIndex(candidates.length);
          }}
        />
      ) : (
        <span className="audit-company-mark__initials">{initialsForName(label)}</span>
      )}
    </span>
  );
};


const DocxInlinePreview: React.FC<{ source: Blob | File | null; fileName?: string | null }> = ({ source, fileName }) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !source) return;
    let cancelled = false;
    host.innerHTML = "";
    setError(null);
    setStatus("Rendering Word preview…");

    import("docx-preview")
      .then(({ renderAsync }) => renderAsync(source, host, undefined, {
        breakPages: false,
        ignoreFonts: true,
        ignoreHeight: true,
        ignoreLastRenderedPageBreak: true,
        ignoreWidth: true,
        inWrapper: false,
        useBase64URL: true,
      }))
      .then(() => {
        if (!cancelled) setStatus(null);
      })
      .catch((previewError: unknown) => {
        if (cancelled) return;
        host.innerHTML = "";
        setStatus(null);
        setError(previewError instanceof Error ? previewError.message : "Word preview could not be rendered in the browser.");
      });

    return () => {
      cancelled = true;
      host.innerHTML = "";
    };
  }, [source]);

  return (
    <div className="audit-docx-preview">
      <div className="audit-docx-preview__bar">
        <FileText size={14} />
        <span>{fileName || "Word checklist"}</span>
        {status ? <em>{status}</em> : null}
      </div>
      {error ? (
        <div className="audit-empty-state audit-empty-state--compact">
          <ShieldAlert size={18} />
          <div>
            <strong>Word preview unavailable</strong>
            <p>{error}. Download the file and continue fieldwork in the live checklist rows.</p>
          </div>
        </div>
      ) : null}
      <div ref={hostRef} className="audit-docx-preview__body" aria-label="Word checklist preview" />
    </div>
  );
};

const QualityAuditRunHubPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; auditId?: string; department?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const auditKey = params.auditId ?? "";
  const activeTab = safeTab(searchParams.get("tab"));
  const [tick, setTick] = useState(Date.now());
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [carChatCollapsed, setCarChatCollapsed] = useState(false);
  const [selectedChatCarId, setSelectedChatCarId] = useState<string | null>(null);
  const [carChatDraft, setCarChatDraft] = useState("");
  const [carRulesOpen, setCarRulesOpen] = useState(false);
  const [pendingReportShareGroups, setPendingReportShareGroups] = useState<string[] | null>(null);
  const [reportShareNotice, setReportShareNotice] = useState<string | null>(null);
  const lastChatActionIdRef = useRef<string | null>(null);
  const chatMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const [selectedChecklistFile, setSelectedChecklistFile] = useState<File | null>(null);
  const [checklistPreviewUrl, setChecklistPreviewUrl] = useState<string | null>(null);
  const [committedChecklistUrl, setCommittedChecklistUrl] = useState<string | null>(null);
  const [committedChecklistBlob, setCommittedChecklistBlob] = useState<Blob | null>(null);
  const [committedChecklistType, setCommittedChecklistType] = useState<string | null>(null);
  const [committedChecklistLoading, setCommittedChecklistLoading] = useState(false);
  const [committedChecklistError, setCommittedChecklistError] = useState<string | null>(null);
  const [checklistDraft, setChecklistDraft] = useState({ section: "", requirement_ref: "", prompt: "", objective_evidence: "" });
  const manualChecklistFirstInputRef = useRef<HTMLInputElement | null>(null);
  const [savingChecklistItemId, setSavingChecklistItemId] = useState<string | null>(null);
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [findingForm, setFindingForm] = useState({ level: "LEVEL_3" as FindingLevelValue, requirement_ref: "", description: "", objective_evidence: "", target_close_date: "", safety_sensitive: false });
  const [editingFindingId, setEditingFindingId] = useState<string | null>(null);
  const [findingEditForm, setFindingEditForm] = useState({ level: "LEVEL_3" as FindingLevelValue, requirement_ref: "", description: "", objective_evidence: "", target_close_date: "", safety_sensitive: false });
  const [findingEvidenceFiles, setFindingEvidenceFiles] = useState<File[]>([]);
  const findingEvidenceInputRef = useRef<HTMLInputElement | null>(null);
  const findingEvidenceTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selectedChecklistFile) {
      setChecklistPreviewUrl(null);
      return;
    }
    const url = window.URL.createObjectURL(selectedChecklistFile);
    setChecklistPreviewUrl(url);
    return () => window.URL.revokeObjectURL(url);
  }, [selectedChecklistFile]);

  const openObjectUrl = (url: string | null, missingMessage: string) => {
    if (!url) {
      setUploadError(missingMessage);
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const openReportWithAuth = async () => {
    if (!audit?.id) return;
    setActionError(null);
    try {
      const blob = await qmsDownloadAuditReport(audit.id);
      const url = window.URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Report could not be opened.");
    }
  };

  const auditContextQuery = useQuery({
    queryKey: ["qms-audit-context", auditKey],
    queryFn: async () => {
      const resolveOnly = async () => {
        const resolved = await qmsResolveAudit(auditKey, { silent: true });
        return resolved ? { audit: resolved, workflow: buildFallbackWorkflow(resolved), degraded: true } : null;
      };

      try {
        if (isUuidLike(auditKey)) {
          return await qmsGetAuditWorkflow(auditKey, { silent: true });
        }
        const resolved = await qmsResolveAudit(auditKey, { silent: true });
        if (!resolved) return null;
        return await qmsGetAuditWorkflow(resolved.id, { silent: true });
      } catch (error) {
        console.warn("Quality audit workflow endpoint unavailable; loading audit register fallback.", error);
        return resolveOnly();
      }
    },
    enabled: !!auditKey,
    staleTime: 30_000,
  });

  const audit = auditContextQuery.data?.audit ?? null;

  useEffect(() => {
    if (!audit?.id || !audit.checklist_file_ref) {
      setCommittedChecklistUrl(null);
      setCommittedChecklistBlob(null);
      setCommittedChecklistType(null);
      setCommittedChecklistError(null);
      setCommittedChecklistLoading(false);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    setCommittedChecklistLoading(true);
    setCommittedChecklistError(null);

    qmsDownloadAuditChecklist(audit.id)
      .then((blob) => {
        objectUrl = window.URL.createObjectURL(blob);
        if (cancelled) {
          window.URL.revokeObjectURL(objectUrl);
          return;
        }
        setCommittedChecklistUrl(objectUrl);
        setCommittedChecklistBlob(blob);
        setCommittedChecklistType(blob.type || null);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setCommittedChecklistUrl(null);
          setCommittedChecklistBlob(null);
          setCommittedChecklistType(null);
          setCommittedChecklistError(error instanceof Error ? error.message : "Checklist preview could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setCommittedChecklistLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) window.URL.revokeObjectURL(objectUrl);
    };
  }, [audit?.id, audit?.checklist_file_ref]);

  useEffect(() => {
    if (!audit) return;
    const canonical = toAuditReferenceSlug(audit.audit_ref);
    if (!canonical) return;
    if (auditKey !== canonical) {
      navigate(`${buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref })}?tab=${activeTab}`, { replace: true });
    }
  }, [activeTab, amoCode, audit, auditKey, department, navigate]);

  const assignedPersonKeys = useMemo(() => (
    [
      audit?.lead_auditor_user_id,
      audit?.observer_auditor_user_id,
      audit?.assistant_auditor_user_id,
      audit?.auditee_user_id,
    ]
      .map((value) => (value || "").trim())
      .filter(Boolean)
  ), [audit?.assistant_auditor_user_id, audit?.auditee_user_id, audit?.lead_auditor_user_id, audit?.observer_auditor_user_id]);

  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", "workspace", amoCode, assignedPersonKeys.join("|")],
    queryFn: async () => {
      const base = await qmsListAuditPersonnelOptions({ limit: 100 });
      const direct = await Promise.all(
        assignedPersonKeys.map((key) => qmsListAuditPersonnelOptions({ search: key, limit: 10 }).catch(() => [] as QMSPersonOption[]))
      );
      const merged = new Map<string, QMSPersonOption>();
      [...base, ...direct.flat()].forEach((person) => {
        const keys = personLookupKeys(person);
        const stableKey = (keys[0] || person.full_name || person.email || `${merged.size}`).toLowerCase();
        merged.set(stableKey, person);
      });
      return Array.from(merged.values());
    },
    enabled: !!audit,
    staleTime: 5 * 60_000,
  });

  const peopleByKey = useMemo(() => {
    const next = new Map<string, QMSPersonOption>();
    (personnelQuery.data ?? []).forEach((person) => {
      personLookupKeys(person).forEach((key) => next.set(key.toLowerCase(), person));
    });
    return next;
  }, [personnelQuery.data]);

  const resolvePerson = (value?: string | null): QMSPersonOption | null => {
    const key = (value || "").trim().toLowerCase();
    if (!key) return null;
    return peopleByKey.get(key) ?? null;
  };

  const resolveAuditPerson = (value?: string | null, nameHint?: string | null): AuditPersonLike | null => {
    const resolved = resolvePerson(value);
    const hintedName = presentablePersonLabel(nameHint);
    if (!hintedName) return resolved;
    return {
      ...(resolved || {}),
      id: resolved?.id || value || hintedName,
      full_name: hintedName,
      email: resolved?.email ?? null,
      role: resolved?.role ?? null,
      department_id: resolved?.department_id ?? null,
      position_title: resolved?.position_title ?? null,
      staff_code: resolved?.staff_code ?? null,
      avatar_url: resolved?.avatar_url ?? null,
    };
  };

  const auditeeBrandQuery = useQuery({
    queryKey: ["qms-auditee-brand", audit?.auditee, audit?.auditee_email],
    queryFn: () => qmsResolveAuditeeBrand({ name: audit?.auditee || undefined, email: audit?.auditee_email || undefined }),
    enabled: !!audit && Boolean(audit.auditee || audit.auditee_email),
    staleTime: 12 * 60_000,
    retry: 1,
  });

  const registerQuery = useQuery({
    queryKey: ["qms-audit-register", "workspace", audit?.id],
    queryFn: () => qmsGetAuditRegister({ audit_id: audit!.id, limit: 200 }, { silent: true }),
    enabled: !!audit?.id,
    staleTime: 60_000,
  });

  const checklistItemsQuery = useQuery({
    queryKey: ["qms-audit-checklist-items", audit?.id],
    queryFn: () => qmsListAuditChecklistItems(audit!.id),
    enabled: !!audit?.id,
    staleTime: 30_000,
  });

  const findingAttachmentsQuery = useQuery({
    queryKey: ["qms-audit-finding-attachments", audit?.id],
    queryFn: () => qmsListAuditFindingAttachments(audit!.id),
    enabled: !!audit?.id && ["findings", "evidence", "closeout"].includes(activeTab),
    staleTime: 45_000,
  });

  const checklistItems = checklistItemsQuery.data ?? [];
  const findings = registerQuery.data?.rows ?? [];
  const cars = useQuery({
    queryKey: ["qms-cars", "workspace", audit?.id],
    queryFn: () => qmsListCars({ audit_id: audit!.id, limit: 200 }, { silent: true }),
    staleTime: 60_000,
    enabled: !!audit?.id && ["war-room", "findings", "cars", "evidence", "closeout"].includes(activeTab),
  });
  const attachments = useQuery({
    queryKey: ["qms-car-attachments", "workspace", audit?.id],
    queryFn: () => qmsListCarAttachmentsBulk({ car_ids: (cars.data ?? []).map((car) => car.id) }),
    enabled: activeTab === "evidence" && (cars.data?.length ?? 0) > 0,
    staleTime: 60_000,
  });

  const carExtensionRequestsQuery = useQuery({
    queryKey: ["qms-car-extension-requests", "workspace", audit?.id, (cars.data ?? []).map((car) => car.id).join(",")],
    queryFn: async () => {
      const pairs = await Promise.all((cars.data ?? []).map(async (car) => ({ carId: car.id, requests: await qmsListCarExtensionRequests(car.id) })));
      return pairs.flatMap((pair) => pair.requests.map((request) => ({ ...request, car_id: pair.carId })));
    },
    enabled: activeTab === "cars" && (cars.data?.length ?? 0) > 0,
    staleTime: 30_000,
  });

  const carResponsesQuery = useQuery({
    queryKey: ["qms-car-responses", "workspace", audit?.id, (cars.data ?? []).map((car) => car.id).join(",")],
    queryFn: async () => {
      const pairs = await Promise.all((cars.data ?? []).map(async (car) => ({ carId: car.id, responses: await qmsListCarResponses(car.id, false) })));
      return pairs.flatMap((pair) => pair.responses.map((response) => ({ ...response, car_id: pair.carId })));
    },
    enabled: activeTab === "cars" && (cars.data?.length ?? 0) > 0,
    staleTime: 15_000,
  });

  const selectedChatCar = useMemo(() => {
    const rows = cars.data ?? [];
    return rows.find((car) => car.id === selectedChatCarId) ?? rows[0] ?? null;
  }, [cars.data, selectedChatCarId]);

  const carActionsQuery = useQuery({
    queryKey: ["qms-car-actions-chat", selectedChatCar?.id],
    queryFn: () => qmsListCarActions(selectedChatCar!.id),
    enabled: activeTab === "cars" && !!selectedChatCar?.id,
    staleTime: 0,
    refetchInterval: activeTab === "cars" && !!selectedChatCar?.id ? 3500 : false,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    lastChatActionIdRef.current = null;
  }, [selectedChatCar?.id]);

  useEffect(() => {
    const newest = carActionsQuery.data?.[0];
    if (!newest || activeTab !== "cars") return;
    const previous = lastChatActionIdRef.current;
    if (previous && previous !== newest.id && newest.actor_user_id !== currentUser?.id) {
      chatActionTone("received");
    }
    lastChatActionIdRef.current = newest.id;
  }, [activeTab, carActionsQuery.data, currentUser?.id]);

  useEffect(() => {
    if (activeTab === "cars" && !carChatCollapsed) {
      chatMessagesEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, [activeTab, carChatCollapsed, carActionsQuery.data?.length, selectedChatCar?.id]);

  const carIdsForAudit = useMemo(() => new Set((cars.data ?? []).map((c) => c.id)), [cars.data]);

  const evidenceCount = useMemo(() => {
    const attachmentCount = (attachments.data ?? []).filter((a) => carIdsForAudit.has(a.car_id)).length;
    return attachmentCount + (audit?.checklist_file_ref ? 1 : 0) + (audit?.report_file_ref ? 1 : 0);
  }, [attachments.data, audit?.checklist_file_ref, audit?.report_file_ref, carIdsForAudit]);

  const canEditChecklist = useMemo(() => {
    if (!currentUser || !audit) return false;
    if (currentUser.is_superuser || currentUser.is_amo_admin) return true;
    return [audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].includes(currentUser.id);
  }, [audit, currentUser]);

  const currentUserRole = String(currentUser?.role ?? "").toUpperCase();
  const isLeadAuditor = Boolean(currentUser?.id && audit?.lead_auditor_user_id === currentUser.id);
  const isSystemQualityAdmin = Boolean(currentUser?.is_superuser || currentUser?.is_amo_admin || ["SUPERUSER", "AMO_ADMIN"].includes(currentUserRole));
  const isQualityManagerOnly = Boolean(currentUserRole === "QUALITY_MANAGER" && !isLeadAuditor && !isSystemQualityAdmin);
  const canOwnAuditFindings = Boolean(isLeadAuditor || isSystemQualityAdmin);
  const canFlagForReview = Boolean(currentUserRole === "QUALITY_MANAGER" || canOwnAuditFindings);
  const findingsLockedByReport = Boolean(audit?.report_file_ref);

  const scheduleCard = useMemo(() => buildScheduleCard(audit, new Date(tick)), [audit, tick]);
  const committedChecklistName = displayChecklistName(audit?.checklist_file_ref);
  const committedChecklistIsPdf = Boolean(committedChecklistUrl && isPdfChecklist(committedChecklistName, committedChecklistType));
  const committedChecklistIsWord = Boolean(committedChecklistBlob && isWordChecklist(committedChecklistName, committedChecklistType));
  const workflow = auditContextQuery.data?.workflow;
  const allCars = cars.data ?? [];
  const openCars = allCars.filter((car) => car.status !== "CLOSED");
  const openFindings = findings.filter((row) => !row.finding.closed_at);
  const linkedCarsFromFindings = findings.flatMap((row) => row.linked_cars);
  const findingAttachmentMap = useMemo(() => {
    const map = new Map<string, NonNullable<typeof findingAttachmentsQuery.data>>();
    (findingAttachmentsQuery.data ?? []).forEach((attachment) => {
      const rows = map.get(attachment.finding_id) ?? [];
      rows.push(attachment);
      map.set(attachment.finding_id, rows);
    });
    return map;
  }, [findingAttachmentsQuery.data]);
  const assignedAuditors = [
    { label: "Lead", value: audit?.lead_auditor_user_id },
    { label: "Observer", value: audit?.observer_auditor_user_id },
    { label: "Assistant", value: audit?.assistant_auditor_user_id },
  ].filter((item) => item.value);
  const leadAuditor = resolveAuditPerson(audit?.lead_auditor_user_id, audit?.lead_auditor_name);
  const observerAuditor = resolveAuditPerson(audit?.observer_auditor_user_id, audit?.observer_auditor_name);
  const assistantAuditor = resolveAuditPerson(audit?.assistant_auditor_user_id, audit?.assistant_auditor_name);
  const auditeeUser = resolveAuditPerson(audit?.auditee_user_id, audit?.auditee_user_name);
  const brand = auditeeBrandQuery.data;
  const auditeeDisplayName = displayPersonName(
    audit?.auditee_user_id,
    auditeeUser,
    "Auditee not set",
    brand?.company_name || audit?.auditee || audit?.auditee_user_name || audit?.auditee_email,
  );

  const refetchAuditData = async () => {
    await auditContextQuery.refetch();
    await checklistItemsQuery.refetch();
    await registerQuery.refetch();
    await cars.refetch();
  };

  const issueNotice = useMutation({
    mutationFn: () => audit ? qmsIssueAuditNotice(audit.id, { stage: "manual" }) : Promise.reject(new Error("Audit not resolved.")),
    onSuccess: () => { void refetchAuditData(); setActionError(null); },
    onError: (error: Error) => setActionError(error.message || "Failed to issue audit notice."),
  });

  const closeAudit = useMutation({
    mutationFn: () => audit ? qmsCloseAudit(audit.id) : Promise.reject(new Error("Audit not resolved.")),
    onSuccess: () => { void refetchAuditData(); setActionError(null); },
    onError: (error: Error) => setActionError(error.message || "Failed to close audit."),
  });

  const exportPack = useMutation({
    mutationFn: () => audit ? downloadAuditEvidencePack(audit.id) : Promise.reject(new Error("Audit not resolved.")),
    onSuccess: (file) => { saveDownloadedFile(file); setActionError(null); },
    onError: (error: Error) => setActionError(error.message || "Failed to export audit evidence pack."),
  });


  const commitChecklistUpload = useMutation({
    mutationFn: () => {
      if (!audit?.id || !selectedChecklistFile) return Promise.reject(new Error("Select a checklist file before committing upload."));
      return qmsUploadAuditChecklist(audit.id, selectedChecklistFile);
    },
    onSuccess: () => {
      setSelectedChecklistFile(null);
      setUploadError(null);
      void refetchAuditData();
    },
    onError: (error: Error) => setUploadError(error.message || "Failed to upload checklist."),
  });

  const createChecklistItem = useMutation({
    mutationFn: () => {
      if (!audit?.id) return Promise.reject(new Error("Audit not resolved."));
      if (!checklistDraft.prompt.trim()) return Promise.reject(new Error("Checklist item text is required."));
      return qmsCreateAuditChecklistItem(audit.id, {
        section: checklistDraft.section.trim() || null,
        requirement_ref: checklistDraft.requirement_ref.trim() || null,
        prompt: checklistDraft.prompt.trim(),
        objective_evidence: checklistDraft.objective_evidence.trim() || null,
        sort_order: checklistItems.length,
      });
    },
    onSuccess: () => {
      setChecklistDraft({ section: "", requirement_ref: "", prompt: "", objective_evidence: "" });
      void checklistItemsQuery.refetch();
      void auditContextQuery.refetch();
      setUploadError(null);
    },
    onError: (error: Error) => setUploadError(error.message || "Failed to add checklist item."),
  });

  const updateChecklistItem = useMutation({
    mutationFn: ({ item, patch }: { item: QualityChecklistItemOut; patch: Partial<QualityChecklistItemOut> }) => {
      if (!audit?.id) return Promise.reject(new Error("Audit not resolved."));
      setSavingChecklistItemId(item.id);
      return qmsUpdateAuditChecklistItem(audit.id, item.id, patch);
    },
    onSuccess: () => {
      setSavingChecklistItemId(null);
      void checklistItemsQuery.refetch();
      void auditContextQuery.refetch();
    },
    onError: (error: Error) => {
      setSavingChecklistItemId(null);
      setUploadError(error.message || "Failed to update checklist item.");
    },
  });

  const updateObjectiveEvidenceText = (value: string, focus = true) => {
    setFindingForm((prev) => ({ ...prev, objective_evidence: value }));
    if (focus) {
      window.requestAnimationFrame(() => findingEvidenceTextareaRef.current?.focus());
    }
  };

  const insertObjectiveEvidenceText = (insertText: string) => {
    const textarea = findingEvidenceTextareaRef.current;
    const current = findingForm.objective_evidence || "";
    if (!textarea) {
      updateObjectiveEvidenceText(`${current}${current && !current.endsWith("\n") ? "\n" : ""}${insertText}`);
      return;
    }
    const start = textarea.selectionStart ?? current.length;
    const end = textarea.selectionEnd ?? current.length;
    const before = current.slice(0, start);
    const after = current.slice(end);
    updateObjectiveEvidenceText(`${before}${insertText}${after}`);
    window.requestAnimationFrame(() => {
      const next = start + insertText.length;
      textarea.setSelectionRange(next, next);
    });
  };

  const wrapObjectiveEvidenceSelection = (prefix: string, suffix: string, placeholder: string) => {
    const textarea = findingEvidenceTextareaRef.current;
    const current = findingForm.objective_evidence || "";
    const start = textarea?.selectionStart ?? current.length;
    const end = textarea?.selectionEnd ?? current.length;
    const selected = current.slice(start, end) || placeholder;
    const replacement = `${prefix}${selected}${suffix}`;
    updateObjectiveEvidenceText(`${current.slice(0, start)}${replacement}${current.slice(end)}`);
    window.requestAnimationFrame(() => {
      const nextStart = start + prefix.length;
      const nextEnd = nextStart + selected.length;
      findingEvidenceTextareaRef.current?.setSelectionRange(nextStart, nextEnd);
    });
  };

  const addFindingEvidenceFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const nextFiles = Array.from(files).filter((file) => file.size > 0);
    setFindingEvidenceFiles((prev) => {
      const existing = new Set(prev.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
      const merged = [...prev];
      nextFiles.forEach((file) => {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (!existing.has(key)) merged.push(file);
      });
      return merged;
    });
    if (findingEvidenceInputRef.current) findingEvidenceInputRef.current.value = "";
  };

  const createFinding = useMutation({
    mutationFn: async () => {
      if (!audit?.id) return Promise.reject(new Error("Audit not resolved."));
      if (audit.report_file_ref) return Promise.reject(new Error("Audit report already issued. New findings are locked."));
      const selected = findingLevelOptions.find((item) => item.value === findingForm.level) ?? findingLevelOptions[2];
      if (!findingForm.description.trim()) return Promise.reject(new Error("Finding description is required."));
      const savedFinding = await qmsCreateFinding(audit.id, {
        finding_ref: buildNextFindingReference(audit.audit_ref, findings),
        finding_type: selected.type,
        severity: selected.severity,
        level: selected.value,
        requirement_ref: findingForm.requirement_ref.trim() || null,
        description: findingForm.description.trim(),
        objective_evidence: findingForm.objective_evidence.trim() || null,
        target_close_date: selected.value === "LEVEL_4" ? null : (findingForm.target_close_date || null),
        safety_sensitive: findingForm.safety_sensitive,
      });
      for (const file of findingEvidenceFiles) {
        await qmsUploadFindingAttachment(savedFinding.id, file);
      }
      return savedFinding;
    },
    onSuccess: () => {
      setFindingForm({ level: "LEVEL_3", requirement_ref: "", description: "", objective_evidence: "", target_close_date: "", safety_sensitive: false });
      setFindingEvidenceFiles([]);
      void refetchAuditData();
      void findingAttachmentsQuery.refetch();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to record finding."),
  });

  const beginEditFinding = (finding: typeof findings[number]["finding"]) => {
    const option = findingLevelOptions.find((item) => item.value === finding.level) ?? findingLevelOptions[2];
    setEditingFindingId(finding.id);
    setFindingEditForm({
      level: option.value,
      requirement_ref: finding.requirement_ref || "",
      description: finding.description || "",
      objective_evidence: finding.objective_evidence || "",
      target_close_date: finding.target_close_date || "",
      safety_sensitive: Boolean(finding.safety_sensitive),
    });
  };

  const updateFindingMutation = useMutation({
    mutationFn: async (finding: typeof findings[number]["finding"]) => {
      const selected = findingLevelOptions.find((item) => item.value === findingEditForm.level) ?? findingLevelOptions[2];
      if (!findingEditForm.description.trim()) throw new Error("Finding description is required.");
      return qmsUpdateFinding(finding.id, {
        finding_type: selected.type,
        severity: selected.severity,
        level: selected.value,
        requirement_ref: findingEditForm.requirement_ref.trim() || null,
        description: findingEditForm.description.trim(),
        objective_evidence: findingEditForm.objective_evidence.trim() || null,
        target_close_date: selected.value === "LEVEL_4" ? null : (findingEditForm.target_close_date || null),
        safety_sensitive: findingEditForm.safety_sensitive,
      }, finding.audit_id);
    },
    onSuccess: () => {
      setEditingFindingId(null);
      void refetchAuditData();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to update finding."),
  });

  const deleteFindingMutation = useMutation({
    mutationFn: async (finding: typeof findings[number]["finding"]) => qmsDeleteFinding(finding.id, finding.audit_id),
    onSuccess: () => {
      void refetchAuditData();
      void findingAttachmentsQuery.refetch();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to delete finding."),
  });

  const flagFindingMutation = useMutation({
    mutationFn: async (finding: typeof findings[number]["finding"]) => {
      const reason = window.prompt("Reason for review flag");
      if (!reason?.trim()) throw new Error("Review flag reason is required.");
      return qmsFlagFindingForReview(finding.id, reason.trim(), finding.audit_id);
    },
    onSuccess: () => setActionError(null),
    onError: (error: Error) => setActionError(error.message || "Failed to flag finding for review."),
  });

  const issueCarMutation = useMutation({
    mutationFn: async (row: typeof findings[number]) => {
      const finding = row.finding;
      const option = findingLevelOptions.find((item) => item.value === finding.level) ?? findingLevelOptions[2];
      return qmsCreateCar({
        program: "QUALITY",
        title: `CAR for ${finding.finding_ref || "audit finding"}`,
        summary: [finding.description, finding.requirement_ref ? `Requirement/reference: ${finding.requirement_ref}` : null, finding.objective_evidence ? `Objective evidence: ${finding.objective_evidence}` : null].filter(Boolean).join("\n\n"),
        priority: option.value === "LEVEL_1" ? "CRITICAL" : option.value === "LEVEL_2" ? "HIGH" : "MEDIUM",
        due_date: finding.target_close_date || null,
        target_closure_date: finding.target_close_date || null,
        assigned_to_user_id: audit?.auditee_user_id || null,
        finding_id: finding.id,
        evidence_required: true,
      });
    },
    onSuccess: () => {
      void refetchAuditData();
      void cars.refetch();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to issue CAR."),
  });

  const shareReportMutation = useMutation({
    mutationFn: async (recipientGroups: string[]) => {
      if (!audit?.id) throw new Error("Audit not resolved.");
      return qmsShareAuditReport(audit.id, {
        recipient_groups: recipientGroups,
        message: `Audit report issued for ${audit.audit_ref}. Review the report and monitor assigned CAR closeout actions.`,
      });
    },
    onSuccess: (result) => {
      setReportShareNotice(`Report shared with ${result.shared} recipient${result.shared === 1 ? "" : "s"}.`);
      setPendingReportShareGroups(null);
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to share report."),
  });

  const sendCarChatMutation = useMutation({
    mutationFn: async (message: string) => {
      if (!selectedChatCar?.id || !message.trim()) throw new Error("Select a CAR and enter a message.");
      return qmsAddCarAction(selectedChatCar.id, { message: message.trim() });
    },
    onMutate: async (message: string) => {
      if (!selectedChatCar?.id) return { tempId: "" };
      const tempId = `pending-${Date.now()}`;
      const optimisticAction: CARActionOut = {
        id: tempId,
        car_id: selectedChatCar.id,
        action_type: "COMMENT" as any,
        message: message.trim(),
        actor_user_id: currentUser?.id ?? null,
        actor_name: currentUser?.full_name || currentUser?.email || "You",
        actor_role: currentUser?.role || null,
        delivery_status: "SENDING",
        created_at: new Date().toISOString(),
      };
      await queryClient.cancelQueries({ queryKey: ["qms-car-actions-chat", selectedChatCar.id] });
      queryClient.setQueryData<CARActionOut[]>(["qms-car-actions-chat", selectedChatCar.id], (prev = []) => [optimisticAction, ...prev]);
      setCarChatDraft("");
      chatActionTone("sent");
      return { tempId };
    },
    onSuccess: (saved, _message, context) => {
      if (selectedChatCar?.id) {
        queryClient.setQueryData<CARActionOut[]>(["qms-car-actions-chat", selectedChatCar.id], (prev = []) => {
          const withoutTemp = prev.filter((item) => item.id !== context?.tempId && item.id !== saved.id);
          return [saved, ...withoutTemp];
        });
      }
      void carActionsQuery.refetch();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to send CAR comment."),
  });

  const requestCarAccessMutation = useMutation({
    mutationFn: async (carId: string) => qmsRequestCarAccess(carId, "I can support resolution of this CAR. Please review and assign write access if appropriate."),
    onSuccess: () => {
      setActionError(null);
      void carActionsQuery.refetch();
    },
    onError: (error: Error) => setActionError(error.message || "Failed to request access."),
  });

  const reviewCarMutation = useMutation({
    mutationFn: async ({ carId, decision }: { carId: string; decision: "accept" | "reject" | "needsEvidence" }) => {
      if (decision === "accept") {
        return qmsReviewCarResponse(carId, { root_cause_status: "ACCEPTED", capa_status: "ACCEPTED", message: "Accepted by lead auditor from audit run hub." });
      }
      const note = window.prompt(decision === "needsEvidence" ? "Evidence note" : "Rejection reason");
      if (!note?.trim()) throw new Error("Review note is required.");
      return qmsReviewCarResponse(carId, {
        root_cause_status: decision === "reject" ? "REJECTED" : "ACCEPTED",
        capa_status: decision === "needsEvidence" ? "NEEDS_EVIDENCE" : "REJECTED",
        root_cause_review_note: decision === "reject" ? note.trim() : null,
        capa_review_note: note.trim(),
        message: note.trim(),
      });
    },
    onSuccess: () => {
      void cars.refetch();
      void carResponsesQuery.refetch();
      void refetchAuditData();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to review CAR response."),
  });

  const forwardDeferralMutation = useMutation({
    mutationFn: async ({ carId, extensionId }: { carId: string; extensionId: string }) => qmsForwardCarExtensionRequest(carId, extensionId),
    onSuccess: () => {
      void carExtensionRequestsQuery.refetch();
      setActionError(null);
    },
    onError: (error: Error) => setActionError(error.message || "Failed to forward deferral request."),
  });

  const setTabUnsafe = (tab: WorkspaceTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
  };

  const currentTabIndex = TABS.indexOf(activeTab);
  const hasCommittedChecklist = Boolean(audit?.checklist_file_ref);
  const hasSelectedChecklist = Boolean(selectedChecklistFile);
  const hasSourceChecklist = hasCommittedChecklist || hasSelectedChecklist;
  const hasPortalChecklist = checklistItems.length > 0;
  const isChecklistEmpty = !hasSourceChecklist && !hasPortalChecklist;
  const workflowStageMap = useMemo(() => new Map((workflow?.stages ?? []).map((stage) => [stage.id, stage])), [workflow?.stages]);
  const isWarRoomReady = Boolean(audit?.planned_start && audit?.planned_end && audit?.lead_auditor_user_id && (audit?.auditee || audit?.auditee_email || audit?.auditee_user_id));
  const isChecklistReady = Boolean(hasCommittedChecklist || workflow?.checklist_uploaded || hasPortalChecklist);
  const isCarsReady = openCars.length === 0;
  const isReportReady = Boolean(audit?.report_file_ref || workflow?.report_uploaded);

  const stepGateMessage = (tab: WorkspaceTab): string | null => {
    switch (tab) {
      case "war-room":
        return isWarRoomReady ? null : "Complete the war room first: schedule, lead auditor, and auditee must be set.";
      case "checklist":
        return isChecklistReady ? null : "Upload or prepare the audit checklist before moving forward.";
      case "cars":
        return isCarsReady ? null : "Close or resolve all open CARs before moving forward.";
      case "report":
        return isReportReady ? null : "Upload the issued audit report before closeout.";
      default:
        return null;
    }
  };

  const firstBlockingStepBefore = (target: WorkspaceTab): string | null => {
    const targetIndex = TABS.indexOf(target);
    for (const step of TABS.slice(0, targetIndex)) {
      const message = stepGateMessage(step);
      if (message) return message;
    }
    return null;
  };

  const setTab = (tab: WorkspaceTab) => {
    const targetIndex = TABS.indexOf(tab);
    if (targetIndex > currentTabIndex) {
      const blocked = firstBlockingStepBefore(tab);
      if (blocked) {
        setActionError(blocked);
        return;
      }
    }
    setActionError(null);
    setTabUnsafe(tab);
  };

  const goPrevious = () => {
    const previous = TABS[Math.max(0, currentTabIndex - 1)];
    if (previous && previous !== activeTab) setTabUnsafe(previous);
  };

  const goNext = () => {
    const currentGate = stepGateMessage(activeTab);
    if (currentGate) {
      setActionError(currentGate);
      return;
    }
    const nextTab = TABS[Math.min(TABS.length - 1, currentTabIndex + 1)];
    if (nextTab && nextTab !== activeTab) {
      setActionError(null);
      setTabUnsafe(nextTab);
    }
  };

  const tabStats = useMemo(() => ({
    findings: findings.length,
    openFindings: openFindings.length,
    cars: allCars.length || linkedCarsFromFindings.length,
    openCars: openCars.length,
    evidence: evidenceCount,
  }), [allCars.length, evidenceCount, findings.length, linkedCarsFromFindings.length, openCars.length, openFindings.length]);

  const percentComplete = Math.max(0, Math.min(100, workflow?.percent_complete ?? 0));
  const nextTab = TABS[Math.min(TABS.length - 1, currentTabIndex + 1)];
  const currentGateMessage = stepGateMessage(activeTab);
  const nextActionTitle = currentGateMessage
    ? `Action required: ${tabLabels[activeTab]}`
    : currentTabIndex >= TABS.length - 1
      ? "Closeout review"
      : `Next: ${tabLabels[nextTab]}`;
  const tabComplete = (tab: WorkspaceTab): boolean => {
    const backendStage = workflowStageMap.get(tab);
    if (backendStage) return Boolean(backendStage.complete);
    if (tab === "war-room") return isWarRoomReady;
    if (tab === "checklist") return isChecklistReady;
    if (tab === "findings") return Boolean(audit?.actual_start || audit?.actual_end || findings.length || checklistItems.some((item) => item.response_status !== "PENDING"));
    if (tab === "cars") return isCarsReady;
    if (tab === "evidence") return evidenceCount > 0;
    if (tab === "report") return isReportReady;
    return audit?.status === "CLOSED";
  };
  const tabStepStatus = (tab: WorkspaceTab, index: number): "active" | "complete" | "locked" | "blocked" | "open" => {
    if (activeTab === tab && currentGateMessage) return "blocked";
    if (firstBlockingStepBefore(tab)) return "locked";
    if (activeTab === tab) return "active";
    if (tabComplete(tab) || index < currentTabIndex) return "complete";
    return "open";
  };
  const tabStatusText = (tab: WorkspaceTab, index: number): string => {
    const blocked = firstBlockingStepBefore(tab);
    if (blocked) return "Locked";
    if (activeTab === tab && currentGateMessage) return "Blocked";
    if (activeTab === tab) return "Active";
    if (tabComplete(tab) || index < currentTabIndex) return "Complete";
    const backendStage = workflowStageMap.get(tab);
    return backendStage?.metric || tabMetric(tab);
  };
  const tabMetric = (tab: WorkspaceTab) => {
    if (tab === "war-room") return isWarRoomReady ? "Ready" : "Schedule, team, and auditee required";
    if (tab === "checklist") return isChecklistReady ? "Checklist ready" : "Checklist pending";
    if (tab === "findings") return `${findings.length} finding${findings.length === 1 ? "" : "s"}`;
    if (tab === "cars") return openCars.length ? `${openCars.length} open CAR${openCars.length === 1 ? "" : "s"}` : "No open CARs";
    if (tab === "evidence") return `${evidenceCount} evidence item${evidenceCount === 1 ? "" : "s"}`;
    if (tab === "report") return isReportReady ? "Report ready" : "Report pending";
    return audit?.status === "CLOSED" ? "Closed" : "Closure gated";
  };
  const auditBrandHue = hueFromString(brand?.domain || brand?.company_name || auditeeDisplayName);

  const activeTabBadges: Array<{ label: string; value: string }> = useMemo(() => {
    switch (activeTab) {
      case "war-room":
        return [
          { label: "Assigned", value: `${assignedAuditors.length}/3` },
          { label: "Notices", value: audit?.upcoming_notice_sent_at || audit?.day_of_notice_sent_at ? "Sent" : "Pending" },
          { label: "Open actions", value: `${openFindings.length + openCars.length}` },
        ];
      case "checklist":
        return [
          { label: "File", value: audit?.checklist_file_ref ? "Uploaded" : selectedChecklistFile ? "Selected" : "Missing" },
          { label: "Items", value: `${checklistItems.length}` },
          { label: "Access", value: canEditChecklist ? "Editable" : "Read only" },
        ];
      case "findings":
        return [
          { label: "Total findings", value: `${findings.length}` },
          { label: "Open", value: `${openFindings.length}` },
          { label: "Linked CARs", value: `${linkedCarsFromFindings.length}` },
        ];
      case "cars":
        return [
          { label: "Total CARs", value: `${tabStats.cars}` },
          { label: "Open", value: `${openCars.length}` },
        ];
      case "evidence":
        return [
          { label: "Evidence files", value: `${evidenceCount}` },
          { label: "Checklist", value: audit?.checklist_file_ref ? "Included" : "None" },
          { label: "Report", value: audit?.report_file_ref ? "Included" : "None" },
        ];
      case "report":
        return [
          { label: "Report", value: audit?.report_file_ref ? "Uploaded" : "Pending" },
          { label: "Checklist", value: audit?.checklist_file_ref ? "Ready" : "Missing" },
        ];
      case "closeout":
        return [
          { label: "Open findings", value: `${openFindings.length}` },
          { label: "Open CARs", value: `${openCars.length}` },
          { label: "Report", value: audit?.report_file_ref ? "Ready" : "Missing" },
        ];
      default:
        return [];
    }
  }, [activeTab, assignedAuditors.length, audit?.checklist_file_ref, audit?.day_of_notice_sent_at, audit?.report_file_ref, audit?.upcoming_notice_sent_at, canEditChecklist, evidenceCount, findings.length, linkedCarsFromFindings.length, openCars.length, openFindings.length, tabStats.cars, checklistItems.length, selectedChecklistFile]);

  const renderTabContent = () => {
    if (!audit) return null;

    if (activeTab === "war-room") {
      return (
        <div className="audit-live-grid">
          <section className="audit-live-card audit-live-card--wide">
            <div className="audit-live-card__header">
              <div>
                <h3><Users size={16} /> Team and notices</h3>
                <p>Live coordination for auditors, auditee contact, and dispatch readiness.</p>
              </div>
              <span className="audit-soft-badge">{assignedAuditors.length ? "Operational" : "Awaiting lead assignment"}</span>
            </div>
            <div className="audit-team-roster audit-team-roster--workspace">
              {[
                { role: "Lead auditor", value: audit.lead_auditor_user_id, person: leadAuditor, nameHint: audit.lead_auditor_name, fallback: "Lead auditor not resolved" },
                { role: "Observer", value: audit.observer_auditor_user_id, person: observerAuditor, nameHint: audit.observer_auditor_name, fallback: "Observer not assigned" },
                { role: "Assistant", value: audit.assistant_auditor_user_id, person: assistantAuditor, nameHint: audit.assistant_auditor_name, fallback: "Assistant not assigned" },
                { role: "Auditee", value: audit.auditee || audit.auditee_email || audit.auditee_user_id, person: auditeeUser, nameHint: audit.auditee_user_name || audit.auditee || audit.auditee_email, fallback: "Auditee not set" },
              ].map((item) => (
                <div key={item.role} className="audit-team-roster__item">
                  <WorkspaceAvatar person={item.person} fallback={item.fallback || item.role} size="lg" />
                  <div>
                    <small>{item.role}</small>
                    <strong>{displayPersonName(item.value, item.person, item.fallback, item.nameHint)}</strong>
                  </div>
                </div>
              ))}
            </div>
            <div className="audit-inline-note">
              <Activity size={15} />
              Notices are sent through the existing backend dispatch and logged to portal notifications and email history.
            </div>
            <div className="qms-header__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => issueNotice.mutate()} disabled={issueNotice.isPending || !assignedAuditors.length}>
                <MailCheck size={14} /> {issueNotice.isPending ? "Sending…" : "Send notice now"}
              </button>
              <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/schedule`)}>
                <ArrowUpRight size={14} /> Open planner
              </button>
            </div>
            {!assignedAuditors.length ? <p className="text-danger">Assign at least a lead auditor before sending notices.</p> : null}
          </section>

          <section className="audit-live-card">
            <div className="audit-live-card__header">
              <div>
                <h3><PackageCheck size={16} /> Readiness</h3>
                <p>Compact closure signals for the active audit.</p>
              </div>
            </div>
            <div className="audit-mini-kpis">
              <div><strong>{openFindings.length}</strong><span>Open findings</span></div>
              <div><strong>{openCars.length}</strong><span>Open CARs</span></div>
              <div><strong>{audit.checklist_file_ref ? "Yes" : "No"}</strong><span>Checklist</span></div>
              <div><strong>{audit.report_file_ref ? "Yes" : "No"}</strong><span>Report</span></div>
            </div>
            <p className="text-muted">Closeout remains governed by backend rules: checklist and report present, CAR verification complete, and mandatory evidence accepted.</p>
            <div className="qms-header__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => exportPack.mutate()} disabled={exportPack.isPending}>
                <FolderKanban size={14} /> {exportPack.isPending ? "Packaging…" : "Export evidence pack"}
              </button>
              <button type="button" className="secondary-chip-btn" onClick={() => setTab("closeout")}>Go to closeout</button>
            </div>
          </section>
        </div>
      );
    }

    if (activeTab === "checklist") {
      const selectedIsPdf = isPdfChecklist(selectedChecklistFile?.name, selectedChecklistFile?.type);
      const selectedIsWord = isWordChecklist(selectedChecklistFile?.name, selectedChecklistFile?.type);
      const activePreviewName = selectedChecklistFile?.name || committedChecklistName;
      const activePreviewSource = selectedChecklistFile || (committedChecklistIsWord ? committedChecklistBlob : null);
      const checklistModeLabel = hasSourceChecklist ? "Source review" : hasPortalChecklist ? "Portal checklist" : "Checklist setup";

      const updateTextField = (item: QualityChecklistItemOut, field: "section" | "requirement_ref" | "prompt" | "objective_evidence", value: string) => {
        const current = (item[field] || "").trim();
        const next = value.trim();
        if (next === current) return;
        const patch = { [field]: next || null } as Partial<QualityChecklistItemOut>;
        updateChecklistItem.mutate({ item, patch });
      };

      const renderFileControls = (mode: "setup" | "toolbar") => (
        <div className={`audit-checklist-command audit-checklist-command--slim audit-checklist-command--${mode}`}>
          <div className="audit-checklist-toolbar__file">
            <span className="audit-file-icon"><FileText size={15} /></span>
            <div>
              <strong>{selectedChecklistFile ? selectedChecklistFile.name : hasCommittedChecklist ? committedChecklistName : "No controlled checklist selected"}</strong>
              <small>
                {selectedChecklistFile
                  ? `Selected · ${bytesLabel(selectedChecklistFile.size)} · preview before committing`
                  : hasCommittedChecklist
                    ? "Committed source document · overwrite only, never deleted"
                    : "Select PDF/DOC/DOCX or build checklist rows directly in the portal"}
              </small>
            </div>
          </div>
          <div className="audit-file-actions audit-file-actions--compact">
            <button
              type="button"
              className="secondary-chip-btn audit-file-action"
              disabled={!hasCommittedChecklist || committedChecklistLoading}
              onClick={() => openObjectUrl(committedChecklistUrl, committedChecklistLoading ? "Checklist is still loading." : "No committed checklist is available.")}
            >
              {committedChecklistIsPdf ? <Eye size={14} /> : <Download size={14} />} {committedChecklistIsPdf ? "Open" : "Download"}
            </button>
            <label className={`secondary-chip-btn audit-file-action audit-file-picker${!canEditChecklist ? " disabled" : ""}`}>
              {selectedChecklistFile ? "Change" : hasCommittedChecklist ? "Replace" : "Upload checklist"}
              <input
                type="file"
                accept={CHECKLIST_FILE_ACCEPT}
                disabled={!canEditChecklist || uploading || commitChecklistUpload.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  setSelectedChecklistFile(file);
                  setUploadError(null);
                  e.currentTarget.value = "";
                }}
              />
            </label>
            <button
              type="button"
              className="secondary-chip-btn audit-file-action audit-file-action--primary"
              disabled={!selectedChecklistFile || !canEditChecklist || commitChecklistUpload.isPending}
              onClick={() => commitChecklistUpload.mutate()}
              title="Overwrite the controlled checklist file. Existing checklist records and notes are kept."
            >
              <Save size={14} /> {commitChecklistUpload.isPending ? "Saving…" : hasCommittedChecklist ? "Commit overwrite" : "Commit selected"}
            </button>
          </div>
        </div>
      );

      const renderChecklistBuilder = (variant: "setup" | "full" | "response") => (
        <section className={`audit-checklist-builder audit-checklist-builder--${variant}`} aria-label="Portal checklist builder">
          <div className="audit-pane-title audit-pane-title--builder">
            <div>
              <small>{variant === "response" ? "Fieldwork notes" : "Manual checklist builder"}</small>
              <strong>{variant === "response" ? "Checklist responses" : "Build checklist rows in the portal"}</strong>
            </div>
            <span>{checklistItems.length} item{checklistItems.length === 1 ? "" : "s"}</span>
          </div>
          <p className="audit-compact-hint">
            {variant === "response"
              ? "Capture objective evidence and response status while reviewing the controlled source document."
              : "Use this full-width builder when the checklist is created directly in the portal instead of from an uploaded source file."}
          </p>

          <div className="audit-checklist-add-row audit-checklist-add-row--fieldwork">
            <input
              ref={manualChecklistFirstInputRef}
              value={checklistDraft.section}
              onChange={(e) => setChecklistDraft((prev) => ({ ...prev, section: e.target.value }))}
              placeholder="Section"
              disabled={!canEditChecklist || createChecklistItem.isPending}
            />
            <input
              value={checklistDraft.requirement_ref}
              onChange={(e) => setChecklistDraft((prev) => ({ ...prev, requirement_ref: e.target.value }))}
              placeholder="Requirement / ref"
              disabled={!canEditChecklist || createChecklistItem.isPending}
            />
            <textarea
              value={checklistDraft.prompt}
              onChange={(e) => setChecklistDraft((prev) => ({ ...prev, prompt: e.target.value }))}
              placeholder="Checklist question / audit prompt"
              disabled={!canEditChecklist || createChecklistItem.isPending}
            />
            <textarea
              value={checklistDraft.objective_evidence}
              onChange={(e) => setChecklistDraft((prev) => ({ ...prev, objective_evidence: e.target.value }))}
              placeholder="Objective evidence / response note"
              disabled={!canEditChecklist || createChecklistItem.isPending}
            />
            <button type="button" className="secondary-chip-btn audit-step-nav--primary" disabled={!canEditChecklist || createChecklistItem.isPending || !checklistDraft.prompt.trim()} onClick={() => createChecklistItem.mutate()}>
              <Plus size={14} /> Add row
            </button>
          </div>

          <div className="audit-checklist-builder-grid" role="table" aria-label="Manual checklist rows">
            <div className="audit-checklist-builder-grid__head" role="row">
              <span>Section</span>
              <span>Requirement / Ref</span>
              <span>Checklist question / audit prompt</span>
              <span>Objective evidence / response note</span>
              <span>Status</span>
              <span>Actions</span>
            </div>
            {checklistItems.length ? (
              checklistItems.map((item) => (
                <article className="audit-checklist-row audit-checklist-row--field-note" key={item.id} role="row">
                  <label className="audit-builder-cell">
                    <span>Section</span>
                    <input
                      defaultValue={item.section || ""}
                      disabled={!canEditChecklist || savingChecklistItemId === item.id}
                      onBlur={(e) => updateTextField(item, "section", e.currentTarget.value)}
                    />
                  </label>
                  <label className="audit-builder-cell">
                    <span>Requirement / Ref</span>
                    <input
                      defaultValue={item.requirement_ref || item.checklist_ref || ""}
                      disabled={!canEditChecklist || savingChecklistItemId === item.id}
                      onBlur={(e) => updateTextField(item, "requirement_ref", e.currentTarget.value)}
                    />
                  </label>
                  <label className="audit-builder-cell audit-builder-cell--prompt">
                    <span>Checklist question / audit prompt</span>
                    <textarea
                      defaultValue={item.prompt || ""}
                      disabled={!canEditChecklist || savingChecklistItemId === item.id}
                      onBlur={(e) => updateTextField(item, "prompt", e.currentTarget.value)}
                    />
                  </label>
                  <label className="audit-builder-cell audit-builder-cell--evidence">
                    <span>Objective evidence / response note</span>
                    <textarea
                      defaultValue={item.objective_evidence || ""}
                      placeholder="Evidence, response note, record reference, interview detail, or photo ID"
                      disabled={!canEditChecklist || savingChecklistItemId === item.id}
                      onBlur={(e) => updateTextField(item, "objective_evidence", e.currentTarget.value)}
                    />
                  </label>
                  <label className="audit-builder-cell audit-builder-cell--status">
                    <span>Status</span>
                    <select
                      value={item.response_status || "PENDING"}
                      disabled={!canEditChecklist || savingChecklistItemId === item.id}
                      onChange={(e) => updateChecklistItem.mutate({ item, patch: { response_status: e.target.value } })}
                    >
                      <option value="PENDING">Pending</option>
                      <option value="COMPLIANT">Compliant</option>
                      <option value="NON_CONFORMING">NCR</option>
                      <option value="OBSERVATION">Observation</option>
                      <option value="NOT_APPLICABLE">N/A</option>
                    </select>
                  </label>
                  <div className="audit-builder-cell audit-builder-cell--actions">
                    <span>Actions</span>
                    <strong>{savingChecklistItemId === item.id ? "Saving…" : checklistItemStatusLabel(item.response_status)}</strong>
                  </div>
                </article>
              ))
            ) : (
              <div className="audit-empty-state audit-empty-state--compact">
                <CircleDashed size={18} />
                <div>
                  <strong>No portal checklist rows yet</strong>
                  <p>Add the first row above. The source document viewer will stay hidden until a checklist file is selected or committed.</p>
                </div>
              </div>
            )}
          </div>
        </section>
      );

      const renderDocumentPane = () => (
        <section className="audit-document-pane">
          <div className="audit-pane-title">
            <div>
              <small>Source document</small>
              <strong>{activePreviewName}</strong>
            </div>
            <span>{selectedChecklistFile ? "Selected file" : "Committed file"}</span>
          </div>
          <div className="audit-checklist-preview audit-checklist-preview--document" aria-label="Checklist preview">
            {selectedChecklistFile && selectedIsPdf && checklistPreviewUrl ? (
              <iframe title="Selected checklist preview" src={checklistPreviewUrl} />
            ) : selectedChecklistFile && selectedIsWord ? (
              <DocxInlinePreview source={selectedChecklistFile} fileName={selectedChecklistFile.name} />
            ) : selectedChecklistFile ? (
              <div className="audit-empty-state audit-empty-state--compact">
                <FileText size={18} />
                <div>
                  <strong>{selectedChecklistFile.name}</strong>
                  <p>This file type cannot be rendered inline. Commit it as the controlled checklist and continue in the field notes panel.</p>
                </div>
              </div>
            ) : committedChecklistLoading ? (
              <div className="audit-empty-state audit-empty-state--compact">
                <CircleDashed size={18} />
                <div>
                  <strong>Loading controlled checklist</strong>
                  <p>The portal is loading the committed file through your authenticated session.</p>
                </div>
              </div>
            ) : committedChecklistError ? (
              <div className="audit-empty-state audit-empty-state--compact">
                <ShieldAlert size={18} />
                <div>
                  <strong>Checklist preview blocked</strong>
                  <p>{committedChecklistError}</p>
                </div>
              </div>
            ) : committedChecklistIsPdf && committedChecklistUrl ? (
              <iframe title="Committed checklist preview" src={committedChecklistUrl} />
            ) : committedChecklistIsWord && activePreviewSource ? (
              <DocxInlinePreview source={activePreviewSource} fileName={activePreviewName} />
            ) : (
              <div className="audit-empty-state audit-empty-state--compact">
                <FileText size={18} />
                <div>
                  <strong>Checklist file is attached</strong>
                  <p>Download the controlled source if needed. Capture fieldwork responses in the notes panel.</p>
                </div>
              </div>
            )}
          </div>
        </section>
      );

      return (
        <div className="audit-checklist-fieldwork">
          <section className="audit-live-card audit-live-card--workspace audit-checklist-fieldwork__main">
            <div className="audit-live-card__header audit-live-card__header--fieldwork">
              <div>
                <h3><ClipboardList size={16} /> Fieldwork checklist</h3>
                <p>{checklistModeLabel}: upload a controlled checklist or work directly in portal checklist rows without wasting space on an empty viewer.</p>
              </div>
              <span className="audit-soft-badge">{hasSourceChecklist ? "Controlled source active" : hasPortalChecklist ? "Manual checklist active" : "Prepare checklist"}</span>
            </div>

            {isChecklistEmpty ? (
              <section className="audit-checklist-setup" aria-label="Checklist setup">
                <div className="audit-checklist-setup__intro">
                  <small>Step 2 · Checklist setup</small>
                  <h3>No checklist has been added yet.</h3>
                  <p>Upload a controlled PDF/DOC/DOCX checklist, or build checklist rows directly in the portal.</p>
                </div>
                <div className="audit-checklist-setup__actions">
                  <label className={`secondary-chip-btn audit-file-action audit-file-picker${!canEditChecklist ? " disabled" : ""}`}>
                    Upload checklist
                    <input
                      type="file"
                      accept={CHECKLIST_FILE_ACCEPT}
                      disabled={!canEditChecklist || uploading || commitChecklistUpload.isPending}
                      onChange={(e) => {
                        const file = e.target.files?.[0] ?? null;
                        setSelectedChecklistFile(file);
                        setUploadError(null);
                        e.currentTarget.value = "";
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary-chip-btn audit-file-action audit-file-action--primary"
                    disabled={!selectedChecklistFile || !canEditChecklist || commitChecklistUpload.isPending}
                    onClick={() => commitChecklistUpload.mutate()}
                  >
                    <Save size={14} /> {commitChecklistUpload.isPending ? "Saving…" : "Commit selected checklist"}
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={() => manualChecklistFirstInputRef.current?.focus()} disabled={!canEditChecklist}>
                    <Plus size={14} /> Start manual checklist
                  </button>
                </div>
                {!canEditChecklist ? <p className="text-muted audit-compact-hint">Read-only for users who are not assigned to this audit.</p> : null}
                {uploadError ? <p className="text-danger audit-gate-message">{uploadError}</p> : null}
                {renderChecklistBuilder("setup")}
              </section>
            ) : hasSourceChecklist ? (
              <>
                {renderFileControls("toolbar")}
                {!canEditChecklist ? <p className="text-muted audit-compact-hint">Read-only for users who are not assigned to this audit.</p> : null}
                {uploadError ? <p className="text-danger audit-gate-message">{uploadError}</p> : null}
                <div className="audit-checklist-review-layout" aria-label="Checklist source review layout">
                  {renderDocumentPane()}
                  <section className="audit-response-pane">
                    {renderChecklistBuilder("response")}
                  </section>
                </div>
              </>
            ) : (
              <>
                {renderFileControls("toolbar")}
                {!canEditChecklist ? <p className="text-muted audit-compact-hint">Read-only for users who are not assigned to this audit.</p> : null}
                {uploadError ? <p className="text-danger audit-gate-message">{uploadError}</p> : null}
                {renderChecklistBuilder("full")}
              </>
            )}
          </section>
        </div>
      );
    }

    if (activeTab === "findings") {
      const selectedLevel = findingLevelOptions.find((item) => item.value === findingForm.level) ?? findingLevelOptions[2];
      const selectedLevelClass = `audit-finding-level-shell--${selectedLevel.value.toLowerCase().replace("_", "-")}`;
      const nextFindingRef = buildNextFindingReference(audit.audit_ref, findings);
      return (
        <div className={`audit-findings-workspace${findingsLockedByReport ? " is-report-locked" : ""}`}>
          {findingsLockedByReport ? (
            <section className="audit-live-card audit-live-card--workspace audit-report-lock-panel" aria-label="Findings locked after report issue">
              <div className="audit-report-lock-panel__icon"><Lock size={18} /></div>
              <div>
                <small>Report issued</small>
                <strong>Findings are locked</strong>
                <p>The issued audit report now controls the record. Existing findings remain visible below; new findings and edits are disabled.</p>
              </div>
              <button type="button" className="secondary-chip-btn" onClick={() => setTab("report")}>Open report</button>
            </section>
          ) : (
            <section className={`audit-live-card audit-live-card--workspace audit-finding-level-shell ${selectedLevelClass}`}>
              <div className="audit-live-card__header">
                <div>
                  <h3><FileText size={16} /> Record fieldwork finding</h3>
                  <p>Capture the finding exactly as observed. The proposed reference is visible before saving.</p>
                </div>
                <span className="audit-soft-badge audit-soft-badge--reference">{nextFindingRef}</span>
              </div>

              <div className="audit-finding-level-banner">
                <div>
                  <small>Selected classification</small>
                  <strong>{selectedLevel.label}</strong>
                </div>
                <span>{selectedLevel.note}</span>
              </div>

              <div className="audit-finding-form-grid">
                <label className="qms-field">
                  Finding reference
                  <input value={nextFindingRef} readOnly />
                </label>
                <label className="qms-field">
                  Classification
                  <select
                    value={findingForm.level}
                    onChange={(e) => setFindingForm((prev) => ({ ...prev, level: e.target.value as FindingLevelValue }))}
                  >
                    {findingLevelOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
                <label className="qms-field">
                  Requirement / clause / checklist ref
                  <input value={findingForm.requirement_ref} onChange={(e) => setFindingForm((prev) => ({ ...prev, requirement_ref: e.target.value }))} placeholder="e.g. MPM 3.4 / audit checklist item" />
                </label>
                <label className="qms-field">
                  Target close date
                  <input type="date" value={findingForm.target_close_date} disabled={selectedLevel.value === "LEVEL_4"} onChange={(e) => setFindingForm((prev) => ({ ...prev, target_close_date: e.target.value }))} />
                </label>
              </div>

              <label className="qms-field">
                Finding / observation statement
                <textarea
                  className="audit-large-textarea"
                  value={findingForm.description}
                  onChange={(e) => setFindingForm((prev) => ({ ...prev, description: e.target.value }))}
                  placeholder="Paste or type the finding exactly as observed."
                />
              </label>

              <section className="audit-evidence-editor" aria-label="Objective evidence editor">
                <div className="audit-evidence-editor__header">
                  <div>
                    <strong>Objective evidence</strong>
                    <span>Use structured notes, paste interview details, and attach supporting files before recording the finding.</span>
                  </div>
                  <div className="audit-evidence-editor__tools" aria-label="Objective evidence formatting tools">
                    <button type="button" onClick={() => wrapObjectiveEvidenceSelection("**", "**", "evidence text")} title="Bold selected evidence"><Bold size={14} /></button>
                    <button type="button" onClick={() => wrapObjectiveEvidenceSelection("_", "_", "evidence text")} title="Italic selected evidence"><Italic size={14} /></button>
                    <button type="button" onClick={() => insertObjectiveEvidenceText("\n- ")} title="Add bullet"><List size={14} /></button>
                    <button type="button" onClick={() => insertObjectiveEvidenceText("\n1. ")} title="Add numbered line"><ListOrdered size={14} /></button>
                    <button type="button" onClick={() => insertObjectiveEvidenceText(`\n- Date/time checked: ${new Date().toLocaleString()}\n- Record/source: `)} title="Insert date and source line"><CalendarClock size={14} /></button>
                  </div>
                </div>
                <textarea
                  ref={findingEvidenceTextareaRef}
                  className="audit-large-textarea audit-large-textarea--evidence"
                  value={findingForm.objective_evidence}
                  onChange={(e) => setFindingForm((prev) => ({ ...prev, objective_evidence: e.target.value }))}
                  placeholder="Records checked, aircraft/component refs, photos, staff interviewed, dates, checklist refs, etc."
                />
                <div className="audit-evidence-attachments">
                  <input
                    ref={findingEvidenceInputRef}
                    type="file"
                    accept={FINDING_EVIDENCE_FILE_ACCEPT}
                    multiple
                    onChange={(event) => addFindingEvidenceFiles(event.currentTarget.files)}
                  />
                  <button type="button" className="secondary-chip-btn" onClick={() => findingEvidenceInputRef.current?.click()}>
                    <UploadCloud size={14} /> Attach evidence
                  </button>
                  <span className="audit-compact-hint">PDF, image, Word, Excel, CSV, or text. Max 15MB each.</span>
                </div>
                {findingEvidenceFiles.length ? (
                  <div className="audit-evidence-file-list" aria-label="Selected finding evidence files">
                    {findingEvidenceFiles.map((file) => (
                      <article key={`${file.name}-${file.size}-${file.lastModified}`}>
                        <Paperclip size={14} />
                        <span>{file.name}</span>
                        <small>{bytesLabel(file.size)}</small>
                        <button type="button" onClick={() => setFindingEvidenceFiles((prev) => prev.filter((item) => item !== file))} aria-label={`Remove ${file.name}`}>
                          <Trash2 size={13} />
                        </button>
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>

              <div className="audit-finding-form-footer">
                <label className="audit-checkbox-line">
                  <input type="checkbox" checked={findingForm.safety_sensitive} onChange={(e) => setFindingForm((prev) => ({ ...prev, safety_sensitive: e.target.checked }))} />
                  Safety sensitive
                </label>
                <span className="text-muted">{findingEvidenceFiles.length ? `${findingEvidenceFiles.length} evidence file${findingEvidenceFiles.length === 1 ? "" : "s"} will upload after save.` : "Evidence files are optional for observations, but recommended for NCRs."}</span>
                <button type="button" className="secondary-chip-btn audit-step-nav--primary" disabled={createFinding.isPending || !findingForm.description.trim()} onClick={() => createFinding.mutate()}>
                  <Save size={14} /> {createFinding.isPending ? "Saving…" : "Record finding"}
                </button>
              </div>
            </section>
          )}

          <section className="audit-live-card audit-live-card--workspace audit-findings-register-card">
            <div className="audit-live-card__header">
              <div>
                <h3>Findings register</h3>
                <p>Saved findings remain linked to this audit workspace in real time.</p>
              </div>
              <div className="audit-mini-kpis audit-mini-kpis--inline">
                <div><strong>{findings.length}</strong><span>Total</span></div>
                <div><strong>{openFindings.length}</strong><span>Open</span></div>
                <div><strong>{linkedCarsFromFindings.length}</strong><span>CARs</span></div>
              </div>
            </div>
            {findings.length ? (
              <div className="audit-list-stack audit-list-stack--dense">
                {findings.slice(0, 8).map((row) => {
                  const savedAttachments = findingAttachmentMap.get(row.finding.id) ?? [];
                  const canModifyThisFinding = Boolean(canOwnAuditFindings) && !findingsLockedByReport;
                  const missingMandatoryCar = row.finding.level !== "LEVEL_4" && row.linked_cars.length === 0;
                  const isEditingThisFinding = editingFindingId === row.finding.id;
                  return (
                    <article key={row.finding.id} className="audit-list-item audit-finding-register-row">
                      <div className="audit-finding-register-main">
                        <div className="audit-finding-register-titleline">
                          <strong>{row.finding.finding_ref || "Finding"}</strong>
                          <span className={`audit-soft-badge audit-finding-level-pill audit-finding-level-pill--${(row.finding.level || "LEVEL_3").toLowerCase().replace("_", "-")}`}>
                            {row.finding.level === "LEVEL_4" ? "Observation" : row.finding.level || row.finding.severity || "Open"}
                          </span>
                        </div>
                        {isEditingThisFinding ? (
                          <div className="audit-finding-edit-grid">
                            <label>Level
                              <select value={findingEditForm.level} onChange={(e) => setFindingEditForm((prev) => ({ ...prev, level: e.target.value as FindingLevelValue }))}>
                                {findingLevelOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                              </select>
                            </label>
                            <label>Requirement / reference
                              <input value={findingEditForm.requirement_ref} onChange={(e) => setFindingEditForm((prev) => ({ ...prev, requirement_ref: e.target.value }))} />
                            </label>
                            <label>Target close date
                              <input type="date" value={findingEditForm.target_close_date} disabled={findingEditForm.level === "LEVEL_4"} onChange={(e) => setFindingEditForm((prev) => ({ ...prev, target_close_date: e.target.value }))} />
                            </label>
                            <label className="audit-finding-edit-grid--wide">Finding statement
                              <textarea value={findingEditForm.description} onChange={(e) => setFindingEditForm((prev) => ({ ...prev, description: e.target.value }))} />
                            </label>
                            <label className="audit-finding-edit-grid--wide">Objective evidence
                              <textarea value={findingEditForm.objective_evidence} onChange={(e) => setFindingEditForm((prev) => ({ ...prev, objective_evidence: e.target.value }))} />
                            </label>
                            <div className="audit-row-actions audit-finding-edit-grid--wide">
                              <button type="button" className="secondary-chip-btn audit-step-nav--primary" disabled={updateFindingMutation.isPending || !findingEditForm.description.trim()} onClick={() => updateFindingMutation.mutate(row.finding)}>Save finding</button>
                              <button type="button" className="secondary-chip-btn" onClick={() => setEditingFindingId(null)}>Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <p>{row.finding.description || "Finding details are available in the linked register."}</p>
                            {row.finding.objective_evidence ? <small>{row.finding.objective_evidence}</small> : null}
                            {savedAttachments.length ? (
                              <div className="audit-saved-evidence-list">
                                {savedAttachments.slice(0, 3).map((attachment) => (
                                  <a key={attachment.id} href={`${getApiBaseUrl()}${attachment.download_url}`} target="_blank" rel="noreferrer">
                                    <Paperclip size={12} /> {attachment.filename}
                                  </a>
                                ))}
                                {savedAttachments.length > 3 ? <span>+{savedAttachments.length - 3} more</span> : null}
                              </div>
                            ) : null}
                          </>
                        )}
                      </div>
                      {!isEditingThisFinding ? (
                        <div className="audit-row-actions audit-row-actions--stacked">
                          {missingMandatoryCar ? (
                            <button type="button" className="secondary-chip-btn audit-step-nav--primary" disabled={!canOwnAuditFindings || issueCarMutation.isPending} onClick={() => issueCarMutation.mutate(row)}>
                              Issue CAR
                            </button>
                          ) : <span className="audit-soft-badge">{row.linked_cars.length ? `${row.linked_cars.length} CAR linked` : "No CAR required"}</span>}
                          {canModifyThisFinding ? <button type="button" className="secondary-chip-btn" onClick={() => beginEditFinding(row.finding)}>Edit</button> : null}
                          {canModifyThisFinding ? <button type="button" className="secondary-chip-btn" onClick={() => window.confirm("Delete this finding and any unlocked linked CAR?") && deleteFindingMutation.mutate(row.finding)}>Delete</button> : null}
                          {canFlagForReview && !canModifyThisFinding ? <button type="button" className="secondary-chip-btn" onClick={() => flagFindingMutation.mutate(row.finding)}>Flag review</button> : null}
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="audit-empty-state">
                <CircleDashed size={18} />
                <div>
                  <strong>No findings yet</strong>
                  <p>{findingsLockedByReport ? "The issued report has locked new findings for this audit." : "Use the form above to record the first fieldwork finding or observation."}</p>
                </div>
              </div>
            )}
          </section>
        </div>
      );
    }

    if (activeTab === "cars") {
      const carRows = allCars.length ? allCars : linkedCarsFromFindings;
      const pendingDeferrals = (carExtensionRequestsQuery.data ?? []).filter((request) => request.status === "PENDING");
      const escalatedCars = carRows.filter((car) => car.status === "ESCALATED");
      const pendingReviewCars = carRows.filter((car) => car.status === "PENDING_VERIFICATION" || car.root_cause_status === "SUBMITTED" || car.capa_status === "SUBMITTED" || Boolean(car.submitted_at));
      const submittedResponses = carResponsesQuery.data ?? [];
      return (
        <div className={`audit-car-workbench ${carChatCollapsed ? "is-chat-collapsed" : ""}`}>
          <aside className="audit-car-chat" aria-label="CAR collaboration chat">
            {carChatCollapsed ? (
              <button type="button" className="audit-car-chat__restore" onClick={() => setCarChatCollapsed(false)} aria-label="Open CAR collaboration chat">
                <MessageSquare size={18} />
                <span>Chat</span>
              </button>
            ) : (
              <>
                <div className="audit-car-chat__header">
                  <div>
                    <strong>CAR collaboration</strong>
                    <small>{selectedChatCar?.car_number || "No CAR selected"}</small>
                  </div>
                  <button type="button" className="secondary-chip-btn" onClick={() => setCarChatCollapsed(true)} aria-label="Minimise CAR chat">
                    <ChevronLeft size={14} />
                  </button>
                </div>
                <div className="audit-car-chat__list">
                  {(allCars.length ? allCars : linkedCarsFromFindings).map((car) => (
                    <button key={car.id} type="button" className={selectedChatCar?.id === car.id ? "is-active" : ""} onClick={() => setSelectedChatCarId(car.id)}>
                      <strong>{car.car_number}</strong><span>{car.status}</span>
                    </button>
                  ))}
                </div>
                <div className="audit-car-chat__messages">
                  {(carActionsQuery.data ?? []).slice().reverse().map((action) => {
                    const bubbleClass = chatActionClass(action, currentUser?.id);
                    const actionLabel = String(action.action_type || "COMMENT").replace(/_/g, " ").toLowerCase();
                    return (
                      <div key={action.id} className={`audit-chat-bubble ${bubbleClass}`}>
                        <div className="audit-chat-bubble__meta">
                          <strong>{chatActorLabel(action, currentUser?.id)}</strong>
                          {bubbleClass === "is-system" ? <span>{actionLabel}</span> : action.actor_role ? <span>{action.actor_role}</span> : null}
                        </div>
                        <p>{action.message}</p>
                        <small>
                          <time>{dateTimeFmt(action.created_at)}</time>
                          {bubbleClass === "is-own" ? (() => {
                            const delivery = chatDeliveryMeta(action.delivery_status);
                            return (
                              <em className={`audit-chat-delivery ${delivery.className}`} title={delivery.label}>
                                {delivery.icon === "clock" ? <CircleDashed size={12} /> : delivery.icon === "check" ? <Check size={12} /> : <CheckCheck size={12} />}
                                {delivery.label}
                              </em>
                            );
                          })() : null}
                        </small>
                      </div>
                    );
                  })}
                  {!(carActionsQuery.data ?? []).length ? <p className="text-muted">No comments yet. Use this thread to coordinate corrective action evidence and access requests.</p> : null}
                  <div ref={chatMessagesEndRef} />
                </div>
                <div className="audit-car-chat__composer">
                  <textarea value={carChatDraft} maxLength={500} onChange={(event) => setCarChatDraft(event.target.value)} placeholder="Write a short CAR update…" />
                  <button type="button" className="secondary-chip-btn audit-step-nav--primary" disabled={!carChatDraft.trim() || sendCarChatMutation.isPending} onClick={() => sendCarChatMutation.mutate(carChatDraft)}><Send size={14} /> Send</button>
                </div>
              </>
            )}
          </aside>
          <section className="audit-live-card audit-live-card--workspace audit-car-board">
            <div className="audit-live-card__header">
              <div>
                <h3><ShieldAlert size={16} /> CAR follow-up workbench</h3>
                <p>Review auditee submissions, evidence, deferral requests, escalation state, and closeout readiness for this audit.</p>
              </div>
            </div>
            <div className="audit-mini-kpis">
              <div><strong>{carRows.length}</strong><span>Total CARs</span></div>
              <div><strong>{openCars.length}</strong><span>Open</span></div>
              <div><strong>{pendingReviewCars.length}</strong><span>Pending review</span></div>
              <div><strong>{pendingDeferrals.length}</strong><span>Deferrals</span></div>
              <div><strong>{escalatedCars.length}</strong><span>Escalated</span></div>
            </div>
            {carRows.length ? (
              <div className="audit-car-columns">
                {carRows.map((car) => {
                  const isEscalated = car.status === "ESCALATED";
                  const isClosedOrCancelled = car.status === "CLOSED" || car.status === "CANCELLED";
                  const deferrals = (carExtensionRequestsQuery.data ?? []).filter((request) => request.car_id === car.id);
                  const pendingDeferral = deferrals.find((request) => request.status === "PENDING");
                  const canReviewCar = canOwnAuditFindings && !isEscalated && !isClosedOrCancelled;
                  return (
                    <article key={car.id} className={`audit-car-card ${isEscalated ? "is-escalated" : ""}`}>
                      <div className="audit-car-card__header">
                        <div>
                          <strong>{car.car_number}</strong>
                          <p>{car.title || car.summary || car.status}</p>
                        </div>
                        <span className={`audit-soft-badge audit-car-status-pill audit-car-status-pill--${String(car.status).toLowerCase().replace(/_/g, "-")}`}>{car.status}</span>
                      </div>
                      <div className="audit-car-card__meta">
                        <span>Due: {dateFmt(car.due_date || car.target_closure_date)}</span>
                        <span>Root cause: {car.root_cause_status || "PENDING"}</span>
                        <span>CAPA: {car.capa_status || "PENDING"}</span>
                        <span>Evidence: {car.evidence_verified_at ? "Verified" : car.evidence_received_at || car.evidence_ref ? "Received" : car.evidence_required ? "Required" : "Optional"}</span>
                      </div>
                      {pendingDeferral ? (
                        <div className="audit-car-deferral-box">
                          <strong>Deferral request</strong>
                          <p>New due date: {dateFmt(pendingDeferral.requested_due_date)} · {pendingDeferral.reason}</p>
                          <button type="button" className="secondary-chip-btn" disabled={!canReviewCar || forwardDeferralMutation.isPending} onClick={() => forwardDeferralMutation.mutate({ carId: car.id, extensionId: pendingDeferral.id })}>
                            Forward to QM
                          </button>
                        </div>
                      ) : null}
                      {submittedResponses.filter((response) => response.car_id === car.id && response.is_latest !== false).slice(0, 1).map((response) => (
                        <div key={response.id} className="audit-car-response-snapshot">
                          <strong>Submitted response</strong>
                          <p><b>Root cause:</b> {response.root_cause || "Not stated"}</p>
                          <p><b>CAPA:</b> {response.corrective_action || "Not stated"}</p>
                          <small>Submitted {dateTimeFmt(response.submitted_at)}{response.review_opened_at ? ` · opened ${dateTimeFmt(response.review_opened_at)}` : " · not opened yet"}</small>
                        </div>
                      ))}
                      {isEscalated ? (
                        <div className="audit-car-locked-note">Escalated to Accountable Manager. This item is view-only from the audit workspace.</div>
                      ) : null}
                      {car.status === "CLOSED" ? (
                        <div className="audit-car-locked-note">Closed. The linked finding and CAR are read-only.</div>
                      ) : null}
                      <div className="audit-row-actions audit-row-actions--wrap">
                        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/cars/${car.id}/overview`)}>
                          <ArrowUpRight size={13} /> Open CAR
                        </button>
                        <button type="button" className="secondary-chip-btn" disabled={requestCarAccessMutation.isPending || isEscalated || isClosedOrCancelled} onClick={() => requestCarAccessMutation.mutate(car.id)}>
                          <MessageSquare size={13} /> Request access
                        </button>
                        <button type="button" className="secondary-chip-btn" disabled={!canReviewCar || reviewCarMutation.isPending || !car.submitted_at} onClick={() => reviewCarMutation.mutate({ carId: car.id, decision: "accept" })}>
                          Accept
                        </button>
                        <button type="button" className="secondary-chip-btn" disabled={!canReviewCar || reviewCarMutation.isPending || !car.submitted_at} onClick={() => reviewCarMutation.mutate({ carId: car.id, decision: "needsEvidence" })}>
                          Needs evidence
                        </button>
                        <button type="button" className="secondary-chip-btn" disabled={!canReviewCar || reviewCarMutation.isPending || !car.submitted_at} onClick={() => reviewCarMutation.mutate({ carId: car.id, decision: "reject" })}>
                          Reject
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="audit-empty-state">
                <CircleDashed size={18} />
                <div>
                  <strong>No CARs linked</strong>
                  <p>Level 1–3 findings now auto-issue CARs. Use Issue CAR in Findings for any older migrated finding without one.</p>
                </div>
              </div>
            )}
          </section>
          <aside className="audit-car-help-rail" aria-label="CAR controls help">
            <button type="button" className="audit-car-help-trigger" onClick={() => setCarRulesOpen((value) => !value)} aria-expanded={carRulesOpen} aria-label="Show CAR control rules">
              <HelpCircle size={18} />
            </button>
            {carRulesOpen ? (
              <div className="audit-car-rules-popover">
                <div>
                  <strong>CAR control rules</strong>
                  <button type="button" className="audit-icon-action" onClick={() => setCarRulesOpen(false)} aria-label="Close CAR control rules"><X size={14} /></button>
                </div>
                <ul>
                  <li>Lead auditor controls CAR review and closeout.</li>
                  <li>Escalated CARs are view-only outside admin/QM controls.</li>
                  <li>Evidence must be accepted before closure where required.</li>
                </ul>
              </div>
            ) : null}
          </aside>
        </div>
      );
    }

    if (activeTab === "evidence") {
      return (
        <div className="audit-live-grid">
          <section className="audit-live-card audit-live-card--wide">
            <div className="audit-live-card__header">
              <div>
                <h3><FolderKanban size={16} /> Evidence inventory</h3>
                <p>Consolidated file presence for this audit scope and linked CAR evidence.</p>
              </div>
            </div>
            <div className="audit-mini-kpis">
              <div><strong>{evidenceCount}</strong><span>Total files</span></div>
              <div><strong>{(attachments.data ?? []).length}</strong><span>CAR attachments</span></div>
              <div><strong>{audit.checklist_file_ref ? 1 : 0}</strong><span>Checklist files</span></div>
              <div><strong>{audit.report_file_ref ? 1 : 0}</strong><span>Report files</span></div>
            </div>
            <p><strong>Audit scope:</strong> {`${audit.audit_ref} — ${audit.title}`}</p>
          </section>
          <section className="audit-live-card">
            <button type="button" className="secondary-chip-btn" onClick={() => exportPack.mutate()} disabled={exportPack.isPending}>
              <FolderKanban size={14} /> {exportPack.isPending ? "Packaging…" : "Export evidence pack"}
            </button>
          </section>
        </div>
      );
    }

    if (activeTab === "report") {
      return (
        <div className="audit-live-grid">
          <section className="audit-live-card audit-live-card--wide">
            <div className="audit-live-card__header">
              <div>
                <h3><FileText size={16} /> Issued report</h3>
                <p>Keep the signed or approved audit report attached to the audit record.</p>
              </div>
              <div className="audit-report-share-actions">
                <span className="audit-soft-badge">{audit.report_file_ref ? "Uploaded" : "Pending"}</span>
                <button type="button" className="secondary-chip-btn" disabled={!audit.report_file_ref || shareReportMutation.isPending} onClick={() => setPendingReportShareGroups(["accountable_manager"])}><Share2 size={14} /> Accountable Manager</button>
                <button type="button" className="secondary-chip-btn" disabled={!audit.report_file_ref || shareReportMutation.isPending} onClick={() => setPendingReportShareGroups(["quality_manager"])}><Share2 size={14} /> Quality Manager</button>
                <button type="button" className="secondary-chip-btn" disabled={!audit.report_file_ref || shareReportMutation.isPending} onClick={() => setPendingReportShareGroups(["department_heads", "audited_department", "shop_personnel", "facility_personnel"])}><Share2 size={14} /> Department / shop</button>
              </div>
            </div>
            {reportShareNotice ? <div className="audit-inline-note"><CheckCircle2 size={15} /> {reportShareNotice}</div> : null}
            <div className="qms-header__actions" style={{ marginBottom: 8 }}>
              {audit.report_file_ref ? <button type="button" className="secondary-chip-btn" onClick={openReportWithAuth}>Open report</button> : null}
              <label className="secondary-chip-btn">
                Upload report
                <input
                  type="file"
                  style={{ display: "none" }}
                  accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  disabled={!canEditChecklist || uploading}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file || !audit.id) return;
                    setUploading(true);
                    setUploadError(null);
                    qmsUploadAuditReport(audit.id, file)
                      .then(() => void refetchAuditData())
                      .catch((err: any) => setUploadError(err?.message || "Failed to upload report."))
                      .finally(() => setUploading(false));
                    e.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
            {uploadError ? <p className="text-danger">{uploadError}</p> : null}
          </section>
          <section className="audit-live-card">
            <div className="audit-mini-kpis audit-mini-kpis--single-column">
              <div><strong>{audit.report_file_ref ? "Ready" : "Missing"}</strong><span>Report status</span></div>
              <div><strong>{audit.checklist_file_ref ? "Ready" : "Missing"}</strong><span>Checklist dependency</span></div>
            </div>
          </section>
        </div>
      );
    }

    if (activeTab === "closeout") {
      return (
        <div className="audit-live-grid">
          <section className="audit-live-card audit-live-card--wide">
            <div className="audit-live-card__header">
              <div>
                <h3><CalendarClock size={16} /> Closeout controls</h3>
                <p>Final checks before the audit can transition to closed status.</p>
              </div>
            </div>
            <div className="audit-mini-kpis">
              <div><strong>{openFindings.length}</strong><span>Open findings</span></div>
              <div><strong>{openCars.length}</strong><span>Open CARs</span></div>
              <div><strong>{audit.checklist_file_ref ? "Yes" : "No"}</strong><span>Checklist</span></div>
              <div><strong>{audit.report_file_ref ? "Yes" : "No"}</strong><span>Report</span></div>
            </div>
            <p className="text-muted">Closure follows the backend rules: checklist and report required, all NC findings must have CARs, CAR root cause and CAPA must be accepted, and required evidence must be verified.</p>
            <div className="qms-header__actions">
              <button type="button" className="secondary-chip-btn" onClick={() => exportPack.mutate()} disabled={exportPack.isPending}>
                <PackageCheck size={14} /> {exportPack.isPending ? "Packaging…" : "Package evidence"}
              </button>
              <button type="button" className="secondary-chip-btn" onClick={() => closeAudit.mutate()} disabled={closeAudit.isPending || audit.status === "CLOSED"}>
                {closeAudit.isPending ? "Closing…" : audit.status === "CLOSED" ? "Audit closed" : "Close audit"}
              </button>
            </div>
          </section>
        </div>
      );
    }

    return null;
  };

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={audit?.title || "Audit workspace"}
      subtitle={audit ? "Live audit workspace" : "Resolve audit"}
      breadcrumbs={[
        { label: "Quality", onClick: () => navigate(`/maintenance/${amoCode}/quality`) },
        { label: "Audits", onClick: () => navigate(`/maintenance/${amoCode}/quality/audits`) },
        { label: audit?.title || auditKey },
      ]}
      toolbar={
        <div className={`audit-countdown-card audit-countdown-card--${scheduleCard.tone}`}>
          <div className="audit-countdown-card__label"><TimerReset size={13} /> {scheduleCard.label}</div>
          <div className="audit-countdown-card__value">{scheduleCard.value}</div>
          <div className="audit-countdown-card__meta">{scheduleCard.meta}</div>
        </div>
      }
      nav={null}
      suppressHeader
    >
      {(auditContextQuery.data as any)?.degraded ? (
        <div className="qms-card" style={{ borderColor: "#f59e0b", marginBottom: 12 }}>
          Workflow controls loaded in compatibility mode. Apply the latest Quality workflow migration to enable checklist, war-room request, reminder, and archive tables.
        </div>
      ) : null}
      {!audit ? <div className="qms-card">{auditContextQuery.isError ? "Audit could not be loaded." : isUuidLike(auditKey) ? "Resolving audit..." : "Audit not found."}</div> : null}
      {audit && (
        <>
          <section className="qms-card audit-cockpit-shell audit-cockpit-shell--workbench">
            <aside className="audit-cockpit-rail audit-cockpit-rail--workbench" aria-label="Audit context">
              <section className="audit-workbench-context" aria-label="Audit workspace identity" style={{ "--audit-brand-hue": auditBrandHue } as React.CSSProperties}>
                <div className="audit-workbench-context__title">
                  <p className="audit-workspace-overview__eyebrow">Audit control room</p>
                  <h2>{audit.title}</h2>
                  <div className="audit-workspace-overview__meta audit-workspace-overview__meta--compact">
                    <span className="qms-pill">{audit.audit_ref}</span>
                    <span className="qms-pill">{audit.kind}</span>
                    <span className="qms-pill">{dateFmt(audit.planned_start)} → {dateFmt(audit.planned_end)}</span>
                  </div>
                </div>

                <div className={`audit-countdown-card audit-countdown-card--${scheduleCard.tone}`}>
                  <div className="audit-countdown-card__label"><TimerReset size={13} /> {scheduleCard.label}</div>
                  <div className="audit-countdown-card__value">{scheduleCard.value}</div>
                  <div className="audit-countdown-card__meta">{scheduleCard.meta}</div>
                </div>

                <div className="audit-side-identity-grid">
                  <article className="audit-side-identity-card audit-side-identity-card--company">
                    <div className="audit-side-identity-card__media">
                      <CompanyLogoMark brand={brand} label={auditeeDisplayName} />
                    </div>
                    <div className="audit-side-identity-card__body">
                      <small>Auditee</small>
                      <strong>{auditeeDisplayName}</strong>
                      <span>{brand?.domain || audit.auditee_email || "No auditee contact"}</span>
                    </div>
                  </article>

                  <article className="audit-side-identity-card audit-side-identity-card--team">
                    <div className="audit-avatar-stack" aria-label="Assigned audit team">
                      <WorkspaceAvatar person={leadAuditor} fallback="Lead" size="lg" />
                      <WorkspaceAvatar person={observerAuditor} fallback="Observer" size="lg" />
                      <WorkspaceAvatar person={assistantAuditor} fallback="Assistant" size="lg" />
                    </div>
                    <div className="audit-side-identity-card__body">
                      <small>Audit team</small>
                      <strong>{displayPersonName(audit.lead_auditor_user_id, leadAuditor, "Lead unassigned", audit.lead_auditor_name)}</strong>
                      <span>{[displayPersonName(audit.observer_auditor_user_id, observerAuditor, "", audit.observer_auditor_name), displayPersonName(audit.assistant_auditor_user_id, assistantAuditor, "", audit.assistant_auditor_name)].filter(Boolean).join(" · ") || "Observer and assistant optional"}</span>
                    </div>
                  </article>
                </div>

                <div className="audit-next-action-card audit-next-action-card--compact">
                  <small>Next best action</small>
                  <strong>{nextActionTitle}</strong>
                  <span>{stepGateMessage(activeTab) || workflow?.stages?.find((stage) => stage.active)?.helper || "Complete this step, then use Next to continue."}</span>
                  <em>{percentComplete}% complete</em>
                </div>

                <div className="audit-progress-orbit__stats audit-progress-orbit__stats--compact">
                  <div><small>Findings</small><strong>{openFindings.length}</strong></div>
                  <div><small>CARs</small><strong>{openCars.length}</strong></div>
                  <div><small>Evidence</small><strong>{evidenceCount}</strong></div>
                </div>
              </section>
            </aside>

            <section className="audit-content-shell audit-content-shell--single-view">
              <nav className="audit-workflow-stepper" aria-label="Audit workflow steps" role="list">
                {TABS.map((tab, index) => {
                  const status = tabStepStatus(tab, index);
                  const blocked = firstBlockingStepBefore(tab);
                  return (
                    <button
                      key={tab}
                      type="button"
                      className={`audit-workflow-step is-${status}`}
                      title={blocked || tabMeta[tab].summary}
                      role="listitem"
                      aria-current={activeTab === tab ? "step" : undefined}
                      aria-disabled={status === "locked"}
                      onClick={() => setTab(tab)}
                    >
                      <span className="audit-workflow-step__index">{status === "complete" ? <CheckCircle2 size={13} /> : index + 1}</span>
                      <span className="audit-workflow-step__copy">
                        <strong>{tabLabels[tab]}</strong>
                        <small>{tabStatusText(tab, index)}</small>
                      </span>
                    </button>
                  );
                })}
              </nav>
              <header className="audit-content-shell__header audit-content-shell__header--sticky">
                <button type="button" className="secondary-chip-btn audit-step-nav" onClick={goPrevious} disabled={currentTabIndex <= 0}>Back</button>
                <div>
                  <p className="audit-content-shell__eyebrow">Step {currentTabIndex + 1} of {TABS.length} · {tabLabels[activeTab]}</p>
                  <h3>{tabMeta[activeTab].title}</h3>
                  <p>{activeTab === "findings" && findingsLockedByReport ? "Report issued. Existing findings are read-only." : tabMeta[activeTab].summary}</p>
                </div>
                {activeTab === "findings" ? (
                  <button type="button" className="audit-icon-action" onClick={() => setGuidanceOpen(true)} title="Open finding guidance" aria-label="Open finding guidance">
                    <PanelRightOpen size={16} />
                  </button>
                ) : null}
                <div className="audit-content-shell__badges">
                  {activeTabBadges.slice(0, 3).map((item) => (
                    <span key={`${item.label}-${item.value}`} className="audit-shell-badge">
                      <small>{item.label}</small>
                      <strong>{item.value}</strong>
                    </span>
                  ))}
                </div>
                <button type="button" className="secondary-chip-btn audit-step-nav audit-step-nav--primary" onClick={goNext} disabled={currentTabIndex >= TABS.length - 1}>Next</button>
              </header>
              {actionError ? <p className="text-danger audit-gate-message">{actionError}</p> : null}
              <div className="audit-tab-scrollport">{renderTabContent()}</div>
            </section>
          </section>

          {pendingReportShareGroups ? (
            <aside className="audit-guidance-drawer audit-share-confirm" aria-label="Confirm report sharing">
              <button type="button" className="audit-guidance-drawer__backdrop" onClick={() => setPendingReportShareGroups(null)} aria-label="Cancel report sharing" />
              <div className="audit-guidance-drawer__panel audit-share-confirm__panel">
                <header>
                  <div>
                    <small>Confirm distribution</small>
                    <strong>Share issued audit report</strong>
                  </div>
                  <button type="button" className="audit-icon-action" onClick={() => setPendingReportShareGroups(null)} aria-label="Close confirmation"><X size={16} /></button>
                </header>
                <div className="audit-guidance-drawer__body">
                  <p>The report will be shared with these recipients as read-only unless they are assigned CAR action access.</p>
                  <ul className="audit-guidance-list">
                    {pendingReportShareGroups.map((group) => <li key={group}>{REPORT_SHARE_GROUP_LABELS[group] || group}</li>)}
                  </ul>
                  <div className="qms-header__actions">
                    <button type="button" className="secondary-chip-btn" onClick={() => setPendingReportShareGroups(null)}>Cancel</button>
                    <button type="button" className="secondary-chip-btn audit-step-nav--primary" disabled={shareReportMutation.isPending} onClick={() => shareReportMutation.mutate(pendingReportShareGroups)}>{shareReportMutation.isPending ? "Sharing…" : "Confirm share"}</button>
                  </div>
                </div>
              </div>
            </aside>
          ) : null}

          {guidanceOpen ? (
            <aside className="audit-guidance-drawer" aria-label="Finding guidance">
              <button type="button" className="audit-guidance-drawer__backdrop" onClick={() => setGuidanceOpen(false)} aria-label="Close guidance" />
              <div className="audit-guidance-drawer__panel">
                <header>
                  <div>
                    <small>Fieldwork guidance</small>
                    <strong>NCR / CAPA classification</strong>
                  </div>
                  <button type="button" className="audit-icon-action" onClick={() => setGuidanceOpen(false)} aria-label="Close guidance"><X size={16} /></button>
                </header>
                <div className="audit-guidance-drawer__body">
                  <p>Level 1-3 are non-conformities and can require CAPA. Observations are monitored and only escalated when repeated or left unresolved.</p>
                  <ol className="audit-guidance-list">
                    <li><strong>Level 1 · Critical:</strong> immediate compliance or safety exposure.</li>
                    <li><strong>Level 2 · Major:</strong> significant system or process failure.</li>
                    <li><strong>Level 3 · Minor:</strong> isolated non-conformity requiring correction.</li>
                    <li><strong>Observation:</strong> no automatic CAPA; escalate to Level 3 if repeated or ignored.</li>
                  </ol>
                </div>
              </div>
            </aside>
          ) : null}
        </>
      )}
    </AuditPageShell>
  );
};

export default QualityAuditRunHubPage;
