import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AnalysisCount, AnalysisSnapshot } from "../../../services/qmsAnalysis";

export function paretoRows(rows: AnalysisCount[], total: number) {
  let cumulative = 0;
  return [...rows].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)).map(row => {
    cumulative += row.count;
    return { ...row, cumulative: total ? Math.round(cumulative / total * 1000) / 10 : 0 };
  });
}
export default function AnalysisQuantitative({ data, selectRequirement, selectSeverity }: {
  data: AnalysisSnapshot; selectRequirement: (value: string) => void; selectSeverity: (value: string) => void;
}) {
  const [view, setView] = useState<"trend" | "pareto" | "severity" | "types">("trend");
  const rows = view === "trend" ? data.trend : view === "pareto" ? paretoRows(data.requirements, data.total) : view === "severity" ? data.severity : data.types;
  const title = { trend: "Finding creation trend", pareto: "Requirement Pareto", severity: "Recorded severity", types: "Finding types" }[view];
  return <section className="qa-analysis-card">
    <div className="qa-analysis-heading"><div><h2>{title}</h2><p>Counts across all {data.total.toLocaleString()} findings in the selected cohort.</p></div>
      <label>Analysis view<select value={view} onChange={e => setView(e.target.value as typeof view)}><option value="trend">Monthly run chart</option><option value="pareto">Requirement Pareto</option><option value="severity">Severity distribution</option><option value="types">Finding type distribution</option></select></label>
    </div>
    {data.total === 0 ? <p className="qa-analysis-empty">No findings match these filters. No rate or trend can be inferred.</p> : <div className="qa-analysis-chart" role="img" aria-label={`${title}. Exact values are in the data table below.`}>
      <ResponsiveContainer width="100%" height="100%">
        {view === "trend" ? <LineChart data={rows} margin={{ left: 0, right: 20, bottom: 20 }} accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} /><Tooltip /><Line type="linear" dataKey="count" name="Findings" stroke="var(--accent-primary, #2563eb)" strokeWidth={2} isAnimationActive={false} /></LineChart>
        : view === "pareto" ? <ComposedChart data={rows} margin={{ bottom: 30, right: 15 }} accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={false} /><YAxis yAxisId="count" allowDecimals={false} /><YAxis yAxisId="percent" orientation="right" domain={[0, 100]} unit="%" /><Tooltip /><Bar yAxisId="count" dataKey="count" name="Findings" fill="var(--accent-primary, #2563eb)" isAnimationActive={false} /><Line yAxisId="percent" dataKey="cumulative" name="Cumulative %" stroke="var(--accent-warning, #b45309)" isAnimationActive={false} /></ComposedChart>
        : <BarChart data={rows} accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Findings" fill="var(--accent-primary, #2563eb)" isAnimationActive={false} /></BarChart>}
      </ResponsiveContainer>
    </div>}
    <p className="qa-analysis-note">{view === "trend" ? "A run chart of counts, not a defect rate. Audit volume and inspection exposure are not available as denominators. Partial months are flagged below; no control limits or prediction are inferred." : view === "pareto" ? `Requirements are exact recorded references, not inferred root causes. Top 30 groups shown; ${data.requirement_tail} findings in the remaining groups. Cumulative percentages use the full cohort.` : "Severity is the finding classification recorded by the auditor. It is not CAR priority and is not converted into an invented risk score."}</p>
    <div className="qa-analysis-table-wrap"><table><caption>{title} — source values and drill-down</caption><thead><tr><th>Category / period</th><th>Findings</th><th>{view === "trend" ? "Coverage" : "Cohort share"}</th><th>Investigate</th></tr></thead><tbody>{rows.map(row => <tr key={row.name}><th scope="row">{row.name}</th><td>{row.count}</td><td>{view === "trend" ? ("partial" in row && row.partial ? "Partial month" : "Full month") : data.total ? `${(row.count / data.total * 100).toFixed(1)}%` : "N/A"}</td><td>{view === "pareto" ? <button onClick={() => selectRequirement(row.name)}>Open findings</button> : view === "severity" ? <button onClick={() => selectSeverity(row.name)}>Open findings</button> : "—"}</td></tr>)}</tbody></table></div>
  </section>;
}
