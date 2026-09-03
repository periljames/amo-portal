import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  CalendarDays,
  ClipboardList,
  Files,
  Gauge,
  ListChecks,
  TableProperties,
  Trash2,
  Workflow,
} from "lucide-react";
import AuditPageShell, { type AuditShellNavItem } from "../../components/QMS/AuditPageShell";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import Drawer from "../../components/shared/Drawer";
import { getContext } from "../../services/auth";
import "./quality-audits-workspace.css";
import "./qa-dark-contrast.css";

const OPEN_ASSURANCE_TOOLS_EVENT = "qa:open-assurance-tools";

type Props = {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  toolbar?: React.ReactNode;
};

type DrawerTab = "actions" | "lifecycle";

type WorkspaceNavItem = AuditShellNavItem & {
  group: "overview" | "plan" | "registers" | "tools";
};

/** Canonical AA local IA — peers, not Plan→segment nesting. */
const AA_CANONICAL_PRIMARY = ["dashboard", "programme", "calendar", "audits", "findings-actions"] as const;

const QualityAuditsSectionLayout: React.FC<Props> = ({ title, subtitle, children, toolbar }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const location = useLocation();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("actions");

  const auditsBase = `/maintenance/${amoCode}/quality/audits`;
  const calendarBase = `/maintenance/${amoCode}/quality/calendar`;
  const programmeHref = `${auditsBase}/program`;
  const calendarHref = `${calendarBase}/week`;
  const onProgramme = location.pathname.startsWith(`${auditsBase}/program`);
  const onCalendar = location.pathname.startsWith(calendarBase);
  const programmeFocusMode = onProgramme;

  const links = useMemo<WorkspaceNavItem[]>(
    () => [
      {
        id: "dashboard",
        label: "Overview",
        shortLabel: "Home",
        icon: Gauge,
        href: `${auditsBase}/dashboard`,
        group: "overview",
        active:
          location.pathname === auditsBase ||
          location.pathname === `${auditsBase}/dashboard`,
      },
      {
        id: "programme",
        label: "Programme",
        shortLabel: "Programme",
        icon: Workflow,
        href: programmeHref,
        group: "plan",
        active: onProgramme,
      },
      {
        id: "calendar",
        label: "Calendar",
        shortLabel: "Calendar",
        icon: CalendarDays,
        href: calendarHref,
        group: "plan",
        active: onCalendar,
      },
      {
        // Audits-first register; occurrence stage routes keep Audits highlighted.
        id: "audits",
        label: "Audits",
        shortLabel: "Audits",
        icon: ClipboardList,
        href: `${auditsBase}/workspace`,
        group: "registers",
        active:
          location.pathname === `${auditsBase}/workspace` ||
          /\/quality\/audits\/[^/]+\/(setup|prepare|live|closing|follow-up|archive)(?:\/|$)/.test(
            location.pathname,
          ),
      },
      {
        id: "findings-actions",
        label: "Findings & Actions",
        shortLabel: "Findings",
        icon: TableProperties,
        href: `${auditsBase}/register?tab=findings`,
        group: "registers",
        active:
          location.pathname === `${auditsBase}/register` ||
          location.pathname.startsWith(`/maintenance/${amoCode}/quality/findings/`),
      },
      {
        id: "checklists",
        label: "Checklists",
        shortLabel: "Checks",
        icon: ListChecks,
        href: `${auditsBase}/checklists`,
        group: "tools",
        active: location.pathname === `${auditsBase}/checklists`,
      },
      {
        id: "evidence-library",
        label: "Evidence vault",
        shortLabel: "Evidence",
        icon: Files,
        href: `/maintenance/${amoCode}/quality/evidence-vault`,
        group: "tools",
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/evidence-vault`),
      },
      {
        id: "create-run",
        label: "Calendar scheduling",
        shortLabel: "Sched.",
        icon: CalendarDays,
        // Demoted tool entry — Calendar week is the sole primary scheduler.
        href: calendarHref,
        group: "tools",
        active:
          location.pathname === `${auditsBase}/new` ||
          location.pathname === `${auditsBase}/plan` ||
          location.pathname === `${auditsBase}/schedule` ||
          location.pathname.startsWith(`${auditsBase}/schedules/`),
      },
      {
        id: "bin",
        label: "Recycle bin",
        shortLabel: "Bin",
        icon: Trash2,
        href: `${auditsBase}/bin`,
        group: "tools",
        active: location.pathname === `${auditsBase}/bin`,
      },
    ],
    [amoCode, auditsBase, calendarHref, location.pathname, onCalendar, onProgramme, programmeHref],
  );

  const primaryLinks = links.filter((link) =>
    (AA_CANONICAL_PRIMARY as readonly string[]).includes(link.id),
  );
  const toolLinks = links.filter((link) => link.group === "tools");
  const toolsOpen = toolLinks.some((link) => link.active);
  const activeId = links.find((link) => link.active)?.id ?? "dashboard";
  // Calendar already has Quality workspace tabs (Calendar selected). Hide the
  // duplicate AA icon rail so headers do not compete for the same navigation job.
  const calendarFocusMode = onCalendar;

  const openDrawer = (tab: DrawerTab = "actions") => {
    setDrawerTab(tab);
    setDrawerOpen(true);
  };

  useEffect(() => {
    const onOpenTools = () => openDrawer("actions");
    window.addEventListener(OPEN_ASSURANCE_TOOLS_EVENT, onOpenTools);
    return () => window.removeEventListener(OPEN_ASSURANCE_TOOLS_EVENT, onOpenTools);
  }, []);

  const workflowActions = [
    {
      title: "Open Programme",
      detail: "Coverage, universe and readiness.",
      href: programmeHref,
      icon: Workflow,
    },
    {
      title: "Open Calendar",
      detail: "Dated audits on the Quality planner.",
      href: calendarHref,
      icon: CalendarDays,
    },
    {
      title: "Browse audits",
      detail: "Planned and in-progress audit records.",
      href: `${auditsBase}/workspace`,
      icon: ClipboardList,
    },
    {
      title: "Findings & actions",
      detail: "Findings register and linked CARs.",
      href: `${auditsBase}/register?tab=findings`,
      icon: TableProperties,
    },
    {
      title: "Corrective actions",
      detail: "CAR closeout linked to audit findings.",
      href: `${auditsBase}/register?tab=cars`,
      icon: ListChecks,
    },
    {
      title: "Evidence vault",
      detail: "Objective evidence and retained records.",
      href: `/maintenance/${amoCode}/quality/evidence-vault`,
      icon: Files,
    },
  ];

  const renderNavButton = (link: WorkspaceNavItem, compact = false) => {
    const Icon = link.icon;
    if (compact) {
      return (
        <button
          key={link.id}
          type="button"
          role="tab"
          aria-selected={link.active}
          aria-label={link.label}
          title={link.label}
          className={`qa-workspace-rail__tab qa-workspace-rail__tab--icon${link.active ? " qa-workspace-rail__tab--active" : ""}`}
          onClick={() => navigate(link.href)}
        >
          <Icon size={17} aria-hidden />
        </button>
      );
    }
    return (
      <button
        key={link.id}
        type="button"
        role="tab"
        aria-selected={link.active}
        className={`qa-workspace-rail__tab qa-workspace-rail__tab--label-only${link.active ? " qa-workspace-rail__tab--active" : ""}`}
        onClick={() => navigate(link.href)}
      >
        <Icon size={17} />
        <span>
          <strong>{link.label}</strong>
        </span>
      </button>
    );
  };

  const renderRailGroup = (label: string, group: WorkspaceNavItem["group"], ariaLabel: string) => (
    <div className="qa-workspace-rail__group" role="tablist" aria-label={ariaLabel} aria-orientation="vertical">
      <span className="qa-workspace-rail__group-label">{label}</span>
      {links.filter((link) => link.group === group).map((link) => renderNavButton(link))}
    </div>
  );

  const mergedToolbar = toolbar ? <div className="qa-workspace-toolbar">{toolbar}</div> : undefined;

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={title}
      subtitle={subtitle}
      breadcrumbs={[
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/quality`) },
        { label: "Audit Assurance", onClick: () => navigate(auditsBase) },
        { label: title },
      ]}
      toolbar={calendarFocusMode ? undefined : mergedToolbar}
      suppressHeader={calendarFocusMode}
      onOverflowAction={calendarFocusMode || programmeFocusMode ? undefined : () => openDrawer("actions")}
      overflowActionLabel="Open Audit Assurance tools"
    >
      {!calendarFocusMode && !programmeFocusMode ? (
      <div className="qa-workspace-mobile-tabs" aria-label="Audit Assurance navigation">
        <ResponsiveSegmentedControl
          label="Audit Assurance"
          value={activeId}
          options={primaryLinks.map((link) => ({
            value: link.id,
            label: link.label,
            shortLabel: link.shortLabel,
            icon: link.icon,
            ariaLabel: link.label,
          }))}
          onChange={(value: string) => {
            const next = links.find((link) => link.id === value);
            if (next) navigate(next.href);
          }}
          compactIconsOnMobile
        />
      </div>
      ) : null}

      <div className={`qms-surface-root qa-workspace-shell${calendarFocusMode ? " qa-workspace-shell--planner qa-workspace-shell--calendar-focus" : ""}`}>
        {!calendarFocusMode ? (
          <aside className="qa-workspace-rail" aria-label="Audit Assurance sections">
            <div className="qa-workspace-rail__heading">
              <span>Audit Assurance</span>
            </div>
            {renderRailGroup("Workspace", "overview", "Overview")}
            {renderRailGroup("Planning", "plan", "Programme and calendar")}
            {renderRailGroup("Work", "registers", "Audits and findings")}
            <details className="qa-workspace-rail__tools" open={toolsOpen}>
              <summary className="qa-workspace-rail__tools-summary">Tools</summary>
              <div className="qa-workspace-rail__group" role="tablist" aria-label="Audit Assurance tools" aria-orientation="vertical">
                {toolLinks.map((link) => renderNavButton(link))}
              </div>
            </details>
          </aside>
        ) : null}

        <section className="qa-workspace-main" data-assurance-workspace-section={activeId} aria-label="Current Audit Assurance workspace">
          {children}
        </section>
      </div>

      <Drawer
        title="Audit Assurance tools"
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        side="right"
        panelClassName="qa-workspace-drawer"
      >
        <div className="qa-workspace-drawer__body">
          <div className="qa-workspace-drawer__tabs" role="tablist" aria-label="Tools drawer tabs">
            <button
              type="button"
              role="tab"
              aria-selected={drawerTab === "actions"}
              className={drawerTab === "actions" ? "is-active" : ""}
              onClick={() => setDrawerTab("actions")}
            >
              Quick actions
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={drawerTab === "lifecycle"}
              className={drawerTab === "lifecycle" ? "is-active" : ""}
              onClick={() => setDrawerTab("lifecycle")}
            >
              Lifecycle
            </button>
          </div>

          {drawerTab === "actions" ? (
            <div className="qa-workspace-drawer__panel" role="tabpanel">
              <div className="qa-workspace-action-list">
                {workflowActions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <Link key={action.title} to={action.href} className="qa-workspace-action" onClick={() => setDrawerOpen(false)}>
                      <span className="qa-workspace-action__icon">
                        <Icon size={17} />
                      </span>
                      <span>
                        <strong>{action.title}</strong>
                        <small>{action.detail}</small>
                      </span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="qa-workspace-drawer__panel" role="tabpanel">
              <ol className="qa-workspace-lifecycle">
                <li>
                  <span>1</span>
                  <div>
                    <strong>Programme</strong>
                    <small>Define why and what must be assured.</small>
                  </div>
                </li>
                <li>
                  <span>2</span>
                  <div>
                    <strong>Calendar</strong>
                    <small>Schedule requirements onto dated audit occurrences.</small>
                  </div>
                </li>
                <li>
                  <span>3</span>
                  <div>
                    <strong>Audits</strong>
                    <small>Prepare, conduct fieldwork, raise findings, close and archive.</small>
                  </div>
                </li>
                <li>
                  <span>4</span>
                  <div>
                    <strong>Findings & Actions</strong>
                    <small>RCA, CAP, implementation, effectiveness and closure.</small>
                  </div>
                </li>
              </ol>
              <div className="qa-workspace-drawer__governance-links">
                {toolLinks.map((link) => (
                  <Link key={link.id} to={link.href} onClick={() => setDrawerOpen(false)}>
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </Drawer>
    </AuditPageShell>
  );
};

export default QualityAuditsSectionLayout;
