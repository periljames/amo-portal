import { isTenantAdmin } from "../../utils/tenantAccess";
import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Download,
  Eye,
  KeyRound,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  ShieldOff,
  Trash2,
  UserCheck,
  UserPlus,
  UserRoundCog,
  UserX,
  UsersRound,
  X,
} from "lucide-react";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext, getToken, onSessionEvent } from "../../services/auth";
import { readCachedAdminProfileState } from "../../services/adminProfileMode";
import { getTenantAccessFramework } from "../../services/accessProfiles";
import {
  LS_ACTIVE_AMO_ID,
  applyAdminUserEmploymentAction,
  bulkAdminUserAction,
  createAdminGroup,
  deleteAdminGroup,
  disableAdminUser,
  downloadAdminUsersExport,
  enableAdminUser,
  forceAdminUserPasswordReset,
  listAdminDepartments,
  listAdminGroups,
  listAdminUserSummaries,
  revokeAdminUserAccess,
  updateAdminUser,
  type AdminDepartmentRead,
  type AdminUserDirectoryItem,
  type AdminUserGroupRead,
  type BulkUserActionPayload,
  type UserEmploymentActionPayload,
} from "../../services/adminUsers";
import {
  getAdminUserDirectoryPage,
  type AdminUserAccountFilter,
  type AdminUserSortDirection,
  type AdminUserSortField,
} from "../../services/adminUserDirectory";
import "../../styles/admin-user-management-v2.css";

type UrlParams = { amoCode?: string };
type WorkspaceTab = "directory" | "roles" | "groups" | "permissions" | "lifecycle";
type BatchAction = BulkUserActionPayload["action"] | "export_csv" | "";

const AccessRolesPanel = React.lazy(() => import("./AccessRolesPanel"));

const PAGE_SIZES = [25, 50, 100];

function formatRole(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function relativeTime(value?: string | null): string {
  if (!value) return "Never";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Never";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 45) return "Now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [delayMs, value]);
  return debounced;
}

function downloadBlob({ blob, filename }: { blob: Blob; filename: string }): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function presenceTone(user: AdminUserDirectoryItem): "online" | "away" | "offline" | "inactive" {
  if (!user.is_active) return "inactive";
  if (user.presence.is_online && user.presence.state === "away") return "away";
  if (user.presence.is_online) return "online";
  return "offline";
}

function IconButton({
  label,
  onClick,
  children,
  disabled = false,
  danger = false,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      className={`aum2-icon-button${danger ? " is-danger" : ""}`}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export default function AdminUserManagementPage() {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const ctx = getContext();
  const currentUser = useMemo(() => getCachedUser(), []);
  const [sessionActive, setSessionActive] = useState(() => Boolean(getToken()));
  const isSuperuser = Boolean(currentUser?.is_superuser);
  const canAccessAdmin = Boolean(
    sessionActive && currentUser && (
      currentUser.is_superuser
      || isTenantAdmin(currentUser)
      || readCachedAdminProfileState(amoCode ?? ctx.amoCode ?? "UNKNOWN")?.active
    ),
  );
  const effectiveAmoId = isSuperuser
    ? localStorage.getItem(LS_ACTIVE_AMO_ID) || currentUser?.amo_id || null
    : currentUser?.amo_id || null;
  const basePath = `/maintenance/${amoCode ?? ctx.amoCode ?? "UNKNOWN"}/admin/users`;

  const requestedTab = searchParams.get("tab");
  const [tab, setTab] = useState<WorkspaceTab>(() =>
    (["directory", "roles", "groups", "permissions", "lifecycle"] as WorkspaceTab[]).includes(requestedTab as WorkspaceTab)
      ? requestedTab as WorkspaceTab
      : "directory",
  );
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput.trim(), 350);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [accessProfileFilter, setAccessProfileFilter] = useState("all");
  const [accountFilter, setAccountFilter] = useState<AdminUserAccountFilter>("all");
  const [departmentFilter, setDepartmentFilter] = useState<"all" | "unassigned" | string>("all");
  const [sortBy, setSortBy] = useState<AdminUserSortField>("name");
  const [sortDirection, setSortDirection] = useState<AdminUserSortDirection>("asc");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState("");
  const [batchAction, setBatchAction] = useState<BatchAction>("");
  const [batchDepartmentId, setBatchDepartmentId] = useState("");
  const [batchAccessProfileId, setBatchAccessProfileId] = useState("");

  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupCode, setNewGroupCode] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [lifecycleSearch, setLifecycleSearch] = useState("");
  const debouncedLifecycleSearch = useDebouncedValue(lifecycleSearch.trim(), 350);
  const [lifecycleUserId, setLifecycleUserId] = useState("");
  const [lifecycleAction, setLifecycleAction] = useState<UserEmploymentActionPayload["action"]>("transfer");
  const [lifecycleDepartmentId, setLifecycleDepartmentId] = useState("");
  const [lifecycleTitle, setLifecycleTitle] = useState("");
  const [lifecycleNote, setLifecycleNote] = useState("");
  const [lifecycleFrom, setLifecycleFrom] = useState("");
  const [lifecycleTo, setLifecycleTo] = useState("");

  useEffect(() => {
    return onSessionEvent((detail) => {
      if (detail.type === "authenticated" || detail.type === "activity") {
        setSessionActive(Boolean(getToken()));
      }
      if (["expired", "idle-logout", "manual-logout"].includes(detail.type)) {
        setSessionActive(false);
      }
    });
  }, []);

  useEffect(() => {
    setPage(1);
    setSelectedIds([]);
  }, [search, accessProfileFilter, accountFilter, departmentFilter, pageSize, sortBy, sortDirection]);

  useEffect(() => {
    const nextTab = (["directory", "roles", "groups", "permissions", "lifecycle"] as WorkspaceTab[]).includes(requestedTab as WorkspaceTab)
      ? requestedTab as WorkspaceTab
      : "directory";
    setTab(nextTab);
  }, [requestedTab]);

  useEffect(() => {
    if (canAccessAdmin) return;
    navigate(amoCode ? `/maintenance/${amoCode}/${ctx.department || "planning"}` : "/login", {
      replace: true,
    });
  }, [amoCode, canAccessAdmin, ctx.department, navigate]);

  const directoryQuery = useQuery({
    queryKey: [
      "admin-user-directory",
      effectiveAmoId,
      page,
      pageSize,
      search,
      accessProfileFilter,
      accountFilter,
      departmentFilter,
      sortBy,
      sortDirection,
    ],
    queryFn: () =>
      getAdminUserDirectoryPage({
        amo_id: effectiveAmoId,
        page,
        page_size: pageSize,
        search,
        access_profile_id: accessProfileFilter,
        account_status: accountFilter,
        department_id: departmentFilter,
        sort_by: sortBy,
        sort_direction: sortDirection,
      }),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 5_000,
    refetchInterval: canAccessAdmin ? 10_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  const departmentsQuery = useQuery({
    queryKey: ["admin-user-departments", effectiveAmoId],
    queryFn: () => listAdminDepartments(effectiveAmoId || undefined),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 60_000,
  });
  const accessFrameworkQuery = useQuery({
    queryKey: ["accounts", "access-framework", effectiveAmoId],
    queryFn: () => getTenantAccessFramework(effectiveAmoId),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 30_000,
  });
  const groupsQuery = useQuery({
    queryKey: ["admin-user-groups", effectiveAmoId],
    queryFn: () => listAdminGroups(effectiveAmoId),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 30_000,
  });
  const lifecycleUsersQuery = useQuery({
    queryKey: ["admin-user-lifecycle-search", effectiveAmoId, debouncedLifecycleSearch],
    queryFn: () =>
      listAdminUserSummaries({
        amo_id: effectiveAmoId || undefined,
        search: debouncedLifecycleSearch || undefined,
        limit: 50,
      }),
    enabled: canAccessAdmin && Boolean(effectiveAmoId) && tab === "lifecycle",
    staleTime: 15_000,
  });

  const data = directoryQuery.data;
  const items = data?.items ?? [];
  const metrics = data?.metrics;
  const departments = departmentsQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const accessProfiles = (accessFrameworkQuery.data?.profiles ?? []).filter((profile) => profile.is_active);
  const allPageSelected = items.length > 0 && items.every((item) => selectedIds.includes(item.id));

  const refreshDirectory = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
  };
  const refreshSupportingData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-user-groups"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-departments"] }),
    ]);
  };

  const toggleUserMutation = useMutation({
    mutationFn: (user: AdminUserDirectoryItem) =>
      user.is_active ? disableAdminUser(user.id) : enableAdminUser(user.id),
    onSuccess: refreshDirectory,
    onError: (error: Error) => setFeedback(error.message),
  });
  const resetPasswordMutation = useMutation({
    mutationFn: (userId: string) => forceAdminUserPasswordReset(userId),
    onSuccess: async () => {
      setFeedback("Password reset is required at the user’s next sign-in.");
      await refreshDirectory();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const revokeMutation = useMutation({
    mutationFn: (userId: string) => revokeAdminUserAccess(userId),
    onSuccess: async () => {
      setFeedback("Existing access tokens were revoked.");
      await refreshDirectory();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const departmentMutation = useMutation({
    mutationFn: ({ userId, departmentId }: { userId: string; departmentId: string | null }) =>
      updateAdminUser(userId, { department_id: departmentId }),
    onSuccess: refreshDirectory,
    onError: (error: Error) => setFeedback(error.message),
  });
  const bulkMutation = useMutation({
    mutationFn: (payload: BulkUserActionPayload) => bulkAdminUserAction(payload),
    onSuccess: async (result) => {
      setFeedback(result.detail);
      setSelectedIds([]);
      setBatchAction("");
      await refreshDirectory();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const exportMutation = useMutation({
    mutationFn: ({ userIds, format }: { userIds: string[]; format: "csv" | "json" }) =>
      downloadAdminUsersExport(userIds, format),
    onSuccess: (result) => downloadBlob(result),
    onError: (error: Error) => setFeedback(error.message),
  });
  const createGroupMutation = useMutation({
    mutationFn: () =>
      createAdminGroup({
        amo_id: effectiveAmoId || "",
        code: newGroupCode.trim() || newGroupName.trim(),
        name: newGroupName.trim(),
        description: newGroupDescription.trim() || undefined,
        group_type: "CUSTOM",
        is_active: true,
      }),
    onSuccess: async () => {
      setNewGroupName("");
      setNewGroupCode("");
      setNewGroupDescription("");
      setFeedback("Group created.");
      await refreshSupportingData();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => deleteAdminGroup(groupId),
    onSuccess: refreshSupportingData,
    onError: (error: Error) => setFeedback(error.message),
  });
  const lifecycleMutation = useMutation({
    mutationFn: () =>
      applyAdminUserEmploymentAction(lifecycleUserId, {
        action: lifecycleAction,
        department_id: lifecycleDepartmentId || undefined,
        position_title: lifecycleTitle.trim() || undefined,
        note: lifecycleNote.trim() || undefined,
        effective_from: lifecycleFrom || undefined,
        effective_to: lifecycleTo || undefined,
      }),
    onSuccess: async (result) => {
      setFeedback(`Lifecycle action “${result.action}” completed.`);
      await refreshDirectory();
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  if (!currentUser || !canAccessAdmin) {
    return (
      <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
        <div className="aum2-shell"><div className="aum2-empty">Loading user management…</div></div>
      </DepartmentLayout>
    );
  }

  const executeBatch = () => {
    if (!selectedIds.length || !batchAction) return;
    if (batchAction === "export_csv") {
      exportMutation.mutate({ userIds: selectedIds, format: "csv" });
      return;
    }
    bulkMutation.mutate({
      user_ids: selectedIds,
      action: batchAction,
      department_id: batchAction === "assign_department" ? batchDepartmentId || undefined : undefined,
      access_profile_id: batchAction === "assign_access_profile" ? batchAccessProfileId || undefined : undefined,
      note: `Applied from paginated user directory`,
    });
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
      <main className="aum2-shell">
        <header className="aum2-header">
          <div>
            <div className="aum2-title-row">
              <UsersRound size={20} aria-hidden="true" />
              <h1>User management</h1>
            </div>
            <p>Accounts, access profiles, approved positions, module boundaries, personal authorizations and employment lifecycle.</p>
          </div>
          <div className="aum2-header-actions">
            <button type="button" className="aum2-compact-action" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode || ctx.amoSlug || ctx.amoCode || "UNKNOWN")}/access-governance`)}>
              <ShieldCheck size={16} /> Administrator governance
            </button>
            <IconButton label="Refresh directory" onClick={() => void refreshDirectory()} disabled={directoryQuery.isFetching}>
              <RefreshCw size={17} className={directoryQuery.isFetching ? "is-spinning" : ""} />
            </IconButton>
            <IconButton label="Add user" onClick={() => navigate(`${basePath}/new`)}>
              <UserPlus size={18} />
            </IconButton>
          </div>
        </header>

        {feedback ? (
          <div className="aum2-feedback" role="status">
            <span>{feedback}</span>
            <IconButton label="Dismiss message" onClick={() => setFeedback("")}><X size={15} /></IconButton>
          </div>
        ) : null}

        <nav className="aum2-tabs" aria-label="User management sections">
          {([
            ["directory", "Directory", UsersRound],
            ["roles", "Structure & access", ShieldCheck],
            ["groups", "Groups", UserRoundCog],
            ["permissions", "Certifying authorizations", KeyRound],
            ["lifecycle", "Lifecycle", UserCheck],
          ] as const).map(([key, label, Icon]) => (
            <button key={key} type="button" className={tab === key ? "is-active" : ""} onClick={() => {
              setTab(key);
              const next = new URLSearchParams(searchParams);
              if (key === "directory") next.delete("tab");
              else next.set("tab", key);
              setSearchParams(next, { replace: true });
            }}>
              <Icon size={16} aria-hidden="true" /><span>{label}</span>
            </button>
          ))}
        </nav>

        {tab === "directory" ? (
          <section className="aum2-panel">
            <div className="aum2-summary-strip" aria-label="Directory summary">
              <span><strong>{metrics?.total_users ?? 0}</strong> Total</span>
              <span><strong>{metrics?.active_users ?? 0}</strong> Active</span>
              <span><strong>{metrics?.inactive_users ?? 0}</strong> Disabled</span>
              <span><strong>{metrics?.departmentless_users ?? 0}</strong> Unassigned</span>
            </div>

            <div className="aum2-toolbar">
              <label className="aum2-search">
                <Search size={16} aria-hidden="true" />
                <input
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search name, email, staff code or title"
                  aria-label="Search users"
                />
                {searchInput ? (
                  <button type="button" onClick={() => setSearchInput("")} aria-label="Clear search" title="Clear search"><X size={14} /></button>
                ) : null}
              </label>
              <select value={accessProfileFilter} onChange={(event) => setAccessProfileFilter(event.target.value)} aria-label="Filter by access profile">
                <option value="all">All access profiles</option>
                {accessProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}
              </select>
              <select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)} aria-label="Filter by department">
                <option value="all">All departments</option>
                <option value="unassigned">Unassigned</option>
                {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
              </select>
              <select value={accountFilter} onChange={(event) => setAccountFilter(event.target.value as AdminUserAccountFilter)} aria-label="Filter account status">
                <option value="all">All accounts</option>
                <option value="active">Enabled</option>
                <option value="inactive">Disabled</option>
              </select>
              <select value={`${sortBy}:${sortDirection}`} onChange={(event) => {
                const [field, direction] = event.target.value.split(":") as [AdminUserSortField, AdminUserSortDirection];
                setSortBy(field);
                setSortDirection(direction);
              }} aria-label="Sort directory">
                <option value="name:asc">Name A–Z</option>
                <option value="name:desc">Name Z–A</option>
                <option value="created_at:desc">Newest accounts</option>
                <option value="last_login_at:desc">Recent sign-in</option>
                <option value="staff_code:asc">Staff code</option>
              </select>
            </div>

            {selectedIds.length ? (
              <div className="aum2-batch-bar">
                <strong>{selectedIds.length} selected</strong>
                <select value={batchAction} onChange={(event) => setBatchAction(event.target.value as BatchAction)} aria-label="Batch action">
                  <option value="">Choose action</option>
                  <option value="enable">Enable</option>
                  <option value="disable">Disable</option>
                  <option value="assign_department">Assign department</option>
                  <option value="clear_department">Clear department</option>
                  <option value="assign_access_profile">Assign supporting access profile</option>
                  <option value="export_csv">Export CSV</option>
                </select>
                {batchAction === "assign_department" ? (
                  <select value={batchDepartmentId} onChange={(event) => setBatchDepartmentId(event.target.value)} aria-label="Target department">
                    <option value="">Choose department</option>
                    {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select>
                ) : null}
                {batchAction === "assign_access_profile" ? (
                  <select value={batchAccessProfileId} onChange={(event) => setBatchAccessProfileId(event.target.value)} aria-label="Target supporting access profile">
                    <option value="">Choose supporting access profile</option>
                    {accessProfiles.filter((profile) => !profile.is_regulated).map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}
                  </select>
                ) : null}
                <button
                  type="button"
                  className="aum2-compact-action"
                  onClick={executeBatch}
                  disabled={
                    !batchAction
                    || bulkMutation.isPending
                    || (batchAction === "assign_department" && !batchDepartmentId)
                    || (batchAction === "assign_access_profile" && !batchAccessProfileId)
                  }
                >Apply</button>
                <IconButton label="Clear selection" onClick={() => setSelectedIds([])}><X size={16} /></IconButton>
              </div>
            ) : null}

            <div className="aum2-table-wrap" aria-busy={directoryQuery.isLoading}>
              <table className="aum2-table">
                <thead>
                  <tr>
                    <th className="is-check"><input type="checkbox" checked={allPageSelected} onChange={() => {
                      if (allPageSelected) setSelectedIds((current) => current.filter((id) => !items.some((item) => item.id === id)));
                      else setSelectedIds((current) => Array.from(new Set([...current, ...items.map((item) => item.id)])));
                    }} aria-label="Select page" /></th>
                    <th>User</th>
                    <th>Position &amp; access</th>
                    <th>Department</th>
                    <th>Access</th>
                    <th>Activity</th>
                    <th className="is-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {directoryQuery.isLoading ? (
                    <tr><td colSpan={7} className="aum2-empty">Loading users…</td></tr>
                  ) : directoryQuery.error ? (
                    <tr><td colSpan={7} className="aum2-empty">{(directoryQuery.error as Error).message}</td></tr>
                  ) : items.length === 0 ? (
                    <tr><td colSpan={7} className="aum2-empty">No users match the current filters.</td></tr>
                  ) : items.map((user) => {
                    const tone = presenceTone(user);
                    const checked = selectedIds.includes(user.id);
                    const activityValue = user.presence.last_seen_at || user.last_login_at;
                    return (
                      <tr key={user.id} className={checked ? "is-selected" : ""}>
                        <td className="is-check"><input type="checkbox" checked={checked} onChange={() => setSelectedIds((current) => checked ? current.filter((id) => id !== user.id) : [...current, user.id])} aria-label={`Select ${user.full_name}`} /></td>
                        <td>
                          <button type="button" className="aum2-user-link" onClick={() => navigate(`${basePath}/${user.id}`)}>{user.full_name}</button>
                          <span className="aum2-secondary">{user.staff_code} · {user.email}</span>
                        </td>
                        <td>
                          <strong className="aum2-cell-primary">{user.position_title || user.access_profile_name || formatRole(user.role)}</strong>
                          <span className="aum2-secondary">{user.access_profile_name || formatRole(user.role)}{user.is_amo_admin ? " · Tenant admin" : ""}{user.is_superuser ? " · Platform superuser" : ""}</span>
                        </td>
                        <td>
                          <select className="aum2-inline-select" value={user.department_id || ""} onChange={(event) => departmentMutation.mutate({ userId: user.id, departmentId: event.target.value || null })} aria-label={`Department for ${user.full_name}`}>
                            <option value="">Unassigned</option>
                            {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                          </select>
                        </td>
                        <td>
                          <span className={`aum2-access ${user.is_active ? "is-enabled" : "is-disabled"}`} title={user.is_active ? "Account enabled" : "Account disabled"}>
                            {user.is_active ? <ShieldCheck size={15} /> : <ShieldOff size={15} />}
                            <span>{user.is_active ? "Enabled" : "Disabled"}</span>
                          </span>
                        </td>
                        <td>
                          <div className="aum2-activity" title={`${user.presence_display.status_label}; ${activityValue ? new Date(activityValue).toLocaleString() : "never seen"}`}>
                            <span className={`aum2-presence-dot is-${tone}`} aria-label={user.presence_display.status_label} />
                            <span>{tone === "online" ? "Now" : tone === "away" ? "Idle" : relativeTime(activityValue)}</span>
                          </div>
                        </td>
                        <td className="is-actions">
                          <div className="aum2-row-actions">
                            <IconButton label={`Open ${user.full_name}`} onClick={() => navigate(`${basePath}/${user.id}`)}><Eye size={16} /></IconButton>
                            <details className="aum2-menu">
                              <summary aria-label={`More actions for ${user.full_name}`} title="More actions"><MoreHorizontal size={17} /></summary>
                              <div>
                                <button type="button" onClick={() => toggleUserMutation.mutate(user)}>{user.is_active ? <UserX size={15} /> : <UserCheck size={15} />}{user.is_active ? "Disable account" : "Enable account"}</button>
                                <button type="button" onClick={() => resetPasswordMutation.mutate(user.id)}><KeyRound size={15} />Require password reset</button>
                                <button type="button" onClick={() => revokeMutation.mutate(user.id)}><ShieldOff size={15} />Revoke sessions</button>
                                <button type="button" onClick={() => exportMutation.mutate({ userIds: [user.id], format: "csv" })}><Download size={15} />Export record</button>
                              </div>
                            </details>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <footer className="aum2-pagination">
              <span>{data?.total ?? 0} users · Page {data?.page ?? page} of {Math.max(1, data?.pages ?? 1)}</span>
              <label>Rows<select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
              <div>
                <IconButton label="First page" onClick={() => setPage(1)} disabled={!data?.has_previous}><ChevronsLeft size={16} /></IconButton>
                <IconButton label="Previous page" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={!data?.has_previous}><ChevronLeft size={16} /></IconButton>
                <IconButton label="Next page" onClick={() => setPage((current) => current + 1)} disabled={!data?.has_next}><ChevronRight size={16} /></IconButton>
                <IconButton label="Last page" onClick={() => setPage(Math.max(1, data?.pages ?? 1))} disabled={!data?.has_next}><ChevronsRight size={16} /></IconButton>
              </div>
            </footer>
          </section>
        ) : null}

        {tab === "roles" ? (
          <><section className="aum2-panel">
            <div className="aum2-section-heading"><div><h2>Organisation appointments</h2><p>Maintain actual positions, reporting lines and effective-dated appointments in Workforce. The access profiles below define portal permissions.</p></div></div>
            <Link className="aum2-primary-action" to={`/maintenance/${amoCode}/rostering/settings?section=workforce&workforce_view=governance`}>Open Workforce structure and appointments</Link>
          </section><React.Suspense fallback={<section className="aum2-panel">Loading roles and structure…</section>}>
            <AccessRolesPanel amoId={effectiveAmoId} />
          </React.Suspense></>
        ) : null}

        {tab === "groups" ? (
          <section className="aum2-grid-two">
            <article className="aum2-panel">
              <div className="aum2-section-heading"><div><h2>Create group</h2><p>Operational cohorts for assignments and access policy.</p></div><Plus size={18} /></div>
              <div className="aum2-form-grid">
                <label><span>Name</span><input value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} /></label>
                <label><span>Code</span><input value={newGroupCode} onChange={(event) => setNewGroupCode(event.target.value)} placeholder="Generated when blank" /></label>
                <label className="is-wide"><span>Description</span><textarea value={newGroupDescription} onChange={(event) => setNewGroupDescription(event.target.value)} rows={3} /></label>
                <button type="button" className="aum2-primary-action" disabled={!newGroupName.trim() || createGroupMutation.isPending} onClick={() => createGroupMutation.mutate()}><Plus size={16} />Create</button>
              </div>
            </article>
            <article className="aum2-panel">
              <div className="aum2-section-heading"><div><h2>Groups</h2><p>{groups.length} configured. Manage membership from each user’s profile.</p></div></div>
              <div className="aum2-compact-list">
                {groups.map((group: AdminUserGroupRead) => (
                  <div key={group.id}><div><strong>{group.name}</strong><span>{group.member_count} members · {group.code}</span></div>{!group.is_system_managed ? <IconButton label={`Delete ${group.name}`} danger onClick={() => { if (window.confirm(`Delete ${group.name}?`)) deleteGroupMutation.mutate(group.id); }}><Trash2 size={15} /></IconButton> : null}</div>
                ))}
                {groupsQuery.isPending ? <div role="status" className="aum2-empty">Loading groups…</div> : groupsQuery.isError ? <div role="alert" className="aum2-empty">Unable to load groups. <button type="button" onClick={() => void groupsQuery.refetch()}>Retry groups</button></div> : !groups.length ? <div className="aum2-empty">No groups configured.</div> : null}
              </div>
            </article>
          </section>
        ) : null}

        {tab === "permissions" ? (
          <section className="aum2-panel">
            <div className="aum2-section-heading"><div><h2>Certifying authorizations are not portal roles</h2><p>User Management shows accounts, organization positions and portal access. Personal maintenance privileges are issued only through the governed readiness and approval workflow.</p></div><KeyRound size={18} /></div>
            <div className="aum2-form-grid">
              <p className="is-wide">Use Training &amp; Competence to prepare the case, verify licence, training, experience and assessment evidence, record the required recommendation or committee decision, and issue, restrict, suspend or withdraw the retained authorization record.</p>
              <button type="button" className="aum2-primary-action" onClick={() => navigate(`/maintenance/${amoCode ?? ctx.amoCode ?? "UNKNOWN"}/training/competence/authorizations`)}>Open governed authorizations</button>
            </div>
          </section>
        ) : null}

        {tab === "lifecycle" ? (
          <section className="aum2-panel">
            <div className="aum2-section-heading"><div><h2>Employment lifecycle</h2><p>Employment events update status, department and descriptive title. Governed position changes are made in Workforce; portal permissions are configured in Structure &amp; access.</p></div><UserRoundCog size={18} /></div>
            <Link className="aum2-primary-action" to={`/maintenance/${amoCode}/rostering/settings?section=workforce&workforce_view=governance`}>Open Workforce appointments</Link>
            {lifecycleUsersQuery.isError ? <p role="alert">Unable to load personnel. <button type="button" onClick={() => void lifecycleUsersQuery.refetch()}>Retry personnel</button></p> : null}
            <div className="aum2-form-grid is-lifecycle">
              <label className="is-wide"><span>Find user</span><input value={lifecycleSearch} onChange={(event) => setLifecycleSearch(event.target.value)} placeholder="Search name, email or staff code" /></label>
              <label className="is-wide"><span>User</span><select value={lifecycleUserId} onChange={(event) => setLifecycleUserId(event.target.value)}><option value="">Choose user</option>{(lifecycleUsersQuery.data ?? []).map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.staff_code}</option>)}</select></label>
              <label><span>Action</span><select value={lifecycleAction} onChange={(event) => setLifecycleAction(event.target.value as UserEmploymentActionPayload["action"])}><option value="new_hire">New hire</option><option value="transfer">Transfer descriptive department</option><option value="schedule_leave">Schedule leave</option><option value="return_from_leave">Return from leave</option><option value="resign">Resign</option><option value="reinstate">Reinstate</option><option value="reemploy">Re-employ</option></select><small>Promotion and demotion are effective-dated Workforce position changes.</small></label>
              <label><span>Department</span><select value={lifecycleDepartmentId} onChange={(event) => setLifecycleDepartmentId(event.target.value)}><option value="">No department change</option>{departments.map((department: AdminDepartmentRead) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
              <label><span>Position title</span><input value={lifecycleTitle} onChange={(event) => setLifecycleTitle(event.target.value)} /></label>
              <label><span>{lifecycleAction === "reinstate" || lifecycleAction === "reemploy" ? "New workforce start" : "Effective from"}</span><input type="datetime-local" required={lifecycleAction === "reinstate" || lifecycleAction === "reemploy"} value={lifecycleFrom} onChange={(event) => setLifecycleFrom(event.target.value)} />{lifecycleAction === "reinstate" || lifecycleAction === "reemploy" ? <small>This starts a new contract period and becomes the locked workforce date.</small> : null}</label>
              <label><span>Effective to</span><input type="datetime-local" value={lifecycleTo} onChange={(event) => setLifecycleTo(event.target.value)} /></label>
              <label className="is-wide"><span>Audit note</span><textarea rows={3} value={lifecycleNote} onChange={(event) => setLifecycleNote(event.target.value)} /></label>
              <button type="button" className="aum2-primary-action" disabled={!lifecycleUserId || lifecycleMutation.isPending || ((lifecycleAction === "reinstate" || lifecycleAction === "reemploy") && !lifecycleFrom)} onClick={() => lifecycleMutation.mutate()}><UserCheck size={16} />Apply lifecycle action</button>
            </div>
          </section>
        ) : null}
      </main>
    </DepartmentLayout>
  );
}
