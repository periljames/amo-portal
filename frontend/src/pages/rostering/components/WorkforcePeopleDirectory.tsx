import "./workforce-people-directory.css";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Download,
  RefreshCw,
  Save,
  Search,
  SlidersHorizontal,
  UsersRound,
  X,
} from "lucide-react";

import { listBaseStations } from "../../../services/foundations";
import {
  createEmploymentContract,
  updateEmploymentContract,
} from "../../../services/workforce";
import {
  exportWorkforceHrPeople,
  getWorkforceHrPeopleFacets,
  listWorkforceHrPeople,
} from "../../../services/workforceHr";
import type { BaseStationRead } from "../../../types/foundations";
import type {
  HrFilterOption,
  HrPeopleFilters,
  HrPeopleSelection,
  HrPersonReadiness,
} from "../../../types/workforceHr";
import type { ContractType, EmploymentStatus } from "../../../types/workforce";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

const EMPTY_FILTERS: HrPeopleFilters = {
  sort_by: "name",
  sort_dir: "asc",
};

const PAGE_SIZES = [25, 50, 100, 200] as const;

type ContractDraft = {
  contract_type: ContractType;
  employment_status: EmploymentStatus;
  effective_from: string;
  effective_to: string;
  primary_base_station_id: string;
  standard_weekly_hours: string;
  standard_daily_hours: string;
  fte_percentage: string;
  cost_centre: string;
  payroll_number: string;
  overtime_eligible: boolean;
  night_shift_eligible: boolean;
  standby_eligible: boolean;
};

type Props = {
  canManageContracts: boolean;
};

export function WorkforcePeopleDirectory({ canManageContracts }: Props) {
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [filters, setFilters] = useState<HrPeopleFilters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(25);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [editing, setEditing] = useState<HrPersonReadiness | null>(null);
  const [draft, setDraft] = useState<ContractDraft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => ({ ...current, search: searchInput.trim() || null }));
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const facetsQuery = useQuery({
    queryKey: ["workforce", "hr", "people", "facets"],
    queryFn: getWorkforceHrPeopleFacets,
    staleTime: 5 * 60_000,
  });

  const peopleQuery = useQuery({
    queryKey: ["workforce", "hr", "people", "directory", page, pageSize, filters],
    queryFn: () => listWorkforceHrPeople({ ...filters, page, page_size: pageSize }),
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });

  const basesQuery = useQuery({
    queryKey: ["foundations", "base-stations", "active"],
    queryFn: () => listBaseStations({ include_inactive: false }),
    enabled: canManageContracts,
    staleTime: 15 * 60_000,
  });

  const data = peopleQuery.data;
  const people = data?.items || [];
  const total = data?.total || 0;
  const pages = data?.pages || 0;
  const currentPage = data?.page || page;

  useEffect(() => {
    setSelectedIds(new Set());
    setExcludedIds(new Set());
    setAllMatching(false);
  }, [filters]);

  const selection = useMemo<HrPeopleSelection>(() => {
    if (allMatching) {
      return {
        mode: "FILTERED",
        filters,
        exclude_user_ids: Array.from(excludedIds),
      };
    }
    return {
      mode: "EXPLICIT",
      user_ids: Array.from(selectedIds),
      exclude_user_ids: [],
      filters: {},
    };
  }, [allMatching, excludedIds, filters, selectedIds]);

  const selectionCount = allMatching
    ? Math.max(0, total - excludedIds.size)
    : selectedIds.size;

  const isSelected = (userId: string) => (
    allMatching ? !excludedIds.has(userId) : selectedIds.has(userId)
  );
  const selectedOnPage = people.filter((person) => isSelected(person.user_id)).length;
  const pageFullySelected = people.length > 0 && selectedOnPage === people.length;
  const pagePartlySelected = selectedOnPage > 0 && !pageFullySelected;

  const updateFilter = <K extends keyof HrPeopleFilters>(key: K, value: HrPeopleFilters[K]) => {
    setFilters((current) => ({ ...current, [key]: value || null }));
    setPage(1);
  };

  const togglePerson = (userId: string) => {
    if (allMatching) {
      setExcludedIds((current) => {
        const next = new Set(current);
        if (next.has(userId)) next.delete(userId);
        else next.add(userId);
        return next;
      });
      return;
    }
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };

  const togglePage = () => {
    const pageIds = people.map((person) => person.user_id);
    if (allMatching) {
      setExcludedIds((current) => {
        const next = new Set(current);
        pageIds.forEach((id) => {
          if (pageFullySelected) next.add(id);
          else next.delete(id);
        });
        return next;
      });
      return;
    }
    setSelectedIds((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => {
        if (pageFullySelected) next.delete(id);
        else next.add(id);
      });
      return next;
    });
  };

  const selectAllMatching = () => {
    setAllMatching(true);
    setSelectedIds(new Set());
    setExcludedIds(new Set());
  };

  const clearSelection = () => {
    setAllMatching(false);
    setSelectedIds(new Set());
    setExcludedIds(new Set());
  };

  const runAction = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const exportSelection = () => runAction("export", async () => {
    await exportWorkforceHrPeople(selection);
    setNotice(`Export prepared for ${selectionCount} selected employees.`);
  });

  const beginEdit = (person: HrPersonReadiness) => {
    setEditing(person);
    setDraft({
      contract_type: (person.contract_type || "PERMANENT") as ContractType,
      employment_status: (person.contract_id ? person.employment_status : "ACTIVE") as EmploymentStatus,
      effective_from: person.hire_date || person.contract_effective_from || isoDate(new Date()),
      effective_to: person.contract_effective_to || "",
      primary_base_station_id: person.primary_base_station_id || "",
      standard_weekly_hours: String((person.standard_weekly_minutes || 2400) / 60),
      standard_daily_hours: String((person.standard_daily_minutes || 480) / 60),
      fte_percentage: String(person.fte_percentage || 100),
      cost_centre: person.cost_centre || "",
      payroll_number: person.payroll_number || "",
      overtime_eligible: person.overtime_eligible,
      night_shift_eligible: person.night_shift_eligible,
      standby_eligible: person.standby_eligible,
    });
  };

  const closeEditor = () => {
    setEditing(null);
    setDraft(null);
  };

  const validDraft = Boolean(
    draft?.effective_from
    && draft.primary_base_station_id
    && Number(draft.standard_weekly_hours) >= 0
    && Number(draft.standard_daily_hours) >= 0
    && Number(draft.fte_percentage) > 0
    && Number(draft.fte_percentage) <= 100
    && (!draft.effective_to || draft.effective_to >= draft.effective_from)
  );

  const saveContract = () => {
    if (!editing || !draft || !validDraft) return;
    void runAction(`contract:${editing.user_id}`, async () => {
      const common = {
        contract_type: draft.contract_type,
        employment_status: draft.employment_status,
        effective_from: draft.effective_from,
        effective_to: draft.effective_to || null,
        primary_base_station_id: draft.primary_base_station_id,
        standard_weekly_minutes: Math.round(Number(draft.standard_weekly_hours) * 60),
        standard_daily_minutes: Math.round(Number(draft.standard_daily_hours) * 60),
        fte_percentage: Number(draft.fte_percentage),
        cost_centre: draft.cost_centre.trim() || null,
        payroll_number: draft.payroll_number.trim() || null,
        overtime_eligible: draft.overtime_eligible,
        night_shift_eligible: draft.night_shift_eligible,
        standby_eligible: draft.standby_eligible,
      };
      if (editing.contract_id) {
        await updateEmploymentContract(editing.contract_id, common);
      } else {
        await createEmploymentContract({ user_id: editing.user_id, ...common });
      }
      setNotice(`${editing.full_name}'s employment contract was saved.`);
      closeEditor();
      await queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] });
    });
  };

  const activeFilters = useMemo(() => filterLabels(filters, facetsQuery.data), [filters, facetsQuery.data]);

  return (
    <section className="wr-panel workforce-directory">
      <header className="workforce-directory__heading">
        <div>
          <span className="wr-eyebrow">People and employment readiness</span>
          <h2>Workforce directory</h2>
          <p>Server-side filters, bounded pages and controlled batch actions keep the register usable for large tenant workforces.</p>
        </div>
        <div className="workforce-directory__heading-actions">
          <button type="button" className="wr-button wr-button--secondary" onClick={() => setFiltersOpen((current) => !current)}>
            <SlidersHorizontal size={15} /> {filtersOpen ? "Hide filters" : "Show filters"}
          </button>
          <button type="button" className="wr-icon-button" aria-label="Refresh Workforce directory" onClick={() => void peopleQuery.refetch()}>
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}
      {notice ? <div className="workforce-directory__notice" role="status">{notice}</div> : null}

      <div className="workforce-directory__search-row">
        <label className="workforce-directory__search">
          <Search size={16} />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search name, staff code, email, title, department, base, payroll or group"
          />
          {searchInput ? <button type="button" aria-label="Clear search" onClick={() => setSearchInput("")}><X size={14} /></button> : null}
        </label>
        <span className="workforce-directory__result-count"><UsersRound size={15} /> {total.toLocaleString()} employees</span>
      </div>

      {filtersOpen ? (
        <div className="workforce-directory__filters" aria-label="Workforce directory filters">
          <FilterSelect label="Department" value={filters.department_id} options={facetsQuery.data?.departments} onChange={(value) => updateFilter("department_id", value)} />
          <FilterSelect label="Portal role" value={filters.role} options={facetsQuery.data?.roles} onChange={(value) => updateFilter("role", value)} />
          <FilterSelect label="Job title" value={filters.position_title} options={facetsQuery.data?.position_titles} onChange={(value) => updateFilter("position_title", value)} />
          <FilterSelect label="Contract type" value={filters.contract_type} options={facetsQuery.data?.contract_types} onChange={(value) => updateFilter("contract_type", value)} />
          <FilterSelect label="Employment status" value={filters.employment_status} options={facetsQuery.data?.employment_statuses} onChange={(value) => updateFilter("employment_status", value)} />
          <FilterSelect label="Primary base" value={filters.base_station_id} options={facetsQuery.data?.bases} onChange={(value) => updateFilter("base_station_id", value)} />
          <FilterSelect label="Group" value={filters.group_id} options={facetsQuery.data?.groups} onChange={(value) => updateFilter("group_id", value)} />
          <FilterSelect label="Readiness" value={filters.readiness_state} options={facetsQuery.data?.readiness_states} onChange={(value) => updateFilter("readiness_state", value as HrPeopleFilters["readiness_state"])} />
          <FilterSelect label="Contract record" value={filters.contract_state} options={facetsQuery.data?.contract_states} onChange={(value) => updateFilter("contract_state", value as HrPeopleFilters["contract_state"])} />
          <FilterSelect label="Work pattern" value={filters.pattern_state} options={facetsQuery.data?.pattern_states} onChange={(value) => updateFilter("pattern_state", value as HrPeopleFilters["pattern_state"])} />
          <label><span>Contract expiry</span><select value={filters.expires_within_days || ""} onChange={(event) => updateFilter("expires_within_days", event.target.value ? Number(event.target.value) : null)}><option value="">Any date</option><option value="30">Within 30 days</option><option value="60">Within 60 days</option><option value="90">Within 90 days</option><option value="180">Within 180 days</option></select></label>
          <label><span>Sort by</span><select value={filters.sort_by || "name"} onChange={(event) => updateFilter("sort_by", event.target.value as HrPeopleFilters["sort_by"])}><option value="name">Name</option><option value="staff_code">Staff code</option><option value="department">Department</option><option value="role">Portal role</option><option value="position_title">Job title</option></select></label>
          <label><span>Direction</span><select value={filters.sort_dir || "asc"} onChange={(event) => updateFilter("sort_dir", event.target.value as HrPeopleFilters["sort_dir"])}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
          <button type="button" className="wr-button wr-button--secondary workforce-directory__clear" disabled={!activeFilters.length && !searchInput} onClick={() => { setSearchInput(""); setFilters(EMPTY_FILTERS); setPage(1); }}><X size={14} /> Clear filters</button>
        </div>
      ) : null}

      {activeFilters.length ? (
        <div className="workforce-directory__chips">
          {activeFilters.map((filter) => <button key={filter.key} type="button" onClick={() => updateFilter(filter.key, null)}>{filter.label}<X size={12} /></button>)}
        </div>
      ) : null}

      {selectionCount > 0 ? (
        <div className="workforce-directory__batch-bar">
          <strong>{selectionCount.toLocaleString()} selected</strong>
          {!allMatching && selectionCount < total ? <button type="button" className="workforce-directory__link" onClick={selectAllMatching}>Select all {total.toLocaleString()} matching employees</button> : null}
          {allMatching ? <span>All matching filters selected{excludedIds.size ? ` · ${excludedIds.size} excluded` : ""}</span> : null}
          <div className="workforce-directory__batch-actions">
            <button type="button" className="wr-button wr-button--secondary" disabled={Boolean(busy)} onClick={() => void exportSelection()}><Download size={14} /> Export CSV</button>
            <button type="button" className="wr-button wr-button--secondary" onClick={clearSelection}>Clear selection</button>
          </div>
        </div>
      ) : null}

      <div className="workforce-directory__table-shell" aria-busy={peopleQuery.isFetching}>
        <table className="workforce-directory__table">
          <thead>
            <tr>
              <th className="is-checkbox"><SelectionCheckbox checked={pageFullySelected} indeterminate={pagePartlySelected} label="Select current page" onChange={togglePage} /></th>
              <th>Employee</th>
              <th>Organization</th>
              <th>Contract</th>
              <th>Base</th>
              <th>Work pattern</th>
              <th>Readiness</th>
              <th className="is-actions">Action</th>
            </tr>
          </thead>
          <tbody>
            {people.map((person) => (
              <tr key={person.user_id} className={isSelected(person.user_id) ? "is-selected" : ""}>
                <td className="is-checkbox"><input type="checkbox" aria-label={`Select ${person.full_name}`} checked={isSelected(person.user_id)} onChange={() => togglePerson(person.user_id)} /></td>
                <td><strong>{person.full_name}</strong><span>{person.staff_code} · {person.email || "No email"}</span></td>
                <td><strong>{person.position_title || formatValue(person.account_role) || "No position"}</strong><span>{person.department_name || person.department_code || "No department"}</span>{person.group_names.length ? <small>{person.group_names.slice(0, 2).join(" · ")}{person.group_names.length > 2 ? ` +${person.group_names.length - 2}` : ""}</small> : null}</td>
                <td><strong>{formatValue(person.employment_status) || "No contract"}</strong><span>{formatValue(person.contract_type) || "—"}</span><small>{contractDateLabel(person)}</small></td>
                <td><strong>{person.primary_base_code || "Missing"}</strong><span>{person.supervisor_name || "No supervisor"}</span></td>
                <td><strong>{person.work_pattern_code || "Unassigned"}</strong><span>{person.work_pattern_name || "No active pattern"}</span><small>{formatValue(person.pattern_state)}</small></td>
                <td><StatusPill value={person.readiness_state} />{person.readiness_reasons.slice(0, 2).map((reason) => <small key={reason}>{reason}</small>)}</td>
                <td className="is-actions">{canManageContracts ? <button type="button" className="wr-button wr-button--small" onClick={() => beginEdit(person)}>{person.contract_id ? "Edit" : "Create"}</button> : <span>Read only</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {peopleQuery.isPending ? <RosterLoading label="Loading Workforce directory…" /> : null}
        {!people.length && !peopleQuery.isPending ? <EmptyState title="No employees match these filters" description="Clear one or more filters or change the search terms." /> : null}
      </div>

      <footer className="workforce-directory__pagination">
        <div><span>Rows per page</span><select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value) as (typeof PAGE_SIZES)[number]); setPage(1); }}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select><span>{total ? `${((currentPage - 1) * pageSize + 1).toLocaleString()}–${Math.min(currentPage * pageSize, total).toLocaleString()} of ${total.toLocaleString()}` : "0 results"}</span></div>
        <div><button type="button" className="wr-icon-button" aria-label="First page" disabled={currentPage <= 1 || peopleQuery.isFetching} onClick={() => setPage(1)}><ChevronsLeft size={16} /></button><button type="button" className="wr-icon-button" aria-label="Previous page" disabled={currentPage <= 1 || peopleQuery.isFetching} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} /></button><span>Page <strong>{currentPage}</strong> of <strong>{pages || 1}</strong></span><button type="button" className="wr-icon-button" aria-label="Next page" disabled={!pages || currentPage >= pages || peopleQuery.isFetching} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} /></button><button type="button" className="wr-icon-button" aria-label="Last page" disabled={!pages || currentPage >= pages || peopleQuery.isFetching} onClick={() => setPage(pages)}><ChevronsRight size={16} /></button></div>
      </footer>

      {editing && draft ? <ContractEditor person={editing} draft={draft} setDraft={setDraft} bases={basesQuery.data || []} loadingBases={basesQuery.isPending} valid={validDraft} busy={Boolean(busy)} onClose={closeEditor} onSave={saveContract} /> : null}
    </section>
  );
}

function SelectionCheckbox({ checked, indeterminate, label, onChange }: { checked: boolean; indeterminate: boolean; label: string; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked} onChange={onChange} />;
}

function FilterSelect({ label, value, options, onChange }: { label: string; value?: string | null; options?: HrFilterOption[]; onChange: (value: string | null) => void }) {
  return <label><span>{label}</span><select value={value || ""} onChange={(event) => onChange(event.target.value || null)}><option value="">All</option>{(options || []).map((option) => <option key={option.value} value={option.value}>{option.label} ({option.count})</option>)}</select></label>;
}

function filterLabels(filters: HrPeopleFilters, facets?: Awaited<ReturnType<typeof getWorkforceHrPeopleFacets>>) {
  const definitions: Array<{ key: keyof HrPeopleFilters; label: string; options?: HrFilterOption[] }> = [
    { key: "department_id", label: "Department", options: facets?.departments },
    { key: "role", label: "Role", options: facets?.roles },
    { key: "position_title", label: "Job title", options: facets?.position_titles },
    { key: "contract_type", label: "Contract", options: facets?.contract_types },
    { key: "employment_status", label: "Status", options: facets?.employment_statuses },
    { key: "base_station_id", label: "Base", options: facets?.bases },
    { key: "group_id", label: "Group", options: facets?.groups },
    { key: "readiness_state", label: "Readiness", options: facets?.readiness_states },
    { key: "contract_state", label: "Contract record", options: facets?.contract_states },
    { key: "pattern_state", label: "Pattern", options: facets?.pattern_states },
  ];
  const result: Array<{ key: keyof HrPeopleFilters; label: string }> = [];
  definitions.forEach(({ key, label, options }) => {
    const value = filters[key];
    if (!value) return;
    const display = options?.find((option) => option.value === String(value))?.label || formatValue(String(value));
    result.push({ key, label: `${label}: ${display}` });
  });
  if (filters.expires_within_days) result.push({ key: "expires_within_days", label: `Expires within ${filters.expires_within_days} days` });
  return result;
}

function ContractEditor({ person, draft, setDraft, bases, loadingBases, valid, busy, onClose, onSave }: { person: HrPersonReadiness; draft: ContractDraft; setDraft: (draft: ContractDraft) => void; bases: BaseStationRead[]; loadingBases: boolean; valid: boolean; busy: boolean; onClose: () => void; onSave: () => void }) {
  const update = <K extends keyof ContractDraft>(key: K, value: ContractDraft[K]) => setDraft({ ...draft, [key]: value });
  return <div className="workforce-directory__dialog workforce-directory__contract" role="dialog" aria-modal="true" aria-label={`Employment contract for ${person.full_name}`}><header><div><span className="wr-eyebrow">Effective-dated Workforce record</span><h3>{person.full_name}</h3><p>{person.staff_code} · {person.position_title || formatValue(person.account_role)}</p></div><button type="button" className="wr-icon-button" aria-label="Close contract editor" onClick={onClose}><X size={16} /></button></header><div className="workforce-directory__contract-grid"><label><span>Contract type</span><select value={draft.contract_type} onChange={(event) => update("contract_type", event.target.value as ContractType)}>{["PERMANENT", "FIXED_TERM", "TEMPORARY", "CONTRACTOR", "INTERN"].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Employment status</span><select value={draft.employment_status} onChange={(event) => update("employment_status", event.target.value as EmploymentStatus)}>{["ONBOARDING", "ACTIVE", "SUSPENDED", "TERMINATED"].map((value) => <option key={value}>{value}</option>)}</select></label><label className={person.hire_date ? "wr-locked-field" : undefined}><span>Workforce start</span><input type="date" value={draft.effective_from} disabled={Boolean(person.hire_date)} onChange={(event) => update("effective_from", event.target.value)} />{person.hire_date ? <small>Imported hire date · re-import the personnel source to correct it.</small> : null}</label><label><span>Effective to</span><input type="date" min={draft.effective_from} value={draft.effective_to} onChange={(event) => update("effective_to", event.target.value)} /></label><label><span>Primary base</span><select value={draft.primary_base_station_id} disabled={loadingBases} onChange={(event) => update("primary_base_station_id", event.target.value)}><option value="">Select canonical base</option>{bases.map((base) => <option key={base.id} value={base.id}>{base.code} · {base.name}</option>)}</select></label><label><span>FTE percentage</span><input type="number" min="1" max="100" step="0.1" value={draft.fte_percentage} onChange={(event) => update("fte_percentage", event.target.value)} /></label><label><span>Weekly hours</span><input type="number" min="0" step="0.25" value={draft.standard_weekly_hours} onChange={(event) => update("standard_weekly_hours", event.target.value)} /></label><label><span>Daily hours</span><input type="number" min="0" step="0.25" value={draft.standard_daily_hours} onChange={(event) => update("standard_daily_hours", event.target.value)} /></label><label><span>Payroll number</span><input value={draft.payroll_number} onChange={(event) => update("payroll_number", event.target.value)} /></label><label><span>Cost centre</span><input value={draft.cost_centre} onChange={(event) => update("cost_centre", event.target.value)} /></label></div><div className="workforce-directory__flags">{(["overtime_eligible", "night_shift_eligible", "standby_eligible"] as const).map((key) => <label key={key}><input type="checkbox" checked={draft[key]} onChange={(event: ChangeEvent<HTMLInputElement>) => update(key, event.target.checked)} /><span>{key === "overtime_eligible" ? "Overtime eligible" : key === "night_shift_eligible" ? "Night duty eligible" : "Standby eligible"}</span></label>)}</div>{!loadingBases && !bases.length ? <div className="wr-inline-error">No active canonical base exists. Create one before saving this contract.</div> : null}<div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={onClose}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={busy || !valid} onClick={onSave}><Save size={15} /> {person.contract_id ? "Save contract" : "Create contract"}</button></div></div>;
}

function contractDateLabel(person: HrPersonReadiness): string {
  if (person.contract_state === "MISSING") return "No effective or future record";
  if (person.contract_state === "FUTURE") return `Starts ${person.contract_effective_from || "later"}`;
  return person.contract_effective_to ? `Ends ${person.contract_effective_to}` : `From ${person.contract_effective_from || "current"}`;
}

function formatValue(value?: string | null): string {
  return String(value || "").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}
