import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  LayoutList,
  MailCheck,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import SectionCard from "../../components/shared/SectionCard";
import Button from "../../components/UI/Button";
import EmptyState from "../../components/shared/EmptyState";
import Drawer from "../../components/shared/Drawer";
import { useToast } from "../../components/feedback/ToastProvider";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsDeleteAuditSchedule,
  qmsListAuditPersonnelOptions,
  qmsListAuditSchedules,
  qmsRunAuditSchedule,
  qmsUpdateAuditSchedule,
  type QMSAuditScheduleFrequency,
  type QMSAuditScheduleOut,
  type QMSExternalAuditeeContact,
  type QMSPersonOption,
} from "../../services/qms";

type PlannerView = "calendar" | "list" | "table";
type DrawerTab = "overview" | "participants" | "review";
type AuditKind = "INTERNAL" | "EXTERNAL" | "THIRD_PARTY";

type ScheduleViewModel = QMSAuditScheduleOut & {
  is_preview?: boolean;
  preview_label?: string;
};

type PersonSearchField =
  | "auditee_user_id"
  | "lead_auditor_user_id"
  | "observer_auditor_user_id"
  | "assistant_auditor_user_id";

type ScheduleFormState = {
  title: string;
  kind: AuditKind;
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

function userLabel(user?: QMSPersonOption | null): string {
  if (!user) return "Unassigned";
  return user.position_title ? `${user.full_name} · ${user.position_title}` : user.full_name;
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [form, setForm] = useState<ScheduleFormState>(defaultSchedule);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
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

  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", amoCode],
    queryFn: () => qmsListAuditPersonnelOptions({ limit: 100 }),
    staleTime: 5 * 60_000,
  });

  const schedules = schedulesQuery.data ?? [];
  const personnelOptions = personnelQuery.data ?? [];
  const peopleById = useMemo(() => {
    const next = new Map<string, QMSPersonOption>();
    personnelOptions.forEach((person) => next.set(person.id, person));
    return next;
  }, [personnelOptions]);

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

  const seedDate = useMemo(() => {
    const firstDue = boardSchedules.find((row) => row.next_due_date)?.next_due_date;
    return firstDue ? new Date(firstDue) : new Date();
  }, [boardSchedules]);

  useEffect(() => {
    setVisibleMonth((prev) => prev ?? new Date(seedDate.getFullYear(), seedDate.getMonth(), 1));
  }, [seedDate]);

  const activeCalendarMonth = visibleMonth ?? new Date(seedDate.getFullYear(), seedDate.getMonth(), 1);
  const calendarCells = useMemo(() => monthGrid(activeCalendarMonth), [activeCalendarMonth]);

  const scheduleSummary = useMemo(
    () => [
      { label: "Visible schedules", value: String(boardSchedules.length) },
      { label: "Next due", value: boardSchedules[0]?.next_due_date ? formatDate(boardSchedules[0].next_due_date) : "Not scheduled" },
      {
        label: editingScheduleId ? "Editing" : isMeaningfulDraft(form) ? "Staged draft" : "Draft state",
        value: editingScheduleId ? "Existing schedule" : isMeaningfulDraft(form) ? "Autosaved" : "Clean",
      },
    ],
    [boardSchedules, editingScheduleId, form]
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
      pushToast({ title: "Audit issued", message: "The live audit has been created from the selected schedule.", variant: "success", sound: true });
    },
  });

  const dismissGuide = () => {
    setGuideDismissed(true);
    if (typeof window !== "undefined") window.localStorage.setItem(guideStorageKey, "1");
  };

  const handleDelete = (schedule: QMSAuditScheduleOut) => {
    const confirmDelete = window.confirm(`Delete schedule \"${schedule.title}\" due ${formatDate(schedule.next_due_date)}?`);
    if (!confirmDelete) return;
    deleteSchedule.mutate(schedule);
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

  const renderCalendar = () => {
    const byDate = new Map<string, ScheduleViewModel[]>();
    boardSchedules.forEach((schedule) => {
      const key = schedule.next_due_date;
      if (!key) return;
      const group = byDate.get(key) ?? [];
      group.push(schedule);
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
              const daySchedules = byDate.get(dateKey) ?? [];
              return (
                <div key={cell.key} className={`planner-calendar-cell${cell.inMonth ? "" : " is-outside"}${cell.isToday ? " is-today" : ""}`}>
                  <div className="planner-calendar-cell__date">{cell.date.getDate()}</div>
                  <div className="planner-calendar-cell__items">
                    {daySchedules.map((schedule) => {
                      const countdown = countdownLabel(schedule.next_due_date);
                      const leadUser = schedule.lead_auditor_user_id ? peopleById.get(schedule.lead_auditor_user_id) : null;
                      return (
                        <button
                          key={schedule.id}
                          type="button"
                          className={`planner-calendar-event${schedule.is_preview ? " planner-calendar-event--preview" : ""}`}
                          onClick={() => (schedule.is_preview ? setDrawerOpen(true) : beginEdit(schedule))}
                        >
                          <strong>{schedule.title}</strong>
                          <span>{schedule.preview_label || formatKindLabel(schedule.kind)}</span>
                          <span>{leadUser ? userLabel(leadUser) : "Lead auditor pending"}</span>
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
              <div><dt>Scope</dt><dd>{schedule.scope || "No scope added yet"}</dd></div>
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
        <Button variant="secondary" size="sm" onClick={() => schedulesQuery.refetch()}>
          <RefreshCw size={15} />
          Refresh
        </Button>
      }
    >
      <div className="qms-page-grid">
        {!guideDismissed ? (
          <SectionCard variant="subtle" className="planner-guide-card">
            <div className="planner-guide-card__header">
              <div>
                <p className="planner-guide-card__eyebrow">First-time guide</p>
                <h3 className="planner-guide-card__title">Full audit lifecycle from schedule to closure</h3>
              </div>
              <Button variant="ghost" size="sm" onClick={dismissGuide}>Dismiss</Button>
            </div>
            <div className="planner-guide-card__grid">
              {lifecycleSummaryItems.map((item) => (
                <div key={item.label} className="planner-guide-card__step">
                  <strong>{item.label}</strong>
                  <span>{item.detail}</span>
                </div>
              ))}
            </div>
          </SectionCard>
        ) : null}

        <SectionCard variant="subtle" className="qms-compact-toolbar-card">
          <div className="qms-toolbar qms-toolbar--portal" style={{ justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <Button size="sm" onClick={openCreateDrawer}>
                <Plus size={15} />
                Create schedule
              </Button>
              <span className="planner-inline-note">Schedules now support internal or external auditee workflows, notice settings, and a structured pre-run review.</span>
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

        <SectionCard title={view === "calendar" ? "Upcoming schedule board" : view === "list" ? "Schedule list" : "Schedule register"} subtitle={view === "calendar" ? "The board reflects staged edits before save so the planner stays predictable." : undefined} eyebrow={view === "calendar" ? "Calendar view" : "Planner"}>
          {schedulesQuery.isLoading ? <p className="qms-loading-copy">Loading schedules…</p> : null}
          {!schedulesQuery.isLoading && !boardSchedules.length ? <EmptyState title="No active schedules yet" description="Create a schedule to populate the planner views." /> : null}
          {!schedulesQuery.isLoading && boardSchedules.length ? (view === "calendar" ? renderCalendar() : view === "list" ? renderList() : renderTable()) : null}
        </SectionCard>
      </div>

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
