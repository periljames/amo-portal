import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock3, GitMerge, PenLine, Plus, Power, Save, ShieldCheck, Trash2, X } from "lucide-react";
import { Link } from "react-router-dom";

import { createShiftTemplate, listShiftTemplates, updateShiftTemplate } from "../../../services/rostering";
import {
  deleteUnusedRosterCode,
  listRosterCodeRegistry,
  mergeDuplicateRosterCode,
  type RosterCodeRegistryEntry,
} from "../../../services/rosteringCodeRegistry";
import { listSetupDepartments, type SetupDepartmentRead } from "../../../services/setupDepartments";
import {
  createWorkPattern,
  deleteWorkPattern,
  listWorkPatterns,
  updateWorkPattern,
} from "../../../services/workforce";
import { listWorkforceHrPositions } from "../../../services/workforceHr";
import type { ShiftTemplateKind, ShiftTemplateRead } from "../../../types/rostering";
import type { ContractType, PatternDayStatus, WorkPatternDayInput, WorkPatternRead } from "../../../types/workforce";
import type { HrPosition } from "../../../types/workforceHr";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

type PatternRecipe = "STANDARD_WEEK" | "FOUR_ON_FOUR_OFF" | "TWO_DAY_TWO_NIGHT" | "CUSTOM";
type ShiftDraft = {
  code: string;
  label: string;
  kind: ShiftTemplateKind;
  start: string;
  end: string;
  description: string;
  isActive: boolean;
  departmentIds: string[];
};

const OFF = "__OFF__";
const CONTRACT_TYPES: ContractType[] = ["PERMANENT", "FIXED_TERM", "TEMPORARY", "CONTRACTOR", "INTERN"];
const SHIFT_KINDS: ShiftTemplateKind[] = ["DAY", "NIGHT", "STANDBY", "TRAINING", "OFF", "LEAVE", "OTHER"];
const RECIPES: Array<{ id: PatternRecipe; title: string; cycle: number; code: string; name: string }> = [
  { id: "STANDARD_WEEK", title: "5D · 2O", cycle: 7, code: "5D2O", name: "Five day, two off" },
  { id: "FOUR_ON_FOUR_OFF", title: "4D · 4O", cycle: 8, code: "4D4O", name: "Four day, four off" },
  { id: "TWO_DAY_TWO_NIGHT", title: "2D · 2N · 4O", cycle: 8, code: "2D2N4O", name: "Two day, two night, four off" },
  { id: "CUSTOM", title: "Custom", cycle: 7, code: "CUSTOM", name: "Custom rotation" },
];

function suggestedAnchor(recipe: PatternRecipe): string {
  const value = new Date();
  if (recipe === "STANDARD_WEEK") value.setDate(value.getDate() - ((value.getDay() + 6) % 7));
  return isoDate(value);
}

function uniqueCode(base: string, patterns: WorkPatternRead[]): string {
  const used = new Set(patterns.map((pattern) => pattern.code.toUpperCase()));
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

function recipeDays(recipe: PatternRecipe, shifts: ShiftTemplateRead[]): Array<string | null> {
  const day = shifts.find((shift) => shift.is_active && shift.kind === "DAY")?.id || null;
  const night = shifts.find((shift) => shift.is_active && shift.kind === "NIGHT")?.id || null;
  if (recipe === "STANDARD_WEEK") return [day, day, day, day, day, null, null];
  if (recipe === "FOUR_ON_FOUR_OFF") return [day, day, day, day, null, null, null, null];
  if (recipe === "TWO_DAY_TWO_NIGHT") return [day, day, night, night, null, null, null, null];
  return Array.from({ length: 7 }, () => null);
}

function shiftSignature(shift: Pick<ShiftTemplateRead, "kind" | "default_start_time" | "default_end_time" | "counts_as_duty">): string {
  return [shift.kind, shift.default_start_time || "", shift.default_end_time || "", String(shift.counts_as_duty)].join("|");
}

function compactShiftCode(shift: ShiftTemplateRead, shifts: ShiftTemplateRead[]): string {
  const current = shift.code.trim().toUpperCase();
  if (/^[A-Z0-9]{1,2}$/.test(current)) return current;
  const preferred: Record<ShiftTemplateKind, string> = {
    DAY: "DY", NIGHT: "NT", STANDBY: "SB", TRAINING: "TR", OFF: "OF", LEAVE: "LV", OTHER: "OT",
  };
  const used = new Set(shifts.filter((item) => item.id !== shift.id).map((item) => item.code.trim().toUpperCase()));
  if (!used.has(preferred[shift.kind])) return preferred[shift.kind];
  const prefix = preferred[shift.kind][0];
  for (let index = 1; index <= 9; index += 1) if (!used.has(`${prefix}${index}`)) return `${prefix}${index}`;
  return "";
}

function scopeLabel(pattern: WorkPatternRead): string {
  const rule = pattern.applicability;
  if (!rule?.auto_assign) return pattern.assigned_employee_count ? `${pattern.assigned_employee_count} override${pattern.assigned_employee_count === 1 ? "" : "s"}` : "Manual";
  if (rule.position_ids.length) return `${rule.position_ids.length} role${rule.position_ids.length === 1 ? "" : "s"}`;
  if (rule.department_ids.length) return `${rule.department_ids.length} dept${rule.department_ids.length === 1 ? "" : "s"}`;
  if (rule.contract_types.length) return rule.contract_types.map((value) => value.replace(/_/g, " ")).join(", ");
  return "All eligible";
}

export function WorkPatternStudio({
  canManageShifts,
  canManagePatterns,
  busy,
  runAction,
  workforcePath,
  timezoneName,
}: {
  canManageShifts: boolean;
  canManagePatterns: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
  workforcePath: string;
  timezoneName: string;
}) {
  const shiftsQuery = useQuery({
    queryKey: ["rostering", "settings", "shifts"],
    queryFn: () => listShiftTemplates(true),
    staleTime: 15 * 60_000,
  });
  const registryQuery = useQuery({
    queryKey: ["rostering", "settings", "shift-registry"],
    queryFn: listRosterCodeRegistry,
    staleTime: 0,
    refetchOnMount: "always",
  });
  const patternsQuery = useQuery({
    queryKey: ["rostering", "settings", "patterns"],
    queryFn: () => listWorkPatterns(true),
    staleTime: 5 * 60_000,
  });
  const departmentsQuery = useQuery({
    queryKey: ["rostering", "settings", "pattern-departments"],
    queryFn: () => listSetupDepartments(false),
    staleTime: 15 * 60_000,
  });
  const positionsQuery = useQuery({
    queryKey: ["rostering", "settings", "pattern-positions"],
    queryFn: () => listWorkforceHrPositions(false),
    staleTime: 15 * 60_000,
  });

  const registryById = useMemo(
    () => new Map((registryQuery.data || []).map((entry) => [entry.id, entry])),
    [registryQuery.data],
  );

  return (
    <div className="rs-pattern-workspace">
      <ShiftLibrary
        shifts={shiftsQuery.data || []}
        registryById={registryById}
        departments={departmentsQuery.data || []}
        loading={shiftsQuery.isPending || registryQuery.isPending || departmentsQuery.isPending}
        error={shiftsQuery.error || registryQuery.error || departmentsQuery.error}
        canManage={canManageShifts}
        busy={busy}
        runAction={runAction}
        refreshRegistry={() => registryQuery.refetch()}
      />
      <PatternLibrary
        shifts={shiftsQuery.data || []}
        patterns={patternsQuery.data || []}
        departments={departmentsQuery.data || []}
        positions={positionsQuery.data || []}
        loading={shiftsQuery.isPending || patternsQuery.isPending}
        error={shiftsQuery.error || patternsQuery.error || departmentsQuery.error || positionsQuery.error}
        canManage={canManagePatterns}
        busy={busy}
        runAction={runAction}
        timezoneName={timezoneName}
      />
      <section className="wr-panel rs-pattern-ownership rs-pattern-ownership--compact">
        <div>
          <ShieldCheck size={17} />
          <span><strong>Person starting phase</strong><p>Use an override only when someone must start on a different cycle day.</p></span>
        </div>
        <Link className="wr-button wr-button--secondary wr-button--small" to={workforcePath}>Manage overrides <ArrowRight size={14} /></Link>
      </section>
    </div>
  );
}

function ShiftLibrary({ shifts, registryById, departments, loading, error, canManage, busy, runAction, refreshRegistry }: {
  shifts: ShiftTemplateRead[];
  registryById: Map<string, RosterCodeRegistryEntry>;
  departments: SetupDepartmentRead[];
  loading: boolean;
  error: unknown;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
  refreshRegistry: () => Promise<unknown>;
}) {
  const empty: ShiftDraft = { code: "", label: "", kind: "DAY", start: "08:00", end: "17:00", description: "", isActive: true, departmentIds: [] };
  const [editing, setEditing] = useState<ShiftTemplateRead | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ShiftDraft>(empty);
  const [mergeSource, setMergeSource] = useState<ShiftTemplateRead | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [mergeCode, setMergeCode] = useState("");
  const [mergePolicyResolution, setMergePolicyResolution] = useState<"" | "KEEP_SOURCE" | "KEEP_TARGET">("");
  const [refreshingMergePolicies, setRefreshingMergePolicies] = useState(false);
  const signatures = useMemo(() => {
    const counts = new Map<string, number>();
    shifts.forEach((shift) => counts.set(shiftSignature(shift), (counts.get(shiftSignature(shift)) || 0) + 1));
    return counts;
  }, [shifts]);

  const beginEdit = (shift: ShiftTemplateRead) => {
    setEditing(shift);
    setCreating(false);
    setDraft({
      code: shift.code,
      label: shift.label,
      kind: shift.kind,
      start: shift.default_start_time?.slice(0, 5) || "08:00",
      end: shift.default_end_time?.slice(0, 5) || "17:00",
      description: shift.description || "",
      isActive: shift.is_active,
      departmentIds: shift.department_ids || [],
    });
  };
  const beginCreate = () => { setEditing(null); setCreating(true); setDraft(empty); };
  const close = () => { setEditing(null); setCreating(false); };
  const normalCode = draft.code.trim().toUpperCase();
  const validCode = /^[A-Z0-9]{1,2}$/.test(normalCode);
  const duplicateCode = shifts.some((shift) => shift.id !== editing?.id && shift.code.trim().toUpperCase() === normalCode);
  const codeError = !normalCode
    ? "Enter a code"
    : !validCode
      ? "Replace legacy codes with 1–2 letters or numbers"
      : duplicateCode
        ? "That code is already in use"
        : null;

  const save = () => runAction("shift", async () => {
    const nonDuty = ["OFF", "LEAVE"].includes(draft.kind);
    const payload = {
      code: normalCode,
      label: draft.label.trim(),
      kind: draft.kind,
      default_start_time: nonDuty ? null : draft.start,
      default_end_time: nonDuty ? null : draft.end,
      duration_minutes: null,
      counts_as_duty: !nonDuty,
      is_active: draft.isActive,
      display_order: editing?.display_order ?? (shifts.length + 1) * 10,
      description: draft.description.trim() || null,
      color_token: editing?.color_token || `shift-${draft.kind.toLowerCase()}`,
      icon_name: editing?.icon_name || null,
      department_ids: draft.departmentIds,
    };
    if (editing) await updateShiftTemplate(editing.id, payload);
    else await createShiftTemplate(payload);
    close();
  });

  const toggleActive = async (shift: ShiftTemplateRead) => {
    const action = shift.is_active ? "Retire" : "Restore";
    if (!window.confirm(`${action} ${shift.code}? Existing roster history remains unchanged.`)) return;
    await runAction(`shift-${shift.id}`, () => updateShiftTemplate(shift.id, { is_active: !shift.is_active }));
  };

  const remove = async (shift: ShiftTemplateRead) => {
    if (!window.confirm(`Delete unused shift ${shift.code}? This cannot be undone.`)) return;
    await runAction(`shift-${shift.id}`, () => deleteUnusedRosterCode(shift.id));
    if (editing?.id === shift.id) close();
  };

  const mergeTargets = useMemo(() => {
    if (!mergeSource) return [];
    return shifts
      .filter((shift) => shift.id !== mergeSource.id && shift.is_active && shiftSignature(shift) === shiftSignature(mergeSource))
      .sort((left, right) => {
        const leftValid = /^[A-Z0-9]{1,2}$/.test(left.code) ? 0 : 1;
        const rightValid = /^[A-Z0-9]{1,2}$/.test(right.code) ? 0 : 1;
        return leftValid - rightValid
          || (registryById.get(right.id)?.usage_count || 0) - (registryById.get(left.id)?.usage_count || 0)
          || left.code.localeCompare(right.code);
      });
  }, [mergeSource, registryById, shifts]);
  const beginMerge = (shift: ShiftTemplateRead) => {
    const candidates = shifts
      .filter((item) => item.id !== shift.id && item.is_active && shiftSignature(item) === shiftSignature(shift))
      .sort((left, right) => {
        const leftValid = /^[A-Z0-9]{1,2}$/.test(left.code) ? 0 : 1;
        const rightValid = /^[A-Z0-9]{1,2}$/.test(right.code) ? 0 : 1;
        return leftValid - rightValid
          || (registryById.get(right.id)?.usage_count || 0) - (registryById.get(left.id)?.usage_count || 0)
          || left.code.localeCompare(right.code);
      });
    setMergeSource(shift);
    setMergeTargetId(candidates[0]?.id || "");
    setMergeCode(candidates[0] ? compactShiftCode(candidates[0], shifts) : "");
    setMergePolicyResolution("");
    setRefreshingMergePolicies(true);
    void refreshRegistry().finally(() => setRefreshingMergePolicies(false));
  };
  const merge = () => {
    if (!mergeSource || !mergeTargetId) return Promise.resolve();
    const target = shifts.find((shift) => shift.id === mergeTargetId);
    const canonicalCode = mergeCode.trim().toUpperCase();
    if (!mergePolicyResolution) return Promise.resolve();
    const resolution: "KEEP_SOURCE" | "KEEP_TARGET" = mergePolicyResolution;
    const keptPolicyLabel = resolution === "KEEP_SOURCE" ? mergeSource.code : canonicalCode;
    const policyNote = `\n\nPolicy: use ${keptPolicyLabel}'s complete policy; remove the other policy after migration.`;
    if (!target || !/^[A-Z0-9]{1,2}$/.test(canonicalCode) || !window.confirm(`Merge ${mergeSource.code} into ${canonicalCode}? Patterns, roster rows and rules will be moved to ${canonicalCode}; ${mergeSource.code} will be removed.${policyNote}`)) return Promise.resolve();
    return runAction(`merge-shift-${mergeSource.id}`, async () => {
      await mergeDuplicateRosterCode(
        mergeSource.id,
        target.id,
        canonicalCode,
        "Consolidated duplicate shift code from roster setup",
        resolution,
      );
      await refreshRegistry();
      setMergeSource(null);
      setMergeTargetId("");
      setMergeCode("");
      setMergePolicyResolution("");
    });
  };
  const departmentById = useMemo(() => new Map(departments.map((row) => [row.id, row])), [departments]);
  const shiftScope = (shift: ShiftTemplateRead) => {
    const ids = shift.department_ids || [];
    if (!ids.length) return "All departments";
    if (ids.length === 1) return departmentById.get(ids[0])?.code || "1 department";
    return `${ids.length} departments`;
  };
  const duplicateCount = [...signatures.values()].filter((count) => count > 1).length;
  const mergeTarget = shifts.find((shift) => shift.id === mergeTargetId);
  const mergeSourcePolicy = mergeSource ? registryById.get(mergeSource.id)?.policy : null;
  const mergeTargetPolicy = mergeTargetId ? registryById.get(mergeTargetId)?.policy : null;
  const mergePolicyReady = Boolean(mergeSourcePolicy && mergeTargetPolicy);
  const mergePolicyDifferences = mergeSourcePolicy && mergeTargetPolicy
    ? [
        mergeSourcePolicy.calendar_mode !== mergeTargetPolicy.calendar_mode ? "calendar" : null,
        mergeSourcePolicy.duty_semantic !== mergeTargetPolicy.duty_semantic ? "duty meaning" : null,
        mergeSourcePolicy.unpaid_break_minutes !== mergeTargetPolicy.unpaid_break_minutes ? "unpaid break" : null,
        mergeSourcePolicy.verification_status !== mergeTargetPolicy.verification_status ? "verification" : null,
        mergeSourcePolicy.effective_from !== mergeTargetPolicy.effective_from || mergeSourcePolicy.effective_to !== mergeTargetPolicy.effective_to ? "effective dates" : null,
        mergeSourcePolicy.source_reference !== mergeTargetPolicy.source_reference ? "source reference" : null,
      ].filter(Boolean)
    : [];
  const policySummary = (policy: RosterCodeRegistryEntry["policy"] | null | undefined) => policy
    ? [
        `${policy.calendar_mode.toLowerCase()} · ${policy.duty_semantic.toLowerCase()} · ${policy.unpaid_break_minutes} min break`,
        policy.verification_status.toLowerCase().replace(/_/g, " "),
        policy.effective_from || policy.effective_to ? `${policy.effective_from || "open"} → ${policy.effective_to || "open"}` : "no date limit",
        policy.source_reference || "no source reference",
      ].join(" · ")
    : "No stored policy";

  return (
    <section className="wr-panel rs-setup-compact-panel rs-shift-library">
      <div className="rs-compact-heading">
        <div><span className="wr-eyebrow">1 · Shift legend</span><h2>Codes</h2></div>
        {canManage ? <button type="button" className="wr-button wr-button--primary wr-button--small" onClick={beginCreate}><Plus size={14} /> Add code</button> : null}
      </div>
      {error ? <div className="wr-inline-error" role="alert">{errorMessage(error)}</div> : null}
      {loading ? <RosterLoading label="Loading shift codes…" /> : null}
      {!loading && duplicateCount ? <div className="wr-inline-warning rs-duplicate-summary"><GitMerge size={15} /> Duplicate hours detected. Merge the obsolete code into the canonical code; assigned rotations are preserved.</div> : null}

      {creating || editing ? (
        <form className="rs-shift-inline-editor" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <label><span>Code</span><input autoFocus maxLength={editing && editing.code.length > 2 ? undefined : 2} value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value.replace(/[^a-z0-9]/gi, "").toUpperCase() })} /></label>
          <label><span>Name</span><input value={draft.label} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></label>
          <label><span>Type</span><select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as ShiftTemplateKind })}>{SHIFT_KINDS.map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select></label>
          <label><span>Start</span><input type="time" value={draft.start} disabled={["OFF", "LEAVE"].includes(draft.kind)} onChange={(event) => setDraft({ ...draft, start: event.target.value })} /></label>
          <label><span>End</span><input type="time" value={draft.end} disabled={["OFF", "LEAVE"].includes(draft.kind)} onChange={(event) => setDraft({ ...draft, end: event.target.value })} /></label>
          <label className="rs-shift-inline-editor__active"><input type="checkbox" checked={draft.isActive} onChange={(event) => setDraft({ ...draft, isActive: event.target.checked })} /><span>Active</span></label>
          <div className="rs-row-actions"><button type="submit" className="wr-icon-button is-primary" aria-label="Save shift code" title="Save" disabled={Boolean(busy) || Boolean(codeError) || !draft.label.trim()}><Save size={15} /></button><button type="button" className="wr-icon-button" aria-label="Cancel shift edit" title="Cancel" onClick={close}><X size={15} /></button></div>
          {codeError ? <span className="rs-field-error">{codeError}</span> : null}
          <fieldset className="rs-shift-department-scope"><legend>Available to</legend><div className="rs-rule-options"><button type="button" className={!draft.departmentIds.length ? "is-selected" : ""} onClick={() => setDraft({ ...draft, departmentIds: [] })}>All</button>{departments.map((department) => <button key={department.id} type="button" className={draft.departmentIds.includes(department.id) ? "is-selected" : ""} onClick={() => setDraft({ ...draft, departmentIds: draft.departmentIds.includes(department.id) ? draft.departmentIds.filter((id) => id !== department.id) : [...draft.departmentIds, department.id] })}>{department.code}</button>)}</div></fieldset>
        </form>
      ) : null}

      {mergeSource ? (
        <div className="rs-shift-merge" role="region" aria-label={`Merge duplicate ${mergeSource.code}`}>
          <GitMerge size={16} />
          <div>
            <span className="rs-shift-merge__step">Review then merge</span>
            <strong>Replace {mergeSource.code} with {mergeTarget?.code || "the kept shift"}</strong>
            <small>{registryById.get(mergeSource.id)?.usage_count || 0} linked records and rotations will move safely.</small>
            {refreshingMergePolicies ? <small className="is-warning">Loading current policies…</small> : mergePolicyDifferences.length ? <small className="is-warning">Choose how to resolve: {mergePolicyDifferences.join(", ")}.</small> : <small>Review both policies and choose the final one.</small>}
          </div>
          <label><span>Keep shift</span><select value={mergeTargetId} onChange={(event) => { const target = shifts.find((shift) => shift.id === event.target.value); setMergeTargetId(event.target.value); setMergeCode(target ? compactShiftCode(target, shifts) : ""); setMergePolicyResolution(""); }}>{mergeTargets.map((target) => <option key={target.id} value={target.id}>{target.code} · {target.label}</option>)}</select></label>
          <label className="rs-shift-merge__code"><span>Final code</span><input maxLength={2} value={mergeCode} onChange={(event) => setMergeCode(event.target.value.replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase())} /></label>
          <fieldset className="rs-shift-policy-choice">
            <legend>{mergePolicyDifferences.length ? "Resolve conflicting policy" : "Review final policy"}</legend>
            <p>Select the complete policy that the final <strong>{mergeCode || mergeTarget?.code}</strong> code should use. The unselected policy is removed after linked records move.</p>
            <label><input type="radio" name="merge-policy" checked={mergePolicyResolution === "KEEP_SOURCE"} onChange={() => setMergePolicyResolution("KEEP_SOURCE")} /><span><strong>Move {mergeSource.code} policy to {mergeCode || mergeTarget?.code}</strong><small>{policySummary(mergeSourcePolicy)}</small></span></label>
            <label><input type="radio" name="merge-policy" checked={mergePolicyResolution === "KEEP_TARGET"} onChange={() => setMergePolicyResolution("KEEP_TARGET")} /><span><strong>Keep {mergeTarget?.code || "target"} policy</strong><small>{policySummary(mergeTargetPolicy)}</small></span></label>
          </fieldset>
          <button type="button" className="wr-button wr-button--primary wr-button--small" disabled={refreshingMergePolicies || !mergePolicyReady || !mergeTargetId || !/^[A-Z0-9]{1,2}$/.test(mergeCode) || shifts.some((shift) => shift.id !== mergeTargetId && shift.code.trim().toUpperCase() === mergeCode) || Boolean(busy) || !mergePolicyResolution} onClick={() => void merge()}>{refreshingMergePolicies ? "Loading policy…" : !mergePolicyResolution ? "Choose policy" : `Merge into ${mergeCode}`}</button>
          <button type="button" className="wr-icon-button" aria-label="Cancel merge" onClick={() => { setMergeSource(null); setMergePolicyResolution(""); }}><X size={15} /></button>
        </div>
      ) : null}

      <div className="rs-shift-compact-list">
        <div className="rs-shift-compact-list__head"><span>Code</span><span>Shift</span><span>Hours</span><span>Scope</span><span>State</span><span aria-label="Actions" /></div>
        {shifts.map((shift) => {
          const registry = registryById.get(shift.id);
          const duplicate = (signatures.get(shiftSignature(shift)) || 0) > 1;
          const canonical = shifts
            .filter((item) => item.is_active && shiftSignature(item) === shiftSignature(shift))
            .sort((left, right) => {
              const leftValid = /^[A-Z0-9]{1,2}$/.test(left.code) ? 0 : 1;
              const rightValid = /^[A-Z0-9]{1,2}$/.test(right.code) ? 0 : 1;
              return leftValid - rightValid
                || (registryById.get(right.id)?.usage_count || 0) - (registryById.get(left.id)?.usage_count || 0)
                || left.code.localeCompare(right.code);
            })[0];
          const mergeable = Boolean(duplicate && canonical && canonical.id !== shift.id);
          const invalidLegacyCode = !/^[A-Z0-9]{1,2}$/.test(shift.code.trim().toUpperCase());
          return (
            <article key={shift.id} className={!shift.is_active ? "is-inactive" : mergeable ? "has-warning" : ""}>
              <span className={`rs-shift-code is-${shift.kind.toLowerCase()}`}>{shift.code}</span>
              <div><strong>{shift.label}</strong>{invalidLegacyCode ? <small className="is-danger">Merge into {canonical?.code || "a canonical code"}</small> : mergeable ? <small className="is-warning">Same type and hours as another code ({canonical?.code})</small> : duplicate ? <small>Canonical code · merge duplicates here</small> : <small>{shift.kind}</small>}</div>
              <span className="rs-shift-hours">{["OFF", "LEAVE"].includes(shift.kind) ? "—" : `${shift.default_start_time?.slice(0, 5) || "Flex"}–${shift.default_end_time?.slice(0, 5) || "Flex"}`}</span>
              <span className="rs-shift-scope">{shiftScope(shift)}</span>
              <StatusPill value={mergeable ? "DUPLICATE" : shift.is_active ? "ACTIVE" : "RETIRED"} tone={mergeable ? "warning" : shift.is_active ? "success" : "neutral"} />
              {canManage ? <div className="rs-row-actions">
                <button type="button" className="wr-icon-button" aria-label={`Edit ${shift.code}`} title="Edit" onClick={() => beginEdit(shift)}><PenLine size={14} /></button>
                {mergeable ? <button type="button" className="wr-icon-button" aria-label={`Merge duplicate ${shift.code}`} title={`Merge into ${canonical?.code}`} onClick={() => beginMerge(shift)}><GitMerge size={14} /></button> : null}
                <button type="button" className="wr-icon-button" aria-label={`${shift.is_active ? "Retire" : "Restore"} ${shift.code}`} title={shift.is_active ? "Retire" : "Restore"} onClick={() => void toggleActive(shift)}><Power size={14} /></button>
                <button type="button" className="wr-icon-button wr-icon-button--danger" aria-label={`Delete ${shift.code}`} title={registry?.can_delete ? "Delete unused code" : `${registry?.usage_count || 0} records use this code; retire it instead`} disabled={!registry?.can_delete || Boolean(busy)} onClick={() => void remove(shift)}><Trash2 size={14} /></button>
              </div> : null}
            </article>
          );
        })}
      </div>
      {!loading && !shifts.length ? <EmptyState title="No shift codes" description="Add the real codes used by your organization." /> : null}
    </section>
  );
}

function PatternLibrary({ shifts, patterns, departments, positions, loading, error, canManage, busy, runAction, timezoneName }: {
  shifts: ShiftTemplateRead[];
  patterns: WorkPatternRead[];
  departments: SetupDepartmentRead[];
  positions: HrPosition[];
  loading: boolean;
  error: unknown;
  canManage: boolean;
  busy: string | null;
  runAction: (key: string, action: () => Promise<unknown>) => Promise<void>;
  timezoneName: string;
}) {
  const usableShifts = useMemo(
    () => shifts
      .filter((shift) => shift.is_active && !["TRAINING", "LEAVE", "OFF"].includes(shift.kind) && /^[A-Z0-9]{1,2}$/.test(shift.code))
      .sort((left, right) => Number(Boolean(left.department_ids?.length)) - Number(Boolean(right.department_ids?.length)) || left.code.localeCompare(right.code)),
    [shifts],
  );
  const [building, setBuilding] = useState(false);
  const [editing, setEditing] = useState<WorkPatternRead | null>(null);
  const [recipe, setRecipe] = useState<PatternRecipe>("STANDARD_WEEK");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [active, setActive] = useState(true);
  const [cycleLength, setCycleLength] = useState(7);
  const [dayShifts, setDayShifts] = useState<Array<string | null>>([]);
  const [autoAssign, setAutoAssign] = useState(false);
  const [departmentIds, setDepartmentIds] = useState<string[]>([]);
  const [positionIds, setPositionIds] = useState<string[]>([]);
  const [contractTypes, setContractTypes] = useState<ContractType[]>([]);
  const [anchorDate, setAnchorDate] = useState(suggestedAnchor("STANDARD_WEEK"));

  const toggle = <T extends string,>(values: T[], value: T, setter: (next: T[]) => void) => setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  const resize = (length: number) => {
    setCycleLength(length);
    setDayShifts((current) => {
      const next = [...current];
      while (next.length < length) next.push(null);
      return next.slice(0, length);
    });
  };
  const applyRecipe = (nextRecipe: PatternRecipe) => {
    const definition = RECIPES.find((item) => item.id === nextRecipe) || RECIPES[0];
    setRecipe(nextRecipe);
    setCycleLength(definition.cycle);
    setDayShifts(recipeDays(nextRecipe, usableShifts));
    setAnchorDate(suggestedAnchor(nextRecipe));
    if (!editing) {
      setCode(uniqueCode(definition.code, patterns));
      setName(definition.name);
    }
  };
  const beginCreate = () => {
    setEditing(null);
    setBuilding(true);
    setDescription("");
    setActive(true);
    setAutoAssign(false);
    setDepartmentIds([]);
    setPositionIds([]);
    setContractTypes([]);
    const definition = RECIPES[0];
    setRecipe(definition.id);
    setCycleLength(definition.cycle);
    setDayShifts(recipeDays(definition.id, usableShifts));
    setCode(uniqueCode(definition.code, patterns));
    setName(definition.name);
    setAnchorDate(suggestedAnchor(definition.id));
  };
  const beginEdit = (pattern: WorkPatternRead) => {
    const next = Array.from({ length: pattern.cycle_length_days }, () => null as string | null);
    pattern.days.forEach((day) => { next[day.cycle_day_index] = day.shift_template_id || null; });
    setEditing(pattern);
    setBuilding(true);
    setRecipe("CUSTOM");
    setCode(pattern.code);
    setName(pattern.name);
    setDescription(pattern.description || "");
    setActive(pattern.is_active);
    setAutoAssign(pattern.applicability?.auto_assign || false);
    setDepartmentIds(pattern.applicability?.department_ids || []);
    setPositionIds(pattern.applicability?.position_ids || []);
    setContractTypes(pattern.applicability?.contract_types || []);
    setAnchorDate(pattern.applicability?.anchor_date || suggestedAnchor("CUSTOM"));
    setCycleLength(pattern.cycle_length_days);
    setDayShifts(next);
  };
  const close = () => { setBuilding(false); setEditing(null); };

  const days: WorkPatternDayInput[] = dayShifts.map((shiftId, index) => {
    const shift = usableShifts.find((item) => item.id === shiftId);
    const status: PatternDayStatus = !shift ? "OFF" : shift.kind === "STANDBY" ? "STANDBY" : "DUTY";
    const spans = Boolean(shift?.default_start_time && shift?.default_end_time && shift.default_end_time <= shift.default_start_time);
    return {
      cycle_day_index: index,
      shift_template_id: shift?.id || null,
      status,
      start_time_local: shift?.default_start_time || null,
      end_time_local: shift?.default_end_time || null,
      spans_next_day: spans,
      planned_minutes: shift?.duration_minutes || 0,
    };
  });
  const duplicateCode = patterns.some((pattern) => pattern.id !== editing?.id && pattern.code.trim().toUpperCase() === code.trim().toUpperCase());
  const shiftFitsRotationScope = (shift: ShiftTemplateRead) => {
    const scope = shift.department_ids || [];
    if (!autoAssign || !scope.length) return true;
    return Boolean(departmentIds.length && departmentIds.every((id) => scope.includes(id)));
  };
  const incompatibleShift = dayShifts
    .map((shiftId) => usableShifts.find((shift) => shift.id === shiftId))
    .find((shift): shift is ShiftTemplateRead => Boolean(shift && !shiftFitsRotationScope(shift)));
  const save = () => runAction("pattern", async () => {
    const payload = {
      code: code.trim().toUpperCase(),
      name: name.trim(),
      description: description.trim() || null,
      cycle_length_days: cycleLength,
      is_active: active,
      timezone_name: timezoneName,
      applicability: {
        auto_assign: autoAssign,
        department_ids: departmentIds,
        position_ids: positionIds,
        contract_types: contractTypes,
        anchor_date: autoAssign ? anchorDate : null,
        priority: 100,
      },
      days,
    };
    if (editing) await updateWorkPattern(editing.id, payload);
    else await createWorkPattern(payload);
    close();
  });
  const toggleActive = async (pattern: WorkPatternRead) => {
    const action = pattern.is_active ? "Retire" : "Restore";
    if (!window.confirm(`${action} ${pattern.code}? Existing roster history remains unchanged.`)) return;
    await runAction(`pattern-${pattern.id}`, () => updateWorkPattern(pattern.id, { is_active: !pattern.is_active }));
  };
  const remove = async (pattern: WorkPatternRead) => {
    if (!window.confirm(`Delete unused rotation ${pattern.code}? Used rotations must be retired instead.`)) return;
    await runAction(`pattern-${pattern.id}`, () => deleteWorkPattern(pattern.id, "Removed unused rotation from roster setup"));
    if (editing?.id === pattern.id) close();
  };
  const matrixDays = Math.min(14, Math.max(7, ...patterns.map((pattern) => pattern.cycle_length_days), cycleLength));

  return (
    <section className="wr-panel rs-setup-compact-panel rs-pattern-studio">
      <div className="rs-compact-heading">
        <div><span className="wr-eyebrow">2 · Repeating order</span><h2>Rotations</h2></div>
        {canManage ? <button type="button" className="wr-button wr-button--primary wr-button--small" disabled={!usableShifts.length} onClick={beginCreate}><Plus size={14} /> Add rotation</button> : null}
      </div>
      {error ? <div className="wr-inline-error" role="alert">{errorMessage(error)}</div> : null}
      {loading ? <RosterLoading label="Loading rotations…" /> : null}
      {!loading && !usableShifts.length ? <div className="wr-inline-warning"><Clock3 size={15} /> Add or repair at least one 1–2 character duty code.</div> : null}

      <div className="rs-rotation-matrix-wrap">
        <table className="rs-rotation-matrix">
          <thead><tr><th>Rotation</th>{Array.from({ length: matrixDays }, (_, index) => <th key={index}>D{index + 1}</th>)}<th>Applies</th><th aria-label="Actions" /></tr></thead>
          <tbody>{patterns.map((pattern) => (
            <tr key={pattern.id} className={!pattern.is_active ? "is-inactive" : ""}>
              <th><strong>{pattern.code}</strong><small>{pattern.name}</small></th>
              {Array.from({ length: matrixDays }, (_, index) => {
                const day = pattern.days.find((item) => item.cycle_day_index === index);
                return <td key={index}><span className={`rs-rotation-code is-${(day?.status || "off").toLowerCase()}`}>{index < pattern.cycle_length_days ? day?.shift_code || "O" : "·"}</span></td>;
              })}
              <td><span className="rs-scope-pill">{scopeLabel(pattern)}</span></td>
              <td>{canManage ? <div className="rs-row-actions">
                <button type="button" className="wr-icon-button" aria-label={`Edit ${pattern.code}`} title="Edit" onClick={() => beginEdit(pattern)}><PenLine size={14} /></button>
                <button type="button" className="wr-icon-button" aria-label={`${pattern.is_active ? "Retire" : "Restore"} ${pattern.code}`} title={pattern.is_active ? "Retire" : "Restore"} onClick={() => void toggleActive(pattern)}><Power size={14} /></button>
                <button type="button" className="wr-icon-button wr-icon-button--danger" aria-label={`Delete ${pattern.code}`} title="Delete if unused" disabled={Boolean(busy)} onClick={() => void remove(pattern)}><Trash2 size={14} /></button>
              </div> : null}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {!loading && !patterns.length ? <EmptyState title="No rotations" description="Choose a preset, then adjust only the days that differ." /> : null}

      {building ? (
        <div className="rs-drawer rs-drawer--wide rs-rotation-editor" role="dialog" aria-modal="true" aria-label={editing ? `Edit ${editing.name}` : "Create rotation"}>
          <div className="rs-drawer__head"><div><span className="wr-eyebrow">Rotation editor</span><h3>{editing ? editing.name : "New rotation"}</h3></div><button type="button" className="wr-icon-button" aria-label="Close rotation editor" onClick={close}><X size={16} /></button></div>
          <div className="rs-rotation-editor__fields">
            <label><span>Preset</span><select value={recipe} onChange={(event) => applyRecipe(event.target.value as PatternRecipe)}>{RECIPES.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <label><span>Code</span><input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></label>
            <label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label><span>Cycle days</span><input type="number" min="1" max="56" value={cycleLength} onChange={(event) => resize(Math.min(56, Math.max(1, Number(event.target.value))))} /></label>
          </div>
          {duplicateCode ? <div className="rs-field-error">That rotation code is already in use.</div> : null}

          <div className="rs-sequence-grid" aria-label="Repeating shift order">
            {dayShifts.map((shiftId, index) => <label key={index}><span>Day {index + 1}</span><select value={shiftId || OFF} onChange={(event) => setDayShifts((current) => current.map((value, dayIndex) => dayIndex === index ? (event.target.value === OFF ? null : event.target.value) : value))}><option value={OFF}>O · Off</option>{usableShifts.map((shift) => <option key={shift.id} value={shift.id} disabled={!shiftFitsRotationScope(shift)}>{shift.code} · {shift.label}{shift.department_ids?.length ? " · scoped" : ""}</option>)}</select></label>)}
          </div>
          {incompatibleShift ? <div className="wr-inline-warning"><Clock3 size={14} /> {incompatibleShift.code} is not available to every department selected for this automatic rotation.</div> : null}

          <details className="rs-rotation-advanced" open={autoAssign}>
            <summary><span><strong>Automatic assignment</strong><small>{autoAssign ? "On" : "Off"}</small></span></summary>
            <div>
              <label className="rs-rule-switch"><input type="checkbox" checked={autoAssign} onChange={(event) => setAutoAssign(event.target.checked)} /><span><strong>Apply automatically</strong><small>Person overrides still win.</small></span></label>
              {autoAssign ? <>
                <label className="rs-anchor-field"><span>Cycle day 1</span><input type="date" value={anchorDate} onChange={(event) => setAnchorDate(event.target.value)} /></label>
                <fieldset><legend>Departments</legend><div className="rs-rule-options">{departments.map((department) => <button key={department.id} type="button" className={departmentIds.includes(department.id) ? "is-selected" : ""} onClick={() => toggle(departmentIds, department.id, setDepartmentIds)}>{department.code}</button>)}</div></fieldset>
                <fieldset><legend>Roles</legend><div className="rs-rule-options">{positions.map((position) => <button key={position.id} type="button" className={positionIds.includes(position.id) ? "is-selected" : ""} onClick={() => toggle(positionIds, position.id, setPositionIds)}>{position.code}</button>)}</div></fieldset>
                <fieldset><legend>Contracts</legend><div className="rs-rule-options">{CONTRACT_TYPES.map((contractType) => <button key={contractType} type="button" className={contractTypes.includes(contractType) ? "is-selected" : ""} onClick={() => toggle(contractTypes, contractType, setContractTypes)}>{contractType.replace(/_/g, " ")}</button>)}</div></fieldset>
              </> : null}
            </div>
          </details>

          <div className="rs-rotation-editor__footer">
            <label><span>Note <small>optional</small></span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label>
            <label className="rs-toggle-row"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /><span>Active</span></label>
            <div className="wr-actions wr-actions--end">
              {editing ? <button type="button" className="wr-button wr-button--danger" disabled={Boolean(busy)} onClick={() => void remove(editing)}><Trash2 size={14} /> Delete</button> : null}
              <button type="button" className="wr-button wr-button--secondary" onClick={close}>Cancel</button>
              <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || duplicateCode || Boolean(incompatibleShift) || !code.trim() || !name.trim() || !dayShifts.some(Boolean)} onClick={() => void save()}><Save size={15} /> Save</button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
