import "./workforce-bulk-setup.css";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw, RotateCcw } from "lucide-react";
import { listBaseStations } from "../../../services/foundations";
import {
  downloadWorkforceHrBulkFailures, exportWorkforceHrPeople, getWorkforceHrBulkOperation,
  getWorkforceHrPeopleFacets, listWorkforceHrBulkOperationItems, listWorkforceHrPeople,
  previewWorkforceHrContractBatch, previewWorkforceHrDefaultDayBatch,
  resumeWorkforceHrBulkOperation, retryWorkforceHrBulkOperation,
  submitWorkforceHrContractBatch, submitWorkforceHrDefaultDayOperation,
} from "../../../services/workforceHr";
import type {
  HrBulkOperation, HrContractBatchPreview, HrContractDefaults, HrContractOverride,
  HrPeopleFilters, HrPeopleSelection,
} from "../../../types/workforceHr";
import { errorMessage, isoDate } from "../rosterUi";
import { RosterLoading, StatusPill } from "./RosterShell";

const PAGE_SIZES = [25, 50, 100, 250] as const;
const TERMINAL = new Set(["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]);
const key = (prefix: string) => `${prefix}-${crypto.randomUUID()}`;
const initialFilters = (): HrPeopleFilters => {
  const p = new URLSearchParams(window.location.search);
  return {
    search: p.get("bulk_search") || null,
    department_id: p.get("bulk_department") || null,
    contract_state: (p.get("bulk_contract") as HrPeopleFilters["contract_state"]) || "MISSING",
    pattern_state: (p.get("bulk_pattern") as HrPeopleFilters["pattern_state"]) || null,
    sort_by: "name", sort_dir: "asc",
  };
};

type Props = { canManageContracts: boolean; canInitializeDefaults: boolean };
export function WorkforceBulkSetupPanel({ canManageContracts, canInitializeDefaults }: Props) {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<HrPeopleFilters>(initialFilters);
  const [search, setSearch] = useState(filters.search || "");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(50);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [contractPreview, setContractPreview] = useState<HrContractBatchPreview | null>(null);
  const [patternPreview, setPatternPreview] = useState<Awaited<ReturnType<typeof previewWorkforceHrDefaultDayBatch>> | null>(null);
  const [overrides, setOverrides] = useState<Record<string, HrContractOverride>>({});
  const [operation, setOperation] = useState<HrBulkOperation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [defaults, setDefaults] = useState<HrContractDefaults>({
    contract_type: "PERMANENT", employment_status: "ACTIVE", effective_from: isoDate(new Date()), effective_to: null,
    standard_weekly_minutes: 2400, standard_daily_minutes: 480, fte_percentage: 100,
    primary_base_station_id: null, secondary_base_station_id: null, supervisor_user_id: null, cost_centre: null,
    overtime_eligible: true, night_shift_eligible: true, standby_eligible: true,
  });

  useEffect(() => { const timer = window.setTimeout(() => { setFilters((f) => ({ ...f, search: search.trim() || null })); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const values = { bulk_search: filters.search, bulk_department: filters.department_id, bulk_contract: filters.contract_state, bulk_pattern: filters.pattern_state };
    Object.entries(values).forEach(([name, value]) => value ? p.set(name, value) : p.delete(name));
    const suffix = p.toString() ? `?${p.toString()}` : "";
    window.history.replaceState(null, "", `${window.location.pathname}${suffix}${window.location.hash}`);
  }, [filters]);

  const facets = useQuery({ queryKey: ["workforce", "hr", "people", "facets"], queryFn: getWorkforceHrPeopleFacets });
  const peopleQuery = useQuery({ queryKey: ["workforce", "hr", "bulk", page, pageSize, filters], queryFn: () => listWorkforceHrPeople({ ...filters, page, page_size: pageSize }), placeholderData: (old) => old });
  const bases = useQuery({ queryKey: ["foundations", "base-stations", "active"], queryFn: () => listBaseStations({ include_inactive: false }), enabled: canManageContracts });
  const failures = useQuery({ queryKey: ["workforce", "hr", "bulk-failures", operation?.id], queryFn: () => listWorkforceHrBulkOperationItems(operation!.id, { page: 1, page_size: 100, status: "FAILED" }), enabled: Boolean(operation?.failed_count) });

  useEffect(() => {
    if (!operation || TERMINAL.has(operation.status)) return;
    const timer = window.setInterval(() => void getWorkforceHrBulkOperation(operation.id).then((next) => {
      setOperation(next);
      if (TERMINAL.has(next.status)) void queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] });
    }).catch((e) => setError(errorMessage(e))), 1500);
    return () => clearInterval(timer);
  }, [operation, queryClient]);

  const people = peopleQuery.data?.items || [];
  const total = peopleQuery.data?.total || 0;
  const pages = peopleQuery.data?.pages || 0;
  const selection = useMemo<HrPeopleSelection>(() => allMatching
    ? { mode: "FILTERED", filters, exclude_user_ids: [...excluded] }
    : { mode: "EXPLICIT", user_ids: [...selected], exclude_user_ids: [], filters: {} }, [allMatching, excluded, filters, selected]);
  const count = allMatching ? Math.max(0, total - excluded.size) : selected.size;
  const checked = (id: string) => allMatching ? !excluded.has(id) : selected.has(id);
  const pageChecked = people.length > 0 && people.every((row) => checked(row.user_id));
  const clearPreview = () => { setContractPreview(null); setPatternPreview(null); };
  const clearSelection = () => { setAllMatching(false); setSelected(new Set()); setExcluded(new Set()); clearPreview(); };
  const changeFilter = <K extends keyof HrPeopleFilters>(name: K, value: HrPeopleFilters[K]) => {
    if (count && !window.confirm("Changing filters clears the current bulk selection. Continue?")) return;
    clearSelection(); setFilters((f) => ({ ...f, [name]: value || null })); setPage(1);
  };
  const toggle = (id: string) => {
    clearPreview();
    const setter = allMatching ? setExcluded : setSelected;
    setter((old) => {
      const next = new Set(old);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const togglePage = () => { clearPreview(); const setter = allMatching ? setExcluded : setSelected; setter((old) => { const next = new Set(old); people.forEach(({ user_id }) => pageChecked ? next.delete(user_id) : next.add(user_id)); return next; }); };
  const run = async (name: string, action: () => Promise<void>) => { setBusy(name); setError(null); setMessage(null); try { await action(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(null); } };
  const contractPayload = { selection, defaults, overrides: Object.values(overrides) as HrContractOverride[], preview_limit: 250 };
  const patchOverride = (userId: string, patch: Partial<HrContractOverride>) => { setOverrides((old) => ({ ...old, [userId]: { ...old[userId], ...patch, user_id: userId } })); setContractPreview(null); };

  if (peopleQuery.isPending && !peopleQuery.data) return <RosterLoading label="Loading batch setup…" />;
  return <section className="wr-panel workforce-bulk">
    <header><div><span className="wr-eyebrow">Controlled Workforce setup</span><h2>Batch contracts and work patterns</h2><p>Preview eligibility, process bounded jobs, inspect failures and retry safely.</p></div><button type="button" className="wr-icon-button" aria-label="Refresh bulk workspace" onClick={() => void peopleQuery.refetch()}><RefreshCw size={16} /></button></header>
    {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}{message ? <div className="workforce-bulk__notice">{message}</div> : null}
    <div className="workforce-bulk__filters">
      <label><span>Search</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, staff, email or payroll" /></label>
      <label><span>Department</span><select value={filters.department_id || ""} onChange={(e) => changeFilter("department_id", e.target.value || null)}><option value="">All departments</option>{facets.data?.departments.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></label>
      <label><span>Contract record</span><select value={filters.contract_state || ""} onChange={(e) => changeFilter("contract_state", (e.target.value || null) as HrPeopleFilters["contract_state"])}><option value="">Any</option><option value="MISSING">Missing</option><option value="FUTURE">Future</option><option value="EFFECTIVE">Effective</option></select></label>
      <label><span>Work pattern</span><select value={filters.pattern_state || ""} onChange={(e) => changeFilter("pattern_state", (e.target.value || null) as HrPeopleFilters["pattern_state"])}><option value="">Any</option><option value="MISSING">Missing</option><option value="DEFAULT">Default</option><option value="ASSIGNED">Assigned</option></select></label>
    </div>
    <div className="workforce-bulk__selection-bar"><strong>{count.toLocaleString()} selected</strong><span>{allMatching ? `${total.toLocaleString()} matching minus ${excluded.size} exclusions` : `${people.filter((x) => checked(x.user_id)).length} on this page`}</span><button type="button" disabled={!total} onClick={() => { setAllMatching(true); setSelected(new Set()); setExcluded(new Set()); clearPreview(); }}>Select all {total.toLocaleString()} matching</button><button type="button" disabled={!count} onClick={clearSelection}>Clear</button><button type="button" disabled={!count} onClick={() => void run("export", () => exportWorkforceHrPeople(selection))}><Download size={14} /> Export</button></div>
    <div className="workforce-bulk__table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Select current page" checked={pageChecked} onChange={togglePage} /></th><th>Staff</th><th>Person</th><th>Department</th><th>Position</th><th>Contract</th><th>Pattern</th><th>Readiness</th></tr></thead><tbody>{people.map((person) => <tr key={person.user_id}><td><input type="checkbox" checked={checked(person.user_id)} onChange={() => toggle(person.user_id)} /></td><td>{person.staff_code}</td><td><strong>{person.full_name}</strong><small>{person.email}</small></td><td>{person.department_name || "—"}</td><td>{person.position_title || "—"}</td><td><StatusPill value={person.contract_state} /></td><td><StatusPill value={person.pattern_state} /></td><td><StatusPill value={person.readiness_state} /></td></tr>)}</tbody></table></div>
    <div className="workforce-bulk__pager"><span>{total ? `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} of ${total.toLocaleString()}` : "0 records"}</span><select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value) as typeof pageSize); setPage(1); }}>{PAGE_SIZES.map((x) => <option key={x} value={x}>{x} per page</option>)}</select><button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} of {Math.max(1, pages)}</span><button type="button" disabled={!pages || page >= pages} onClick={() => setPage(page + 1)}>Next</button></div>

    {canManageContracts ? <div className="workforce-bulk__card"><h3>Create employment contracts</h3><div className="workforce-bulk__defaults">
      <label><span>Contract type</span><select value={defaults.contract_type} onChange={(e) => { setDefaults({ ...defaults, contract_type: e.target.value }); setContractPreview(null); }}><option value="PERMANENT">Permanent</option><option value="FIXED_TERM">Fixed term</option><option value="TEMPORARY">Temporary</option><option value="CONTRACTOR">Contractor</option><option value="INTERN">Intern</option></select></label>
      <label><span>Status</span><select value={defaults.employment_status} onChange={(e) => { setDefaults({ ...defaults, employment_status: e.target.value }); setContractPreview(null); }}><option value="ACTIVE">Active</option><option value="ONBOARDING">Onboarding</option><option value="SUSPENDED">Suspended</option></select></label>
      <label><span>Start</span><input type="date" value={defaults.effective_from} onChange={(e) => { setDefaults({ ...defaults, effective_from: e.target.value }); setContractPreview(null); }} /></label>
      <label><span>End</span><input type="date" value={defaults.effective_to || ""} onChange={(e) => { setDefaults({ ...defaults, effective_to: e.target.value || null }); setContractPreview(null); }} /></label>
      <label><span>Primary base</span><select value={defaults.primary_base_station_id || ""} onChange={(e) => { setDefaults({ ...defaults, primary_base_station_id: e.target.value || null }); setContractPreview(null); }}><option value="">Select base</option>{bases.data?.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></label>
      <label><span>Supervisor user ID</span><input value={defaults.supervisor_user_id || ""} onChange={(e) => { setDefaults({ ...defaults, supervisor_user_id: e.target.value || null }); setContractPreview(null); }} /></label>
      <label><span>Weekly hours</span><input type="number" value={defaults.standard_weekly_minutes / 60} onChange={(e) => setDefaults({ ...defaults, standard_weekly_minutes: Math.round(Number(e.target.value) * 60) })} /></label>
      <label><span>Daily hours</span><input type="number" value={defaults.standard_daily_minutes / 60} onChange={(e) => setDefaults({ ...defaults, standard_daily_minutes: Math.round(Number(e.target.value) * 60) })} /></label>
      <label><span>FTE %</span><input type="number" min="1" max="100" value={defaults.fte_percentage} onChange={(e) => setDefaults({ ...defaults, fte_percentage: Number(e.target.value) })} /></label>
    </div><div className="workforce-bulk__actions"><button type="button" disabled={!count || busy === "contract-preview"} onClick={() => void run("contract-preview", async () => setContractPreview(await previewWorkforceHrContractBatch(contractPayload)))}>Preview contract batch</button>{contractPreview ? <button type="button" disabled={!contractPreview.eligible_count} onClick={() => void run("contract-submit", async () => { const op = await submitWorkforceHrContractBatch({ ...contractPayload, expected_match_count: contractPreview.matched_count, expected_selection_token: contractPreview.selection_token }, key("contracts")); setOperation(op); setMessage(`${op.total_count} eligible contracts queued; blocked records were excluded.`); clearSelection(); })}>Confirm {contractPreview.eligible_count} eligible contracts</button> : null}</div>
    {contractPreview ? <div className="workforce-bulk__preview"><p>{contractPreview.eligible_count} eligible · {contractPreview.blocked_count} blocked · {contractPreview.already_contracted_count} overlaps</p><div className="workforce-bulk__preview-table"><table><thead><tr><th>Person</th><th>End date override</th><th>Base override</th><th>Supervisor override</th><th>Validation</th></tr></thead><tbody>{contractPreview.rows.map((row) => <tr key={row.user_id}><td><strong>{row.full_name}</strong><small>{row.staff_code}</small></td><td><input type="date" value={overrides[row.user_id]?.effective_to || row.effective_to || ""} onChange={(e) => patchOverride(row.user_id, { effective_to: e.target.value || null })} /></td><td><select value={overrides[row.user_id]?.primary_base_station_id || row.primary_base_station_id || ""} onChange={(e) => patchOverride(row.user_id, { primary_base_station_id: e.target.value || null })}><option value="">Default</option>{bases.data?.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></td><td><input value={overrides[row.user_id]?.supervisor_user_id || row.supervisor_user_id || ""} onChange={(e) => patchOverride(row.user_id, { supervisor_user_id: e.target.value || null })} /></td><td>{row.eligible ? <StatusPill value="ELIGIBLE" /> : row.reasons.join(", ")}</td></tr>)}</tbody></table></div>{contractPreview.rows_truncated ? <small>Spreadsheet preview capped at 250 rows; the server retains the complete selection snapshot.</small> : null}</div> : null}</div> : null}

    {canInitializeDefaults ? <div className="workforce-bulk__card"><h3>Assign managed default day pattern</h3><p>This never blindly processes the tenant; the exact selection is previewed before submission.</p><div className="workforce-bulk__actions"><button type="button" disabled={!count} onClick={() => void run("pattern-preview", async () => setPatternPreview(await previewWorkforceHrDefaultDayBatch(selection)))}>Preview eligibility</button>{patternPreview ? <button type="button" disabled={!patternPreview.assignable_count} onClick={() => void run("pattern-submit", async () => { const op = await submitWorkforceHrDefaultDayOperation(selection, patternPreview.matched_count, patternPreview.selection_token, key("pattern")); setOperation(op); clearSelection(); })}>Confirm {patternPreview.assignable_count} assignments</button> : null}</div>{patternPreview ? <p>{patternPreview.eligible_count} eligible · {patternPreview.already_assigned_count} compliant · {patternPreview.ineligible_count} ineligible</p> : null}</div> : null}

    {operation ? <div className="workforce-bulk__operation"><div><h3>Operation {operation.id}</h3><StatusPill value={operation.status} /></div><progress max="100" value={operation.progress_percent} /><p>{operation.succeeded_count} succeeded · {operation.skipped_count} skipped · {operation.failed_count} failed · {operation.processed_count}/{operation.total_count}</p>{operation.last_error ? <div className="wr-inline-error">{operation.last_error}</div> : null}<div className="workforce-bulk__actions">{operation.failed_count ? <><button type="button" onClick={() => void run("retry", async () => setOperation(await retryWorkforceHrBulkOperation(operation.id, key("retry"))))}><RotateCcw size={14} /> Retry failed only</button><button type="button" onClick={() => void downloadWorkforceHrBulkFailures(operation.id)}><Download size={14} /> Failure report</button></> : null}{operation.status === "FAILED" ? <button type="button" onClick={() => void run("resume", async () => setOperation(await resumeWorkforceHrBulkOperation(operation.id)))}>Resume interrupted job</button> : null}</div>{failures.data?.items.length ? <ul>{failures.data.items.map((x) => <li key={x.id}>{x.staff_code || x.user_id}: {x.outcome_message}</li>)}</ul> : null}</div> : null}
  </section>;
}
