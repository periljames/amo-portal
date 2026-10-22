import { useEffect, useState } from "react";
import { listCarRcaParetoSnapshots, saveCarRcaParetoSnapshot, type CarRcaParetoSnapshot } from "../../../services/qmsCarRca";
import "./car-rca.css";

type Group = "severity" | "finding_type" | "requirement";
const today = () => new Date().toISOString().slice(0, 10);

export default function CarRcaParetoSource({ amoCode, carId, canSave }: {
  amoCode: string; carId: string; canSave: boolean;
}) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState(today);
  const [group, setGroup] = useState<Group>("requirement");
  const [items, setItems] = useState<CarRcaParetoSnapshot[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = async () => {
    const data = await listCarRcaParetoSnapshots(amoCode, carId);
    setItems(data);
    setSelectedId(id => id || data[0]?.id || "");
  };
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    void listCarRcaParetoSnapshots(amoCode, carId).then(data => {
      if (active) { setItems(data); setSelectedId(data[0]?.id || ""); }
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : "Pareto source unavailable"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [amoCode, carId]);
  const selected = items.find(x => x.id === selectedId) || null;
  const save = async () => {
    if (!start || end < start || saving) return;
    setSaving(true); setError(null);
    try {
      const record = await saveCarRcaParetoSnapshot(amoCode, carId, { start, end, group_by: group });
      await load(); setSelectedId(record.id);
    } catch(e) { setError(e instanceof Error ? e.message : "Source analysis failed."); }
    finally { setSaving(false); }
  };
  return <section className="car-rca" aria-label="Source-backed QMS Pareto">
    <header className="car-rca-heading"><div><h4>Verified QMS source frequencies</h4>
      <p>Full-population counts from tenant audit findings in non-deleted audits, by UTC creation date. Only an authorized Quality user can generate or retain these snapshots.</p>
    </div></header>
    {canSave && <div className="car-rca-grid">
      <label>Period from<input type="date" value={start} max={end} disabled={saving} onChange={e => setStart(e.target.value)} /></label>
      <label>Period to<input type="date" value={end} min={start} disabled={saving} onChange={e => setEnd(e.target.value)} /></label>
      <label>Group by<select value={group} disabled={saving} onChange={e => setGroup(e.target.value as Group)}>
        <option value="requirement">Requirement</option><option value="finding_type">Finding type</option><option value="severity">Severity</option>
      </select></label>
      <button type="button" disabled={saving || !start || !end || end < start}
        onClick={() => void save()}>{saving ? "Calculating…" : "Calculate and retain source snapshot"}</button>
    </div>}
    {loading && <p role="status">Loading Pareto snapshots…</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => void load().catch(e => setError(String(e)))}>Retry</button></p>}
    {!loading && !items.length && <p>No authenticated QMS source snapshot has been retained for this CAR.</p>}
    {items.length > 0 && <label className="car-rca-field">Retained snapshot
      <select value={selectedId} onChange={e => setSelectedId(e.target.value)}>
        {items.map(x => <option key={x.id} value={x.id}>{x.created_at.slice(0,16)} · {x.filters.group_by} · {x.sample_size} findings</option>)}
      </select></label>}
    {selected && <div className="car-rca-analysis">
      <p className="car-rca-note">
        Source cohort: {selected.filters.start} to {selected.filters.end} (UTC).
        Total: {selected.sample_size}; retained source IDs: {selected.source_reference_count}.
        {selected.source_references_truncated && " Source IDs limited to 100; frequencies cover the complete cohort."}
        {selected.sample_size < 5 && " Small cohort — use caution interpreting frequencies."}
      </p>
      {selected.categories.length > 0 && <svg className="car-rca-pareto" viewBox="0 0 720 240" role="img" aria-label={`Pareto of ${selected.sample_size} QMS findings`}>
        {selected.categories.slice(0,18).map((row,i,shown) => {
          const width=635/shown.length, max=Math.max(1,...shown.map(x=>x.count)), height=row.count/max*160;
          return <g key={row.category}>
            <rect x={60+i*width} y={195-height} width={Math.max(5,width-9)} height={height} fill="currentColor" opacity=".35"/>
            <text x={60+i*width} y={211} fontSize={9} fill="currentColor">{row.category.slice(0,9)}</text>
          </g>;
        })}
        <polyline points={selected.categories.slice(0,18).map((x,i,rows) =>
          `${60+(i+.5)*635/rows.length},${195-x.cumulative_percent*1.6}`).join(" ")}
          fill="none" stroke="currentColor" strokeWidth={2}/>
      </svg>}
      <div className="car-rca-table-scroll"><table><caption>Full-cohort frequencies, descending</caption>
        <thead><tr><th>Category</th><th>Frequency</th><th>%</th><th>Cumulative %</th></tr></thead>
        <tbody>{selected.categories.map(x => <tr key={x.category}>
          <td>{x.category}</td><td>{x.count}</td><td>{x.share_percent.toFixed(2)}%</td><td>{x.cumulative_percent.toFixed(2)}%</td>
        </tr>)}</tbody></table></div>
      <details><summary>Source finding references ({selected.source_reference_count})</summary>
        <div className="car-rca-table-scroll"><table><thead><tr><th>Finding</th><th>Audit</th><th>Requirement</th><th>Created</th></tr></thead>
          <tbody>{selected.source_references.map(x => <tr key={x.id}>
            <td>{x.reference || x.id}</td><td>{x.audit_reference}</td>
            <td>{x.requirement}</td><td>{x.created_at?.slice(0,10)}</td>
          </tr>)}</tbody></table></div>
      </details>
      <p className="car-rca-note">High frequency does not demonstrate root cause. Quality must independently validate any claimed causal relationship.</p>
    </div>}
  </section>;
}
