import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock3,
  MapPin,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Button from "../../../components/UI/Button";
import { apiRequest, qmsPath } from "../../../services/apiClient";
import "../../../styles/qms-planner-schedule-dialog.css";

type PersonOption = {
  id: string;
  full_name: string;
  email?: string | null;
  role?: string | null;
  department_name?: string | null;
};

type ScopeOption = {
  id: string;
  code: string;
  name: string;
  party_level: string;
  default_kind: string;
};

type ScheduleOptions = {
  timezone_name: string;
  frequencies: string[];
  kinds: string[];
  scopes: ScopeOption[];
  people: PersonOption[];
};

type ExternalAuditeeDraft = {
  first_name: string;
  last_name: string;
  email: string;
  phone_contact: string;
  designation: string;
};

type ExternalAttendeeDraft = {
  name: string;
  email: string;
  designation: string;
};

type ScheduleResponse = {
  id: string;
  title: string;
  next_due_date: string;
  start_time?: string | null;
  automation_active: boolean;
  notifications_queued: number;
};

type Props = {
  amoCode: string;
  open: boolean;
  initialDate: string;
  initialTime?: string;
  initialTitle?: string;
  onClose: () => void;
  onCreated: (schedule: ScheduleResponse) => void;
};

type FormState = {
  title: string;
  kind: string;
  audit_scope_id: string;
  frequency: string;
  next_due_date: string;
  start_time: string;
  end_time: string;
  duration_days: number;
  location: string;
  scope: string;
  criteria: string;
  notes: string;
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  assistant_auditor_user_id: string;
  auditee_user_id: string;
  attendee_user_ids: string[];
  external_auditees: ExternalAuditeeDraft[];
  external_attendees: ExternalAttendeeDraft[];
  notify_auditors: boolean;
  notify_auditees: boolean;
  notify_attendees: boolean;
  reminder_interval_days: number;
  automation_active: boolean;
};

const EMPTY_EXTERNAL_AUDITEE: ExternalAuditeeDraft = {
  first_name: "",
  last_name: "",
  email: "",
  phone_contact: "",
  designation: "",
};

const EMPTY_EXTERNAL_ATTENDEE: ExternalAttendeeDraft = {
  name: "",
  email: "",
  designation: "",
};

function defaultForm(initialDate: string, initialTime = "09:00", initialTitle = ""): FormState {
  return {
    title: initialTitle,
    kind: "INTERNAL",
    audit_scope_id: "",
    frequency: "ONE_TIME",
    next_due_date: initialDate,
    start_time: initialTime || "09:00",
    end_time: "",
    duration_days: 1,
    location: "",
    scope: "",
    criteria: "",
    notes: "",
    lead_auditor_user_id: "",
    observer_auditor_user_id: "",
    assistant_auditor_user_id: "",
    auditee_user_id: "",
    attendee_user_ids: [],
    external_auditees: [],
    external_attendees: [],
    notify_auditors: true,
    notify_auditees: true,
    notify_attendees: true,
    reminder_interval_days: 7,
    automation_active: true,
  };
}

function friendlyError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "The schedule could not be created. Review the details and try again.";
}

function personLabel(person: PersonOption): string {
  const suffix = [person.role?.replaceAll("_", " "), person.department_name].filter(Boolean).join(" · ");
  return suffix ? `${person.full_name} — ${suffix}` : person.full_name;
}

function validExternalAuditee(item: ExternalAuditeeDraft): boolean {
  return Boolean(item.first_name.trim() && item.last_name.trim() && item.email.trim() && item.designation.trim());
}

function validExternalAttendee(item: ExternalAttendeeDraft): boolean {
  return Boolean(item.name.trim() && item.email.trim());
}

export default function QmsPlannerScheduleDialog({
  amoCode,
  open,
  initialDate,
  initialTime = "09:00",
  initialTitle = "",
  onClose,
  onCreated,
}: Props): React.ReactElement | null {
  const [options, setOptions] = useState<ScheduleOptions | null>(null);
  const [form, setForm] = useState<FormState>(() => defaultForm(initialDate, initialTime, initialTitle));
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [peopleQuery, setPeopleQuery] = useState("");
  const [attendeePickerOpen, setAttendeePickerOpen] = useState(false);
  const titleRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setForm(defaultForm(initialDate, initialTime, initialTitle));
    setError(null);
    setPeopleQuery("");
    setAttendeePickerOpen(false);
  }, [initialDate, initialTime, initialTitle, open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingOptions(true);
    apiRequest<ScheduleOptions>(qmsPath(amoCode, "/integrations/calendar/schedule-options"), { timeoutMs: 15000 })
      .then((result) => {
        if (cancelled) return;
        setOptions(result);
        setForm((current) => ({
          ...current,
          audit_scope_id: current.audit_scope_id || result.scopes[0]?.id || "",
          kind: current.kind || result.scopes[0]?.default_kind || "INTERNAL",
        }));
        window.setTimeout(() => titleRef.current?.focus(), 0);
      })
      .catch((loadError) => {
        if (!cancelled) setError(friendlyError(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoadingOptions(false);
      });
    return () => {
      cancelled = true;
    };
  }, [amoCode, open]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (attendeePickerOpen) {
        setAttendeePickerOpen(false);
        return;
      }
      if (!saving) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [attendeePickerOpen, onClose, open, saving]);

  const people = options?.people || [];
  const peopleById = useMemo(() => new Map(people.map((person) => [person.id, person])), [people]);
  const attendeeCandidates = useMemo(() => {
    const query = peopleQuery.trim().toLowerCase();
    return people
      .filter((person) => !form.attendee_user_ids.includes(person.id))
      .filter((person) => !query || [person.full_name, person.email, person.role, person.department_name].some((value) => String(value || "").toLowerCase().includes(query)))
      .slice(0, 50);
  }, [form.attendee_user_ids, people, peopleQuery]);

  const selectedScope = options?.scopes.find((scope) => scope.id === form.audit_scope_id) || null;
  const hasAuditee = Boolean(
    form.auditee_user_id
    || form.external_auditees.some(validExternalAuditee),
  );
  const canSubmit = Boolean(
    options
    && form.title.trim()
    && form.audit_scope_id
    && form.next_due_date
    && form.start_time
    && form.lead_auditor_user_id
    && hasAuditee
    && (!form.end_time || form.end_time > form.start_time),
  );

  const updateExternalAuditee = (index: number, patch: Partial<ExternalAuditeeDraft>) => {
    setForm((current) => ({
      ...current,
      external_auditees: current.external_auditees.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }));
  };

  const updateExternalAttendee = (index: number, patch: Partial<ExternalAttendeeDraft>) => {
    setForm((current) => ({
      ...current,
      external_attendees: current.external_attendees.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || saving || !options) return;
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: form.title.trim(),
        domain: "AMO",
        kind: form.kind,
        audit_scope_id: form.audit_scope_id,
        frequency: form.frequency,
        next_due_date: form.next_due_date,
        start_time: form.start_time,
        end_time: form.end_time || null,
        duration_days: form.duration_days,
        timezone_name: options.timezone_name,
        location: form.location.trim() || null,
        scope: form.scope.trim() || null,
        criteria: form.criteria.trim() || null,
        notes: form.notes.trim() || null,
        auditee_user_id: form.auditee_user_id || null,
        external_auditees: form.external_auditees.filter(validExternalAuditee).map((item) => ({
          first_name: item.first_name.trim(),
          last_name: item.last_name.trim(),
          email: item.email.trim(),
          phone_contact: item.phone_contact.trim() || null,
          designation: item.designation.trim(),
        })),
        lead_auditor_user_id: form.lead_auditor_user_id,
        observer_auditor_user_id: form.observer_auditor_user_id || null,
        assistant_auditor_user_id: form.assistant_auditor_user_id || null,
        attendee_user_ids: form.attendee_user_ids,
        external_attendees: form.external_attendees.filter(validExternalAttendee).map((item) => ({
          name: item.name.trim(),
          email: item.email.trim(),
          designation: item.designation.trim() || null,
        })),
        notify_auditors: form.notify_auditors,
        notify_auditees: form.notify_auditees,
        notify_attendees: form.notify_attendees,
        reminder_interval_days: form.reminder_interval_days,
        automation_active: form.automation_active,
      };
      const created = await apiRequest<ScheduleResponse>(qmsPath(amoCode, "/integrations/calendar/audit-schedules"), {
        method: "POST",
        timeoutMs: 20000,
        body: JSON.stringify(payload),
      });
      onCreated(created);
    } catch (saveError) {
      setError(friendlyError(saveError));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="qms-schedule-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !saving) onClose(); }}>
      <section className="qms-schedule-dialog" role="dialog" aria-modal="true" aria-labelledby="qms-schedule-dialog-title">
        <header className="qms-schedule-dialog__header">
          <div className="qms-schedule-dialog__heading">
            <span><CalendarClock size={16} /> Quality Operations Planner</span>
            <strong id="qms-schedule-dialog-title">Create an automated audit schedule</strong>
            <small>Set the full responsibility, timing, recurrence, and notification contract without leaving the planner.</small>
          </div>
          <button type="button" aria-label="Close schedule dialog" onClick={onClose} disabled={saving}><X size={20} /></button>
        </header>

        <form onSubmit={submit}>
          {error ? <div className="qms-schedule-dialog__error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div> : null}
          {loadingOptions ? <div className="qms-schedule-dialog__loading"><CalendarClock size={18} /><span>Loading audit scopes and active personnel…</span></div> : null}

          <div className="qms-schedule-dialog__body" aria-busy={loadingOptions}>
            <section className="qms-schedule-section qms-schedule-section--primary">
              <header><div><ShieldCheck size={17} /><span><strong>Audit definition</strong><small>Authoritative QMS schedule details</small></span></div></header>
              <div className="qms-schedule-grid qms-schedule-grid--2">
                <label className="qms-schedule-field qms-schedule-field--wide">
                  <span>Audit title <b>*</b></span>
                  <input ref={titleRef} value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="e.g. Procurement and supplier-control audit" maxLength={255} />
                </label>
                <label className="qms-schedule-field">
                  <span>Audit scope <b>*</b></span>
                  <select value={form.audit_scope_id} onChange={(event) => {
                    const scope = options?.scopes.find((item) => item.id === event.target.value);
                    setForm((current) => ({ ...current, audit_scope_id: event.target.value, kind: scope?.default_kind || current.kind }));
                  }}>
                    <option value="">Select scope</option>
                    {(options?.scopes || []).map((scope) => <option key={scope.id} value={scope.id}>{scope.code} · {scope.name}</option>)}
                  </select>
                  {selectedScope ? <small>{selectedScope.party_level.replaceAll("_", " ")}</small> : null}
                </label>
                <label className="qms-schedule-field">
                  <span>Audit kind</span>
                  <select value={form.kind} onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value }))}>
                    {(options?.kinds || ["INTERNAL", "EXTERNAL", "THIRD_PARTY"]).map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}
                  </select>
                </label>
                <label className="qms-schedule-field qms-schedule-field--wide">
                  <span>Scope statement</span>
                  <textarea rows={2} value={form.scope} onChange={(event) => setForm((current) => ({ ...current, scope: event.target.value }))} placeholder="Departments, processes, locations, products, or approvals covered" />
                </label>
                <label className="qms-schedule-field qms-schedule-field--wide">
                  <span>Audit criteria</span>
                  <textarea rows={2} value={form.criteria} onChange={(event) => setForm((current) => ({ ...current, criteria: event.target.value }))} placeholder="KCARs, MOE/MPM, procedures, contracts, standards, or checklist references" />
                </label>
              </div>
            </section>

            <section className="qms-schedule-section">
              <header><div><Clock3 size={17} /><span><strong>Timing and recurrence</strong><small>Runs automatically until suspended</small></span></div></header>
              <div className="qms-schedule-grid qms-schedule-grid--3">
                <label className="qms-schedule-field"><span>First audit date <b>*</b></span><input type="date" value={form.next_due_date} onChange={(event) => setForm((current) => ({ ...current, next_due_date: event.target.value }))} /></label>
                <label className="qms-schedule-field"><span>Start time <b>*</b></span><input type="time" value={form.start_time} onChange={(event) => setForm((current) => ({ ...current, start_time: event.target.value }))} /></label>
                <label className="qms-schedule-field"><span>End time</span><input type="time" value={form.end_time} onChange={(event) => setForm((current) => ({ ...current, end_time: event.target.value }))} /><small>{form.end_time && form.end_time <= form.start_time ? "End time must be later." : options?.timezone_name || "Africa/Nairobi"}</small></label>
                <label className="qms-schedule-field"><span>Recurrence</span><select value={form.frequency} onChange={(event) => setForm((current) => ({ ...current, frequency: event.target.value }))}>{(options?.frequencies || ["ONE_TIME"]).map((frequency) => <option key={frequency} value={frequency}>{frequency.replaceAll("_", " ")}</option>)}</select></label>
                <label className="qms-schedule-field"><span>Duration</span><select value={form.duration_days} onChange={(event) => setForm((current) => ({ ...current, duration_days: Number(event.target.value) }))}>{Array.from({ length: 14 }, (_, index) => index + 1).map((days) => <option key={days} value={days}>{days} day{days === 1 ? "" : "s"}</option>)}</select></label>
                <label className="qms-schedule-field"><span><MapPin size={13} /> Location / base</span><input value={form.location} onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))} placeholder="Hangar, base, department, or remote" /></label>
              </div>
              <label className="qms-schedule-automation"><input type="checkbox" checked={form.automation_active} onChange={(event) => setForm((current) => ({ ...current, automation_active: event.target.checked }))} /><span><strong>Activate automatic scheduler</strong><small>The backend creates each due audit automatically and advances the next occurrence until this schedule is suspended.</small></span></label>
            </section>

            <section className="qms-schedule-section">
              <header><div><UserRound size={17} /><span><strong>Responsibility</strong><small>Named ownership and auditee accountability</small></span></div></header>
              <div className="qms-schedule-grid qms-schedule-grid--2">
                <label className="qms-schedule-field"><span>Lead auditor <b>*</b></span><select value={form.lead_auditor_user_id} onChange={(event) => setForm((current) => ({ ...current, lead_auditor_user_id: event.target.value }))}><option value="">Select lead auditor</option>{people.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select></label>
                <label className="qms-schedule-field"><span>Primary auditee <b>*</b></span><select value={form.auditee_user_id} onChange={(event) => setForm((current) => ({ ...current, auditee_user_id: event.target.value }))}><option value="">External auditee / select later</option>{people.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select><small>An internal auditee or complete external auditee is required.</small></label>
                <label className="qms-schedule-field"><span>Observer auditor</span><select value={form.observer_auditor_user_id} onChange={(event) => setForm((current) => ({ ...current, observer_auditor_user_id: event.target.value }))}><option value="">None</option>{people.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select></label>
                <label className="qms-schedule-field"><span>Assistant auditor</span><select value={form.assistant_auditor_user_id} onChange={(event) => setForm((current) => ({ ...current, assistant_auditor_user_id: event.target.value }))}><option value="">None</option>{people.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select></label>
              </div>

              <div className="qms-schedule-attendees">
                <div className="qms-schedule-attendees__label"><Users size={15} /><span><strong>Additional internal attendees</strong><small>Every selected attendee receives in-app and email notices.</small></span></div>
                <div className="qms-schedule-attendees__chips">
                  {form.attendee_user_ids.map((userId) => {
                    const person = peopleById.get(userId);
                    return <span key={userId}>{person?.full_name || userId}<button type="button" aria-label={`Remove ${person?.full_name || "attendee"}`} onClick={() => setForm((current) => ({ ...current, attendee_user_ids: current.attendee_user_ids.filter((item) => item !== userId) }))}><X size={13} /></button></span>;
                  })}
                  <button type="button" className="qms-schedule-attendees__add" onClick={() => setAttendeePickerOpen((current) => !current)}><Plus size={14} /> Add people <ChevronDown size={13} /></button>
                </div>
                {attendeePickerOpen ? <div className="qms-schedule-people-picker"><label><Search size={14} /><input autoFocus value={peopleQuery} onChange={(event) => setPeopleQuery(event.target.value)} placeholder="Search name, email, role, or department" /></label><div>{attendeeCandidates.map((person) => <button key={person.id} type="button" onClick={() => { setForm((current) => ({ ...current, attendee_user_ids: [...current.attendee_user_ids, person.id] })); setPeopleQuery(""); }}><span><strong>{person.full_name}</strong><small>{[person.email, person.role?.replaceAll("_", " "), person.department_name].filter(Boolean).join(" · ")}</small></span><Plus size={14} /></button>)}{!attendeeCandidates.length ? <p>No matching active personnel.</p> : null}</div></div> : null}
              </div>
            </section>

            <section className="qms-schedule-section">
              <header><div><Users size={17} /><span><strong>External parties</strong><small>Auditees and attendees outside the tenant</small></span></div></header>
              <div className="qms-schedule-external-group">
                <div className="qms-schedule-external-group__heading"><span><strong>External auditees</strong><small>Use for suppliers, contracted organisations, authorities, and third parties.</small></span><button type="button" onClick={() => setForm((current) => ({ ...current, external_auditees: [...current.external_auditees, { ...EMPTY_EXTERNAL_AUDITEE }] }))}><Plus size={14} /> Add auditee</button></div>
                {form.external_auditees.map((item, index) => <div className="qms-schedule-external-row qms-schedule-external-row--auditee" key={`auditee-${index}`}><input aria-label="First name" value={item.first_name} onChange={(event) => updateExternalAuditee(index, { first_name: event.target.value })} placeholder="First name" /><input aria-label="Last name" value={item.last_name} onChange={(event) => updateExternalAuditee(index, { last_name: event.target.value })} placeholder="Last name" /><input aria-label="Email" type="email" value={item.email} onChange={(event) => updateExternalAuditee(index, { email: event.target.value })} placeholder="Email" /><input aria-label="Designation" value={item.designation} onChange={(event) => updateExternalAuditee(index, { designation: event.target.value })} placeholder="Designation" /><input aria-label="Phone contact" value={item.phone_contact} onChange={(event) => updateExternalAuditee(index, { phone_contact: event.target.value })} placeholder="Phone" /><button type="button" aria-label="Remove external auditee" onClick={() => setForm((current) => ({ ...current, external_auditees: current.external_auditees.filter((_, itemIndex) => itemIndex !== index) }))}><Trash2 size={15} /></button></div>)}
                {!form.external_auditees.length ? <p className="qms-schedule-external-empty">No external auditees added.</p> : null}
              </div>

              <div className="qms-schedule-external-group">
                <div className="qms-schedule-external-group__heading"><span><strong>External attendees</strong><small>Observers, specialists, or guests who need schedule alerts.</small></span><button type="button" onClick={() => setForm((current) => ({ ...current, external_attendees: [...current.external_attendees, { ...EMPTY_EXTERNAL_ATTENDEE }] }))}><Plus size={14} /> Add attendee</button></div>
                {form.external_attendees.map((item, index) => <div className="qms-schedule-external-row" key={`attendee-${index}`}><input aria-label="External attendee name" value={item.name} onChange={(event) => updateExternalAttendee(index, { name: event.target.value })} placeholder="Full name" /><input aria-label="External attendee email" type="email" value={item.email} onChange={(event) => updateExternalAttendee(index, { email: event.target.value })} placeholder="Email" /><input aria-label="External attendee designation" value={item.designation} onChange={(event) => updateExternalAttendee(index, { designation: event.target.value })} placeholder="Designation / organisation" /><button type="button" aria-label="Remove external attendee" onClick={() => setForm((current) => ({ ...current, external_attendees: current.external_attendees.filter((_, itemIndex) => itemIndex !== index) }))}><Trash2 size={15} /></button></div>)}
                {!form.external_attendees.length ? <p className="qms-schedule-external-empty">No external attendees added.</p> : null}
              </div>
            </section>

            <section className="qms-schedule-section">
              <header><div><BellRing size={17} /><span><strong>Alerts and reminders</strong><small>Uses the same QMS notification and email delivery controls</small></span></div></header>
              <div className="qms-schedule-notification-grid">
                <label><input type="checkbox" checked={form.notify_auditors} onChange={(event) => setForm((current) => ({ ...current, notify_auditors: event.target.checked }))} /><span><strong>Notify audit team</strong><small>Lead, observer, and assistant auditors</small></span></label>
                <label><input type="checkbox" checked={form.notify_auditees} onChange={(event) => setForm((current) => ({ ...current, notify_auditees: event.target.checked }))} /><span><strong>Notify auditees</strong><small>Internal and external auditee contacts</small></span></label>
                <label><input type="checkbox" checked={form.notify_attendees} onChange={(event) => setForm((current) => ({ ...current, notify_attendees: event.target.checked }))} /><span><strong>Notify attendees</strong><small>Additional internal and external participants</small></span></label>
                <label className="qms-schedule-reminder"><span><strong>Upcoming reminder</strong><small>Days before each audit</small></span><input type="number" min={1} max={60} value={form.reminder_interval_days} onChange={(event) => setForm((current) => ({ ...current, reminder_interval_days: Math.max(1, Math.min(60, Number(event.target.value) || 1)) }))} /></label>
              </div>
            </section>

            <section className="qms-schedule-section qms-schedule-section--notes">
              <header><div><CheckCircle2 size={17} /><span><strong>Planner notes</strong><small>Operational context visible with the schedule</small></span></div></header>
              <label className="qms-schedule-field"><textarea rows={3} value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Access arrangements, preparation instructions, dependencies, or other planning notes" /></label>
            </section>
          </div>

          <footer className="qms-schedule-dialog__footer">
            <div><ShieldCheck size={16} /><span><strong>Controlled creation</strong><small>The schedule, participant alerts, automation state, and audit trail are committed together.</small></span></div>
            <div><Button type="button" variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button><Button type="submit" loading={saving} disabled={!canSubmit || loadingOptions}>Create schedule</Button></div>
          </footer>
        </form>
      </section>
    </div>
  );
}
