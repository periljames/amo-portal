import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { classifyQmsPath } from "./routes/qmsRouteRegistry";
import "./inbox/qms-work-inbox.css";

const QmsPersonalTasks = lazy(() => import("./inbox/QmsPersonalTasks"));
const QmsConnectedWork = lazy(() => import("./inbox/QmsConnectedWork"));
const QmsDailyFocus = lazy(() => import("./inbox/QmsDailyFocus"));
const QmsSavedViews = lazy(() => import("./inbox/QmsSavedViews"));
type WorkItem = { id: string; record_id: string; source: string; source_label: string; title: string; status: string; due_date: string | null; route: string; watching: boolean; next_action?: string; scope?: string; updated_at?: string | null };
type WorkList = { items: WorkItem[]; total: number; offset: number; limit: number; source_errors: { source: string; message: string }[] };
type Summary = { assigned_to_me: number; approvals: number; overdue: number; completed: number; source_errors: { source: string; message: string }[] };
const titles: Record<string, string> = {
  "assigned-to-me": "Assigned to me", approvals: "Management approvals", overdue: "Overdue work",
  watching: "Watching", completed: "Completed work",
};
const sources = [
  ["", "All Quality sources"], ["audits", "Audits"], ["cars", "CAR / CAPA"],
  ["review-actions", "Management review actions"], ["reviews", "Management reviews"],
  ["risks", "Risk assessments"], ["treatments", "Risk treatments"], ["commitments", "External commitments"],
];
function duePresentation(item: WorkItem) {
  if (!item.due_date) return { date: "No deadline", timing: "", overdue: false };
  const raw = item.due_date.slice(0, 10);
  const due = new Date(raw + "T00:00:00");
  if (Number.isNaN(due.getTime())) return { date: raw, timing: "", overdue: false };
  const now = new Date();
  const days = Math.round((Date.UTC(due.getFullYear(), due.getMonth(), due.getDate()) -
    Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  // Match backend work_inbox_router.TERMINAL. Watched terminal records remain visible,
  // but never imply that an action is still overdue or approaching its deadline.
  const terminal = ["CLOSED", "COMPLETED", "COMPLETE", "DONE", "ARCHIVED", "CANCELLED", "REJECTED", "RESOLVED", "RETIRED"];
  const finished = terminal.includes(item.status.toUpperCase());
  const timing = finished ? "" : days < 0 ? String(-days) + " days overdue" :
    days === 0 ? "Due today" : days === 1 ? "Due tomorrow" : "Due in " + days + " days";
  return { date: due.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }),
    timing, overdue: !finished && days < 0 };
}
function emptyText(view: string, filtered: boolean) {
  if (filtered) return ["No matching work", "Try another search or clear the source filter."];
  if (view === "approvals") return ["No pending management decisions", "New authorised review decisions will appear here."];
  if (view === "watching") return ["You are not watching any records", "Use Watch on an authorised source record to follow its progress."];
  if (view === "completed") return ["No completed assignments", "Source workflows will appear here after completion."];
  if (view === "overdue") return ["No overdue work found", "Only available Quality assignment sources are included."];
  return ["No active Quality assignments", "New work will appear when you are assigned in a source workflow."];
}
export default function QmsWorkInboxPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const context = classifyQmsPath(location.pathname);
  const amoCode = context.amoCode || "";
  const view = context.relativePath?.split("/")[1] || "assigned-to-me";
  const [params, setParams] = useSearchParams();
  const personal = params.get("mode") === "personal";
  const connected = params.get("mode") === "connected";
  const focused = params.get("mode") === "focus";
  const q = params.get("q") || "";
  const source = params.get("source") || "";
  const dueFilter = ["today", "next-seven", "undated"].includes(params.get("due") || "") ? params.get("due")! : "all";
  const sort = params.get("sort") === "title" ? "title" : "priority";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [search, setSearch] = useState(q);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  function update(values: Record<string, string | null>) {
    setParams(previous => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(values)) {
        if (!value) next.delete(key); else next.set(key, value);
      }
      return next;
    }, { replace: true });
  }
  useEffect(() => { setSearch(q); }, [q]);
  useEffect(() => {
    if (search === q) return;
    const timer = window.setTimeout(() => update({ q: search, offset: null }), 300);
    return () => window.clearTimeout(timer);
    // URL search state is the committed, debounced filter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, q]);
  const data = useQuery({
    queryKey: ["quality-work-inbox", amoCode, view, q, source, dueFilter, sort, offset, revision],
    enabled: !personal && !connected && !focused && !!amoCode,
    queryFn: ({ signal }) => apiRequest<WorkList>(
      qmsPath(amoCode, "/work-inbox/" + view) + "?" + new URLSearchParams({ q, source, due: dueFilter, sort, offset: String(offset) }),
      { signal, cacheTtlMs: 0 },
    ),
  });
  const summary = useQuery({
    queryKey: ["quality-work-inbox-summary", amoCode, revision],
    enabled: !personal && !connected && !focused && !!amoCode,
    queryFn: ({ signal }) => apiRequest<Summary>(qmsPath(amoCode, "/work-inbox/summary"), { signal, cacheTtlMs: 0 }),
  });
  async function toggle(item: WorkItem) {
    setBusy(item.id); setError("");
    try {
      await apiRequest(qmsPath(amoCode,
        item.watching ? "/work-inbox/watch/" + item.source + "/" + encodeURIComponent(item.record_id) : "/work-inbox/watch"), {
        method: item.watching ? "DELETE" : "POST",
        ...(item.watching ? {} : { body: JSON.stringify({ source: item.source, record_id: item.record_id }) }),
      });
      setRevision(previous => previous + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The watch preference could not be saved.");
    } finally { setBusy(""); }
  }
  const base = "/maintenance/" + encodeURIComponent(amoCode) + "/quality/inbox/";
  const counts = [
    ["assigned-to-me", "Assigned", summary.data?.assigned_to_me],
    ["approvals", "Approvals", summary.data?.approvals],
    ["overdue", "Overdue", summary.data?.overdue],
    ["completed", "Completed", summary.data?.completed],
  ] as const;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-inbox" aria-label="My Quality Work">
      <header className="qms-inbox__header"><div><h1>My Quality Work</h1>
        <p>Find Quality assignments, authorised review decisions and personal follow-ups in one place.</p></div>
        {!personal && !connected && !focused && <button type="button" onClick={() => setRevision(previous => previous + 1)}
          disabled={data.isFetching || summary.isFetching}>Refresh work</button>}
      </header>
      <nav aria-label="Work areas" className="qms-inbox__area-tabs">
        <button type="button" aria-current={focused ? "page" : undefined}
          onClick={() => update({ mode: "focus" })}>Today & next steps</button>
        <button type="button" aria-current={!personal && !connected && !focused ? "page" : undefined}
          onClick={() => update({ mode: null })}>Governed assignments</button>
        <button type="button" aria-current={personal ? "page" : undefined}
          onClick={() => update({ mode: "personal" })}>Personal to-dos</button>
        <button type="button" aria-current={connected ? "page" : undefined}
          onClick={() => update({ mode: "connected" })}>Connected work</button>
      </nav>
      {personal ? <Suspense fallback={<p role="status">Loading personal tasks…</p>}>
        <QmsPersonalTasks amoCode={amoCode} />
      </Suspense> : focused ?
        <Suspense fallback={<p role="status">Loading today's priorities…</p>}>
          <QmsDailyFocus amoCode={amoCode} />
        </Suspense> : connected ?
        <Suspense fallback={<p role="status">Loading connected responsibilities…</p>}>
          <QmsConnectedWork amoCode={amoCode} />
        </Suspense> : <>
        <div className="qms-inbox__overview" aria-label="Quality work summary">
          {counts.map(([target, label, count]) => <Link to={base + target} key={target}
            className={"qms-inbox__metric" + (target === "overdue" && count ? " qms-inbox__metric--attention" : "")}>
            <span>{label}</span><strong>{summary.isError ? "—" : count ?? "…"}</strong>
          </Link>)}
        </div>
        {summary.isError && <p role="alert" className="qms-inbox__notice">Overview counts could not be loaded. Work lists remain available.</p>}
        {!!summary.data?.source_errors.length && <p role="alert" className="qms-inbox__notice">Some Quality sources could not be counted. Totals may be incomplete.</p>}
        <QmsSectionTabs amoCode={amoCode} />
        <Suspense fallback={<p role="status">Loading your saved work filters…</p>}>
          <QmsSavedViews amoCode={amoCode} filters={{ view, q, source, due: dueFilter, sort }}
            onApply={saved => {
              if (!titles[saved.view]) {
                setError("This saved work view is no longer supported.");
                return;
              }
              setSearch(saved.q || "");
              const next = new URLSearchParams();
              if (saved.q) next.set("q", saved.q);
              if (saved.source) next.set("source", saved.source);
              if (saved.due && saved.due !== "all") next.set("due", saved.due);
              if (saved.sort && saved.sort !== "priority") next.set("sort", saved.sort);
              navigate(base + saved.view + (next.size ? "?" + next.toString() : ""));
            }} />
        </Suspense>
        <section className="qms-inbox__panel" aria-labelledby="qms-inbox-list-title">
          <div className="qms-inbox__panel-heading">
            <div><h2 id="qms-inbox-list-title">{titles[view] || "Quality work"}</h2>
              <p>{view === "approvals" ? "Permission-authorised decisions. This may be a shared management queue rather than an individual assignment." :
                view === "watching" ? "Following never changes ownership or review authority." :
                "Open the authoritative source record to perform governed actions."}</p></div>
            <div className="qms-inbox__filters">
              <label>Search work<input type="search" value={search} maxLength={80}
                placeholder="Search titles" onChange={event => setSearch(event.target.value)} /></label>
              <label>Quality source<select value={source}
                onChange={event => update({ source: event.target.value, offset: null })}>
                {sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select></label>
              <label>Deadline<select value={dueFilter} onChange={event => update({ due: event.target.value, offset: null })}>
                <option value="all">Any deadline</option>
                <option value="today">Due today</option>
                <option value="next-seven">Next 7 days</option>
                <option value="undated">Not dated</option>
              </select></label>
              <label>Order<select value={sort} onChange={event =>
                update({ sort: event.target.value === "title" ? "title" : null, offset: null })}>
                <option value="priority">Urgency first</option>
                <option value="title">Title A to Z</option>
              </select></label>
            </div>
          </div>
          {error && <p role="alert" className="qms-inbox__notice">{error}</p>}
          {data.isError && <div role="alert" className="qms-inbox__notice">
            Unable to load work: {data.error.message} <button type="button" onClick={() => void data.refetch()}>Retry</button>
          </div>}
          {!!data.data?.source_errors.length && <div role="alert" className="qms-inbox__notice">
            <strong>Some sources are unavailable. This list is incomplete.</strong>
            <ul>{data.data.source_errors.map(row => <li key={row.source}>{row.source}: {row.message}</li>)}</ul>
          </div>}
          {data.isPending && <p role="status" className="qms-inbox__loading">Loading Quality assignments…</p>}
          {!!data.data?.items.length && <div className="qms-inbox__work-list" aria-label="Quality work items">
            {data.data.items.map(item => {
              const due = duePresentation(item);
              return <article className="qms-inbox__work-card" key={item.id}>
                <div className="qms-inbox__work-main"><div className="qms-inbox__eyebrow">
                  <span>{item.source_label}</span><span>{item.scope === "SHARED_REVIEW" ? "Shared review queue" : item.scope === "WATCHING" ? "Following" : "My assignment"}</span><span>{item.status.replaceAll("_", " ").toLowerCase()}</span>
                </div><h3><Link to={item.route}>{item.title || "Untitled source record"}</Link></h3>
                  {item.next_action && <p className="qms-connected-work__next"><strong>Next:</strong> {item.next_action}</p>}
                </div>
                <div className={"qms-inbox__due" + (due.overdue ? " qms-inbox__due--overdue" : "")}>
                  <span>{due.date}</span>{due.timing && <strong>{due.timing}</strong>}</div>
                <div className="qms-inbox__item-actions">
                  <Link className="qms-inbox__open" to={item.route}>Open workflow</Link>
                  <button type="button" disabled={!!busy} onClick={() => void toggle(item)}
                    aria-label={(item.watching ? "Stop watching " : "Watch ") + (item.title || "record")}>
                    {busy === item.id ? "Saving…" : item.watching ? "Unwatch" : "Watch"}
                  </button>
                </div>
              </article>;
            })}
          </div>}
          {data.data && !data.data.items.length && !data.isError && <div className="qms-inbox__empty" role="status">
            <h3>{data.data.source_errors.length ? "No records available from loaded sources" :
              offset > 0 ? "No further records" : emptyText(view, Boolean(q || source || dueFilter !== "all"))[0]}</h3>
            <p>{data.data.source_errors.length ? "Try again when the unavailable sources have recovered." :
              offset > 0 ? "Go back to the previous page." : emptyText(view, Boolean(q || source || dueFilter !== "all"))[1]}</p>
            {(q || source || dueFilter !== "all" || sort !== "priority") && <button type="button"
              onClick={() => { setSearch(""); update({ q: null, source: null, due: null, sort: null, offset: null }); }}>Clear filters</button>}
          </div>}
          {!!data.data?.total && <nav className="qms-inbox__paging" aria-label="Work pages">
            <span>{offset + 1}–{Math.min(offset + data.data.items.length, data.data.total)} of {data.data.total} records</span>
            <div><button disabled={!offset} type="button"
              onClick={() => update({ offset: String(Math.max(0, offset - data.data!.limit)) })}>Previous</button>
              <button disabled={offset + data.data.limit >= data.data.total} type="button"
                onClick={() => update({ offset: String(offset + data.data!.limit) })}>Next</button></div>
          </nav>}
        </section>
      </>}
    </main>
  </DepartmentLayout>;
}
