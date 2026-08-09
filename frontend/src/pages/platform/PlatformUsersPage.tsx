import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { platformOperationsApi, type DataMode } from "../../services/platformOperations";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const PAGE_SIZE = 100;

type UserHubRow = {
  id: string;
  email: string;
  full_name: string;
  staff_code?: string | null;
  role?: string | null;
  tenant_id?: string | null;
  tenant_name?: string | null;
  data_mode?: string;
  is_active: boolean;
  is_superuser: boolean;
  mfa_registered?: boolean;
  failed_login_count?: number;
  locked_until?: string | null;
  last_login_at?: string | null;
  token_revoked_at?: string | null;
  must_change_password?: boolean;
  updated_at?: string | null;
};

type BulkAction = "DISABLE" | "ENABLE" | "REVOKE_SESSIONS" | "REQUIRE_PASSWORD_RESET";

function formatDate(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "Never";
}

export default function PlatformUsersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const status = searchParams.get("status") ?? "";
  const role = searchParams.get("role") ?? "";
  const [dataMode, setDataMode] = useState<DataMode>("REAL");
  const [mfa, setMfa] = useState("");
  const [platformOnly, setPlatformOnly] = useState(false);
  const [minFailedLogins, setMinFailedLogins] = useState("");
  const [sort, setSort] = useState<"updated" | "last_login" | "name" | "failed_logins">("updated");
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkAction, setBulkAction] = useState<BulkAction>("REVOKE_SESSIONS");
  const [reason, setReason] = useState("Platform user security action");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const cursor = cursorStack[cursorStack.length - 1] ?? null;

  const users = usePlatformData(
    () => platformOperationsApi.usersV2({
      data_mode: dataMode,
      q,
      role: role || undefined,
      status: status === "active" || status === "disabled" ? status : undefined,
      mfa: mfa === "true" ? true : mfa === "false" ? false : undefined,
      min_failed_logins: minFailedLogins ? Math.max(0, Number(minFailedLogins) || 0) : undefined,
      platform_only: platformOnly || undefined,
      sort,
      limit: PAGE_SIZE,
      cursor,
    }),
    [dataMode, q, role, status, mfa, minFailedLogins, platformOnly, sort, cursor],
  );

  const loaded = (users.data?.items ?? []) as UserHubRow[];
  const total = Number(users.data?.total ?? 0);
  const nextCursor = (users.data?.next_cursor as string | null | undefined) ?? null;
  const activeCount = loaded.filter((user) => user.is_active).length;
  const platformUsers = loaded.filter((user) => user.is_superuser).length;
  const mfaCount = loaded.filter((user) => user.mfa_registered).length;
  const allLoadedSelected = loaded.length > 0 && loaded.every((user) => selected.has(user.id));
  const selectedLoadedCount = useMemo(() => loaded.filter((user) => selected.has(user.id)).length, [loaded, selected]);

  const resetCursor = () => {
    setCursorStack([null]);
    setSelected(new Set());
  };

  const updateFilters = (next: { q?: string; status?: string; role?: string }) => {
    const params = new URLSearchParams(searchParams);
    const nextQ = next.q ?? q;
    const nextStatus = next.status ?? status;
    const nextRole = next.role ?? role;
    if (nextQ.trim()) params.set("q", nextQ);
    else params.delete("q");
    if (nextStatus) params.set("status", nextStatus);
    else params.delete("status");
    if (nextRole) params.set("role", nextRole);
    else params.delete("role");
    setSearchParams(params, { replace: true });
    resetCursor();
  };

  const toggleUser = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleLoaded = () => {
    setSelected((current) => {
      const next = new Set(current);
      if (allLoadedSelected) loaded.forEach((user) => next.delete(user.id));
      else loaded.forEach((user) => next.add(user.id));
      return next;
    });
  };

  const runAction = async (action: BulkAction, userIds: string[]) => {
    if (!reason.trim()) {
      setActionError("A reason is required for privileged user actions.");
      return;
    }
    if (!userIds.length) {
      setActionError("Select at least one user.");
      return;
    }
    setNotice(null);
    setActionError(null);
    try {
      const result = await platformOperationsApi.usersBulk({ action, reason: reason.trim(), user_ids: userIds.slice(0, 200) });
      const completed = Number(result?.completed ?? result?.updated ?? userIds.length);
      setNotice(`${action.replaceAll("_", " ")} completed for ${completed} user${completed === 1 ? "" : "s"}.`);
      setSelected(new Set());
      await users.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const nextPage = () => {
    if (!nextCursor) return;
    setCursorStack((current) => [...current, nextCursor]);
    setSelected(new Set());
  };

  const previousPage = () => {
    setCursorStack((current) => current.length > 1 ? current.slice(0, -1) : current);
    setSelected(new Set());
  };

  return (
    <PlatformShell
      title="Global User Hub"
      subtitle="Cursor-based platform-wide account visibility with MFA/login risk filters and audited bounded bulk security actions."
      actions={<button className="platform-btn" onClick={users.reload}>Refresh directory</button>}
    >
      {users.error ? <ErrorState error={users.error} retry={users.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <p><StatusBadge value="SUCCEEDED" /> {notice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="Users matched" value={total} tone="blue" mark="US" />
        <MetricCard label="Active on page" value={activeCount} tone="green" mark="AC" />
        <MetricCard label="MFA on page" value={mfaCount} tone="purple" mark="MF" />
        <MetricCard label="Selected" value={selected.size} caption="Bulk limit 200" tone={selected.size ? "amber" : "blue"} mark="BL" />
      </section>

      <section className="platform-card">
        <div className="platform-section-title">
          <div><h2>Directory filters</h2><p>Filters are evaluated server-side before cursor pagination.</p></div>
          <StatusBadge value={`${dataMode} DATA`} />
        </div>
        <div className="platform-toolbar">
          <input placeholder="Search name, email or staff code" value={q} onChange={(event) => updateFilters({ q: event.target.value })} />
          <select value={status} onChange={(event) => updateFilters({ status: event.target.value })}><option value="">All account states</option><option value="active">Active</option><option value="disabled">Disabled</option></select>
          <input placeholder="Role filter" value={role} onChange={(event) => updateFilters({ role: event.target.value })} />
          <select value={mfa} onChange={(event) => { setMfa(event.target.value); resetCursor(); }}><option value="">Any MFA state</option><option value="true">MFA registered</option><option value="false">MFA missing</option></select>
          <input type="number" min="0" placeholder="Min failed logins" value={minFailedLogins} onChange={(event) => { setMinFailedLogins(event.target.value); resetCursor(); }} />
          <select value={sort} onChange={(event) => { setSort(event.target.value as typeof sort); resetCursor(); }}><option value="updated">Recently updated</option><option value="last_login">Last login</option><option value="name">Name</option><option value="failed_logins">Failed logins</option></select>
          <select value={dataMode} onChange={(event) => { setDataMode(event.target.value as DataMode); resetCursor(); }}><option value="REAL">Real tenants</option><option value="DEMO">Demo tenants</option></select>
          <label><input type="checkbox" checked={platformOnly} onChange={(event) => { setPlatformOnly(event.target.checked); resetCursor(); }} /> Platform users only</label>
        </div>
      </section>

      <section className="platform-card">
        <div className="platform-section-title">
          <div><h2>Bulk security actions</h2><p>Actions are audited server-side and accept at most 200 unique user IDs per request.</p></div>
          <StatusBadge value={`${selectedLoadedCount} SELECTED ON PAGE`} />
        </div>
        <div className="platform-toolbar">
          <select value={bulkAction} onChange={(event) => setBulkAction(event.target.value as BulkAction)}><option value="REVOKE_SESSIONS">Revoke sessions</option><option value="REQUIRE_PASSWORD_RESET">Require password reset</option><option value="DISABLE">Disable users</option><option value="ENABLE">Enable users</option></select>
          <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required reason for privileged actions" />
          <button className={`platform-btn ${bulkAction === "DISABLE" ? "danger" : "primary"}`} disabled={!selected.size || selected.size > 200} onClick={() => runAction(bulkAction, Array.from(selected))}>Run for {selected.size || 0} selected</button>
        </div>
      </section>

      <section className="platform-card">
        {loaded.length ? (
          <DataTable>
            <thead><tr><th><input aria-label="Select all loaded users" type="checkbox" checked={allLoadedSelected} onChange={toggleLoaded} /></th><th>User</th><th>Tenant</th><th>Role</th><th>MFA</th><th>Status</th><th>Last login</th><th>Failed logins</th><th>Actions</th></tr></thead>
            <tbody>{loaded.map((user) => (
              <tr key={user.id}>
                <td><input aria-label={`Select ${user.full_name || user.email}`} type="checkbox" checked={selected.has(user.id)} onChange={() => toggleUser(user.id)} /></td>
                <td><strong>{user.full_name || "Unnamed user"}</strong><br /><small>{user.email}</small>{user.staff_code ? <><br /><small>{user.staff_code}</small></> : null}</td>
                <td>{user.tenant_name || (user.is_superuser ? "Platform" : "Tenant unavailable")}</td>
                <td>{user.role || "—"}{user.is_superuser ? <><br /><StatusBadge value="PLATFORM" /></> : null}</td>
                <td><StatusBadge value={user.mfa_registered ? "REGISTERED" : "MISSING"} /></td>
                <td><StatusBadge value={user.is_active ? "ACTIVE" : "DISABLED"} />{user.locked_until ? <><br /><small>Locked until {formatDate(user.locked_until)}</small></> : null}{user.must_change_password ? <><br /><small>Password reset required</small></> : null}</td>
                <td>{formatDate(user.last_login_at)}</td>
                <td>{user.failed_login_count ?? 0}</td>
                <td><div className="platform-actions"><button className="platform-btn" onClick={() => runAction("REVOKE_SESSIONS", [user.id])}>Revoke</button><button className="platform-btn" onClick={() => runAction("REQUIRE_PASSWORD_RESET", [user.id])}>Reset</button>{user.is_active ? <button className="platform-btn danger" onClick={() => runAction("DISABLE", [user.id])}>Disable</button> : <button className="platform-btn" onClick={() => runAction("ENABLE", [user.id])}>Enable</button>}</div></td>
              </tr>
            ))}</tbody>
          </DataTable>
        ) : <EmptyState label="No users match the current server-side filters." />}
        <div className="platform-actions" style={{ marginTop: 12 }}>
          <button className="platform-btn" disabled={cursorStack.length <= 1} onClick={previousPage}>Previous</button>
          <span>Page {cursorStack.length} · {loaded.length} loaded · {total} matched</span>
          <button className="platform-btn" disabled={!nextCursor} onClick={nextPage}>Next</button>
          <span style={{ marginLeft: "auto" }}>Platform users on page: {platformUsers}</span>
        </div>
      </section>
    </PlatformShell>
  );
}
