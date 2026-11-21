import { ArrowUpRight, RefreshCw, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { canFilterFindingSeverity, findingDistribution, findingGroupLabel, findingMonthLabel, findingTrendSummary, type FindingInsights } from "./findingAnalysisModel";
import "./finding-analysis.css";

type Props = {
  view: string; year: number; data?: FindingInsights; loading: boolean; refreshing: boolean; error: Error | null;
  openOnly: boolean; search: string; onFilter: (key: string, value: string) => void; onRefresh: () => void;
  register: (filters: Record<string, string>) => string;
};

export function FindingAnalysisControls({ year, refreshing, onFilter, onRefresh }: Pick<Props, "year" | "refreshing" | "onFilter" | "onRefresh">) {
  return <div className="finding-analysis__actions"><form onSubmit={event => { event.preventDefault(); onFilter("period", String(new FormData(event.currentTarget).get("period"))); }}>
    <label htmlFor="finding-analysis-year">Year</label><input id="finding-analysis-year" key={year} name="period" aria-label="Finding year" type="number" min={2000} max={2199} required defaultValue={year} /><button type="submit">Apply year</button>
  </form><button type="button" disabled={refreshing} onClick={onRefresh} aria-label="Refresh analysis"><RefreshCw size={15} className={refreshing ? "is-refreshing" : ""} aria-hidden /><span>Refresh</span></button></div>;
}

function TrendChart({ months }: { months: FindingInsights["months"] }) {
  const maximum = Math.max(1, ...months.flatMap(month => [month.raised, month.closed]));
  const ceiling = Math.ceil(maximum / 4) * 4;
  const plotHeight = 200, base = 230, start = 45, step = 59;
  return <div className="finding-analysis__trend-scroll" role="region" aria-label="Scrollable monthly chart" tabIndex={0}><svg className="finding-analysis__trend" viewBox="0 0 770 274" role="img" aria-labelledby="finding-trend-title finding-trend-description">
    <title id="finding-trend-title">Monthly finding events</title><desc id="finding-trend-description">Findings raised and closed each month. Exact figures are available in Monthly figures below.</desc>
    {[0, 1, 2, 3, 4].map(tick => {
      const value = ceiling * tick / 4, y = base - plotHeight * tick / 4;
      return <g key={tick}><line x1={start} x2={755} y1={y} y2={y} className="finding-analysis__gridline" /><text x={start - 10} y={y + 4} textAnchor="end">{Number.isInteger(value) ? value : value.toFixed(1)}</text></g>;
    })}
    {months.map((month, index) => {
      const x = start + index * step + 15;
      return <g key={month.month}><title>{findingMonthLabel(month.month)}: {month.raised} raised, {month.closed} closed</title>
        <rect x={x} y={base - month.raised / ceiling * plotHeight} width={15} height={month.raised / ceiling * plotHeight} rx={2} className="finding-analysis__raised" />
        <rect x={x + 18} y={base - month.closed / ceiling * plotHeight} width={15} height={month.closed / ceiling * plotHeight} rx={2} className="finding-analysis__closed-event" />
        <text x={x + 16} y={base + 25} textAnchor="middle">{findingMonthLabel(month.month)}</text>
      </g>;
    })}
  </svg></div>;
}

export default function FindingAnalysis({ view, year, data, loading, refreshing, error, openOnly, search, onFilter, onRefresh, register }: Props) {
  const process = view === "by-process", trends = view === "trends";
  const groups = data ? findingDistribution(data, view, openOnly, search) : [];
  const events = findingTrendSummary(data?.months || []);
  const denominator = data ? (openOnly ? data.open : data.total) : 0;
  const scale = Math.max(1, denominator);
  return <section className="finding-analysis" aria-label="Finding analysis" aria-busy={refreshing}>
    {loading ? <div className="finding-analysis__state" role="status">Loading finding analysis…</div> : error ? <div className="finding-analysis__state" role="alert"><strong>Analysis unavailable</strong><p>{error.message}</p><button onClick={onRefresh}>Retry analysis</button></div> : data ? <>
      <div className="finding-analysis__metrics">
        <Link to={register({})}><span>Raised in {year}</span><strong>{trends ? events.raised : data.total}</strong></Link>
        {trends ? <><div><span>Closed in {year}</span><strong>{events.closed}</strong></div><div><span>{events.balance < 0 ? "More closed than raised" : events.balance > 0 ? "More raised than closed" : "Raised / closed balance"}</span><strong>{Math.abs(events.balance)}</strong></div></>
          : <><Link to={register({ status: "open" })}><span>Still open</span><strong>{data.open}</strong><small>{data.total ? Math.round(data.open / data.total * 100) : 0}% of this year's findings</small></Link><Link to={register({ status: "closed" })}><span>Closed</span><strong>{data.total - data.open}</strong></Link></>}
      </div>
      <section className="finding-analysis__panel" aria-labelledby="finding-analysis-chart-title">
        <header className="finding-analysis__panel-header"><div><h2 id="finding-analysis-chart-title">{trends ? "Raised and closed by month" : process ? "Findings by process area" : "Severity distribution"}</h2><p>{trends ? `Monthly events · ${year}` : `${openOnly ? "Open findings" : "Findings raised"} · ${year}`}</p></div>
          {!trends && <div className="finding-analysis__filters">{process && <label className="finding-analysis__search"><Search size={15} aria-hidden /><input aria-label="Filter process areas" type="search" placeholder="Find a process…" value={search} onChange={event => onFilter("processSearch", event.target.value)} /></label>}
            <label><span className="sr-only">Finding status</span><select aria-label="Finding status" value={openOnly ? "open" : "all"} onChange={event => onFilter("status", event.target.value === "open" ? "open" : "")}><option value="all">All findings</option><option value="open">Open only</option></select></label></div>}
        </header>
        {trends ? <>
          <div className="finding-analysis__legend"><span><i className="finding-analysis__raised" />Raised</span><span><i className="finding-analysis__closed-event" />Closed</span></div>
          {events.raised || events.closed ? <TrendChart months={data.months} /> : <div className="finding-analysis__state">No findings raised or closed in {year}.</div>}
          <p className="finding-analysis__note">Closures include findings raised in earlier years. The difference shows event balance, not outstanding backlog.</p>
          <details className="finding-analysis__figures"><summary>Monthly figures</summary><div><table><caption className="sr-only">Monthly finding events for {year}</caption><thead><tr><th>Month</th><th>Raised</th><th>Closed</th></tr></thead><tbody>{data.months.map(month => <tr key={month.month}><th scope="row">{findingMonthLabel(month.month)}</th><td>{month.raised}</td><td>{month.closed}</td></tr>)}</tbody></table></div></details>
        </> : <>
          <div className="finding-analysis__legend"><span><i className="finding-analysis__open" />Open</span>{!openOnly && <span><i className="finding-analysis__resolved" />Closed</span>}<small>Share of {openOnly ? "open " : ""}findings in {year}</small></div>
          {groups.length ? <ul className="finding-analysis__groups" aria-label={process ? "Process distribution" : "Severity distribution"}>{groups.map(group => {
            const count = openOnly ? group.open : group.total;
            const content = <><span className="finding-analysis__group-name" data-severity={!process ? group.key.toLowerCase() : undefined}>{process ? group.key : findingGroupLabel(group.key)}</span><span className="finding-analysis__bar" aria-hidden><i className="finding-analysis__open" style={{ width: `${group.open / scale * 100}%` }} />{!openOnly && <i className="finding-analysis__resolved" style={{ width: `${(group.total - group.open) / scale * 100}%` }} />}</span><span className="finding-analysis__count"><strong>{count}</strong><small>{denominator ? Math.round(count / denominator * 100) : 0}%</small></span>{process || canFilterFindingSeverity(group.key) ? <ArrowUpRight size={16} aria-hidden /> : <span />}</>;
            return <li key={group.key}>{process || canFilterFindingSeverity(group.key)
              ? <Link to={register({ [process ? "process" : "severity"]: group.key, ...(openOnly ? { status: "open" } : {}) })} aria-label={`Inspect ${process ? group.key : findingGroupLabel(group.key)} findings${openOnly ? ", open only" : ""}`}>{content}</Link>
              : <div className="finding-analysis__unclassified">{content}</div>}</li>;
          })}</ul> : <div className="finding-analysis__state">{search ? <>No process areas match “{search}”. <button onClick={() => onFilter("processSearch", "")}>Clear search</button></> : openOnly ? "No open findings in this year." : "No findings recorded for this year."}</div>}
          {process && <>
            <div className="finding-analysis__coverage"><span><strong>{data.total - (data.unmapped || 0)}</strong> of {data.total} total findings mapped to a process</span>{data.unmapped ? <Link to={register({ processUnmapped: "1" })}>{data.unmapped} unmapped <ArrowUpRight size={14} aria-hidden /></Link> : null}</div>
            <p className="finding-analysis__note">Process areas come from verified links to approved active controls. A finding may belong to more than one process, so shares can exceed 100% in total.</p>
          </>}
        </>}
      </section>
    </> : null}
  </section>;
}
