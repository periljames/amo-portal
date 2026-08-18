import type { ReactNode } from "react";
import { Link, NavLink, useLocation, useParams } from "react-router-dom";
import {
  Building2,
  CalendarDays,
  CircleHelp,
  ClipboardCheck,
  Download,
  Gauge,
  MoreHorizontal,
  Settings2,
  ShieldCheck,
  UsersRound,
} from "lucide-react";

import DepartmentLayout from "../../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../../services/auth";
import { canViewFeature, type ModuleFeature } from "../../../utils/roleAccess";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import "../../../styles/rostering-workforce.css";
import "../../../styles/rostering-workforce-layout.css";
import "./roster-shell-ux.css";

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

const PRIMARY_NAV: NavItem[] = [
  { suffix: "dashboard", label: "Command", icon: Gauge, feature: "rostering.dashboard" },
  { suffix: "calendar", label: "Planner", icon: CalendarDays, feature: "rostering.calendar" },
  { suffix: "settings?section=workforce", label: "Workforce", icon: Building2, requiredPermissions: ["workforce.view_sensitive"] },
  { suffix: "my-roster", label: "My duty", icon: ClipboardCheck, feature: "rostering.my-roster" },
];

const MORE_NAV: NavItem[] = [
  { suffix: "planning-board", label: "Operations", icon: UsersRound, feature: "rostering.planning-board" },
  { suffix: "reports", label: "Reports", icon: Download, feature: "rostering.reports" },
  { suffix: "training-impact", label: "Readiness", icon: ShieldCheck, feature: "rostering.training-impact" },
  {
    suffix: "settings?section=start",
    label: "Setup",
    icon: Settings2,
    requiredPermissions: ["roster.create", "roster.manage_shift_templates", "roster.manage_patterns", "roster.manage_rules"],
  },
];

export function RosterShell({ title, eyebrow, description, actions, children, context }: Props) {
  const { amoCode = "UNKNOWN" } = useParams();
  const location = useLocation();
  const user = getCachedUser();
  const permissionsQuery = useWorkforcePermissions();
  const livePermissions = permissionsQuery.isSuccess ? permissionsQuery.data.permissions : [];
  const root = `/maintenance/${encodeURIComponent(amoCode)}/rostering`;
  const selectedSection = new URLSearchParams(location.search).get("section");

  const canSee = (item: NavItem) => {
    if (item.requiredPermissions) {
      return item.requiredPermissions.some((permission) => livePermissions.includes(permission));
    }
    return item.feature ? canViewFeature(user, item.feature) : false;
  };

  const visiblePrimary = PRIMARY_NAV.filter(canSee);
  const visibleMore = MORE_NAV.filter(canSee);
  const isSpecialActive = (item: NavItem) => {
    if (item.label === "Workforce") {
      return location.pathname.endsWith("/rostering/settings") && selectedSection === "workforce";
    }
    if (item.label === "Setup") {
      return location.pathname.endsWith("/rostering/settings") && selectedSection !== "workforce";
    }
    return location.pathname.endsWith(`/rostering/${item.suffix.split("?", 1)[0]}`);
  };
  const moreActive = visibleMore.some(isSpecialActive);

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="rostering">
      <div className="wr-page">
        <header className="wr-header">
          <div className="wr-header__copy">
            <h1>{title}</h1>
            <span className="wr-header__context">{eyebrow}</span>
          </div>
          <div className="wr-header__actions">
            <details className="wr-header-help">
              <summary aria-label={`About ${title}`} title={`About ${title}`}><CircleHelp size={17} /></summary>
              <p>{description}</p>
            </details>
            {actions}
          </div>
        </header>

        <nav className="wr-tabs" aria-label="Duty rostering sections">
          {visiblePrimary.map(({ suffix, label, icon: Icon }) => (
            <NavLink
              key={`${suffix}:${label}`}
              to={`${root}/${suffix}`}
              className={({ isActive }) => {
                const active = label === "Workforce" ? isSpecialActive({ suffix, label, icon: Icon }) : isActive;
                return `wr-tab${active ? " wr-tab--active" : ""}`;
              }}
            >
              <Icon aria-hidden="true" size={16} strokeWidth={1.9} />
              <span>{label}</span>
            </NavLink>
          ))}
          {visibleMore.length ? (
            <details className="wr-roster-more">
              <summary className={`wr-tab${moreActive ? " wr-tab--active" : ""}`} aria-label="More rostering sections">
                <MoreHorizontal aria-hidden="true" size={17} strokeWidth={1.9} />
                <span>More</span>
              </summary>
              <div className="wr-roster-more__menu">
                {visibleMore.map(({ suffix, label, icon: Icon }) => (
                  <Link
                    key={`${suffix}:${label}`}
                    to={`${root}/${suffix}`}
                    className={isSpecialActive({ suffix, label, icon: Icon }) ? "is-active" : ""}
                  >
                    <Icon aria-hidden="true" size={16} strokeWidth={1.9} />
                    <span>{label}</span>
                  </Link>
                ))}
              </div>
            </details>
          ) : null}
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

export function RosterError({ title = "Could not load this workspace", message, onRetry }: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="wr-state wr-state--error" role="alert">
      <div>
        <strong>{title}</strong>
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
