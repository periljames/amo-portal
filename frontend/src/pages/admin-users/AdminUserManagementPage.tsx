import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import {
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  CircleAlert,
  Eye,
  KeyRound,
  MapPin,
  Pencil,
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
import {
  LS_ACTIVE_AMO_ID,
  applyAdminUserEmploymentAction,
  bulkAdminUserAction,
  createAdminAuthorisationType,
  createAdminGroup,
  deleteAdminAuthorisationType,
  deleteAdminGroup,
  disableAdminUser,
  downloadAdminUsersExport,
  enableAdminUser,
  forceAdminUserPasswordReset,
  listAdminAuthorisationTypes,
  listAdminDepartments,
  listAdminGroups,
  listAdminUserSummaries,
  revokeAdminUserAccess,
  type AccountRole,
  type AdminAuthorisationTypeCreatePayload,
  type AdminUserDirectoryItem,
  type BulkUserActionPayload,
  type UserEmploymentActionPayload,
} from "../../services/adminUsers";
import {
  assignAdminDirectoryBases,
  assignAdminDirectoryDepartments,
  getAdminUserDirectoryPage,
  listAdminDirectoryBases,
  type AdminDirectoryBaseItem,
  type AdminUserAccountFilter,
  type AdminUserDirectoryPageItem,
  type AdminUserSortDirection,
  type AdminUserSortField,
} from "../../services/adminUserDirectory";
import "../../styles/admin-user-management-v2.css";

type UrlParams = { amoCode?: string };
type WorkspaceTab = "directory" | "groups" | "permissions" | "lifecycle";
type BatchAction =
  | BulkUserActionPayload["action"]
  | "assign_base"
  | "clear_base"
  | "export_csv"
  | "";

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

const PAGE_SIZES = [10, 25, 50, 100];

function formatRole(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatGroupType(value: string): string {
  return formatRole(value || "custom");
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

function presenceTone(
  user: AdminUserDirectoryItem,
): "online" | "away" | "offline" | "inactive" {
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

function PlacementCell({
  user,
  kind,
  departments,
  bases,
  editing,
  setEditing,
  onAssign,
  pending,
}: {
  user: AdminUserDirectoryPageItem;
  kind: "department" | "base";
  departments: Array<{ id: string; name: string; is_active: boolean }>;
  bases: AdminDirectoryBaseItem[];
  editing: boolean;
  setEditing: (editing: boolean) => void;
  onAssign: (value: string | null) => void;
  pending: boolean;
}) {
  const isDepartment = kind === "department";
  const value = isDepartment ? user.department_id : user.base_station_id;
  const label = isDepartment
    ? user.department_name || "Unassigned"
    : user.base_station_name || "Unassigned";
  const code = isDepartment ? null : user.base_station_code;
  const canEdit = user.is_active || Boolean(value);

  if (editing) {
    return (
      <div className="aum2-inline-editor">
        <select
          className="aum2-inline-select"
          value={value || ""}
          autoFocus
          disabled={pending}
          aria-label={`Set ${kind} for ${user.full_name}`}
          onChange={(event) => onAssign(event.target.value || null)}
        >
          <option value="">Unassigned</option>
          {user.is_active
            ? isDepartment
              ? departments
                  .filter((department) => department.is_active)
                  .map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))
              : bases.map((base) => (
                  <option key={base.id} value={base.id}>
                    {base.code} · {base.name}
                  </option>
                ))
            : null}
          {!user.is_active && value ? (
            <option value={value}>{code ? `${code} · ${label}` : label}</option>
          ) : null}
        </select>
        <IconButton label="Cancel editing" onClick={() => setEditing(false)} disabled={pending}>
          <X size={14} />
        </IconButton>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="aum2-placement-display"
      disabled={!canEdit || pending}
      onClick={() => setEditing(true)}
      title={
        user.is_active
          ? `Change ${kind}`
          : value
            ? `Inactive account: only clearing the ${kind} is allowed`
            : `Inactive accounts cannot receive a ${kind}`
      }
    >
      <span>
        <strong>{code || label}</strong>
        {code ? <small>{label}</small> : null}
        {!user.is_active ? <small>Inactive account</small> : null}
      </span>
      {canEdit ? <Pencil size={13} aria-hidden="true" /> : <ShieldOff size={13} aria-hidden="true" />}
    </button>
  );
}

export default function AdminUserManagementPage() {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ctx = getContext();
  const currentUser = useMemo(() => getCachedUser(), []);
  const [sessionActive, setSessionActive] = useState(() => Boolean(getToken()));
  const isSuperuser = Boolean(currentUser?.is_superuser);
  const canAccessAdmin = Boolean(
    sessionActive && currentUser && (currentUser.is_superuser || currentUser.is_amo_admin),
  );
  const effectiveAmoId = isSuperuser
    ? localStorage.getItem(LS_ACTIVE_AMO_ID) || currentUser?.amo_id || null
    : currentUser?.amo_id || null;
  const basePath = `/maintenance/${amoCode ?? ctx.amoCode ?? "UNKNOWN"}/admin/users`;

  const [tab, setTab] = useState<WorkspaceTab>("directory");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput.trim(), 300);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [roleFilter, setRoleFilter] = useState<AccountRole | "all">("all");
  const [accountFilter, setAccountFilter] = useState<AdminUserAccountFilter>("all");
  const [departmentFilter, setDepartmentFilter] = useState<"all" | "unassigned" | string>("all");
  const [baseFilter, setBaseFilter] = useState<"all" | "unassigned" | string>("all");
  const [sortBy, setSortBy] = useState<AdminUserSortField>("name");
  const [sortDirection, setSortDirection] = useState<AdminUserSortDirection>("asc");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState("");
  const [batchAction, setBatchAction] = useState<BatchAction>("");
  const [batchDepartmentId, setBatchDepartmentId] = useState("");
  const [batchBaseId, setBatchBaseId] = useState("");
  const [batchRole, setBatchRole] = useState<AccountRole | "">("");
  const [editingDepartmentUserId, setEditingDepartmentUserId] = useState<string | null>(null);
  const [editingBaseUserId, setEditingBaseUserId] = useState<string | null>(null);

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

  const [lifecycleSearch, setLifecycleSearch] = useState("");
  const debouncedLifecycleSearch = useDebouncedValue(lifecycleSearch.trim(), 300);
  const [lifecycleUserId, setLifecycleUserId] = useState("");
  const [lifecycleAction, setLifecycleAction] =
    useState<UserEmploymentActionPayload["action"]>("transfer");
  const [lifecycleRole, setLifecycleRole] = useState<AccountRole | "">("");
  const [lifecycleDepartmentId, setLifecycleDepartmentId] = useState("");
  const [lifecycleBaseId, setLifecycleBaseId] = useState("");
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
  }, [
    search,
    roleFilter,
    accountFilter,
    departmentFilter,
    baseFilter,
    pageSize,
    sortBy,
    sortDirection,
  ]);

  useEffect(() => {
    setSelectedIds([]);
    setEditingDepartmentUserId(null);
    setEditingBaseUserId(null);
  }, [page]);

  useEffect(() => {
    setPermissionForm((current) => ({ ...current, amo_id: effectiveAmoId || "" }));
  }, [effectiveAmoId]);

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
      roleFilter,
      accountFilter,
      departmentFilter,
      baseFilter,
      sortBy,
      sortDirection,
    ],
    queryFn: () =>
      getAdminUserDirectoryPage({
        amo_id: effectiveAmoId,
        page,
        page_size: pageSize,
        search,
        role: roleFilter,
        account_status: accountFilter,
        department_id: departmentFilter,
        base_station_id: baseFilter,
        sort_by: sortBy,
        sort_direction: sortDirection,
      }),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 8_000,
    refetchInterval: canAccessAdmin ? 15_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  const departmentsQuery = useQuery({
    queryKey: ["admin-user-departments", effectiveAmoId],
    queryFn: () => listAdminDepartments(effectiveAmoId || undefined),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 60_000,
  });
  const basesQuery = useQuery({
    queryKey: ["admin-user-directory-bases", effectiveAmoId],
    queryFn: () => listAdminDirectoryBases(effectiveAmoId),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 60_000,
  });
  const groupsQuery = useQuery({
    queryKey: ["admin-user-groups", effectiveAmoId],
    queryFn: () => listAdminGroups(effectiveAmoId),
    enabled: canAccessAdmin && Boolean(effectiveAmoId),
    staleTime: 30_000,
  });
  const permissionTypesQuery = useQuery({
    queryKey: ["admin-user-authorisation-types", effectiveAmoId],
    queryFn: () => listAdminAuthorisationTypes(effectiveAmoId),
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
  const assignableDepartments = departments.filter((department) => department.is_active);
  const bases = basesQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const permissionTypes = permissionTypesQuery.data ?? [];
  const lifecycleUsers = lifecycleUsersQuery.data ?? [];
  const lifecycleSelectedUser = lifecycleUsers.find((user) => user.id === lifecycleUserId);
  const lifecycleCanChangePlacement = Boolean(
    lifecycleSelectedUser?.is_active ||
      lifecycleAction === "new_hire" ||
      lifecycleAction === "reinstate",
  );
  const selectedUsers = items.filter((item) => selectedIds.includes(item.id));
  const selectedInactiveCount = selectedUsers.filter((item) => !item.is_active).length;
  const allPageSelected = items.length > 0 && items.every((item) => selectedIds.includes(item.id));
  const refreshDirectory = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
  };
  const refreshSupportingData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-user-groups"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-authorisation-types"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-departments"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-directory-bases"] }),
    ]);
  };

  const toggleUserMutation = useMutation({
    mutationFn: (user: AdminUserDirectoryPageItem) =>
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
  const departmentAssignmentMutation = useMutation({
    mutationFn: ({
      userIds,
      departmentId,
    }: {
      userIds: string[];
      departmentId: string | null;
    }) =>
      assignAdminDirectoryDepartments({
        user_ids: userIds,
        department_id: departmentId,
        amo_id: effectiveAmoId,
      }),
    onSuccess: async (result) => {
      setFeedback(result.detail);
      setEditingDepartmentUserId(null);
      setSelectedIds([]);
      setBatchAction("");
      await refreshDirectory();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const baseAssignmentMutation = useMutation({
    mutationFn: ({
      userIds,
      baseStationId,
    }: {
      userIds: string[];
      baseStationId: string | null;
    }) =>
      assignAdminDirectoryBases({
        user_ids: userIds,
        base_station_id: baseStationId,
        amo_id: effectiveAmoId,
        note: "Assigned from user management",
      }),
    onSuccess: async (result) => {
      setFeedback(result.detail);
      setEditingBaseUserId(null);
      setSelectedIds([]);
      setBatchAction("");
      await refreshDirectory();
    },
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
  const createPermissionMutation = useMutation({
    mutationFn: () => createAdminAuthorisationType(permissionForm),
    onSuccess: async () => {
      setPermissionForm((current) => ({
        ...current,
        code: "",
        name: "",
        description: "",
        regulation_reference: "",
      }));
      setFeedback("Permission type created.");
      await refreshSupportingData();
    },
    onError: (error: Error) => setFeedback(error.message),
  });
  const deletePermissionMutation = useMutation({
    mutationFn: (permissionId: string) => deleteAdminAuthorisationType(permissionId),
    onSuccess: refreshSupportingData,
    onError: (error: Error) => setFeedback(error.message),
  });
  const lifecycleMutation = useMutation({
    mutationFn: () =>
      applyAdminUserEmploymentAction(lifecycleUserId, {
        action: lifecycleAction,
        role: lifecycleRole || undefined,
        department_id:
          lifecycleCanChangePlacement && lifecycleDepartmentId
            ? lifecycleDepartmentId
            : undefined,
        position_title: lifecycleTitle.trim() || undefined,
        note: lifecycleNote.trim() || undefined,
        effective_from: lifecycleFrom || undefined,
        effective_to: lifecycleTo || undefined,
      }),
    onSuccess: async (result) => {
      let message = `Lifecycle action “${result.action}” completed.`;
      if (lifecycleBaseId && lifecycleCanChangePlacement) {
        try {
          const baseResult = await assignAdminDirectoryBases({
            user_ids: [lifecycleUserId],
            base_station_id: lifecycleBaseId,
            amo_id: effectiveAmoId,
            note: lifecycleNote.trim() || "Assigned during lifecycle update",
          });
          message = `${message} ${baseResult.detail}`;
        } catch (error) {
          message = `${message} Base assignment failed: ${
            error instanceof Error ? error.message : "Unknown error"
          }`;
        }
      }
      setFeedback(message);
      await refreshDirectory();
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  if (!currentUser || !canAccessAdmin) {
    return (
      <DepartmentLayout
        amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"}
        activeDepartment="admin-users"
      >
        <div className="aum2-shell">
          <div className="aum2-empty">Loading user management…</div>
        </div>
      </DepartmentLayout>
    );
  }

  const executeBatch = () => {
    if (!selectedIds.length || !batchAction) return;

    const assigningPlacement =
      batchAction === "assign_department" || batchAction === "assign_base";
    if (assigningPlacement && selectedInactiveCount > 0) {
      setFeedback(
        `${selectedInactiveCount} selected inactive account(s) cannot receive a new ${
          batchAction === "assign_department" ? "department" : "base"
        }. Enable them first or remove them from the selection.`,
      );
      return;
    }

    if (batchAction === "export_csv") {
      exportMutation.mutate({ userIds: selectedIds, format: "csv" });
      return;
    }
    if (
      batchAction === "delete" &&
      !window.confirm(`Permanently delete ${selectedIds.length} selected users?`)
    ) {
      return;
    }
    if (batchAction === "assign_department" || batchAction === "clear_department") {
      departmentAssignmentMutation.mutate({
        userIds: selectedIds,
        departmentId: batchAction === "assign_department" ? batchDepartmentId || null : null,
      });
      return;
    }
    if (batchAction === "assign_base" || batchAction === "clear_base") {
      baseAssignmentMutation.mutate({
        userIds: selectedIds,
        baseStationId: batchAction === "assign_base" ? batchBaseId || null : null,
      });
      return;
    }
    bulkMutation.mutate({
      user_ids: selectedIds,
      action: batchAction,
      role: batchAction === "change_role" ? batchRole || undefined : undefined,
      note: "Applied from paginated user directory",
    });
  };

  const batchTargetMissing =
    (batchAction === "assign_department" && !batchDepartmentId) ||
    (batchAction === "assign_base" && !batchBaseId) ||
    (batchAction === "change_role" && !batchRole);
  const batchBlocked =
    (batchAction === "assign_department" || batchAction === "assign_base") &&
    selectedInactiveCount > 0;
  const batchPending =
    bulkMutation.isPending ||
    exportMutation.isPending ||
    departmentAssignmentMutation.isPending ||
    baseAssignmentMutation.isPending;

  return (
    <DepartmentLayout
      amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"}
      activeDepartment="admin-users"
    >
      <main className="aum2-shell">
        <header className="aum2-header">
          <div>
            <div className="aum2-title-row">
              <UsersRound size={20} aria-hidden="true" />
              <h1>User management</h1>
            </div>
            <p>Set up accounts, roles, departments, operating bases and employment status.</p>
          </div>
          <div className="aum2-header-actions">
            <IconButton
              label="Refresh directory"
              onClick={() => void refreshDirectory()}
              disabled={directoryQuery.isFetching}
            >
              <RefreshCw
                size={17}
                className={directoryQuery.isFetching ? "is-spinning" : ""}
              />
            </IconButton>
            <IconButton label="Add user" onClick={() => navigate(`${basePath}/new`)}>
              <UserPlus size={18} />
            </IconButton>
          </div>
        </header>

        {feedback ? (
          <div className="aum2-feedback" role="status">
            <span>{feedback}</span>
            <IconButton label="Dismiss message" onClick={() => setFeedback("")}>
              <X size={15} />
            </IconButton>
          </div>
        ) : null}

        <nav className="aum2-tabs" aria-label="User management sections">
          {(
            [
              ["directory", "Directory", UsersRound],
              ["groups", "Groups", UserRoundCog],
              ["permissions", "Permissions", ShieldCheck],
              ["lifecycle", "Lifecycle", UserCheck],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              type="button"
              className={tab === key ? "is-active" : ""}
              onClick={() => setTab(key)}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        {tab === "directory" ? (
          <section className="aum2-panel aum2-directory-panel">
            <div className="aum2-setup-strip" aria-label="User setup status">
              <div className="aum2-setup-intro">
                <strong>Setup status</strong>
                <span>Resolve placement gaps before allocating operational work.</span>
              </div>
              <button type="button" onClick={() => setAccountFilter("active")}>
                <CheckCircle2 size={15} />
                <span><strong>{metrics?.active_users ?? 0}</strong> active</span>
              </button>
              <button type="button" onClick={() => setDepartmentFilter("unassigned")}>
                <Building2 size={15} />
                <span><strong>{metrics?.departmentless_users ?? 0}</strong> without department</span>
              </button>
              <button type="button" onClick={() => setBaseFilter("unassigned")}>
                <MapPin size={15} />
                <span><strong>{data?.unassigned_base_users ?? 0}</strong> without base</span>
              </button>
              <button type="button" onClick={() => setBaseFilter("all")}>
                <Building2 size={15} />
                <span><strong>{data?.base_station_count ?? 0}</strong> active bases</span>
              </button>
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
                  <button
                    type="button"
                    onClick={() => setSearchInput("")}
                    aria-label="Clear search"
                    title="Clear search"
                  >
                    <X size={14} />
                  </button>
                ) : null}
              </label>
              <select
                value={roleFilter}
                onChange={(event) =>
                  setRoleFilter(event.target.value as AccountRole | "all")
                }
                aria-label="Filter by role"
              >
                <option value="all">All roles</option>
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>{formatRole(role)}</option>
                ))}
              </select>
              <select
                value={departmentFilter}
                onChange={(event) => setDepartmentFilter(event.target.value)}
                aria-label="Filter by department"
              >
                <option value="all">All departments</option>
                <option value="unassigned">No department</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}{department.is_active ? "" : " (inactive)"}
                  </option>
                ))}
              </select>
              <select
                value={baseFilter}
                onChange={(event) => setBaseFilter(event.target.value)}
                aria-label="Filter by operating base"
              >
                <option value="all">All bases</option>
                <option value="unassigned">No primary base</option>
                {bases.map((base) => (
                  <option key={base.id} value={base.id}>
                    {base.code} · {base.name}
                  </option>
                ))}
              </select>
              <select
                value={accountFilter}
                onChange={(event) =>
                  setAccountFilter(event.target.value as AdminUserAccountFilter)
                }
                aria-label="Filter by account status"
              >
                <option value="all">All accounts</option>
                <option value="active">Active only</option>
                <option value="inactive">Inactive only</option>
              </select>
              <select
                value={`${sortBy}:${sortDirection}`}
                onChange={(event) => {
                  const [field, direction] = event.target.value.split(":");
                  setSortBy(field as AdminUserSortField);
                  setSortDirection(direction as AdminUserSortDirection);
                }}
                aria-label="Sort users"
              >
                <option value="name:asc">Name A–Z</option>
                <option value="name:desc">Name Z–A</option>
                <option value="staff_code:asc">Staff code</option>
                <option value="department:asc">Department</option>
                <option value="last_login_at:desc">Recent activity</option>
                <option value="created_at:desc">Newest accounts</option>
              </select>
            </div>

            <div className={`aum2-batch-bar${selectedIds.length ? " is-active" : ""}`}>
              <strong>{selectedIds.length ? `${selectedIds.length} selected` : "Bulk actions"}</strong>
              <span className="aum2-batch-hint">
                {selectedIds.length
                  ? "Apply one change to all selected rows."
                  : "Select users from the table to avoid editing every row separately."}
              </span>
              <select
                value={batchAction}
                onChange={(event) => setBatchAction(event.target.value as BatchAction)}
                disabled={!selectedIds.length}
                aria-label="Bulk action"
              >
                <option value="">Choose action</option>
                <option value="enable">Enable accounts</option>
                <option value="disable">Disable accounts</option>
                <option value="assign_department">Assign department</option>
                <option value="clear_department">Clear department</option>
                <option value="assign_base">Assign primary base</option>
                <option value="clear_base">Clear primary base</option>
                <option value="change_role">Change role</option>
                <option value="export_csv">Export CSV</option>
                <option value="delete">Permanently delete</option>
              </select>
              {batchAction === "assign_department" ? (
                <select
                  value={batchDepartmentId}
                  onChange={(event) => setBatchDepartmentId(event.target.value)}
                  aria-label="Department to assign"
                >
                  <option value="">Select department</option>
                  {assignableDepartments.map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
                </select>
              ) : null}
              {batchAction === "assign_base" ? (
                <select
                  value={batchBaseId}
                  onChange={(event) => setBatchBaseId(event.target.value)}
                  aria-label="Base to assign"
                >
                  <option value="">Select base</option>
                  {bases.map((base) => (
                    <option key={base.id} value={base.id}>
                      {base.code} · {base.name}
                    </option>
                  ))}
                </select>
              ) : null}
              {batchAction === "change_role" ? (
                <select
                  value={batchRole}
                  onChange={(event) => setBatchRole(event.target.value as AccountRole | "")}
                  aria-label="Role to assign"
                >
                  <option value="">Select role</option>
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>{formatRole(role)}</option>
                  ))}
                </select>
              ) : null}
              <button
                type="button"
                className="aum2-compact-action"
                onClick={executeBatch}
                disabled={
                  !selectedIds.length ||
                  !batchAction ||
                  batchTargetMissing ||
                  batchBlocked ||
                  batchPending
                }
              >
                Apply
              </button>
              {selectedIds.length ? (
                <button
                  type="button"
                  className="aum2-text-action"
                  onClick={() => setSelectedIds([])}
                >
                  Clear selection
                </button>
              ) : null}
              {batchBlocked ? (
                <span className="aum2-inline-warning">
                  <CircleAlert size={14} />
                  Remove {selectedInactiveCount} inactive account(s) before assigning placement.
                </span>
              ) : null}
            </div>

            <div className="aum2-table-wrap" role="region" aria-label="User directory" tabIndex={0}>
              <table className="aum2-table">
                <thead>
                  <tr>
                    <th className="is-check">
                      <input
                        type="checkbox"
                        checked={allPageSelected}
                        onChange={(event) =>
                          setSelectedIds(
                            event.target.checked
                              ? items.map((item) => item.id)
                              : [],
                          )
                        }
                        aria-label="Select current page"
                      />
                    </th>
                    <th>User</th>
                    <th>Role</th>
                    <th>Department</th>
                    <th>Primary base</th>
                    <th>Access</th>
                    <th>Activity</th>
                    <th className="is-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {directoryQuery.isLoading ? (
                    <tr><td colSpan={8} className="aum2-empty">Loading users…</td></tr>
                  ) : directoryQuery.isError ? (
                    <tr>
                      <td colSpan={8} className="aum2-empty is-error">
                        {directoryQuery.error instanceof Error
                          ? directoryQuery.error.message
                          : "The directory could not be loaded."}
                      </td>
                    </tr>
                  ) : items.length ? (
                    items.map((user) => {
                      const tone = presenceTone(user);
                      return (
                        <tr
                          key={user.id}
                          className={`${selectedIds.includes(user.id) ? "is-selected" : ""}${
                            !user.is_active ? " is-inactive" : ""
                          }`}
                        >
                          <td className="is-check">
                            <input
                              type="checkbox"
                              checked={selectedIds.includes(user.id)}
                              onChange={(event) =>
                                setSelectedIds((current) =>
                                  event.target.checked
                                    ? [...current, user.id]
                                    : current.filter((id) => id !== user.id),
                                )
                              }
                              aria-label={`Select ${user.full_name}`}
                            />
                          </td>
                          <td>
                            <button
                              type="button"
                              className="aum2-user-link"
                              onClick={() => navigate(`${basePath}/${user.id}`)}
                              title={user.full_name}
                            >
                              {user.full_name}
                            </button>
                            <span className="aum2-secondary" title={`${user.staff_code} · ${user.email}`}>
                              {user.staff_code} · {user.email}
                            </span>
                          </td>
                          <td>
                            <strong className="aum2-cell-primary">{user.display_title}</strong>
                            <span className="aum2-secondary">{formatRole(user.role)}</span>
                          </td>
                          <td>
                            <PlacementCell
                              user={user}
                              kind="department"
                              departments={departments}
                              bases={bases}
                              editing={editingDepartmentUserId === user.id}
                              setEditing={(editing) =>
                                setEditingDepartmentUserId(editing ? user.id : null)
                              }
                              pending={departmentAssignmentMutation.isPending}
                              onAssign={(departmentId) =>
                                departmentAssignmentMutation.mutate({
                                  userIds: [user.id],
                                  departmentId,
                                })
                              }
                            />
                          </td>
                          <td>
                            <PlacementCell
                              user={user}
                              kind="base"
                              departments={departments}
                              bases={bases}
                              editing={editingBaseUserId === user.id}
                              setEditing={(editing) =>
                                setEditingBaseUserId(editing ? user.id : null)
                              }
                              pending={baseAssignmentMutation.isPending}
                              onAssign={(baseStationId) =>
                                baseAssignmentMutation.mutate({
                                  userIds: [user.id],
                                  baseStationId,
                                })
                              }
                            />
                          </td>
                          <td>
                            <span className={`aum2-access ${user.is_active ? "is-enabled" : "is-disabled"}`}>
                              {user.is_active ? <ShieldCheck size={14} /> : <ShieldOff size={14} />}
                              {user.is_active ? "Enabled" : "Disabled"}
                            </span>
                          </td>
                          <td>
                            <span className="aum2-activity">
                              <span className={`aum2-presence-dot is-${tone}`} />
                              <span>
                                {user.presence_display.status_label}
                                <small>{relativeTime(user.presence_display.last_seen_at)}</small>
                              </span>
                            </span>
                          </td>
                          <td className="is-actions">
                            <div className="aum2-row-actions">
                              <IconButton label={`View ${user.full_name}`} onClick={() => navigate(`${basePath}/${user.id}`)}>
                                <Eye size={15} />
                              </IconButton>
                              <IconButton
                                label={user.is_active ? "Disable account" : "Enable account"}
                                onClick={() => toggleUserMutation.mutate(user)}
                                disabled={toggleUserMutation.isPending}
                                danger={user.is_active}
                              >
                                {user.is_active ? <UserX size={15} /> : <UserCheck size={15} />}
                              </IconButton>
                              <IconButton
                                label="Require password reset"
                                onClick={() => resetPasswordMutation.mutate(user.id)}
                                disabled={resetPasswordMutation.isPending}
                              >
                                <KeyRound size={15} />
                              </IconButton>
                              <IconButton
                                label="Revoke active sessions"
                                onClick={() => revokeMutation.mutate(user.id)}
                                disabled={revokeMutation.isPending}
                                danger
                              >
                                <ShieldOff size={15} />
                              </IconButton>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={8} className="aum2-empty">
                        No users match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <footer className="aum2-pagination">
              <span>
                {data?.total
                  ? `${(data.page - 1) * data.page_size + 1}–${Math.min(
                      data.page * data.page_size,
                      data.total,
                    )} of ${data.total}`
                  : "0 users"}
              </span>
              <div>
                <label>
                  Rows
                  <select
                    value={pageSize}
                    onChange={(event) => setPageSize(Number(event.target.value))}
                  >
                    {PAGE_SIZES.map((size) => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </label>
                <IconButton label="First page" onClick={() => setPage(1)} disabled={!data?.has_previous}>
                  <ChevronsLeft size={15} />
                </IconButton>
                <IconButton label="Previous page" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={!data?.has_previous}>
                  <ChevronLeft size={15} />
                </IconButton>
                <span>Page {data?.page ?? 1} of {data?.pages ?? 1}</span>
                <IconButton label="Next page" onClick={() => setPage((current) => current + 1)} disabled={!data?.has_next}>
                  <ChevronRight size={15} />
                </IconButton>
                <IconButton label="Last page" onClick={() => setPage(data?.pages ?? 1)} disabled={!data?.has_next}>
                  <ChevronsRight size={15} />
                </IconButton>
              </div>
            </footer>
          </section>
        ) : null}

        {tab === "groups" ? (
          <section className="aum2-grid-two">
            <div className="aum2-panel">
              <div className="aum2-section-heading">
                <div>
                  <h2>Create group</h2>
                  <p>Build reusable cohorts instead of assigning users one at a time.</p>
                </div>
                <Plus size={18} />
              </div>
              <div className="aum2-form-grid">
                <label>
                  Name
                  <input value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} />
                </label>
                <label>
                  Code
                  <input value={newGroupCode} onChange={(event) => setNewGroupCode(event.target.value)} placeholder="Auto-generated when blank" />
                </label>
                <label className="is-wide">
                  Description
                  <textarea rows={3} value={newGroupDescription} onChange={(event) => setNewGroupDescription(event.target.value)} />
                </label>
                <button
                  type="button"
                  className="aum2-primary-action is-wide"
                  disabled={!newGroupName.trim() || createGroupMutation.isPending}
                  onClick={() => createGroupMutation.mutate()}
                >
                  <Plus size={15} /> Create group
                </button>
              </div>
            </div>
            <div className="aum2-panel">
              <div className="aum2-section-heading">
                <div>
                  <h2>Groups</h2>
                  <p>{groups.length} configured cohorts.</p>
                </div>
              </div>
              <div className="aum2-table-wrap is-short">
                <table className="aum2-table is-compact">
                  <thead>
                    <tr><th>Name</th><th>Type</th><th>Members</th><th>Status</th><th className="is-actions">Actions</th></tr>
                  </thead>
                  <tbody>
                    {groups.length ? groups.map((group) => (
                      <tr key={group.id}>
                        <td>
                          <strong className="aum2-cell-primary">{group.name}</strong>
                          <span className="aum2-secondary">{group.code}</span>
                        </td>
                        <td>{formatGroupType(group.group_type)}</td>
                        <td>{group.member_count}</td>
                        <td>
                          <span className={`aum2-status-pill ${group.is_active ? "is-success" : "is-muted"}`}>
                            {group.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="is-actions">
                          <IconButton
                            label={`Delete ${group.name}`}
                            onClick={() => {
                              if (window.confirm(`Delete group “${group.name}”?`)) {
                                deleteGroupMutation.mutate(group.id);
                              }
                            }}
                            disabled={group.is_system_managed || deleteGroupMutation.isPending}
                            danger
                          >
                            <Trash2 size={15} />
                          </IconButton>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan={5} className="aum2-empty">No groups configured.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {tab === "permissions" ? (
          <section className="aum2-grid-two">
            <div className="aum2-panel">
              <div className="aum2-section-heading">
                <div>
                  <h2>Create permission type</h2>
                  <p>Define controlled authorisation rules for later user grants.</p>
                </div>
                <ShieldCheck size={18} />
              </div>
              <div className="aum2-form-grid">
                <label>
                  Code
                  <input
                    value={permissionForm.code}
                    onChange={(event) =>
                      setPermissionForm((current) => ({ ...current, code: event.target.value }))
                    }
                  />
                </label>
                <label>
                  Name
                  <input
                    value={permissionForm.name}
                    onChange={(event) =>
                      setPermissionForm((current) => ({ ...current, name: event.target.value }))
                    }
                  />
                </label>
                <label>
                  Maintenance scope
                  <select
                    value={permissionForm.maintenance_scope || "LINE"}
                    onChange={(event) =>
                      setPermissionForm((current) => ({
                        ...current,
                        maintenance_scope:
                          event.target.value as AdminAuthorisationTypeCreatePayload["maintenance_scope"],
                      }))
                    }
                  >
                    <option value="LINE">Line</option>
                    <option value="BASE">Base</option>
                    <option value="SHOP">Shop</option>
                    <option value="ALL">All</option>
                  </select>
                </label>
                <label>
                  Regulation reference
                  <input
                    value={permissionForm.regulation_reference || ""}
                    onChange={(event) =>
                      setPermissionForm((current) => ({
                        ...current,
                        regulation_reference: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="is-wide">
                  Description
                  <textarea
                    rows={2}
                    value={permissionForm.description || ""}
                    onChange={(event) =>
                      setPermissionForm((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                  />
                </label>
                <div className="aum2-check-row is-wide">
                  <label>
                    <input
                      type="checkbox"
                      checked={Boolean(permissionForm.can_issue_crs)}
                      onChange={(event) =>
                        setPermissionForm((current) => ({
                          ...current,
                          can_issue_crs: event.target.checked,
                        }))
                      }
                    />
                    May issue CRS
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={Boolean(permissionForm.requires_dual_sign)}
                      onChange={(event) =>
                        setPermissionForm((current) => ({
                          ...current,
                          requires_dual_sign: event.target.checked,
                        }))
                      }
                    />
                    Dual sign required
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={Boolean(permissionForm.requires_valid_licence)}
                      onChange={(event) =>
                        setPermissionForm((current) => ({
                          ...current,
                          requires_valid_licence: event.target.checked,
                        }))
                      }
                    />
                    Valid licence required
                  </label>
                </div>
                <button
                  type="button"
                  className="aum2-primary-action is-wide"
                  disabled={
                    !permissionForm.code.trim() ||
                    !permissionForm.name.trim() ||
                    createPermissionMutation.isPending
                  }
                  onClick={() => createPermissionMutation.mutate()}
                >
                  <Plus size={15} /> Create permission type
                </button>
              </div>
            </div>
            <div className="aum2-panel">
              <div className="aum2-section-heading">
                <div>
                  <h2>Permission catalogue</h2>
                  <p>{permissionTypes.length} authorisation types.</p>
                </div>
              </div>
              <div className="aum2-table-wrap is-short">
                <table className="aum2-table is-compact">
                  <thead>
                    <tr><th>Permission</th><th>Scope</th><th>Controls</th><th>Status</th><th className="is-actions">Actions</th></tr>
                  </thead>
                  <tbody>
                    {permissionTypes.length ? permissionTypes.map((permission) => (
                      <tr key={permission.id}>
                        <td>
                          <strong className="aum2-cell-primary">{permission.name}</strong>
                          <span className="aum2-secondary">{permission.code}</span>
                        </td>
                        <td>{formatRole(permission.maintenance_scope || "ALL")}</td>
                        <td>
                          <div className="aum2-control-tags">
                            {permission.can_issue_crs ? <span>CRS</span> : null}
                            {permission.requires_dual_sign ? <span>Dual sign</span> : null}
                            {permission.requires_valid_licence ? <span>Licence</span> : null}
                            {!permission.can_issue_crs &&
                            !permission.requires_dual_sign &&
                            !permission.requires_valid_licence ? <span>Standard</span> : null}
                          </div>
                        </td>
                        <td>
                          <span className={`aum2-status-pill ${permission.is_active ? "is-success" : "is-muted"}`}>
                            {permission.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="is-actions">
                          <IconButton
                            label={`Delete ${permission.name}`}
                            onClick={() => {
                              if (window.confirm(`Delete permission type “${permission.name}” and its linked grants?`)) {
                                deletePermissionMutation.mutate(permission.id);
                              }
                            }}
                            disabled={deletePermissionMutation.isPending}
                            danger
                          >
                            <Trash2 size={15} />
                          </IconButton>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan={5} className="aum2-empty">No permission types configured.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {tab === "lifecycle" ? (
          <section className="aum2-panel">
            <div className="aum2-section-heading">
              <div>
                <h2>Employment lifecycle</h2>
                <p>Apply controlled hire, transfer, leave, role and offboarding changes.</p>
              </div>
              <UserRoundCog size={18} />
            </div>
            <div className="aum2-form-grid is-lifecycle">
              <label className="is-wide">
                Find user
                <input
                  value={lifecycleSearch}
                  onChange={(event) => setLifecycleSearch(event.target.value)}
                  placeholder="Search name, email or staff code"
                />
              </label>
              <label className="is-wide">
                User
                <select
                  value={lifecycleUserId}
                  onChange={(event) => {
                    setLifecycleUserId(event.target.value);
                    setLifecycleDepartmentId("");
                    setLifecycleBaseId("");
                  }}
                >
                  <option value="">Select user</option>
                  {lifecycleUsers.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name} · {user.staff_code} · {user.is_active ? "Active" : "Inactive"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Action
                <select
                  value={lifecycleAction}
                  onChange={(event) =>
                    setLifecycleAction(event.target.value as UserEmploymentActionPayload["action"])
                  }
                >
                  <option value="new_hire">New hire</option>
                  <option value="promote">Promote</option>
                  <option value="demote">Demote</option>
                  <option value="transfer">Transfer</option>
                  <option value="resign">Resign / offboard</option>
                  <option value="reinstate">Reinstate</option>
                  <option value="schedule_leave">Schedule leave</option>
                  <option value="return_from_leave">Return from leave</option>
                </select>
              </label>
              <label>
                Role
                <select
                  value={lifecycleRole}
                  onChange={(event) => setLifecycleRole(event.target.value as AccountRole | "")}
                >
                  <option value="">Keep current role</option>
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>{formatRole(role)}</option>
                  ))}
                </select>
              </label>
              <label>
                Department
                <select
                  value={lifecycleDepartmentId}
                  disabled={!lifecycleCanChangePlacement}
                  onChange={(event) => setLifecycleDepartmentId(event.target.value)}
                >
                  <option value="">Keep current department</option>
                  {assignableDepartments.map((department) => (
                    <option key={department.id} value={department.id}>{department.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Primary base
                <select
                  value={lifecycleBaseId}
                  disabled={!lifecycleCanChangePlacement}
                  onChange={(event) => setLifecycleBaseId(event.target.value)}
                >
                  <option value="">Keep current base</option>
                  {bases.map((base) => (
                    <option key={base.id} value={base.id}>
                      {base.code} · {base.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Position title
                <input value={lifecycleTitle} onChange={(event) => setLifecycleTitle(event.target.value)} />
              </label>
              <label>
                Effective from
                <input type="datetime-local" value={lifecycleFrom} onChange={(event) => setLifecycleFrom(event.target.value)} />
              </label>
              <label>
                Effective to
                <input type="datetime-local" value={lifecycleTo} onChange={(event) => setLifecycleTo(event.target.value)} />
              </label>
              <label className="is-wide">
                Reason / note
                <textarea rows={3} value={lifecycleNote} onChange={(event) => setLifecycleNote(event.target.value)} />
              </label>
              {!lifecycleCanChangePlacement && lifecycleUserId ? (
                <div className="aum2-inline-warning is-wide">
                  <CircleAlert size={15} />
                  This account is inactive. Select Reinstate or New hire before assigning a new department or base.
                </div>
              ) : null}
              <button
                type="button"
                className="aum2-primary-action is-wide"
                disabled={!lifecycleUserId || lifecycleMutation.isPending}
                onClick={() => lifecycleMutation.mutate()}
              >
                <UserCheck size={16} /> Apply lifecycle action
              </button>
            </div>
          </section>
        ) : null}
      </main>
    </DepartmentLayout>
  );
}
