import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
import {
  disableAdminUser,
  enableAdminUser,
  forceAdminUserPasswordReset,
  getAdminUserWorkspace,
  notifyAdminUser,
  revokeAdminUserAccess,
  scheduleAdminUserReview,
  updateAdminUser,
} from "../services/adminUsers";
import type { AccountRole, AdminUserUpdatePayload } from "../services/adminUsers";
import "../styles/admin-user-management.css";

type ProfileTab = "profile" | "tasks" | "permissions" | "activity" | "login";

const ROLE_OPTIONS: AccountRole[] = [
  "SUPERUSER",
  "AMO_ADMIN",
  "QUALITY_MANAGER",
  "SAFETY_MANAGER",
  "PLANNING_ENGINEER",
  "PRODUCTION_ENGINEER",
  "CERTIFYING_ENGINEER",
  "CERTIFYING_TECHNICIAN",
  "TECHNICIAN",
  "AUDITOR",
  "STORES",
  "VIEW_ONLY",
];

const formatDateTime = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};

const AdminUserDetailPage: React.FC = () => {
  const { amoCode, userId } = useParams<{ amoCode?: string; userId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ctx = getContext();
  const resolvedAmoCode = amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const resolvedUserId = userId ?? "";

  const [activeTab, setActiveTab] = useState<ProfileTab>("profile");
  const [selectedRole, setSelectedRole] = useState<AccountRole | "">("");
  const [notifySubject, setNotifySubject] = useState("QMS user notification");
  const [notifyMessage, setNotifyMessage] = useState("");
  const [reviewTitle, setReviewTitle] = useState("Authorization review");
  const [reviewDueAt, setReviewDueAt] = useState("");

  const workspaceQuery = useQuery({
    queryKey: ["admin-user-workspace", resolvedUserId],
    queryFn: () => getAdminUserWorkspace(resolvedUserId),
    enabled: !!resolvedUserId,
  });

  const workspace = workspaceQuery.data;
  const user = workspace?.user;

  const refreshWorkspace = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin-user-workspace", resolvedUserId] });
    await queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
  };

  const updateUserMutation = useMutation({
    mutationFn: (payload: AdminUserUpdatePayload) => updateAdminUser(resolvedUserId, payload),
    onSuccess: refreshWorkspace,
  });

  const commandMutation = useMutation({
    mutationFn: async (command: "disable" | "enable" | "revoke" | "reset") => {
      if (command === "disable") return disableAdminUser(resolvedUserId);
      if (command === "enable") return enableAdminUser(resolvedUserId);
      if (command === "revoke") return revokeAdminUserAccess(resolvedUserId);
      return forceAdminUserPasswordReset(resolvedUserId);
    },
    onSuccess: refreshWorkspace,
  });

  const notifyMutation = useMutation({
    mutationFn: () => notifyAdminUser(resolvedUserId, { subject: notifySubject.trim(), message: notifyMessage.trim() }),
    onSuccess: async () => {
      setNotifyMessage("");
      await refreshWorkspace();
    },
  });

  const reviewMutation = useMutation({
    mutationFn: () => scheduleAdminUserReview(resolvedUserId, { title: reviewTitle.trim(), due_at: reviewDueAt || undefined, priority: 2 }),
    onSuccess: refreshWorkspace,
  });

  const currentStatus = useMemo(() => workspace?.presence_display.status_label || "Offline", [workspace]);
  const currentLastSeenPrimary = useMemo(() => {
    if (!workspace || !user) return "Never seen";
    if (workspace.presence_display.last_seen_label === "Active now") return "Active now";
    if (workspace.presence_display.last_seen_label === "Never seen") return "Never seen";
    const seen = workspace.presence_display.last_seen_at || user.last_login_at;
    if (!seen) return "Never seen";
    const dt = new Date(seen);
    if (Number.isNaN(dt.getTime())) return "Never seen";
    const deltaMs = Date.now() - dt.getTime();
    if (deltaMs < 60_000) return "Just now";
    const mins = Math.floor(deltaMs / 60_000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  }, [workspace, user]);
  const currentLastSeenSecondary = useMemo(() => {
    if (!workspace || !user) return null;
    if (workspace.presence_display.status_label === "Online") return null;
    if (currentLastSeenPrimary === "Never seen") return null;
    return formatDateTime(workspace.presence_display.last_seen_at || user.last_login_at);
  }, [workspace, user, currentLastSeenPrimary]);

  return (
    <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment="admin-users">
      <div className="admin-user-profile">
        <div className="aum-header">
          <div>
            <p className="aum-eyebrow">User Profile</p>
            <h1>{user?.full_name || "User profile"}</h1>
            <p className="aum-subtitle">Single-page review for profile details, assigned tasks, permissions, activity, and login history.</p>
          </div>
          <div className="aum-header-actions">
            <button type="button" className="aum-button aum-button--secondary" onClick={() => navigate(`/maintenance/${resolvedAmoCode}/admin/users`)}>
              Back to users
            </button>
            <button type="button" className="aum-button aum-button--primary" onClick={() => workspaceQuery.refetch()}>
              Refresh
            </button>
          </div>
        </div>

        {workspaceQuery.isLoading ? (
          <div className="aum-panel"><div className="aum-empty">Loading user workspace…</div></div>
        ) : workspaceQuery.error ? (
          <div className="aum-panel"><div className="aum-empty">{(workspaceQuery.error as Error).message}</div></div>
        ) : workspace && user ? (
          <>
            <section className="aum-profile-hero aum-panel">
              <div>
                <h2>{user.full_name}</h2>
                <p>{user.email}</p>
                <div className="aum-chip-row">
                  <span className={`aum-status ${currentStatus === "Inactive" ? "is-inactive" : currentStatus === "Online" ? "is-online" : workspace.presence.state === "away" ? "is-away" : "is-offline"}`}>{currentStatus}</span>
                  <span className="aum-chip">Title: {workspace.display_title}</span>
                  <span className="aum-chip">Department: {workspace.department_name || "—"}</span>
                  <span className="aum-chip">Last seen: {currentLastSeenPrimary}</span>
                </div>
                {currentLastSeenSecondary ? <p className="aum-muted">{currentLastSeenSecondary}</p> : null}
              </div>
              <div className="aum-profile-metrics">
                {workspace.metrics.map((metric) => (
                  <div key={metric.key} className="aum-metric-card compact">
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </div>
                ))}
              </div>
            </section>

            <div className="aum-tabs" role="tablist" aria-label="User profile sections">
              {([
                ["profile", "Profile details"],
                ["tasks", "Tasks assigned"],
                ["permissions", "Project permissions"],
                ["activity", "Activity log"],
                ["login", "Login record"],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`aum-tab ${activeTab === key ? "is-active" : ""}`}
                  onClick={() => setActiveTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            {activeTab === "profile" && (
              <section className="aum-three-col">
                <article className="aum-panel">
                  <h2>Profile details</h2>
                  <div className="aum-definition-list">
                    <div><span>First name</span><strong>{user.first_name}</strong></div>
                    <div><span>Last name</span><strong>{user.last_name}</strong></div>
                    <div><span>Staff code</span><strong>{user.staff_code}</strong></div>
                    <div><span>Title</span><strong>{workspace.display_title}</strong></div>
                    <div><span>Phone</span><strong>{user.phone || "—"}</strong></div>
                    <div><span>Secondary phone</span><strong>{user.secondary_phone || "—"}</strong></div>
                    <div><span>Department</span><strong>{workspace.department_name || "—"}</strong></div>
                  </div>
                </article>
                <article className="aum-panel">
                  <h2>Access & commands</h2>
                  <div className="aum-stack">
                    <label className="aum-field">
                      <span>Role</span>
                      <select className="aum-select" value={selectedRole || user.role} onChange={(event) => setSelectedRole(event.target.value as AccountRole)}>
                        {ROLE_OPTIONS.map((role) => <option key={role} value={role}>{role}</option>)}
                      </select>
                    </label>
                    <button type="button" className="aum-button aum-button--primary" onClick={() => updateUserMutation.mutate({ role: (selectedRole || user.role) as AccountRole })}>
                      Update role
                    </button>
                    <div className="aum-row-actions wrap">
                      <button type="button" className="aum-button aum-button--ghost" onClick={() => commandMutation.mutate(user.is_active ? "disable" : "enable")}>
                        {user.is_active ? "Disable" : "Enable"}
                      </button>
                      <button type="button" className="aum-button aum-button--ghost" onClick={() => commandMutation.mutate("revoke")}>Revoke access</button>
                      <button type="button" className="aum-button aum-button--ghost" onClick={() => commandMutation.mutate("reset")}>Force password reset</button>
                    </div>
                  </div>
                </article>
                <article className="aum-panel">
                  <h2>Groups</h2>
                  <div className="aum-chip-row">
                    {workspace.groups.map((group) => (
                      <span key={`${group.kind}-${group.value || group.label}`} className="aum-chip">{group.label}: {group.value || "—"}</span>
                    ))}
                  </div>
                  <div className="aum-stack top-gap">
                    <label className="aum-field">
                      <span>Notification subject</span>
                      <input className="aum-input" value={notifySubject} onChange={(event) => setNotifySubject(event.target.value)} />
                    </label>
                    <label className="aum-field">
                      <span>Notification message</span>
                      <textarea className="aum-input aum-textarea" value={notifyMessage} onChange={(event) => setNotifyMessage(event.target.value)} rows={4} />
                    </label>
                    <button type="button" className="aum-button aum-button--primary" onClick={() => notifyMutation.mutate()} disabled={!notifySubject.trim() || !notifyMessage.trim()}>
                      Send notification
                    </button>
                  </div>
                </article>
              </section>
            )}

            {activeTab === "tasks" && (
              <section className="aum-panel">
                <div className="aum-panel-header"><div><h2>Tasks assigned</h2><p>Operational tasks owned by this user.</p></div></div>
                <div className="aum-table-wrap">
                  <table className="aum-table">
                    <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Due</th><th>Updated</th></tr></thead>
                    <tbody>
                      {workspace.tasks.length === 0 ? (
                        <tr><td colSpan={5} className="aum-empty-row">No tasks assigned.</td></tr>
                      ) : workspace.tasks.map((task) => (
                        <tr key={task.id}>
                          <td>{task.title}</td>
                          <td>{task.status}</td>
                          <td>{task.priority}</td>
                          <td>{formatDateTime(task.due_at)}</td>
                          <td>{formatDateTime(task.updated_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {activeTab === "permissions" && (
              <section className="aum-panel">
                <div className="aum-panel-header"><div><h2>Project permissions</h2><p>Current authorisations and operational scope linked to this account.</p></div></div>
                <div className="aum-table-wrap">
                  <table className="aum-table">
                    <thead><tr><th>Code</th><th>Permission</th><th>Scope</th><th>Effective</th><th>Expires</th><th>Valid</th></tr></thead>
                    <tbody>
                      {workspace.permissions.length === 0 ? (
                        <tr><td colSpan={6} className="aum-empty-row">No permissions recorded.</td></tr>
                      ) : workspace.permissions.map((permission) => (
                        <tr key={permission.id}>
                          <td>{permission.code}</td>
                          <td>{permission.label}</td>
                          <td>{permission.scope_text || permission.maintenance_scope || "—"}</td>
                          <td>{permission.effective_from}</td>
                          <td>{permission.expires_at || "—"}</td>
                          <td>{permission.is_currently_valid ? "Current" : "Expired / Revoked"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="aum-stack top-gap">
                  <label className="aum-field">
                    <span>Review title</span>
                    <input className="aum-input" value={reviewTitle} onChange={(event) => setReviewTitle(event.target.value)} />
                  </label>
                  <label className="aum-field">
                    <span>Due date</span>
                    <input className="aum-input" type="datetime-local" value={reviewDueAt} onChange={(event) => setReviewDueAt(event.target.value)} />
                  </label>
                  <button type="button" className="aum-button aum-button--primary" onClick={() => reviewMutation.mutate()} disabled={!reviewTitle.trim()}>
                    Schedule review
                  </button>
                </div>
              </section>
            )}

            {activeTab === "activity" && (
              <section className="aum-panel">
                <div className="aum-panel-header"><div><h2>Activity log</h2><p>Recent recorded actions involving this user.</p></div></div>
                <div className="aum-table-wrap">
                  <table className="aum-table">
                    <thead><tr><th>When</th><th>Action</th><th>Entity type</th><th>Entity ID</th></tr></thead>
                    <tbody>
                      {workspace.activity_log.length === 0 ? (
                        <tr><td colSpan={4} className="aum-empty-row">No activity recorded.</td></tr>
                      ) : workspace.activity_log.map((entry) => (
                        <tr key={entry.id}>
                          <td>{formatDateTime(entry.occurred_at)}</td>
                          <td>{entry.action}</td>
                          <td>{entry.entity_type}</td>
                          <td>{entry.entity_id}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {activeTab === "login" && (
              <section className="aum-panel">
                <div className="aum-panel-header"><div><h2>Login record</h2><p>Current session state and account access history.</p></div></div>
                <div className="aum-definition-list two-col">
                  <div><span>Online status</span><strong>{currentStatus}</strong></div>
                  <div><span>Last seen</span><strong>{currentLastSeenPrimary}</strong></div>
                  <div><span>Last login</span><strong>{formatDateTime(workspace.login_record.last_login_at)}</strong></div>
                  <div><span>Last login IP</span><strong>{workspace.login_record.last_login_ip || "—"}</strong></div>
                  <div><span>Password change required</span><strong>{workspace.login_record.must_change_password ? "Yes" : "No"}</strong></div>
                  <div><span>Password changed at</span><strong>{formatDateTime(workspace.login_record.password_changed_at)}</strong></div>
                  <div><span>Token revoked at</span><strong>{formatDateTime(workspace.login_record.token_revoked_at)}</strong></div>
                  <div><span>User agent</span><strong>{workspace.login_record.last_login_user_agent || "—"}</strong></div>
                </div>
              </section>
            )}
          </>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default AdminUserDetailPage;
