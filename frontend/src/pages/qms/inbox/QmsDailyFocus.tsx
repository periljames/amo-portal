import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest, qmsPath } from "../../../services/apiClient";
import type { TaskItem } from "../../../services/tasks";

type QueueItem = {
  id: string; title: string; source_label: string; status: string; due_date: string | null;
  route: string; next_action?: string; scope?: string; blocked?: boolean;
};
type QueuePage = {
  items: QueueItem[]; total: number; source_errors: Array<{ source: string; message: string }>;
};
type PersonalPage = { items: TaskItem[]; total: number };
type Summary = {
  assigned_to_me: number; approvals: number; overdue: number; completed: number;
  source_errors: Array<{ source: string; message: string }>;
};
type FocusItem = {
  id: string; title: string; source_label: string; status: string;
  due_date: string | null; next_action: string; route: string;
  scope: string; priority: number;
};
function dateState(raw: string | null) {
  if (!raw) return { label: "No due date", rank: 3, overdue: false };
  const key = raw.slice(0, 10);
  // Governed source dates are calendar-only; personal due_at is an instant
  // and must use the user's local calendar day to avoid false overdue ranking.
  const when = /^\d{4}-\d{2}-\d{2}T/.test(raw)
    ? new Date(raw)
    : new Date(key + "T00:00:00");
  if (Number.isNaN(when.getTime())) return { label: "Due date not available", rank: 3, overdue: false };
  const today = new Date();
  const days = Math.round((Date.UTC(when.getFullYear(), when.getMonth(), when.getDate()) -
    Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
  return { label: days < 0 ? String(-days) + " days overdue" : days === 0 ? "Due today" :
    days === 1 ? "Due tomorrow" : "Due in " + days + " days",
  rank: days < 0 ? 0 : days === 0 ? 1 : 2, overdue: days < 0 };
}

export default function QmsDailyFocus({ amoCode }: { amoCode: string }) {
  const base = "/maintenance/" + encodeURIComponent(amoCode) + "/quality/inbox/";
  const governed = useQuery({
    queryKey: ["qms-daily-focus-governed", amoCode],
    queryFn: ({ signal }) => apiRequest<QueuePage>(
      qmsPath(amoCode, "/work-inbox/assigned-to-me?offset=0&sort=priority"),
      { signal, cacheTtlMs: 0 },
    ),
  });
  const connected = useQuery({
    queryKey: ["qms-daily-focus-connected", amoCode],
    queryFn: ({ signal }) => apiRequest<QueuePage>(
      qmsPath(amoCode, "/work-inbox/related?limit=30&offset=0"),
      { signal, cacheTtlMs: 0 },
    ),
  });
  const personal = useQuery({
    queryKey: ["qms-daily-focus-personal", amoCode],
    queryFn: ({ signal }) => apiRequest<PersonalPage>(
      "/tasks/personal?status=open&limit=30&offset=0", { signal, cacheTtlMs: 0 },
    ),
  });
  const summary = useQuery({
    queryKey: ["qms-daily-focus-summary", amoCode],
    queryFn: ({ signal }) => apiRequest<Summary>(
      qmsPath(amoCode, "/work-inbox/summary"), { signal, cacheTtlMs: 0 },
    ),
  });

  const items: FocusItem[] = [
    ...(governed.data?.items || []).map(item => ({
      id: "governed:" + item.id, title: item.title, source_label: item.source_label,
      status: item.status, due_date: item.due_date,
      next_action: item.next_action || "Open the regulated source workflow",
      route: item.route, scope: "My governed assignment", priority: 3,
    })),
    ...(connected.data?.items || []).map(item => ({
      id: "connected:" + item.id, title: item.title, source_label: item.source_label,
      status: item.status, due_date: item.due_date,
      next_action: item.next_action || "Open the source workflow",
      route: item.route,
      scope: item.scope === "SHARED_REVIEW" ? "Shared authorised queue" : "My connected work",
      priority: 3,
    })),
    ...(personal.data?.items || []).map(task => ({
      id: "personal:" + task.id, title: task.title,
      source_label: "Personal to-do", status: task.status,
      due_date: task.due_at || null, next_action: "Plan, edit or complete this personal follow-up",
      route: base + "assigned-to-me?mode=personal", scope: "Personal only",
      priority: Number(task.priority) || 3,
    })),
  ].sort((a, b) => {
    const ad = dateState(a.due_date);
    const bd = dateState(b.due_date);
    if (ad.rank !== bd.rank) return ad.rank - bd.rank;
    if (a.priority !== b.priority) return a.priority - b.priority;
    if (a.due_date !== b.due_date) return (a.due_date || "9999").localeCompare(b.due_date || "9999");
    return a.title.localeCompare(b.title);
  });
  const errors = [
    ...(governed.data?.source_errors || []),
    ...(connected.data?.source_errors || []),
    ...(summary.data?.source_errors || []),
  ];
  const incomplete = governed.isError || connected.isError || personal.isError || summary.isError || !!errors.length;
  const busy = governed.isPending || connected.isPending || personal.isPending;

  return <section className="qms-daily-focus" aria-label="Today and next steps">
    <header className="qms-personal-tasks__heading">
      <div><h2>Today & next steps</h2>
        <p>Prioritised preview across Quality assignments, connected obligations and personal follow-ups.
          The source workflow remains authoritative for every regulated decision.</p></div>
      <button type="button" disabled={governed.isFetching || connected.isFetching || personal.isFetching}
        onClick={() => {
          void governed.refetch();
          void connected.refetch();
          void personal.refetch();
          void summary.refetch();
        }}>Refresh priorities</button>
    </header>
    <nav className="qms-daily-focus__shortcuts" aria-label="Work areas">
      <Link to={base + "overdue"}>Governed overdue <strong>{summary.isError ? "—" : summary.data?.overdue ?? "…"}</strong></Link>
      <Link to={base + "approvals"}>Management approvals <strong>{summary.isError ? "—" : summary.data?.approvals ?? "…"}</strong></Link>
      <Link to={base + "assigned-to-me?mode=connected"}>Connected work <strong>{connected.isError ? "—" : connected.data?.total ?? "…"}</strong></Link>
      <Link to={base + "assigned-to-me?mode=personal"}>Personal open <strong>{personal.isError ? "—" : personal.data?.total ?? "…"}</strong></Link>
    </nav>
    {incomplete && <div role="alert" className="qms-inbox__notice">
      <strong>Some work is not available in this preview. Counts and priorities may be incomplete.</strong>
      {!!errors.length && <ul>{errors.map((error, index) => <li key={index}>{error.source}: {error.message}</li>)}</ul>}
      {governed.isError && <p>Governed assignments could not load.</p>}
      {connected.isError && <p>Connected sources could not load.</p>}
      {personal.isError && <p>Personal to-dos could not load.</p>}
    </div>}
    {busy && <p role="status" className="qms-inbox__loading">Checking assigned and connected responsibilities…</p>}
    {!busy && items.length > 0 && <div className="qms-daily-focus__list">
      {items.slice(0, 12).map(item => {
        const due = dateState(item.due_date);
        return <article className="qms-inbox__work-card" key={item.id}>
          <div className="qms-inbox__work-main">
            <div className="qms-inbox__eyebrow"><span>{item.source_label}</span><span>{item.scope}</span>
              <span>{item.status.replaceAll("_", " ").toLowerCase()}</span></div>
            <h3>{item.title}</h3>
            <p className="qms-connected-work__next"><strong>Next:</strong> {item.next_action}</p>
          </div>
          <div className={"qms-inbox__due" + (due.overdue ? " qms-inbox__due--overdue" : "")}>
            <strong>{due.label}</strong>
          </div>
          <div className="qms-inbox__item-actions">
            <Link to={item.route} className="qms-inbox__open">
              {item.scope === "Personal only" ? "Open to-dos" : "Open workflow"}
            </Link>
          </div>
        </article>;
      })}
    </div>}
    {!busy && !items.length && !incomplete && <div className="qms-inbox__empty" role="status">
      <h3>No outstanding work in the connected preview</h3>
      <p>There are no assigned or personal tasks in the first available source pages.
        This preview does not replace the complete governed registers.</p>
    </div>}
    <p className="qms-daily-focus__footnote">
      Showing up to 12 prioritised items from the first 30 records of each queue. Open the individual work areas
      for complete totals, full pagination, histories and decisions.
    </p>
  </section>;
}
