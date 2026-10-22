import InlineLoading from "../../components/shared/InlineLoading";
import React, { useEffect, useState } from "react";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { listEngineTrendStatuses, type EngineTrend } from "../../services/reliability";
import "./ReliabilityEngineSpotlight.css";

function display(value?: string | null): string { return value || "Not recorded"; }

export default function ReliabilityEngineSpotlight(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const root = "/maintenance/" + encodeURIComponent(amoCode) + "/reliability";
  const [records, setRecords] = useState<EngineTrend[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    void listEngineTrendStatuses({ limit: 13, offset: 0 }).then((result) => {
      if (active) { setRecords(result.slice(0, 12)); setHasMore(result.length > 12); setLoading(false); setError(""); }
    }).catch((cause: unknown) => {
      if (active) { setError(cause instanceof Error ? cause.message : "Engine status unavailable"); setLoading(false); }
    });
    return () => { active = false; };
  }, [reload]);

  return <section className="rel-engine-spotlight" aria-label="Engine technical status register">
    <div className="rel-engine-spotlight__head">
      <div><p className="reliability-v2__eyebrow">Engine identification and condition</p>
        <h2>Current fleet engine statuses</h2>
        <p>Source-derived status and review dates. The chart above may cover a different measured period.</p></div>
      <div><button type="button" disabled={loading} onClick={() => { setLoading(true); setReload((x) => x + 1); }}>
        <RefreshCw size={15} aria-hidden="true" /> Refresh</button>
      <Link to={root + "/engines"}>Full engine register <ArrowUpRight size={15} aria-hidden="true" /></Link></div>
    </div>
    {loading && <p><InlineLoading label={"Loading engine status…"}/></p>}
    {error && <p role="alert">Engine status could not be retrieved: {error}</p>}
    {!loading && !error && <div className="rel-engine-spotlight__viewport" role="region" tabIndex={0} aria-label="Scrollable engine status table">
      <table><thead><tr><th>Aircraft</th><th>Engine position</th><th>Physical engine serial</th>
        <th>Condition</th><th>Previous condition</th><th>Last upload</th><th>Last reviewed</th></tr></thead>
        <tbody>{records.map((row) => <tr key={row.id}>
          <td>{row.aircraft_serial_number}</td><td>{row.engine_position}</td>
          <td>{display(row.engine_serial_number)}</td>
          <td><span className={row.current_status === "Trend Shift" ? "rel-engine-spotlight__watch" : "rel-engine-spotlight__neutral"}>
            {display(row.current_status)}</span></td>
          <td>{display(row.previous_status)}</td><td>{display(row.last_upload_date)}</td><td>{display(row.last_review_date)}</td>
        </tr>)}</tbody></table>
      {!records.length && <p>No engine trend-status records were returned. Do not infer normal conditions.</p>}
      {hasMore && <p className="rel-engine-spotlight__hint">Showing first 12 source records. Open the full register to browse additional engines.</p>}
    </div>}
  </section>;
}
