import "./roster-rule-control.css";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Save, ShieldCheck, X } from "lucide-react";

import {
  listRosterRules,
  updateRosterRule,
} from "../../../services/rostering";
import { getCurrentWorkforcePermissions } from "../../../services/workforce";
import type { RosterRuleRead } from "../../../types/rostering";
import { errorMessage } from "../rosterUi";

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
  const [name, setName] = useState("");
  const [severity, setSeverity] = useState<RosterRuleRead["severity"]>("WARNING");
  const [allowOverride, setAllowOverride] = useState(true);
  const [isActive, setIsActive] = useState(true);
  const [numericValue, setNumericValue] = useState("");
  const [windowDays, setWindowDays] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const permissionsQuery = useQuery({
    queryKey: ["rostering", "settings", "permissions"],
    queryFn: getCurrentWorkforcePermissions,
    staleTime: 15 * 60_000,
    networkMode: "offlineFirst",
  });
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

      <div className="wr-rule-control__list">
        {rules.map((rule) => (
          <article key={rule.id} className={!rule.is_active ? "is-inactive" : ""}>
            <div><strong>{rule.name}</strong><small>{compactValue(rule)}</small></div>
            <button type="button" className="wr-button wr-button--small" onClick={() => beginEdit(rule)}><Pencil size={14} /> Edit</button>
          </article>
        ))}
      </div>

      {editing ? (
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
