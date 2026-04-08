import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { RealtimeContext } from "../components/realtime/realtimeContext";
import { getCachedUser, getContext } from "../services/auth";
import {
  disableAdminUser,
  enableAdminUser,
  getAdminUserDirectory,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";
import type { AdminUserDirectoryItem } from "../services/adminUsers";
import "../styles/admin-user-management.css";

type UrlParams = { amoCode?: string };
type UserTab = "users" | "groups" | "hr";
type PresenceFilter = "all" | "online" | "away" | "offline" | "inactive";
const ZERO_METRICS = {
  total_users: 0,
  active_users: 0,
  inactive_users: 0,
  online_users: 0,
  away_users: 0,
  recently_active_users: 0,
  departmentless_users: 0,
  managers: 0,
} as const;

class AdminUsersErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; message: string }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error?.message || "Unexpected rendering failure" };
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="aum-panel">
          <div className="aum-empty">
            Unable to render user workspace right now. {this.state.message}
          </div>
        </section>
      );
    }
    return this.props.children;
  }
}

const presenceLabel = (user: AdminUserDirectoryItem) => {
  return user.presence_display.status_label;
};

const resolvePresenceTone = (user: AdminUserDirectoryItem) => {
  if (user.presence_display.status_label === "Inactive") return "is-inactive";
  if (user.presence.state === "away") return "is-away";
  return user.presence.is_online ? "is-online" : "is-offline";
};

const formatDateTime = (value?: string | null) => {
  if (!value) return "Never seen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Never seen";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};

const formatRelativeLastSeen = (value?: string | null) => {
  if (!value) return "Never seen";
  const seen = new Date(value);
  if (Number.isNaN(seen.getTime())) return "Never seen";
  const deltaMs = Date.now() - seen.getTime();
  if (deltaMs < 60_000) return "Just now";
  const mins = Math.floor(deltaMs / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};

const AdminDashboardPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const realtime = React.useContext(RealtimeContext);
  const realtimeStatus = realtime?.status || "offline";
  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const canAccessAdmin = !!currentUser && (currentUser.is_superuser || currentUser.is_amo_admin);
  const effectiveAmoId = isSuperuser
    ? (localStorage.getItem(LS_ACTIVE_AMO_ID) || currentUser?.amo_id || null)
    : (currentUser?.amo_id || null);

  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<UserTab>("users");
  const [statusFilter, setStatusFilter] = useState<PresenceFilter>("all");
  const [roleFilter, setRoleFilter] = useState<string>("all");

  const directoryQuery = useQuery({
    queryKey: ["admin-user-directory", effectiveAmoId, search],
    queryFn: () => getAdminUserDirectory({ amo_id: effectiveAmoId, search, limit: 200 }),
    enabled: canAccessAdmin && !!effectiveAmoId,
  });

  const directory = directoryQuery.data;
  const items = useMemo(
    () => (directory?.items ?? []).map((item) => ({
      ...item,
      display_title: item.display_title || item.position_title || String(item.role || "Portal User"),
      presence: item.presence || { state: "offline", is_online: false, last_seen_at: item.last_login_at || null, source: "fallback" },
      presence_display: item.presence_display || {
        status_label: item.is_active ? "Offline" : "Inactive",
        last_seen_label: item.last_login_at ? "Last seen" : "Never seen",
        last_seen_at: item.last_login_at || null,
        last_seen_at_display: item.last_login_at || null,
      },
    })),
    [directory?.items],
  );
  const metrics = directory?.metrics ?? ZERO_METRICS;
  const roleOptions = useMemo(
    () => ["all", ...Array.from(new Set(items.map((item) => item.display_title))).sort()],
    [items],
  );

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesRole = roleFilter === "all" || item.display_title === roleFilter;
      const userStatus = presenceLabel(item).toLowerCase();
      const matchesStatus =
        statusFilter === "all"
          ? true
          : statusFilter === "inactive"
            ? !item.is_active
            : statusFilter === "away"
              ? item.is_active && item.presence.state === "away"
              : userStatus === statusFilter;
      return matchesRole && matchesStatus;
    });
  }, [items, roleFilter, statusFilter, currentUser?.id, realtimeStatus, clientOnline, nowIso]);

  const departmentGroups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      const key = item.department_name || "Unassigned";
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [items]);

  const managerialGroups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      const key = item.position_title || item.role;
      if (!item.position_title && !String(item.role).includes("MANAGER") && !item.is_amo_admin && !item.is_superuser) {
        continue;
      }
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [items]);

  const toggleUserMutation = useMutation({
    mutationFn: async (user: AdminUserDirectoryItem) => {
      if (user.is_active) {
        await disableAdminUser(user.id);
      } else {
        await enableAdminUser(user.id);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
    },
  });

  useEffect(() => {
    if (canAccessAdmin) return;
    navigate(amoCode ? `/maintenance/${amoCode}/${ctx.department || "planning"}` : "/login", { replace: true });
  }, [amoCode, canAccessAdmin, ctx.department, navigate]);

  if (!currentUser) {
    return (
      <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
        <div className="admin-users-workspace aum-shell">
          <section className="aum-panel">
            <div className="aum-empty">Loading user management workspace…</div>
          </section>
        </div>
      </DepartmentLayout>
    );
  }

  if (!canAccessAdmin) {
    return (
      <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
        <div className="admin-users-workspace aum-shell">
          <section className="aum-panel">
            <div className="aum-empty">You do not have permission to access User Management.</div>
          </section>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
      <AdminUsersErrorBoundary>
      <div className="admin-users-workspace aum-shell">
        <header className="aum-header">
          <div>
            <p className="aum-eyebrow">User Management</p>
            <h1>User management</h1>
            <p className="aum-subtitle">
              Single-page workspace for people, presence, permissions, and HR review.
            </p>
          </div>
          <div className="aum-header-actions">
            <span className={`aum-live ${realtimeStatus === "live" ? "is-live" : ""}`}>{realtimeStatus}</span>
            <button type="button" className="aum-button aum-button--secondary" onClick={() => directoryQuery.refetch()}>
              Refresh
            </button>
            <button type="button" className="aum-button aum-button--primary" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}>
              Add user
            </button>
          </div>
        </header>

        <section className="aum-metrics-grid">
          <article className="aum-metric-card">
            <span>Total users</span>
            <strong>{metrics?.total_users ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Active</span>
            <strong>{metrics?.active_users ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Online now</span>
            <strong>{metrics?.online_users ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Away</span>
            <strong>{metrics?.away_users ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Recently active (10m)</span>
            <strong>{metrics?.recently_active_users ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Inactive</span>
            <strong>{metrics?.inactive_users ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Managers</span>
            <strong>{metrics?.managers ?? 0}</strong>
          </article>
          <article className="aum-metric-card">
            <span>Unassigned department</span>
            <strong>{metrics?.departmentless_users ?? 0}</strong>
          </article>
        </section>

        <div className="aum-tabs" role="tablist" aria-label="User management sections">
          {([
            ["users", "Users"],
            ["groups", "Groups & cohorts"],
            ["hr", "Import & HR metrics"],
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

        {activeTab === "users" && (
          <section className="aum-panel">
            <div className="aum-panel-header">
              <div>
                <h2>User directory</h2>
                <p>Dense operational table for HR, QA, and managerial review.</p>
              </div>
              <div className="aum-filters">
                <input
                  className="aum-input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search name, email, staff code, or title"
                />
                <select className="aum-select" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                  {roleOptions.map((role) => (
                    <option key={role} value={role}>
                      {role === "all" ? "All roles" : role}
                    </option>
                  ))}
                </select>
                <select className="aum-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
                  <option value="all">All statuses</option>
                  <option value="online">Online</option>
                  <option value="away">Away</option>
                  <option value="offline">Offline</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
            </div>

            {directoryQuery.isLoading ? (
              <div className="aum-empty">Loading users…</div>
            ) : directoryQuery.error ? (
              <div className="aum-empty">Unable to load users right now. {(directoryQuery.error as Error).message}</div>
            ) : (
              <div className="aum-table-wrap">
                <table className="aum-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Staff code</th>
                      <th>Role</th>
                      <th>Department</th>
                      <th>Account</th>
                      <th>Status</th>
                      <th>Last seen</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredItems.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="aum-empty-row">No users match the current filter.</td>
                      </tr>
                    ) : (
                      filteredItems.map((user) => {
                        const primaryLastSeen = user.presence_display.last_seen_label === "Active now"
                          ? "Active now"
                          : user.presence_display.last_seen_label === "Never seen"
                            ? "Never seen"
                            : formatRelativeLastSeen(user.presence_display.last_seen_at || user.last_login_at);
                        const secondaryLastSeen =
                          user.presence_display.status_label === "Online" ||
                          primaryLastSeen === "Never seen"
                            ? null
                            : formatDateTime(user.presence_display.last_seen_at || user.last_login_at);
                        return (
                        <tr key={user.id}>
                          <td>
                            <button type="button" className="aum-link" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/${user.id}`)}>
                              {user.full_name}
                            </button>
                            <div className="aum-muted">{user.email}</div>
                          </td>
                          <td>{user.staff_code}</td>
                          <td>
                            <div>{user.display_title}</div>
                          </td>
                          <td>{user.department_name || "—"}</td>
                          <td>{user.is_active ? "Enabled" : "Disabled"}</td>
                          <td>
                            <span className={`aum-status ${resolvePresenceTone(user)}`}>
                              {presenceLabel(user)}
                            </span>
                          </td>
                          <td>
                            <div>{primaryLastSeen}</div>
                            {secondaryLastSeen ? <div className="aum-muted">{secondaryLastSeen}</div> : null}
                          </td>
                          <td>
                            <div className="aum-row-actions">
                              <button type="button" className="aum-button aum-button--ghost" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/${user.id}`)}>
                                View
                              </button>
                              <button
                                type="button"
                                className="aum-button aum-button--ghost"
                                onClick={() => toggleUserMutation.mutate(user)}
                                disabled={toggleUserMutation.isPending}
                              >
                                {user.is_active ? "Disable" : "Enable"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )})
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {activeTab === "groups" && (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Department groups</h2>
                  <p>Live cohorts derived from current department assignments.</p>
                </div>
              </div>
              <div className="aum-list-grid">
                {departmentGroups.map(([label, count]) => (
                  <div key={label} className="aum-list-card">
                    <strong>{label}</strong>
                    <span>{count} users</span>
                  </div>
                ))}
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Post-holder cohorts</h2>
                  <p>Managerial and named responsibility groupings based on active titles.</p>
                </div>
              </div>
              <div className="aum-list-grid">
                {managerialGroups.length === 0 ? (
                  <div className="aum-empty">No managerial cohorts found.</div>
                ) : (
                  managerialGroups.map(([label, count]) => (
                    <div key={label} className="aum-list-card">
                      <strong>{label}</strong>
                      <span>{count} users</span>
                    </div>
                  ))
                )}
              </div>
            </article>
          </section>
        )}

        {activeTab === "hr" && (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>HR watchpoints</h2>
                  <p>Quick signals for long-run management review.</p>
                </div>
              </div>
              <div className="aum-list-grid">
                <div className="aum-list-card">
                  <strong>Users never seen</strong>
                  <span>{items.filter((item) => !item.presence.last_seen_at && !item.last_login_at).length}</span>
                </div>
                <div className="aum-list-card">
                  <strong>Disabled accounts</strong>
                  <span>{items.filter((item) => !item.is_active).length}</span>
                </div>
                <div className="aum-list-card">
                  <strong>Unassigned department</strong>
                  <span>{items.filter((item) => !item.department_name).length}</span>
                </div>
                <div className="aum-list-card">
                  <strong>Managerial seats</strong>
                  <span>{items.filter((item) => item.position_title || item.is_amo_admin || item.is_superuser).length}</span>
                </div>
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Operational note</h2>
                  <p>This repair build focuses on stable user operations and accurate presence.</p>
                </div>
              </div>
              <div className="aum-note">
                Persistent custom groups are not enabled on this page yet. This avoids another schema-drift failure while the current account schema is being stabilized.
              </div>
            </article>
          </section>
        )}
      </div>
      </AdminUsersErrorBoundary>
    </DepartmentLayout>
  );
};

export default AdminDashboardPage;
