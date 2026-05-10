import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { endSession, getCachedUser } from "../../../services/auth";
import "../../../styles/platform-control.css";

export const platformNav = [
  ["/platform/control", "Platform Control", "PC"],
  ["/platform/tenants", "Tenants & Institutions", "TI"],
  ["/platform/users", "Global User Hub", "UH"],
  ["/platform/billing", "Subscription & Billing", "BI"],
  ["/platform/analytics", "Platform Analytics", "AN"],
  ["/platform/security", "Security & Compliance", "SC"],
  ["/platform/integrations", "Integrations & API", "IA"],
  ["/platform/infrastructure", "System Infrastructure", "SI"],
] as const;

export const StatusBadge: React.FC<{ value?: unknown }> = ({ value }) => {
  const text = String(value ?? "UNKNOWN");
  const v = text.toUpperCase();
  const cls =
    v.includes("ACTIVE") || v.includes("HEALTHY") || v.includes("SUCCEEDED") || v === "OPEN"
      ? "ok"
      : v.includes("FAIL") || v.includes("CRITICAL") || v.includes("LOCK") || v.includes("ERROR") || v.includes("DENIED")
        ? "bad"
        : v.includes("WARN") || v.includes("PENDING") || v.includes("DEGRADED") || v.includes("TRIAL")
          ? "warn"
          : "neutral";
  return <span className={`platform-badge ${cls}`}>{text}</span>;
};

export const MetricCard: React.FC<{ label: string; value: React.ReactNode; caption?: React.ReactNode; tone?: "blue" | "green" | "amber" | "red" | "purple" }> = ({ label, value, caption, tone = "blue" }) => (
  <section className={`platform-card platform-metric platform-metric--${tone}`}>
    <div className="platform-metric__shine" />
    <div className="label">{label}</div>
    <div className="value">{value ?? "-"}</div>
    {caption ? <div className="caption">{caption}</div> : null}
  </section>
);

export const PlatformShell: React.FC<{ title: string; subtitle: string; actions?: React.ReactNode; children: React.ReactNode }> = ({ title, subtitle, actions, children }) => {
  const user = getCachedUser();
  const navigate = useNavigate();
  if (!user?.is_superuser) {
    return (
      <main className="platform-access-denied">
        <section className="platform-card">
          <h1>Platform access required</h1>
          <p>This console is available only to global platform superusers.</p>
          <button className="platform-btn primary" onClick={() => navigate("/login", { replace: true })}>Go to login</button>
        </section>
      </main>
    );
  }
  const initials = user.full_name?.split(/\s+/).slice(0, 2).map((part) => part[0]).join("") || user.email?.slice(0, 2)?.toUpperCase() || "SA";
  return (
    <div className="platform-shell">
      <aside className="platform-sidebar">
        <div className="platform-sidebar__brand">
          <span className="platform-brand-mark">AM</span>
          <span><strong>AMO SaaS</strong><small>Control Plane</small></span>
        </div>
        <nav className="platform-nav" aria-label="Platform navigation">
          {platformNav.map(([to, label, mark]) => (
            <NavLink key={to} to={to}>
              <span className="platform-nav__mark">{mark}</span>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="platform-sidebar__footer">
          <span className="platform-status-dot" />
          <span>Protected platform scope</span>
        </div>
      </aside>
      <main className="platform-main">
        <header className="platform-topbar">
          <div className="platform-title">
            <span className="platform-eyebrow">Superadmin console</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <div className="platform-actions">
            {actions}
            <div className="platform-profile-chip" title={user.email || "Platform user"}>
              <span>{initials}</span>
              <small>{user.email || "Platform user"}</small>
            </div>
            <button className="platform-btn" onClick={() => navigate("/login", { replace: true })}>Switch account</button>
            <button className="platform-btn danger" onClick={() => { endSession("manual"); navigate("/login", { replace: true }); }}>Sign out</button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
};

export const ErrorState: React.FC<{ error: unknown; retry?: () => void }> = ({ error, retry }) => (
  <div className="platform-error">
    <div>
      <strong>Unable to load this platform section.</strong>
      <p>{error instanceof Error ? error.message : String(error || "Unable to load data.")}</p>
    </div>
    {retry ? <button className="platform-btn" onClick={retry}>Retry</button> : null}
  </div>
);
export const EmptyState: React.FC<{ label: string }> = ({ label }) => <div className="platform-empty">{label}</div>;
export const DataTable: React.FC<{ children: React.ReactNode }> = ({ children }) => <div className="platform-table-wrap"><table className="platform-table">{children}</table></div>;
