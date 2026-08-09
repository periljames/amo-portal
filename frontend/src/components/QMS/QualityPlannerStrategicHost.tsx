import React, { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Building2, CalendarRange, Factory, PanelRightClose, PanelRightOpen, RefreshCw, ShieldCheck, Users } from "lucide-react";

import { getQmsPlannerStrategicView } from "../../services/qmsPlannerStrategic";
import "../../styles/qms-planner-strategic.css";

type Props = { amoCode: string };
type View = "year" | "quarter" | "workload" | "coverage";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const QualityPlannerStrategicHost: React.FC<Props> = ({ amoCode }) => {
  const location = useLocation();
  const isPlannerRoute = /\/(?:quality|qms)\/(?:calendar|planner)(?:\/|$)/i.test(location.pathname);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("year");
  const [year, setYear] = useState(new Date().getFullYear());
  const query = useQuery({
    queryKey: ["qms-planner-strategic", amoCode, year],
    queryFn: ({ signal }) => getQmsPlannerStrategicView(amoCode, year, signal),
    enabled: isPlannerRoute && open,
  });
  const data = query.data;
  const maxMonth = useMemo(() => Math.max(1, ...(data?.months.map((row) => row.schedule_count) || [1])), [data]);

  if (!isPlannerRoute) return null;

  return <>
    <button className="qms-planner-strategic-launcher" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="qms-planner-strategic-panel">
      {open ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />} Strategic Planner
    </button>
    {open ? <aside id="qms-planner-strategic-panel" className="qms-planner-strategic-panel" aria-label="Strategic Quality Planner">
      <header>
        <div><span>Strategic planning</span><strong>Year · Quarter · Coverage</strong></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close strategic Planner"><PanelRightClose size={18} /></button>
      </header>
      <div className="qms-planner-strategic-toolbar">
        <button type="button" onClick={() => setYear((value) => value - 1)}>←</button>
        <strong>{year}</strong>
        <button type="button" onClick={() => setYear((value) => value + 1)}>→</button>
        <button type="button" onClick={() => void query.refetch()} disabled={query.isFetching}><RefreshCw size={15} /> Refresh</button>
      </div>
      <nav aria-label="Strategic Planner views">
        <button type="button" className={view === "year" ? "is-active" : ""} onClick={() => setView("year")}><CalendarRange size={15} /> Year</button>
        <button type="button" className={view === "quarter" ? "is-active" : ""} onClick={() => setView("quarter")}><CalendarRange size={15} /> Quarter</button>
        <button type="button" className={view === "workload" ? "is-active" : ""} onClick={() => setView("workload")}><Users size={15} /> Workload</button>
        <button type="button" className={view === "coverage" ? "is-active" : ""} onClick={() => setView("coverage")}><Building2 size={15} /> Coverage</button>
      </nav>
      <div className="qms-planner-strategic-body">
        {query.isLoading ? <p>Loading authoritative Planner coverage…</p> : query.error ? <p role="alert">{query.error instanceof Error ? query.error.message : "Strategic Planner could not be loaded."}</p> : null}
        {data && view === "year" ? <>
          <section className="qms-planner-strategic-summary"><strong>{data.schedule_count}</strong><span>authoritative audit schedules in {year}</span><small>{data.timezone_name}</small></section>
          <div className="qms-planner-strategic-months">{data.months.map((row) => <article key={row.month}><strong>{MONTHS[row.month - 1]}</strong><div><span style={{ height: `${Math.max(6, (row.schedule_count / maxMonth) * 100)}%` }} /></div><small>{row.schedule_count}</small></article>)}</div>
          <section className="qms-planner-strategic-card"><header><ShieldCheck size={17} /><strong>Lifecycle states</strong></header><dl>{Object.entries(data.lifecycle_states).map(([state, count]) => <div key={state}><dt>{state}</dt><dd>{count}</dd></div>)}</dl></section>
        </> : null}
        {data && view === "quarter" ? <div className="qms-planner-strategic-quarters">{data.quarters.map((row) => <article key={row.quarter}><span>Quarter {row.quarter}</span><strong>{row.schedule_count}</strong><small>scheduled audit occurrence(s)</small></article>)}</div> : null}
        {data && view === "workload" ? <section className="qms-planner-strategic-card"><header><Users size={17} /><strong>Auditor workload</strong></header><div className="qms-planner-strategic-table"><table><thead><tr><th>Auditor</th><th>Department</th><th>Audit slots</th></tr></thead><tbody>{data.auditor_workload.length ? data.auditor_workload.map((row) => <tr key={row.user_id}><td>{row.name}</td><td>{row.department}</td><td>{row.schedule_count}</td></tr>) : <tr><td colSpan={3}>No assigned auditor workload in this year.</td></tr>}</tbody></table></div></section> : null}
        {data && view === "coverage" ? <>
          <section className="qms-planner-strategic-card"><header><Building2 size={17} /><strong>Department coverage</strong></header><dl>{data.department_coverage.map((row) => <div key={row.department}><dt>{row.department}</dt><dd>{row.assigned_audit_slots}</dd></div>)}</dl>{data.data_quality.unresolved_department_assignments ? <p>{data.data_quality.unresolved_department_assignments} assignment(s) have unresolved department data.</p> : null}</section>
          <section className="qms-planner-strategic-card"><header><Factory size={17} /><strong>Facility / location coverage</strong></header><dl>{data.location_coverage.map((row) => <div key={row.location}><dt>{row.location}</dt><dd>{row.schedule_count}</dd></div>)}</dl></section>
          <section className="qms-planner-strategic-card"><header><ShieldCheck size={17} /><strong>Supplier surveillance</strong></header><ul>{data.supplier_surveillance.length ? data.supplier_surveillance.map((row) => <li key={row.id}><strong>{row.label}</strong><span>{row.risk_classification} risk · {row.programme_states.join(", ") || "not yet in programme"}</span>{row.source_route ? <a href={row.source_route}>Open source</a> : null}</li>) : <li>No supplier Audit Universe items are configured.</li>}</ul></section>
          <section className="qms-planner-strategic-card"><header><ShieldCheck size={17} /><strong>Regulatory commitments</strong></header><ul>{data.regulatory_commitments.length ? data.regulatory_commitments.map((row) => <li key={row.id}><strong>{row.label}</strong><span>{row.mandatory_surveillance ? "Mandatory" : row.regulatory_criticality} · {row.programme_states.join(", ") || "not yet in programme"}</span>{row.source_route ? <a href={row.source_route}>Open source</a> : null}</li>) : <li>No regulatory/mandatory Audit Universe items are configured.</li>}</ul></section>
        </> : null}
      </div>
    </aside> : null}
  </>;
};

export default QualityPlannerStrategicHost;
