import React, { useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Archive,
  BarChart3,
  CalendarRange,
  ClipboardList,
  Gauge,
  ListTree,
  ListChecks,
  TableProperties,
  Trash2,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { userHasQmsRolePermission } from "../../app/routeGuards";
import AuditPageShell, { type AuditShellNavItem } from "../../components/QMS/AuditPageShell";
import { getCachedUser, getContext } from "../../services/auth";
import {
  AUDIT_ASSURANCE_DESTINATIONS,
  auditAssuranceHref,
  isAuditAssuranceDestinationActive,
  type AuditAssuranceNavGroup,
  type AuditAssuranceNavId,
} from "../qms/routes/qmsRouteRegistry";
import "./quality-audits-workspace.css";
import "./qa-dark-contrast.css";

type Props = {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  toolbar?: React.ReactNode;
};

type WorkspaceNavItem = AuditShellNavItem & {
  group: AuditAssuranceNavGroup;
  permission: string;
};

const NAV_GROUPS: ReadonlyArray<{
  id: AuditAssuranceNavGroup;
  label: string;
  ariaLabel: string;
}> = [
  { id: "workspace", label: "Workspace", ariaLabel: "Assurance overview" },
  { id: "planning", label: "Planning", ariaLabel: "Audit programme" },
  { id: "execution", label: "Execution", ariaLabel: "Audits and controlled checklists" },
  { id: "follow-up", label: "Follow-up", ariaLabel: "Finding lifecycle and analysis" },
  { id: "records", label: "Records", ariaLabel: "Audit records" },
];

const DESTINATION_ICONS: Record<AuditAssuranceNavId, LucideIcon> = {
  dashboard: Gauge,
  programme: Workflow,
  planner: CalendarRange,
  scopes: ListTree,
  audits: ClipboardList,
  checklists: ListChecks,
  "findings-actions": TableProperties,
  "finding-intelligence": BarChart3,
  evidence: Archive,
  bin: Trash2,
};

const QualityAuditsSectionLayout: React.FC<Props> = ({ title, subtitle, children, toolbar }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const navigate = useNavigate();
  const location = useLocation();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";

  const qualityBase = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const auditsBase = `${qualityBase}/audits`;
  const calendarBase = `${qualityBase}/calendar`;
  const onCalendar = location.pathname.startsWith(calendarBase);

  const links = useMemo<WorkspaceNavItem[]>(() => {
    return AUDIT_ASSURANCE_DESTINATIONS
      .filter((destination) => userHasQmsRolePermission(currentUser, destination.permission))
      .map((destination) => ({
        id: destination.id,
        label: destination.label,
        shortLabel: destination.shortLabel,
        icon: DESTINATION_ICONS[destination.id],
        href: auditAssuranceHref(amoCode, destination),
        group: destination.group,
        permission: destination.permission,
        active: isAuditAssuranceDestinationActive(destination, location.pathname, amoCode),
      }));
  }, [amoCode, currentUser, location.pathname]);

  const activeId = links.find((link) => link.active)?.id ?? links[0]?.id ?? "dashboard";
  const calendarFocusMode = onCalendar;

  const renderNavButton = (link: WorkspaceNavItem) => {
    const Icon = link.icon;
    return (
      <button
        key={link.id}
        type="button"
        aria-current={link.active ? "page" : undefined}
        className={`qa-workspace-rail__tab qa-workspace-rail__tab--label-only${link.active ? " qa-workspace-rail__tab--active" : ""}`}
        onClick={() => navigate(link.href)}
      >
        <Icon size={17} aria-hidden />
        <span>
          <strong>{link.label}</strong>
        </span>
      </button>
    );
  };

  const renderRailGroup = ({ id, label, ariaLabel }: (typeof NAV_GROUPS)[number]) => {
    const groupLinks = links.filter((link) => link.group === id);
    if (!groupLinks.length) return null;
    return (
      <nav key={id} className="qa-workspace-rail__group" aria-label={ariaLabel}>
        <span className="qa-workspace-rail__group-label">{label}</span>
        {groupLinks.map(renderNavButton)}
      </nav>
    );
  };

  const mergedToolbar = toolbar ? <div className="qa-workspace-toolbar">{toolbar}</div> : undefined;

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={title}
      subtitle={subtitle}
      breadcrumbs={[
        { label: "QMS", onClick: () => navigate(qualityBase) },
        { label: "Audit Assurance", onClick: () => navigate(auditsBase) },
        { label: title },
      ]}
      toolbar={calendarFocusMode ? undefined : mergedToolbar}
      suppressHeader={calendarFocusMode}
    >
      {!calendarFocusMode ? (
        <label className="qa-workspace-mobile-tabs">
          <span>Assurance page</span>
          <select
            aria-label="Assurance page"
            value={activeId}
            onChange={(event) => {
              const next = links.find((link) => link.id === event.target.value);
              if (next) navigate(next.href);
            }}
          >
            {NAV_GROUPS.map((group) => {
              const groupLinks = links.filter((link) => link.group === group.id);
              return groupLinks.length ? (
                <optgroup key={group.id} label={group.label}>
                  {groupLinks.map((link) => (
                    <option key={link.id} value={link.id}>{link.label}</option>
                  ))}
                </optgroup>
              ) : null;
            })}
          </select>
        </label>
      ) : null}

      <div className={`qms-surface-root qa-workspace-shell${calendarFocusMode ? " qa-workspace-shell--calendar-focus" : ""}`}>
        {!calendarFocusMode ? (
          <aside className="qa-workspace-rail" aria-label="Audit Assurance pages">
            <div className="qa-workspace-rail__heading">
              <span>Audit Assurance</span>
            </div>
            {NAV_GROUPS.map(renderRailGroup)}
          </aside>
        ) : null}

        <section className="qa-workspace-main" data-assurance-workspace-section={activeId} aria-label="Current Audit Assurance workspace">
          {children}
        </section>
      </div>
    </AuditPageShell>
  );
};

export default QualityAuditsSectionLayout;
