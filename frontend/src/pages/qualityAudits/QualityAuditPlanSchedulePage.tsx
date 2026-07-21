import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarRange,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Filter,
  ClipboardList,
  ExternalLink,
  HelpCircle,
  LayoutList,
  MailCheck,
  Search,
  ShieldCheck,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
} from "lucide-react";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import "./quality-audit-dashboard.css";
import SectionCard from "../../components/shared/SectionCard";
import Button from "../../components/UI/Button";
import EmptyState from "../../components/shared/EmptyState";
import Drawer from "../../components/shared/Drawer";
import { useToast } from "../../components/feedback/ToastProvider";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsDeleteAudit,
  qmsDeleteAuditSchedule,
  qmsListAuditPersonnelOptions,
  qmsListAuditScopes,
  qmsCreateAuditScope,
  qmsUpdateAuditScope,
  qmsListAudits,
  qmsListAuditSchedules,
  qmsRunAuditSchedule,
  qmsUpdateAudit,
  qmsUpdateAuditSchedule,
  type QMSAuditOut,
  type QMSAuditScheduleFrequency,
  type QMSAuditScheduleOut,
  type QMSAuditScopeOut,
  type QMSExternalAuditeeContact,
  type QMSPersonOption,
} from "../../services/qms";
import { getQmsCalendar } from "../../services/qmsCalendar";

type PlannerView = "calendar" | "list" | "table";
type PlannedRecordFilter = "all" | "needsAssignment" | "scheduled" | "dueSoon" | "deferred";
type PlannedRecordDensity = "comfortable" | "compact";
type DrawerTab = "overview" | "participants" | "review";
type AuditKind = "INTERNAL" | "EXTERNAL" | "THIRD_PARTY";

type AuditScopeFormState = {
  id: string | null;
  code: string;
  name: string;
  description: string;
  party_level: "FIRST_PARTY" | "SECOND_PARTY" | "THIRD_PARTY" | "REGULATORY";
  default_kind: AuditKind;
  is_active: boolean;
  sort_order: string;
};

type ScheduleViewModel = QMSAuditScheduleOut & {
  is_preview?: boolean;
  preview_label?: string;
};

type PlannerCalendarItem = {
  id: string;
  source: "audit" | "schedule";
  title: string;
  kind: string;
  date: string;
  ref?: string | null;
  status?: string | null;
  auditee?: string | null;
  lead_auditor_user_id?: string | null;
  is_preview?: boolean;
  schedule?: ScheduleViewModel;
  audit?: QMSAuditOut;
  link?: string | null;
};

type PersonSearchField =
  | "auditee_user_id"
  | "lead_auditor_user_id"
  | "observer_auditor_user_id"
  | "assistant_auditor_user_id";

type ScheduleFormState = {
  title: string;
  kind: AuditKind;
  audit_scope_code: string;
  frequency: QMSAuditScheduleFrequency;
  next_due_date: string;
  duration_days: string;
  scope: string;
  criteria: string;
  auditee: string;
  auditee_email: string;
  auditee_user_id: string;
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  assistant_auditor_user_id: string;
  external_auditees: QMSExternalAuditeeContact[];
  notify_auditors: boolean;
  notify_auditees: boolean;
  reminder_interval_days: string;
  is_active: boolean;
};

type PlannedAuditFormState = {
  title: string;
  kind: AuditKind;
  audit_scope_code: string;
  planned_start: string;
  planned_end: string;
  scope: string;
  criteria: string;
  auditee: string;
  auditee_email: string;
  auditee_user_id: string;
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  assistant_auditor_user_id: string;
  notify_auditors: boolean;
  notify_auditees: boolean;
  reminder_interval_days: string;
};

const frequencies: QMSAuditScheduleFrequency[] = ["ONE_TIME", "MONTHLY", "QUARTERLY", "BI_ANNUAL", "ANNUAL"];
const auditKinds: Array<{ value: AuditKind; label: string; helper: string }> = [
  { value: "INTERNAL", label: "Internal", helper: "Use internal personnel records for auditee and audit team selection." },
  { value: "EXTERNAL", label: "External", helper: "Capture named external auditees, their roles, and contact details." },
  { value: "THIRD_PARTY", label: "Third party", helper: "Use named external auditees for regulatory, customer, or certification audits." },
];
const weekdayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const drawerTabs: Array<{ id: DrawerTab; label: string; helper: string }> = [
  { id: "overview", label: "Overview", helper: "Audit identity, scope, window, and cadence" },
  { id: "participants", label: "Participants", helper: "Internal team or external auditee contacts" },
  { id: "review", label: "Review", helper: "Lifecycle summary, notices, and confirmation" },
];

const defaultExternalAuditee = (): QMSExternalAuditeeContact => ({
  first_name: "",
  last_name: "",
  email: "",
  phone_contact: "",
  designation: "",
});

const defaultSchedule: ScheduleFormState = {
  title: "",
  kind: "INTERNAL",
  audit_scope_code: "MO",
  frequency: "QUARTERLY",
  next_due_date: "",
  duration_days: "3",
  scope: "",
  criteria: "",
  auditee: "",
  auditee_email: "",
  auditee_user_id: "",
  lead_auditor_user_id: "",
  observer_auditor_user_id: "",
  assistant_auditor_user_id: "",
  external_auditees: [defaultExternalAuditee()],
  notify_auditors: true,
  notify_auditees: true,
  reminder_interval_days: "7",
  is_active: true,
};

const defaultPlannedAudit: PlannedAuditFormState = {
  title: "",
  kind: "INTERNAL",
  audit_scope_code: "MO",
  planned_start: "",
  planned_end: "",
  scope: "",
  criteria: "",
  auditee: "",
  auditee_email: "",
  auditee_user_id: "",
  lead_auditor_user_id: "",
  observer_auditor_user_id: "",
  assistant_auditor_user_id: "",
  notify_auditors: true,
  notify_auditees: true,
  reminder_interval_days: "7",
};

const defaultAuditScopeForm: AuditScopeFormState = {
  id: null,
  code: "",
  name: "",
  description: "",
  party_level: "FIRST_PARTY",
  default_kind: "INTERNAL",
  is_active: true,
  sort_order: "100",
};

function plannerViewOptions() {
  return [
    { value: "calendar" as PlannerView, label: "Calendar", icon: CalendarRange },
    { value: "list" as PlannerView, label: "List", icon: LayoutList },
    { value: "table" as PlannerView, label: "Table", icon: ClipboardList },
  ];
}

function normalizeNullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function formatFrequencyLabel(value: QMSAuditScheduleFrequency): string {
  return value.replaceAll("_", " ");
}

function formatKindLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

function addMonthsDateOnly(months: number): string {
  const date = new Date();
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() + months);
  return date.toISOString().slice(0, 10);
}

function userLabel(user?: QMSPersonOption | null): string {
  if (!user) return "Unassigned";
  return user.position_title ? `${user.full_name} · ${user.position_title}` : user.full_name;
}
function initialsForName(value?: string | null): string {
  const cleaned = (value || "").trim();
  if (!cleaned) return "--";
  const parts = cleaned.split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || cleaned.slice(0, 2).toUpperCase();
}

function getStoredAvatarUrl(userId?: string | null): string | null {
  if (!userId || typeof window === "undefined") return null;
  return window.localStorage.getItem(`amo_portal_profile_avatar:${userId}`);
}

function personRoleLabel(role: string): string {
  return role.replaceAll("_", " ");
}

const PersonAvatar: React.FC<{ person?: QMSPersonOption | null; fallback?: string | null; label?: string; size?: "sm" | "md" }> = ({ person, fallback, label, size = "md" }) => {
  const src = getStoredAvatarUrl(person?.id);
  const name = person?.full_name || fallback || label || "User";
  return (
    <span className={`qa-person-avatar qa-person-avatar--${size}`} title={name}>
      {src ? <img src={src} alt={name} /> : <span>{initialsForName(name)}</span>}
    </span>
  );
};

const PersonChip: React.FC<{ person?: QMSPersonOption | null; fallback?: string | null; label: string; muted?: boolean }> = ({ person, fallback, label, muted }) => (
  <span className={`qa-person-chip${muted ? " is-muted" : ""}`}>
    <PersonAvatar person={person} fallback={fallback} size="sm" />
    <span>
      <small>{label}</small>
      <strong>{person ? person.full_name : fallback || "Unassigned"}</strong>
    </span>
  </span>
);

function auditWindowLabel(audit: QMSAuditOut): { text: string; className: string; bucket: PlannedRecordFilter } {
  if (!audit.planned_start) return { text: "Date pending", className: "audit-countdown-chip", bucket: "needsAssignment" };
  const start = new Date(audit.planned_start);
  if (Number.isNaN(start.getTime())) return { text: audit.planned_start, className: "audit-countdown-chip", bucket: "scheduled" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  start.setHours(0, 0, 0, 0);
  const diffDays = Math.round((start.getTime() - today.getTime()) / 86_400_000);
  if (!audit.lead_auditor_user_id) return { text: diffDays >= 0 ? `Starts in ${diffDays} day(s)` : `${Math.abs(diffDays)} day(s) overdue`, className: "audit-countdown-chip is-warning", bucket: "needsAssignment" };
  if (diffDays < 0) return { text: `${Math.abs(diffDays)} day(s) overdue`, className: "audit-countdown-chip is-overdue", bucket: "deferred" };
  if (diffDays <= 30) return { text: diffDays === 0 ? "Due today" : `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip is-due-soon", bucket: "dueSoon" };
  return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip", bucket: "scheduled" };
}

function auditCalendarDate(audit: QMSAuditOut): string | null {
  return audit.planned_start || audit.planned_end || audit.actual_start || audit.actual_end || null;
}

function auditDisplayAuditee(audit: QMSAuditOut, peopleById: Map<string, QMSPersonOption>): string {
  const internalAuditee = audit.auditee_user_id ? peopleById.get(audit.auditee_user_id) : null;
  return internalAuditee?.full_name || audit.auditee || audit.auditee_email || "Auditee not set";
}

function groupAuditLabel(key: PlannedRecordFilter): string {
  if (key === "needsAssignment") return "Needs assignment";
  if (key === "dueSoon") return "Due soon";
  if (key === "deferred") return "Deferred / overdue";
  if (key === "scheduled") return "Scheduled and ready";
  return "All planned records";
}

function matchesAuditSearch(audit: QMSAuditOut, query: string, peopleById: Map<string, QMSPersonOption>): boolean {
  const cleaned = query.trim().toLowerCase();
  if (!cleaned) return true;
  const lead = audit.lead_auditor_user_id ? peopleById.get(audit.lead_auditor_user_id)?.full_name || "" : "";
  const auditee = audit.auditee_user_id ? peopleById.get(audit.auditee_user_id)?.full_name || "" : "";
  return [audit.audit_ref, audit.title, audit.kind, audit.status, audit.auditee || "", audit.auditee_email || "", audit.scope || "", lead, auditee].join(" ").toLowerCase().includes(cleaned);
}


function personSearchLabel(person: QMSPersonOption | null | undefined): string {
  if (!person) return "";
  return person.full_name;
}

function personSearchMeta(person: QMSPersonOption | null | undefined): string {
  if (!person) return "";
  return [person.position_title, person.staff_code].filter(Boolean).join(" · ");
}

function matchesPerson(person: QMSPersonOption, rawQuery: string): boolean {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return true;
  const haystack = [
    person.full_name,
    person.staff_code || "",
    person.email || "",
    person.id,
    person.position_title || "",
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function findExactPerson(options: QMSPersonOption[], rawQuery: string): QMSPersonOption | null {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return null;
  return (
    options.find((person) => {
      const exactCandidates = [person.full_name, person.staff_code || "", person.email || "", person.id]
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean);
      return exactCandidates.includes(query);
    }) || null
  );
}

function countdownLabel(nextDueDate?: string | null): { text: string; className: string } {
  if (!nextDueDate) return { text: "Due date pending", className: "audit-countdown-chip" };
  const target = new Date(nextDueDate);
  if (Number.isNaN(target.getTime())) return { text: nextDueDate, className: "audit-countdown-chip" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (diffDays < 0) return { text: `${Math.abs(diffDays)} day(s) overdue`, className: "audit-countdown-chip is-overdue" };
  if (diffDays === 0) return { text: "Due today", className: "audit-countdown-chip is-due-soon" };
  if (diffDays <= 14) return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip is-due-soon" };
  return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip" };
}


function auditToForm(audit: QMSAuditOut): PlannedAuditFormState {
  return {
    title: audit.title || "",
    kind: (audit.kind || "INTERNAL") as AuditKind,
    audit_scope_code: audit.audit_scope_code || "MO",
    planned_start: audit.planned_start || "",
    planned_end: audit.planned_end || audit.planned_start || "",
    scope: audit.scope || "",
    criteria: audit.criteria || "",
    auditee: audit.auditee || "",
    auditee_email: audit.auditee_email || "",
    auditee_user_id: audit.auditee_user_id || "",
    lead_auditor_user_id: audit.lead_auditor_user_id || "",
    observer_auditor_user_id: audit.observer_auditor_user_id || "",
    assistant_auditor_user_id: audit.assistant_auditor_user_id || "",
    notify_auditors: audit.notify_auditors ?? true,
    notify_auditees: audit.notify_auditees ?? true,
    reminder_interval_days: String(audit.reminder_interval_days ?? 7),
  };
}

function monthGrid(seedDate: Date) {
  const start = new Date(seedDate.getFullYear(), seedDate.getMonth(), 1);
  const end = new Date(seedDate.getFullYear(), seedDate.getMonth() + 1, 0);
  const firstWeekday = (start.getDay() + 6) % 7;
  const daysInMonth = end.getDate();
  const cells: Array<{ key: string; date: Date; inMonth: boolean; isToday: boolean }> = [];
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - firstWeekday);
  for (let i = 0; i < 42; i += 1) {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + i);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const compare = new Date(day);
    compare.setHours(0, 0, 0, 0);
    cells.push({
      key: compare.toISOString(),
      date: day,
      inMonth: day.getMonth() === start.getMonth() && day.getDate() <= daysInMonth,
      isToday: compare.getTime() === today.getTime(),
    });
  }
  return cells;
}

function cleanExternalAuditees(items: QMSExternalAuditeeContact[]): QMSExternalAuditeeContact[] {
  return items
    .map((item) => ({
      first_name: item.first_name.trim(),
      last_name: item.last_name.trim(),
      email: item.email.trim(),
      phone_contact: item.phone_contact?.trim() || null,
      designation: item.designation.trim(),
    }))
    .filter((item) => item.first_name || item.last_name || item.email || item.designation);
}

function validateExternalAuditees(items: QMSExternalAuditeeContact[]): string | null {
  const cleaned = cleanExternalAuditees(items);
  if (!cleaned.length) return "Add at least one external auditee for external or third-party audits.";
  const invalid = cleaned.find((item) => !item.first_name || !item.last_name || !item.email || !item.designation);
  if (invalid) return "Each external auditee must have first name, last name, email, and designation.";
  return null;
}

function formToPayload(form: ScheduleFormState) {
  const cleanedExternalAuditees = cleanExternalAuditees(form.external_auditees);
  const firstExternal = cleanedExternalAuditees[0];
  return {
    domain: "AMO",
    title: form.title.trim(),
    kind: form.kind,
    audit_scope_code: form.audit_scope_code || undefined,
    frequency: form.frequency,
    next_due_date: form.next_due_date,
    duration_days: Math.max(1, Number(form.duration_days) || 1),
    scope: normalizeNullable(form.scope),
    criteria: normalizeNullable(form.criteria),
    auditee:
      form.kind === "INTERNAL"
        ? normalizeNullable(form.auditee)
        : firstExternal
          ? `${firstExternal.first_name} ${firstExternal.last_name}`.trim()
          : normalizeNullable(form.auditee),
    auditee_email: form.kind === "INTERNAL" ? normalizeNullable(form.auditee_email) : firstExternal?.email ?? normalizeNullable(form.auditee_email),
    auditee_user_id: form.kind === "INTERNAL" ? normalizeNullable(form.auditee_user_id) : null,
    external_auditees: form.kind === "INTERNAL" ? [] : cleanedExternalAuditees,
    lead_auditor_user_id: normalizeNullable(form.lead_auditor_user_id),
    observer_auditor_user_id: normalizeNullable(form.observer_auditor_user_id),
    assistant_auditor_user_id: normalizeNullable(form.assistant_auditor_user_id),
    notify_auditors: form.notify_auditors,
    notify_auditees: form.notify_auditees,
    reminder_interval_days: Math.max(1, Number(form.reminder_interval_days) || 7),
    is_active: form.is_active,
  };
}

function isMeaningfulDraft(form: ScheduleFormState): boolean {
  const externalCount = cleanExternalAuditees(form.external_auditees).length;
  return Object.entries(form).some(([key, value]) => {
    if (key === "frequency") return value !== defaultSchedule.frequency;
    if (key === "duration_days") return value !== defaultSchedule.duration_days;
    if (key === "kind") return value !== defaultSchedule.kind;
    if (key === "audit_scope_code") return value !== defaultSchedule.audit_scope_code;
    if (key === "notify_auditors") return value !== defaultSchedule.notify_auditors;
    if (key === "notify_auditees") return value !== defaultSchedule.notify_auditees;
    if (key === "reminder_interval_days") return value !== defaultSchedule.reminder_interval_days;
    if (key === "is_active") return value !== defaultSchedule.is_active;
    if (key === "external_auditees") return externalCount > 0 && JSON.stringify(value) !== JSON.stringify(defaultSchedule.external_auditees);
    return String(value).trim().length > 0;
  });
}

function scheduleToForm(schedule: QMSAuditScheduleOut): ScheduleFormState {
  return {
    title: schedule.title || "",
    kind: (schedule.kind || "INTERNAL") as AuditKind,
    audit_scope_code: schedule.audit_scope_code || "MO",
    frequency: schedule.frequency,
    next_due_date: schedule.next_due_date || "",
    duration_days: String(Math.max(1, schedule.duration_days || 1)),
    scope: schedule.scope || "",
    criteria: schedule.criteria || "",
    auditee: schedule.auditee || "",
    auditee_email: schedule.auditee_email || "",
    auditee_user_id: schedule.auditee_user_id || "",
    lead_auditor_user_id: schedule.lead_auditor_user_id || "",
    observer_auditor_user_id: schedule.observer_auditor_user_id || "",
    assistant_auditor_user_id: schedule.assistant_auditor_user_id || "",
    external_auditees: schedule.external_auditees?.length ? schedule.external_auditees : [defaultExternalAuditee()],
    notify_auditors: schedule.notify_auditors ?? true,
    notify_auditees: schedule.notify_auditees ?? true,
    reminder_interval_days: String(schedule.reminder_interval_days ?? 7),
    is_active: schedule.is_active,
  };
}

const PersonLookupField: React.FC<{
  label: string;
  value: string;
  query: string;
  options: QMSPersonOption[];
  placeholder: string;
  helper?: string;
  onQueryChange: (value: string) => void;
  onSelect: (personId: string) => void;
}> = ({ label, value, query, options, placeholder, helper, onQueryChange, onSelect }) => {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const filtered = useMemo(() => options.filter((person) => matchesPerson(person, query)).slice(0, 8), [options, query]);

  useEffect(() => {
    const handleDown = (event: MouseEvent) => {
      if (!wrapperRef.current) return;
      if (event.target instanceof Node && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", handleDown);
    return () => window.removeEventListener("mousedown", handleDown);
  }, []);

  return (
    <div className="profile-inline-field planner-person-field" ref={wrapperRef}>
      <span>{label}</span>
      <input
        className="input"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setOpen(true);
          onQueryChange(e.target.value);
        }}
        placeholder={placeholder}
      />
      <input type="hidden" value={value} readOnly />
      {helper ? <small className="planner-field-help">{helper}</small> : null}
      {open && query.trim() ? (
        <div className="planner-person-picker" role="listbox" aria-label={label}>
          {filtered.length ? (
            filtered.map((person) => (
              <button
                key={person.id}
                type="button"
                className="planner-person-picker__item"
                onClick={() => {
                  onSelect(person.id);
                  setOpen(false);
                }}
              >
                <strong>{person.full_name}</strong>
                <span>{personSearchMeta(person) || person.email || person.id}</span>
              </button>
            ))
          ) : (
            <div className="planner-person-picker__empty">No matching internal user found.</div>
          )}
        </div>
      ) : null}
    </div>
  );
};

const QualityAuditPlanSchedulePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const { pushToast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [form, setForm] = useState<ScheduleFormState>(defaultSchedule);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState(false);
  const [scopeDrawerOpen, setScopeDrawerOpen] = useState(false);
  const [scopeForm, setScopeForm] = useState<AuditScopeFormState>(defaultAuditScopeForm);
  const [auditForm, setAuditForm] = useState<PlannedAuditFormState>(defaultPlannedAudit);
  const [editingAuditId, setEditingAuditId] = useState<string | null>(null);
  const [visibleMonth, setVisibleMonth] = useState<Date | null>(null);
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("overview");
  const [personSearch, setPersonSearch] = useState<Record<PersonSearchField, string>>({
    auditee_user_id: "",
    lead_auditor_user_id: "",
    observer_auditor_user_id: "",
    assistant_auditor_user_id: "",
  });
  const [guideDismissed, setGuideDismissed] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [recordFilter, setRecordFilter] = useState<PlannedRecordFilter>("all");
  const [recordSearch, setRecordSearch] = useState("");
  const [recordDensity, setRecordDensity] = useState<PlannedRecordDensity>("compact");
  const [expandedAuditIds, setExpandedAuditIds] = useState<Set<string>>(new Set());
  const [collapsedAuditGroups, setCollapsedAuditGroups] = useState<Set<PlannedRecordFilter>>(new Set());
  const [auditPersonSearch, setAuditPersonSearch] = useState<Record<PersonSearchField, string>>({
    auditee_user_id: "",
    lead_auditor_user_id: "",
    observer_auditor_user_id: "",
    assistant_auditor_user_id: "",
  });
  const queryClient = useQueryClient();
  const draftStorageKey = useMemo(() => `qms-audit-schedule-draft:${amoCode}:${department}`, [amoCode, department]);
  const guideStorageKey = useMemo(() => `qms-audit-planner-guide-dismissed:${amoCode}`, [amoCode]);

  const rawView = searchParams.get("view") || "calendar";
  const view = (["calendar", "list", "table"].includes(rawView) ? rawView : "calendar") as PlannerView;

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode, department],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const plannedAuditsQuery = useQuery({
    queryKey: ["qms-audits-planned", amoCode, department],
    queryFn: () => qmsListAudits({ domain: "AMO", status_: "PLANNED" }),
    staleTime: 30_000,
  });

  const auditCalendarIntegrationQuery = useQuery({
    queryKey: ["qms-audit-planner-calendar-integration", amoCode],
    queryFn: () => getQmsCalendar(amoCode, {
      source: "audits",
      start: addMonthsDateOnly(-3),
      end: addMonthsDateOnly(18),
      limit: 300,
    }),
    staleTime: 60_000,
  });

  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", amoCode],
    queryFn: () => qmsListAuditPersonnelOptions({ limit: 100 }),
    staleTime: 5 * 60_000,
  });

  const auditScopesQuery = useQuery({
    queryKey: ["qms-audit-scopes", amoCode],
    queryFn: () => qmsListAuditScopes({ active: true }),
    staleTime: 5 * 60_000,
  });

  const schedules = schedulesQuery.data ?? [];
  const plannedAudits = plannedAuditsQuery.data ?? [];
  const personnelOptions = personnelQuery.data ?? [];
  const auditScopes = auditScopesQuery.data ?? [];
  const peopleById = useMemo(() => {
    const next = new Map<string, QMSPersonOption>();
    personnelOptions.forEach((person) => next.set(person.id, person));
    return next;
  }, [personnelOptions]);
  const scopeByCode = useMemo(() => {
    const next = new Map<string, QMSAuditScopeOut>();
    auditScopes.forEach((scope) => next.set(scope.code, scope));
    return next;
  }, [auditScopes]);

  const beginScopeEdit = (scope?: QMSAuditScopeOut) => {
    setScopeForm(scope ? {
      id: scope.id,
      code: scope.code,
      name: scope.name,
      description: scope.description || "",
      party_level: (scope.party_level as AuditScopeFormState["party_level"]) || "FIRST_PARTY",
      default_kind: (scope.default_kind || "INTERNAL") as AuditKind,
      is_active: scope.is_active,
      sort_order: String(scope.sort_order ?? 100),
    } : defaultAuditScopeForm);
    setScopeDrawerOpen(true);
  };

  const saveAuditScope = useMutation({
    mutationFn: async () => {
      if (!scopeForm.code.trim()) throw new Error("Scope code is required.");
      if (!scopeForm.name.trim()) throw new Error("Scope name is required.");
      const payload = {
        code: scopeForm.code.trim().toUpperCase(),
        name: scopeForm.name.trim(),
        description: scopeForm.description.trim() || null,
        party_level: scopeForm.party_level,
        default_kind: scopeForm.default_kind,
        is_active: scopeForm.is_active,
        sort_order: Math.max(0, Number(scopeForm.sort_order) || 100),
      };
      return scopeForm.id ? qmsUpdateAuditScope(scopeForm.id, payload) : qmsCreateAuditScope(payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-scopes", amoCode] });
      setScopeForm(defaultAuditScopeForm);
      setScopeDrawerOpen(false);
      pushToast({ title: "Audit scope saved", message: "Future audit references will use the configured scope code.", variant: "success" });
    },
    onError: (e: Error) => pushToast({ title: "Scope not saved", message: e.message || "The audit scope could not be saved.", variant: "error" }),
  });

  const plannedRecordStats = useMemo(() => {
    const buckets: Record<PlannedRecordFilter, number> = { all: plannedAudits.length, needsAssignment: 0, scheduled: 0, dueSoon: 0, deferred: 0 };
    plannedAudits.forEach((audit) => {
      const bucket = auditWindowLabel(audit).bucket;
      buckets[bucket] += 1;
    });
    return buckets;
  }, [plannedAudits]);

  const filteredPlannedAudits = useMemo(() => plannedAudits
    .filter((audit) => recordFilter === "all" || auditWindowLabel(audit).bucket === recordFilter)
    .filter((audit) => matchesAuditSearch(audit, recordSearch, peopleById))
    .sort((a, b) => (a.planned_start || a.planned_end || "").localeCompare(b.planned_start || b.planned_end || "")), [peopleById, plannedAudits, recordFilter, recordSearch]);

  const groupedPlannedAudits = useMemo(() => {
    const order: PlannedRecordFilter[] = ["needsAssignment", "dueSoon", "scheduled", "deferred"];
    const groups = new Map<PlannedRecordFilter, QMSAuditOut[]>();
    order.forEach((key) => groups.set(key, []));
    filteredPlannedAudits.forEach((audit) => {
      const key = auditWindowLabel(audit).bucket;
      groups.get(key)?.push(audit);
    });
    return order.map((key) => ({ key, label: groupAuditLabel(key), audits: groups.get(key) || [] })).filter((group) => group.audits.length > 0);
  }, [filteredPlannedAudits]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(draftStorageKey);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { form?: ScheduleFormState; editingScheduleId?: string | null };
      if (parsed.form) {
        setForm({ ...defaultSchedule, ...parsed.form, external_auditees: parsed.form.external_auditees?.length ? parsed.form.external_auditees : [defaultExternalAuditee()] });
      }
      if (parsed.editingScheduleId) setEditingScheduleId(parsed.editingScheduleId);
    } catch {
      window.localStorage.removeItem(draftStorageKey);
    }
  }, [draftStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setGuideDismissed(window.localStorage.getItem(guideStorageKey) === "1");
  }, [guideStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!isMeaningfulDraft(form) && !editingScheduleId) {
      window.localStorage.removeItem(draftStorageKey);
      return;
    }
    window.localStorage.setItem(draftStorageKey, JSON.stringify({ form, editingScheduleId, savedAt: new Date().toISOString() }));
  }, [draftStorageKey, editingScheduleId, form]);

  const previewSchedule = useMemo<ScheduleViewModel | null>(() => {
    if (!form.title.trim() || !form.next_due_date) return null;
    return {
      id: editingScheduleId || "preview-schedule",
      amo_id: null,
      domain: "AMO",
      kind: form.kind,
      audit_scope_code: form.audit_scope_code,
      frequency: form.frequency,
      title: form.title.trim(),
      scope: form.scope.trim() || null,
      criteria: form.criteria.trim() || null,
      auditee: form.auditee.trim() || null,
      auditee_email: form.auditee_email.trim() || null,
      auditee_user_id: form.auditee_user_id.trim() || null,
      external_auditees: form.kind === "INTERNAL" ? [] : cleanExternalAuditees(form.external_auditees),
      lead_auditor_user_id: form.lead_auditor_user_id.trim() || null,
      observer_auditor_user_id: form.observer_auditor_user_id.trim() || null,
      assistant_auditor_user_id: form.assistant_auditor_user_id.trim() || null,
      notify_auditors: form.notify_auditors,
      notify_auditees: form.notify_auditees,
      reminder_interval_days: Math.max(1, Number(form.reminder_interval_days) || 7),
      duration_days: Math.max(1, Number(form.duration_days) || 1),
      next_due_date: form.next_due_date,
      last_run_at: null,
      is_active: form.is_active,
      created_by_user_id: null,
      created_at: new Date().toISOString(),
      is_preview: true,
      preview_label: editingScheduleId ? "Editing draft" : "Unsaved draft",
    };
  }, [editingScheduleId, form]);

  const boardSchedules = useMemo<ScheduleViewModel[]>(() => {
    const merged: ScheduleViewModel[] = [...schedules];
    if (previewSchedule) {
      const existingIndex = merged.findIndex((row) => row.id === previewSchedule.id);
      if (existingIndex >= 0) merged[existingIndex] = previewSchedule;
      else merged.unshift(previewSchedule);
    }
    return merged.sort((a, b) => (a.next_due_date || "").localeCompare(b.next_due_date || ""));
  }, [previewSchedule, schedules]);

  const plannerCalendarItems = useMemo<PlannerCalendarItem[]>(() => {
    const scheduleItems: PlannerCalendarItem[] = boardSchedules
      .filter((schedule) => Boolean(schedule.next_due_date))
      .map((schedule) => ({
        id: `schedule:${schedule.id}`,
        source: "schedule",
        title: schedule.title,
        kind: schedule.kind,
        date: schedule.next_due_date,
        status: schedule.is_active ? "ACTIVE" : "PAUSED",
        auditee: schedule.auditee || schedule.auditee_email || null,
        lead_auditor_user_id: schedule.lead_auditor_user_id,
        is_preview: schedule.is_preview,
        schedule,
      }));
    const auditItems: PlannerCalendarItem[] = plannedAudits
      .map<PlannerCalendarItem | null>((audit) => {
        const date = auditCalendarDate(audit);
        if (!date) return null;
        return {
          id: `audit:${audit.id}`,
          source: "audit" as const,
          title: audit.title,
          kind: audit.kind,
          date,
          ref: audit.audit_ref,
          status: audit.status,
          auditee: auditDisplayAuditee(audit, peopleById),
          lead_auditor_user_id: audit.lead_auditor_user_id,
          audit,
        };
      })
      .filter((item): item is PlannerCalendarItem => item !== null);

    const existingKeys = new Set([...auditItems, ...scheduleItems].map((item) => `${item.source}:${item.date}:${item.title.trim().toLowerCase()}:${item.kind}`));
    const integrationItems: PlannerCalendarItem[] = (auditCalendarIntegrationQuery.data?.items ?? [])
      .filter((event) => event.module === "audits" && Boolean(event.date))
      .map((event) => {
        const source = event.entity_type === "audit_schedule" ? "schedule" as const : "audit" as const;
        const title = String(event.title || event.audit_ref || "Audit commitment");
        const item: PlannerCalendarItem = {
          id: `integration:${event.entity_type}:${event.entity_id}:${event.date}`,
          source,
          title,
          kind: event.kind || "AUDIT",
          date: String(event.date),
          ref: event.audit_ref || null,
          status: event.status || event.event_type || null,
          auditee: event.auditee || event.auditee_email || null,
          lead_auditor_user_id: event.lead_auditor_user_id || null,
          link: event.link || null,
        };
        return item;
      })
      .filter((item) => {
        const key = `${item.source}:${item.date}:${item.title.trim().toLowerCase()}:${item.kind}`;
        if (existingKeys.has(key)) return false;
        existingKeys.add(key);
        return true;
      });

    return [...auditItems, ...scheduleItems, ...integrationItems].sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title));
  }, [auditCalendarIntegrationQuery.data?.items, boardSchedules, peopleById, plannedAudits]);

  const seedDate = useMemo(() => {
    const firstDue = plannerCalendarItems[0]?.date;
    return firstDue ? new Date(firstDue) : new Date();
  }, [plannerCalendarItems]);

  useEffect(() => {
    setVisibleMonth((prev) => prev ?? new Date(seedDate.getFullYear(), seedDate.getMonth(), 1));
  }, [seedDate]);

  const activeCalendarMonth = visibleMonth ?? new Date(seedDate.getFullYear(), seedDate.getMonth(), 1);
  const calendarCells = useMemo(() => monthGrid(activeCalendarMonth), [activeCalendarMonth]);

  const scheduleSummary = useMemo(
    () => [
      { label: "Calendar items", value: String(plannerCalendarItems.length) },
      { label: "Live planned", value: String(plannedAudits.length) },
      { label: "Next due", value: plannerCalendarItems[0]?.date ? formatDate(plannerCalendarItems[0].date) : "Not scheduled" },
      {
        label: editingScheduleId ? "Editing" : isMeaningfulDraft(form) ? "Staged draft" : "Draft state",
        value: editingScheduleId ? "Existing schedule" : isMeaningfulDraft(form) ? "Autosaved" : "Clean",
      },
    ],
    [editingScheduleId, form, plannedAudits.length, plannerCalendarItems]
  );

  const leadAuditorUser = form.lead_auditor_user_id ? peopleById.get(form.lead_auditor_user_id) ?? null : null;
  const observerAuditorUser = form.observer_auditor_user_id ? peopleById.get(form.observer_auditor_user_id) ?? null : null;
  const assistantAuditorUser = form.assistant_auditor_user_id ? peopleById.get(form.assistant_auditor_user_id) ?? null : null;
  const auditeeUser = form.auditee_user_id ? peopleById.get(form.auditee_user_id) ?? null : null;
  const cleanedExternalAuditees = useMemo(() => cleanExternalAuditees(form.external_auditees), [form.external_auditees]);
  const recipientSummary = useMemo(() => {
    const items: Array<{ key: string; label: string; value: string; muted?: boolean }> = [];
    if (form.notify_auditors) {
      const team = [leadAuditorUser, observerAuditorUser, assistantAuditorUser].filter(Boolean) as QMSPersonOption[];
      items.push({
        key: "auditors",
        label: "Auditor notices",
        value: team.length ? team.map((person) => person.full_name).join(", ") : "No auditor selected yet.",
        muted: !team.length,
      });
    }
    if (form.notify_auditees) {
      if (form.kind === "INTERNAL") {
        items.push({
          key: "auditee-internal",
          label: "Auditee notices",
          value: auditeeUser ? `${auditeeUser.full_name}${auditeeUser.email ? ` · ${auditeeUser.email}` : ""}` : form.auditee_email.trim() || "No internal auditee contact selected yet.",
          muted: !auditeeUser && !form.auditee_email.trim(),
        });
      } else {
        items.push({
          key: "auditee-external",
          label: "Auditee notices",
          value: cleanedExternalAuditees.length
            ? cleanedExternalAuditees.map((person) => `${person.first_name} ${person.last_name}`).join(", ")
            : "No external auditee contact added yet.",
          muted: !cleanedExternalAuditees.length,
        });
      }
    }
    if (!items.length) {
      items.push({
        key: "none",
        label: "Notification plan",
        value: "Notices are disabled for this schedule.",
        muted: true,
      });
    }
    return items;
  }, [assistantAuditorUser, auditeeUser, cleanedExternalAuditees, form.auditee_email, form.kind, form.notify_auditees, form.notify_auditors, leadAuditorUser, observerAuditorUser]);

  const activeDrawerTabIndex = drawerTabs.findIndex((tab) => tab.id === drawerTab);
  const canGoBackDrawerTab = activeDrawerTabIndex > 0;
  const canGoForwardDrawerTab = activeDrawerTabIndex < drawerTabs.length - 1;

  const setField = <K extends keyof ScheduleFormState>(key: K, value: ScheduleFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const applyScheduleScopeCode = (code: string) => {
    const scope = scopeByCode.get(code);
    setForm((prev) => ({
      ...prev,
      audit_scope_code: code,
      kind: ((scope?.default_kind || prev.kind) as AuditKind),
      title: prev.title.trim() ? prev.title : scope?.name || prev.title,
    }));
  };

  const applyPlannedAuditScopeCode = (code: string) => {
    const scope = scopeByCode.get(code);
    setAuditForm((prev) => ({
      ...prev,
      audit_scope_code: code,
      kind: ((scope?.default_kind || prev.kind) as AuditKind),
      title: prev.title.trim() ? prev.title : scope?.name || prev.title,
    }));
  };

  const setExternalAuditeeField = (index: number, key: keyof QMSExternalAuditeeContact, value: string) => {
    setForm((prev) => ({
      ...prev,
      external_auditees: prev.external_auditees.map((item, itemIndex) => (itemIndex === index ? { ...item, [key]: value } : item)),
    }));
  };

  const addExternalAuditee = () => {
    setForm((prev) => ({ ...prev, external_auditees: [...prev.external_auditees, defaultExternalAuditee()] }));
  };

  const removeExternalAuditee = (index: number) => {
    setForm((prev) => ({
      ...prev,
      external_auditees: prev.external_auditees.length === 1 ? [defaultExternalAuditee()] : prev.external_auditees.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const syncPersonSearch = (field: PersonSearchField, personId: string) => {
    const person = peopleById.get(personId);
    setPersonSearch((prev) => ({ ...prev, [field]: personSearchLabel(person) }));
  };

  const applyPerson = (field: PersonSearchField, personId: string) => {
    const person = peopleById.get(personId);
    setForm((prev) => {
      const next: ScheduleFormState = { ...prev, [field]: personId } as ScheduleFormState;
      if (field === "auditee_user_id") {
        next.auditee = person?.full_name ?? prev.auditee;
        next.auditee_email = person?.email ?? prev.auditee_email;
      }
      return next;
    });
    syncPersonSearch(field, personId);
  };

  const updatePersonLookup = (field: PersonSearchField, rawValue: string) => {
    setPersonSearch((prev) => ({ ...prev, [field]: rawValue }));
    const exact = findExactPerson(personnelOptions, rawValue);
    if (exact) applyPerson(field, exact.id);
  };

  const applyAuditPerson = (field: PersonSearchField, personId: string) => {
    const person = peopleById.get(personId);
    setAuditForm((prev) => {
      const next: PlannedAuditFormState = { ...prev, [field]: personId } as PlannedAuditFormState;
      if (field === "auditee_user_id") {
        next.auditee = person?.full_name ?? prev.auditee;
        next.auditee_email = person?.email ?? prev.auditee_email;
      }
      return next;
    });
    setAuditPersonSearch((prev) => ({ ...prev, [field]: personSearchLabel(person) }));
  };

  const updateAuditPersonLookup = (field: PersonSearchField, rawValue: string) => {
    setAuditPersonSearch((prev) => ({ ...prev, [field]: rawValue }));
    const exact = findExactPerson(personnelOptions, rawValue);
    if (exact) applyAuditPerson(field, exact.id);
  };

  const beginEditAudit = (audit: QMSAuditOut) => {
    if (audit.kind === "INTERNAL") {
      pushToast({ title: "Internal audit locked", message: "Internal and first-party audit records cannot be edited after creation. Create a new audit or use scope setup for future schedules.", variant: "warning" });
      return;
    }
    const nextForm = auditToForm(audit);
    setAuditForm(nextForm);
    setEditingAuditId(audit.id);
    setError(null);
    setAuditDrawerOpen(true);
    setAuditPersonSearch({
      auditee_user_id: personSearchLabel(peopleById.get(nextForm.auditee_user_id) || null),
      lead_auditor_user_id: personSearchLabel(peopleById.get(nextForm.lead_auditor_user_id) || null),
      observer_auditor_user_id: personSearchLabel(peopleById.get(nextForm.observer_auditor_user_id) || null),
      assistant_auditor_user_id: personSearchLabel(peopleById.get(nextForm.assistant_auditor_user_id) || null),
    });
  };

  const resetAuditEdit = () => {
    setAuditForm(defaultPlannedAudit);
    setEditingAuditId(null);
    setAuditPersonSearch({ auditee_user_id: "", lead_auditor_user_id: "", observer_auditor_user_id: "", assistant_auditor_user_id: "" });
    setAuditDrawerOpen(false);
  };

  const validateAuditForm = (): string | null => {
    if (!auditForm.title.trim()) return "Audit title is required.";
    if (!auditForm.audit_scope_code) return "Select the audit scope before saving.";
    if (!auditForm.planned_start) return "Planned start date is required.";
    if (auditForm.planned_end && auditForm.planned_start && auditForm.planned_end < auditForm.planned_start) return "Planned end date cannot be before the start date.";
    return null;
  };

  const openCreateDrawer = () => {
    setEditingScheduleId(null);
    setError(null);
    setDrawerTab("overview");
    setDrawerOpen(true);
  };

  const discardDraft = () => {
    setForm(defaultSchedule);
    setEditingScheduleId(null);
    setError(null);
    setPersonSearch({ auditee_user_id: "", lead_auditor_user_id: "", observer_auditor_user_id: "", assistant_auditor_user_id: "" });
    if (typeof window !== "undefined") window.localStorage.removeItem(draftStorageKey);
  };

  const beginEdit = (schedule: QMSAuditScheduleOut) => {
    if (schedule.kind === "INTERNAL") {
      pushToast({ title: "Internal schedule locked", message: "Internal and first-party audit schedules are locked after creation. Create a new schedule for changes.", variant: "warning" });
      return;
    }
    const nextForm = scheduleToForm(schedule);
    setForm(nextForm);
    setEditingScheduleId(schedule.id);
    setError(null);
    setDrawerTab("overview");
    setDrawerOpen(true);
    setPersonSearch({
      auditee_user_id: personSearchLabel(peopleById.get(nextForm.auditee_user_id) || null),
      lead_auditor_user_id: personSearchLabel(peopleById.get(nextForm.lead_auditor_user_id) || null),
      observer_auditor_user_id: personSearchLabel(peopleById.get(nextForm.observer_auditor_user_id) || null),
      assistant_auditor_user_id: personSearchLabel(peopleById.get(nextForm.assistant_auditor_user_id) || null),
    });
  };

  const validateForm = (): string | null => {
    const duration = Number(form.duration_days);
    if (!form.title.trim()) return "Audit title is required.";
    if (!form.audit_scope_code) return "Select the audit scope before saving.";
    if (!form.next_due_date) return "Next due date is required.";
    if (!Number.isFinite(duration) || duration < 1) return "Enter a valid duration in days.";
    if (!form.lead_auditor_user_id) return "Assign a lead auditor before saving the schedule.";
    if (form.kind === "INTERNAL" && !form.auditee_user_id && !form.auditee_email.trim()) {
      return "Select an internal auditee or provide an auditee contact email.";
    }
    if (form.kind !== "INTERNAL") {
      return validateExternalAuditees(form.external_auditees);
    }
    return null;
  };

  const saveSchedule = useMutation({
    mutationFn: async () => {
      const validationError = validateForm();
      if (validationError) throw new Error(validationError);
      const payload = formToPayload(form);
      const confirmationMessage = editingScheduleId
        ? `Confirm rescheduling or updating this audit. Notices${payload.notify_auditors || payload.notify_auditees ? " will" : " will not"} be prepared for the selected recipients.`
        : `Confirm creation of this audit schedule. Notices${payload.notify_auditors || payload.notify_auditees ? " will" : " will not"} be prepared for the selected recipients.`;
      if (!window.confirm(confirmationMessage)) {
        throw new Error("Schedule confirmation cancelled.");
      }
      if (editingScheduleId) return qmsUpdateAuditSchedule(editingScheduleId, payload);
      return qmsCreateAuditSchedule(payload);
    },
    onSuccess: async () => {
      const wasEditing = Boolean(editingScheduleId);
      discardDraft();
      setDrawerTab("overview");
      setDrawerOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({
        title: wasEditing ? "Schedule updated" : "Schedule created",
        message: wasEditing
          ? "The schedule, notice plan, and participant selection have been updated."
          : "The schedule is now live in the planner and ready to run into an audit.",
        variant: "success",
        sound: true,
      });
    },
    onError: (e: Error) => {
      if (e.message === "Schedule confirmation cancelled.") return;
      setError(e.message || "Failed to save schedule.");
    },
  });

  const deleteSchedule = useMutation({
    mutationFn: async (schedule: QMSAuditScheduleOut) => {
      await qmsDeleteAuditSchedule(schedule.id);
      return schedule;
    },
    onSuccess: async (schedule) => {
      if (editingScheduleId === schedule.id) {
        discardDraft();
        setDrawerTab("overview");
        setDrawerOpen(false);
      }
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({ title: "Schedule deleted", message: `${schedule.title} has been removed from the planner.`, variant: "success" });
    },
    onError: (e: Error) => {
      pushToast({ title: "Delete failed", message: e.message || "The schedule could not be deleted.", variant: "error" });
    },
  });

  const runSchedule = useMutation({
    mutationFn: (scheduleId: string) => qmsRunAuditSchedule(scheduleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      await queryClient.invalidateQueries({ queryKey: ["qms-audits-planned", amoCode, department] });
      pushToast({ title: "Audit issued", message: "The live audit has been created from the selected schedule.", variant: "success", sound: true });
    },
  });

  const savePlannedAudit = useMutation({
    mutationFn: async () => {
      const validationError = validateAuditForm();
      if (validationError) throw new Error(validationError);
      if (!editingAuditId) throw new Error("No audit record selected.");
      return qmsUpdateAudit(editingAuditId, {
        title: auditForm.title.trim(),
        kind: auditForm.kind,
        audit_scope_code: auditForm.audit_scope_code || null,
        planned_start: auditForm.planned_start || null,
        planned_end: auditForm.planned_end || auditForm.planned_start || null,
        scope: normalizeNullable(auditForm.scope),
        criteria: normalizeNullable(auditForm.criteria),
        auditee: normalizeNullable(auditForm.auditee),
        auditee_email: normalizeNullable(auditForm.auditee_email),
        auditee_user_id: normalizeNullable(auditForm.auditee_user_id),
        lead_auditor_user_id: normalizeNullable(auditForm.lead_auditor_user_id),
        observer_auditor_user_id: normalizeNullable(auditForm.observer_auditor_user_id),
        assistant_auditor_user_id: normalizeNullable(auditForm.assistant_auditor_user_id),
        notify_auditors: auditForm.notify_auditors,
        notify_auditees: auditForm.notify_auditees,
        reminder_interval_days: Math.max(1, Number(auditForm.reminder_interval_days) || 7),
      });
    },
    onSuccess: async () => {
      resetAuditEdit();
      await queryClient.invalidateQueries({ queryKey: ["qms-audits-planned", amoCode, department] });
      pushToast({ title: "Planned audit updated", message: "The audit record, assignment, and dates have been updated.", variant: "success", sound: true });
    },
    onError: (e: Error) => {
      setError(e.message || "Failed to update planned audit.");
      pushToast({ title: "Update failed", message: e.message || "The planned audit could not be updated.", variant: "error" });
    },
  });

  const deletePlannedAudit = useMutation({
    mutationFn: async (audit: QMSAuditOut) => {
      await qmsDeleteAudit(audit.id);
      return audit;
    },
    onSuccess: async (audit) => {
      if (editingAuditId === audit.id) resetAuditEdit();
      await queryClient.invalidateQueries({ queryKey: ["qms-audits-planned", amoCode, department] });
      pushToast({ title: "Planned audit deleted", message: `${audit.audit_ref} has been removed.`, variant: "success" });
    },
    onError: (e: Error) => {
      pushToast({ title: "Delete failed", message: e.message || "The planned audit could not be deleted.", variant: "error" });
    },
  });

  const startPlannedAudit = useMutation({
    mutationFn: (audit: QMSAuditOut) => qmsUpdateAudit(audit.id, { status: "IN_PROGRESS" }),
    onSuccess: async (audit) => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audits-planned", amoCode, department] });
      pushToast({ title: "Fieldwork started", message: `${audit.audit_ref} is now in progress.`, variant: "success", sound: true });
      navigate(`/maintenance/${amoCode}/quality/audits/${audit.id}`);
    },
    onError: (e: Error) => {
      pushToast({ title: "Could not start fieldwork", message: e.message || "The audit could not be started.", variant: "error" });
    },
  });

  const dismissGuide = () => {
    setGuideDismissed(true);
    setGuideOpen(false);
    if (typeof window !== "undefined") window.localStorage.setItem(guideStorageKey, "1");
  };

  const reopenGuide = () => {
    setGuideOpen(true);
  };

  const guideAction = (action: "create" | "participants" | "review" | "calendar" | "list") => {
    if (action === "create") {
      openCreateDrawer();
      setGuideOpen(false);
      return;
    }
    if (action === "participants" || action === "review") {
      if (!drawerOpen) setDrawerOpen(true);
      setDrawerTab(action);
      setGuideOpen(false);
      return;
    }
    if (action === "calendar" || action === "list") {
      setSearchParams({ view: action });
      setGuideOpen(false);
    }
  };

  const handleDelete = (schedule: QMSAuditScheduleOut) => {
    const confirmDelete = window.confirm(`Delete schedule \"${schedule.title}\" due ${formatDate(schedule.next_due_date)}?`);
    if (!confirmDelete) return;
    deleteSchedule.mutate(schedule);
  };

  const handleDeleteAudit = (audit: QMSAuditOut) => {
    const confirmDelete = window.confirm(`Delete planned audit "${audit.audit_ref} - ${audit.title}"?`);
    if (!confirmDelete) return;
    deletePlannedAudit.mutate(audit);
  };

  const openAuditWorkspace = (audit: QMSAuditOut) => {
    navigate(`/maintenance/${amoCode}/quality/audits/${audit.id}`);
  };

  const toggleAuditExpansion = (auditId: string) => {
    setExpandedAuditIds((prev) => {
      const next = new Set(prev);
      if (next.has(auditId)) next.delete(auditId);
      else next.add(auditId);
      return next;
    });
  };

  const toggleAuditGroup = (group: PlannedRecordFilter) => {
    setCollapsedAuditGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const expandActiveAuditGroups = () => {
    setCollapsedAuditGroups(new Set());
  };

  const collapseQuietAuditGroups = () => {
    setCollapsedAuditGroups(new Set(["scheduled", "deferred"]));
  };

  const renderActionCluster = (schedule: ScheduleViewModel) => {
    if (schedule.is_preview) {
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>Continue</Button>
          <Button variant="secondary" size="sm" onClick={discardDraft}>Discard draft</Button>
        </div>
      );
    }
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" onClick={() => beginEdit(schedule)}>
          <Pencil size={14} />
          Edit
        </Button>
        <Button variant="secondary" size="sm" onClick={() => runSchedule.mutate(schedule.id)} loading={runSchedule.isPending && runSchedule.variables === schedule.id}>
          <Play size={14} />
          Run
        </Button>
        <Button variant="danger" size="sm" onClick={() => handleDelete(schedule)} loading={deleteSchedule.isPending && deleteSchedule.variables?.id === schedule.id}>
          <Trash2 size={14} />
          Delete
        </Button>
      </div>
    );
  };

  const renderPlannedAuditActions = (audit: QMSAuditOut) => {
    const isStarting = startPlannedAudit.isPending && startPlannedAudit.variables?.id === audit.id;
    const isDeleting = deletePlannedAudit.isPending && deletePlannedAudit.variables?.id === audit.id;
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" onClick={() => beginEditAudit(audit)}>
          <Pencil size={14} />
          Modify
        </Button>
        <Button variant="secondary" size="sm" onClick={() => openAuditWorkspace(audit)}>
          <ExternalLink size={14} />
          Workspace
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => startPlannedAudit.mutate(audit)}
          disabled={!audit.lead_auditor_user_id}
          loading={isStarting}
        >
          <Play size={14} />
          Start fieldwork
        </Button>
        <Button variant="danger" size="sm" onClick={() => handleDeleteAudit(audit)} loading={isDeleting}>
          <Trash2 size={14} />
          Delete
        </Button>
      </div>
    );
  };

  const renderPlannedAuditRow = (audit: QMSAuditOut) => {
    const countdown = auditWindowLabel(audit);
    const auditee = audit.auditee_user_id ? peopleById.get(audit.auditee_user_id) : null;
    const leadUser = audit.lead_auditor_user_id ? peopleById.get(audit.lead_auditor_user_id) : null;
    const observerUser = audit.observer_auditor_user_id ? peopleById.get(audit.observer_auditor_user_id) : null;
    const assistantUser = audit.assistant_auditor_user_id ? peopleById.get(audit.assistant_auditor_user_id) : null;
    const expanded = expandedAuditIds.has(audit.id);
    const auditeeName = auditee ? auditee.full_name : audit.auditee || audit.auditee_email || "Not set";
    return (
      <article key={audit.id} className={`qa-audit-row ${recordDensity === "compact" ? "qa-audit-row--compact" : ""}${!audit.lead_auditor_user_id ? " is-attention" : ""}`}>
        <button type="button" className="qa-audit-row__main" onClick={() => toggleAuditExpansion(audit.id)} aria-expanded={expanded}>
          <span className="qa-audit-row__rail" aria-hidden="true" />
          <span className="qa-audit-row__identity">
            <span className="qa-audit-row__ref">{audit.audit_ref}</span>
            <strong>{audit.title}</strong>
            <small>{formatKindLabel(audit.kind)} · {audit.status}</small>
          </span>
          <span className="qa-audit-row__team">
            <PersonAvatar person={leadUser} fallback="Lead" size="sm" />
            <span>
              <small>Lead auditor</small>
              <strong>{leadUser ? leadUser.full_name : "Unassigned"}</strong>
            </span>
          </span>
          <span className="qa-audit-row__team qa-audit-row__team--auditee">
            <PersonAvatar person={auditee} fallback={auditeeName} size="sm" />
            <span>
              <small>Auditee</small>
              <strong>{auditeeName}</strong>
            </span>
          </span>
          <span className="qa-audit-row__window">
            <Clock3 size={14} />
            <span>
              <small>{formatDate(audit.planned_start)} → {formatDate(audit.planned_end)}</small>
              <strong className={countdown.className}>{countdown.text}</strong>
            </span>
          </span>
          <span className="qa-audit-row__status">
            {!audit.lead_auditor_user_id ? <span className="qa-status-pill qa-status-pill--warning">Lead pending</span> : <span className="qa-status-pill qa-status-pill--ready">Ready</span>}
            <ChevronDown size={16} className={expanded ? "is-rotated" : ""} />
          </span>
        </button>

        <div className={`qa-audit-row__details${expanded ? " is-open" : ""}`}>
          <div className="qa-audit-row__details-inner">
            {!audit.lead_auditor_user_id ? (
              <div className="planned-audit-record-alert planned-audit-record-alert--inline">
                <UserPlus size={14} />
                Waiting for lead auditor assignment. Modify this record to unlock fieldwork.
              </div>
            ) : null}
            <div className="qa-audit-detail-grid">
              <PersonChip label="Lead" person={leadUser} muted={!leadUser} />
              <PersonChip label="Observer" person={observerUser} fallback="Optional" muted={!observerUser} />
              <PersonChip label="Assistant" person={assistantUser} fallback="Optional" muted={!assistantUser} />
              <PersonChip label="Auditee" person={auditee} fallback={auditeeName} muted={!auditeeName || auditeeName === "Not set"} />
              <div className="qa-detail-tile qa-detail-tile--wide"><small>Scope</small><strong>{audit.scope || "No scope added yet"}</strong></div>
              <div className="qa-detail-tile qa-detail-tile--wide"><small>Criteria</small><strong>{audit.criteria || "No criteria added yet"}</strong></div>
            </div>
            <div className="qa-audit-row__actions">
              {renderPlannedAuditActions(audit)}
            </div>
          </div>
        </div>
      </article>
    );
  };

  const renderPlannedAuditsList = () => (
    <div className={`qa-audit-records-shell qa-audit-records-shell--${recordDensity}`}>
      <div className="qa-audit-record-command">
        <div className="qa-search-box">
          <Search size={15} />
          <input value={recordSearch} onChange={(event) => setRecordSearch(event.target.value)} placeholder="Search audit ref, title, auditor, auditee or scope" />
        </div>
        <div className="qa-record-filter-tabs" role="tablist" aria-label="Planned audit filters">
          {[
            ["all", "All"],
            ["needsAssignment", "Needs assignment"],
            ["scheduled", "Scheduled"],
            ["dueSoon", "Due soon"],
            ["deferred", "Deferred"],
          ].map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={recordFilter === key} className={recordFilter === key ? "is-active" : ""} onClick={() => setRecordFilter(key as PlannedRecordFilter)}>
              <span>{label}</span>
              <strong>{plannedRecordStats[key as PlannedRecordFilter]}</strong>
            </button>
          ))}
        </div>
        <div className="qa-record-tools">
          <button type="button" onClick={() => setRecordDensity((prev) => prev === "compact" ? "comfortable" : "compact")}>
            <Filter size={14} /> {recordDensity === "compact" ? "Compact" : "Comfort"}
          </button>
          <button type="button" onClick={collapseQuietAuditGroups}>Collapse quiet</button>
          <button type="button" onClick={expandActiveAuditGroups}>Expand all</button>
        </div>
      </div>

      {!filteredPlannedAudits.length ? (
        <EmptyState title="No records match this view" description="Adjust search, filters, or run another schedule into a planned audit record." />
      ) : null}

      {groupedPlannedAudits.map((group) => {
        const collapsed = collapsedAuditGroups.has(group.key);
        return (
          <section key={group.key} className="qa-audit-group">
            <button type="button" className="qa-audit-group__header" onClick={() => toggleAuditGroup(group.key)} aria-expanded={!collapsed}>
              <span>
                <strong>{group.label}</strong>
                <small>{group.audits.length} record{group.audits.length === 1 ? "" : "s"}</small>
              </span>
              <ChevronDown size={17} className={collapsed ? "" : "is-rotated"} />
            </button>
            <div className={`qa-audit-group__body${collapsed ? " is-collapsed" : ""}`}>
              {!collapsed ? group.audits.map(renderPlannedAuditRow) : null}
            </div>
          </section>
        );
      })}
    </div>
  );

  const renderPlannedAuditsTable = () => (
    <div className="table-responsive">
      <table className="table table--portal">
        <thead>
          <tr>
            <th>Audit</th>
            <th>Window</th>
            <th>Lead auditor</th>
            <th>Auditee</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {plannedAudits.map((audit) => {
            const leadUser = audit.lead_auditor_user_id ? peopleById.get(audit.lead_auditor_user_id) : null;
            const auditeeUser = audit.auditee_user_id ? peopleById.get(audit.auditee_user_id) : null;
            return (
              <tr key={audit.id}>
                <td><div className="table-primary-cell"><strong>{audit.title}</strong><span>{audit.audit_ref} · {formatKindLabel(audit.kind)}</span></div></td>
                <td>{formatDate(audit.planned_start)} → {formatDate(audit.planned_end)}</td>
                <td>{leadUser ? userLabel(leadUser) : "Unassigned"}</td>
                <td>{auditeeUser ? userLabel(auditeeUser) : audit.auditee || audit.auditee_email || "Not set"}</td>
                <td><span className={auditWindowLabel(audit).className}>{audit.lead_auditor_user_id ? "Planned" : "Lead pending"}</span></td>
                <td>{renderPlannedAuditActions(audit)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const renderCalendar = () => {
    const byDate = new Map<string, PlannerCalendarItem[]>();
    plannerCalendarItems.forEach((item) => {
      const key = item.date;
      if (!key) return;
      const group = byDate.get(key) ?? [];
      group.push(item);
      byDate.set(key, group);
    });

    return (
      <div className="planner-calendar-shell">
        <div className="planner-calendar-toolbar">
          <Button variant="ghost" size="sm" onClick={() => setVisibleMonth((prev) => new Date((prev ?? activeCalendarMonth).getFullYear(), (prev ?? activeCalendarMonth).getMonth() - 1, 1))}>
            <ChevronLeft size={15} />
            Prev
          </Button>
          <strong>{activeCalendarMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</strong>
          <Button variant="ghost" size="sm" onClick={() => setVisibleMonth((prev) => new Date((prev ?? activeCalendarMonth).getFullYear(), (prev ?? activeCalendarMonth).getMonth() + 1, 1))}>
            Next
            <ChevronRight size={15} />
          </Button>
        </div>

        <div className="planner-calendar-scroll">
          <div className="planner-calendar-grid planner-calendar-grid--header">
            {weekdayLabels.map((label) => (
              <div key={label} className="planner-calendar-cell planner-calendar-cell--label">{label}</div>
            ))}
          </div>

          <div className="planner-calendar-grid">
            {calendarCells.map((cell) => {
              const dateKey = cell.date.toISOString().slice(0, 10);
              const dayItems = byDate.get(dateKey) ?? [];
              return (
                <div key={cell.key} className={`planner-calendar-cell${cell.inMonth ? "" : " is-outside"}${cell.isToday ? " is-today" : ""}`}>
                  <div className="planner-calendar-cell__date">{cell.date.getDate()}</div>
                  <div className="planner-calendar-cell__items">
                    {dayItems.map((item) => {
                      const countdown = countdownLabel(item.date);
                      const leadUser = item.lead_auditor_user_id ? peopleById.get(item.lead_auditor_user_id) : null;
                      const sourceLabel = item.source === "audit" ? item.status || "PLANNED" : item.schedule?.preview_label || formatKindLabel(item.kind);
                      return (
                        <button
                          key={item.id}
                          type="button"
                          className={`planner-calendar-event${item.is_preview ? " planner-calendar-event--preview" : ""}${item.source === "audit" ? " planner-calendar-event--audit-record" : ""}`}
                          onClick={() => {
                            if (item.schedule?.is_preview) setDrawerOpen(true);
                            else if (item.schedule) beginEdit(item.schedule);
                            else if (item.audit) openAuditWorkspace(item.audit);
                            else if (item.link) navigate(item.link);
                          }}
                        >
                          <strong>{item.ref ? `${item.ref} · ${item.title}` : item.title}</strong>
                          <span>{sourceLabel}</span>
                          <span>{leadUser ? userLabel(leadUser) : "Lead auditor pending"}</span>
                          <span>{item.auditee || "Auditee not set"}</span>
                          <span className={countdown.className}>{countdown.text}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const renderList = () => (
    <div className="portal-list-grid">
      {boardSchedules.map((schedule) => {
        const countdown = countdownLabel(schedule.next_due_date);
        const auditee = schedule.kind === "INTERNAL"
          ? (schedule.auditee_user_id ? peopleById.get(schedule.auditee_user_id) : null)
          : null;
        const leadUser = schedule.lead_auditor_user_id ? peopleById.get(schedule.lead_auditor_user_id) : null;
        return (
          <article key={schedule.id} className={`portal-list-card${schedule.is_preview ? " portal-list-card--draft" : ""}`}>
            <div className="portal-list-card__header">
              <div>
                <p className="portal-list-card__eyebrow">{schedule.preview_label || schedule.frequency.replaceAll("_", " ")}</p>
                <h3 className="portal-list-card__title">{schedule.title}</h3>
              </div>
              <span className={countdown.className}>{countdown.text}</span>
            </div>
            <dl className="portal-list-card__meta">
              <div><dt>Due</dt><dd>{formatDate(schedule.next_due_date)}</dd></div>
              <div><dt>Lead auditor</dt><dd>{leadUser ? userLabel(leadUser) : "Unassigned"}</dd></div>
              <div><dt>Auditee</dt><dd>{auditee ? userLabel(auditee) : schedule.auditee || "Not set"}</dd></div>
              <div><dt>Audit scope</dt><dd>{schedule.audit_scope_code ? `${schedule.audit_scope_code} · ${scopeByCode.get(schedule.audit_scope_code)?.name || "Configured scope"}` : "Scope not set"}</dd></div>
              <div><dt>Coverage</dt><dd>{schedule.scope || "No coverage detail added yet"}</dd></div>
            </dl>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
              <span>{schedule.is_active ? "Active schedule" : "Paused schedule"}</span>
              {renderActionCluster(schedule)}
            </div>
          </article>
        );
      })}
    </div>
  );

  const renderTable = () => (
    <div className="table-responsive">
      <table className="table table--portal">
        <thead>
          <tr>
            <th>Audit</th>
            <th>Frequency</th>
            <th>Next due</th>
            <th>Lead auditor</th>
            <th>Auditee</th>
            <th>Schedule</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {boardSchedules.map((schedule) => {
            const countdown = countdownLabel(schedule.next_due_date);
            const leadUser = schedule.lead_auditor_user_id ? peopleById.get(schedule.lead_auditor_user_id) : null;
            const auditeeUser = schedule.auditee_user_id ? peopleById.get(schedule.auditee_user_id) : null;
            return (
              <tr key={schedule.id}>
                <td>
                  <div className="table-primary-cell">
                    <strong>{schedule.title}</strong>
                    <span>{schedule.preview_label || formatKindLabel(schedule.kind)}</span>
                  </div>
                </td>
                <td>{formatFrequencyLabel(schedule.frequency)}</td>
                <td>{formatDate(schedule.next_due_date)}</td>
                <td>{leadUser ? userLabel(leadUser) : "Unassigned"}</td>
                <td>{auditeeUser ? userLabel(auditeeUser) : schedule.auditee || "Not set"}</td>
                <td><span className={countdown.className}>{countdown.text}</span></td>
                <td>{renderActionCluster(schedule)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const lifecycleSummaryItems = [
    { label: "1. Schedule", detail: "Define type, scope, criteria, participants, and due window." },
    { label: "2. Notify", detail: "Confirm whether auditors and auditees should receive notices and reminders." },
    { label: "3. Run", detail: "Issue the schedule into a live audit workspace when ready to execute." },
    { label: "4. Record", detail: "Capture checklist evidence, findings, CARs, and responses until verification." },
    { label: "5. Close", detail: "Upload report, verify closure conditions, and retain the audit evidence pack." },
  ];

  return (
    <QualityAuditsSectionLayout
      title="Audit Planner"
      subtitle="Stage, confirm, schedule, reschedule, and launch audits from one controlled workspace."
      toolbar={
        <div className="planner-toolbar-actions">
          <Button variant="secondary" size="sm" onClick={reopenGuide}>
            <HelpCircle size={15} />
            Guide
          </Button>
          <Button variant="secondary" size="sm" onClick={() => { void schedulesQuery.refetch(); void plannedAuditsQuery.refetch(); }}>
            <RefreshCw size={15} />
            Refresh
          </Button>
        </div>
      }
    >
      <div className="qms-page-grid">
        {!guideDismissed ? (
          <SectionCard variant="subtle" className="planner-guide-card planner-guide-card--attention">
            <div className="planner-guide-card__header">
              <div>
                <p className="planner-guide-card__eyebrow"><HelpCircle size={15} /> First-time guide</p>
                <h3 className="planner-guide-card__title">Start here: build the audit from schedule to closure</h3>
                <p className="planner-guide-card__copy">Use the buttons below to jump directly to the next action. The guide stays available on the right after you dismiss it.</p>
              </div>
              <div className="planner-guide-card__actions">
                <Button variant="secondary" size="sm" onClick={() => setGuideOpen(true)}>Open guide drawer</Button>
                <Button variant="ghost" size="sm" onClick={dismissGuide}>Minimise</Button>
              </div>
            </div>
            <div className="planner-guide-card__grid planner-guide-card__grid--actions">
              {lifecycleSummaryItems.map((item, index) => (
                <button
                  key={item.label}
                  type="button"
                  className="planner-guide-card__step planner-guide-card__step--button"
                  onClick={() => guideAction(index === 0 ? "create" : index === 1 ? "participants" : index === 2 ? "review" : index === 3 ? "list" : "calendar")}
                >
                  <strong>{item.label}</strong>
                  <span>{item.detail}</span>
                  <em>Go there <ExternalLink size={12} /></em>
                </button>
              ))}
            </div>
          </SectionCard>
        ) : (
          <button type="button" className="planner-help-fab" onClick={reopenGuide} aria-label="Open audit planner guide">
            <HelpCircle size={18} />
            <span>Guide</span>
          </button>
        )}

        <SectionCard variant="subtle" className="qms-compact-toolbar-card">
          <div className="qms-toolbar qms-toolbar--portal" style={{ justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <Button size="sm" onClick={openCreateDrawer}>
                <Plus size={15} />
                Create schedule
              </Button>
              <Button size="sm" variant="secondary" onClick={() => beginScopeEdit()}>
                Manage audit scopes
              </Button>
              <span className="planner-inline-note">Scopes drive references such as QAR/AC/26/001 and are tenant-specific.</span>
            </div>
            <div className="portal-view-switcher">
              {plannerViewOptions().map((option) => {
                const Icon = option.icon;
                return (
                  <button key={option.value} type="button" className={`portal-view-switcher__item${view === option.value ? " is-active" : ""}`} onClick={() => setSearchParams({ view: option.value })}>
                    <Icon size={16} />
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>
        </SectionCard>

        <SectionCard variant="subtle">
          <div className="portal-summary-strip">
            {scheduleSummary.map((item) => (
              <div key={item.label} className="portal-summary-chip">
                <span className="portal-summary-chip__label">{item.label}</span>
                <strong className="portal-summary-chip__value">{item.value}</strong>
              </div>
            ))}
          </div>
        </SectionCard>

        {view !== "calendar" ? (
          <SectionCard
            title="Planned audit records"
            subtitle="These are the live audit records already created from the schedule/programme. Assign the lead auditor here, push dates forward, open the workspace, or delete the record."
            eyebrow="Audit records"
          >
            {plannedAuditsQuery.isLoading ? <p className="qms-loading-copy">Loading planned audit records…</p> : null}
            {!plannedAuditsQuery.isLoading && !plannedAudits.length ? (
              <EmptyState title="No planned audit records found" description="Run a schedule into a live audit or create a new audit record to populate this list." />
            ) : null}
            {!plannedAuditsQuery.isLoading && plannedAudits.length ? (view === "table" ? renderPlannedAuditsTable() : renderPlannedAuditsList()) : null}
          </SectionCard>
        ) : null}

        <SectionCard
          title={view === "calendar" ? "Integrated audit calendar" : view === "list" ? "Recurring schedule programme" : "Recurring schedule register"}
          subtitle={view === "calendar" ? "Shows live planned audit records and recurring programme schedules in one planning surface." : "Schedules are programme templates. Use Run to create a live planned audit record above."}
          eyebrow={view === "calendar" ? "Calendar view" : "Schedule templates"}
        >
          {schedulesQuery.isLoading || plannedAuditsQuery.isLoading || auditCalendarIntegrationQuery.isLoading ? <p className="qms-loading-copy">Loading audit calendar…</p> : null}
          {!schedulesQuery.isLoading && !plannedAuditsQuery.isLoading && !auditCalendarIntegrationQuery.isLoading && !plannerCalendarItems.length ? <EmptyState title="No audit dates found" description="Create a schedule or a planned audit record to populate the planner and QMS calendar views." /> : null}
          {!schedulesQuery.isLoading && !plannedAuditsQuery.isLoading && !auditCalendarIntegrationQuery.isLoading && plannerCalendarItems.length ? (view === "calendar" ? renderCalendar() : view === "list" ? renderList() : renderTable()) : null}
        </SectionCard>
      </div>

      <Drawer title="Audit planner guide" isOpen={guideOpen} onClose={() => setGuideOpen(false)} side="right" panelClassName="drawer-panel--planner-guide">
        <div className="planner-guide-drawer">
          <p className="planner-guide-drawer__lead">Follow these steps in order. Each action opens the exact workspace you need, so the guide remains useful even after the first visit.</p>
          <div className="planner-guide-drawer__steps">
            <button type="button" onClick={() => guideAction("create")}><strong>1. Create or continue schedule</strong><span>Open the schedule drawer and define title, type, due date, scope and criteria.</span></button>
            <button type="button" onClick={() => guideAction("participants")}><strong>2. Assign people</strong><span>Set lead auditor, observer, assistant and internal or external auditees.</span></button>
            <button type="button" onClick={() => guideAction("review")}><strong>3. Review notices</strong><span>Check recipients, reminder interval and whether notices should be sent.</span></button>
            <button type="button" onClick={() => guideAction("calendar")}><strong>4. Check the calendar</strong><span>Confirm spacing and upcoming workload before saving or running an audit.</span></button>
            <button type="button" onClick={() => guideAction("list")}><strong>5. Run or edit saved items</strong><span>Use the schedule action buttons to run, edit or delete saved audit schedules.</span></button>
          </div>
          <div className="planner-guide-drawer__footer">
            <Button onClick={() => guideAction("create")}><Plus size={15} /> Create schedule</Button>
            <Button variant="secondary" onClick={dismissGuide}>Keep as right-side guide</Button>
          </div>
        </div>
      </Drawer>

      <Drawer
        title="Modify planned audit record"
        isOpen={auditDrawerOpen}
        onClose={resetAuditEdit}
        side="left"
        panelClassName="drawer-panel--planner"
      >
        <div className="planner-drawer-layout">
          <div className="planner-drawer-layout__body">
            <p className="planner-inline-note">This edits the live planned audit record, not only the recurring schedule template. Use it to assign the lead auditor, adjust dates, and clear the “waiting for lead auditor assignment” blocker.</p>
            <div className="planner-drawer-form__grid">
              <label className="profile-inline-field planner-form-span-2">
                <span>Audit title</span>
                <input className="input" value={auditForm.title} onChange={(e) => setAuditForm((prev) => ({ ...prev, title: e.target.value }))} />
              </label>

              <label className="profile-inline-field planner-form-span-2">
                <span>Audit scope</span>
                <select className="input" value={auditForm.audit_scope_code} onChange={(e) => applyPlannedAuditScopeCode(e.target.value)}>
                  {auditScopes.map((scope) => <option key={scope.id} value={scope.code}>{scope.code} · {scope.name}</option>)}
                </select>
                <small>{scopeByCode.get(auditForm.audit_scope_code)?.description || "Scope drives the system-generated audit reference."}</small>
              </label>

              <label className="profile-inline-field">
                <span>Audit type</span>
                <select className="input" value={auditForm.kind} onChange={(e) => setAuditForm((prev) => ({ ...prev, kind: e.target.value as AuditKind }))}>
                  {auditKinds.map((kind) => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
                </select>
              </label>

              <label className="profile-inline-field">
                <span>Planned start</span>
                <input className="input" type="date" value={auditForm.planned_start} onChange={(e) => setAuditForm((prev) => ({ ...prev, planned_start: e.target.value }))} />
              </label>

              <label className="profile-inline-field">
                <span>Planned end</span>
                <input className="input" type="date" value={auditForm.planned_end} onChange={(e) => setAuditForm((prev) => ({ ...prev, planned_end: e.target.value }))} />
              </label>

              <label className="profile-inline-field">
                <span>Reminder interval (days)</span>
                <input className="input" type="number" min={1} max={60} value={auditForm.reminder_interval_days} onChange={(e) => setAuditForm((prev) => ({ ...prev, reminder_interval_days: e.target.value }))} />
              </label>

              <PersonLookupField
                label="Lead auditor"
                value={auditForm.lead_auditor_user_id}
                query={auditPersonSearch.lead_auditor_user_id}
                options={personnelOptions}
                placeholder="Search by name or staff code"
                helper="Required before fieldwork can be started from the list."
                onQueryChange={(value) => updateAuditPersonLookup("lead_auditor_user_id", value)}
                onSelect={(personId) => applyAuditPerson("lead_auditor_user_id", personId)}
              />
              <PersonLookupField
                label="Observer auditor"
                value={auditForm.observer_auditor_user_id}
                query={auditPersonSearch.observer_auditor_user_id}
                options={personnelOptions}
                placeholder="Optional"
                onQueryChange={(value) => updateAuditPersonLookup("observer_auditor_user_id", value)}
                onSelect={(personId) => applyAuditPerson("observer_auditor_user_id", personId)}
              />
              <PersonLookupField
                label="Assistant auditor"
                value={auditForm.assistant_auditor_user_id}
                query={auditPersonSearch.assistant_auditor_user_id}
                options={personnelOptions}
                placeholder="Optional"
                onQueryChange={(value) => updateAuditPersonLookup("assistant_auditor_user_id", value)}
                onSelect={(personId) => applyAuditPerson("assistant_auditor_user_id", personId)}
              />
              <PersonLookupField
                label="Auditee"
                value={auditForm.auditee_user_id}
                query={auditPersonSearch.auditee_user_id}
                options={personnelOptions}
                placeholder="Internal auditee, if applicable"
                onQueryChange={(value) => updateAuditPersonLookup("auditee_user_id", value)}
                onSelect={(personId) => applyAuditPerson("auditee_user_id", personId)}
              />

              <label className="profile-inline-field">
                <span>Auditee name</span>
                <input className="input" value={auditForm.auditee} onChange={(e) => setAuditForm((prev) => ({ ...prev, auditee: e.target.value }))} placeholder="Department, supplier, or person" />
              </label>
              <label className="profile-inline-field">
                <span>Auditee email</span>
                <input className="input" type="email" value={auditForm.auditee_email} onChange={(e) => setAuditForm((prev) => ({ ...prev, auditee_email: e.target.value }))} placeholder="optional@example.com" />
              </label>

              <label className="profile-inline-field planner-form-span-2">
                <span>Scope</span>
                <textarea className="input" value={auditForm.scope} onChange={(e) => setAuditForm((prev) => ({ ...prev, scope: e.target.value }))} rows={3} />
              </label>
              <label className="profile-inline-field planner-form-span-2">
                <span>Criteria</span>
                <textarea className="input" value={auditForm.criteria} onChange={(e) => setAuditForm((prev) => ({ ...prev, criteria: e.target.value }))} rows={3} />
              </label>

              <div className="planner-review-card planner-form-span-2">
                <label className="planner-checkbox-row">
                  <input type="checkbox" checked={auditForm.notify_auditors} onChange={(e) => setAuditForm((prev) => ({ ...prev, notify_auditors: e.target.checked }))} />
                  <span>Notify auditors when audit notices are issued</span>
                </label>
                <label className="planner-checkbox-row">
                  <input type="checkbox" checked={auditForm.notify_auditees} onChange={(e) => setAuditForm((prev) => ({ ...prev, notify_auditees: e.target.checked }))} />
                  <span>Notify auditees when audit notices are issued</span>
                </label>
              </div>
            </div>

            {error ? <p className="form-error">{error}</p> : null}
          </div>
          <div className="planner-drawer-layout__footer">
            <Button variant="secondary" onClick={resetAuditEdit}>Cancel</Button>
            <Button onClick={() => savePlannedAudit.mutate()} loading={savePlannedAudit.isPending}>Save planned audit</Button>
          </div>
        </div>
      </Drawer>

      <Drawer
        title="Audit scope setup"
        isOpen={scopeDrawerOpen}
        onClose={() => { setScopeDrawerOpen(false); setScopeForm(defaultAuditScopeForm); }}
        side="right"
        panelClassName="drawer-panel--planner"
      >
        <div className="planner-drawer-layout">
          <div className="planner-drawer-layout__body">
            <p className="planner-inline-note">Only AMO Admins and Quality Managers should maintain this list. Scope codes are tenant-specific and become the middle part of the system-generated reference.</p>
            <div className="planner-scope-list">
              {auditScopes.map((scope) => (
                <button key={scope.id} type="button" className="planner-scope-row" onClick={() => beginScopeEdit(scope)}>
                  <strong>{scope.code}</strong>
                  <span>{scope.name}</span>
                  <em>{scope.party_level.replaceAll("_", " ")} · {scope.default_kind.replaceAll("_", " ")}</em>
                </button>
              ))}
            </div>
            <div className="planner-drawer-form__grid">
              <label className="profile-inline-field">
                <span>Scope code</span>
                <input className="input" value={scopeForm.code} onChange={(e) => setScopeForm((prev) => ({ ...prev, code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16) }))} placeholder="AC" />
              </label>
              <label className="profile-inline-field">
                <span>Scope name</span>
                <input className="input" value={scopeForm.name} onChange={(e) => setScopeForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="Aircraft audit" />
              </label>
              <label className="profile-inline-field">
                <span>Party level</span>
                <select className="input" value={scopeForm.party_level} onChange={(e) => setScopeForm((prev) => ({ ...prev, party_level: e.target.value as AuditScopeFormState["party_level"] }))}>
                  <option value="FIRST_PARTY">1st party / internal</option>
                  <option value="SECOND_PARTY">2nd party / supplier-subcontractor</option>
                  <option value="THIRD_PARTY">3rd party / external</option>
                  <option value="REGULATORY">Regulatory external</option>
                </select>
              </label>
              <label className="profile-inline-field">
                <span>Default audit type</span>
                <select className="input" value={scopeForm.default_kind} onChange={(e) => setScopeForm((prev) => ({ ...prev, default_kind: e.target.value as AuditKind }))}>
                  {auditKinds.map((kind) => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
                </select>
              </label>
              <label className="profile-inline-field">
                <span>Sort order</span>
                <input className="input" type="number" min={0} value={scopeForm.sort_order} onChange={(e) => setScopeForm((prev) => ({ ...prev, sort_order: e.target.value }))} />
              </label>
              <label className="planner-checkbox-row">
                <input type="checkbox" checked={scopeForm.is_active} onChange={(e) => setScopeForm((prev) => ({ ...prev, is_active: e.target.checked }))} />
                <span>Available for new audits</span>
              </label>
              <label className="profile-inline-field planner-form-span-2">
                <span>Description</span>
                <textarea className="input" rows={3} value={scopeForm.description} onChange={(e) => setScopeForm((prev) => ({ ...prev, description: e.target.value }))} />
              </label>
            </div>
          </div>
          <div className="planner-drawer-layout__footer">
            <Button variant="secondary" onClick={() => { setScopeForm(defaultAuditScopeForm); setScopeDrawerOpen(false); }}>Cancel</Button>
            <Button onClick={() => saveAuditScope.mutate()} loading={saveAuditScope.isPending}>Save scope</Button>
          </div>
        </div>
      </Drawer>

      <Drawer
        title={editingScheduleId ? "Edit audit schedule" : "Create audit schedule"}
        isOpen={drawerOpen}
        onClose={() => {
          setDrawerTab("overview");
          setDrawerOpen(false);
        }}
        side="left"
        panelClassName="drawer-panel--planner"
      >
        <div className="planner-drawer-layout">
          <div className="planner-drawer-layout__body">
            <div className="planner-drawer-layout__intro">
              <p className="planner-inline-note">Draft changes are staged automatically for the current user and AMO. Confirmatory prompts appear when you save or reschedule.</p>
              {previewSchedule ? (
                <div className="planner-preview-card">
                  <p className="planner-preview-card__eyebrow">{previewSchedule.preview_label || "Live preview"}</p>
                  <h3 className="planner-preview-card__title">{previewSchedule.title}</h3>
                  <span>{formatDate(previewSchedule.next_due_date)} · {countdownLabel(previewSchedule.next_due_date).text}</span>
                  <span>{formatKindLabel(previewSchedule.kind)} · {formatFrequencyLabel(previewSchedule.frequency)}</span>
                  <span>Lead auditor: {userLabel(peopleById.get(previewSchedule.lead_auditor_user_id || "") || null)}</span>
                </div>
              ) : null}
            </div>

            <div className="planner-drawer-tabs" role="tablist" aria-label="Audit schedule form sections">
              {drawerTabs.map((tab) => (
                <button key={tab.id} type="button" role="tab" aria-selected={drawerTab === tab.id} className={`planner-drawer-tabs__item${drawerTab === tab.id ? " is-active" : ""}`} onClick={() => setDrawerTab(tab.id)}>
                  <strong>{tab.label}</strong>
                  <span>{tab.helper}</span>
                </button>
              ))}
            </div>

            {drawerTab === "overview" ? (
              <div className="planner-drawer-form__grid">
                <label className="profile-inline-field planner-form-span-2">
                  <span>Audit title</span>
                  <input className="input" value={form.title} onChange={(e) => setField("title", e.target.value)} placeholder="e.g. Base maintenance quality audit" />
                </label>

                <label className="profile-inline-field planner-form-span-2">
                  <span>Audit scope</span>
                  <select className="input" value={form.audit_scope_code} onChange={(e) => applyScheduleScopeCode(e.target.value)}>
                    {auditScopes.map((scope) => <option key={scope.id} value={scope.code}>{scope.code} · {scope.name}</option>)}
                  </select>
                  <small>{scopeByCode.get(form.audit_scope_code)?.description || "The selected scope controls the generated QAR reference."}</small>
                </label>

                <div className="profile-inline-field planner-form-span-2">
                  <span>Audit type</span>
                  <div className="planner-kind-grid">
                    {auditKinds.map((kind) => (
                      <button key={kind.value} type="button" className={`planner-kind-option${form.kind === kind.value ? " is-active" : ""}`} onClick={() => setField("kind", kind.value)}>
                        <strong>{kind.label}</strong>
                        <span>{kind.helper}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <label className="profile-inline-field">
                  <span>Frequency</span>
                  <select className="input" value={form.frequency} onChange={(e) => setField("frequency", e.target.value as QMSAuditScheduleFrequency)}>
                    {frequencies.map((freq) => <option key={freq} value={freq}>{formatFrequencyLabel(freq)}</option>)}
                  </select>
                </label>

                <label className="profile-inline-field">
                  <span>Next due date</span>
                  <input className="input" type="date" value={form.next_due_date} onChange={(e) => setField("next_due_date", e.target.value)} />
                </label>

                <label className="profile-inline-field">
                  <span>Duration in days</span>
                  <input className="input" type="number" min={1} value={form.duration_days} onChange={(e) => setField("duration_days", e.target.value)} />
                </label>

                <label className="profile-inline-field">
                  <span>Reminder interval (days)</span>
                  <input className="input" type="number" min={1} max={60} value={form.reminder_interval_days} onChange={(e) => setField("reminder_interval_days", e.target.value)} />
                </label>

                <label className="profile-inline-field planner-form-span-2">
                  <span>Scope</span>
                  <textarea className="input" value={form.scope} onChange={(e) => setField("scope", e.target.value)} placeholder="Stations, processes, manuals, product areas, or departments covered" rows={3} />
                </label>

                <label className="profile-inline-field planner-form-span-2">
                  <span>Criteria</span>
                  <textarea className="input" value={form.criteria} onChange={(e) => setField("criteria", e.target.value)} placeholder="Applicable manuals, KCARs, ISO criteria, customer requirements, and internal procedures" rows={3} />
                </label>

                <div className="planner-review-card planner-review-card--muted planner-form-span-2">
                  <strong>Lifecycle control</strong>
                  <span>Use the planner to define the audit type, participants, notice plan, and execution window before issuing the audit into the live workspace.</span>
                </div>
              </div>
            ) : null}

            {drawerTab === "participants" ? (
              <div className="planner-drawer-form__grid">
                <PersonLookupField
                  label="Lead auditor"
                  value={form.lead_auditor_user_id}
                  query={personSearch.lead_auditor_user_id}
                  options={personnelOptions}
                  placeholder="Search by name or staff code"
                  helper="Suggestions only show the person name, but search still matches user ID, email, and staff code."
                  onQueryChange={(value) => updatePersonLookup("lead_auditor_user_id", value)}
                  onSelect={(personId) => applyPerson("lead_auditor_user_id", personId)}
                />
                <PersonLookupField
                  label="Observer auditor"
                  value={form.observer_auditor_user_id}
                  query={personSearch.observer_auditor_user_id}
                  options={personnelOptions}
                  placeholder="Optional"
                  onQueryChange={(value) => updatePersonLookup("observer_auditor_user_id", value)}
                  onSelect={(personId) => applyPerson("observer_auditor_user_id", personId)}
                />
                <PersonLookupField
                  label="Assistant auditor"
                  value={form.assistant_auditor_user_id}
                  query={personSearch.assistant_auditor_user_id}
                  options={personnelOptions}
                  placeholder="Optional"
                  onQueryChange={(value) => updatePersonLookup("assistant_auditor_user_id", value)}
                  onSelect={(personId) => applyPerson("assistant_auditor_user_id", personId)}
                />

                {form.kind === "INTERNAL" ? (
                  <>
                    <PersonLookupField
                      label="Auditee"
                      value={form.auditee_user_id}
                      query={personSearch.auditee_user_id}
                      options={personnelOptions}
                      placeholder="Search internal auditee"
                      helper="Select an internal auditee. The visible suggestion is just the name, while matching still works with user ID or staff code."
                      onQueryChange={(value) => updatePersonLookup("auditee_user_id", value)}
                      onSelect={(personId) => applyPerson("auditee_user_id", personId)}
                    />
                    <label className="profile-inline-field">
                      <span>Auditee email</span>
                      <input className="input" type="email" value={form.auditee_email} onChange={(e) => setField("auditee_email", e.target.value)} placeholder="name@example.com" />
                    </label>
                    <label className="profile-inline-field planner-form-span-2">
                      <span>Auditee label</span>
                      <input className="input" value={form.auditee} onChange={(e) => setField("auditee", e.target.value)} placeholder="Department head, station manager, or accountable holder" />
                    </label>
                  </>
                ) : (
                  <div className="planner-form-span-2 planner-external-group">
                    <div className="planner-external-group__header">
                      <div>
                        <strong>External auditees</strong>
                        <p>Add one or more named auditees with the contacts required for notices and follow-up.</p>
                      </div>
                      <Button variant="secondary" size="sm" onClick={addExternalAuditee}>
                        <UserPlus size={15} />
                        Add auditee
                      </Button>
                    </div>
                    <div className="planner-external-group__list">
                      {form.external_auditees.map((contact, index) => (
                        <div key={`external-${index}`} className="planner-external-card">
                          <div className="planner-external-card__toolbar">
                            <strong>Auditee {index + 1}</strong>
                            <Button variant="ghost" size="sm" onClick={() => removeExternalAuditee(index)} disabled={form.external_auditees.length === 1}>
                              <Trash2 size={14} />
                              Remove
                            </Button>
                          </div>
                          <div className="planner-drawer-form__grid">
                            <label className="profile-inline-field">
                              <span>First name</span>
                              <input className="input" value={contact.first_name} onChange={(e) => setExternalAuditeeField(index, "first_name", e.target.value)} />
                            </label>
                            <label className="profile-inline-field">
                              <span>Last name</span>
                              <input className="input" value={contact.last_name} onChange={(e) => setExternalAuditeeField(index, "last_name", e.target.value)} />
                            </label>
                            <label className="profile-inline-field">
                              <span>Email</span>
                              <input className="input" type="email" value={contact.email} onChange={(e) => setExternalAuditeeField(index, "email", e.target.value)} />
                            </label>
                            <label className="profile-inline-field">
                              <span>Phone contact (optional)</span>
                              <input className="input" value={contact.phone_contact || ""} onChange={(e) => setExternalAuditeeField(index, "phone_contact", e.target.value)} />
                            </label>
                            <label className="profile-inline-field planner-form-span-2">
                              <span>Designation / role</span>
                              <input className="input" value={contact.designation} onChange={(e) => setExternalAuditeeField(index, "designation", e.target.value)} placeholder="Quality manager, regulator representative, customer liaison, etc." />
                            </label>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <label className="planner-checkbox-field">
                  <input type="checkbox" checked={form.is_active} onChange={(e) => setField("is_active", e.target.checked)} />
                  <span>Schedule active</span>
                </label>
              </div>
            ) : null}

            {drawerTab === "review" ? (
              <div className="planner-review-grid">
                <div className="planner-review-card">
                  <strong>Advanced audit summary</strong>
                  <dl className="planner-review-list">
                    <div><dt>Audit</dt><dd>{form.title.trim() || "Title pending"}</dd></div>
                    <div><dt>Type</dt><dd>{formatKindLabel(form.kind)}</dd></div>
                    <div><dt>Frequency</dt><dd>{formatFrequencyLabel(form.frequency)}</dd></div>
                    <div><dt>Next due</dt><dd>{form.next_due_date ? formatDate(form.next_due_date) : "Select a date"}</dd></div>
                    <div><dt>Duration</dt><dd>{form.duration_days || "1"} day(s)</dd></div>
                    <div><dt>Scope</dt><dd>{form.scope.trim() || "Not set"}</dd></div>
                    <div><dt>Criteria</dt><dd>{form.criteria.trim() || "Not set"}</dd></div>
                    <div><dt>Lead auditor</dt><dd>{leadAuditorUser ? userLabel(leadAuditorUser) : "Not assigned"}</dd></div>
                    <div><dt>Auditee model</dt><dd>{form.kind === "INTERNAL" ? "Internal personnel selection" : `${cleanedExternalAuditees.length} named external auditee(s)`}</dd></div>
                  </dl>
                </div>

                <div className="planner-review-card">
                  <strong>Notification and reminder plan</strong>
                  <div className="planner-notice-grid">
                    <label className="planner-checkbox-field">
                      <input type="checkbox" checked={form.notify_auditors} onChange={(e) => setField("notify_auditors", e.target.checked)} />
                      <span><BellRing size={15} /> Notify auditors</span>
                    </label>
                    <label className="planner-checkbox-field">
                      <input type="checkbox" checked={form.notify_auditees} onChange={(e) => setField("notify_auditees", e.target.checked)} />
                      <span><MailCheck size={15} /> Notify auditees</span>
                    </label>
                  </div>
                  <p className="planner-inline-note">Reminder cadence is currently manual-by-interval and will later support availability checks and auto-scheduling.</p>
                  <div className="planner-recipient-list">
                    {recipientSummary.map((item) => (
                      <div key={item.key} className={`planner-recipient-chip${item.muted ? " is-muted" : ""}`}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="planner-review-card planner-review-card--muted">
                  <strong>What happens next</strong>
                  <span>Save the schedule first. When you run it, the audit is created with its participant set, notice preferences, reminder interval, and execution window carried into the live workspace.</span>
                </div>
              </div>
            ) : null}

            {personnelQuery.isLoading ? <p className="planner-inline-note">Loading personnel options…</p> : null}
            {personnelQuery.isError ? <p className="planner-form-error">Personnel options could not be loaded. You can still type free text for auditee details.</p> : null}
            {error ? <p className="planner-form-error">{error}</p> : null}
          </div>

          <div className="planner-drawer-layout__footer">
            <div className="planner-drawer-layout__footer-left">
              <Button variant="secondary" onClick={discardDraft}>Discard draft</Button>
            </div>
            <div className="planner-drawer-layout__footer-right">
              <Button variant="ghost" onClick={() => setDrawerTab(drawerTabs[Math.max(activeDrawerTabIndex - 1, 0)].id)} disabled={!canGoBackDrawerTab}>
                Back
              </Button>
              {canGoForwardDrawerTab ? (
                <Button variant="secondary" onClick={() => setDrawerTab(drawerTabs[Math.min(activeDrawerTabIndex + 1, drawerTabs.length - 1)].id)}>
                  Next
                </Button>
              ) : null}
              <Button onClick={() => saveSchedule.mutate()} loading={saveSchedule.isPending}>
                <Plus size={16} />
                {editingScheduleId ? "Save changes" : "Save schedule"}
              </Button>
            </div>
          </div>
        </div>
      </Drawer>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
