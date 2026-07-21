import { useCallback, useEffect, useMemo, useState } from "react";
import { addDays } from "date-fns";
import {
  AlertTriangle,
  ArrowRight,
  BriefcaseBusiness,
  CalendarRange,
  Filter,
  RefreshCw,
  ShieldCheck,
  UsersRound,
  Wrench,
} from "lucide-react";

import { getPlanningBoard } from "../../../services/rostering";
import type { RosterPlanningBoardResponse } from "../../../types/rostering";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, MetricCard, RosterError, RosterLoading, StatusPill } from "./RosterShell";

function initialRange() {
  const from = new Date();
  const to = addDays(from, 13);
  return { from: isoDate(from), to: isoDate(to) };
}

export function CapacityBoard() {
  const [range, setRange] = useState(initialRange);
  const [data, setData] = useState<RosterPlanningBoardResponse | null>(null);
  const [base, setBase] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskSearch, setTaskSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getPlanningBoard({ from: range.from, to: range.to, base_station_id: base || null }));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [base, range.from, range.to]);

  useEffect(() => { void load(); }, [load]);

  const bases = useMemo(() => data?.base_capacity || [], [data]);
  const tasks = useMemo(() => {
    const term = taskSearch.trim().toLowerCase();
    return (data?.tasks || []).filter((task) => !term || `${task.wo_number} ${task.task_code || ""} ${task.title} ${task.aircraft_registration || ""}`.toLowerCase().includes(term));
  }, [data, taskSearch]);

  if (loading && !data) return <RosterLoading label="Loading manpower capacity…" />;
  if (error && !data) return <RosterError message={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="wr-capacity">
      <section className="wr-filter-bar">
        <label><span>From</span><input type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} /></label>
        <label><span>To</span><input type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} /></label>
        <label><span>Base</span><select value={base} onChange={(event) => setBase(event.target.value)}><option value="">All bases</option>{bases.map((row) => <option key={row.base_station_id || row.base_code} value={row.base_station_id || ""}>{row.base_code} · {row.base_name}</option>)}</select></label>
        <button type="button" className="wr-button wr-button--secondary" onClick={load}><RefreshCw size={16} className={loading ? "is-spinning" : ""} /> Refresh</button>
      </section>

      <section className="wr-metric-grid">
        <MetricCard label="Rostered people" value={data.metrics.assigned_people} detail={`${data.metrics.productive_assignment_count} productive duties`} tone="info" />
        <MetricCard label="Available capacity" value={`${data.metrics.available_duty_hours.toFixed(1)}h`} detail={`${data.metrics.standby_hours.toFixed(1)}h standby`} tone="good" />
        <MetricCard label="Maintenance demand" value={`${data.metrics.required_task_hours.toFixed(1)}h`} detail={`${data.metrics.task_count} open tasks`} tone="neutral" />
        <MetricCard label="Capacity variance" value={`${data.metrics.capacity_variance_hours.toFixed(1)}h`} detail="Capacity minus demand" tone={data.metrics.capacity_variance_hours < 0 ? "danger" : "good"} />
        <MetricCard label="Unallocated tasks" value={data.metrics.unallocated_task_count} detail={`${data.metrics.missing_estimate_count} without estimates`} tone={data.metrics.unallocated_task_count ? "warning" : "good"} />
        <MetricCard label="Validation" value={`${data.metrics.blocker_count}/${data.metrics.warning_count}`} detail="Blockers / warnings" tone={data.metrics.blocker_count ? "danger" : data.metrics.warning_count ? "warning" : "good"} />
      </section>

      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Base control</span><h2>Capacity by operating base</h2></div><span className="wr-range-label"><CalendarRange size={15} /> {range.from} → {range.to}</span></div>
        {bases.length === 0 ? <EmptyState title="No published capacity" description="Publish a roster version covering this range to expose manpower capacity." /> : (
          <div className="wr-capacity-grid">
            {bases.map((row) => {
              const utilisation = row.available_hours > 0 ? Math.min((row.roster_linked_hours / row.available_hours) * 100, 100) : 0;
              return (
                <article className={`wr-capacity-card${row.capacity_gap_hours > 0 || row.headcount_gap > 0 ? " has-gap" : ""}`} key={row.base_station_id || row.base_code}>
                  <div className="wr-capacity-card__head"><div><strong>{row.base_code}</strong><span>{row.base_name}</span></div><StatusPill value={row.capacity_gap_hours > 0 ? "GAP" : "COVERED"} tone={row.capacity_gap_hours > 0 ? "blocker" : "published"} /></div>
                  <div className="wr-capacity-card__numbers"><span><UsersRound size={15} /><b>{row.assigned_people}</b> people</span><span><ShieldCheck size={15} /><b>{row.certifying_people}</b> certifying</span><span><Wrench size={15} /><b>{row.technician_people}</b> technicians</span></div>
                  <div className="wr-progress" aria-label={`${utilisation.toFixed(0)} percent of available roster hours allocated`}><span style={{ width: `${utilisation}%` }} /></div>
                  <div className="wr-capacity-card__facts"><span>Available <b>{row.available_hours.toFixed(1)}h</b></span><span>Linked <b>{row.roster_linked_hours.toFixed(1)}h</b></span><span>Demand <b>{row.required_task_hours.toFixed(1)}h</b></span><span>Gap <b>{row.capacity_gap_hours.toFixed(1)}h</b></span></div>
                  {row.headcount_gap > 0 ? <div className="wr-inline-warning"><AlertTriangle size={14} /> {row.headcount_gap} more person{row.headcount_gap === 1 ? "" : "s"} required</div> : null}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <div className="wr-two-column">
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Maintenance load</span><h2>Open work orders</h2></div><BriefcaseBusiness size={20} /></div>
          {data.work_orders.length === 0 ? <EmptyState title="No work orders in range" description="No open task demand matched the selected horizon and base." /> : (
            <div className="wr-data-list">
              {data.work_orders.map((row) => (
                <article key={row.work_order_id} className="wr-data-row">
                  <div><strong>{row.wo_number}</strong><small>{row.aircraft_registration || row.aircraft_serial_number} · {row.check_type || "Maintenance"}</small></div>
                  <span>{row.open_task_count} tasks</span>
                  <span>{row.remaining_manhours.toFixed(1)}h remaining</span>
                  <StatusPill value={row.status} />
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Allocation queue</span><h2>Task demand</h2></div><label className="wr-search wr-search--small"><Filter size={14} /><input value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} placeholder="Filter tasks" /></label></div>
          {tasks.length === 0 ? <EmptyState title="No task demand" description="No matching open tasks require allocation." /> : (
            <div className="wr-data-list wr-data-list--dense">
              {tasks.slice(0, 120).map((row) => (
                <article key={row.task_id} className="wr-data-row">
                  <div><strong>{row.task_code || `Task ${row.task_id}`}</strong><small>{row.wo_number} · {row.title}</small></div>
                  <span>{row.remaining_manhours.toFixed(1)}h</span>
                  <StatusPill value={row.roster_link_count ? "LINKED" : "UNALLOCATED"} tone={row.roster_link_count ? "published" : "warning"} />
                  <button className="wr-icon-button" type="button" title="Allocate from the planner assignment drawer"><ArrowRight size={16} /></button>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
