import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, useLocation, useParams } from "react-router-dom";
import {
  Building2,
  CalendarDays,
  ClipboardCheck,
  Gauge,
  GraduationCap,
  Settings2,
  UsersRound,
} from "lucide-react";

import DepartmentLayout from "../../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../../services/auth";
import { getCurrentWorkforcePermissions } from "../../../services/workforce";
import { canViewFeature, type ModuleFeature } from "../../../utils/roleAccess";
import "../../../styles/rostering-workforce.css";
import "../../../styles/rostering-workforce-layout.css";

type Props = {
  title: string;
  eyebrow: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
  context?: ReactNode;
};

type NavItem = {
  suffix: string;
  label: string;
  icon: typeof Gauge;
  feature?: ModuleFeature;
  requiredPermissions?: string[];
};

const NAV: NavItem[] = [
  { suffix: "dashboard", label: "Command", icon: Gauge, feature: "rostering.dashboard" },
  { suffix: "calendar", label: "Planner", icon: CalendarDays, feature: "rostering.calendar" },
  { suffix: "planning-board", label: "Operations", icon: UsersRound, feature: "rostering.planning-board" },
  { suffix: "training-impact", label: "Compliance", icon: GraduationCap, feature: "rostering.training-impact" },
  { suffix: "my-roster", label: "My duty", icon: ClipboardCheck, feature: "rostering.my-roster" },
  { suffix: "settings?section=workforce", label: "Workforce", icon: Building2, requiredPermissions: ["workforce.view_sensitive"] },
  {
    suffix: "settings?section=overview",
    label: "Setup",
    icon: Settings2,
    requiredPermissions: ["roster.create", "roster.manage_shift_templates", "roster.manage_patterns", "roster.manage_rules"],
  },
];

export function RosterShell({ title, eyebrow, description, actions, children, context }: Props) {
  const { amoCode = "UNKNOWN" } = useParams();
  const location = useLocation();
  const user = getCachedUser();
  const permissionsQuery = useQuery({
    queryKey: ["rostering", "shell", "workforce-permissions"],
    queryFn: getCurrentWorkforcePermissions,
    staleTime: 5 * 60_000,
    networkMode: "offlineFirst",
  });
  const livePermissions = permissionsQuery.data?.permissions || [];
  const visibleNav = NAV.filter((item) => {
    if (item.requiredPermissions) {
      return item.requiredPermissions.some((permission) => livePermissions.includes(permission));
    }
    return item.feature ? canViewFeature(user, item.feature) : false;
  });
  const root = `/maintenance/${encodeURIComponent(amoCode)}/rostering`;
  const selectedSection = new URLSearchParams(location.search).get("section");

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="rostering">
      <div className="wr-page">
        <header className="wr-header">
          <div className="wr-header__copy">
            <span className="wr-eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          {actions ? <div className="wr-header__actions">{actions}</div> : null}
        </header>

        <nav className="wr-tabs" aria-label="Duty rostering sections">
          {visibleNav.map(({ suffix, label, icon: Icon }) => (
            <NavLink
              key={`${suffix}:${label}`}
              to={`${root}/${suffix}`}
              className={({ isActive }) => {
                const workforceActive = label === "Workforce" && location.pathname.endsWith("/rostering/settings") && selectedSection === "workforce";
                const setupActive = label === "Setup" && location.pathname.endsWith("/rostering/settings") && selectedSection !== "workforce";
                const active = label === "Workforce" ? workforceActive : label === "Setup" ? setupActive : isActive;
                return `wr-tab${active ? " wr-tab--active" : ""}`;
              }}
            >
              <Icon aria-hidden="true" size={16} strokeWidth={1.9} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {context ? <div className="wr-context">{context}</div> : null}

        <main className="wr-main wr-main--enter">{children}</main>
      </div>
    </DepartmentLayout>
  );
}

export function RosterLoading({ label = "Loading duty data…" }: { label?: string }) {
  return (
    <div className="wr-state" role="status" aria-live="polite">
      <span className="wr-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function RosterError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="wr-state wr-state--error" role="alert">
      <div>
        <strong>Could not load this workspace</strong>
        <p>{message}</p>
      </div>
      {onRetry ? <button className="wr-button wr-button--secondary" type="button" onClick={onRetry}>Retry</button> : null}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="wr-empty">
      <strong>{title}</strong>
      <p>{description}</p>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

export function MetricCard({ label, value, detail, tone = "neutral" }: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "neutral" | "good" | "warning" | "danger" | "info";
}) {
  return (
    <article className={`wr-metric wr-tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}

export function StatusPill({ value, tone }: { value: string; tone?: string }) {
  const normalized = value.toLowerCase().replace(/_/g, "-");
  return <span className={`wr-pill wr-pill--${tone || normalized}`}>{value.replace(/_/g, " ")}</span>;
}
