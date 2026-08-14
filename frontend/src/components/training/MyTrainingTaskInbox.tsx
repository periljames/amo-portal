import React from "react";
import { CheckCircle2, ClipboardCheck, RefreshCw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { completeTrainingWorkflowStep, listMyTrainingTasks, transitionTrainingWorkflow } from "../../services/trainingOperating";

const MyTrainingTaskInbox: React.FC = () => {
  const client = useQueryClient();
  const tasks = useQuery({ queryKey: ["training", "my-task-inbox"], queryFn: listMyTrainingTasks });
  const refresh = () => client.invalidateQueries({ queryKey: ["training", "my-task-inbox"] });
  return <section className="page-section" id="training-task-inbox">
    <div className="card"><div className="card-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}><div><h2>My training tasks</h2><p className="text-muted">Attendance follow-up, induction, controlled forms, assessments and experience actions assigned to you.</p></div><button type="button" className="icon-button" aria-label="Refresh tasks" onClick={() => void tasks.refetch()}><RefreshCw size={17} /></button></div>
      {tasks.isLoading ? <p>Loading assigned work…</p> : null}
      {tasks.isError ? <div className="card card--error"><strong>Task source unavailable</strong><p>Your queue is Unknown, not empty.</p></div> : null}
      {tasks.data && !tasks.data.items.length ? <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 0" }}><CheckCircle2 size={20} /><span>No open controlled-form tasks.</span></div> : null}
      <div style={{ display: "grid", gap: 8 }}>{tasks.data?.items.map((task) => { const nextStep = task.steps.find((step) => step.status !== "COMPLETED"); return <article key={task.id} style={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: 12, border: "1px solid #dde4ee", borderRadius: 10 }}><ClipboardCheck size={19} /><div><strong>{task.title}</strong><small style={{ display: "block" }}>{task.workflow_type.replaceAll("_", " ")} · {task.due_at ? `due ${new Date(task.due_at).toLocaleDateString()}` : "no due date"} · {task.steps.filter((step) => step.status === "COMPLETED").length}/{task.steps.length} steps</small></div><div style={{ display: "flex", gap: 6 }}>{nextStep ? <button type="button" className="secondary-chip-btn" onClick={async () => { await completeTrainingWorkflowStep(task.id, nextStep.id, { completed: true }, "Authenticated self-service completion"); await refresh(); }}>Complete next step</button> : ["DRAFT", "RETURNED"].includes(task.status) ? <button type="button" className="primary-chip-btn" onClick={async () => { await transitionTrainingWorkflow(task.id, "SUBMITTED"); await refresh(); }}>Submit</button> : <span>{task.status}</span>}</div></article>; })}</div>
    </div>
  </section>;
};

export default MyTrainingTaskInbox;
