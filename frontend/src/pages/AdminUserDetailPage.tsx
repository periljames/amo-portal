import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getContext } from "../services/auth";
import {
  applyAdminUserEmploymentAction,
  bulkAdminUserAction,
  deleteAdminUserAuthorisation,
  downloadAdminUserExport,
  enableAdminUser,
  disableAdminUser,
  forceAdminUserPasswordReset,
  getAdminUserWorkspace,
  grantAdminUserAuthorisation,
  listAdminAuthorisationTypes,
  listAdminDepartments,
  listAdminGroups,
  notifyAdminUser,
  permanentDeleteAdminUser,
  revokeAdminUserAccess,
  scheduleAdminUserReview,
  updateAdminUser,
} from "../services/adminUsers";
import type {
  AccountRole,
  AdminDepartmentRead,
  AdminUserGroupRead,
  AdminUserUpdatePayload,
  AdminUserWorkspace,
  UserEmploymentActionPayload,
} from "../services/adminUsers";
import "../styles/admin-user-management.css";

type ProfileTab = "profile" | "permissions" | "groups" | "tasks" | "lifecycle" | "activity" | "login";

const ROLE_OPTIONS: AccountRole[] = [
  "SUPERUSER",
  "AMO_ADMIN",
  "QUALITY_MANAGER",
  "AUDITOR",
  "SAFETY_MANAGER",
  "PLANNING_ENGINEER",
  "PRODUCTION_ENGINEER",
  "CERTIFYING_ENGINEER",
  "CERTIFYING_TECHNICIAN",
  "TECHNICIAN",
  "STORES",
  "VIEW_ONLY",
  "FINANCE_MANAGER",
  "ACCOUNTS_OFFICER",
  "STORES_MANAGER",
  "STOREKEEPER",
  "PROCUREMENT_OFFICER",
  "QUALITY_INSPECTOR",
];

const formatRole = (value: string) => value.replaceAll("_", " ");

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

const relativeLabel = (value?: string | null) => {
  if (!value) return "Never seen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Never seen";
  const delta = Date.now() - date.getTime();
  if (delta < 60_000) return "Just now";
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

const downloadBlob = ({ blob, filename }: { blob: Blob; filename: string }) => {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

const workspaceStatus = (workspace?: AdminUserWorkspace) => {
  if (!workspace) return "Offline";
  if (!workspace.user.is_active) return "Inactive";
  if (workspace.presence_display.status_label === "On leave") return "On leave";
  if (workspace.presence.is_online && workspace.presence.state === "away") return "Away";
  if (workspace.presence.is_online) return "Online";
  return "Offline";
};

const statusTone = (workspace?: AdminUserWorkspace) => {
  const status = workspaceStatus(workspace);
  if (status === "Online") return "is-online";
  if (status === "Away") return "is-away";
  if (status === "On leave") return "is-leave";
  if (status === "Inactive") return "is-inactive";
  return "is-offline";
};

const AdminUserDetailPage: React.FC = () => {
  const { amoCode, userId } = useParams<{ amoCode?: string; userId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ctx = getContext();
  const resolvedAmoCode = amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const resolvedUserId = userId ?? "";

  const [activeTab, setActiveTab] = useState<ProfileTab>("profile");
  const [profileRole, setProfileRole] = useState<AccountRole | "">("");
  const [profileDepartmentId, setProfileDepartmentId] = useState("");
  const [profileTitle, setProfileTitle] = useState("");
  const [profilePhone, setProfilePhone] = useState("");
  const [profileSecondaryPhone, setProfileSecondaryPhone] = useState("");
  const [notifySubject, setNotifySubject] = useState("QMS user notification");
  const [notifyMessage, setNotifyMessage] = useState("");
  const [reviewTitle, setReviewTitle] = useState("Authorization review");
  const [reviewDueAt, setReviewDueAt] = useState("");
  const [permissionTypeId, setPermissionTypeId] = useState("");
  const [permissionScopeText, setPermissionScopeText] = useState("");
  const [permissionEffectiveFrom, setPermissionEffectiveFrom] = useState("");
  const [permissionExpiresAt, setPermissionExpiresAt] = useState("");
  const [groupToAddId, setGroupToAddId] = useState("");
  const [lifecycleAction, setLifecycleAction] = useState<UserEmploymentActionPayload["action"]>("transfer");
  const [lifecycleRole, setLifecycleRole] = useState<AccountRole | "">("");
  const [lifecycleDepartmentId, setLifecycleDepartmentId] = useState("");
  const [lifecycleTitle, setLifecycleTitle] = useState("");
  const [lifecycleStatus, setLifecycleStatus] = useState("");
  const [lifecycleNote, setLifecycleNote] = useState("");
  const [lifecycleEffectiveFrom, setLifecycleEffectiveFrom] = useState("");
  const [lifecycleEffectiveTo, setLifecycleEffectiveTo] = useState("");
  const [feedback, setFeedback] = useState("");

  const workspaceQuery = useQuery({
    queryKey: ["admin-user-workspace", resolvedUserId],
    queryFn: () => getAdminUserWorkspace(resolvedUserId),
    enabled: !!resolvedUserId,
    staleTime: 30_000,
  });

  const departmentsQuery = useQuery({
    queryKey: ["admin-user-departments", resolvedAmoCode],
    queryFn: () => listAdminDepartments(),
    enabled: !!resolvedUserId,
  });

  const groupsQuery = useQuery({
    queryKey: ["admin-user-groups", resolvedAmoCode],
    queryFn: () => listAdminGroups(),
    enabled: !!resolvedUserId,
  });

  const permissionTypesQuery = useQuery({
    queryKey: ["admin-user-authorisation-types", resolvedAmoCode],
    queryFn: () => listAdminAuthorisationTypes(),
    enabled: !!resolvedUserId,
  });

  const workspace = workspaceQuery.data;
  const user = workspace?.user;
  const departments = departmentsQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const permissionTypes = permissionTypesQuery.data ?? [];

  const refreshWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-user-workspace", resolvedUserId] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-groups"] }),
    ]);
  };

  React.useEffect(() => {
    if (!user) return;
    setProfileRole(user.role);
    setProfileDepartmentId(user.department_id || "");
    setProfileTitle(user.position_title || "");
    setProfilePhone(user.phone || "");
    setProfileSecondaryPhone(user.secondary_phone || "");
    setLifecycleRole(user.role);
    setLifecycleDepartmentId(user.department_id || "");
    setLifecycleTitle(user.position_title || "");
    setPermissionEffectiveFrom(new Date().toISOString().slice(0, 10));
  }, [user?.id]);

  const updateUserMutation = useMutation({
    mutationFn: (payload: AdminUserUpdatePayload) => updateAdminUser(resolvedUserId, payload),
    onSuccess: async () => {
      setFeedback("Profile updated.");
      await refreshWorkspace();
    },
  });

  const commandMutation = useMutation({
    mutationFn: async (command: "disable" | "enable" | "revoke" | "reset") => {
      if (command === "disable") return disableAdminUser(resolvedUserId);
      if (command === "enable") return enableAdminUser(resolvedUserId);
      if (command === "revoke") return revokeAdminUserAccess(resolvedUserId);
      return forceAdminUserPasswordReset(resolvedUserId);
    },
    onSuccess: async (_, command) => {
      setFeedback(`Command completed: ${command}.`);
      await refreshWorkspace();
    },
  });

  const notifyMutation = useMutation({
    mutationFn: () => notifyAdminUser(resolvedUserId, { subject: notifySubject.trim(), message: notifyMessage.trim() }),
    onSuccess: async () => {
      setNotifyMessage("");
      setFeedback("Notification sent.");
      await refreshWorkspace();
    },
  });

  const reviewMutation = useMutation({
    mutationFn: () => scheduleAdminUserReview(resolvedUserId, { title: reviewTitle.trim(), due_at: reviewDueAt || undefined, priority: 2 }),
    onSuccess: async () => {
      setFeedback("Review task scheduled.");
      await refreshWorkspace();
    },
  });

  const permissionGrantMutation = useMutation({
    mutationFn: () =>
      grantAdminUserAuthorisation({
        user_id: resolvedUserId,
        authorisation_type_id: permissionTypeId,
        scope_text: permissionScopeText || undefined,
        effective_from: permissionEffectiveFrom,
        expires_at: permissionExpiresAt || undefined,
      }),
    onSuccess: async () => {
      setFeedback("Permission granted.");
      setPermissionTypeId("");
      setPermissionScopeText("");
      setPermissionExpiresAt("");
      await refreshWorkspace();
    },
  });

  const deletePermissionMutation = useMutation({
    mutationFn: (permissionId: string) => deleteAdminUserAuthorisation(permissionId),
    onSuccess: async () => {
      setFeedback("Permission removed.");
      await refreshWorkspace();
    },
  });

  const groupMembershipMutation = useMutation({
    mutationFn: ({ action, groupId }: { action: "add_group" | "remove_group"; groupId: string }) =>
      bulkAdminUserAction({ user_ids: [resolvedUserId], action, group_id: groupId }),
    onSuccess: async (_, variables) => {
      setFeedback(variables.action === "add_group" ? "User added to group." : "User removed from group.");
      await refreshWorkspace();
    },
  });

  const lifecycleMutation = useMutation({
    mutationFn: (payload: UserEmploymentActionPayload) => applyAdminUserEmploymentAction(resolvedUserId, payload),
    onSuccess: async (result) => {
      setFeedback(`Lifecycle action ${result.action} applied.`);
      await refreshWorkspace();
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => downloadAdminUserExport(resolvedUserId),
    onSuccess: (result) => {
      downloadBlob(result);
      setFeedback(`Export ready: ${result.filename}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => permanentDeleteAdminUser(resolvedUserId),
    onSuccess: async () => {
      setFeedback("User permanently deleted.");
      await queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
      navigate(`/maintenance/${resolvedAmoCode}/admin/users`);
    },
  });

  const displayTitle = useMemo(() => {
    if (!workspace) return "Portal User";
    return workspace.display_title || workspace.user.position_title || formatRole(String(workspace.user.role || "Portal User"));
  }, [workspace]);

  const currentStatus = workspaceStatus(workspace);
  const primaryLastSeen = workspace?.presence.is_online ? "Active now" : relativeLabel(workspace?.presence.last_seen_at || workspace?.user.last_login_at);

  if (workspaceQuery.isPending) {
    return (
      <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment="admin-users">
        <div className="admin-user-profile"><div className="aum-panel"><div className="aum-empty">Loading user workspace…</div></div></div>
      </DepartmentLayout>
    );
  }

  if (workspaceQuery.isError || !workspace || !user) {
    return (
      <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment="admin-users">
        <div className="admin-user-profile"><div className="aum-panel"><div className="aum-empty">{workspaceQuery.isError ? (workspaceQuery.error as Error).message : "User workspace is unavailable."}</div></div></div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment="admin-users">
      <div className="admin-user-profile">
        <header className="aum-header aum-brand-hero">
          <div>
            <p className="aum-eyebrow">User Profile</p>
            <h1>{user.full_name}</h1>
            <p className="aum-subtitle">Full user admin workspace for profile control, permissions, group assignment, leave handling, and audit evidence export.</p>
          </div>
          <div className="aum-header-actions">
            <button type="button" className="aum-button aum-button--secondary" onClick={() => navigate(`/maintenance/${resolvedAmoCode}/admin/users`)}>
              Back to users
            </button>
            <button type="button" className="aum-button aum-button--primary" onClick={() => refreshWorkspace()}>
              Refresh
            </button>
          </div>
        </header>

        {feedback ? <section className="aum-inline-banner">{feedback}</section> : null}

        <section className="aum-profile-hero aum-panel">
          <div>
            <h2>{user.full_name}</h2>
            <p>{user.email}</p>
            <div className="aum-chip-row">
              <span className={`aum-status ${statusTone(workspace)}`}>{currentStatus}</span>
              <span className="aum-chip">Title: {displayTitle}</span>
              <span className="aum-chip">Department: {workspace.department_name || "—"}</span>
              <span className="aum-chip">Last seen: {primaryLastSeen}</span>
            </div>
            <p className="aum-muted top-gap">{formatDateTime(workspace.presence.last_seen_at || workspace.user.last_login_at)}</p>
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
            ["profile", "Profile"],
            ["permissions", "Permissions"],
            ["groups", "Groups"],
            ["tasks", "Tasks"],
            ["lifecycle", "Lifecycle"],
            ["activity", "Activity"],
            ["login", "Login"],
          ] as const).map(([key, label]) => (
            <button key={key} type="button" className={`aum-tab ${activeTab === key ? "is-active" : ""}`} onClick={() => setActiveTab(key)}>
              {label}
            </button>
          ))}
        </div>

        {activeTab === "profile" ? (
          <section className="aum-three-col">
            <article className="aum-panel">
              <h2>Profile details</h2>
              <div className="aum-definition-list">
                <div><span>Staff code</span><strong>{user.staff_code}</strong></div>
                <div><span>Role</span><strong>{formatRole(user.role)}</strong></div>
                <div><span>Phone</span><strong>{user.phone || "—"}</strong></div>
                <div><span>Secondary phone</span><strong>{user.secondary_phone || "—"}</strong></div>
                <div><span>Department</span><strong>{workspace.department_name || "—"}</strong></div>
                <div><span>Hire date</span><strong>{workspace.profile?.hire_date || "—"}</strong></div>
                <div><span>Employment status</span><strong>{workspace.profile?.employment_status || "—"}</strong></div>
                <div><span>Personnel status</span><strong>{workspace.profile?.status || "—"}</strong></div>
              </div>
            </article>
            <article className="aum-panel">
              <h2>Edit account</h2>
              <div className="aum-stack">
                <label className="aum-field"><span>Role</span><select className="aum-select" value={profileRole} onChange={(event) => setProfileRole(event.target.value as AccountRole)}>{ROLE_OPTIONS.map((role) => <option key={role} value={role}>{formatRole(role)}</option>)}</select></label>
                <label className="aum-field"><span>Department</span><select className="aum-select" value={profileDepartmentId} onChange={(event) => setProfileDepartmentId(event.target.value)}><option value="">Unassigned</option>{departments.map((department: AdminDepartmentRead) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
                <label className="aum-field"><span>Position title</span><input className="aum-input" value={profileTitle} onChange={(event) => setProfileTitle(event.target.value)} /></label>
                <label className="aum-field"><span>Primary phone</span><input className="aum-input" value={profilePhone} onChange={(event) => setProfilePhone(event.target.value)} /></label>
                <label className="aum-field"><span>Secondary phone</span><input className="aum-input" value={profileSecondaryPhone} onChange={(event) => setProfileSecondaryPhone(event.target.value)} /></label>
                <button type="button" className="aum-button aum-button--primary" onClick={() => updateUserMutation.mutate({ role: (profileRole || user.role) as AccountRole, department_id: profileDepartmentId || null, position_title: profileTitle || null, phone: profilePhone || null, secondary_phone: profileSecondaryPhone || null })}>
                  Save profile changes
                </button>
              </div>
            </article>
            <article className="aum-panel">
              <h2>Access commands</h2>
              <div className="aum-stack">
                <div className="aum-row-actions wrap">
                  <button type="button" className="aum-button aum-button--ghost" onClick={() => commandMutation.mutate(user.is_active ? "disable" : "enable")}>{user.is_active ? "Disable" : "Enable"}</button>
                  <button type="button" className="aum-button aum-button--ghost" onClick={() => commandMutation.mutate("revoke")}>Revoke access</button>
                  <button type="button" className="aum-button aum-button--ghost" onClick={() => commandMutation.mutate("reset")}>Force password reset</button>
                </div>
                <label className="aum-field"><span>Notification subject</span><input className="aum-input" value={notifySubject} onChange={(event) => setNotifySubject(event.target.value)} /></label>
                <label className="aum-field"><span>Notification message</span><textarea className="aum-textarea" rows={4} value={notifyMessage} onChange={(event) => setNotifyMessage(event.target.value)} /></label>
                <button type="button" className="aum-button aum-button--primary" disabled={!notifySubject.trim() || !notifyMessage.trim()} onClick={() => notifyMutation.mutate()}>Send notification</button>
                <div className="aum-row-actions wrap top-gap">
                  <button type="button" className="aum-button aum-button--ghost" onClick={() => exportMutation.mutate()}>Export full record</button>
                  <button
                    type="button"
                    className="aum-button aum-button--danger"
                    onClick={() => {
                      if (window.confirm(`Permanently delete ${user.full_name}? This cannot be undone.`)) {
                        deleteMutation.mutate();
                      }
                    }}
                  >
                    Hard delete
                  </button>
                </div>
              </div>
            </article>
          </section>
        ) : null}

        {activeTab === "permissions" ? (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header"><div><h2>Grant permission</h2><p>Grant a permission type to this user with scope and validity dates.</p></div></div>
              <div className="aum-stack">
                <label className="aum-field"><span>Permission type</span><select className="aum-select" value={permissionTypeId} onChange={(event) => setPermissionTypeId(event.target.value)}><option value="">Select permission type</option>{permissionTypes.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
                <label className="aum-field"><span>Scope text</span><input className="aum-input" value={permissionScopeText} onChange={(event) => setPermissionScopeText(event.target.value)} placeholder="Fleet / shop / work scope" /></label>
                <label className="aum-field"><span>Effective from</span><input className="aum-input" type="date" value={permissionEffectiveFrom} onChange={(event) => setPermissionEffectiveFrom(event.target.value)} /></label>
                <label className="aum-field"><span>Expires at</span><input className="aum-input" type="date" value={permissionExpiresAt} onChange={(event) => setPermissionExpiresAt(event.target.value)} /></label>
                <button type="button" className="aum-button aum-button--primary" disabled={!permissionTypeId || !permissionEffectiveFrom} onClick={() => permissionGrantMutation.mutate()}>
                  Grant permission
                </button>
              </div>
              <div className="aum-stack top-gap">
                <label className="aum-field"><span>Review title</span><input className="aum-input" value={reviewTitle} onChange={(event) => setReviewTitle(event.target.value)} /></label>
                <label className="aum-field"><span>Review due date</span><input className="aum-input" type="datetime-local" value={reviewDueAt} onChange={(event) => setReviewDueAt(event.target.value)} /></label>
                <button type="button" className="aum-button aum-button--ghost" disabled={!reviewTitle.trim()} onClick={() => reviewMutation.mutate()}>Schedule permission review</button>
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header"><div><h2>Current permissions</h2><p>Delete any permission that should no longer remain in force.</p></div></div>
              <div className="aum-table-wrap">
                <table className="aum-table">
                  <thead><tr><th>Code</th><th>Permission</th><th>Scope</th><th>Effective</th><th>Expires</th><th>Status</th><th>Actions</th></tr></thead>
                  <tbody>
                    {workspace.permissions.length === 0 ? (
                      <tr><td colSpan={7} className="aum-empty-row">No permissions recorded.</td></tr>
                    ) : workspace.permissions.map((permission) => (
                      <tr key={permission.id}>
                        <td>{permission.code}</td>
                        <td>{permission.label}</td>
                        <td>{permission.scope_text || permission.maintenance_scope || "—"}</td>
                        <td>{permission.effective_from}</td>
                        <td>{permission.expires_at || "—"}</td>
                        <td>{permission.is_currently_valid ? "Current" : "Expired / Revoked"}</td>
                        <td><button type="button" className="aum-button aum-button--danger" onClick={() => deletePermissionMutation.mutate(permission.id)}>Delete</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        ) : null}

        {activeTab === "groups" ? (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header"><div><h2>Current group memberships</h2><p>Use this to manage custom groups, departmental cohorts, and policy bundles.</p></div></div>
              <div className="aum-list-grid">
                {workspace.group_memberships.length === 0 ? (
                  <div className="aum-empty">This user is not currently in any custom group.</div>
                ) : workspace.group_memberships.map((group) => (
                  <div key={group.id} className="aum-list-card">
                    <strong>{group.name}</strong>
                    <span>{group.member_count} members</span>
                    <div className="aum-muted">{group.code} · {group.group_type}</div>
                    <div className="aum-row-actions wrap top-gap">
                      <button type="button" className="aum-button aum-button--danger" onClick={() => groupMembershipMutation.mutate({ action: "remove_group", groupId: group.id })}>Remove</button>
                    </div>
                  </div>
                ))}
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header"><div><h2>Add to group</h2><p>Assign the user to any active group defined in the tenant.</p></div></div>
              <div className="aum-stack">
                <label className="aum-field"><span>Group</span><select className="aum-select" value={groupToAddId} onChange={(event) => setGroupToAddId(event.target.value)}><option value="">Select group</option>{groups.map((group: AdminUserGroupRead) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
                <button type="button" className="aum-button aum-button--primary" disabled={!groupToAddId} onClick={() => groupMembershipMutation.mutate({ action: "add_group", groupId: groupToAddId })}>Add to group</button>
              </div>
              <div className="aum-chip-row top-gap">
                {workspace.groups.map((group) => <span key={`${group.kind}-${group.label}-${group.value || ""}`} className="aum-chip">{group.label}: {group.value || "—"}</span>)}
              </div>
            </article>
          </section>
        ) : null}

        {activeTab === "tasks" ? (
          <section className="aum-panel">
            <div className="aum-panel-header"><div><h2>Tasks assigned</h2><p>Operational tasks currently owned by this user.</p></div></div>
            <div className="aum-table-wrap">
              <table className="aum-table">
                <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Due</th><th>Updated</th></tr></thead>
                <tbody>
                  {workspace.tasks.length === 0 ? (
                    <tr><td colSpan={5} className="aum-empty-row">No tasks assigned.</td></tr>
                  ) : workspace.tasks.map((task) => (
                    <tr key={task.id}><td>{task.title}</td><td>{task.status}</td><td>{task.priority}</td><td>{formatDateTime(task.due_at)}</td><td>{formatDateTime(task.updated_at)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {activeTab === "lifecycle" ? (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header"><div><h2>Employment lifecycle</h2><p>Promote, demote, transfer, schedule leave, reinstate, or resign the employee from this workspace.</p></div></div>
              <div className="aum-stack">
                <label className="aum-field"><span>Action</span><select className="aum-select" value={lifecycleAction} onChange={(event) => setLifecycleAction(event.target.value as UserEmploymentActionPayload["action"])}><option value="new_hire">New hire</option><option value="promote">Promote</option><option value="demote">Demote</option><option value="transfer">Transfer</option><option value="resign">Resign</option><option value="reinstate">Reinstate</option><option value="schedule_leave">Schedule leave</option><option value="return_from_leave">Return from leave</option></select></label>
                <label className="aum-field"><span>Role</span><select className="aum-select" value={lifecycleRole} onChange={(event) => setLifecycleRole(event.target.value as AccountRole)}>{ROLE_OPTIONS.map((role) => <option key={role} value={role}>{formatRole(role)}</option>)}</select></label>
                <label className="aum-field"><span>Department</span><select className="aum-select" value={lifecycleDepartmentId} onChange={(event) => setLifecycleDepartmentId(event.target.value)}><option value="">Unassigned</option>{departments.map((department: AdminDepartmentRead) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
                <label className="aum-field"><span>Position title</span><input className="aum-input" value={lifecycleTitle} onChange={(event) => setLifecycleTitle(event.target.value)} /></label>
                <label className="aum-field"><span>Employment status text</span><input className="aum-input" value={lifecycleStatus} onChange={(event) => setLifecycleStatus(event.target.value)} /></label>
                <label className="aum-field"><span>Note</span><textarea className="aum-textarea" rows={3} value={lifecycleNote} onChange={(event) => setLifecycleNote(event.target.value)} /></label>
                <label className="aum-field"><span>Effective from</span><input className="aum-input" type="datetime-local" value={lifecycleEffectiveFrom} onChange={(event) => setLifecycleEffectiveFrom(event.target.value)} /></label>
                <label className="aum-field"><span>Effective to</span><input className="aum-input" type="datetime-local" value={lifecycleEffectiveTo} onChange={(event) => setLifecycleEffectiveTo(event.target.value)} /></label>
                <button type="button" className="aum-button aum-button--primary" onClick={() => lifecycleMutation.mutate({ action: lifecycleAction, role: lifecycleRole || undefined, department_id: lifecycleDepartmentId || undefined, position_title: lifecycleTitle || undefined, employment_status: lifecycleStatus || undefined, note: lifecycleNote || undefined, effective_from: lifecycleEffectiveFrom || undefined, effective_to: lifecycleEffectiveTo || undefined })}>Apply lifecycle action</button>
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header"><div><h2>Availability history</h2><p>Leave and return-to-duty events that affect planning and manpower availability.</p></div></div>
              <div className="aum-table-wrap">
                <table className="aum-table">
                  <thead><tr><th>Status</th><th>Effective from</th><th>Effective to</th><th>Note</th><th>Updated</th></tr></thead>
                  <tbody>
                    {workspace.availability.length === 0 ? (
                      <tr><td colSpan={5} className="aum-empty-row">No availability history recorded.</td></tr>
                    ) : workspace.availability.map((entry) => (
                      <tr key={entry.id}><td>{entry.status}</td><td>{formatDateTime(entry.effective_from)}</td><td>{formatDateTime(entry.effective_to)}</td><td>{entry.note || "—"}</td><td>{formatDateTime(entry.updated_at)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        ) : null}

        {activeTab === "activity" ? (
          <section className="aum-panel">
            <div className="aum-panel-header"><div><h2>Activity log</h2><p>Recent recorded actions involving this user.</p></div></div>
            <div className="aum-table-wrap">
              <table className="aum-table">
                <thead><tr><th>When</th><th>Action</th><th>Entity type</th><th>Entity ID</th></tr></thead>
                <tbody>
                  {workspace.activity_log.length === 0 ? (
                    <tr><td colSpan={4} className="aum-empty-row">No activity recorded.</td></tr>
                  ) : workspace.activity_log.map((entry) => (
                    <tr key={entry.id}><td>{formatDateTime(entry.occurred_at)}</td><td>{entry.action}</td><td>{entry.entity_type}</td><td>{entry.entity_id}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {activeTab === "login" ? (
          <section className="aum-panel">
            <div className="aum-panel-header"><div><h2>Login record</h2><p>Account access state and authentication history.</p></div></div>
            <div className="aum-definition-list two-col">
              <div><span>Online status</span><strong>{currentStatus}</strong></div>
              <div><span>Last seen</span><strong>{primaryLastSeen}</strong></div>
              <div><span>Last login</span><strong>{formatDateTime(workspace.login_record.last_login_at)}</strong></div>
              <div><span>Last login IP</span><strong>{workspace.login_record.last_login_ip || "—"}</strong></div>
              <div><span>Password change required</span><strong>{workspace.login_record.must_change_password ? "Yes" : "No"}</strong></div>
              <div><span>Password changed at</span><strong>{formatDateTime(workspace.login_record.password_changed_at)}</strong></div>
              <div><span>Token revoked at</span><strong>{formatDateTime(workspace.login_record.token_revoked_at)}</strong></div>
              <div><span>User agent</span><strong>{workspace.login_record.last_login_user_agent || "—"}</strong></div>
            </div>
          </section>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default AdminUserDetailPage;
