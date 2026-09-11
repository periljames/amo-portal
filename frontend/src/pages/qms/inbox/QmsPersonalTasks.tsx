import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";
import { apiRequest } from "../../../services/apiClient";
import { getCachedUser } from "../../../services/auth";
import { listMyTasks, type TaskItem, type TaskStatus } from "../../../services/tasks";
import QmsWorkspaceGrid from "../components/QmsWorkspaceGrid";

type Draft = { title: string; description: string; due_at: string; reminder_at: string; priority: number; status: TaskStatus };
const emptyDraft: Draft = { title: "", description: "", due_at: "", reminder_at: "", priority: 3, status: "OPEN" };
function localInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
function taskDraft(task: TaskItem): Draft {
  return { title: task.title, description: task.description || "", due_at: localInput(task.due_at),
    reminder_at: localInput(task.metadata_json?.reminder_at as string | undefined), priority: task.priority, status: task.status };
}

export default function QmsPersonalTasks({ amoCode }: { amoCode: string }) {
  const client = useQueryClient();
  const queryKey = ["qms-personal-tasks", amoCode, getCachedUser()?.id];
  const query = useQuery({ queryKey, queryFn: listMyTasks });
  const [editing, setEditing] = useState<TaskItem | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [showCompleted, setShowCompleted] = useState(false);
  const mutation = useMutation({
    mutationFn: ({ task, values }: { task: TaskItem | "new"; values: Draft }) => apiRequest<TaskItem>(
      task === "new" ? "/tasks/personal" : `/tasks/personal/${encodeURIComponent(task.id)}`,
      { method: task === "new" ? "POST" : "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        ...values, title: values.title.trim(), due_at: values.due_at ? new Date(values.due_at).toISOString() : null,
        reminder_at: values.reminder_at ? new Date(values.reminder_at).toISOString() : null,
        ...(task === "new" ? { status: undefined } : {}),
      }) },
    ),
    onSuccess: async () => { setEditing(null); await client.invalidateQueries({ queryKey }); },
  });
  const rows = useMemo(() => (query.data || []).filter(task => task.entity_type === "quality_personal"
    && (showCompleted || !["DONE", "CANCELLED"].includes(task.status))), [query.data, showCompleted]);
  const edit = (task: TaskItem) => { mutation.reset(); setDraft(taskDraft(task)); setEditing(task); };
  const columns: ColDef<TaskItem>[] = [
    { headerName: "To-do", field: "title", minWidth: 240, flex: 2 },
    { headerName: "Status", field: "status" },
    { headerName: "Due", field: "due_at", valueFormatter: ({ value }) => value ? new Date(value).toLocaleString() : "No deadline" },
    { headerName: "Priority", field: "priority", valueFormatter: ({ value }) => ({ 1: "Urgent", 2: "High", 3: "Normal", 4: "Low", 5: "Lowest" })[value as 1] || "Normal" },
    { headerName: "Reminder", valueGetter: ({ data }) => data?.metadata_json?.reminder_at || null,
      valueFormatter: ({ value }) => value ? new Date(value).toLocaleString() : "None" },
    { headerName: "Actions", minWidth: 180, sortable: false, filter: false, cellRenderer: ({ data }: { data?: TaskItem }) => data ? <div className="qms-workspace-row-actions">
      <button type="button" disabled={mutation.isPending} onClick={() => edit(data)}>Edit</button>
      <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate({ task: data, values: { ...taskDraft(data), status: data.status === "DONE" ? "OPEN" : "DONE" } })}>{data.status === "DONE" ? "Reopen" : "Complete"}</button>
    </div> : null },
  ];
  return <section className="qms-personal-tasks" aria-label="Personal to-do list">
    <header className="qms-workspace-heading"><div><h2>My to-do list</h2><p>Plan follow-ups and set email reminders.</p></div><div className="qms-workspace-actions">
      <label><input type="checkbox" checked={showCompleted} onChange={event => setShowCompleted(event.target.checked)} /> Show completed</label>
      <button type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh tasks</button>
      <button type="button" onClick={() => { mutation.reset(); setDraft(emptyDraft); setEditing("new"); }}>New to-do</button>
    </div></header>
    {query.error || mutation.error ? <p role="alert">{(query.error || mutation.error)?.message}</p> : null}
    {editing ? <form className="qms-workspace-form" onSubmit={event => { event.preventDefault(); if (draft.title.trim()) mutation.mutate({ task: editing, values: draft }); }}>
      <label>Task<input required maxLength={255} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>Notes<textarea maxLength={1024} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
      <label>Due date<input type="datetime-local" value={draft.due_at} onChange={event => setDraft({ ...draft, due_at: event.target.value })} /></label>
      <label>Email reminder<input type="datetime-local" value={draft.reminder_at} onChange={event => setDraft({ ...draft, reminder_at: event.target.value })} /></label>
      <label>Priority<select value={draft.priority} onChange={event => setDraft({ ...draft, priority: Number(event.target.value) })}>{["Urgent", "High", "Normal", "Low", "Lowest"].map((label, index) => <option key={label} value={index + 1}>{label}</option>)}</select></label>
      {editing !== "new" ? <label>Status<select value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value as TaskStatus })}>{["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"].map(value => <option key={value}>{value}</option>)}</select></label> : null}
      <div className="qms-workspace-actions"><button type="submit" disabled={mutation.isPending || !draft.title.trim()}>{mutation.isPending ? "Saving…" : "Save task"}</button><button type="button" disabled={mutation.isPending} onClick={() => setEditing(null)}>Cancel</button></div>
    </form> : null}
    <QmsWorkspaceGrid<TaskItem> rowData={rows} columnDefs={columns} getRowId={({ data }) => data.id} loading={query.isLoading} onRowDoubleClicked={({ data }) => { if (data && !mutation.isPending) edit(data); }} pagination paginationPageSize={20} paginationPageSizeSelector={[20, 50, 100]} />
  </section>;
}
