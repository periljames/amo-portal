import "./roster-rule-control.css";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Save, ShieldCheck, X } from "lucide-react";

import {
  createRosterRule,
  listRosterRules,
  updateRosterRule,
} from "../../../services/rostering";
import type { RosterRuleRead, RosterRuleType } from "../../../types/rostering";
import { errorMessage } from "../rosterUi";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";

type NumericParameter = {
  key: string;
  label: string;
  divisor: number;
  suffix: string;
};

const NUMERIC_PARAMETERS: NumericParameter[] = [
  { key: "minimum_minutes", label: "Minimum hours", divisor: 60, suffix: "h" },
  { key: "maximum_minutes", label: "Maximum hours", divisor: 60, suffix: "h" },
  { key: "minimum_continuous_minutes", label: "Continuous rest", divisor: 60, suffix: "h" },
  { key: "maximum_days", label: "Maximum days", divisor: 1, suffix: "days" },
  { key: "maximum_nights", label: "Maximum nights", divisor: 1, suffix: "nights" },
];

const NEW_RULE_TYPES: Array<{
  value: RosterRuleType;
  label: string;
  parameter: string;
  unit: "hours" | "days" | "nights";
  defaultValue: string;
  rolling?: boolean;
}> = [
  { value: "MIN_REST_HOURS", label: "Minimum rest", parameter: "minimum_minutes", unit: "hours", defaultValue: "11" },
  { value: "MAX_ASSIGNMENT_DURATION", label: "Maximum shift duration", parameter: "maximum_minutes", unit: "hours", defaultValue: "12" },
  { value: "MAX_DUTY_HOURS_DAY", label: "Maximum duty per day", parameter: "maximum_minutes", unit: "hours", defaultValue: "12" },
  { value: "MAX_DUTY_HOURS_ROLLING", label: "Maximum duty in rolling window", parameter: "maximum_minutes", unit: "hours", defaultValue: "60", rolling: true },
  { value: "MAX_CONSECUTIVE_DAYS", label: "Maximum consecutive duty days", parameter: "maximum_days", unit: "days", defaultValue: "6" },
  { value: "MAX_CONSECUTIVE_NIGHTS", label: "Maximum consecutive nights", parameter: "maximum_nights", unit: "nights", defaultValue: "4" },
];

function parameterFor(rule: RosterRuleRead): NumericParameter | null {
  return NUMERIC_PARAMETERS.find((parameter) => typeof rule.parameters_json?.[parameter.key] === "number") || null;
}

function compactValue(rule: RosterRuleRead): string {
  const parameter = parameterFor(rule);
  if (!parameter) return "Policy check";
  const raw = Number(rule.parameters_json[parameter.key]);
  const value = raw / parameter.divisor;
  const window = typeof rule.parameters_json.window_days === "number"
    ? ` / ${rule.parameters_json.window_days}d`
    : "";
  return `${value}${parameter.suffix}${window}`;
}

export function RosterRuleQuickEditor() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<RosterRuleRead | null>(null);
  const [creating, setCreating] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newType, setNewType] = useState<RosterRuleType>("MIN_REST_HOURS");
  const [newValue, setNewValue] = useState("11");
  const [newWindowDays, setNewWindowDays] = useState("7");
  const [newSeverity, setNewSeverity] = useState<RosterRuleRead["severity"]>("BLOCKER");
  const [newAllowOverride, setNewAllowOverride] = useState(false);
  const [name, setName] = useState("");
  const [severity, setSeverity] = useState<RosterRuleRead["severity"]>("WARNING");
  const [allowOverride, setAllowOverride] = useState(true);
  const [isActive, setIsActive] = useState(true);
  const [numericValue, setNumericValue] = useState("");
  const [windowDays, setWindowDays] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const permissionsQuery = useWorkforcePermissions();
  const canManage = (permissionsQuery.data?.permissions || []).includes("roster.manage_rules");
  const rulesQuery = useQuery({
    queryKey: ["rostering", "settings", "rules"],
    queryFn: () => listRosterRules(true),
    enabled: canManage,
    staleTime: 15 * 60_000,
    networkMode: "offlineFirst",
  });

  const rules = useMemo(
    () => [...(rulesQuery.data || [])].sort((left, right) => left.display_order - right.display_order || left.name.localeCompare(right.name)),
    [rulesQuery.data],
  );
  const activeCount = rules.filter((rule) => rule.is_active).length;
  const parameter = editing ? parameterFor(editing) : null;

  const beginEdit = (rule: RosterRuleRead) => {
    const numericParameter = parameterFor(rule);
    setEditing(rule);
    setName(rule.name);
    setSeverity(rule.severity);
    setAllowOverride(rule.allow_override);
    setIsActive(rule.is_active);
    setNumericValue(numericParameter ? String(Number(rule.parameters_json[numericParameter.key]) / numericParameter.divisor) : "");
    setWindowDays(typeof rule.parameters_json.window_days === "number" ? String(rule.parameters_json.window_days) : "");
    setError(null);
  };

  const close = () => {
    setEditing(null);
    setError(null);
  };

  const closeCreate = () => {
    setCreating(false);
    setError(null);
  };

  const selectNewType = (value: RosterRuleType) => {
    const definition = NEW_RULE_TYPES.find((row) => row.value === value) || NEW_RULE_TYPES[0];
    setNewType(value);
    setNewValue(definition.defaultValue);
  };

  const create = async () => {
    const definition = NEW_RULE_TYPES.find((row) => row.value === newType) || NEW_RULE_TYPES[0];
    const threshold = Number(newValue);
    const windowDaysValue = Number(newWindowDays);
    if (!newCode.trim() || !newName.trim()) {
      setError("Rule code and name are required.");
      return;
    }
    if (!Number.isFinite(threshold) || threshold <= 0) {
      setError("The rule threshold must be greater than zero.");
      return;
    }
    if (definition.rolling && (!Number.isFinite(windowDaysValue) || windowDaysValue <= 0)) {
      setError("Rolling window days must be greater than zero.");
      return;
    }
    const normalizedThreshold = definition.unit === "hours" ? Math.round(threshold * 60) : Math.round(threshold);
    setBusy(true);
    setError(null);
    try {
      await createRosterRule({
        rule_set_id: null,
        code: newCode.trim().toUpperCase(),
        name: newName.trim(),
        description: newDescription.trim() || null,
        rule_type: newType,
        scope: "AMO",
        severity: newSeverity,
        parameters_json: {
          [definition.parameter]: normalizedThreshold,
          ...(definition.rolling ? { window_days: Math.round(windowDaysValue) } : {}),
        },
        department_id: null,
        base_station_id: null,
        shift_template_id: null,
        user_id: null,
        effective_from: null,
        effective_to: null,
        allow_override: newAllowOverride,
        is_active: true,
        display_order: rules.length * 10 + 10,
      });
      setCreating(false);
      setNewCode("");
      setNewName("");
      setNewDescription("");
      await queryClient.invalidateQueries({ queryKey: ["rostering"] });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!editing || !name.trim()) return;
    const parameters = { ...(editing.parameters_json || {}) };
    if (parameter) {
      const value = Number(numericValue);
      if (!Number.isFinite(value) || value < 0) {
        setError(`${parameter.label} must be a valid non-negative number.`);
        return;
      }
      parameters[parameter.key] = Math.round(value * parameter.divisor);
    }
    if (Object.prototype.hasOwnProperty.call(parameters, "window_days")) {
      const value = Number(windowDays);
      if (!Number.isFinite(value) || value <= 0) {
        setError("Rolling window days must be greater than zero.");
        return;
      }
      parameters.window_days = Math.round(value);
    }

    setBusy(true);
    setError(null);
    try {
      await updateRosterRule(editing.id, {
        name: name.trim(),
        severity,
        allow_override: allowOverride,
        is_active: isActive,
        parameters_json: parameters,
      });
      close();
      await queryClient.invalidateQueries({ queryKey: ["rostering"] });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  if (!canManage) return null;

  return (
    <details className="wr-panel wr-rule-control">
      <summary>
        <span><ShieldCheck size={17} /><strong>Rule controls</strong></span>
        <small>{activeCount} active</small>
      </summary>

      {rulesQuery.error ? <div className="wr-inline-error" role="alert">{errorMessage(rulesQuery.error)}</div> : null}
      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}

      <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--primary" onClick={() => { setCreating(true); setEditing(null); setError(null); }}><Plus size={15} /> New rule</button></div>

      {creating ? (
        <div className="wr-rule-control__editor">
          <div className="wr-rule-control__editor-head"><div><span className="wr-eyebrow">Structured policy control</span><strong>Create compliance rule</strong></div><button type="button" className="wr-icon-button" aria-label="Close new rule form" onClick={closeCreate}><X size={16} /></button></div>
          <div className="wr-rule-control__fields">
            <label><span>Code</span><input value={newCode} onChange={(event) => setNewCode(event.target.value.toUpperCase())} placeholder="MIN-REST" /></label>
            <label><span>Name</span><input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Minimum rest between duties" /></label>
            <label><span>Rule type</span><select value={newType} onChange={(event) => selectNewType(event.target.value as RosterRuleType)}>{NEW_RULE_TYPES.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}</select></label>
            <label><span>Threshold ({(NEW_RULE_TYPES.find((row) => row.value === newType) || NEW_RULE_TYPES[0]).unit})</span><input type="number" min="0.25" step="0.25" value={newValue} onChange={(event) => setNewValue(event.target.value)} /></label>
            {(NEW_RULE_TYPES.find((row) => row.value === newType) || NEW_RULE_TYPES[0]).rolling ? <label><span>Window days</span><input type="number" min="1" step="1" value={newWindowDays} onChange={(event) => setNewWindowDays(event.target.value)} /></label> : null}
            <label><span>Severity</span><select value={newSeverity} onChange={(event) => setNewSeverity(event.target.value as RosterRuleRead["severity"])}><option>INFO</option><option>WARNING</option><option>BLOCKER</option></select></label>
            <label className="wr-rule-control__check"><input type="checkbox" checked={newAllowOverride} onChange={(event) => setNewAllowOverride(event.target.checked)} /><span>Allow controlled override</span></label>
            <label className="wr-span-2"><span>Description / controlled source</span><input value={newDescription} onChange={(event) => setNewDescription(event.target.value)} placeholder="Describe the policy basis and controlled reference" /></label>
          </div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={closeCreate}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={busy || !newCode.trim() || !newName.trim()} onClick={() => void create()}><Save size={15} /> Save rule</button></div>
        </div>
      ) : null}

      <div className="wr-rule-control__list">
        {rules.map((rule) => (
          <article key={rule.id} className={!rule.is_active ? "is-inactive" : ""}>
            <div><strong>{rule.name}</strong><small>{compactValue(rule)}</small></div>
            <button type="button" className="wr-button wr-button--small" onClick={() => beginEdit(rule)}><Pencil size={14} /> Edit</button>
          </article>
        ))}
      </div>

      {editing && !creating ? (
        <div className="wr-rule-control__editor">
          <div className="wr-rule-control__editor-head">
            <strong>Edit {editing.code}</strong>
            <button type="button" className="wr-icon-button" aria-label="Close rule editor" onClick={close}><X size={16} /></button>
          </div>
          <div className="wr-rule-control__fields">
            <label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label>
            {parameter ? <label><span>{parameter.label}</span><input type="number" min="0" step="0.25" value={numericValue} onChange={(event) => setNumericValue(event.target.value)} /></label> : null}
            {editing && Object.prototype.hasOwnProperty.call(editing.parameters_json || {}, "window_days") ? <label><span>Window days</span><input type="number" min="1" step="1" value={windowDays} onChange={(event) => setWindowDays(event.target.value)} /></label> : null}
            <label><span>Severity</span><select value={severity} onChange={(event) => setSeverity(event.target.value as RosterRuleRead["severity"])}><option>INFO</option><option>WARNING</option><option>BLOCKER</option></select></label>
            <label className="wr-rule-control__check"><input type="checkbox" checked={allowOverride} onChange={(event) => setAllowOverride(event.target.checked)} /><span>Allow controlled override</span></label>
            <label className="wr-rule-control__check"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /><span>Active</span></label>
          </div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={close}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={busy || !name.trim()} onClick={() => void save()}><Save size={15} /> Save rule</button></div>
        </div>
      ) : null}
    </details>
  );
}
