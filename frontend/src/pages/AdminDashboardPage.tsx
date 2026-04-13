import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { RealtimeContext } from "../components/realtime/realtimeContext";
import { getCachedUser, getContext } from "../services/auth";
import {
  LS_ACTIVE_AMO_ID,
  applyAdminUserEmploymentAction,
  bulkAdminUserAction,
  createAdminAuthorisationType,
  createAdminGroup,
  deleteAdminAuthorisationType,
  deleteAdminGroup,
  downloadAdminUsersExport,
  enableAdminUser,
  disableAdminUser,
  getAdminUserDirectory,
  listAdminAuthorisationTypes,
  listAdminDepartments,
  listAdminGroups,
  updateAdminUser,
} from "../services/adminUsers";
import type {
  AccountRole,
  AdminAuthorisationTypeCreatePayload,
  AdminDepartmentRead,
  AdminUserDirectoryItem,
  AdminUserDirectoryMetrics,
  AdminUserGroupRead,
  BulkUserActionPayload,
  UserEmploymentActionPayload,
} from "../services/adminUsers";
import "../styles/admin-user-management.css";

type UrlParams = { amoCode?: string };
type UserTab = "users" | "groups" | "permissions" | "hr";
type PresenceFilter = "all" | "online" | "away" | "offline" | "inactive" | "leave";
type BulkToolbarAction = BulkUserActionPayload["action"] | "export_csv" | "export_json" | "";

const ZERO_METRICS: AdminUserDirectoryMetrics = {
  total_users: 0,
  active_users: 0,
  inactive_users: 0,
  online_users: 0,
  away_users: 0,
  on_leave_users: 0,
  recently_active_users: 0,
  departmentless_users: 0,
  managers: 0,
};

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

const formatRelative = (value?: string | null) => {
  if (!value) return "Never seen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Never seen";
  const deltaMs = Date.now() - date.getTime();
  if (deltaMs < 60_000) return "Just now";
  const mins = Math.floor(deltaMs / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

const statusTone = (user: AdminUserDirectoryItem) => {
  if (user.presence_display.status_label === "Inactive") return "is-inactive";
  if (user.availability_status === "ON_LEAVE" || user.presence_display.status_label === "On leave") return "is-leave";
  if (user.presence.state === "away") return "is-away";
  return user.presence.is_online ? "is-online" : "is-offline";
};

const buildDownload = ({ blob, filename }: { blob: Blob; filename: string }) => {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

const metricCard = (label: string, value: number) => (
  <article className="aum-metric-card" key={label}>
    <span>{label}</span>
    <strong>{value}</strong>
  </article>
);

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
    ? localStorage.getItem(LS_ACTIVE_AMO_ID) || currentUser?.amo_id || null
    : currentUser?.amo_id || null;

  const [activeTab, setActiveTab] = useState<UserTab>("users");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<PresenceFilter>("all");
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
  const [bulkDepartmentId, setBulkDepartmentId] = useState("");
  const [bulkRole, setBulkRole] = useState<AccountRole | "">("");
  const [bulkGroupId, setBulkGroupId] = useState("");
  const [bulkNote, setBulkNote] = useState("");
  const [bulkEffectiveFrom, setBulkEffectiveFrom] = useState("");
  const [bulkEffectiveTo, setBulkEffectiveTo] = useState("");
  const [bulkAction, setBulkAction] = useState<BulkToolbarAction>("");
  const [selectedLifecycleUserId, setSelectedLifecycleUserId] = useState("");
  const [lifecycleAction, setLifecycleAction] = useState<UserEmploymentActionPayload["action"]>("transfer");
  const [lifecycleRole, setLifecycleRole] = useState<AccountRole | "">("");
  const [lifecycleDepartmentId, setLifecycleDepartmentId] = useState("");
  const [lifecycleTitle, setLifecycleTitle] = useState("");
  const [lifecycleStatus, setLifecycleStatus] = useState("");
  const [lifecycleNote, setLifecycleNote] = useState("");
  const [lifecycleEffectiveFrom, setLifecycleEffectiveFrom] = useState("");
  const [lifecycleEffectiveTo, setLifecycleEffectiveTo] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupCode, setNewGroupCode] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [permissionForm, setPermissionForm] = useState<AdminAuthorisationTypeCreatePayload>({
    amo_id: effectiveAmoId || "",
    code: "",
    name: "",
    description: "",
    maintenance_scope: "LINE",
    regulation_reference: "",
    can_issue_crs: false,
    requires_dual_sign: false,
    requires_valid_licence: false,
  });
  const [feedback, setFeedback] = useState<string>("");

  useEffect(() => {
    setPermissionForm((current) => ({ ...current, amo_id: effectiveAmoId || current.amo_id || "" }));
  }, [effectiveAmoId]);

  const directoryQuery = useQuery({
    queryKey: ["admin-user-directory", effectiveAmoId, search],
    queryFn: () => getAdminUserDirectory({ amo_id: effectiveAmoId, search, limit: 250 }),
    enabled: canAccessAdmin && !!effectiveAmoId,
  });

  const departmentsQuery = useQuery({
    queryKey: ["admin-user-departments", effectiveAmoId],
    queryFn: () => listAdminDepartments(effectiveAmoId || undefined),
    enabled: canAccessAdmin && !!effectiveAmoId,
  });

  const groupsQuery = useQuery({
    queryKey: ["admin-user-groups", effectiveAmoId],
    queryFn: () => listAdminGroups(effectiveAmoId || undefined),
    enabled: canAccessAdmin && !!effectiveAmoId,
  });

  const permissionsQuery = useQuery({
    queryKey: ["admin-user-authorisation-types", effectiveAmoId],
    queryFn: () => listAdminAuthorisationTypes(effectiveAmoId || undefined),
    enabled: canAccessAdmin && !!effectiveAmoId,
  });

  const items = directoryQuery.data?.items ?? [];
  const metrics = directoryQuery.data?.metrics ?? ZERO_METRICS;
  const departments = departmentsQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const permissionTypes = permissionsQuery.data ?? [];

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesRole = roleFilter === "all" || item.role === roleFilter;
      const matchesStatus =
        statusFilter === "all"
          ? true
          : statusFilter === "inactive"
            ? !item.is_active
            : statusFilter === "leave"
              ? item.availability_status === "ON_LEAVE" || item.presence_display.status_label === "On leave"
              : statusFilter === "away"
                ? item.presence.state === "away"
                : item.presence_display.status_label.toLowerCase() === statusFilter;
      return matchesRole && matchesStatus;
    });
  }, [items, roleFilter, statusFilter]);

  const selectedUsers = useMemo(
    () => items.filter((item) => selectedUserIds.includes(item.id)),
    [items, selectedUserIds],
  );

  const allVisibleSelected = filteredItems.length > 0 && filteredItems.every((item) => selectedUserIds.includes(item.id));
  const hasActiveFilters = !!search.trim() || roleFilter !== "all" || statusFilter !== "all";
  const batchMode = selectedUserIds.length > 0;
  const bulkActionNeedsDepartment = bulkAction === "assign_department";
  const bulkActionNeedsRole = bulkAction === "change_role";
  const bulkActionNeedsGroup = bulkAction === "add_group" || bulkAction === "remove_group";
  const bulkActionNeedsDates = bulkAction === "schedule_leave";
  const bulkActionNeedsNote = [
    "assign_department",
    "change_role",
    "add_group",
    "remove_group",
    "disable",
    "delete",
    "schedule_leave",
    "return_from_leave",
  ].includes(bulkAction);
  const bulkApplyLabel =
    bulkAction === "export_csv"
      ? "Download CSV"
      : bulkAction === "export_json"
        ? "Download JSON"
        : "Apply";

  const resetBulkFields = () => {
    setBulkAction("");
    setBulkDepartmentId("");
    setBulkRole("");
    setBulkGroupId("");
    setBulkNote("");
    setBulkEffectiveFrom("");
    setBulkEffectiveTo("");
  };

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-groups"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-authorisation-types"] }),
    ]);
  };

  const bulkMutation = useMutation({
    mutationFn: (payload: BulkUserActionPayload) => bulkAdminUserAction(payload),
    onSuccess: async (result) => {
      setFeedback(result.detail);
      if (result.action === "delete") {
        setSelectedUserIds([]);
      }
      resetBulkFields();
      await refreshAll();
    },
  });

  const lifecycleMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: UserEmploymentActionPayload }) =>
      applyAdminUserEmploymentAction(userId, payload),
    onSuccess: async (result) => {
      setFeedback(`Lifecycle action ${result.action} applied.`);
      await refreshAll();
    },
  });

  const toggleUserMutation = useMutation({
    mutationFn: async (user: AdminUserDirectoryItem) => {
      if (user.is_active) return disableAdminUser(user.id);
      return enableAdminUser(user.id);
    },
    onSuccess: async () => {
      await refreshAll();
    },
  });

  const quickDepartmentMutation = useMutation({
    mutationFn: ({ userId, departmentId }: { userId: string; departmentId: string | null }) =>
      updateAdminUser(userId, { department_id: departmentId }),
    onSuccess: async () => {
      setFeedback("Department updated.");
      await refreshAll();
    },
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
      setFeedback("Group created.");
      setNewGroupName("");
      setNewGroupCode("");
      setNewGroupDescription("");
      await refreshAll();
    },
  });

  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => deleteAdminGroup(groupId),
    onSuccess: async () => {
      setFeedback("Group deleted.");
      await refreshAll();
    },
  });

  const createPermissionTypeMutation = useMutation({
    mutationFn: () => createAdminAuthorisationType(permissionForm),
    onSuccess: async () => {
      setFeedback("Permission type created.");
      setPermissionForm({
        amo_id: effectiveAmoId || "",
        code: "",
        name: "",
        description: "",
        maintenance_scope: "LINE",
        regulation_reference: "",
        can_issue_crs: false,
        requires_dual_sign: false,
        requires_valid_licence: false,
      });
      await refreshAll();
    },
  });

  const deletePermissionTypeMutation = useMutation({
    mutationFn: (permissionTypeId: string) => deleteAdminAuthorisationType(permissionTypeId),
    onSuccess: async () => {
      setFeedback("Permission type deleted.");
      await refreshAll();
    },
  });

  const exportMutation = useMutation({
    mutationFn: ({ userIds, format }: { userIds: string[]; format: "json" | "csv" }) =>
      downloadAdminUsersExport(userIds, format),
    onSuccess: (result) => {
      buildDownload(result);
      setFeedback(`Export ready: ${result.filename}`);
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
          <section className="aum-panel"><div className="aum-empty">Loading user management workspace…</div></section>
        </div>
      </DepartmentLayout>
    );
  }

  if (!canAccessAdmin) {
    return (
      <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
        <div className="admin-users-workspace aum-shell">
          <section className="aum-panel"><div className="aum-empty">You do not have permission to access User Management.</div></section>
        </div>
      </DepartmentLayout>
    );
  }

  const handleToggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelectedUserIds((current) => current.filter((id) => !filteredItems.some((item) => item.id === id)));
      return;
    }
    setSelectedUserIds((current) => Array.from(new Set([...current, ...filteredItems.map((item) => item.id)])));
  };

  const submitBulkAction = (action: BulkUserActionPayload["action"]) => {
    if (!selectedUserIds.length) {
      setFeedback("Select at least one user first.");
      return;
    }
    if (action === "delete" && !window.confirm(`Permanently delete ${selectedUserIds.length} selected user(s)? This cannot be undone.`)) {
      return;
    }
    bulkMutation.mutate({
      user_ids: selectedUserIds,
      action,
      department_id: bulkDepartmentId || undefined,
      role: bulkRole || undefined,
      group_id: bulkGroupId || undefined,
      note: bulkNote || undefined,
      effective_from: bulkEffectiveFrom || undefined,
      effective_to: bulkEffectiveTo || undefined,
    });
  };

  const submitLifecycle = () => {
    if (!selectedLifecycleUserId) {
      setFeedback("Select a user for the lifecycle action.");
      return;
    }
    lifecycleMutation.mutate({
      userId: selectedLifecycleUserId,
      payload: {
        action: lifecycleAction,
        role: lifecycleRole || undefined,
        department_id: lifecycleDepartmentId || undefined,
        position_title: lifecycleTitle || undefined,
        note: lifecycleNote || undefined,
        employment_status: lifecycleStatus || undefined,
        effective_from: lifecycleEffectiveFrom || undefined,
        effective_to: lifecycleEffectiveTo || undefined,
      },
    });
  };

  const applyBulkToolbarAction = () => {
    if (!selectedUserIds.length) {
      setFeedback("Select at least one user first.");
      return;
    }
    if (!bulkAction) {
      setFeedback("Choose a batch action.");
      return;
    }
    if (bulkAction === "export_csv" || bulkAction === "export_json") {
      exportMutation.mutate({
        userIds: selectedUserIds,
        format: bulkAction === "export_csv" ? "csv" : "json",
      });
      return;
    }
    if (bulkActionNeedsDepartment && !bulkDepartmentId) {
      setFeedback("Choose the target department first.");
      return;
    }
    if (bulkActionNeedsRole && !bulkRole) {
      setFeedback("Choose the target role first.");
      return;
    }
    if (bulkActionNeedsGroup && !bulkGroupId) {
      setFeedback("Choose the target group first.");
      return;
    }
    submitBulkAction(bulkAction);
  };

  const runRowAction = (
    user: AdminUserDirectoryItem,
    action: "toggle_access" | "schedule_leave" | "return_from_leave" | "export_csv" | "export_json" | "delete",
  ) => {
    if (action === "toggle_access") {
      toggleUserMutation.mutate(user);
      return;
    }
    if (action === "export_csv" || action === "export_json") {
      exportMutation.mutate({
        userIds: [user.id],
        format: action === "export_csv" ? "csv" : "json",
      });
      return;
    }
    if (action === "delete") {
      if (!window.confirm(`Permanently delete ${user.full_name}? This cannot be undone.`)) {
        return;
      }
      bulkMutation.mutate({
        user_ids: [user.id],
        action: "delete",
        note: `Hard deleted from row menu by admin`,
      });
      return;
    }
    bulkMutation.mutate({
      user_ids: [user.id],
      action,
      effective_from: action === "schedule_leave" ? new Date().toISOString() : undefined,
      note: action === "schedule_leave" ? "Leave started from row menu" : "Returned from leave from row menu",
    });
  };

  const handleRowMenuAction = (
    event: React.MouseEvent<HTMLButtonElement>,
    user: AdminUserDirectoryItem,
    action: "toggle_access" | "schedule_leave" | "return_from_leave" | "export_csv" | "export_json" | "delete",
  ) => {
    const details = event.currentTarget.closest("details");
    if (details instanceof HTMLDetailsElement) {
      details.open = false;
    }
    runRowAction(user, action);
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
      <div className="admin-users-workspace aum-shell">
        <header className="aum-header aum-brand-hero">
          <div>
            <p className="aum-eyebrow">User Management</p>
            <h1>User management</h1>
            <p className="aum-subtitle">
              Full front-end admin workspace for departments, roles, permissions, bulk actions, lifecycle control, and audit-ready exports.
            </p>
          </div>
          <div className="aum-header-actions">
            <span className={`aum-live ${realtimeStatus === "live" ? "is-live" : ""}`}>{realtimeStatus}</span>
            <button type="button" className="aum-button aum-button--secondary" onClick={() => refreshAll()}>
              Refresh
            </button>
            <button type="button" className="aum-button aum-button--primary" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/new`)}>
              Add user
            </button>
          </div>
        </header>

        {feedback ? <section className="aum-inline-banner">{feedback}</section> : null}

        <section className="aum-metrics-grid">
          {metricCard("Total users", metrics.total_users)}
          {metricCard("Active", metrics.active_users)}
          {metricCard("Online now", metrics.online_users)}
          {metricCard("Away", metrics.away_users)}
          {metricCard("On leave", metrics.on_leave_users)}
          {metricCard("Recently active (10m)", metrics.recently_active_users)}
          {metricCard("Inactive", metrics.inactive_users)}
          {metricCard("Managers", metrics.managers)}
          {metricCard("Unassigned department", metrics.departmentless_users)}
        </section>

        <div className="aum-tabs" role="tablist" aria-label="User management sections">
          {([
            ["users", "Users"],
            ["groups", "Groups & policying"],
            ["permissions", "Roles & permissions"],
            ["hr", "Lifecycle & compliance"],
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

        {activeTab === "users" ? (
          <section className="aum-panel">
            <div className="aum-panel-header">
              <div>
                <h2>User directory</h2>
                <p>Compact operational table for departments, access control, audit exports, and staff lifecycle administration.</p>
              </div>
            </div>

            <div className="aum-directory-toolbar">
              <div className="aum-directory-toolbar__filters">
                <input
                  className="aum-input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search name, email, staff code, or title"
                />
                <select className="aum-select" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                  <option value="all">All roles</option>
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>{formatRole(role)}</option>
                  ))}
                </select>
                <select className="aum-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as PresenceFilter)}>
                  <option value="all">All statuses</option>
                  <option value="online">Online</option>
                  <option value="away">Away</option>
                  <option value="leave">On leave</option>
                  <option value="offline">Offline</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
              <div className="aum-directory-toolbar__meta">
                <span className="aum-record-count">{filteredItems.length} shown</span>
                {hasActiveFilters ? (
                  <button
                    type="button"
                    className="aum-button aum-button--ghost"
                    onClick={() => {
                      setSearch("");
                      setRoleFilter("all");
                      setStatusFilter("all");
                    }}
                  >
                    Clear filters
                  </button>
                ) : null}
              </div>
            </div>

            {batchMode ? (
              <div className="aum-batch-bar" role="region" aria-label="Batch actions">
                <div className="aum-batch-bar__summary">
                  <strong>{selectedUserIds.length} selected</strong>
                  <span>Batch actions apply to the current checked rows.</span>
                </div>
                <div className="aum-batch-bar__controls">
                  <label className="aum-field aum-field--compact">
                    <span>Batch action</span>
                    <select className="aum-select" value={bulkAction} onChange={(event) => setBulkAction(event.target.value as BulkToolbarAction)}>
                      <option value="">Choose action</option>
                      <option value="assign_department">Assign department</option>
                      <option value="clear_department">Clear department</option>
                      <option value="change_role">Change role</option>
                      <option value="add_group">Add to group</option>
                      <option value="remove_group">Remove from group</option>
                      <option value="enable">Enable account</option>
                      <option value="disable">Disable account</option>
                      <option value="schedule_leave">Schedule leave</option>
                      <option value="return_from_leave">Return from leave</option>
                      <option value="export_csv">Export CSV</option>
                      <option value="export_json">Export JSON</option>
                      <option value="delete">Hard delete</option>
                    </select>
                  </label>

                  {bulkActionNeedsDepartment ? (
                    <label className="aum-field aum-field--compact">
                      <span>Department</span>
                      <select className="aum-select" value={bulkDepartmentId} onChange={(event) => setBulkDepartmentId(event.target.value)}>
                        <option value="">Choose department</option>
                        {departments.map((department: AdminDepartmentRead) => (
                          <option key={department.id} value={department.id}>{department.name}</option>
                        ))}
                      </select>
                    </label>
                  ) : null}

                  {bulkActionNeedsRole ? (
                    <label className="aum-field aum-field--compact">
                      <span>Role</span>
                      <select className="aum-select" value={bulkRole} onChange={(event) => setBulkRole(event.target.value as AccountRole | "") }>
                        <option value="">Choose role</option>
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>{formatRole(role)}</option>
                        ))}
                      </select>
                    </label>
                  ) : null}

                  {bulkActionNeedsGroup ? (
                    <label className="aum-field aum-field--compact">
                      <span>Group</span>
                      <select className="aum-select" value={bulkGroupId} onChange={(event) => setBulkGroupId(event.target.value)}>
                        <option value="">Choose group</option>
                        {groups.map((group: AdminUserGroupRead) => (
                          <option key={group.id} value={group.id}>{group.name}</option>
                        ))}
                      </select>
                    </label>
                  ) : null}

                  {bulkActionNeedsDates ? (
                    <>
                      <label className="aum-field aum-field--compact">
                        <span>Leave from</span>
                        <input className="aum-input" type="datetime-local" value={bulkEffectiveFrom} onChange={(event) => setBulkEffectiveFrom(event.target.value)} />
                      </label>
                      <label className="aum-field aum-field--compact">
                        <span>Leave to</span>
                        <input className="aum-input" type="datetime-local" value={bulkEffectiveTo} onChange={(event) => setBulkEffectiveTo(event.target.value)} />
                      </label>
                    </>
                  ) : null}

                  {bulkActionNeedsNote ? (
                    <label className="aum-field aum-field--compact aum-field--wide">
                      <span>Reason / note</span>
                      <input className="aum-input" value={bulkNote} onChange={(event) => setBulkNote(event.target.value)} placeholder="Optional audit note" />
                    </label>
                  ) : null}

                  <div className="aum-batch-bar__actions">
                    <button
                      type="button"
                      className={`aum-button ${bulkAction === "delete" ? "aum-button--danger" : "aum-button--primary"}`}
                      disabled={bulkMutation.isPending || exportMutation.isPending || !bulkAction}
                      onClick={applyBulkToolbarAction}
                    >
                      {bulkApplyLabel}
                    </button>
                    <button type="button" className="aum-button aum-button--ghost" onClick={() => setSelectedUserIds([])}>
                      Clear selection
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="aum-selection-hint">Select one or more rows to reveal batch actions.</div>
            )}

            {directoryQuery.isLoading ? (
              <div className="aum-empty">Loading users…</div>
            ) : directoryQuery.error ? (
              <div className="aum-empty">Unable to load users right now. {(directoryQuery.error as Error).message}</div>
            ) : (
              <div className="aum-table-wrap">
                <table className="aum-table">
                  <thead>
                    <tr>
                      <th className="aum-checkbox-col"><input type="checkbox" checked={allVisibleSelected} onChange={handleToggleSelectAll} /></th>
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
                      <tr><td colSpan={9} className="aum-empty-row">No users match the current filter.</td></tr>
                    ) : (
                      filteredItems.map((user) => {
                        const checked = selectedUserIds.includes(user.id);
                        const primaryLastSeen = user.presence_display.status_label === "Online"
                          ? "Active now"
                          : user.presence_display.status_label === "On leave"
                            ? "Leave scheduled"
                            : formatRelative(user.presence_display.last_seen_at || user.last_login_at);
                        const displayRole = user.position_title?.trim() || formatRole(user.role);
                        const secondaryRole = user.position_title?.trim()
                          ? formatRole(user.role)
                          : user.display_title && user.display_title !== formatRole(user.role)
                            ? user.display_title
                            : null;
                        return (
                          <tr key={user.id} className={checked ? "is-selected" : ""}>
                            <td className="aum-checkbox-col">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => setSelectedUserIds((current) => checked ? current.filter((id) => id !== user.id) : [...current, user.id])}
                              />
                            </td>
                            <td>
                              <button type="button" className="aum-link" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/${user.id}`)}>
                                {user.full_name}
                              </button>
                              <div className="aum-muted">{user.email}</div>
                            </td>
                            <td>{user.staff_code}</td>
                            <td>
                              <div className="aum-role-primary">{displayRole}</div>
                              {secondaryRole ? <div className="aum-muted">{secondaryRole}</div> : null}
                            </td>
                            <td>
                              <select
                                className="aum-select aum-inline-select"
                                value={user.department_id || ""}
                                onChange={(event) => quickDepartmentMutation.mutate({ userId: user.id, departmentId: event.target.value || null })}
                              >
                                <option value="">Unassigned</option>
                                {departments.map((department: AdminDepartmentRead) => (
                                  <option key={department.id} value={department.id}>{department.name}</option>
                                ))}
                              </select>
                            </td>
                            <td>{user.is_active ? "Enabled" : "Disabled"}</td>
                            <td>
                              <span className={`aum-status ${statusTone(user)}`}>{user.presence_display.status_label}</span>
                            </td>
                            <td>
                              <div>{primaryLastSeen}</div>
                              <div className="aum-muted">{formatDateTime(user.presence_display.last_seen_at || user.last_login_at)}</div>
                            </td>
                            <td>
                              <div className="aum-row-actions aum-row-actions--compact">
                                <button type="button" className="aum-button aum-button--ghost" onClick={() => navigate(`/maintenance/${amoCode}/admin/users/${user.id}`)}>
                                  View
                                </button>
                                <details className="aum-overflow">
                                  <summary>More</summary>
                                  <div className="aum-overflow-menu">
                                    <button type="button" onClick={(event) => handleRowMenuAction(event, user, "toggle_access")}>
                                      {user.is_active ? "Disable account" : "Enable account"}
                                    </button>
                                    {user.availability_status === "ON_LEAVE" ? (
                                      <button type="button" onClick={(event) => handleRowMenuAction(event, user, "return_from_leave")}>
                                        Return from leave
                                      </button>
                                    ) : (
                                      <button type="button" onClick={(event) => handleRowMenuAction(event, user, "schedule_leave")}>
                                        Set on leave now
                                      </button>
                                    )}
                                    <button type="button" onClick={(event) => handleRowMenuAction(event, user, "export_csv")}>
                                      Export CSV
                                    </button>
                                    <button type="button" onClick={(event) => handleRowMenuAction(event, user, "export_json")}>
                                      Export JSON
                                    </button>
                                    <button type="button" className="is-danger" onClick={(event) => handleRowMenuAction(event, user, "delete")}>
                                      Hard delete
                                    </button>
                                  </div>
                                </details>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : null}

        {activeTab === "groups" ? (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Custom groups</h2>
                  <p>Create operational cohorts for promotions, departmental controls, task squads, or audit collections.</p>
                </div>
              </div>
              <div className="aum-stack">
                <label className="aum-field">
                  <span>Group name</span>
                  <input className="aum-input" value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} />
                </label>
                <label className="aum-field">
                  <span>Group code</span>
                  <input className="aum-input" value={newGroupCode} onChange={(event) => setNewGroupCode(event.target.value)} placeholder="Optional. Auto-generated if blank." />
                </label>
                <label className="aum-field">
                  <span>Description</span>
                  <textarea className="aum-textarea" value={newGroupDescription} onChange={(event) => setNewGroupDescription(event.target.value)} rows={3} />
                </label>
                <button type="button" className="aum-button aum-button--primary" disabled={!newGroupName.trim() || createGroupMutation.isPending} onClick={() => createGroupMutation.mutate()}>
                  Create group
                </button>
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Active groups</h2>
                  <p>Use the bulk toolbar in the Users tab to add or remove selected staff from any group.</p>
                </div>
              </div>
              <div className="aum-list-grid">
                {groups.length === 0 ? (
                  <div className="aum-empty">No groups available yet.</div>
                ) : (
                  groups.map((group: AdminUserGroupRead) => (
                    <div key={group.id} className="aum-list-card">
                      <strong>{group.name}</strong>
                      <span>{group.member_count} members</span>
                      <div className="aum-muted">{group.code} · {group.group_type}</div>
                      <div className="aum-row-actions wrap top-gap">
                        <button type="button" className="aum-button aum-button--ghost" onClick={() => setBulkGroupId(group.id)}>
                          Stage for bulk assignment
                        </button>
                        {!group.is_system_managed ? (
                          <button
                            type="button"
                            className="aum-button aum-button--danger"
                            onClick={() => {
                              if (window.confirm(`Delete group ${group.name}?`)) {
                                deleteGroupMutation.mutate(group.id);
                              }
                            }}
                          >
                            Delete
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </article>
          </section>
        ) : null}

        {activeTab === "permissions" ? (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Permission library</h2>
                  <p>Create the permission types that can later be granted to individual users.</p>
                </div>
              </div>
              <div className="aum-stack">
                <label className="aum-field"><span>Code</span><input className="aum-input" value={permissionForm.code} onChange={(event) => setPermissionForm((current) => ({ ...current, code: event.target.value }))} /></label>
                <label className="aum-field"><span>Name</span><input className="aum-input" value={permissionForm.name} onChange={(event) => setPermissionForm((current) => ({ ...current, name: event.target.value }))} /></label>
                <label className="aum-field"><span>Description</span><textarea className="aum-textarea" rows={3} value={permissionForm.description || ""} onChange={(event) => setPermissionForm((current) => ({ ...current, description: event.target.value }))} /></label>
                <label className="aum-field"><span>Maintenance scope</span><select className="aum-select" value={permissionForm.maintenance_scope || "LINE"} onChange={(event) => setPermissionForm((current) => ({ ...current, maintenance_scope: event.target.value }))}><option value="LINE">LINE</option><option value="BASE">BASE</option><option value="COMPONENT">COMPONENT</option><option value="STRUCTURES">STRUCTURES</option><option value="AVIONICS">AVIONICS</option><option value="POWERPLANT">POWERPLANT</option><option value="OTHER">OTHER</option></select></label>
                <label className="aum-field"><span>Regulation reference</span><input className="aum-input" value={permissionForm.regulation_reference || ""} onChange={(event) => setPermissionForm((current) => ({ ...current, regulation_reference: event.target.value }))} /></label>
                <label className="aum-check"><input type="checkbox" checked={!!permissionForm.can_issue_crs} onChange={(event) => setPermissionForm((current) => ({ ...current, can_issue_crs: event.target.checked }))} /><span>Can issue CRS</span></label>
                <label className="aum-check"><input type="checkbox" checked={!!permissionForm.requires_dual_sign} onChange={(event) => setPermissionForm((current) => ({ ...current, requires_dual_sign: event.target.checked }))} /><span>Requires dual sign</span></label>
                <label className="aum-check"><input type="checkbox" checked={!!permissionForm.requires_valid_licence} onChange={(event) => setPermissionForm((current) => ({ ...current, requires_valid_licence: event.target.checked }))} /><span>Requires valid licence</span></label>
                <button type="button" className="aum-button aum-button--primary" disabled={!permissionForm.code.trim() || !permissionForm.name.trim() || createPermissionTypeMutation.isPending} onClick={() => createPermissionTypeMutation.mutate()}>
                  Create permission type
                </button>
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Available permission types</h2>
                  <p>Grant these from the user detail page.</p>
                </div>
              </div>
              <div className="aum-list-grid">
                {permissionTypes.length === 0 ? (
                  <div className="aum-empty">No permission types defined yet.</div>
                ) : (
                  permissionTypes.map((item) => (
                    <div key={item.id} className="aum-list-card">
                      <strong>{item.code}</strong>
                      <span>{item.name}</span>
                      <div className="aum-muted">{item.maintenance_scope || "—"} · {item.regulation_reference || "No regulation reference"}</div>
                      <div className="aum-chip-row top-gap">
                        {item.can_issue_crs ? <span className="aum-chip">CRS</span> : null}
                        {item.requires_dual_sign ? <span className="aum-chip">Dual sign</span> : null}
                        {item.requires_valid_licence ? <span className="aum-chip">Valid licence</span> : null}
                      </div>
                      <div className="aum-row-actions wrap top-gap">
                        <button
                          type="button"
                          className="aum-button aum-button--danger"
                          onClick={() => {
                            if (window.confirm(`Delete permission type ${item.code}?`)) {
                              deletePermissionTypeMutation.mutate(item.id);
                            }
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </article>
          </section>
        ) : null}

        {activeTab === "hr" ? (
          <section className="aum-two-col">
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Lifecycle actions</h2>
                  <p>Promotions, demotions, transfers, new hires, resignations, reinstatements, and leave control.</p>
                </div>
              </div>
              <div className="aum-stack">
                <label className="aum-field">
                  <span>User</span>
                  <select className="aum-select" value={selectedLifecycleUserId} onChange={(event) => setSelectedLifecycleUserId(event.target.value)}>
                    <option value="">Select user</option>
                    {items.map((item) => (
                      <option key={item.id} value={item.id}>{item.full_name} · {item.staff_code}</option>
                    ))}
                  </select>
                </label>
                <label className="aum-field">
                  <span>Action</span>
                  <select className="aum-select" value={lifecycleAction} onChange={(event) => setLifecycleAction(event.target.value as UserEmploymentActionPayload["action"])}>
                    <option value="new_hire">New hire</option>
                    <option value="promote">Promote</option>
                    <option value="demote">Demote</option>
                    <option value="transfer">Transfer</option>
                    <option value="resign">Resign</option>
                    <option value="reinstate">Reinstate</option>
                    <option value="schedule_leave">Schedule leave</option>
                    <option value="return_from_leave">Return from leave</option>
                  </select>
                </label>
                <label className="aum-field">
                  <span>Role</span>
                  <select className="aum-select" value={lifecycleRole} onChange={(event) => setLifecycleRole(event.target.value as AccountRole | "") }>
                    <option value="">No role change</option>
                    {ROLE_OPTIONS.map((role) => <option key={role} value={role}>{formatRole(role)}</option>)}
                  </select>
                </label>
                <label className="aum-field">
                  <span>Department</span>
                  <select className="aum-select" value={lifecycleDepartmentId} onChange={(event) => setLifecycleDepartmentId(event.target.value)}>
                    <option value="">No department change</option>
                    {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select>
                </label>
                <label className="aum-field"><span>Position title</span><input className="aum-input" value={lifecycleTitle} onChange={(event) => setLifecycleTitle(event.target.value)} /></label>
                <label className="aum-field"><span>Employment status text</span><input className="aum-input" value={lifecycleStatus} onChange={(event) => setLifecycleStatus(event.target.value)} placeholder="Active, Resigned, Suspended…" /></label>
                <label className="aum-field"><span>Note</span><textarea className="aum-textarea" rows={3} value={lifecycleNote} onChange={(event) => setLifecycleNote(event.target.value)} /></label>
                <label className="aum-field"><span>Effective from</span><input className="aum-input" type="datetime-local" value={lifecycleEffectiveFrom} onChange={(event) => setLifecycleEffectiveFrom(event.target.value)} /></label>
                <label className="aum-field"><span>Effective to</span><input className="aum-input" type="datetime-local" value={lifecycleEffectiveTo} onChange={(event) => setLifecycleEffectiveTo(event.target.value)} /></label>
                <button type="button" className="aum-button aum-button--primary" disabled={lifecycleMutation.isPending} onClick={submitLifecycle}>Apply action</button>
              </div>
            </article>
            <article className="aum-panel">
              <div className="aum-panel-header">
                <div>
                  <h2>Compliance export shortcuts</h2>
                  <p>Use current selection from the Users tab for audit evidence packs.</p>
                </div>
              </div>
              <div className="aum-list-grid">
                <div className="aum-list-card">
                  <strong>Selected user records</strong>
                  <span>{selectedUsers.length} ready</span>
                  <div className="aum-row-actions wrap top-gap">
                    <button type="button" className="aum-button aum-button--ghost" disabled={!selectedUsers.length || exportMutation.isPending} onClick={() => exportMutation.mutate({ userIds: selectedUsers.map((item) => item.id), format: "csv" })}>Download CSV</button>
                    <button type="button" className="aum-button aum-button--ghost" disabled={!selectedUsers.length || exportMutation.isPending} onClick={() => exportMutation.mutate({ userIds: selectedUsers.map((item) => item.id), format: "json" })}>Download JSON</button>
                  </div>
                </div>
                <div className="aum-list-card">
                  <strong>Users on leave</strong>
                  <span>{items.filter((item) => item.availability_status === "ON_LEAVE").length} currently flagged</span>
                </div>
                <div className="aum-list-card">
                  <strong>New-hire readiness</strong>
                  <span>{items.filter((item) => !item.last_login_at).length} never signed in</span>
                </div>
                <div className="aum-list-card">
                  <strong>Resignation / inactive controls</strong>
                  <span>{items.filter((item) => !item.is_active).length} disabled accounts</span>
                </div>
              </div>
            </article>
          </section>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default AdminDashboardPage;
