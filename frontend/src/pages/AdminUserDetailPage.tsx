import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, EmptyState, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
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
import type { AdminUserRead, AdminUserWorkspaceRead } from "../services/adminUsers";

type ProfileTabKey = "details" | "tasks" | "permissions" | "activity" | "login" | "groups";

type UrlParams = { amoCode?: string; userId?: string };

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function roleLabel(value?: string | null): string {
  return (value || "—").replaceAll("_", " ");
}

function presenceTone(status?: string): string {
  if (status === "online") return "is-online";
  if (status === "away") return "is-away";
  return "is-offline";
}

const AdminUserDetailPage: React.FC = () => {
  const params = useParams<UrlParams>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const userId = params.userId ?? "";

  const [activeTab, setActiveTab] = useState<ProfileTabKey>("details");
  const [notifySubject, setNotifySubject] = useState("AMO Portal notification");
  const [notifyMessage, setNotifyMessage] = useState("");
  const [reviewTitle, setReviewTitle] = useState("User access review");
  const [reviewDueAt, setReviewDueAt] = useState("");
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    full_name: "",
    position_title: "",
    phone: "",
    secondary_phone: "",
    licence_number: "",
    licence_state_or_country: "",
    licence_expires_on: "",
  });

  const workspaceQuery = useQuery<AdminUserWorkspaceRead>({
    queryKey: ["admin-user-workspace", userId],
    queryFn: () => getAdminUserWorkspace(userId),
    enabled: !!userId,
    staleTime: 15_000,
  });

  const workspace = workspaceQuery.data ?? null;
  const user = workspace?.user ?? null;

  useEffect(() => {
    if (!user) return;
    setForm({
      first_name: user.first_name || "",
      last_name: user.last_name || "",
      full_name: user.full_name || "",
      position_title: user.position_title || "",
      phone: user.phone || "",
      secondary_phone: user.secondary_phone || "",
      licence_number: user.licence_number || "",
      licence_state_or_country: user.licence_state_or_country || "",
      licence_expires_on: user.licence_expires_on || "",
    });
  }, [user]);

  const invalidateWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-user-workspace", userId] }),
      queryClient.invalidateQueries({ queryKey: ["admin-users-summary"] }),
    ]);
  };

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<AdminUserRead>) => updateAdminUser(userId, payload),
    onSuccess: async () => {
      await invalidateWorkspace();
    },
  });

  const commandMutation = useMutation({
    mutationFn: async (command: "disable" | "enable" | "revoke" | "reset") => {
      if (command === "disable") return disableAdminUser(userId);
      if (command === "enable") return enableAdminUser(userId);
      if (command === "revoke") return revokeAdminUserAccess(userId);
      return forceAdminUserPasswordReset(userId);
    },
    onSuccess: async () => {
      await invalidateWorkspace();
    },
  });

  const notifyMutation = useMutation({
    mutationFn: () => notifyAdminUser(userId, { subject: notifySubject.trim(), message: notifyMessage.trim() }),
    onSuccess: async () => {
      setNotifyMessage("");
      await invalidateWorkspace();
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: () =>
      scheduleAdminUserReview(userId, {
        title: reviewTitle.trim(),
        due_at: reviewDueAt || undefined,
        priority: 2,
      }),
    onSuccess: async () => {
      await invalidateWorkspace();
    },
  });

  const profileFacts = useMemo(
    () => [
      { label: "Role", value: roleLabel(user?.role) },
      { label: "Status", value: user?.is_active ? "Active" : "Disabled" },
      { label: "Online", value: roleLabel(user?.online_status) },
      { label: "Last seen", value: formatDateTime(user?.last_seen_at) },
      { label: "Last login", value: formatDateTime(user?.last_login_at) },
      { label: "Last login IP", value: user?.last_login_ip || "—" },
      { label: "Created", value: formatDateTime(user?.created_at) },
      { label: "Updated", value: formatDateTime(user?.updated_at) },
    ],
    [user]
  );

  const metrics = workspace?.metrics;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin-users">
      <div className="admin-page admin-user-profile-page">
        <PageHeader
          title={user?.full_name || "User profile"}
          subtitle="Single-page profile with operational details, task ownership, permissions, audit trail, login history, and groups."
          actions={
            <div className="admin-user-profile-page__header-actions">
              <Button type="button" variant="secondary" onClick={() => navigate(`/maintenance/${amoCode}/admin/users`)}>
                Back to list
              </Button>
              <Button type="button" variant="secondary" onClick={() => workspaceQuery.refetch()}>
                Refresh
              </Button>
            </div>
          }
        />

        {workspaceQuery.isLoading ? <Panel title="Loading user workspace…"><p>Fetching the latest profile, task, and audit data.</p></Panel> : null}

        {workspaceQuery.isError ? (
          <InlineAlert tone="danger" title="Failed to load user profile">
            <span>The user workspace could not be loaded.</span>
          </InlineAlert>
        ) : null}

        {user ? (
          <>
            <div className="admin-user-profile-page__hero">
              <div className="admin-user-profile-page__identity">
                <div className="admin-user-profile-page__avatar">{user.full_name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "U"}</div>
                <div>
                  <h2>{user.full_name}</h2>
                  <p>{user.email}</p>
                  <div className="admin-user-profile-page__chips">
                    <span className="admin-user-profile-page__chip">{roleLabel(user.role)}</span>
                    <span className={`admin-user-profile-page__chip admin-user-profile-page__chip--presence ${presenceTone(user.online_status)}`}>{user.online_status}</span>
                    <span className="admin-user-profile-page__chip">Last seen {formatDateTime(user.last_seen_at)}</span>
                  </div>
                </div>
              </div>
              <div className="admin-user-profile-page__command-bar">
                <Button type="button" variant="secondary" onClick={() => window.open(`mailto:${user.email}`, "_self")}>Email</Button>
                <Button type="button" variant="secondary" onClick={() => commandMutation.mutate(user.is_active ? "disable" : "enable")}>{user.is_active ? "Disable" : "Enable"}</Button>
                <Button type="button" variant="secondary" onClick={() => commandMutation.mutate("revoke")}>Revoke sessions</Button>
                <Button type="button" variant="danger" onClick={() => commandMutation.mutate("reset")}>Force password reset</Button>
              </div>
            </div>

            <div className="admin-user-profile-page__metrics">
              <div className="admin-user-profile-page__metric"><span>Open tasks</span><strong>{metrics?.open_tasks ?? 0}</strong></div>
              <div className="admin-user-profile-page__metric"><span>Overdue tasks</span><strong>{metrics?.overdue_tasks ?? 0}</strong></div>
              <div className="admin-user-profile-page__metric"><span>Completed 30d</span><strong>{metrics?.completed_tasks_30d ?? 0}</strong></div>
              <div className="admin-user-profile-page__metric"><span>Authorisations</span><strong>{metrics?.active_authorisations ?? 0}</strong></div>
              <div className="admin-user-profile-page__metric"><span>Activity 30d</span><strong>{metrics?.activity_events_30d ?? 0}</strong></div>
              <div className="admin-user-profile-page__metric"><span>Login failures 30d</span><strong>{metrics?.login_failures_30d ?? 0}</strong></div>
            </div>

            <div className="admin-user-profile-page__tabs" role="tablist" aria-label="User profile sections">
              {[
                { id: "details", label: "Profile details" },
                { id: "tasks", label: "Tasks assigned" },
                { id: "permissions", label: "Project permissions" },
                { id: "activity", label: "Activity log" },
                { id: "login", label: "Login record" },
                { id: "groups", label: "Groups" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  className={`admin-user-profile-page__tab ${activeTab === tab.id ? "is-active" : ""}`}
                  onClick={() => setActiveTab(tab.id as ProfileTabKey)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {activeTab === "details" ? (
              <div className="admin-user-profile-page__grid">
                <Panel title="Profile details" subtitle="Editable identity, contacts, and credential metadata.">
                  <div className="admin-user-profile-page__form-grid">
                    <label><span>First name</span><input className="input" value={form.first_name} onChange={(event) => setForm((prev) => ({ ...prev, first_name: event.target.value }))} /></label>
                    <label><span>Last name</span><input className="input" value={form.last_name} onChange={(event) => setForm((prev) => ({ ...prev, last_name: event.target.value }))} /></label>
                    <label><span>Full name</span><input className="input" value={form.full_name} onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))} /></label>
                    <label><span>Position title</span><input className="input" value={form.position_title} onChange={(event) => setForm((prev) => ({ ...prev, position_title: event.target.value }))} /></label>
                    <label><span>Primary phone</span><input className="input" value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} /></label>
                    <label><span>Secondary phone</span><input className="input" value={form.secondary_phone} onChange={(event) => setForm((prev) => ({ ...prev, secondary_phone: event.target.value }))} /></label>
                    <label><span>Licence number</span><input className="input" value={form.licence_number} onChange={(event) => setForm((prev) => ({ ...prev, licence_number: event.target.value }))} /></label>
                    <label><span>Licence state/country</span><input className="input" value={form.licence_state_or_country} onChange={(event) => setForm((prev) => ({ ...prev, licence_state_or_country: event.target.value }))} /></label>
                    <label><span>Licence expiry</span><input className="input" type="date" value={form.licence_expires_on} onChange={(event) => setForm((prev) => ({ ...prev, licence_expires_on: event.target.value }))} /></label>
                  </div>
                  <div className="admin-user-profile-page__form-actions">
                    <Button type="button" onClick={() => updateMutation.mutate(form)}>Save profile</Button>
                  </div>
                </Panel>

                <Panel title="Operational status" subtitle="Presence, sign-in, and audit-friendly account facts.">
                  <div className="admin-user-profile-page__facts-grid">
                    {profileFacts.map((item) => (
                      <div key={item.label} className="admin-user-profile-page__fact-card">
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </div>
                    ))}
                  </div>
                </Panel>

                <Panel title="Supervisor actions" subtitle="Fast communication and review actions for managers and HR.">
                  <div className="admin-user-profile-page__stack">
                    <input className="input" value={notifySubject} onChange={(event) => setNotifySubject(event.target.value)} placeholder="Notification subject" />
                    <textarea className="input" rows={4} value={notifyMessage} onChange={(event) => setNotifyMessage(event.target.value)} placeholder="Notification message" />
                    <Button type="button" onClick={() => notifyMutation.mutate()} disabled={!notifySubject.trim() || !notifyMessage.trim()}>
                      Send notification
                    </Button>
                    <hr />
                    <input className="input" value={reviewTitle} onChange={(event) => setReviewTitle(event.target.value)} placeholder="Review title" />
                    <input className="input" type="datetime-local" value={reviewDueAt} onChange={(event) => setReviewDueAt(event.target.value)} />
                    <Button type="button" variant="secondary" onClick={() => scheduleMutation.mutate()} disabled={!reviewTitle.trim()}>
                      Schedule review task
                    </Button>
                  </div>
                </Panel>
              </div>
            ) : null}

            {activeTab === "tasks" ? (
              <Panel title="Tasks assigned" subtitle="Every task currently or recently assigned to this user.">
                <Table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Status</th>
                      <th>Priority</th>
                      <th>Due</th>
                      <th>Entity</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspace?.tasks.length ? workspace.tasks.map((task) => (
                      <tr key={task.id}>
                        <td>{task.title}</td>
                        <td>{roleLabel(task.status)}</td>
                        <td>{task.priority}</td>
                        <td>{formatDateTime(task.due_at)}</td>
                        <td>{task.entity_type || "—"}</td>
                        <td>{formatDateTime(task.updated_at)}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={6}><EmptyState title="No tasks are assigned to this user." /></td></tr>
                    )}
                  </tbody>
                </Table>
              </Panel>
            ) : null}

            {activeTab === "permissions" ? (
              <Panel title="Project permissions" subtitle="Role, authorisation, and access scope currently recorded for this user.">
                <Table>
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th>Subject</th>
                      <th>Permission</th>
                      <th>Status</th>
                      <th>Valid from</th>
                      <th>Valid to</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspace?.permissions.length ? workspace.permissions.map((item, index) => (
                      <tr key={`${item.category}-${item.subject}-${index}`}>
                        <td>{item.category}</td>
                        <td>{item.subject}</td>
                        <td>{item.permission_level}</td>
                        <td>{item.status}</td>
                        <td>{item.effective_from || "—"}</td>
                        <td>{item.expires_at || "—"}</td>
                        <td>{item.notes || "—"}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={7}><EmptyState title="No permissions or authorisations found." /></td></tr>
                    )}
                  </tbody>
                </Table>
              </Panel>
            ) : null}

            {activeTab === "activity" ? (
              <Panel title="Activity log" subtitle="Append-only actions associated with this user across the portal.">
                <Table>
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Action</th>
                      <th>Entity type</th>
                      <th>Entity id</th>
                      <th>Module</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspace?.activity.length ? workspace.activity.map((item) => (
                      <tr key={item.id}>
                        <td>{formatDateTime(item.happened_at)}</td>
                        <td>{item.action}</td>
                        <td>{item.entity_type}</td>
                        <td>{item.entity_id}</td>
                        <td>{item.note || "—"}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={5}><EmptyState title="No activity recorded for this user yet." /></td></tr>
                    )}
                  </tbody>
                </Table>
              </Panel>
            ) : null}

            {activeTab === "login" ? (
              <Panel title="Login record" subtitle="Authentication success, failures, and credential support history.">
                <Table>
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Event</th>
                      <th>IP address</th>
                      <th>User agent</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspace?.login_records.length ? workspace.login_records.map((row) => (
                      <tr key={row.id}>
                        <td>{formatDateTime(row.created_at)}</td>
                        <td>{row.event_type}</td>
                        <td>{row.ip_address || "—"}</td>
                        <td>{row.user_agent || "—"}</td>
                        <td>{row.description || "—"}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={5}><EmptyState title="No login history is available for this user." /></td></tr>
                    )}
                  </tbody>
                </Table>
              </Panel>
            ) : null}

            {activeTab === "groups" ? (
              <Panel title="Group memberships" subtitle="Shows every group this user belongs to, including member count and visibility.">
                <Table>
                  <thead>
                    <tr>
                      <th>Group</th>
                      <th>Type</th>
                      <th>Visibility</th>
                      <th>Members</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspace?.groups.length ? workspace.groups.map((group) => (
                      <tr key={group.id}>
                        <td>
                          <strong>{group.name}</strong>
                          <div className="admin-user-profile-page__subcell">{group.description || group.code}</div>
                        </td>
                        <td>{roleLabel(group.group_type)}</td>
                        <td>{roleLabel(group.visibility)}</td>
                        <td>{group.member_count}</td>
                        <td>{group.is_active ? "Active" : "Inactive"}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={5}><EmptyState title="This user is not in any groups yet." /></td></tr>
                    )}
                  </tbody>
                </Table>
              </Panel>
            ) : null}
          </>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default AdminUserDetailPage;
