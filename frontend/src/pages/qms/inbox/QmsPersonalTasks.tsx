import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../../../services/apiClient";
import { getCachedUser } from "../../../services/auth";
import type { TaskItem, TaskStatus } from "../../../services/tasks";

type Draft = { title: string; description: string; due_at: string; reminder_at: string; priority: number; status: TaskStatus };
type PersonalPage = { items: TaskItem[]; total: number; offset: number; limit: number };
const emptyDraft: Draft = { title: "", description: "", due_at: "", reminder_at: "", priority: 3, status: "OPEN" };
const priorityNames: Record<number, string> = { 1: "Urgent", 2: "High", 3: "Normal", 4: "Low", 5: "Lowest" };
const pageSize = 25;
function localInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
function taskDraft(task: TaskItem): Draft {
  return { title: task.title, description: task.description || "", due_at: localInput(task.due_at),
    reminder_at: localInput(task.metadata_json?.reminder_at as string | undefined),
    priority: task.priority, status: task.status };
}
function displayDate(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not set" : date.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function QmsPersonalTasks({ amoCode }: { amoCode: string }) {
  const client = useQueryClient();
  const queryKey = ["qms-personal-tasks", amoCode, getCachedUser()?.id];
  const [editing, setEditing] = useState<TaskItem | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [quickTitle, setQuickTitle] = useState("");
  const [showCompleted, setShowCompleted] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const timer = window.setTimeout(() => { setDebouncedSearch(search); setOffset(0); }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);
  const query = useQuery({
    queryKey: [...queryKey, showCompleted, debouncedSearch, offset],
    queryFn: ({ signal }) => apiRequest<PersonalPage>(
      "/tasks/personal?" + new URLSearchParams({
        status: showCompleted ? "all" : "open", q: debouncedSearch,
        limit: String(pageSize), offset: String(offset),
      }), { signal, cacheTtlMs: 0 },
    ),
  });
  const mutation = useMutation({
    mutationFn: ({ task, values }: { task: TaskItem | "new"; values: Draft }) => apiRequest<TaskItem>(
      task === "new" ? "/tasks/personal" : "/tasks/personal/" + encodeURIComponent(task.id), {
        method: task === "new" ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...values, title: values.title.trim(),
          due_at: values.due_at ? new Date(values.due_at).toISOString() : null,
          reminder_at: values.reminder_at ? new Date(values.reminder_at).toISOString() : null,
          ...(task === "new" ? { status: undefined } : {}),
        }),
      },
    ),
    onSuccess: async () => {
      setEditing(null); setQuickTitle(""); setOffset(0);
      await client.invalidateQueries({ queryKey });
    },
  });
  const edit = (task: TaskItem | "new") => {
    mutation.reset();
    setDraft(task === "new" ? { ...emptyDraft } : taskDraft(task));
    setEditing(task);
  };
  const complete = (task: TaskItem) => {
    mutation.reset();
    mutation.mutate({ task, values: { ...taskDraft(task), status: task.status === "DONE" ? "OPEN" : "DONE" } });
  };
  const rows = query.data?.items || [];
  return <section className="qms-personal-tasks" aria-label="Personal to-do list">
    <header className="qms-personal-tasks__heading">
      <div><h2>My personal to-dos</h2>
        <p>Plan your follow-ups. Completing a personal task never closes a governed Quality record.</p></div>
      <button type="button" className="qms-inbox__primary" onClick={() => edit("new")}>New to-do</button>
    </header>
    <form className="qms-personal-tasks__quick-add" aria-label="Quick add personal task" onSubmit={event => {
      event.preventDefault();
      if (quickTitle.trim()) mutation.mutate({ task: "new", values: { ...emptyDraft, title: quickTitle.trim() } });
    }}>
      <label htmlFor="qms-personal-quick">Quick add</label><div>
        <input id="qms-personal-quick" value={quickTitle} maxLength={255}
          placeholder="Add a personal task…" onChange={event => setQuickTitle(event.target.value)} />
        <button type="submit" disabled={mutation.isPending || !quickTitle.trim()}>Add task</button>
      </div>
    </form>
    <div className="qms-personal-tasks__toolbar">
      <label>Find personal tasks<input type="search" value={search} maxLength={80}
        onChange={event => setSearch(event.target.value)} /></label>
      <label className="qms-personal-tasks__checkbox">
        <input type="checkbox" checked={showCompleted} onChange={event => {
          setShowCompleted(event.target.checked); setOffset(0);
        }} /> Show completed
      </label>
      <button type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh tasks</button>
    </div>
    {query.error || mutation.error ? <div className="qms-inbox__notice" role="alert">
      {(query.error || mutation.error)?.message}
      {query.error && <button type="button" onClick={() => void query.refetch()}>Retry</button>}
    </div> : null}
    {editing && <form className="qms-personal-tasks__editor" aria-label="Personal task editor"
      onSubmit={event => { event.preventDefault(); if (draft.title.trim()) mutation.mutate({ task: editing, values: draft }); }}>
      <h3>{editing === "new" ? "New personal to-do" : "Edit personal to-do"}</h3>
      <label>Task<input required maxLength={255} value={draft.title}
        onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>Notes<textarea maxLength={1024} value={draft.description}
        onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
      <label>Due date<input type="datetime-local" value={draft.due_at}
        onChange={event => setDraft({ ...draft, due_at: event.target.value })} /></label>
      <label>Email reminder<input type="datetime-local" value={draft.reminder_at}
        onChange={event => setDraft({ ...draft, reminder_at: event.target.value })} /></label>
      <label>Priority<select value={draft.priority} onChange={event => setDraft({ ...draft, priority: Number(event.target.value) })}>
        {Object.entries(priorityNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      {editing !== "new" && <label>Status<select value={draft.status}
        onChange={event => setDraft({ ...draft, status: event.target.value as TaskStatus })}>
        {["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"].map(value =>
          <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}
      </select></label>}
      <div className="qms-personal-tasks__editor-actions">
        <button type="submit" className="qms-inbox__primary" disabled={mutation.isPending || !draft.title.trim()}>
          {mutation.isPending ? "Saving…" : "Save task"}
        </button>
        <button type="button" disabled={mutation.isPending} onClick={() => setEditing(null)}>Cancel</button>
      </div>
    </form>}
    {query.isPending && <p role="status">Loading personal tasks…</p>}
    {query.data && !rows.length && <div className="qms-inbox__empty" role="status">
      <h3>{search ? "No personal tasks found" : showCompleted ? "No tasks to show" : "Plan your first follow-up"}</h3>
      <p>{search ? "Try another search term." : "Use quick add for a simple task, or New to-do to set dates and reminders."}</p>
    </div>}
    {!!rows.length && <div className="qms-personal-tasks__list" aria-label="Personal tasks">
      {rows.map(task => <article key={task.id}
        className={"qms-personal-tasks__item" + (["DONE", "CANCELLED"].includes(task.status) ? " qms-personal-tasks__item--done" : "")}>
        <div className="qms-personal-tasks__item-info"><h3>{task.title}</h3>
          {task.description && <p>{task.description}</p>}
          <div className="qms-personal-tasks__metadata">
            <span>{task.status.replaceAll("_", " ").toLowerCase()}</span>
            <span>Due: {displayDate(task.due_at)}</span>
            <span>Priority: {priorityNames[task.priority] || "Normal"}</span>
            {Boolean(task.metadata_json?.reminder_at) &&
              <span>Reminder: {displayDate(task.metadata_json?.reminder_at as string)}</span>}
          </div>
        </div>
        <div className="qms-personal-tasks__item-actions">
          <button type="button" disabled={mutation.isPending} onClick={() => edit(task)}>Edit</button>
          <button type="button" className="qms-inbox__primary"
            disabled={mutation.isPending || task.status === "CANCELLED"} onClick={() => complete(task)}>
            {task.status === "DONE" ? "Reopen" : task.status === "CANCELLED" ? "Cancelled" : "Complete"}
          </button>
        </div>
      </article>)}
    </div>}
    {!!query.data?.total && <nav className="qms-inbox__paging" aria-label="Personal task pages">
      <span>{offset + 1}–{Math.min(offset + rows.length, query.data.total)} of {query.data.total} tasks</span>
      <div><button type="button" disabled={!offset}
        onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button>
        <button type="button" disabled={offset + pageSize >= query.data.total}
          onClick={() => setOffset(offset + pageSize)}>Next</button></div>
    </nav>}
  </section>;
}
