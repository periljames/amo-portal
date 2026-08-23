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
  group: "operate" | "govern";
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
        label: "Assurance",
        shortLabel: "Home",
        icon: Gauge,
        href: `/maintenance/${amoCode}/quality/audits/dashboard`,
        description: "Risk, exposure and action overview",
        group: "operate",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits` || location.pathname === `/maintenance/${amoCode}/quality/audits/dashboard`,
      },
      {
        id: "plan-schedule",
        label: "Plan & schedule",
        shortLabel: "Planner",
        icon: CalendarDays,
        href: `/maintenance/${amoCode}/quality/audits/plan?view=calendar`,
        description: "Programme, schedule and reschedule work",
        group: "operate",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/plan` || location.pathname === `/maintenance/${amoCode}/quality/audits/schedule`,
      },
      {
        id: "register",
        label: "Audit register",
        shortLabel: "Register",
        icon: TableProperties,
        href: `/maintenance/${amoCode}/quality/audits/register?tab=findings`,
        description: "Audits, findings and corrective actions",
        group: "operate",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/register`,
      },
      {
        id: "programme",
        label: "Programme",
        shortLabel: "Program",
        icon: Workflow,
        href: `/maintenance/${amoCode}/quality/audits/program`,
        description: "Governed audit programme controls",
        group: "govern",
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/audits/program`),
      },
      {
        id: "checklists",
        label: "Checklists",
        shortLabel: "Checks",
        icon: ListChecks,
        href: `/maintenance/${amoCode}/quality/audits/checklists`,
        description: "Controlled audit checklist library",
        group: "govern",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/checklists`,
      },
      {
        id: "evidence-library",
        label: "Evidence vault",
        shortLabel: "Evidence",
        icon: Files,
        href: `/maintenance/${amoCode}/quality/evidence-vault`,
        description: "Objective evidence and retained records",
        group: "govern",
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/evidence-vault`),
      },
      {
        id: "bin",
        label: "Recycle bin",
        shortLabel: "Bin",
        icon: Trash2,
        href: `/maintenance/${amoCode}/quality/audits/bin`,
        description: "Recover or review removed audit records",
        group: "govern",
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/bin`,
      },
    ],
    [amoCode, location.pathname]
  );

  const activeId = links.find((link) => link.active)?.id ?? "dashboard";

  const openDrawer = (tab: DrawerTab = "actions") => {
    setDrawerTab(tab);
    setDrawerOpen(true);
  };

  const workflowActions = [
    {
      title: "Plan or create an audit",
      detail: "Open the authoritative planner and schedule workflow.",
      href: `/maintenance/${amoCode}/quality/audits/plan?view=calendar`,
      icon: CalendarDays,
    },
    {
      title: "Review planned work",
      detail: "See scheduled audits, assignments and due dates.",
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

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={title}
      subtitle={subtitle}
      breadcrumbs={[
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/quality`) },
        { label: "Audits", onClick: () => navigate(`/maintenance/${amoCode}/quality/audits`) },
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
      overflowActionLabel="Open assurance workflow drawer"
    >
      <div className="qa-workspace-mobile-tabs" aria-label="Audit workspace navigation">
        <ResponsiveSegmentedControl
          label="Audit workspace"
          value={activeId}
          options={links.map((link) => ({
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

      <div className="qa-workspace-shell">
        <aside className="qa-workspace-rail" aria-label="Assurance workspace sections">
          <div className="qa-workspace-rail__heading">
            <span>Assurance workspace</span>
            <button type="button" onClick={() => openDrawer("lifecycle")} aria-label="Open audit lifecycle drawer">
              <Workflow size={15} />
            </button>
          </div>

          <div className="qa-workspace-rail__group" role="tablist" aria-label="Operate" aria-orientation="vertical">
            <span className="qa-workspace-rail__group-label">Operate</span>
            {links.filter((link) => link.group === "operate").map((link) => {
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

          <div className="qa-workspace-rail__group" role="tablist" aria-label="Govern" aria-orientation="vertical">
            <span className="qa-workspace-rail__group-label">Govern & retain</span>
            {links.filter((link) => link.group === "govern").map((link) => {
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
        </aside>

        <section className="qa-workspace-main" data-assurance-workspace-section={activeId} aria-label="Current assurance workspace">
          {children}
        </section>
      </div>

      <Drawer
        title="Assurance workflows"
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
                These shortcuts open the existing governed audit workflows. No duplicate planner, register or closeout path is introduced.
              </p>
              <div className="qa-workspace-action-list">
                {workflowActions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <Link key={action.title} to={action.href} className="qa-workspace-action" onClick={() => setDrawerOpen(false)}>
                      <span className="qa-workspace-action__icon"><Icon size={17} /></span>
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
                  <div><strong>Programme & plan</strong><small>Define the audit commitment, scope, timing and accountable lead.</small></div>
                </li>
                <li>
                  <span>2</span>
                  <div><strong>Prepare & execute</strong><small>Open the audit record for preparation, fieldwork, evidence and observations.</small></div>
                </li>
                <li>
                  <span>3</span>
                  <div><strong>Findings & CAPA</strong><small>Control findings and corrective actions through the audit register.</small></div>
                </li>
                <li>
                  <span>4</span>
                  <div><strong>Verify & close</strong><small>Verify objective evidence before closure and retain the issued output.</small></div>
                </li>
              </ol>
              <div className="qa-workspace-drawer__governance-links">
                {links.filter((link) => link.group === "govern" && link.id !== "bin").map((link) => (
                  <Link key={link.id} to={link.href} onClick={() => setDrawerOpen(false)}>{link.label}</Link>
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
