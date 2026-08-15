import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, Link2, Plus, RefreshCw, Trash2, X } from "lucide-react";

import {
  allocateRosterAssignmentToTask,
  deleteRosterTaskLink,
  getPlanningBoard,
  listRosterTaskLinks,
} from "../../../services/rostering";
import type { RosterAssignmentRead } from "../../../types/rostering";
import { errorMessage } from "../rosterUi";
import { EmptyState, StatusPill } from "./RosterShell";

export function RosterTaskAllocationEditor({ assignment, editable }: {
  assignment: RosterAssignmentRead;
  editable: boolean;
}) {
  const queryClient = useQueryClient();
  const [taskId, setTaskId] = useState("");
  const [hours, setHours] = useState("");
  const [role, setRole] = useState("SUPPORT");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeReason, setRemoveReason] = useState("");
  const from = assignment.starts_at.slice(0, 10);
  const to = assignment.ends_at.slice(0, 10);

  const linksQuery = useQuery({
    queryKey: ["rostering", "assignment", assignment.id, "task-links"],
    queryFn: () => listRosterTaskLinks(assignment.id),
    enabled: !assignment.id.startsWith("offline-"),
    staleTime: 30_000,
  });
  const demandQuery = useQuery({
    queryKey: ["rostering", "assignment", assignment.id, "task-demand", from, to, assignment.base_station_id],
    queryFn: () => getPlanningBoard({ from, to, base_station_id: assignment.base_station_id || null }),
    enabled: editable,
    staleTime: 60_000,
  });
  const linkedTaskIds = useMemo(() => new Set((linksQuery.data || []).map((row) => row.task_id)), [linksQuery.data]);
  const tasks = useMemo(
    () => (demandQuery.data?.tasks || []).filter((task) => !linkedTaskIds.has(task.task_id)),
    [demandQuery.data?.tasks, linkedTaskIds],
  );
  const selectedTaskId = taskId || String(tasks[0]?.task_id || "");

  const refresh = async () => {
    await Promise.all([
      linksQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["rostering", "planner"] }),
    ]);
  };
  const allocate = async () => {
    if (!selectedTaskId) return;
    setBusy(true); setError(null);
    try {
      await allocateRosterAssignmentToTask(assignment.id, {
        task_id: Number(selectedTaskId),
        role_on_task: role,
        task_assignment_status: "ASSIGNED",
        allocated_start: assignment.starts_at,
        allocated_end: assignment.ends_at,
        allocated_hours: hours ? Number(hours) : null,
      });
      setTaskId(""); setHours("");
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!removingId || removeReason.trim().length < 5) return;
    setBusy(true); setError(null);
    try {
      await deleteRosterTaskLink(assignment.id, removingId, removeReason.trim());
      setRemovingId(null); setRemoveReason("");
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="wr-task-editor" aria-labelledby={`task-allocation-${assignment.id}`}>
      <div className="wr-task-editor__head"><div><span className="wr-eyebrow">Work allocation</span><h3 id={`task-allocation-${assignment.id}`}>Linked maintenance tasks</h3></div><BriefcaseBusiness size={18} /></div>
      {linksQuery.isPending ? <div className="wr-task-editor__loading"><RefreshCw size={14} className="is-spinning" /> Loading task links…</div> : null}
      <div className="wr-task-editor__links">
        {(linksQuery.data || []).map((link) => <article key={link.id}><Link2 size={14} /><div><strong>{link.task_code || `Task ${link.task_id}`}</strong><span>{link.wo_number || "Work order"} · {link.task_title || "Allocated task"}</span><small>{link.allocated_hours ?? "Calculated"}h · {link.role_on_task.replace(/_/g, " ")}</small></div><StatusPill value={link.task_assignment_status} />{editable ? <button type="button" className="wr-icon-button is-danger" aria-label={`Remove ${link.task_code || `task ${link.task_id}`}`} onClick={() => { setRemovingId(link.id); setRemoveReason(""); }}><Trash2 size={14} /></button> : null}</article>)}
      </div>
      {!linksQuery.isPending && !(linksQuery.data || []).length ? <EmptyState title="No linked maintenance task" description="Allocate task demand to this duty when productive work is known." /> : null}

      {editable ? <div className="wr-task-editor__create"><label className="wr-span-2"><span>Open task</span><select value={selectedTaskId} disabled={demandQuery.isPending || !tasks.length} onChange={(event) => setTaskId(event.target.value)}><option value="">{demandQuery.isPending ? "Loading task demand…" : "Select task"}</option>{tasks.slice(0, 250).map((task) => <option key={task.task_id} value={task.task_id}>{task.wo_number} · {task.task_code || `Task ${task.task_id}`} · {task.title}</option>)}</select></label><label><span>Role</span><select value={role} onChange={(event) => setRole(event.target.value)}><option value="LEAD">Lead</option><option value="SUPPORT">Support</option><option value="INSPECTOR">Inspector</option></select></label><label><span>Hours</span><input type="number" min="0" step="0.25" value={hours} onChange={(event) => setHours(event.target.value)} placeholder="Auto" /></label><button type="button" className="wr-button wr-button--secondary wr-span-2" disabled={busy || !selectedTaskId} onClick={() => void allocate()}><Plus size={15} /> Allocate task</button></div> : null}
      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}

      {removingId ? <div className="wr-task-editor__remove"><div><strong>Remove task link</strong><button type="button" className="wr-icon-button" aria-label="Cancel task unlink" onClick={() => setRemovingId(null)}><X size={14} /></button></div><label><span>Audited reason</span><textarea rows={2} value={removeReason} onChange={(event) => setRemoveReason(event.target.value)} /></label><button type="button" className="wr-button wr-button--danger-ghost" disabled={busy || removeReason.trim().length < 5} onClick={() => void remove()}><Trash2 size={14} /> Remove link</button></div> : null}
    </section>
  );
}
