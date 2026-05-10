// src/layouts/QmsShell.tsx
import React from "react";
import { NavLink, useLocation, useParams } from "react-router-dom";
import { getCachedUser } from "../services/auth";
import { isPlatformSuperuser } from "../app/routeGuards";
import "../styles/qms-canonical.css";

type QmsShellProps = {
  children: React.ReactNode;
};

type QmsNavItem = {
  label: string;
  path: string;
  permission: string;
  exact?: boolean;
};

const rolePermissions: Record<string, string[]> = {
  // Platform superusers are intentionally excluded from tenant QMS navigation.
  AMO_ADMIN: ["qms.*"],
  QUALITY_MANAGER: ["qms.*"],
  QUALITY_INSPECTOR: [
    "qms.dashboard.view",
    "qms.inbox.view",
    "qms.calendar.view",
    "qms.audit.view",
    "qms.finding.view",
    "qms.car.view",
    "qms.document.view",
    "qms.evidence.view",
  ],
  AUDITOR: [
    "qms.dashboard.view",
    "qms.inbox.view",
    "qms.calendar.view",
    "qms.audit.view",
    "qms.finding.view",
    "qms.car.view",
    "qms.document.view",
    "qms.evidence.view",
  ],
  VIEW_ONLY: [
    "qms.dashboard.view",
    "qms.inbox.view",
    "qms.calendar.view",
    "qms.audit.view",
    "qms.finding.view",
    "qms.car.view",
    "qms.document.view",
    "qms.training.view",
    "qms.supplier.view",
    "qms.equipment.view",
    "qms.risk.view",
    "qms.change.view",
    "qms.management_review.view",
    "qms.reports.view",
    "qms.evidence.view",
  ],
};

function permissionMatches(grant: string, permission: string): boolean {
  if (grant === "*") return true;
  if (grant.endsWith(".*")) return permission.startsWith(grant.slice(0, -1));
  return grant === permission;
}

function canView(permission: string): boolean {
  const user = getCachedUser();
  if (!user) return false;
  if (isPlatformSuperuser()) return false;
  if (!user.amo_id) return false;
  if (user.is_amo_admin && permission.startsWith("qms.")) return true;
  const grants = rolePermissions[user.role] || [];
  return grants.some((grant) => permissionMatches(grant, permission));
}

const groups: Array<{ heading: string; items: QmsNavItem[] }> = [
  {
    heading: "Command",
    items: [
      { label: "QMS Cockpit", path: "", permission: "qms.dashboard.view", exact: true },
      { label: "My QMS Work", path: "inbox", permission: "qms.inbox.view" },
      { label: "Calendar", path: "calendar", permission: "qms.calendar.view" },
    ],
  },
  {
    heading: "System & Control",
    items: [
      { label: "System & Processes", path: "system", permission: "qms.risk.view" },
      { label: "Controlled Documents", path: "documents", permission: "qms.document.view" },
      { label: "Audits", path: "audits", permission: "qms.audit.view" },
      { label: "Findings", path: "findings", permission: "qms.finding.view" },
      { label: "CAR / CAPA", path: "cars", permission: "qms.car.view" },
      { label: "Risk & Opportunities", path: "risk", permission: "qms.risk.view" },
      { label: "Change Control", path: "change-control", permission: "qms.change.view" },
    ],
  },
  {
    heading: "Assurance",
    items: [
      { label: "Training & Competence", path: "training-competence", permission: "qms.training.view" },
      { label: "Suppliers", path: "suppliers", permission: "qms.supplier.view" },
      { label: "Equipment & Calibration", path: "equipment-calibration", permission: "qms.equipment.view" },
      { label: "External Interface", path: "external-interface", permission: "qms.finding.view" },
      { label: "Management Review", path: "management-review", permission: "qms.management_review.view" },
    ],
  },
  {
    heading: "Archive & Admin",
    items: [
      { label: "Reports & Analytics", path: "reports", permission: "qms.reports.view" },
      { label: "Evidence Vault", path: "evidence-vault", permission: "qms.evidence.view" },
      { label: "QMS Settings", path: "settings", permission: "qms.settings.view" },
    ],
  },
];

export default function QmsShell({ children }: QmsShellProps): React.ReactElement {
  const { amoCode = "" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const base = `/maintenance/${amoCode}/qms`;
  const crumbs = location.pathname
    .replace(base, "")
    .split("/")
    .filter(Boolean)
    .map((part) => part.replace(/-/g, " "));

  return (
    <div className="qms-shell" data-canonical-route={base}>
      <aside className="qms-shell__sidebar" aria-label="QMS navigation">
        <div className="qms-shell__brand">
          <span className="qms-shell__eyebrow">Canonical QMS</span>
          <strong>{amoCode || "AMO"}</strong>
        </div>
        {groups.map((group) => {
          const visibleItems = group.items.filter((item) => canView(item.permission));
          if (!visibleItems.length) return null;
          return (
            <section key={group.heading} className="qms-shell__group">
              <h2>{group.heading}</h2>
              {visibleItems.map((item) => {
                const to = item.path ? `${base}/${item.path}` : base;
                return (
                  <NavLink
                    key={item.path || "cockpit"}
                    to={to}
                    end={item.exact}
                    className={({ isActive }) => `qms-shell__link${isActive ? " is-active" : ""}`}
                  >
                    {item.label}
                  </NavLink>
                );
              })}
            </section>
          );
        })}
      </aside>
      <main className="qms-shell__main">
        <nav className="qms-shell__breadcrumbs" aria-label="Breadcrumb">
          <NavLink to={base}>QMS</NavLink>
          {crumbs.map((crumb, index) => (
            <span key={`${crumb}-${index}`}>/ {crumb}</span>
          ))}
        </nav>
        {children}
      </main>
    </div>
  );
}
