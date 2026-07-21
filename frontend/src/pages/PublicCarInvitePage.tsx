import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Eye,
  FileText,
  Link2,
  List,
  ListOrdered,
  Paperclip,
  QrCode as QrCodeIcon,
  RotateCcw,
  Save,
  UploadCloud,
  Video,
  X,
  Trash2,
} from "lucide-react";
import { BarcodeFormat, QRCodeWriter } from "@zxing/library";
import AuthLayout from "../components/Layout/AuthLayout";
import {
  qmsGetCarInviteByToken,
  qmsListCarInviteActions,
  qmsListCarInviteAttachments,
  qmsRecallCarInviteSubmission,
  qmsSubmitCarInvite,
  qmsUploadCarInviteAttachment,
  qmsUpdateCarInviteAttachment,
  qmsDeleteCarInviteAttachment,
  type CARActionOut,
  type CARAttachmentOut,
  type CARInviteOut,
  type CARPriority,
  type CARStatus,
} from "../services/qms";
import { getApiBaseUrl } from "../services/config";
import "../styles/car-invite.css";

const MAX_RESPONSE_CHARS = 500;
const MAX_INVITE_EVIDENCE_BYTES = 100 * 1024 * 1024;
const INVITE_EVIDENCE_ACCEPT = [
  "image/*",
  "video/*",
  "application/pdf",
  "text/plain",
  "text/csv",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".heic",
  ".heif",
  ".mp4",
  ".mov",
  ".webm",
  ".mkv",
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".csv",
  ".txt",
].join(",");
const INVITE_EVIDENCE_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".heic",
  ".heif",
  ".mp4",
  ".mov",
  ".webm",
  ".mkv",
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".csv",
  ".txt",
]);
const INVITE_EVIDENCE_MIME_TYPES = new Set([
  "application/pdf",
  "text/plain",
  "text/csv",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/octet-stream",
]);

type InviteStepId = "identity" | "containment" | "analysis" | "corrective" | "evidence" | "review";

type InviteForm = {
  submitted_by_name: string;
  submitted_by_email: string;
  containment_action: string;
  root_cause: string;
  corrective_action: string;
  preventive_action: string;
  evidence_ref: string;
  due_date: string;
  target_closure_date: string;
};

type LoadState = "idle" | "loading" | "ready" | "error";

type InviteEntry = {
  token: string;
  state: LoadState;
  error: string | null;
  notice: string | null;
  invite: CARInviteOut | null;
  form: InviteForm;
  consentAccepted: boolean;
  attachments: CARAttachmentOut[];
  actions: CARActionOut[];
  attachmentsError: string | null;
  uploading: boolean;
  submitting: boolean;
  recalling: boolean;
};

type SelectedPreview = {
  token: string;
  attachment: CARAttachmentOut;
  carNumber: string;
};

type CameraState = {
  token: string;
  stream: MediaStream | null;
  error: string | null;
  opening: boolean;
};

type StructuredTextFieldProps = {
  label: string;
  value: string;
  required?: boolean;
  disabled?: boolean;
  placeholder: string;
  onChange: (value: string) => void;
  note?: string | null;
  toolbarActions?: React.ReactNode;
};

const PRIORITY_LABELS: Record<CARPriority, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  CRITICAL: "Critical",
};

const STATUS_LABELS: Record<CARStatus, string> = {
  DRAFT: "Draft",
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  PENDING_VERIFICATION: "Submitted for review",
  CLOSED: "Closed",
  ESCALATED: "Escalated",
  CANCELLED: "Cancelled",
};

const INVITE_STEPS: Array<{ id: InviteStepId; label: string; help: string }> = [
  { id: "identity", label: "Responder", help: "Confirm who is submitting this response." },
  { id: "containment", label: "Containment", help: "State the immediate action taken to control the issue." },
  { id: "analysis", label: "Root cause", help: "State why the issue happened, not only what was seen." },
  { id: "corrective", label: "Corrective action", help: "State what will change, who owns it, and when it will be done." },
  { id: "evidence", label: "Evidence", help: "Attach proof and reference supporting records." },
  { id: "review", label: "Preview", help: "Check the response before final submission." },
];

const emptyForm = (): InviteForm => ({
  submitted_by_name: "",
  submitted_by_email: "",
  containment_action: "",
  root_cause: "",
  corrective_action: "",
  preventive_action: "",
  evidence_ref: "",
  due_date: "",
  target_closure_date: "",
});

const clampResponseText = (value: string): string => value.slice(0, MAX_RESPONSE_CHARS);

const toForm = (invite: CARInviteOut): InviteForm => ({
  submitted_by_name: invite.submitted_by_name ?? "",
  submitted_by_email: invite.submitted_by_email ?? invite.auditee_email ?? "",
  containment_action: clampResponseText(invite.containment_action ?? ""),
  root_cause: clampResponseText(invite.root_cause ?? ""),
  corrective_action: clampResponseText(invite.corrective_action ?? ""),
  preventive_action: clampResponseText(invite.preventive_action ?? ""),
  evidence_ref: clampResponseText(invite.evidence_ref ?? ""),
  due_date: invite.due_date ?? "",
  target_closure_date: invite.target_closure_date ?? "",
});

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
};

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};

const formatDateOnly = (value: string | null | undefined): string => {
  if (!value) return "Not set";
  const date = new Date(`${value}T23:59:59`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(date);
};

const countdownText = (dateValue: string | null | undefined, now: Date): { label: string; tone: "normal" | "late" | "none" } => {
  if (!dateValue) return { label: "No due date", tone: "none" };
  const due = new Date(`${dateValue}T23:59:59`);
  if (Number.isNaN(due.getTime())) return { label: "Date pending", tone: "none" };
  const diffMs = due.getTime() - now.getTime();
  const absMs = Math.abs(diffMs);
  const days = Math.floor(absMs / 86_400_000);
  const hours = Math.floor((absMs % 86_400_000) / 3_600_000);
  const label = `${days}d ${hours}h`;
  return diffMs >= 0 ? { label: `Due in ${label}`, tone: "normal" } : { label: `Overdue by ${label}`, tone: "late" };
};

const absoluteApiUrl = (url: string): string => {
  if (/^https?:\/\//i.test(url)) return url;
  return `${getApiBaseUrl()}${url.startsWith("/") ? url : `/${url}`}`;
};

const statusBadgeClass = (status: CARStatus): string => {
  if (status === "CLOSED") return "car-invite-badge car-invite-badge--success";
  if (status === "ESCALATED") return "car-invite-badge car-invite-badge--danger";
  if (status === "PENDING_VERIFICATION") return "car-invite-badge car-invite-badge--warning";
  return "car-invite-badge car-invite-badge--info";
};

const fileExtension = (name: string): string => {
  const match = name.toLowerCase().match(/\.[a-z0-9]+$/);
  return match ? match[0] : "";
};

const isInviteEvidenceFileAllowed = (file: File): { ok: true } | { ok: false; reason: string } => {
  if (file.size <= 0) return { ok: false, reason: `${file.name} is empty.` };
  if (file.size > MAX_INVITE_EVIDENCE_BYTES) return { ok: false, reason: `${file.name} exceeds the 100MB evidence limit.` };
  const ext = fileExtension(file.name);
  const mime = file.type.toLowerCase();
  if (mime.startsWith("image/") || mime.startsWith("video/")) return { ok: true };
  if (INVITE_EVIDENCE_MIME_TYPES.has(mime) || INVITE_EVIDENCE_EXTENSIONS.has(ext)) return { ok: true };
  return { ok: false, reason: `${file.name} is not an accepted evidence type.` };
};

const inviteShareUrl = (invite: CARInviteOut, tokenValue: string): string => {
  if (invite.invite_url) return invite.invite_url;
  if (typeof window !== "undefined") return `${window.location.origin}/car-invite?token=${encodeURIComponent(tokenValue)}`;
  return `/car-invite?token=${encodeURIComponent(tokenValue)}`;
};

const insertAtSelection = (source: string, insertText: string, start: number, end: number): { value: string; cursor: number } => {
  const next = clampResponseText(`${source.slice(0, start)}${insertText}${source.slice(end)}`);
  return { value: next, cursor: Math.min(start + insertText.length, next.length) };
};

const isInviteEditable = (invite: CARInviteOut | null): boolean => {
  if (!invite) return false;
  if (["CLOSED", "ESCALATED", "CANCELLED", "PENDING_VERIFICATION"].includes(invite.status)) return false;
  return invite.can_edit !== false;
};

const canSubmitInvite = (invite: CARInviteOut | null): boolean => {
  if (!invite) return false;
  return invite.can_submit !== false && isInviteEditable(invite);
};

const fieldHasValue = (value: string): boolean => Boolean(value.trim());

const romanValues: Record<string, number> = { i: 1, v: 5, x: 10, l: 50, c: 100, d: 500, m: 1000 };
const romanToNumber = (value: string): number => {
  const letters = value.toLowerCase();
  let total = 0;
  for (let index = 0; index < letters.length; index += 1) {
    const current = romanValues[letters[index]] ?? 0;
    const next = romanValues[letters[index + 1]] ?? 0;
    total += current < next ? -current : current;
  }
  return Math.max(1, total);
};

const numberToRoman = (value: number): string => {
  const pairs: Array<[number, string]> = [
    [1000, "m"],
    [900, "cm"],
    [500, "d"],
    [400, "cd"],
    [100, "c"],
    [90, "xc"],
    [50, "l"],
    [40, "xl"],
    [10, "x"],
    [9, "ix"],
    [5, "v"],
    [4, "iv"],
    [1, "i"],
  ];
  let remaining = Math.max(1, Math.min(value, 99));
  let output = "";
  pairs.forEach(([amount, letter]) => {
    while (remaining >= amount) {
      output += letter;
      remaining -= amount;
    }
  });
  return output;
};

const nextListPrefix = (line: string): string | null => {
  const bullet = line.match(/^(\s*)([-•*])\s+/);
  if (bullet) return `${bullet[1]}${bullet[2]} `;
  const numeric = line.match(/^(\s*)(\d+)([.)])\s+/);
  if (numeric) return `${numeric[1]}${Number(numeric[2]) + 1}${numeric[3]} `;
  const roman = line.match(/^(\s*)([ivxlcdm]+)([.)])\s+/i);
  if (roman) return `${roman[1]}${numberToRoman(romanToNumber(roman[2]) + 1)}${roman[3]} `;
  return null;
};

const StructuredTextField: React.FC<StructuredTextFieldProps> = ({ label, value, required, disabled, placeholder, onChange, note, toolbarActions }) => {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const remaining = MAX_RESPONSE_CHARS - value.length;

  const insertListMarker = (marker: "• " | "1. " | "i. ") => {
    if (disabled) return;
    const textarea = ref.current;
    const start = textarea?.selectionStart ?? value.length;
    const end = textarea?.selectionEnd ?? value.length;
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const prefix = start === lineStart || value.slice(lineStart, start).trim() === "" ? marker : `\n${marker}`;
    const { value: next, cursor } = insertAtSelection(value, prefix, start, end);
    onChange(next);
    window.setTimeout(() => {
      textarea?.focus();
      textarea?.setSelectionRange(cursor, cursor);
    }, 0);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || disabled) return;
    const textarea = event.currentTarget;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const beforeCursor = value.slice(0, start);
    const currentLine = beforeCursor.split("\n").pop() ?? "";
    const prefix = nextListPrefix(currentLine);
    if (!prefix) return;
    event.preventDefault();
    const { value: next, cursor } = insertAtSelection(value, `\n${prefix}`, start, end);
    onChange(next);
    window.setTimeout(() => textarea.setSelectionRange(cursor, cursor), 0);
  };

  return (
    <label className="car-invite-field car-invite-field--full">
      <span>{label}{required && <em aria-hidden="true">*</em>}</span>
      <div className="car-invite-editor" aria-label={`${label} structured editor`}>
        <div className="car-invite-editor__toolbar">
          <button type="button" disabled={disabled} onClick={() => insertListMarker("• ")} title="Start bullet list"><List size={15} /><span>Bullets</span></button>
          <button type="button" disabled={disabled} onClick={() => insertListMarker("1. ")} title="Start numbered list"><ListOrdered size={15} /><span>Numbers</span></button>
          <button type="button" disabled={disabled} onClick={() => insertListMarker("i. ")} title="Start roman numeral list"><span>i. ii.</span></button>
          <span className={`car-invite-editor__count ${remaining < 50 ? "is-low" : ""}`}>{remaining} characters left</span>
          {toolbarActions ? <span className="car-invite-editor__actions">{toolbarActions}</span> : null}
        </div>
        <textarea
          ref={ref}
          className="car-invite-textarea"
          value={value}
          disabled={disabled}
          maxLength={MAX_RESPONSE_CHARS}
          onChange={(event) => onChange(clampResponseText(event.target.value))}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          required={required}
        />
      </div>
      {note && <small className="car-invite-auditor-note">Auditor guidance: {note}</small>}
    </label>
  );
};

const InviteQr: React.FC<{ value: string }> = ({ value }) => {
  const qr = useMemo(() => {
    try {
      const matrix = new QRCodeWriter().encode(value, BarcodeFormat.QR_CODE, 180, 180) as {
        get: (x: number, y: number) => boolean;
        getWidth: () => number;
        getHeight: () => number;
      };
      const width = matrix.getWidth();
      const height = matrix.getHeight();
      const cells: React.ReactNode[] = [];
      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          if (matrix.get(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" />);
        }
      }
      return { width, height, cells };
    } catch {
      return null;
    }
  }, [value]);

  if (!qr) return <a href={value} className="car-invite-btn">Open on phone</a>;

  return (
    <svg className="car-invite-qr" viewBox={`0 0 ${qr.width} ${qr.height}`} role="img" aria-label="QR code for phone capture">
      <rect width={qr.width} height={qr.height} fill="white" />
      <g fill="black">{qr.cells}</g>
    </svg>
  );
};

const SubmissionPreview: React.FC<{
  entry: InviteEntry;
  onClose: () => void;
  onConfirm: () => void;
}> = ({ entry, onClose, onConfirm }) => {
  const invite = entry.invite;
  if (!invite) return null;
  const rows: Array<[string, string]> = [
    ["Submitted by", `${entry.form.submitted_by_name} <${entry.form.submitted_by_email}>`],
    ["Immediate containment", entry.form.containment_action || "Not stated"],
    ["Root cause", entry.form.root_cause],
    ["Corrective action", entry.form.corrective_action],
    ["Preventive control", entry.form.preventive_action || "Not stated"],
    ["Evidence", entry.form.evidence_ref || `${entry.attachments.length} uploaded file(s)`],
  ];
  return (
    <div className="car-invite-modal" role="dialog" aria-modal="true" aria-label="Preview CAR submission">
      <div className="car-invite-modal__panel car-invite-modal__panel--preview">
        <div className="car-invite-modal__header">
          <div>
            <p className="car-invite-kicker">Preview before submission</p>
            <h2>{invite.car_number}</h2>
          </div>
          <button type="button" className="car-invite-icon-btn" onClick={onClose} aria-label="Close preview"><X size={18} /></button>
        </div>
        <div className="car-invite-preview-table">
          {rows.map(([label, text]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{text}</strong>
            </div>
          ))}
        </div>
        <p className="car-invite-subtitle">Only one active submission is allowed. After the auditor opens it, the response becomes read-only until returned.</p>
        <div className="car-invite-submit-row">
          <button type="button" className="car-invite-btn" onClick={onClose}>Edit response</button>
          <button type="button" className="car-invite-btn car-invite-btn--primary" onClick={onConfirm} disabled={entry.submitting}>
            <Save size={16} /> {entry.submitting ? "Submitting…" : "Confirm and submit"}
          </button>
        </div>
      </div>
    </div>
  );
};

const PublicCarInvitePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [entries, setEntries] = useState<InviteEntry[]>([]);
  const [selectedPreview, setSelectedPreview] = useState<SelectedPreview | null>(null);
  const [submissionPreviewToken, setSubmissionPreviewToken] = useState<string | null>(null);
  const [camera, setCamera] = useState<CameraState | null>(null);
  const [activeSteps, setActiveSteps] = useState<Record<string, InviteStepId>>({});
  const [now, setNow] = useState(() => new Date());
  const initialized = useRef(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!camera?.stream || !videoRef.current) return;
    videoRef.current.srcObject = camera.stream;
    void videoRef.current.play().catch(() => undefined);
  }, [camera?.stream]);

  const stopCamera = () => {
    camera?.stream?.getTracks().forEach((track) => track.stop());
    setCamera(null);
  };

  useEffect(() => stopCamera, []);

  const updateEntry = (tokenValue: string, updater: (entry: InviteEntry) => InviteEntry) => {
    setEntries((prev) => prev.map((entry) => (entry.token === tokenValue ? updater(entry) : entry)));
  };

  const updateFormField = (tokenValue: string, field: keyof InviteForm, value: string) => {
    const nextValue = (["containment_action", "root_cause", "corrective_action", "preventive_action", "evidence_ref"] as string[]).includes(field)
      ? clampResponseText(value)
      : value;
    updateEntry(tokenValue, (entry) => ({ ...entry, form: { ...entry.form, [field]: nextValue } }));
  };

  const createEntry = (tokenValue: string): InviteEntry => ({
    token: tokenValue,
    state: "loading",
    error: null,
    notice: null,
    invite: null,
    form: emptyForm(),
    consentAccepted: false,
    attachments: [],
    actions: [],
    attachmentsError: null,
    uploading: false,
    submitting: false,
    recalling: false,
  });

  const isStepComplete = (entry: InviteEntry, stepId: InviteStepId): boolean => {
    const invite = entry.invite;
    switch (stepId) {
      case "identity":
        return fieldHasValue(entry.form.submitted_by_name) && fieldHasValue(entry.form.submitted_by_email);
      case "containment":
        return fieldHasValue(entry.form.containment_action);
      case "analysis":
        return fieldHasValue(entry.form.root_cause) || ["ACCEPTED", "APPROVED"].includes(invite?.root_cause_status ?? "");
      case "corrective":
        return fieldHasValue(entry.form.corrective_action) || ["ACCEPTED", "APPROVED"].includes(invite?.capa_status ?? "");
      case "evidence":
        return !invite?.evidence_required || fieldHasValue(entry.form.evidence_ref) || entry.attachments.length > 0 || Boolean(invite.evidence_received_at);
      case "review":
        return Boolean(invite?.latest_submission_at || invite?.submitted_at) || invite?.status === "PENDING_VERIFICATION" || invite?.status === "CLOSED";
      default:
        return false;
    }
  };

  const firstIncompleteStep = (entry: InviteEntry): InviteStepId => {
    return INVITE_STEPS.find((step) => !isStepComplete(entry, step.id))?.id ?? "review";
  };

  const stepIndex = (stepId: InviteStepId): number => INVITE_STEPS.findIndex((step) => step.id === stepId);

  const isStepUnlocked = (entry: InviteEntry, stepId: InviteStepId): boolean => {
    const index = stepIndex(stepId);
    if (index <= 0) return true;
    return INVITE_STEPS.slice(0, index).every((step) => isStepComplete(entry, step.id));
  };

  const getActiveStep = (entry: InviteEntry): InviteStepId => {
    const preferred = activeSteps[entry.token];
    if (preferred && isStepUnlocked(entry, preferred)) return preferred;
    return firstIncompleteStep(entry);
  };

  const setActiveStep = (tokenValue: string, stepId: InviteStepId) => {
    setActiveSteps((prev) => ({ ...prev, [tokenValue]: stepId }));
  };

  const validateStep = (entry: InviteEntry, stepId: InviteStepId): string | null => {
    if (!entry.invite) return "CAR invite is not loaded.";
    if (!isInviteEditable(entry.invite) && stepId !== "review") return entry.invite.locked_reason || "This CAR is read-only.";
    if (stepId === "identity") {
      if (!fieldHasValue(entry.form.submitted_by_name)) return "Your name is required.";
      if (!fieldHasValue(entry.form.submitted_by_email)) return "Your email is required.";
    }
    if (stepId === "containment" && !fieldHasValue(entry.form.containment_action)) {
      return "Immediate containment is required. Enter N/A if no containment was required.";
    }
    if (stepId === "analysis" && !fieldHasValue(entry.form.root_cause)) return "Root cause is required.";
    if (stepId === "corrective" && !fieldHasValue(entry.form.corrective_action)) return "Corrective action plan is required.";
    if (stepId === "evidence" && entry.invite.evidence_required && !fieldHasValue(entry.form.evidence_ref) && entry.attachments.length === 0) {
      return "Evidence is required before submission.";
    }
    return null;
  };

  const advanceStep = (entry: InviteEntry, stepId: InviteStepId) => {
    const validationError = validateStep(entry, stepId);
    if (validationError) {
      updateEntry(entry.token, (current) => ({ ...current, error: validationError, notice: null }));
      return;
    }
    const next = INVITE_STEPS[stepIndex(stepId) + 1]?.id ?? "review";
    updateEntry(entry.token, (current) => ({ ...current, error: null, notice: `${INVITE_STEPS[stepIndex(stepId)].label} saved. Continue with ${INVITE_STEPS[stepIndex(next)].label}.` }));
    setActiveStep(entry.token, next);
  };

  const loadInvite = React.useCallback(async (tokenValue: string, notice?: string) => {
    updateEntry(tokenValue, (entry) => ({ ...entry, state: "loading", error: null, notice: notice ?? entry.notice }));
    try {
      const [data, attachmentsResult, actionsResult] = await Promise.allSettled([
        qmsGetCarInviteByToken(tokenValue),
        qmsListCarInviteAttachments(tokenValue),
        qmsListCarInviteActions(tokenValue),
      ]);
      if (data.status === "rejected") throw data.reason;
      updateEntry(tokenValue, (entry) => {
        const nextEntry = {
          ...entry,
          invite: data.value,
          form: toForm(data.value),
          attachments: attachmentsResult.status === "fulfilled" ? attachmentsResult.value : [],
          actions: actionsResult.status === "fulfilled" ? actionsResult.value : [],
          attachmentsError: attachmentsResult.status === "rejected" ? getErrorMessage(attachmentsResult.reason, "Could not load attachments.") : null,
          state: "ready" as const,
          notice: notice ?? null,
        };
        setActiveSteps((prev) => ({ ...prev, [tokenValue]: prev[tokenValue] ?? firstIncompleteStep(nextEntry) }));
        return nextEntry;
      });
      const relatedTokens = (data.value.related_cars ?? [])
        .map((item) => item.invite_token)
        .filter((relatedToken) => relatedToken && relatedToken !== tokenValue);
      if (relatedTokens.length) {
        const toLoad: string[] = [];
        setEntries((prev) => {
          const seen = new Set(prev.map((entry) => entry.token));
          const additions = relatedTokens.filter((relatedToken) => !seen.has(relatedToken));
          toLoad.push(...additions);
          return additions.length ? [...prev, ...additions.map((relatedToken) => createEntry(relatedToken))] : prev;
        });
        toLoad.forEach((relatedToken) => window.setTimeout(() => void loadInvite(relatedToken), 0));
      }
    } catch (error: unknown) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        error: getErrorMessage(error, "Failed to load CAR invite."),
        state: "error",
        notice: null,
      }));
    }
  }, []);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!token) {
      setEntries([{ ...createEntry(""), state: "error", error: "Invite token missing." }]);
      return;
    }
    const tokens = token.split(",").map((value) => value.trim()).filter(Boolean);
    setEntries(tokens.map((tokenValue) => createEntry(tokenValue)));
    tokens.forEach((tokenValue) => void loadInvite(tokenValue));
  }, [token, loadInvite]);

  useEffect(() => {
    if (!selectedPreview) return;
    const entry = entries.find((item) => item.token === selectedPreview.token);
    const stillExists = entry?.attachments.some((attachment) => attachment.id === selectedPreview.attachment.id);
    if (!stillExists) setSelectedPreview(null);
  }, [entries, selectedPreview]);

  const validateEntry = (entry: InviteEntry): string | null => {
    if (!entry.invite) return "CAR invite is not loaded.";
    if (!canSubmitInvite(entry.invite)) return entry.invite.locked_reason || "This CAR cannot be submitted right now.";
    const stepError = INVITE_STEPS.slice(0, -1).map((step) => validateStep(entry, step.id)).find(Boolean);
    if (stepError) return stepError;
    if (!entry.consentAccepted) return "Accept the submission declaration before submitting.";
    return null;
  };

  const submitInvite = async (tokenValue: string) => {
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current || !current.invite) return;
    const validationError = validateEntry(current);
    if (validationError) {
      updateEntry(tokenValue, (entry) => ({ ...entry, error: validationError }));
      return;
    }
    updateEntry(tokenValue, (entry) => ({ ...entry, error: null, notice: null, submitting: true }));
    try {
      await qmsSubmitCarInvite(tokenValue, {
        submitted_by_name: current.form.submitted_by_name.trim(),
        submitted_by_email: current.form.submitted_by_email.trim(),
        containment_action: clampResponseText(current.form.containment_action.trim()),
        root_cause: clampResponseText(current.form.root_cause.trim()),
        corrective_action: clampResponseText(current.form.corrective_action.trim()),
        preventive_action: clampResponseText(current.form.preventive_action.trim()),
        evidence_ref: clampResponseText(current.form.evidence_ref.trim()),
        due_date: current.form.due_date || null,
        target_closure_date: current.form.target_closure_date || null,
      });
      setSubmissionPreviewToken(null);
      updateEntry(tokenValue, (entry) => ({ ...entry, submitting: false, consentAccepted: false }));
      await loadInvite(tokenValue, "Response submitted. The audit team can now review it.");
    } catch (error: unknown) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        submitting: false,
        error: getErrorMessage(error, "Failed to submit CAR response."),
      }));
    }
  };

  const handleSubmit = (tokenValue: string) => (event: React.FormEvent) => {
    event.preventDefault();
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current) return;
    const validationError = validateEntry(current);
    if (validationError) {
      updateEntry(tokenValue, (entry) => ({ ...entry, error: validationError }));
      setActiveStep(tokenValue, firstIncompleteStep(current));
      return;
    }
    updateEntry(tokenValue, (entry) => ({ ...entry, error: null }));
    setSubmissionPreviewToken(tokenValue);
  };

  const handleRecall = async (tokenValue: string) => {
    updateEntry(tokenValue, (entry) => ({ ...entry, recalling: true, error: null, notice: null }));
    try {
      await qmsRecallCarInviteSubmission(tokenValue);
      updateEntry(tokenValue, (entry) => ({ ...entry, recalling: false, consentAccepted: false }));
      setActiveStep(tokenValue, "identity");
      await loadInvite(tokenValue, "Submission recalled. You may edit and resubmit if submissions remain.");
    } catch (error: unknown) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        recalling: false,
        error: getErrorMessage(error, "Failed to recall submission."),
      }));
    }
  };

  const uploadFiles = async (tokenValue: string, files: File[]) => {
    if (!files.length) return;
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current?.invite || !isInviteEditable(current.invite)) {
      updateEntry(tokenValue, (entry) => ({ ...entry, attachmentsError: current?.invite?.locked_reason || "This CAR is not editable." }));
      return;
    }
    const rejected: string[] = [];
    const uploads: File[] = [];
    files.forEach((file) => {
      const result = isInviteEvidenceFileAllowed(file);
      if (result.ok) {
        uploads.push(file);
      } else if ("reason" in result) {
        rejected.push(result.reason);
      }
    });
    if (uploads.length === 0) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachmentsError: rejected[0] || "Selected files are not accepted evidence types.",
      }));
      return;
    }
    updateEntry(tokenValue, (entry) => ({ ...entry, uploading: true, attachmentsError: rejected.length ? rejected.join(" ") : null, notice: null }));
    try {
      const results: CARAttachmentOut[] = [];
      for (const upload of uploads) {
        const uploaded = await qmsUploadCarInviteAttachment(tokenValue, upload);
        results.push(uploaded);
      }
      const actions = await qmsListCarInviteActions(tokenValue).catch(() => []);
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachments: [...entry.attachments, ...results],
        actions,
        uploading: false,
        notice: `${results.length} evidence file${results.length === 1 ? "" : "s"} uploaded successfully.`,
      }));
    } catch (error: unknown) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        uploading: false,
        attachmentsError: getErrorMessage(error, "Failed to upload attachment."),
      }));
    }
  };

  const handleUpload = (tokenValue: string) => async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles: File[] = event.target.files ? Array.from(event.target.files) : [];
    await uploadFiles(tokenValue, selectedFiles);
    event.target.value = "";
  };

  const updateAttachmentDescription = async (tokenValue: string, attachmentId: string, description: string) => {
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current?.invite || !isInviteEditable(current.invite)) return;
    const nextDescription = clampResponseText(description);
    updateEntry(tokenValue, (entry) => ({
      ...entry,
      attachments: entry.attachments.map((attachment) =>
        attachment.id === attachmentId ? { ...attachment, description: nextDescription } : attachment
      ),
    }));
    try {
      const updated = await qmsUpdateCarInviteAttachment(tokenValue, attachmentId, { description: nextDescription });
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachments: entry.attachments.map((attachment) => (attachment.id === attachmentId ? updated : attachment)),
        notice: "Evidence description saved.",
      }));
    } catch (error: unknown) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachmentsError: getErrorMessage(error, "Could not save evidence description."),
      }));
    }
  };

  const deleteInviteAttachment = async (tokenValue: string, attachmentId: string) => {
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current?.invite || !isInviteEditable(current.invite)) return;
    updateEntry(tokenValue, (entry) => ({ ...entry, attachmentsError: null }));
    try {
      await qmsDeleteCarInviteAttachment(tokenValue, attachmentId);
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachments: entry.attachments.filter((attachment) => attachment.id !== attachmentId),
        notice: "Evidence attachment removed.",
      }));
      if (selectedPreview?.token === tokenValue && selectedPreview.attachment.id === attachmentId) setSelectedPreview(null);
    } catch (error: unknown) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachmentsError: getErrorMessage(error, "Could not delete evidence attachment."),
      }));
    }
  };

  const triggerCaptureInput = (tokenValue: string) => {
    const input = document.getElementById(`camera-file-${tokenValue}`) as HTMLInputElement | null;
    if (input) {
      input.click();
      return true;
    }
    return false;
  };

  const openCamera = async (tokenValue: string) => {
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current?.invite || !isInviteEditable(current.invite)) {
      updateEntry(tokenValue, (entry) => ({ ...entry, attachmentsError: current?.invite?.locked_reason || "This CAR is not editable." }));
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      if (!triggerCaptureInput(tokenValue)) {
        updateEntry(tokenValue, (entry) => ({ ...entry, attachmentsError: "Camera requires HTTPS or localhost. Use Upload files from this device." }));
      }
      return;
    }
    setCamera({ token: tokenValue, stream: null, error: null, opening: true });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      setCamera({ token: tokenValue, stream, error: null, opening: false });
    } catch (error: unknown) {
      setCamera(null);
      if (!triggerCaptureInput(tokenValue)) {
        updateEntry(tokenValue, (entry) => ({ ...entry, attachmentsError: getErrorMessage(error, "Camera permission was denied or unavailable.") }));
      }
    }
  };

  const capturePhoto = async () => {
    if (!camera?.token || !videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) {
      setCamera((prev) => (prev ? { ...prev, error: "Could not capture a photo from the camera stream." } : prev));
      return;
    }
    const file = new File([blob], `car-evidence-${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`, { type: "image/jpeg" });
    const tokenValue = camera.token;
    stopCamera();
    await uploadFiles(tokenValue, [file]);
  };

  const renderStageSummary = (entry: InviteEntry, stepId: InviteStepId): string => {
    switch (stepId) {
      case "identity":
        return entry.form.submitted_by_name ? `${entry.form.submitted_by_name} • ${entry.form.submitted_by_email || "email pending"}` : "Responder details pending";
      case "containment":
        return entry.form.containment_action || "Immediate containment pending";
      case "analysis":
        return entry.form.root_cause || "Root cause pending";
      case "corrective":
        return entry.form.corrective_action || "Corrective action pending";
      case "evidence":
        return entry.attachments.length ? `${entry.attachments.length} file(s) attached` : entry.form.evidence_ref || "Evidence pending";
      case "review":
        return entry.invite?.latest_submission_at ? `Submitted ${formatDateTime(entry.invite.latest_submission_at)}` : "Preview before final submission";
      default:
        return "";
    }
  };

  const readyEntries = entries.filter((entry) => entry.state === "ready" && entry.invite);
  const openItems = readyEntries.filter((entry) => !["CLOSED", "CANCELLED"].includes(entry.invite?.status ?? "")).length;
  const evidenceCount = entries.reduce((sum, entry) => sum + entry.attachments.length, 0);
  const sideEvidence = entries.flatMap((entry) => entry.attachments.map((attachment) => ({ entry, attachment })));
  const sideHistory = entries.flatMap((entry) => entry.actions.map((action) => ({ entry, action }))).slice(0, 18);
  const previewEntry = submissionPreviewToken ? entries.find((entry) => entry.token === submissionPreviewToken) ?? null : null;

  return (
    <AuthLayout
      className="auth-layout--car-invite"
      title="Corrective Action Response"
      subtitle="Review the finding, respond through the guided CAR flow, attach evidence, and track status."
    >
      <div className="car-invite-workbench">
        <section className="car-invite-toolbar">
          <div>
            <p className="car-invite-kicker">Public CAR workspace</p>
            <h2 className="car-invite-title">Assigned corrective actions</h2>
            <p className="car-invite-subtitle">Fields marked <strong>*</strong> are required. Response fields are limited to {MAX_RESPONSE_CHARS} characters each.</p>
          </div>
          <div className="car-invite-toolbar__stats" aria-label="Workspace status">
            <span><ClipboardCheck size={16} /> {readyEntries.length} CAR{readyEntries.length === 1 ? "" : "s"}</span>
            <span><AlertTriangle size={16} /> {openItems} open</span>
            <span><Paperclip size={16} /> {evidenceCount} evidence</span>
          </div>
        </section>

        {readyEntries.length > 1 && (
          <nav className="car-invite-car-tabs" aria-label="Assigned CARs">
            {readyEntries.map((entry) => (
              <button key={entry.token} type="button" onClick={() => document.getElementById(`car-${entry.invite?.car_number}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                <strong>{entry.invite?.car_number}</strong>
                <span>{entry.invite?.finding_description || entry.invite?.finding_ref || entry.invite?.title}</span>
              </button>
            ))}
          </nav>
        )}

        <div className="car-invite-layout">
          <main className="car-invite-stack">
            {entries.map((entry) => {
              const invite = entry.invite;
              const dueCountdown = countdownText(invite?.due_date || invite?.target_closure_date, now);
              const locked = !isInviteEditable(invite);
              const canSubmit = canSubmitInvite(invite);
              const shareUrl = invite ? inviteShareUrl(invite, entry.token) : "";
              const activeStep = getActiveStep(entry);

              return (
                <article key={entry.token || "missing-token"} id={invite ? `car-${invite.car_number}` : undefined} className={`car-invite-card ${entry.state === "ready" ? "is-active" : ""}`}>
                  {entry.state === "loading" && <p className="car-invite-subtitle">Loading invite…</p>}
                  {entry.state === "error" && <div className="car-invite-error">{entry.error}</div>}

                  {entry.state === "ready" && invite && (
                    <>
                      <header className="car-invite-card__head">
                        <div>
                          <p className="car-invite-kicker">{invite.car_number}</p>
                          <h2 className="car-invite-title">{invite.finding_ref ? `Action for ${invite.finding_ref}` : invite.title}</h2>
                          <div className="car-invite-meta-line">
                            <span>{PRIORITY_LABELS[invite.priority]} priority</span>
                            <span className={statusBadgeClass(invite.status)}>{STATUS_LABELS[invite.status]}</span>
                            <span>{invite.remaining_submissions ?? 0} submission{(invite.remaining_submissions ?? 0) === 1 ? "" : "s"} remaining</span>
                          </div>
                        </div>
                        <aside className={`car-invite-countdown ${dueCountdown.tone === "late" ? "is-late" : ""}`}>
                          <Clock3 size={18} />
                          <div><strong>{dueCountdown.label}</strong><small>Due {formatDateOnly(invite.due_date || invite.target_closure_date)}</small></div>
                        </aside>
                      </header>

                      {entry.notice && <div className="car-invite-notice"><CheckCircle2 size={18} /> {entry.notice}</div>}
                      {entry.error && <div className="car-invite-error"><AlertTriangle size={18} /> {entry.error}</div>}
                      {invite.locked_reason && <div className="car-invite-readonly"><Eye size={16} /> {invite.locked_reason}</div>}

                      <section className="car-invite-finding">
                        <div className="car-invite-finding__main">
                          <p className="car-invite-kicker">Finding to address</p>
                          <h3>{invite.finding_description || invite.summary || "Finding details pending"}</h3>
                        </div>
                        <dl>
                          <div><dt>Finding ref</dt><dd>{invite.finding_ref || "N/A"}</dd></div>
                          <div><dt>Audit</dt><dd>{invite.audit_title || invite.audit_ref || "N/A"}</dd></div>
                          <div><dt>Auditee</dt><dd>{invite.auditee || "N/A"}</dd></div>
                        </dl>
                      </section>

                      <form className="car-invite-form" onSubmit={handleSubmit(entry.token)}>
                        <div className="car-invite-flow-shell">
                          <aside className="car-invite-stage-rail" aria-label="Corrective action response progress">
                            {INVITE_STEPS.map((step, index) => {
                              const complete = isStepComplete(entry, step.id);
                              const unlocked = isStepUnlocked(entry, step.id);
                              const active = activeStep === step.id;
                              return (
                                <button
                                  key={step.id}
                                  type="button"
                                  className={`car-invite-stage-rail__step ${active ? "is-active" : ""} ${complete ? "is-complete" : ""}`}
                                  disabled={!unlocked || locked}
                                  onClick={() => setActiveStep(entry.token, step.id)}
                                >
                                  <span>{complete ? <CheckCircle2 size={15} /> : index + 1}</span>
                                  <strong>{step.label}</strong>
                                </button>
                              );
                            })}
                          </aside>
                          <div className="car-invite-stage-stack">
                          {INVITE_STEPS.map((step, index) => {
                            if (!isStepUnlocked(entry, step.id)) return null;
                            const active = activeStep === step.id;
                            const complete = isStepComplete(entry, step.id);
                            return (
                              <section key={step.id} className={`car-invite-stage ${active ? "is-active" : ""} ${complete ? "is-complete" : ""}`}>
                                <header className="car-invite-stage__head">
                                  <span className="car-invite-stage__index">{complete ? <CheckCircle2 size={17} /> : index + 1}</span>
                                  <div>
                                    <h3>{step.label}</h3>
                                    <p>{step.help}</p>
                                  </div>
                                  {!active && (
                                    <button type="button" className="car-invite-btn car-invite-btn--compact" disabled={locked} onClick={() => setActiveStep(entry.token, step.id)}>Edit</button>
                                  )}
                                </header>
                                {!active && <p className="car-invite-stage__summary">{renderStageSummary(entry, step.id)}</p>}

                                {active && step.id === "identity" && (
                                  <div className="car-invite-stage__body car-invite-form-grid">
                                    <label className="car-invite-field">
                                      <span>Your name<em aria-hidden="true">*</em></span>
                                      <input className="car-invite-input" value={entry.form.submitted_by_name} disabled={locked} onChange={(event) => updateFormField(entry.token, "submitted_by_name", event.target.value)} required />
                                    </label>
                                    <label className="car-invite-field">
                                      <span>Your email<em aria-hidden="true">*</em></span>
                                      <input className="car-invite-input" type="email" value={entry.form.submitted_by_email} disabled={locked} onChange={(event) => updateFormField(entry.token, "submitted_by_email", event.target.value)} required />
                                    </label>
                                    <div className="car-invite-stage__actions">
                                      <button type="button" className="car-invite-btn car-invite-btn--primary" disabled={locked} onClick={() => advanceStep(entry, "identity")}>Save responder details</button>
                                    </div>
                                  </div>
                                )}

                                {active && step.id === "containment" && (
                                  <div className="car-invite-stage__body">
                                    <StructuredTextField
                                      label="Immediate containment action"
                                      required
                                      value={entry.form.containment_action}
                                      disabled={locked}
                                      onChange={(value) => updateFormField(entry.token, "containment_action", value)}
                                      placeholder="State the immediate action taken. Use N/A if containment was not required."
                                    />
                                    <div className="car-invite-stage__actions">
                                      <button type="button" className="car-invite-btn car-invite-btn--primary" disabled={locked} onClick={() => advanceStep(entry, "containment")}>Save containment and continue</button>
                                    </div>
                                  </div>
                                )}

                                {active && step.id === "analysis" && (
                                  <div className="car-invite-stage__body">
                                    <StructuredTextField
                                      label="Root cause analysis"
                                      required
                                      value={entry.form.root_cause}
                                      disabled={locked}
                                      onChange={(value) => updateFormField(entry.token, "root_cause", value)}
                                      placeholder="State the verified root cause. Example: The inspection control was missed because the checklist did not identify the required sign-off."
                                      note={invite.root_cause_review_note}
                                    />
                                    <div className="car-invite-stage__actions">
                                      <button type="button" className="car-invite-btn" disabled={locked} onClick={() => setActiveStep(entry.token, "containment")}>Back</button>
                                      <button type="button" className="car-invite-btn car-invite-btn--primary" disabled={locked} onClick={() => advanceStep(entry, "analysis")}>Save root cause and continue</button>
                                    </div>
                                  </div>
                                )}

                                {active && step.id === "corrective" && (
                                  <div className="car-invite-stage__body car-invite-form-grid">
                                    <StructuredTextField
                                      label="Corrective action plan"
                                      required
                                      value={entry.form.corrective_action}
                                      disabled={locked}
                                      onChange={(value) => updateFormField(entry.token, "corrective_action", value)}
                                      placeholder="State what will change, who owns it, and when it will be completed."
                                      note={invite.capa_review_note}
                                    />
                                    <StructuredTextField
                                      label="Preventive action / systemic control"
                                      value={entry.form.preventive_action}
                                      disabled={locked}
                                      onChange={(value) => updateFormField(entry.token, "preventive_action", value)}
                                      placeholder="State how recurrence will be prevented."
                                    />
                                    <label className="car-invite-field">
                                      <span>Target closure date</span>
                                      <input className="car-invite-input" type="date" value={entry.form.target_closure_date} disabled={locked} onChange={(event) => updateFormField(entry.token, "target_closure_date", event.target.value)} />
                                    </label>
                                    <label className="car-invite-field">
                                      <span>Due date</span>
                                      <input className="car-invite-input" type="date" value={entry.form.due_date} disabled={locked} onChange={(event) => updateFormField(entry.token, "due_date", event.target.value)} />
                                    </label>
                                    <div className="car-invite-stage__actions">
                                      <button type="button" className="car-invite-btn" disabled={locked} onClick={() => setActiveStep(entry.token, "analysis")}>Back</button>
                                      <button type="button" className="car-invite-btn car-invite-btn--primary" disabled={locked} onClick={() => advanceStep(entry, "corrective")}>Save corrective action and continue</button>
                                    </div>
                                  </div>
                                )}

                                {active && step.id === "evidence" && (
                                  <div className="car-invite-stage__body car-invite-evidence-compact">
                                    <input id={`evidence-${entry.token}`} type="file" multiple disabled={locked || entry.uploading} onChange={handleUpload(entry.token)} accept={INVITE_EVIDENCE_ACCEPT} />
                                    <input id={`camera-file-${entry.token}`} type="file" capture="environment" disabled={locked || entry.uploading} onChange={handleUpload(entry.token)} accept="image/*,video/*" />
                                    <StructuredTextField
                                      label="Evidence reference"
                                      value={entry.form.evidence_ref}
                                      disabled={locked}
                                      onChange={(value) => updateFormField(entry.token, "evidence_ref", value)}
                                      placeholder="Reference the uploaded file, record, work order, photo, video, or signed offline CAR form."
                                      toolbarActions={
                                        <>
                                          <button type="button" className="car-invite-icon-btn" disabled={locked || entry.uploading} onClick={() => openCamera(entry.token)} title="Open camera" aria-label="Open camera"><Camera size={16} /></button>
                                          <label className="car-invite-icon-btn" htmlFor={`evidence-${entry.token}`} title="Attach evidence" aria-label="Attach evidence"><Paperclip size={16} /></label>
                                        </>
                                      }
                                    />
                                    <details className="car-invite-phone-capture">
                                      <summary><QrCodeIcon size={15} /> Use phone camera</summary>
                                      <div>
                                        <p>Scan this QR on a phone to capture field photos or video directly against this CAR.</p>
                                        <InviteQr value={shareUrl} />
                                      </div>
                                    </details>
                                    {entry.uploading && <div className="car-invite-notice"><UploadCloud size={18} /> Uploading evidence…</div>}
                                    {entry.attachmentsError && <div className="car-invite-error"><AlertTriangle size={18} /> {entry.attachmentsError}</div>}
                                    {entry.attachments.length > 0 && (
                                      <div className="car-invite-evidence-list">
                                        {entry.attachments.map((attachment) => {
                                          const url = absoluteApiUrl(attachment.download_url);
                                          const isImage = attachment.content_type?.startsWith("image/");
                                          const isVideo = attachment.content_type?.startsWith("video/");
                                          const isPdf = attachment.content_type?.includes("pdf") || attachment.filename.toLowerCase().endsWith(".pdf");
                                          return (
                                            <article key={attachment.id} className="car-invite-evidence-item">
                                              <button type="button" className="car-invite-file car-invite-file--compact" onClick={() => setSelectedPreview({ token: entry.token, attachment, carNumber: invite.car_number })}>
                                                <span className="car-invite-file__preview">
                                                  {isImage ? <img src={url} alt={attachment.filename} /> : isVideo ? <Video size={24} /> : isPdf ? "PDF" : <FileText size={22} />}
                                                </span>
                                                <strong>{attachment.filename}</strong>
                                              </button>
                                              <label className="car-invite-field car-invite-field--evidence-note">
                                                <span>Short description for auditor</span>
                                                <input
                                                  className="car-invite-input"
                                                  value={attachment.description ?? ""}
                                                  disabled={locked}
                                                  maxLength={500}
                                                  onChange={(event) => updateEntry(entry.token, (current) => ({
                                                    ...current,
                                                    attachments: current.attachments.map((item) => item.id === attachment.id ? { ...item, description: clampResponseText(event.target.value) } : item),
                                                  }))}
                                                  onBlur={(event) => void updateAttachmentDescription(entry.token, attachment.id, event.target.value)}
                                                  placeholder="e.g. Attendance form for SMS recurrent course, trainee no. 12"
                                                />
                                              </label>
                                              <button type="button" className="car-invite-icon-btn car-invite-icon-btn--danger" disabled={locked} onClick={() => void deleteInviteAttachment(entry.token, attachment.id)} title="Delete evidence" aria-label={`Delete ${attachment.filename}`}><Trash2 size={16} /></button>
                                            </article>
                                          );
                                        })}
                                      </div>
                                    )}
                                    <div className="car-invite-stage__actions">
                                      <button type="button" className="car-invite-btn" disabled={locked} onClick={() => setActiveStep(entry.token, "corrective")}>Back</button>
                                      <button type="button" className="car-invite-btn car-invite-btn--primary" disabled={locked} onClick={() => advanceStep(entry, "evidence")}>Save evidence and continue</button>
                                    </div>
                                  </div>
                                )}

                                {active && step.id === "review" && (
                                  <div className="car-invite-stage__body">
                                    <div className="car-invite-review-grid">
                                      <div><span>Responder</span><strong>{entry.form.submitted_by_name || "Pending"}</strong></div>
                                      <div><span>Containment</span><strong>{entry.form.containment_action || "Pending"}</strong></div>
                                      <div><span>Root cause</span><strong>{entry.form.root_cause || "Pending"}</strong></div>
                                      <div><span>Corrective action</span><strong>{entry.form.corrective_action || "Pending"}</strong></div>
                                      <div><span>Evidence</span><strong>{entry.form.evidence_ref || `${entry.attachments.length} uploaded file(s)`}</strong></div>
                                    </div>
                                    <label className="car-invite-consent">
                                      <input type="checkbox" checked={entry.consentAccepted} disabled={locked} onChange={(event) => updateEntry(entry.token, (prev) => ({ ...prev, consentAccepted: event.target.checked }))} required />
                                      <span>I confirm this response and evidence are accurate for audit closeout.</span>
                                    </label>
                                    <div className="car-invite-submit-row">
                                      <span className="car-invite-subtitle">
                                        {locked ? invite.locked_reason || "This CAR is read-only." : "Preview is required before final submission."}
                                      </span>
                                      <div className="car-invite-actions">
                                        {invite.can_recall ? (
                                          <button type="button" className="car-invite-btn" disabled={entry.recalling} onClick={() => handleRecall(entry.token)}>
                                            <RotateCcw size={16} /> {entry.recalling ? "Recalling…" : "Recall submission"}
                                          </button>
                                        ) : null}
                                        <button type="submit" className="car-invite-btn car-invite-btn--primary" disabled={!canSubmit || !entry.consentAccepted || entry.submitting}>
                                          <Eye size={16} /> Preview submission
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </section>
                            );
                          })}
                          </div>
                        </div>
                      </form>
                    </>
                  )}
                </article>
              );
            })}
          </main>

          <aside className="car-invite-side">
            <details className="car-invite-panel" open>
              <summary><span>Action items</span><strong>{readyEntries.length}</strong></summary>
              <div className="car-invite-list">
                {readyEntries.length === 0 && <p className="car-invite-subtitle">No CARs loaded yet.</p>}
                {readyEntries.map((entry) => (
                  <button key={entry.token} type="button" onClick={() => document.getElementById(`car-${entry.invite?.car_number}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                    <strong>{entry.invite?.car_number}</strong>
                    <small>{entry.invite?.finding_description || entry.invite?.title}</small>
                  </button>
                ))}
              </div>
            </details>

            <details className="car-invite-panel" open>
              <summary><span>Audit report</span><FileText size={16} /></summary>
              {readyEntries.find((entry) => entry.invite?.audit_report_download_url)?.invite ? (
                <a className="car-invite-btn car-invite-btn--wide" href={absoluteApiUrl(readyEntries.find((entry) => entry.invite?.audit_report_download_url)!.invite!.audit_report_download_url!)} target="_blank" rel="noreferrer">
                  <FileText size={16} /> View / download report
                </a>
              ) : <p className="car-invite-subtitle">The auditor has not issued the report yet.</p>}
            </details>

            <details className="car-invite-panel" open>
              <summary><span>Evidence attached</span><strong>{sideEvidence.length}</strong></summary>
              <div className="car-invite-side-evidence">
                {sideEvidence.length === 0 && <p className="car-invite-subtitle">No evidence uploaded yet.</p>}
                {sideEvidence.map(({ entry, attachment }) => (
                  <button key={`${entry.token}-${attachment.id}`} type="button" onClick={() => setSelectedPreview({ token: entry.token, attachment, carNumber: entry.invite?.car_number || "CAR" })}>
                    <Paperclip size={15} />
                    <span>
                      <strong>{attachment.description || attachment.filename}</strong>
                      <small>{entry.invite?.car_number} • {attachment.filename}</small>
                    </span>
                  </button>
                ))}
              </div>
            </details>

            <details className="car-invite-panel">
              <summary><span>Phone capture</span><QrCodeIcon size={16} /></summary>
              {readyEntries[0]?.invite ? (
                <div className="car-invite-share">
                  <InviteQr value={inviteShareUrl(readyEntries[0].invite, readyEntries[0].token)} />
                  <a className="car-invite-btn" href={inviteShareUrl(readyEntries[0].invite, readyEntries[0].token)} target="_blank" rel="noreferrer"><Link2 size={16} /> Open link</a>
                </div>
              ) : <p className="car-invite-subtitle">QR appears after a CAR loads.</p>}
            </details>

            <details className="car-invite-panel" open>
              <summary><span>History and progress</span><strong>{sideHistory.length}</strong></summary>
              <div className="car-invite-history">
                {sideHistory.length === 0 && <p className="car-invite-subtitle">No history entries yet.</p>}
                {sideHistory.map(({ entry, action }) => (
                  <div key={action.id} className="car-invite-history__item">
                    <strong>{entry.invite?.car_number || "CAR"}: {action.action_type.replaceAll("_", " ")}</strong>
                    <p className="car-invite-subtitle">{action.message}</p>
                    <small>{formatDateTime(action.created_at)}</small>
                  </div>
                ))}
              </div>
            </details>
          </aside>
        </div>
      </div>

      {previewEntry && <SubmissionPreview entry={previewEntry} onClose={() => setSubmissionPreviewToken(null)} onConfirm={() => submitInvite(previewEntry.token)} />}

      {selectedPreview && (() => {
        const previewEntryState = entries.find((entry) => entry.token === selectedPreview.token);
        const previewLocked = !isInviteEditable(previewEntryState?.invite ?? null);
        const previewUrl = absoluteApiUrl(selectedPreview.attachment.download_url);
        const contentType = selectedPreview.attachment.content_type || "";
        const filename = selectedPreview.attachment.filename.toLowerCase();
        const isImage = contentType.startsWith("image/");
        const isVideo = contentType.startsWith("video/");
        const isPdf = contentType.includes("pdf") || filename.endsWith(".pdf");
        return (
          <div className="car-invite-modal car-invite-modal--preview" role="dialog" aria-modal="true" aria-label="Evidence preview">
            <div className="car-invite-preview-modal">
              <div className="car-invite-modal__header">
                <div>
                  <p className="car-invite-kicker">Evidence preview • {selectedPreview.carNumber}</p>
                  <h2>{selectedPreview.attachment.description || selectedPreview.attachment.filename}</h2>
                  {selectedPreview.attachment.description && <p className="car-invite-subtitle">{selectedPreview.attachment.filename}</p>}
                </div>
                <div className="car-invite-actions">
                  <button type="button" className="car-invite-icon-btn car-invite-icon-btn--danger" disabled={previewLocked} onClick={() => void deleteInviteAttachment(selectedPreview.token, selectedPreview.attachment.id)} aria-label="Delete evidence"><Trash2 size={18} /></button>
                  <button type="button" className="car-invite-icon-btn" onClick={() => setSelectedPreview(null)} aria-label="Close preview"><X size={18} /></button>
                </div>
              </div>
              <div className="car-invite-preview-surface">
                {isImage && <img src={previewUrl} alt={selectedPreview.attachment.filename} />}
                {isVideo && <video src={previewUrl} controls playsInline />}
                {isPdf && <embed src={previewUrl} type="application/pdf" />}
                {!isImage && !isVideo && !isPdf && <iframe src={previewUrl} title={selectedPreview.attachment.filename} />}
              </div>
            </div>
          </div>
        );
      })()}

      {camera && (
        <div className="car-invite-modal" role="dialog" aria-modal="true" aria-label="Camera capture">
          <div className="car-invite-modal__panel">
            <div className="car-invite-modal__header">
              <div>
                <p className="car-invite-kicker">Camera evidence</p>
                <h2>Capture site photo</h2>
              </div>
              <button type="button" className="car-invite-icon-btn" onClick={stopCamera} aria-label="Close camera"><X size={18} /></button>
            </div>
            {camera.opening && <div className="car-invite-notice"><Camera size={18} /> Opening camera…</div>}
            {camera.error && <div className="car-invite-error"><AlertTriangle size={18} /> {camera.error}</div>}
            {camera.stream && <video ref={videoRef} className="car-invite-camera-video" playsInline muted />}
            <canvas ref={canvasRef} hidden />
            <div className="car-invite-submit-row">
              <button type="button" className="car-invite-btn" onClick={stopCamera}>Cancel</button>
              <button type="button" className="car-invite-btn car-invite-btn--primary" disabled={!camera.stream} onClick={capturePhoto}><Camera size={16} /> Capture and upload</button>
            </div>
          </div>
        </div>
      )}
    </AuthLayout>
  );
};

export default PublicCarInvitePage;
