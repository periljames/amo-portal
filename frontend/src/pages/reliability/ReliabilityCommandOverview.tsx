import InlineLoading from "../../components/shared/InlineLoading";
import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock3, Database, ExternalLink, RefreshCw, ShieldAlert } from "lucide-react";
import { getReliabilityWorkbench, type ReliabilityWorkbench } from "../../services/reliability";
import "./ReliabilityCommandOverview.css";

function when(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function ReliabilityCommandOverview(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const root = "/maintenance/" + encodeURIComponent(amoCode) + "/reliability";
  const [data, setData] = useState<ReliabilityWorkbench | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let current = true;
    void getReliabilityWorkbench(10).then((result) => {
      if (current) { setData(result); setLoading(false); setError(""); }
    }).catch((cause: unknown) => {
      if (current) { setError(cause instanceof Error ? cause.message : "Operational summary unavailable"); setLoading(false); }
    });
    return () => { current = false; };
  }, [reload]);

  return <section className="rel-command" aria-label="Operational reliability priorities">
    <div className="rel-command__heading">
      <div><p className="reliability-v2__eyebrow">Live operational evidence</p><h2>What needs attention now</h2>
        <p>Actual source records and case queues, independently of analytical calculation results.</p></div>
      <button type="button" className="rel-command__refresh" onClick={() => {
        setLoading(true); setReload((v) => v + 1);
      }} disabled={loading}><RefreshCw size={15} aria-hidden="true" /> Refresh sources</button>
    </div>
    {loading && <p><InlineLoading label={"Loading operational priorities and source freshness…"}/></p>}
    {error && <div role="alert" className="rel-command__error">
      <ShieldAlert size={17} aria-hidden="true" /> Operational source data unavailable: {error}.
      Dashboard calculations do not replace operational source verification.
    </div>}
    {!loading && data && <>
      <div className="rel-command__metrics" aria-label="Current operational counts">
        {([
          ["Critical alerts", data.counts.critical_alerts, "alerts"],
          ["Open alerts", data.counts.open_alerts, "alerts"],
          ["Active FRACAS", data.counts.active_cases, "cases"],
          ["Overdue actions", data.counts.overdue_actions, "cases"],
          ["Engine shifts", data.counts.engine_shifts, "engines"],
          ["Data issues", data.counts.data_quality_issues, "data-quality"],
        ] as const).map(([label, count, path]) =>
          <Link key={label} to={root + "/" + path} className="rel-command__metric">
            <span>{label}</span><strong>{count}</strong><ArrowUpRight size={15} aria-hidden="true" /></Link>)}
      </div>
      <div className="rel-command__split">
        <section className="rel-command__panel">
          <div className="rel-command__panel-head"><h3><AlertTriangle size={17} aria-hidden="true" /> Priority queue</h3>
            <span>{data.priorities.length} shown</span></div>
          {data.priorities.length ? <div className="rel-command__scroll">
            {data.priorities.map((priority, index) =>
              <Link className="rel-command__priority" key={priority.kind + "-" + (priority.entity_id ?? index)}
                to={root + "/" + priority.relative_path}>
                <span className="rel-command__severity">{priority.severity}</span>
                <span><strong>{priority.title}</strong><small>{priority.summary || priority.kind.replaceAll("_", " ")}</small></span>
                <ArrowUpRight size={15} aria-hidden="true" />
              </Link>)}
          </div> : <p className="rel-command__empty"><CheckCircle2 size={15} aria-hidden="true" />
            No priorities were triggered in the loaded source data. Check source freshness before treating this as a clear fleet.</p>}
        </section>
        <section className="rel-command__panel">
          <div className="rel-command__panel-head"><h3><Database size={17} aria-hidden="true" /> Source confidence</h3>
            <Link to={root + "/data-quality"}>Review data quality <ExternalLink size={13} aria-hidden="true" /></Link></div>
          <div className="rel-command__scroll"><table className="rel-command__table">
            <thead><tr><th>Source</th><th>State</th><th>Last record</th><th>Issues</th></tr></thead>
            <tbody>{data.data_freshness.map((source) =>
              <tr key={source.source}><td title={source.detail ?? undefined}>{source.source}</td>
                <td><span className={"rel-command__state rel-command__state--" + source.status.toLowerCase()}>{source.status}</span></td>
                <td>{source.latest_record_at ? when(source.latest_record_at) : "Unavailable"}</td>
                <td>{source.issue_count}</td></tr>)}</tbody>
          </table>{!data.data_freshness.length && <p className="rel-command__empty">No source-freshness evidence available.</p>}</div>
        </section>
      </div>
      <div className="rel-command__split">
        <section className="rel-command__panel">
          <div className="rel-command__panel-head"><h3><Clock3 size={16} aria-hidden="true" /> Recent occurrences</h3>
            <Link to={root + "/events"}>Open register <ArrowUpRight size={13} aria-hidden="true" /></Link></div>
          <div className="rel-command__scroll"><table className="rel-command__table"><thead><tr><th>Recorded</th><th>Aircraft</th><th>Event</th><th>ATA</th></tr></thead>
            <tbody>{data.recent_events.map((item) => <tr key={item.id}><td><Link to={root + "/events/" + item.id}>{when(item.occurred_at)}</Link></td>
              <td>{item.aircraft_serial_number || "Fleet"}</td><td>{item.event_type}</td><td>{item.ata_chapter || "—"}</td></tr>)}</tbody>
          </table>{!data.recent_events.length && <p className="rel-command__empty">No recent records in the source response.</p>}</div>
        </section>
        <section className="rel-command__panel">
          <div className="rel-command__panel-head"><h3><ShieldAlert size={17} aria-hidden="true" /> Active investigations</h3>
            <Link to={root + "/cases"}>Open cases <ArrowUpRight size={13} aria-hidden="true" /></Link></div>
          <div className="rel-command__scroll"><table className="rel-command__table"><thead><tr><th>Case</th><th>Aircraft</th><th>Status</th></tr></thead>
            <tbody>{data.active_cases.map((item) => <tr key={item.id}>
              <td><Link to={root + "/cases/" + item.id}>{item.title}</Link></td><td>{item.aircraft_serial_number || "Fleet"}</td>
              <td>{item.status.replaceAll("_", " ")}</td></tr>)}</tbody>
          </table>{!data.active_cases.length && <p className="rel-command__empty">No active cases in the source response.</p>}</div>
        </section>
      </div>
      <p className="rel-command__provenance">Operational summary generated {when(data.generated_at)}.
        These values reflect the accessible records, not an assurance of complete upstream ingestion.</p>
    </>}
  </section>;
}
