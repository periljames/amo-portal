import { useEffect, useState } from "react";
import { getRevisionWorkflow, transitionRevision, type ManualWorkflowPayload } from "../../services/manuals";
import { useManualRouteContext } from "./context";

const actions = [
  { id: "submit_department_review", label: "Submit Department Review" },
  { id: "approve_quality", label: "Approve Head of Quality" },
  { id: "approve_regulator", label: "Approve Regulator" },
  { id: "publish", label: "Publish" },
  { id: "archive", label: "Archive" },
];

export default function ManualWorkflowPage() {
  const { tenant, manualId, revId } = useManualRouteContext();
  const [workflow, setWorkflow] = useState<ManualWorkflowPayload | null>(null);
  const [comment, setComment] = useState("");

  const refresh = () => {
    if (!tenant || !manualId || !revId) return;
    getRevisionWorkflow(tenant, manualId, revId).then(setWorkflow).catch(() => setWorkflow(null));
  };

  useEffect(() => {
    refresh();
  }, [tenant, manualId, revId]);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Workflow Trail</h1>
      <div className="rounded border p-3 text-sm">
        <div><b>Status:</b> {workflow?.status || "-"}</div>
        <div><b>Authority approval required:</b> {workflow?.requires_authority_approval ? "Yes" : "No"}</div>
      </div>

      <div className="rounded border p-3 space-y-2">
        <textarea className="w-full rounded border p-2 text-sm" rows={3} placeholder="Workflow comment" value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="flex flex-wrap gap-2">
          {actions.map((a) => (
            <button
              key={a.id}
              className="rounded border px-2 py-1 text-xs"
              onClick={async () => {
                if (!tenant || !manualId || !revId) return;
                await transitionRevision(tenant, manualId, revId, a.id, comment || undefined);
                setComment("");
                refresh();
              }}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded border p-3">
        <h2 className="font-medium mb-2">Audit history</h2>
        <ul className="space-y-2 text-sm">
          {(workflow?.history || []).map((entry, idx) => (
            <li key={`${entry.at}-${idx}`} className="rounded border p-2">
              <div>{entry.action}</div>
              <div className="text-xs text-slate-500">{entry.at} · actor: {entry.actor_id || "system"}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
