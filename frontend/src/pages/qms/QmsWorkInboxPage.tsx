import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { classifyQmsPath } from "./routes/qmsRouteRegistry";
import "./qms-management-review.css";

const QmsPersonalTasks = lazy(() => import("./inbox/QmsPersonalTasks"));
type WorkItem = { id: string; record_id: string; source: string; source_label: string; title: string; status: string; due_date: string | null; route: string; watching: boolean };
type WorkList = { items: WorkItem[]; total: number; offset: number; limit: number; source_errors: { source: string; message: string }[] };
const titles: Record<string, string> = { "assigned-to-me": "Assigned to me", approvals: "Awaiting my review", overdue: "My overdue work", watching: "Watching", completed: "My completed work" };

export default function QmsWorkInboxPage() {
  const location = useLocation();
  const context = classifyQmsPath(location.pathname);
  const amoCode = context.amoCode || "";
  const view = context.relativePath?.split("/")[1] || "assigned-to-me";
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const data = useQuery({ queryKey: ["quality-work-inbox", amoCode, view, q, offset, revision], queryFn: ({ signal }) =>
    apiRequest<WorkList>(`${qmsPath(amoCode, `/work-inbox/${view}`)}?${new URLSearchParams({ q, offset: String(offset) })}`, { signal, cacheTtlMs: 0 }) });
  function update(values: Record<string, string | null>) {
    const next = new URLSearchParams(params); for (const [key, value] of Object.entries(values)) { if (!value) next.delete(key); else next.set(key, value); } setParams(next, { replace: true });
  }
  async function toggle(item: WorkItem) {
    setBusy(item.id); setError("");
    try {
      await apiRequest(qmsPath(amoCode, item.watching ? `/work-inbox/watch/${item.source}/${encodeURIComponent(item.record_id)}` : "/work-inbox/watch"), {
        method: item.watching ? "DELETE" : "POST", ...(item.watching ? {} : { body: JSON.stringify({ source: item.source, record_id: item.record_id }) }),
      }); setRevision(r => r + 1);
    } catch (e) { setError(e instanceof Error ? e.message : "The watch preference could not be saved."); }
    finally { setBusy(""); }
  }
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><section className="qms-review" aria-label="Quality assignments">
    <header className="qms-review__heading"><div><h1>My Quality Work</h1><p>Assignments and review decisions from their source workflows. Complete the work in its source record.</p></div><button disabled={data.isFetching} onClick={() => setRevision(r => r + 1)}>Refresh work</button></header>
    <QmsSectionTabs amoCode={amoCode} />
    <section className="qms-review__section"><div className="qms-review__heading"><h2>{titles[view]}</h2><label>Find assigned work<input type="search" value={q} onChange={e => update({ q: e.target.value, offset: null })} /></label></div>
      {view === "approvals" && <p>Management-review approval, action verification and CAR verification queues for which you have management permission.</p>}
      {view === "watching" && <p>Use Watch on an assignment to follow it here. Watching does not change ownership or approval authority.</p>}
      {data.isPending && <p role="status">Loading Quality assignments…</p>}
      {data.isError && <p role="alert">{data.error.message} <button onClick={() => void data.refetch()}>Retry assignments</button></p>}
      {error && <p role="alert">{error}</p>}
      {Boolean(data.data?.source_errors.length) && <div role="alert" className="qms-review__error"><strong>Some sources are unavailable; this list is incomplete.</strong><ul>{data.data?.source_errors.map(s => <li key={s.source}>{s.source}: {s.message}</li>)}</ul></div>}
      {data.data && !data.data.items.length && <p>No records match this view. Notifications and personal to-dos are separate from governed assignments.</p>}
      {!!data.data?.items.length && <div className="qms-review__table"><table><thead><tr><th>Work</th><th>Source</th><th>Status</th><th>Due</th><th>Next step</th></tr></thead><tbody>{data.data.items.map(item => <tr key={item.id}><td>{item.title || "Untitled source record"}</td><td>{item.source_label}</td><td>{item.status.replaceAll("_", " ").toLowerCase()}</td><td>{item.due_date?.slice(0, 10) || "No date set"}</td><td><div className="qms-review__buttons"><Link to={item.route}>Open work</Link><button disabled={!!busy} onClick={() => void toggle(item)}>{busy === item.id ? "Saving…" : item.watching ? "Stop watching" : "Watch"}</button></div></td></tr>)}</tbody></table></div>}
      {data.data && <nav aria-label="Register pages"><button disabled={!offset} onClick={() => update({ offset: String(Math.max(0, offset - 30)) })}>Previous</button><span>{data.data.total} matching records</span><button disabled={offset + 30 >= data.data.total} onClick={() => update({ offset: String(offset + 30) })}>Next</button></nav>}
    </section>
    <details className="qms-review__section"><summary>Personal to-do list and reminders</summary><Suspense fallback={<p role="status">Loading personal tasks…</p>}><QmsPersonalTasks amoCode={amoCode} /></Suspense></details>
  </section></DepartmentLayout>;
}
