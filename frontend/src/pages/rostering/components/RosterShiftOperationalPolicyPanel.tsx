import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Clock3, Save, ShieldCheck } from "lucide-react";

import {
  listRosterShiftOperationalPolicies,
  updateRosterShiftOperationalPolicy,
  type RosterShiftCalendarMode,
  type RosterShiftDutySemantic,
  type RosterShiftOperationalPolicy,
  type RosterShiftVerification,
} from "../../../services/rosteringShiftSemantics";
import { errorMessage } from "../rosterUi";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import { RosterLoading, StatusPill } from "./RosterShell";

const SHIFT_POLICY_KEY = ["rostering", "settings", "shift-operational-policies"] as const;
const SEMANTICS: RosterShiftDutySemantic[] = ["DUTY", "STANDBY", "TRAINING", "REST", "OFF", "LEAVE", "SICK", "OTHER"];
const CALENDAR_MODES: RosterShiftCalendarMode[] = ["TIMED", "ALL_DAY", "HIDDEN"];
const VERIFICATION_STATES: RosterShiftVerification[] = ["CONFIRMED", "REVIEW_REQUIRED", "UNRESOLVED"];
const DUTY_SEMANTICS: RosterShiftDutySemantic[] = ["DUTY", "STANDBY", "TRAINING"];

type Draft = {
  counts_as_duty: boolean;
  counts_as_rest: boolean;
  on_site_availability: boolean;
  scheduling_eligible: boolean;
  calendar_mode: RosterShiftCalendarMode;
  duty_semantic: RosterShiftDutySemantic;
  verification_status: RosterShiftVerification;
  unpaid_break_minutes: number;
  requires_personnel_acknowledgement: boolean;
  requires_supervisor_approval: boolean;
  fatigue_weight: number;
  pay_classification: string;
  effective_from: string;
  effective_to: string;
  source_reference: string;
};

function draftFrom(row: RosterShiftOperationalPolicy): Draft {
  return {
    counts_as_duty: row.counts_as_duty,
    counts_as_rest: row.counts_as_rest,
    on_site_availability: row.on_site_availability,
    scheduling_eligible: row.scheduling_eligible,
    calendar_mode: row.calendar_mode,
    duty_semantic: row.duty_semantic,
    verification_status: row.verification_status,
    unpaid_break_minutes: row.unpaid_break_minutes,
    requires_personnel_acknowledgement: row.requires_personnel_acknowledgement,
    requires_supervisor_approval: row.requires_supervisor_approval,
    fatigue_weight: row.fatigue_weight,
    pay_classification: row.pay_classification || "",
    effective_from: row.effective_from || "",
    effective_to: row.effective_to || "",
    source_reference: row.source_reference || "",
  };
}

function sameDraft(left: Draft, right: Draft): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function timeLabel(row: RosterShiftOperationalPolicy): string {
  if (!row.default_start_time || !row.default_end_time) return "Assignment-specific time";
  return `${row.default_start_time}–${row.default_end_time}${row.spans_midnight ? " · crosses midnight" : ""}`;
}

function PolicyEditor({
  row,
  canManage,
  saving,
  onSave,
}: {
  row: RosterShiftOperationalPolicy;
  canManage: boolean;
  saving: boolean;
  onSave: (row: RosterShiftOperationalPolicy, draft: Draft) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(row));
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(draftFrom(row));
    setLocalError(null);
  }, [row]);

  const initial = useMemo(() => draftFrom(row), [row]);
  const changed = !sameDraft(initial, draft);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }));

  const save = async () => {
    if (draft.counts_as_duty && draft.counts_as_rest) {
      setLocalError("A shift cannot count as both duty and a roster rest designation.");
      return;
    }
    if (draft.on_site_availability && !draft.counts_as_duty) {
      setLocalError("On-site availability/standby must count as duty because personnel are not relieved from all duties.");
      return;
    }
    if (["REST", "OFF"].includes(draft.duty_semantic) && draft.counts_as_duty) {
      setLocalError("REST/OFF semantics cannot count as duty. Use DUTY or STANDBY instead.");
      return;
    }
    if (DUTY_SEMANTICS.includes(draft.duty_semantic) && !draft.counts_as_duty) {
      setLocalError("DUTY, STANDBY and TRAINING semantics must count as duty.");
      return;
    }
    if (draft.effective_from && draft.effective_to && draft.effective_to < draft.effective_from) {
      setLocalError("Policy end date cannot precede its start date.");
      return;
    }
    setLocalError(null);
    await onSave(row, draft);
  };

  return (
    <details className="wr-native-guidance">
      <summary>
        <span><strong>{row.code} · {row.label}</strong><small>{timeLabel(row)} · {row.kind.replace(/_/g, " ")}</small></span>
        <StatusPill value={row.effective_scheduling_eligible ? "SCHEDULABLE" : "HISTORY ONLY"} tone={row.effective_scheduling_eligible ? "good" : "warning"} />
      </summary>
      <div className="wr-form-grid">
        <label><span>Duty semantic</span><select value={draft.duty_semantic} disabled={!canManage} onChange={(event) => set("duty_semantic", event.target.value as RosterShiftDutySemantic)}>{SEMANTICS.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Calendar mode</span><select value={draft.calendar_mode} disabled={!canManage} onChange={(event) => set("calendar_mode", event.target.value as RosterShiftCalendarMode)}>{CALENDAR_MODES.map((value) => <option key={value}>{value.replace(/_/g, " ")}</option>)}</select></label>
        <label><span>Verification</span><select value={draft.verification_status} disabled={!canManage} onChange={(event) => set("verification_status", event.target.value as RosterShiftVerification)}>{VERIFICATION_STATES.map((value) => <option key={value}>{value.replace(/_/g, " ")}</option>)}</select></label>
        <label><span>Unpaid break minutes</span><input type="number" min="0" max="1440" value={draft.unpaid_break_minutes} disabled={!canManage} onChange={(event) => set("unpaid_break_minutes", Number(event.target.value))} /></label>
        <label><span>Fatigue weight</span><input type="number" min="0" max="100" step="0.1" value={draft.fatigue_weight} disabled={!canManage} onChange={(event) => set("fatigue_weight", Number(event.target.value))} /></label>
        <label><span>Pay classification</span><input value={draft.pay_classification} disabled={!canManage} placeholder="Tenant-defined pay classification" onChange={(event) => set("pay_classification", event.target.value)} /></label>
        <label><span>Policy effective from</span><input type="date" value={draft.effective_from} disabled={!canManage} onChange={(event) => set("effective_from", event.target.value)} /></label>
        <label><span>Policy effective to</span><input type="date" value={draft.effective_to} disabled={!canManage} onChange={(event) => set("effective_to", event.target.value)} /></label>
        <label className="wr-span-2"><span>Controlled source / evidence</span><input value={draft.source_reference} disabled={!canManage} placeholder="Tenant-approved controlled source or policy" onChange={(event) => set("source_reference", event.target.value)} /></label>
      </div>
      <div className="wr-form-grid wr-form-grid--inspector">
        <label><input type="checkbox" checked={draft.counts_as_duty} disabled={!canManage} onChange={(event) => set("counts_as_duty", event.target.checked)} /> Counts as duty</label>
        <label><input type="checkbox" checked={draft.counts_as_rest} disabled={!canManage} onChange={(event) => set("counts_as_rest", event.target.checked)} /> Roster rest designation</label>
        <label><input type="checkbox" checked={draft.on_site_availability} disabled={!canManage} onChange={(event) => set("on_site_availability", event.target.checked)} /> Personnel remain on-site / available</label>
        <label><input type="checkbox" checked={draft.scheduling_eligible} disabled={!canManage} onChange={(event) => set("scheduling_eligible", event.target.checked)} /> Eligible for new scheduling</label>
        <label><input type="checkbox" checked={draft.requires_personnel_acknowledgement} disabled={!canManage} onChange={(event) => set("requires_personnel_acknowledgement", event.target.checked)} /> Requires personnel acknowledgement</label>
        <label><input type="checkbox" checked={draft.requires_supervisor_approval} disabled={!canManage} onChange={(event) => set("requires_supervisor_approval", event.target.checked)} /> Requires supervisor approval</label>
      </div>
      {row.spans_midnight ? <div className="wr-inline-note"><Clock3 size={15} /> This template crosses midnight. Compliance uses the resulting timestamp interval, not the calendar cell.</div> : null}
      {draft.counts_as_rest ? <div className="wr-inline-warning"><AlertTriangle size={15} /> A rest/off code is only roster evidence. It does not itself prove uninterrupted protected rest; the compliance engine still checks the surrounding timestamps.</div> : null}
      {localError ? <div className="wr-inline-error" role="alert">{localError}</div> : null}
      {canManage ? <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--primary" disabled={!changed || saving} onClick={() => void save()}><Save size={14} /> Save operational policy</button></div> : null}
    </details>
  );
}

export function RosterShiftOperationalPolicyPanel() {
  const queryClient = useQueryClient();
  const policiesQuery = useQuery({ queryKey: SHIFT_POLICY_KEY, queryFn: listRosterShiftOperationalPolicies, staleTime: 5 * 60_000 });
  const permissionsQuery = useWorkforcePermissions();
  const canManage = (permissionsQuery.data?.permissions || []).includes("roster.manage_shift_semantics");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const save = async (row: RosterShiftOperationalPolicy, draft: Draft) => {
    setBusy(row.shift_template_id);
    setActionError(null);
    try {
      await updateRosterShiftOperationalPolicy(row.shift_template_id, {
        counts_as_duty: draft.counts_as_duty,
        counts_as_rest: draft.counts_as_rest,
        on_site_availability: draft.on_site_availability,
        scheduling_eligible: draft.scheduling_eligible,
        calendar_mode: draft.calendar_mode,
        duty_semantic: draft.duty_semantic,
        verification_status: draft.verification_status,
        unpaid_break_minutes: draft.unpaid_break_minutes,
        requires_personnel_acknowledgement: draft.requires_personnel_acknowledgement,
        requires_supervisor_approval: draft.requires_supervisor_approval,
        fatigue_weight: draft.fatigue_weight,
        pay_classification: draft.pay_classification.trim() || null,
        effective_from: draft.effective_from || null,
        effective_to: draft.effective_to || null,
        source_reference: draft.source_reference.trim() || null,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: SHIFT_POLICY_KEY }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "settings", "shifts"] }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "settings", "code-registry"] }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "planner"] }),
      ]);
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally { setBusy(null); }
  };

  if (policiesQuery.isPending && !policiesQuery.data) return <RosterLoading label="Loading shift operational policy…" />;
  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div><span className="wr-eyebrow">Tenant-owned duty semantics</span><h2><ShieldCheck size={19} /> Shift operational policy</h2><p>Configure what each tenant shift means. No tenant code, shift time, form number or operating pattern is imposed by the portal.</p></div>
        <span className="wr-header-badge">{(policiesQuery.data || []).length} templates</span>
      </div>
      <div className="wr-inline-warning"><ShieldCheck size={16} /> On-site standby/availability must count as duty. REST/OFF labels never replace the timestamp-based protected-rest calculation.</div>
      {actionError || policiesQuery.error ? <div className="wr-inline-error" role="alert">{actionError || errorMessage(policiesQuery.error)}</div> : null}
      <div className="wr-recommendation-list">{(policiesQuery.data || []).map((row) => <PolicyEditor key={row.shift_template_id} row={row} canManage={canManage} saving={busy === row.shift_template_id} onSave={save} />)}</div>
      {!canManage ? <div className="wr-inline-note">You can review tenant shift semantics. Editing requires the governed roster-semantics permission.</div> : null}
    </section>
  );
}
