import { useCallback, useEffect, useMemo, useState } from "react";

import { getCachedUser } from "../../services/auth";
import {
  getCoordinatorTrainingWorkspace,
  getManagerTrainingWorkspace,
} from "../../services/trainingWorkflowCompletion";
import TrainingPerson360Drawer from "./TrainingPerson360Drawer";

type TeamHealth = {
  people: number;
  current: number;
  due_soon: number;
  overdue: number;
  incomplete: number;
};

type WorkspaceAction = {
  priority?: number;
  type?: string;
  user_id?: string;
  person?: string;
  course?: string;
  status?: string;
  due?: string | null;
  age_days?: number;
};

type WorkspacePayload = {
  workspace: "MANAGER" | "COORDINATOR";
  generated_at?: string;
  team_health: TeamHealth;
  action_queue: WorkspaceAction[];
};

const coordinatorRoles = new Set(["SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER"]);
const managerRoles = new Set([
  "SUPERUSER",
  "AMO_ADMIN",
  "ACCOUNTABLE_EXECUTIVE",
  "BASE_MAINTENANCE_MANAGER",
  "LINE_MAINTENANCE_MANAGER",
  "WORKSHOP_MANAGER",
  "QUALITY_MANAGER",
  "SAFETY_MANAGER",
  "FINANCE_MANAGER",
  "STORES_MANAGER",
]);

function asWorkspace(value: Record<string, unknown>): WorkspacePayload {
  const health = (value.team_health || {}) as Partial<TeamHealth>;
  return {
    workspace: value.workspace === "COORDINATOR" ? "COORDINATOR" : "MANAGER",
    generated_at: typeof value.generated_at === "string" ? value.generated_at : undefined,
    team_health: {
      people: Number(health.people || 0),
      current: Number(health.current || 0),
      due_soon: Number(health.due_soon || 0),
      overdue: Number(health.overdue || 0),
      incomplete: Number(health.incomplete || 0),
    },
    action_queue: Array.isArray(value.action_queue) ? (value.action_queue as WorkspaceAction[]) : [],
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Team Training workspace could not be loaded.";
}

const TrainingRoleWorkspacePanel = () => {
  const user = getCachedUser();
  const mode = useMemo<"COORDINATOR" | "MANAGER" | null>(() => {
    const role = String(user?.role || "").toUpperCase();
    if (coordinatorRoles.has(role)) return "COORDINATOR";
    if (managerRoles.has(role)) return "MANAGER";
    return null;
  }, [user?.role]);
  const [workspace, setWorkspace] = useState<WorkspacePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [person360UserId, setPerson360UserId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!mode) return;
    setLoading(true);
    setError(null);
    try {
      const raw = mode === "COORDINATOR"
        ? await getCoordinatorTrainingWorkspace()
        : await getManagerTrainingWorkspace();
      setWorkspace(asWorkspace(raw));
    } catch (err: unknown) {
      setWorkspace(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!mode) return null;

  const health = workspace?.team_health;
  return (
    <>
      <section className="page-section" id="training-role-workspace" aria-labelledby="training-role-workspace-title">
        <div className="card">
          <div className="card-header" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
            <div>
              <h2 id="training-role-workspace-title">{mode === "COORDINATOR" ? "Training coordination" : "Team Training"}</h2>
              <p className="text-muted">
                {mode === "COORDINATOR"
                  ? "Tenant-wide compliance health and governed Training action queue."
                  : "Your department's compliance health and items requiring management attention."}
              </p>
            </div>
            <button type="button" className="secondary-chip-btn" onClick={() => void load()} disabled={loading}>
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          {error ? <div className="card card--error"><p>{error}</p></div> : null}
          {health ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10, marginBottom: 14 }}>
              <div><strong>{health.people}</strong><div className="text-muted">People</div></div>
              <div><strong>{health.current}</strong><div className="text-muted">Current</div></div>
              <div><strong>{health.due_soon}</strong><div className="text-muted">Due soon</div></div>
              <div><strong>{health.overdue}</strong><div className="text-muted">Overdue</div></div>
              <div><strong>{health.incomplete}</strong><div className="text-muted">Incomplete</div></div>
            </div>
          ) : null}

          {workspace ? (
            <div>
              <h3>Action queue</h3>
              {workspace.action_queue.length ? (
                <div style={{ display: "grid", gap: 8 }}>
                  {workspace.action_queue.slice(0, 20).map((item, index) => (
                    <article key={`${item.type || "ACTION"}:${item.user_id || index}:${item.course || index}`} style={{ border: "1px solid #dde4ee", borderRadius: 10, padding: 10 }}>
                      <div style={{ display: "flex", gap: 8, justifyContent: "space-between", flexWrap: "wrap" }}>
                        <strong>{item.type || "Training action"}</strong>
                        <span className="badge badge--neutral">{item.status || "ACTION REQUIRED"}</span>
                      </div>
                      <div>{item.person || "Team member"}{item.course ? ` · ${item.course}` : ""}</div>
                      <small className="text-muted">
                        {item.due ? `Due ${new Date(item.due).toLocaleDateString()}` : item.age_days != null ? `${item.age_days} day(s) in queue` : "Review required"}
                      </small>
                      {item.user_id ? <div style={{ marginTop: 8 }}><button type="button" className="secondary-chip-btn" onClick={() => setPerson360UserId(item.user_id || null)}>Open Person 360</button></div> : null}
                    </article>
                  ))}
                  {workspace.action_queue.length > 20 ? <p className="text-muted">Showing the highest-priority 20 of {workspace.action_queue.length} actions.</p> : null}
                </div>
              ) : <p className="text-muted">No governed Training actions are currently waiting in this workspace.</p>}
            </div>
          ) : loading ? <p>Loading team Training workspace…</p> : null}
        </div>
      </section>
      <TrainingPerson360Drawer userId={person360UserId} isOpen={Boolean(person360UserId)} onClose={() => setPerson360UserId(null)} />
    </>
  );
};

export default TrainingRoleWorkspacePanel;
