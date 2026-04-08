import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, EmptyState, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
import { getCachedUser, getContext } from "../services/auth";
import {
  addAdminUserGroupMember,
  createAdminUserGroup,
  deactivateAdminUser,
  deactivateAdminUserGroup,
  getActiveAmoId,
  importPersonnelFile,
  listAdminAmos,
  listAdminDepartments,
  listAdminUserGroups,
  listAdminUserSummaries,
  setActiveAmoId,
  setAdminContext,
  updateAdminUser,
} from "../services/adminUsers";
import type {
  AdminAmoRead,
  AdminDepartmentRead,
  AdminUserGroupRead,
  AdminUserSummaryRead,
  PersonnelImportSummary,
} from "../services/adminUsers";

type AdminTabKey = "users" | "groups" | "import";

type UrlParams = { amoCode?: string };

const GROUP_TEMPLATES = [
  { name: "Post Holders", group_type: "POST_HOLDERS" as const, visibility: "SYSTEM" as const, description: "Managers and nominated post holders." },
  { name: "Quality", group_type: "DEPARTMENT" as const, visibility: "AMO" as const, description: "Quality assurance and compliance personnel." },
  { name: "Base Maintenance", group_type: "DEPARTMENT" as const, visibility: "AMO" as const, description: "Heavy maintenance and hangar teams." },
  { name: "Line Maintenance", group_type: "DEPARTMENT" as const, visibility: "AMO" as const, description: "Turnaround, transit, and line support staff." },
  { name: "Internal Auditors", group_type: "CUSTOM" as const, visibility: "AMO" as const, description: "Internal audit pool and supporting reviewers." },
];

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatLastSeen(value?: string | null, onlineStatus?: string): string {
  if (!value) return onlineStatus === "online" ? "Active now" : "Never seen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function presenceTone(status?: string): string {
  if (status === "online") return "is-online";
  if (status === "away") return "is-away";
  return "is-offline";
}

function roleLabel(value: string): string {
  return value.replaceAll("_", " ");
}

const AdminDashboardPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const canAccessAdmin = !!currentUser?.is_superuser || !!currentUser?.is_amo_admin;

  const [activeTab, setActiveTab] = useState<AdminTabKey>("users");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [selectedAmoId, setSelectedAmoId] = useState<string>(() => getActiveAmoId() || currentUser?.amo_id || "");
  const [selectedGroupId, setSelectedGroupId] = useState<string>("");
  const [groupName, setGroupName] = useState("");
  const [groupDescription, setGroupDescription] = useState("");
  const [groupOwnerUserId, setGroupOwnerUserId] = useState<string>(currentUser?.id || "");
  const [groupMemberUserId, setGroupMemberUserId] = useState("");
  const [personnelFile, setPersonnelFile] = useState<File | null>(null);
  const [personnelResult, setPersonnelResult] = useState<PersonnelImportSummary | null>(null);
  const [personnelError, setPersonnelError] = useState<string | null>(null);
  const [personnelNotice, setPersonnelNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedAmoId && currentUser?.amo_id) {
      setSelectedAmoId(currentUser.amo_id);
    }
  }, [currentUser?.amo_id, selectedAmoId]);

  const amosQuery = useQuery<AdminAmoRead[]>({
    queryKey: ["admin-amos-picker"],
    queryFn: listAdminAmos,
    enabled: isSuperuser,
    staleTime: 5 * 60_000,
  });

  const departmentsQuery = useQuery<AdminDepartmentRead[]>({
    queryKey: ["admin-departments", selectedAmoId || currentUser?.amo_id],
    queryFn: () => listAdminDepartments(selectedAmoId || currentUser?.amo_id || undefined),
    enabled: !!(selectedAmoId || currentUser?.amo_id),
    staleTime: 60_000,
  });

  const usersQuery = useQuery<AdminUserSummaryRead[]>({
    queryKey: ["admin-users-summary", selectedAmoId || currentUser?.amo_id, search],
    queryFn: () =>
      listAdminUserSummaries({
        amo_id: selectedAmoId || currentUser?.amo_id || undefined,
        limit: 300,
        search: search.trim() || undefined,
      }),
    enabled: !!(selectedAmoId || currentUser?.amo_id),
    staleTime: 30_000,
  });

  const groupsQuery = useQuery<AdminUserGroupRead[]>({
    queryKey: ["admin-user-groups", selectedAmoId || currentUser?.amo_id],
    queryFn: () => listAdminUserGroups({ amo_id: selectedAmoId || currentUser?.amo_id || undefined }),
    enabled: !!(selectedAmoId || currentUser?.amo_id),
    staleTime: 30_000,
  });

  const departments = departmentsQuery.data ?? [];
  const departmentMap = useMemo(() => new Map(departments.map((dept) => [dept.id, dept.name])), [departments]);
  const users = usersQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const selectedGroup = groups.find((group) => group.id === selectedGroupId) ?? groups[0] ?? null;

  useEffect(() => {
    if (selectedGroupId) return;
    if (groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const invalidateAdminData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-users-summary"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-groups"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-departments"] }),
    ]);
  };

  const toggleUserMutation = useMutation({
    mutationFn: async (user: AdminUserSummaryRead) => {
      if (user.is_active) {
        await deactivateAdminUser(user.id);
        return;
      }
      await updateAdminUser(user.id, { is_active: true });
    },
    onSuccess: () => void invalidateAdminData(),
  });

  const createGroupMutation = useMutation({
    mutationFn: createAdminUserGroup,
    onSuccess: async () => {
      setGroupName("");
      setGroupDescription("");
      await invalidateAdminData();
    },
  });

  const addMemberMutation = useMutation({
    mutationFn: ({ groupId, userId }: { groupId: string; userId: string }) =>
      addAdminUserGroupMember(groupId, { user_id: userId, member_role: "member" }),
    onSuccess: async (group) => {
      setSelectedGroupId(group.id);
      setGroupMemberUserId("");
      await invalidateAdminData();
    },
  });

  const deactivateGroupMutation = useMutation({
    mutationFn: deactivateAdminUserGroup,
    onSuccess: async () => {
      await invalidateAdminData();
    },
  });

  const activeAmoMutation = useMutation({
    mutationFn: async (amoId: string) => {
      setActiveAmoId(amoId);
      return setAdminContext({ active_amo_id: amoId });
    },
    onSuccess: async () => {
      await invalidateAdminData();
    },
  });

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      if (roleFilter !== "ALL" && user.role !== roleFilter) return false;
      if (statusFilter === "ACTIVE" && !user.is_active) return false;
      if (statusFilter === "INACTIVE" && user.is_active) return false;
      if (statusFilter === "ONLINE" && user.online_status !== "online") return false;
      if (statusFilter === "OFFLINE" && user.online_status === "online") return false;
      return true;
    });
  }, [roleFilter, statusFilter, users]);

  const metrics = useMemo(() => {
    const total = users.length;
    const active = users.filter((user) => user.is_active).length;
    const online = users.filter((user) => user.online_status === "online").length;
    const inactive = total - active;
    const groupCount = groups.length;
    return { total, active, online, inactive, groupCount };
  }, [groups.length, users]);

  const activeAmoLabel = useMemo(() => {
    if (!isSuperuser) return null;
    const amo = (amosQuery.data ?? []).find((item) => item.id === selectedAmoId);
    return amo ? `${amo.amo_code} — ${amo.name}` : null;
  }, [amosQuery.data, isSuperuser, selectedAmoId]);

  const runPersonnelImport = async (dryRun: boolean) => {
    if (!personnelFile) {
      setPersonnelError("Choose the latest People workbook before running import.");
      return;
    }
    setPersonnelError(null);
    setPersonnelNotice(dryRun ? "Dry-run in progress…" : "Live import in progress…");
    try {
      const result = await importPersonnelFile({
        file: personnelFile,
        dryRun,
        amoId: selectedAmoId || currentUser?.amo_id || undefined,
        sheetName: "People",
      });
      setPersonnelResult(result);
      setPersonnelNotice(dryRun ? "Dry-run completed." : "Live import completed.");
      await invalidateAdminData();
    } catch (error: any) {
      setPersonnelError(error?.message || "Personnel import failed.");
      setPersonnelNotice(null);
    }
  };

  if (!canAccessAdmin) {
    return null;
  }

  return (
    <DepartmentLayout amoCode={amoCode ?? ctx.amoCode ?? "UNKNOWN"} activeDepartment="admin-users">
      <div className="admin-page admin-user-hub">
        <PageHeader
          title="User management"
          subtitle="Single-page workspace for people, groups, permissions, presence, and import operations."
          actions={
            <div className="admin-user-hub__header-actions">
              {isSuperuser ? (
                <select
                  className="input input--compact"
                  value={selectedAmoId}
                  onChange={(event) => {
                    const next = event.target.value;
                    setSelectedAmoId(next);
                    activeAmoMutation.mutate(next);
                  }}
                >
                  {(amosQuery.data ?? []).map((amo) => (
                    <option key={amo.id} value={amo.id}>
                      {amo.amo_code} — {amo.name}
                    </option>
                  ))}
                </select>
              ) : null}
              <Button type="button" variant="secondary" onClick={() => void invalidateAdminData()}>
                Refresh
              </Button>
              <Button type="button" onClick={() => navigate(`/maintenance/${amoCode ?? ctx.amoCode ?? "UNKNOWN"}/admin/users/new`)}>
                Add user
              </Button>
            </div>
          }
        />

        {activeAmoLabel ? <div className="admin-user-hub__amo-label">Managing: {activeAmoLabel}</div> : null}

        <div className="admin-user-hub__metrics">
          <div className="admin-user-hub__metric-card"><span>Total users</span><strong>{metrics.total}</strong></div>
          <div className="admin-user-hub__metric-card"><span>Active</span><strong>{metrics.active}</strong></div>
          <div className="admin-user-hub__metric-card"><span>Online now</span><strong>{metrics.online}</strong></div>
          <div className="admin-user-hub__metric-card"><span>Inactive</span><strong>{metrics.inactive}</strong></div>
          <div className="admin-user-hub__metric-card"><span>Groups</span><strong>{metrics.groupCount}</strong></div>
        </div>

        <div className="admin-user-hub__tabs" role="tablist" aria-label="User management sections">
          {[
            { id: "users", label: "Users" },
            { id: "groups", label: "Groups" },
            { id: "import", label: "Import & HR metrics" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`admin-user-hub__tab ${activeTab === tab.id ? "is-active" : ""}`}
              onClick={() => setActiveTab(tab.id as AdminTabKey)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {usersQuery.isError ? (
          <InlineAlert tone="danger" title="User load failed">
            <span>Users could not be loaded for this AMO.</span>
          </InlineAlert>
        ) : null}

        {activeTab === "users" ? (
          <Panel title="User directory" subtitle="Dense, operational table for HR and management use.">
            <div className="admin-user-hub__toolbar">
              <input
                className="input"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search name, email, or staff code"
              />
              <select className="input input--compact" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                <option value="ALL">All roles</option>
                {[...new Set(users.map((user) => user.role))].map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </select>
              <select className="input input--compact" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="ALL">All statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
                <option value="ONLINE">Online</option>
                <option value="OFFLINE">Away / Offline</option>
              </select>
            </div>
            <Table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Staff code</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Account</th>
                  <th>Status</th>
                  <th>Last seen</th>
                  <th>Groups</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {!usersQuery.isLoading && filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={9}><EmptyState title="No users match the current filters." /></td>
                  </tr>
                ) : null}
                {filteredUsers.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <button type="button" className="link-button" onClick={() => navigate(`/maintenance/${amoCode ?? ctx.amoCode ?? "UNKNOWN"}/admin/users/${user.id}`)}>
                        {user.full_name}
                      </button>
                      <div className="admin-user-hub__subcell">{user.email}</div>
                    </td>
                    <td>{user.staff_code}</td>
                    <td>{roleLabel(user.role)}</td>
                    <td>{departmentMap.get(user.department_id ?? "") ?? "—"}</td>
                    <td>{user.is_active ? "Enabled" : "Disabled"}</td>
                    <td>
                      <span className={`admin-user-hub__presence ${presenceTone(user.online_status)}`}>
                        {user.online_status}
                      </span>
                    </td>
                    <td>{formatLastSeen(user.last_seen_at, user.online_status)}</td>
                    <td>{user.groups_count}</td>
                    <td>
                      <div className="admin-user-hub__actions-cell">
                        <Button type="button" size="sm" variant="secondary" onClick={() => navigate(`/maintenance/${amoCode ?? ctx.amoCode ?? "UNKNOWN"}/admin/users/${user.id}`)}>
                          View
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant={user.is_active ? "danger" : "ghost"}
                          onClick={() => toggleUserMutation.mutate(user)}
                        >
                          {user.is_active ? "Disable" : "Enable"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>
        ) : null}

        {activeTab === "groups" ? (
          <div className="admin-user-hub__groups-layout">
            <Panel title="Create and manage groups" subtitle="System groups, departmental groups, and user-owned collaboration groups.">
              <div className="admin-user-hub__group-form">
                <input className="input" value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="Group name" />
                <input className="input" value={groupDescription} onChange={(event) => setGroupDescription(event.target.value)} placeholder="Description" />
                <select className="input input--compact" value={groupOwnerUserId} onChange={(event) => setGroupOwnerUserId(event.target.value)}>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>{user.full_name}</option>
                  ))}
                </select>
                <Button
                  type="button"
                  onClick={() =>
                    createGroupMutation.mutate({
                      amo_id: selectedAmoId || currentUser?.amo_id || undefined,
                      owner_user_id: groupOwnerUserId || currentUser?.id || null,
                      name: groupName.trim(),
                      description: groupDescription.trim() || undefined,
                      group_type: "CUSTOM",
                      visibility: "AMO",
                    })
                  }
                  disabled={!groupName.trim()}
                >
                  Create custom group
                </Button>
              </div>
              <div className="admin-user-hub__template-grid">
                {GROUP_TEMPLATES.map((template) => (
                  <button
                    key={template.name}
                    type="button"
                    className="admin-user-hub__template-card"
                    onClick={() =>
                      createGroupMutation.mutate({
                        amo_id: selectedAmoId || currentUser?.amo_id || undefined,
                        owner_user_id: currentUser?.id || null,
                        name: template.name,
                        description: template.description,
                        group_type: template.group_type,
                        visibility: template.visibility,
                        is_system_managed: template.visibility === "SYSTEM",
                      })
                    }
                  >
                    <strong>{template.name}</strong>
                    <span>{template.description}</span>
                  </button>
                ))}
              </div>
            </Panel>

            <Panel title="Group register" subtitle="Select a group to review members, ownership, and visibility.">
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
                  {groups.length === 0 ? (
                    <tr>
                      <td colSpan={5}><EmptyState title="No groups created yet." /></td>
                    </tr>
                  ) : null}
                  {groups.map((group) => (
                    <tr
                      key={group.id}
                      className={selectedGroup?.id === group.id ? "admin-user-hub__row-selected" : undefined}
                      onClick={() => setSelectedGroupId(group.id)}
                    >
                      <td>
                        <strong>{group.name}</strong>
                        <div className="admin-user-hub__subcell">{group.code}</div>
                      </td>
                      <td>{roleLabel(group.group_type)}</td>
                      <td>{roleLabel(group.visibility)}</td>
                      <td>{group.member_count}</td>
                      <td>{group.is_active ? "Active" : "Inactive"}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>

              {selectedGroup ? (
                <div className="admin-user-hub__group-detail">
                  <div className="admin-user-hub__group-detail-header">
                    <div>
                      <h3>{selectedGroup.name}</h3>
                      <p>{selectedGroup.description || "No description provided."}</p>
                    </div>
                    <Button type="button" variant="danger" size="sm" onClick={() => deactivateGroupMutation.mutate(selectedGroup.id)}>
                      Deactivate
                    </Button>
                  </div>
                  <div className="admin-user-hub__toolbar">
                    <select className="input" value={groupMemberUserId} onChange={(event) => setGroupMemberUserId(event.target.value)}>
                      <option value="">Add user to this group</option>
                      {users.filter((user) => !selectedGroup.members.some((member) => member.user_id === user.id)).map((user) => (
                        <option key={user.id} value={user.id}>{user.full_name}</option>
                      ))}
                    </select>
                    <Button type="button" variant="secondary" onClick={() => selectedGroup && groupMemberUserId && addMemberMutation.mutate({ groupId: selectedGroup.id, userId: groupMemberUserId })} disabled={!groupMemberUserId}>
                      Add member
                    </Button>
                  </div>
                  <Table>
                    <thead>
                      <tr>
                        <th>Member</th>
                        <th>Role</th>
                        <th>Member type</th>
                        <th>Added</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedGroup.members.length === 0 ? (
                        <tr>
                          <td colSpan={4}><EmptyState title="This group has no members yet." /></td>
                        </tr>
                      ) : null}
                      {selectedGroup.members.map((member) => (
                        <tr key={`${selectedGroup.id}-${member.user_id}`}>
                          <td>
                            <strong>{member.full_name}</strong>
                            <div className="admin-user-hub__subcell">{member.email}</div>
                          </td>
                          <td>{roleLabel(member.role)}</td>
                          <td>{roleLabel(member.member_role)}</td>
                          <td>{formatDateTime(member.added_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              ) : null}
            </Panel>
          </div>
        ) : null}

        {activeTab === "import" ? (
          <div className="admin-user-hub__import-grid">
            <Panel title="Personnel import" subtitle="People workbook ingestion with dry-run support.">
              <div className="admin-user-hub__import-panel">
                <input type="file" accept=".xlsx,.xlsm" onChange={(event) => setPersonnelFile(event.target.files?.[0] ?? null)} />
                <div className="admin-user-hub__actions-cell">
                  <Button type="button" variant="secondary" onClick={() => void runPersonnelImport(true)}>Dry-run</Button>
                  <Button type="button" onClick={() => void runPersonnelImport(false)}>Import</Button>
                </div>
                {personnelError ? (
                  <InlineAlert tone="danger" title="Import error"><span>{personnelError}</span></InlineAlert>
                ) : null}
                {personnelNotice && !personnelError ? (
                  <InlineAlert tone="info" title="Import status"><span>{personnelNotice}</span></InlineAlert>
                ) : null}
                {personnelResult ? (
                  <div className="admin-user-hub__import-summary">
                    <div>Rows processed: {personnelResult.rows_processed}</div>
                    <div>Personnel created / updated: {personnelResult.created_personnel} / {personnelResult.updated_personnel}</div>
                    <div>Accounts created / updated: {personnelResult.created_accounts} / {personnelResult.updated_accounts}</div>
                    <div>Rejected rows: {personnelResult.rejected_rows}</div>
                    <div>Conflicts: {personnelResult.conflicts?.length ?? 0}</div>
                  </div>
                ) : null}
              </div>
            </Panel>
            <Panel title="Managerial signals" subtitle="Fast HR and leadership indicators from the current view.">
              <div className="admin-user-hub__signals-grid">
                <div className="admin-user-hub__signal-card"><span>Active headcount</span><strong>{metrics.active}</strong></div>
                <div className="admin-user-hub__signal-card"><span>Offline today</span><strong>{users.filter((user) => user.online_status === "offline").length}</strong></div>
                <div className="admin-user-hub__signal-card"><span>Post-holder / manager groups</span><strong>{groups.filter((group) => group.group_type === "POST_HOLDERS").length}</strong></div>
                <div className="admin-user-hub__signal-card"><span>Users without groups</span><strong>{users.filter((user) => user.groups_count === 0).length}</strong></div>
              </div>
              <p className="admin-user-hub__note">
                Long-run HR scoring should combine this page with task completion data, recurrent training validity, authorization coverage, login hygiene,
                and activity trends from each user profile page.
              </p>
            </Panel>
          </div>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default AdminDashboardPage;
