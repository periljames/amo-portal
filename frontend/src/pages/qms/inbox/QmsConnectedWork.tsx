import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { apiRequest, qmsPath } from "../../../services/apiClient";

type ConnectedItem = {
  id: string; record_id: string; source: string; source_label: string;
  title: string; status: string; due_date: string | null; route: string;
  scope: "ASSIGNED" | "SHARED_REVIEW"; next_action: string; blocked: boolean;
};
type ConnectedPage = {
  items: ConnectedItem[]; total: number; limit: number; offset: number;
  source_errors: Array<{ source: string; message: string }>;
};
const categories = [
  ["all", "All linked work"], ["overdue", "Overdue"], ["due-today", "Due today"], ["upcoming", "Upcoming"],
] as const;
const sources = [
  ["", "All connected sources"], ["training-steps", "Training workflow"],
  ["training-remedial", "Remedial training"], ["document-reviews", "Controlled document reviews"],
  ["document-acknowledgements", "Document acknowledgements"],
  ["provider-invitations", "External provider invitations"],
  ["provider-approvals", "External provider account approvals"],
] as const;
function dueState(value: string | null) {
  if (!value) return { date: "No set deadline", urgency: "", overdue: false };
  const raw = value.slice(0, 10);
  const date = new Date(raw + "T00:00:00");
  if (Number.isNaN(date.getTime())) return { date: raw, urgency: "", overdue: false };
  const now = new Date();
  const days = Math.round((Date.UTC(date.getFullYear(),date.getMonth(),date.getDate()) -
    Date.UTC(now.getFullYear(),now.getMonth(),now.getDate())) / 86400000);
  return {
    date: date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }),
    urgency: days < 0 ? String(-days) + " days overdue" : days === 0 ? "Due today" :
      days === 1 ? "Due tomorrow" : "Due in " + days + " days",
    overdue: days < 0,
  };
}

export default function QmsConnectedWork({ amoCode }: { amoCode: string }) {
  const [params, setParams] = useSearchParams();
  const source = params.get("related_source") || "";
  const category = categories.some(([name]) => name === params.get("related_category"))
    ? (params.get("related_category") || "all") : "all";
  const q = params.get("related_q") || "";
  const offset = Math.max(0, Number(params.get("related_offset")) || 0);
  const [draftSearch, setDraftSearch] = useState(q);
  function update(values: Record<string, string | null>) {
    setParams(previous => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(values)) {
        if (!value) next.delete(key); else next.set(key, value);
      }
      return next;
    }, { replace: true });
  }
  useEffect(() => { setDraftSearch(q); }, [q]);
  useEffect(() => {
    if (draftSearch === q) return;
    const timer = window.setTimeout(() => update({ related_q: draftSearch, related_offset: null }), 300);
    return () => window.clearTimeout(timer);
    // URL is the persisted, debounced search state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftSearch, q]);
  const work = useQuery({
    queryKey: ["qms-connected-work", amoCode, source, category, q, offset],
    queryFn: ({ signal }) => apiRequest<ConnectedPage>(
      qmsPath(amoCode, "/work-inbox/related") + "?" + new URLSearchParams({
        source, category, q, offset: String(offset), limit: "30",
      }), { cacheTtlMs: 0, signal },
    ),
  });
  return <section className="qms-connected-work" aria-label="Connected Quality work">
    <header className="qms-personal-tasks__heading">
      <div><h2>Connected responsibilities</h2><p>
        Training, controlled documents and authorised vendor review decisions, linked to their governing modules.
        These records are not personal to-dos and cannot be closed from the inbox.
      </p></div>
      <button type="button" disabled={work.isFetching} onClick={() => void work.refetch()}>
        Refresh connected work
      </button>
    </header>
    <div className="qms-connected-work__categories" aria-label="Due date category">
      {categories.map(([value, label]) =>
        <button key={value} type="button" aria-pressed={value === category} onClick={() =>
          update({ related_category: value === "all" ? null : value, related_offset: null })
        }>{label}</button>)}
    </div>
    <div className="qms-inbox__filters qms-connected-work__filters">
      <label>Search related work<input type="search" value={draftSearch} maxLength={80}
        placeholder="Search titles" onChange={event => setDraftSearch(event.target.value)} /></label>
      <label>Connected source<select value={source} onChange={event =>
        update({ related_source: event.target.value, related_offset: null })}>
        {sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
    </div>
    {work.isPending && <p role="status" className="qms-inbox__loading">Loading connected responsibilities…</p>}
    {work.isError && <p role="alert" className="qms-inbox__notice">
      Connected work could not be loaded: {work.error.message}
      <button type="button" onClick={() => void work.refetch()}>Retry</button>
    </p>}
    {!!work.data?.source_errors.length && <div role="alert" className="qms-inbox__notice">
      <strong>Some connected sources are unavailable. These results are incomplete.</strong>
      <ul>{work.data.source_errors.map(row => <li key={row.source}>{row.source}: {row.message}</li>)}</ul>
    </div>}
    {!!work.data?.items.length && <div className="qms-connected-work__list" aria-label="Connected responsibilities">
      {work.data.items.map(item => {
        const due = dueState(item.due_date);
        return <article className="qms-inbox__work-card" key={item.id}>
          <div className="qms-inbox__work-main">
            <div className="qms-inbox__eyebrow"><span>{item.source_label}</span>
              <span>{item.scope === "SHARED_REVIEW" ? "Shared decision queue" : "Assigned to you"}</span>
              <span>{item.status.replaceAll("_", " ").toLowerCase()}</span></div>
            <h3>{item.title}</h3>
            <p className="qms-connected-work__next">
              <strong>{item.blocked ? "Waiting on workflow" : "Next step"}:</strong> {item.next_action}
            </p>
          </div>
          <div className={"qms-inbox__due" + (due.overdue ? " qms-inbox__due--overdue" : "")}>
            <span>{due.date}</span>{due.urgency && <strong>{due.urgency}</strong>}
          </div>
          <div className="qms-inbox__item-actions">
            <Link className="qms-inbox__open" to={item.route}>Open source workspace</Link>
          </div>
        </article>;
      })}
    </div>}
    {work.data && !work.data.items.length && <div className="qms-inbox__empty" role="status">
      <h3>{work.data.source_errors.length ? "No results from available sources" : "No matching connected responsibilities"}</h3>
      <p>Only assigned or specifically authorised Quality work is shown. An unavailable source is not treated as zero work.</p>
      {(source || q || category !== "all") &&
        <button type="button" onClick={() => { setDraftSearch(""); update({
          related_source: null, related_q: null, related_category: null, related_offset: null,
        }); }}>Clear filters</button>}
    </div>}
    {!!work.data?.total && <nav className="qms-inbox__paging" aria-label="Connected work pages">
      <span>{offset + 1}–{Math.min(offset + work.data.items.length, work.data.total)} of {work.data.total} responsibilities</span>
      <div><button type="button" disabled={!offset}
        onClick={() => update({ related_offset: String(Math.max(0, offset - work.data!.limit)) })}>Previous</button>
      <button type="button" disabled={offset + work.data.limit >= work.data.total}
        onClick={() => update({ related_offset: String(offset + work.data!.limit) })}>Next</button></div>
    </nav>}
  </section>;
}
