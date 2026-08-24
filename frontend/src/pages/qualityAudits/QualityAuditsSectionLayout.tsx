import React, { useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  CalendarDays,
  ClipboardList,
  Files,
  Gauge,
  ListChecks,
  PanelRightOpen,
  TableProperties,
  Trash2,
  Workflow,
} from "lucide-react";
import AuditPageShell, { type AuditShellNavItem } from "../../components/QMS/AuditPageShell";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import Drawer from "../../components/shared/Drawer";
import Button from "../../components/UI/Button";
import { getContext } from "../../services/auth";
import "./quality-audits-workspace.css";

type Props = {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  toolbar?: React.ReactNode;
};

type DrawerTab = "actions" | "lifecycle";

type WorkspaceNavItem = AuditShellNavItem & {
  description: string;
  group: "primary" | "retain" | "ops";
};

const QualityAuditsSectionLayout: React.FC<Props> = ({ title, subtitle, children, toolbar }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const location = useLocation();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("actions");

  const links = useMemo<WorkspaceNavItem[]>(
    () => [
      {
        id: "dashboard",
        label: "Overview",
        shortLabel: "Home",
        icon: Gauge,
        href: `/maintenance/${amoCode}/quality/audits/dashboard`,
        description: "Exposure, pipeline and next actions",
        group: "primary",
        active:
          location.pathname === `/maintenance/${amoCode}/quality/audits` ||
          location.pathname === `/maintenance/${amoCode}/quality/audits/dashboard`,
      },
      {
        id: "programme",
        label: "Audit Programme",
        shortLabel: "Programme",
        icon: Workflow,
        href: `/maintenance/${amoCode}/quality/audits/program`,
        description: "Governed coverage, universe and readiness",
        group: "primary",
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/audits/program`),
      },
      {
        id: "register",
        label: "Audit Register",
        shortLabel: "Register",
        icon: TableProperties,
        href: `/maintenance/${amoCode}/quality/audits/register?tab=findings`,
        description: "Audits, findings and corrective actions",
        group: "primary",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/register`,
      },
      {
        id: "planner",
        label: "Planner",
        shortLabel: "Planner",
        icon: CalendarDays,
        href: `/maintenance/${amoCode}/quality/calendar/week`,
        description: "Dated calendar — Planner V2 only",
        group: "primary",
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/calendar`),
      },
      {
        id: "checklists",
        label: "Checklists",
        shortLabel: "Checks",
        icon: ListChecks,
        href: `/maintenance/${amoCode}/quality/audits/checklists`,
        description: "Controlled checklist library",
        group: "retain",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/checklists`,
      },
      {
        id: "evidence-library",
        label: "Evidence",
        shortLabel: "Evidence",
        icon: Files,
        href: `/maintenance/${amoCode}/quality/evidence-vault`,
        description: "Objective evidence and retained records",
        group: "retain",
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/evidence-vault`),
      },
      {
        id: "create-run",
        label: "Create / run",
        shortLabel: "Create",
        icon: ClipboardList,
        href: `/maintenance/${amoCode}/quality/audits/plan?view=list`,
        description: "Operational schedules and run records",
        group: "ops",
        active:
          location.pathname === `/maintenance/${amoCode}/quality/audits/plan` ||
          location.pathname === `/maintenance/${amoCode}/quality/audits/schedule` ||
          location.pathname === `/maintenance/${amoCode}/quality/audits/new` ||
          location.pathname.startsWith(`/maintenance/${amoCode}/quality/audits/schedules/`),
      },
      {
        id: "bin",
        label: "Recycle bin",
        shortLabel: "Bin",
        icon: Trash2,
        href: `/maintenance/${amoCode}/quality/audits/bin`,
        description: "Recover removed audit records",
        group: "ops",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/bin`,
      },
    ],
    [amoCode, location.pathname],
  );

  const primaryLinks = links.filter((link) => link.group === "primary" || link.group === "retain");
  const activeId = links.find((link) => link.active)?.id ?? "dashboard";
  const plannerActive = activeId === "planner";

  const openDrawer = (tab: DrawerTab = "actions") => {
    setDrawerTab(tab);
    setDrawerOpen(true);
  };

  const workflowActions = [
    {
      title: "Open Audit Programme",
      detail: "Define coverage intent, requirements, universe and readiness.",
      href: `/maintenance/${amoCode}/quality/audits/program`,
      icon: Workflow,
    },
    {
      title: "Open Planner",
      detail: "Browse and reschedule dated audits on Planner V2 — the only Quality calendar.",
      href: `/maintenance/${amoCode}/quality/calendar/week`,
      icon: CalendarDays,
    },
    {
      title: "Create or run a schedule",
      detail: "Operational templates and run records (not a second planner).",
      href: `/maintenance/${amoCode}/quality/audits/plan?view=list`,
      icon: ClipboardList,
    },
    {
      title: "Work findings",
      detail: "Open the governed finding register and audit records.",
      href: `/maintenance/${amoCode}/quality/audits/register?tab=findings`,
      icon: TableProperties,
    },
    {
      title: "Work corrective actions",
      detail: "Open the CAR closeout view linked to audit findings.",
      href: `/maintenance/${amoCode}/quality/audits/register?tab=cars`,
      icon: ListChecks,
    },
    {
      title: "Open evidence vault",
      detail: "Review objective evidence and retained audit records.",
      href: `/maintenance/${amoCode}/quality/evidence-vault`,
      icon: Files,
    },
  ];

  const renderRailGroup = (label: string, group: WorkspaceNavItem["group"], ariaLabel: string) => (
    <div className="qa-workspace-rail__group" role="tablist" aria-label={ariaLabel} aria-orientation="vertical">
      <span className="qa-workspace-rail__group-label">{label}</span>
      {links
        .filter((link) => link.group === group)
        .map((link) => {
          const Icon = link.icon;
          return (
            <button
              key={link.id}
              type="button"
              role="tab"
              aria-selected={link.active}
              className={`qa-workspace-rail__tab${link.active ? " qa-workspace-rail__tab--active" : ""}`}
              onClick={() => navigate(link.href)}
            >
              <Icon size={17} />
              <span>
                <strong>{link.label}</strong>
                <small>{link.description}</small>
              </span>
            </button>
          );
        })}
    </div>
  );

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={title}
      subtitle={subtitle}
      breadcrumbs={[
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/quality`) },
        { label: "Audit Assurance", onClick: () => navigate(`/maintenance/${amoCode}/quality/audits`) },
        { label: title },
      ]}
      toolbar={
        <div className="qa-workspace-toolbar">
          {toolbar}
          <Button variant="secondary" size="sm" onClick={() => openDrawer("actions")}>
            <PanelRightOpen size={14} /> Workflows
          </Button>
        </div>
      }
      onOverflowAction={() => openDrawer("actions")}
      overflowActionLabel="Open Audit Assurance workflow drawer"
    >
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

      <div className={`qa-workspace-shell${plannerActive ? " qa-workspace-shell--planner" : ""}`}>
        <aside
          className={`qa-workspace-rail${plannerActive ? " qa-workspace-rail--compact" : ""}`}
          aria-label="Audit Assurance sections"
        >
          <div className="qa-workspace-rail__heading">
            <span>{plannerActive ? "AA" : "Audit Assurance"}</span>
            <button type="button" onClick={() => openDrawer("lifecycle")} aria-label="Open audit lifecycle drawer" title="Lifecycle">
              <Workflow size={15} />
            </button>
          </div>

          {plannerActive ? (
            <div className="qa-workspace-rail__group qa-workspace-rail__group--compact" role="tablist" aria-label="Assurance destinations" aria-orientation="vertical">
              {primaryLinks.map((link) => {
                const Icon = link.icon;
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
              })}
            </div>
          ) : (
            <>
              {renderRailGroup("Workspace", "primary", "Primary workspace")}
              {renderRailGroup("Evidence & templates", "retain", "Checklists and evidence")}
              {renderRailGroup("Operations", "ops", "Operational actions")}
            </>
          )}
        </aside>

        <section className="qa-workspace-main" data-assurance-workspace-section={activeId} aria-label="Current Audit Assurance workspace">
          {children}
        </section>
      </div>

      <Drawer
        title="Audit Assurance workflows"
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        side="right"
        panelClassName="qa-workspace-drawer"
      >
        <div className="qa-workspace-drawer__body">
          <div className="qa-workspace-drawer__tabs" role="tablist" aria-label="Workflow drawer tabs">
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
              <p className="qa-workspace-drawer__intro">
                Programme defines coverage intent. Planner V2 owns dated scheduling. Create / run stays operational — not a second calendar.
              </p>
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
                    <strong>Audit Programme</strong>
                    <small>Setup coverage, requirements, universe and readiness.</small>
                  </div>
                </li>
                <li>
                  <span>2</span>
                  <div>
                    <strong>Schedule → Planner V2</strong>
                    <small>Commit dates on the Quality calendar — never a duplicate planner under audits.</small>
                  </div>
                </li>
                <li>
                  <span>3</span>
                  <div>
                    <strong>Execute</strong>
                    <small>Open the audit record via Setup for preparation, fieldwork and evidence.</small>
                  </div>
                </li>
                <li>
                  <span>4</span>
                  <div>
                    <strong>Follow-up & close</strong>
                    <small>Findings, CAPA, verification and retained output.</small>
                  </div>
                </li>
              </ol>
              <div className="qa-workspace-drawer__governance-links">
                {links
                  .filter((link) => link.group === "retain")
                  .map((link) => (
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
