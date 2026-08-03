import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { commercialApi, type PlatformDataMode } from "../../services/commercialControl";
import { platformApi, type PlatformUser } from "../../services/platformControl";
import { phase4Api } from "../../services/platformPhase4";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";
import "../../styles/platform-commercial-control.css";

const PAGE_SIZE = 50;

export default function PlatformUsersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const status = searchParams.get("status") ?? "";
  const tenantId = searchParams.get("tenant") ?? "";
  const dataMode = (searchParams.get("mode") === "DEMO" ? "DEMO" : "REAL") as PlatformDataMode;
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<PlatformUser | null>(null);
  const [reason, setReason] = useState("Platform user security action");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const users = usePlatformData(
    () => phase4Api.users({ data_mode: dataMode, q, status, tenant_id: tenantId || undefined, limit: PAGE_SIZE, offset }),
    [dataMode, q, status, tenantId, offset],
    { pollMs: 20_000 },
  );
  const tenants = usePlatformData(
    () => platformApi.tenants({ data_mode: dataMode, limit: 200 }),
    [dataMode],
    { pollMs: 30_000 },
  );

  const setFilters = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setOffset(0);
    setSearchParams(next, { replace: true });
  };

  const act = async (user: PlatformUser, action: "enable" | "disable" | "revoke-sessions" | "force-password-reset") => {
    setNotice(null);
    setActionError(null);
    try {
      if (action === "force-password-reset") {
        await commercialApi.forcePasswordReset(user.id, reason);
      } else {
        await platformApi.userAction(user.id, action, reason);
      }
      setNotice(`User action completed: ${action.replaceAll("-", " ")}.`);
      users.reload();
      setSelected((current) => current?.id === user.id ? { ...current, is_active: action === "enable" ? true : action === "disable" ? false : current.is_active } : current);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const loaded = users.data?.items ?? [];
  const activeCount = loaded.filter((user) => user.is_active).length;
  const platformUsers = loaded.filter((user) => user.is_superuser).length;
  const lockedSignals = loaded.filter((user) => Number(user.failed_login_count || 0) > 0).length;
  const tenantOptions = tenants.data?.items || [];
  const total = users.data?.total || 0;
  const selectedTenantName = useMemo(() => tenantOptions.find((tenant) => tenant.id === tenantId)?.name, [tenantId, tenantOptions]);

  return (
    <PlatformShell
      title="Global User Hub"
      subtitle="Accounts, access and session controls for the selected environment."
      actions={<><div className="platform-mode-switch">{(["REAL", "DEMO"] as PlatformDataMode[]).map((mode) => <button key={mode} className={dataMode === mode ? "active" : ""} onClick={() => setFilters({ mode, tenant: null })}>{mode}</button>)}</div><button className="platform-btn" onClick={users.reload}>Refresh</button></>}
    >
      {users.error ? <ErrorState error={users.error} retry={users.reload} /> : null}
      {tenants.error ? <ErrorState error={tenants.error} retry={tenants.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <div className="platform-inline-success">{notice}</div> : null}

      <section className="platform-grid">
        <MetricCard label="Users matched" value={total} caption={selectedTenantName || `${dataMode} directory`} tone="blue" mark="US" />
        <MetricCard label="Active loaded" value={activeCount} tone="green" mark="AC" />
        <MetricCard label="Platform users" value={platformUsers} tone="purple" mark="PA" />
        <MetricCard label="Failed-login signals" value={lockedSignals} tone={lockedSignals ? "amber" : "green"} mark="FL" />
      </section>

      <section className="platform-commercial-layout">
        <div className="platform-card">
          <div className="platform-section-title"><div><h2>User directory</h2><p>Only {dataMode.toLowerCase()} tenant accounts are shown.</p></div><StatusBadge value={dataMode} /></div>
          <div className="platform-toolbar">
            <input placeholder="Search name or email" value={q} onChange={(event) => setFilters({ q: event.target.value || null })} />
            <select value={tenantId} onChange={(event) => setFilters({ tenant: event.target.value || null })}><option value="">All {dataMode.toLowerCase()} tenants</option>{tenantOptions.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select>
            <select value={status} onChange={(event) => setFilters({ status: event.target.value || null })}><option value="">All account states</option><option value="active">Active</option><option value="disabled">Disabled</option></select>
          </div>
          {loaded.length ? <DataTable><thead><tr><th>User</th><th>Tenant</th><th>Role</th><th>Status</th><th>Last login</th><th>Failed</th><th>Open</th></tr></thead><tbody>{loaded.map((user) => <tr key={user.id}><td><strong>{user.full_name}</strong><br /><small>{user.email}</small></td><td>{user.tenant_name || user.amo_id || "Platform"}</td><td>{user.role}</td><td><StatusBadge value={user.is_active ? "ACTIVE" : "DISABLED"} /></td><td>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}</td><td>{user.failed_login_count ?? 0}</td><td><button className="platform-btn" onClick={() => setSelected(user)}>Manage</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No users match the filters." />}
          <div className="platform-actions" style={{ marginTop: 12 }}><button className="platform-btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><span>{total ? offset + 1 : 0}-{Math.min(offset + PAGE_SIZE, total)} of {total}</span><button className="platform-btn" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></div>
        </div>

        <aside className="platform-card platform-commercial-sidebar">
          <div className="platform-section-title"><div><h2>Account control</h2><p>A reason is required.</p></div></div>
          {selected ? <div className="platform-stack-form"><div className="platform-subtle-panel"><strong>{selected.full_name}</strong><br /><small>{selected.email}</small><p>{selected.tenant_name || selected.amo_id || "Platform account"} · {selected.role}</p><StatusBadge value={selected.is_active ? "ACTIVE" : "DISABLED"} /></div><label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label><button className="platform-btn" onClick={() => act(selected, "revoke-sessions")}>Revoke all sessions</button><button className="platform-btn" onClick={() => act(selected, "force-password-reset")}>Force password reset</button>{selected.is_active ? <button className="platform-btn danger" data-confirm-message="Disable this account and revoke its active access?" onClick={() => act(selected, "disable")}>Disable account</button> : <button className="platform-btn primary" onClick={() => act(selected, "enable")}>Enable account</button>}</div> : <EmptyState label="Select a user to open account controls." />}
        </aside>
      </section>
    </PlatformShell>
  );
}
