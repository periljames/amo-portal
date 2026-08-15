import "./workforce-bulk-setup.css";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, CheckCircle2, Clock3, Download, FileText, FilterX, LoaderCircle, RefreshCw, RotateCcw, UsersRound, X } from "lucide-react";
import { listBaseStations } from "../../../services/foundations";
import {
  downloadWorkforceHrBulkFailures, exportWorkforceHrPeople, getWorkforceHrBulkOperation,
  getWorkforceHrPeopleFacets, listWorkforceHrBulkOperationItems, listWorkforceHrPeople,
  listWorkforceHrPatterns,
  previewWorkforceHrContractBatch,
  previewWorkforceHrPatternBatch,
  resumeWorkforceHrBulkOperation, retryWorkforceHrBulkOperation,
  submitWorkforceHrContractBatch,
  submitWorkforceHrPatternBatch,
} from "../../../services/workforceHr";
import type {
  HrBulkOperation, HrContractBatchPreview, HrContractDefaults, HrContractOverride,
  HrPeopleFilters, HrPeopleSelection, HrWorkPatternBatchOptions, HrWorkPatternBatchPreview,
} from "../../../types/workforceHr";
import { errorMessage, isoDate } from "../rosterUi";
import { RosterLoading, StatusPill } from "./RosterShell";

const PAGE_SIZES = [25, 50, 100, 250] as const;
const TERMINAL = new Set(["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]);
const STALLED_QUEUE_MS = 15_000;
const STALLED_RUNNING_MS = 5 * 60_000;
const key = (prefix: string) => `${prefix}-${crypto.randomUUID()}`;
const ageMs = (value?: string | null) => value ? Math.max(0, Date.now() - new Date(value).getTime()) : Number.POSITIVE_INFINITY;
const selectedFilter = <T extends string>(value: string | null): T | null => value && value !== "ANY" ? value as T : null;
const formatDuration = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "Calculating…";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} sec`;
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
};
const initialFilters = (): HrPeopleFilters => {
  const p = new URLSearchParams(window.location.search);
  const legacyPatternDefault = p.get("bulk_pattern") === "MISSING" && p.get("workforce_view") !== "bulk";
  return {
    search: p.get("bulk_search") || null,
    department_id: p.get("bulk_department") || null,
    contract_state: selectedFilter<NonNullable<HrPeopleFilters["contract_state"]>>(p.get("bulk_contract")),
    pattern_state: legacyPatternDefault ? null : selectedFilter<NonNullable<HrPeopleFilters["pattern_state"]>>(p.get("bulk_pattern")),
    sort_by: "name", sort_dir: "asc",
  };
};

type BatchAction = "contracts" | "patterns";
type Props = { canManageContracts: boolean; canManagePatterns: boolean };
export function WorkforceBulkSetupPanel({ canManageContracts, canManagePatterns }: Props) {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<HrPeopleFilters>(initialFilters);
  const [search, setSearch] = useState(filters.search || "");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(50);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [contractPreview, setContractPreview] = useState<HrContractBatchPreview | null>(null);
  const [patternPreview, setPatternPreview] = useState<HrWorkPatternBatchPreview | null>(null);
  const [overrides, setOverrides] = useState<Record<string, HrContractOverride>>({});
  const [action, setAction] = useState<BatchAction>(canManagePatterns ? "patterns" : "contracts");
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
  const [patternOptions, setPatternOptions] = useState<HrWorkPatternBatchOptions>({
    work_pattern_id: "", effective_from: isoDate(new Date()), effective_to: null,
    cycle_anchor_date: isoDate(new Date()), conflict_strategy: "REPLACE_OVERLAPS",
    reason: "Batch work-pattern change",
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
  const patterns = useQuery({
    queryKey: ["workforce", "hr", "work-patterns", "active"],
    queryFn: () => listWorkforceHrPatterns(false),
    enabled: canManagePatterns,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
  });
  const failures = useQuery({ queryKey: ["workforce", "hr", "bulk-failures", operation?.id], queryFn: () => listWorkforceHrBulkOperationItems(operation!.id, { page: 1, page_size: 100, status: "FAILED" }), enabled: Boolean(operation?.failed_count) });
  const runningItems = useQuery({
    queryKey: ["workforce", "hr", "bulk-running", operation?.id],
    queryFn: () => listWorkforceHrBulkOperationItems(operation!.id, { page: 1, page_size: 3, status: "RUNNING" }),
    enabled: Boolean(operation && !TERMINAL.has(operation.status)),
    refetchInterval: operation && !TERMINAL.has(operation.status) ? 750 : false,
  });
  const pendingItems = useQuery({
    queryKey: ["workforce", "hr", "bulk-pending", operation?.id],
    queryFn: () => listWorkforceHrBulkOperationItems(operation!.id, { page: 1, page_size: 3, status: "PENDING" }),
    enabled: Boolean(operation && !TERMINAL.has(operation.status)),
    refetchInterval: operation && !TERMINAL.has(operation.status) ? 1500 : false,
  });

  useEffect(() => {
    if (!operation || TERMINAL.has(operation.status)) return;
    const timer = window.setInterval(() => void getWorkforceHrBulkOperation(operation.id).then((next) => {
      setOperation(next);
      if (TERMINAL.has(next.status)) void queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] });
    }).catch((e) => setError(errorMessage(e))), 750);
    return () => clearInterval(timer);
  }, [operation, queryClient]);

  const people = peopleQuery.data?.items || [];
  const total = peopleQuery.data?.total || 0;
  const pages = peopleQuery.data?.pages || 0;
  const selection = useMemo<HrPeopleSelection>(() => allMatching
    ? { mode: "FILTERED", filters, exclude_user_ids: [...excluded] }
    : { mode: "EXPLICIT", user_ids: [...selected], exclude_user_ids: [], filters: {} }, [allMatching, excluded, filters, selected]);
  const count = allMatching ? Math.max(0, total - excluded.size) : selected.size;
  const queueIsSlow = operation?.status === "QUEUED" && ageMs(operation.updated_at || operation.created_at) >= STALLED_QUEUE_MS;
  const runningIsStale = operation?.status === "RUNNING" && ageMs(operation.heartbeat_at || operation.started_at) >= STALLED_RUNNING_MS;
  const elapsedSeconds = operation ? ageMs(operation.started_at || operation.created_at) / 1000 : 0;
  const throughput = operation?.processed_count ? operation.processed_count / Math.max(1, elapsedSeconds) : 0;
  const remainingSeconds = operation && throughput ? (operation.total_count - operation.processed_count) / throughput : Number.POSITIVE_INFINITY;
  const activeItem = runningItems.data?.items[0];
  const upcoming = pendingItems.data?.items || [];
  const resetFilters = () => {
    clearSelection();
    setSearch("");
    setFilters({ search: null, department_id: null, contract_state: null, pattern_state: null, sort_by: "name", sort_dir: "asc" });
    setPage(1);
  };
  const refreshWorkspace = async () => {
    setError(null);
    await Promise.all([
      peopleQuery.refetch(),
      facets.refetch(),
      canManagePatterns ? patterns.refetch() : Promise.resolve(),
      canManageContracts ? bases.refetch() : Promise.resolve(),
    ]);
  };
  const checked = (id: string) => allMatching ? !excluded.has(id) : selected.has(id);
  const pageChecked = people.length > 0 && people.every((row) => checked(row.user_id));
  useEffect(() => {
    const available = patterns.data || [];
    if (!available.length) return;
    if (!patternOptions.work_pattern_id || !available.some((pattern) => pattern.id === patternOptions.work_pattern_id)) {
      setPatternOptions((old) => ({ ...old, work_pattern_id: available[0].id }));
      setPatternPreview(null);
    }
  }, [patternOptions.work_pattern_id, patterns.data]);

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
  const patternPayload = { selection, options: patternOptions, preview_limit: 250 };
  const patchOverride = (userId: string, patch: Partial<HrContractOverride>) => { setOverrides((old) => ({ ...old, [userId]: { ...old[userId], ...patch, user_id: userId } })); setContractPreview(null); };

  if (peopleQuery.isPending && !peopleQuery.data) return <RosterLoading label="Loading batch setup…" />;
  return <section className="wr-panel workforce-bulk">
    <header><div><span className="wr-eyebrow">Controlled Workforce setup</span><h2>Batch personnel setup</h2><p>Select people or one department, preview, then confirm.</p></div><button type="button" className="wr-icon-button" aria-label="Refresh people and rotations" title="Refresh people and rotations" onClick={() => void refreshWorkspace()}><RefreshCw size={16} /></button></header>
    {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}{patterns.error && canManagePatterns ? <div className="wr-inline-error" role="alert">Could not refresh work patterns. {errorMessage(patterns.error)} <button type="button" onClick={() => void patterns.refetch()}>Retry</button></div> : null}{message ? <div className="workforce-bulk__notice">{message}</div> : null}
    <div className="workforce-bulk__directory">
      <aside className="workforce-bulk__filter-rail" aria-label="Personnel filters">
        <div className="workforce-bulk__rail-heading"><strong>Find personnel</strong><span>Filters update the list immediately.</span></div>
        <div className="workforce-bulk__filters">
      <label><span>Search</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, staff, email or payroll" /></label>
      <label><span>Department</span><select value={filters.department_id || ""} onChange={(e) => changeFilter("department_id", e.target.value || null)}><option value="">All departments</option>{facets.data?.departments.map((x) => <option key={x.value} value={x.value}>{x.label} ({x.count})</option>)}</select></label>
      <label><span>Contract record</span><select value={filters.contract_state || ""} onChange={(e) => changeFilter("contract_state", (e.target.value || null) as HrPeopleFilters["contract_state"])}><option value="">Any</option><option value="MISSING">Missing</option><option value="FUTURE">Future</option><option value="EFFECTIVE">Effective</option></select></label>
      <label><span>Work pattern</span><select value={filters.pattern_state || ""} onChange={(e) => changeFilter("pattern_state", (e.target.value || null) as HrPeopleFilters["pattern_state"])}><option value="">Any</option><option value="MISSING">Missing</option><option value="DEFAULT">Legacy default</option><option value="ASSIGNED">Assigned or automatic</option></select></label>
        </div>
        <button type="button" className="workforce-bulk__reset" onClick={resetFilters}><FilterX size={14} /> Reset filters</button>
      </aside>
      <div className="workforce-bulk__people-pane">
    <div className="workforce-bulk__people-heading"><div><UsersRound size={17} /><strong>Personnel</strong></div><span>{total.toLocaleString()} matching records</span></div>
    <div className="workforce-bulk__selection-bar"><strong>{count.toLocaleString()} selected</strong><span>{allMatching ? `${total.toLocaleString()} matching minus ${excluded.size} exclusions` : `${people.filter((x) => checked(x.user_id)).length} on this page`}</span><button type="button" disabled={!total} onClick={() => { setAllMatching(true); setSelected(new Set()); setExcluded(new Set()); clearPreview(); }}>{filters.department_id ? `Select department (${total.toLocaleString()})` : `Select all ${total.toLocaleString()} matching`}</button><button type="button" disabled={!count} onClick={clearSelection}>Clear</button><button type="button" disabled={!count} onClick={() => void run("export", () => exportWorkforceHrPeople(selection))}><Download size={14} /> Export</button></div>
    <div className="workforce-bulk__table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Select current page" checked={pageChecked} onChange={togglePage} /></th><th>Staff</th><th>Person</th><th>Department</th><th>Position</th><th>Contract</th><th>Pattern</th><th>Readiness</th></tr></thead><tbody>{people.map((person) => <tr key={person.user_id}><td><input type="checkbox" checked={checked(person.user_id)} onChange={() => toggle(person.user_id)} /></td><td>{person.staff_code}</td><td><strong>{person.full_name}</strong><small>{person.email}</small></td><td>{person.department_name || "—"}</td><td>{person.position_title || "—"}</td><td><StatusPill value={person.contract_state} /></td><td><StatusPill value={person.pattern_state} /></td><td><StatusPill value={person.readiness_state} /></td></tr>)}</tbody></table></div>
    <div className="workforce-bulk__pager"><span>{total ? `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} of ${total.toLocaleString()}` : "0 records"}</span><select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value) as typeof pageSize); setPage(1); }}>{PAGE_SIZES.map((x) => <option key={x} value={x}>{x} per page</option>)}</select><button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} of {Math.max(1, pages)}</span><button type="button" disabled={!pages || page >= pages} onClick={() => setPage(page + 1)}>Next</button></div>
      </div>
    </div>

    <div className="workforce-bulk__action-workspace">
      <aside className="workforce-bulk__action-rail"><span className="wr-eyebrow">Selected action</span>{canManagePatterns ? <button type="button" className={action === "patterns" ? "is-active" : ""} onClick={() => { setAction("patterns"); clearPreview(); }}><CalendarRange size={16} /><span><strong>Work patterns</strong><small>Assign or replace rotations</small></span></button> : null}{canManageContracts ? <button type="button" className={action === "contracts" ? "is-active" : ""} onClick={() => { setAction("contracts"); clearPreview(); }}><FileText size={16} /><span><strong>Employment contracts</strong><small>Create governed records</small></span></button> : null}</aside>
      <div className="workforce-bulk__action-content">
    {canManagePatterns && action === "patterns" ? <div className="workforce-bulk__card"><div><h3>Change work pattern</h3><p>The selected rotation applies only to the people above; earlier assignment history is retained.</p></div><div className="workforce-bulk__defaults workforce-bulk__defaults--pattern">
      <label><span>New pattern</span><select value={patternOptions.work_pattern_id} disabled={patterns.isPending && !patterns.data} onChange={(e) => { setPatternOptions({ ...patternOptions, work_pattern_id: e.target.value }); setPatternPreview(null); }}><option value="">{patterns.isPending ? "Loading patterns…" : "Select pattern"}</option>{patterns.data?.map((pattern) => <option key={pattern.id} value={pattern.id}>{pattern.code} · {pattern.name}</option>)}</select></label>
      <label><span>Effective from</span><input type="date" value={patternOptions.effective_from} onChange={(e) => { setPatternOptions({ ...patternOptions, effective_from: e.target.value, cycle_anchor_date: e.target.value }); setPatternPreview(null); }} /></label>
      <label><span>Effective until</span><input type="date" min={patternOptions.effective_from} value={patternOptions.effective_to || ""} onChange={(e) => { setPatternOptions({ ...patternOptions, effective_to: e.target.value || null }); setPatternPreview(null); }} /></label>
      <label><span>Cycle day 1</span><input type="date" value={patternOptions.cycle_anchor_date || patternOptions.effective_from} onChange={(e) => { setPatternOptions({ ...patternOptions, cycle_anchor_date: e.target.value }); setPatternPreview(null); }} /></label>
      <label><span>If already assigned</span><select value={patternOptions.conflict_strategy} onChange={(e) => { setPatternOptions({ ...patternOptions, conflict_strategy: e.target.value as HrWorkPatternBatchOptions["conflict_strategy"] }); setPatternPreview(null); }}><option value="REPLACE_OVERLAPS">Replace from effective date</option><option value="SKIP_ASSIGNED">Keep existing assignment</option></select></label>
      <label><span>Change reason</span><input value={patternOptions.reason} onChange={(e) => { setPatternOptions({ ...patternOptions, reason: e.target.value }); setPatternPreview(null); }} /></label>
    </div><div className="workforce-bulk__actions"><button type="button" disabled={!count || !patternOptions.work_pattern_id || patternOptions.reason.trim().length < 5 || busy === "pattern-preview"} onClick={() => void run("pattern-preview", async () => setPatternPreview(await previewWorkforceHrPatternBatch(patternPayload)))}>Preview pattern changes</button>{patternPreview ? <button type="button" disabled={!patternPreview.eligible_count || busy === "pattern-submit"} onClick={() => void run("pattern-submit", async () => { const op = await submitWorkforceHrPatternBatch({ ...patternPayload, expected_match_count: patternPreview.matched_count, expected_selection_token: patternPreview.selection_token }, key("patterns")); setOperation(op); setMessage(`${op.total_count} work-pattern changes queued.`); clearSelection(); })}>Confirm {patternPreview.eligible_count} changes</button> : null}</div>
    {patternPreview ? <div className="workforce-bulk__preview"><p><strong>{patternPreview.target_pattern_code}</strong> · {patternPreview.assign_count} new · {patternPreview.replace_count} replacements · {patternPreview.unchanged_count} unchanged · {patternPreview.skipped_count} kept · {patternPreview.blocked_count} blocked</p><div className="workforce-bulk__preview-table"><table><thead><tr><th>Person</th><th>Department</th><th>Current</th><th>New</th><th>Action</th></tr></thead><tbody>{patternPreview.rows.map((row) => <tr key={row.user_id}><td><strong>{row.full_name}</strong><small>{row.staff_code}</small></td><td>{row.department_name || "—"}</td><td>{row.current_pattern_code ? <><strong>{row.current_pattern_code}</strong><small>{row.current_pattern_name}</small></> : "Not assigned"}</td><td><strong>{row.target_pattern_code}</strong><small>{row.target_pattern_name}</small></td><td><StatusPill value={row.action} />{row.reasons.length ? <small>{row.reasons.join(" · ")}</small> : null}</td></tr>)}</tbody></table></div>{patternPreview.rows_truncated ? <small>Preview capped at 250 rows; the complete filtered selection is rechecked before submission.</small> : null}</div> : null}</div> : null}

    {canManageContracts && action === "contracts" ? <div className="workforce-bulk__card"><h3>Create employment contracts</h3><div className="workforce-bulk__defaults">
      <label><span>Contract type</span><select value={defaults.contract_type} onChange={(e) => { setDefaults({ ...defaults, contract_type: e.target.value }); setContractPreview(null); }}><option value="PERMANENT">Permanent</option><option value="FIXED_TERM">Fixed term</option><option value="TEMPORARY">Temporary</option><option value="CONTRACTOR">Contractor</option><option value="INTERN">Intern</option></select></label>
      <label><span>Status</span><select value={defaults.employment_status} onChange={(e) => { setDefaults({ ...defaults, employment_status: e.target.value }); setContractPreview(null); }}><option value="ACTIVE">Active</option><option value="ONBOARDING">Onboarding</option><option value="SUSPENDED">Suspended</option></select></label>
      <label><span>Fallback start</span><input type="date" value={defaults.effective_from} onChange={(e) => { setDefaults({ ...defaults, effective_from: e.target.value }); setContractPreview(null); }} /><small>Each person’s imported hire date takes priority.</small></label>
      <label><span>End</span><input type="date" value={defaults.effective_to || ""} onChange={(e) => { setDefaults({ ...defaults, effective_to: e.target.value || null }); setContractPreview(null); }} /></label>
      <label><span>Primary base</span><select value={defaults.primary_base_station_id || ""} onChange={(e) => { setDefaults({ ...defaults, primary_base_station_id: e.target.value || null }); setContractPreview(null); }}><option value="">Select base</option>{bases.data?.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></label>
      <label><span>Supervisor user ID</span><input value={defaults.supervisor_user_id || ""} onChange={(e) => { setDefaults({ ...defaults, supervisor_user_id: e.target.value || null }); setContractPreview(null); }} /></label>
      <label><span>Weekly hours</span><input type="number" value={defaults.standard_weekly_minutes / 60} onChange={(e) => setDefaults({ ...defaults, standard_weekly_minutes: Math.round(Number(e.target.value) * 60) })} /></label>
      <label><span>Daily hours</span><input type="number" value={defaults.standard_daily_minutes / 60} onChange={(e) => setDefaults({ ...defaults, standard_daily_minutes: Math.round(Number(e.target.value) * 60) })} /></label>
      <label><span>FTE %</span><input type="number" min="1" max="100" value={defaults.fte_percentage} onChange={(e) => setDefaults({ ...defaults, fte_percentage: Number(e.target.value) })} /></label>
    </div><div className="workforce-bulk__actions"><button type="button" disabled={!count || busy === "contract-preview"} onClick={() => void run("contract-preview", async () => setContractPreview(await previewWorkforceHrContractBatch(contractPayload)))}>Preview contract batch</button>{contractPreview ? <button type="button" disabled={!contractPreview.eligible_count} onClick={() => void run("contract-submit", async () => { const op = await submitWorkforceHrContractBatch({ ...contractPayload, expected_match_count: contractPreview.matched_count, expected_selection_token: contractPreview.selection_token }, key("contracts")); setOperation(op); setMessage(`${op.total_count} eligible contracts queued; blocked records were excluded.`); clearSelection(); })}>Confirm {contractPreview.eligible_count} eligible contracts</button> : null}</div>
    {contractPreview ? <div className="workforce-bulk__preview"><p>{contractPreview.eligible_count} eligible · {contractPreview.blocked_count} blocked · {contractPreview.already_contracted_count} overlaps</p><div className="workforce-bulk__preview-table"><table><thead><tr><th>Person</th><th>Workforce start</th><th>End date override</th><th>Base override</th><th>Supervisor override</th><th>Validation</th></tr></thead><tbody>{contractPreview.rows.map((row) => <tr key={row.user_id}><td><strong>{row.full_name}</strong><small>{row.staff_code}</small></td><td><strong>{row.effective_from}</strong><small>Hire date when available</small></td><td><input type="date" value={overrides[row.user_id]?.effective_to || row.effective_to || ""} onChange={(e) => patchOverride(row.user_id, { effective_to: e.target.value || null })} /></td><td><select value={overrides[row.user_id]?.primary_base_station_id || row.primary_base_station_id || ""} onChange={(e) => patchOverride(row.user_id, { primary_base_station_id: e.target.value || null })}><option value="">Default</option>{bases.data?.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</select></td><td><input value={overrides[row.user_id]?.supervisor_user_id || row.supervisor_user_id || ""} onChange={(e) => patchOverride(row.user_id, { supervisor_user_id: e.target.value || null })} /></td><td>{row.eligible ? <StatusPill value="ELIGIBLE" /> : row.reasons.join(", ")}</td></tr>)}</tbody></table></div>{contractPreview.rows_truncated ? <small>Spreadsheet preview capped at 250 rows; the server retains the complete selection snapshot.</small> : null}</div> : null}</div> : null}

      </div>
    </div>

    {operation ? <aside className="workforce-bulk__operation" aria-live="polite" aria-label="Background operation progress">
      <div className="workforce-bulk__operation-heading">
        <div>{TERMINAL.has(operation.status) ? <CheckCircle2 size={19} /> : <LoaderCircle className="is-spinning" size={19} />}<div><strong>{operation.operation_type === "CREATE_CONTRACTS" ? "Creating employment contracts" : operation.operation_type === "ASSIGN_WORK_PATTERN" ? "Changing work patterns" : "Processing personnel"}</strong><small>{operation.id}</small></div></div>
        <div><StatusPill value={operation.status} />{TERMINAL.has(operation.status) ? <button type="button" className="wr-icon-button" aria-label="Dismiss completed operation" onClick={() => setOperation(null)}><X size={14} /></button> : null}</div>
      </div>
      <div className="workforce-bulk__progress-copy"><strong>{Math.round(operation.progress_percent)}%</strong><span>{operation.processed_count} of {operation.total_count} records</span></div>
      <div className={`workforce-bulk__progress-track ${operation.status === "QUEUED" ? "is-indeterminate" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(operation.progress_percent)}>
        <span style={{ width: `${operation.status === "QUEUED" ? 8 : operation.progress_percent}%` }} />
      </div>
      <div className="workforce-bulk__operation-stages">
        <span className="is-done"><CheckCircle2 size={13} /> Accepted</span>
        <span className={operation.status === "RUNNING" ? "is-active" : operation.processed_count ? "is-done" : ""}>{operation.status === "RUNNING" ? <LoaderCircle className="is-spinning" size={13} /> : <CheckCircle2 size={13} />} Process records</span>
        <span className={TERMINAL.has(operation.status) ? "is-done" : ""}><CheckCircle2 size={13} /> Refresh workforce</span>
      </div>
      <div className="workforce-bulk__live-row">
        <div><span>Now</span><strong>{activeItem ? `${activeItem.full_name || activeItem.staff_code || activeItem.user_id}` : operation.status === "QUEUED" ? "Waiting for a worker" : TERMINAL.has(operation.status) ? "Finished" : "Preparing next record"}</strong></div>
        <div><span>Estimated remaining</span><strong><Clock3 size={13} /> {TERMINAL.has(operation.status) ? "Complete" : formatDuration(remainingSeconds)}</strong></div>
      </div>
      {upcoming.length && !TERMINAL.has(operation.status) ? <p className="workforce-bulk__up-next">Up next: {upcoming.map((item) => item.full_name || item.staff_code || item.user_id).join(", ")}</p> : null}
      <div className="workforce-bulk__result-counts"><span>{operation.succeeded_count} succeeded</span><span>{operation.skipped_count} skipped</span><span className={operation.failed_count ? "has-failures" : ""}>{operation.failed_count} failed</span></div>
      {operation.status === "QUEUED" && !queueIsSlow ? <p className="workforce-bulk__queue-note">The request is accepted. Live progress will start as soon as the first record is claimed.</p> : null}
      {queueIsSlow ? <div className="wr-inline-error">This operation has waited longer than expected. It can be released without repeating completed records.</div> : null}
      {runningIsStale ? <div className="wr-inline-error">The processing heartbeat is stale. Completed records remain safe when processing resumes.</div> : null}
      {operation.last_error ? <div className="wr-inline-error">{operation.last_error}</div> : null}
      <div className="workforce-bulk__actions">
        {operation.failed_count ? <><button type="button" onClick={() => void run("retry", async () => setOperation(await retryWorkforceHrBulkOperation(operation.id, key("retry"))))}><RotateCcw size={14} /> Retry failed only</button><button type="button" onClick={() => void downloadWorkforceHrBulkFailures(operation.id)}><Download size={14} /> Failure report</button></> : null}
        {operation.status === "FAILED" || queueIsSlow || runningIsStale ? <button type="button" disabled={busy === "resume"} onClick={() => void run("resume", async () => setOperation(await resumeWorkforceHrBulkOperation(operation.id)))}>{operation.status === "FAILED" || runningIsStale ? "Resume interrupted job" : "Release queued job now"}</button> : null}
      </div>
      {failures.data?.items.length ? <ul>{failures.data.items.map((item) => <li key={item.id}>{item.staff_code || item.user_id}: {item.outcome_message}</li>)}</ul> : null}
    </aside> : null}
  </section>;
}
