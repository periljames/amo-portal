import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { classifyQmsPath, qmsModulePath } from "./routes/qmsRouteRegistry";
import "./qms-management-review.css";

type Event = { id: string; actor_name: string; action: string; module: string; entity_type: string; entity_id: string; previous_value: unknown; new_value: unknown; created_at: string };
type History = { items: Event[]; total: number; limit: number; offset: number; modules: string[] };
const human = (text: string) => text.replaceAll("_", " ").replaceAll("-", " ").toLowerCase();

export default function QmsActivityLogPage() {
  const location = useLocation();
  const amoCode = classifyQmsPath(location.pathname).amoCode || "";
  const [params, setParams] = useSearchParams();
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const q = params.get("q") || ""; const module = params.get("module") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const data = useQuery({ queryKey: ["qms-activity-log", amoCode, q, module, offset, revision], queryFn: ({ signal }) => apiRequest<History>(`${qmsPath(amoCode, "/activity-log")}?${new URLSearchParams({ q, module, offset: String(offset), limit: "30" })}`, { signal, cacheTtlMs: 0 }) });
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== "offset") next.delete("offset"); setSelected(null); setParams(next, { replace: true }); };
  const event = data.data?.items.find(item => item.id === selected);
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><section className="qms-review" aria-label="Quality activity history">
    <header className="qms-review__heading"><div><h1>Quality activity log</h1><p>Attributable source changes and retained before / after records. This history is read-only.</p></div><div className="qms-review__buttons"><Link to={qmsModulePath(amoCode, "settings")}>Quality settings</Link><button disabled={data.isFetching} onClick={() => setRevision(r => r + 1)}>Refresh history</button></div></header>
    <QmsSectionTabs amoCode={amoCode} />
    <section className="qms-review__section"><div className="qms-review__fields"><label>Search action or record<input type="search" value={q} onChange={e => update("q", e.target.value)} /></label><label>Quality module<select aria-label="Quality module" value={module} onChange={e => update("module", e.target.value)}><option value="">All modules</option>{data.data?.modules.filter(Boolean).map(m => <option key={m} value={m}>{human(m)}</option>)}</select></label></div>
      {data.isPending && <p role="status">Loading retained history…</p>}{data.isError && <p role="alert">{data.error.message} <button onClick={() => void data.refetch()}>Retry history</button></p>}
      {data.data && <><p>{data.data.total} matching events</p><div className="qms-review__table"><table><thead><tr><th>Recorded</th><th>Actor</th><th>Action</th><th>Module / record</th><th>Change</th></tr></thead><tbody>{data.data.items.map(item => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.actor_name}</td><td>{human(item.action)}</td><td>{human(item.module)}<small className="qms-register__rating">{item.entity_id}</small></td><td><button onClick={() => setSelected(item.id)}>Inspect change</button></td></tr>)}</tbody></table></div>{!data.data.items.length && <p>No retained events match this view.</p>}
        <nav aria-label="Register pages"><button disabled={!offset} onClick={() => update("offset", String(Math.max(0, offset - 30)))}>Previous</button><span>Page {Math.floor(offset / 30) + 1}</span><button disabled={offset + 30 >= data.data.total} onClick={() => update("offset", String(offset + 30))}>Next</button></nav>
      </>}
    </section>
    {event && <section className="qms-review__section"><div className="qms-review__heading"><h2>Retained change: {human(event.action)}</h2><button onClick={() => setSelected(null)}>Close change</button></div><p>{event.actor_name} · {new Date(event.created_at).toLocaleString()}</p><h3>Before</h3><pre className="qms-review__prose">{JSON.stringify(event.previous_value, null, 2) || "No previous record"}</pre><h3>After</h3><pre className="qms-review__prose">{JSON.stringify(event.new_value, null, 2) || "No replacement record"}</pre></section>}
  </section></DepartmentLayout>;
}
