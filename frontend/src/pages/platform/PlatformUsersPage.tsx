import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { platformApi, type PlatformUser } from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

export default function PlatformUsersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState(() => searchParams.get("q") ?? "");
  const [status, setStatus] = useState(() => searchParams.get("status") ?? "");
  const [reason, setReason] = useState("Platform user security action");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const users = usePlatformData(() => platformApi.users({ q, status, limit: 100 }), [q, status], { pollMs: 15_000 });

  useEffect(() => {
    const nextQ = searchParams.get("q") ?? "";
    const nextStatus = searchParams.get("status") ?? "";
    if (nextQ !== q) setQ(nextQ);
    if (nextStatus !== status) setStatus(nextStatus);
  // q and status deliberately participate so browser navigation remains authoritative.
  }, [q, searchParams, status]);

  const updateFilters = (nextQ: string, nextStatus: string) => {
    setQ(nextQ);
    setStatus(nextStatus);
    const next = new URLSearchParams(searchParams);
    if (nextQ.trim()) next.set("q", nextQ);
    else next.delete("q");
    if (nextStatus) next.set("status", nextStatus);
    else next.delete("status");
    setSearchParams(next, { replace: true });
  };

  const act = async (id: string, action: "enable" | "disable" | "revoke-sessions" | "force-password-reset") => {
    setNotice(null);
    setActionError(null);
    try {
      await platformApi.userAction(id, action, reason);
      setNotice(`User action completed: ${action.replaceAll("-", " ")}.`);
      users.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const loaded = users.data?.items ?? [];
  const activeCount = loaded.filter((user) => user.is_active).length;
  const platformUsers = loaded.filter((user) => user.is_superuser).length;

  return (
    <PlatformShell
      title="Global User Hub"
      subtitle="Platform-wide account visibility, role state, failed-login indicators, password controls and immediate session revocation."
      actions={<button className="platform-btn" onClick={users.reload}>Refresh directory</button>}
    >
      {users.error ? <ErrorState error={users.error} retry={users.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <p><StatusBadge value="SUCCEEDED" /> {notice}</p> : null}
      <section className="platform-grid">
        <MetricCard label="Users matched" value={users.data?.total ?? 0} tone="blue" mark="US" />
        <MetricCard label="Active loaded" value={activeCount} tone="green" mark="AC" />
        <MetricCard label="Platform users" value={platformUsers} tone="purple" mark="PA" />
        <MetricCard label="Session control" value="Immediate" caption="Uses token_revoked_at" tone="amber" mark="SR" />
      </section>
      <section className="platform-card">
        <div className="platform-toolbar">
          <input placeholder="Search name or email" value={q} onChange={(event) => updateFilters(event.target.value, status)} />
          <select value={status} onChange={(event) => updateFilters(q, event.target.value)}><option value="">All account states</option><option value="active">Active</option><option value="disabled">Disabled</option></select>
          <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Required reason for privileged actions" />
        </div>
        {loaded.length ? (
          <DataTable>
            <thead><tr><th>User</th><th>Tenant</th><th>Role</th><th>Status</th><th>Last login</th><th>Failed logins</th><th>Actions</th></tr></thead>
            <tbody>{loaded.map((user: PlatformUser) => (
              <tr key={user.id}>
                <td><strong>{user.full_name}</strong><br /><small>{user.email}</small></td>
                <td>{user.tenant_name || user.amo_id || "Platform"}</td>
                <td>{user.role}</td>
                <td><StatusBadge value={user.is_active ? "ACTIVE" : "DISABLED"} /></td>
                <td>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}</td>
                <td>{user.failed_login_count ?? 0}</td>
                <td><div className="platform-actions"><button className="platform-btn" onClick={() => act(user.id, "revoke-sessions")}>Revoke sessions</button><button className="platform-btn" onClick={() => act(user.id, "force-password-reset")}>Force reset</button>{user.is_active ? <button className="platform-btn danger" onClick={() => act(user.id, "disable")}>Disable</button> : <button className="platform-btn" onClick={() => act(user.id, "enable")}>Enable</button>}</div></td>
              </tr>
            ))}</tbody>
          </DataTable>
        ) : <EmptyState label="No users match the current filters." />}
      </section>
    </PlatformShell>
  );
}
