import type { ReactNode } from "react";
import {
  Archive,
  BookOpen,
  Boxes,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  Copy,
  Database,
  FileClock,
  FileCog,
  FileSearch,
  FolderTree,
  Gauge,
  GitPullRequestArrow,
  Landmark,
  Link2,
  Settings,
  Send,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import DocumentationAssistantPanel from "../manuals/DocumentationAssistantPanel";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentControlWorkspace.css";
import "./documentControlExperience.css";
import "./documentControlLibraryExperience.css";

export type DocumentControlWorkspaceId =
  | "desk"
  | "library"
  | "structure"
  | "records"
  | "changes"
  | "revisions"
  | "authority"
  | "temporary-revisions"
  | "distribution"
  | "reviews"
  | "copies"
  | "external"
  | "integrations"
  | "archive"
  | "reports"
  | "settings";

type WorkspaceRoute = {
  id: DocumentControlWorkspaceId;
  label: string;
  path: string;
  icon: typeof Gauge;
  description: string;
  controlOnly?: boolean;
};

type WorkspaceGroup = {
  id: string;
  label: string;
  path: string;
  icon: typeof Gauge;
  workspaces: WorkspaceRoute[];
  controlOnly?: boolean;
};

const WORKSPACE_GROUPS: WorkspaceGroup[] = [
  {
    id: "overview",
    label: "Overview",
    path: "",
    icon: Gauge,
    workspaces: [
      {
        id: "desk",
        label: "Control desk",
        path: "",
        icon: Gauge,
        description: "Priorities, release risks, document health, and recent evidence.",
      },
    ],
  },
  {
    id: "documents",
    label: "Documents",
    path: "/library",
    icon: BookOpen,
    workspaces: [
      {
        id: "library",
        label: "Company library",
        path: "/library",
        icon: BookOpen,
        description: "Policies, manuals, procedures, work instructions, forms and permitted external data.",
      },
      {
        id: "structure",
        label: "Document structure",
        path: "/structure",
        icon: FolderTree,
        description: "Full hierarchy, classification, applicability, and document ownership.",
      },
      {
        id: "records",
        label: "Generated records",
        path: "/records",
        icon: Database,
        description: "Controlled evidence produced by portal workflows.",
        controlOnly: true,
      },
    ],
  },
  {
    id: "lifecycle",
    label: "Lifecycle",
    path: "/drafts",
    icon: GitPullRequestArrow,
    controlOnly: true,
    workspaces: [
      {
        id: "changes",
        label: "Change requests",
        path: "/change-proposals",
        icon: ClipboardList,
        description: "Capture, assess, assign, and close amendment triggers.",
        controlOnly: true,
      },
      {
        id: "revisions",
        label: "Revision workflows",
        path: "/drafts",
        icon: GitPullRequestArrow,
        description: "Technical, Quality, accountable-manager, and release gates.",
        controlOnly: true,
      },
      {
        id: "authority",
        label: "Authority submissions",
        path: "/authority",
        icon: Landmark,
        description: "Submission references, responses, approval evidence, and due dates.",
        controlOnly: true,
      },
      {
        id: "temporary-revisions",
        label: "Temporary revisions",
        path: "/tr",
        icon: FileClock,
        description: "Effectivity, distribution, expiry, withdrawal, and incorporation.",
        controlOnly: true,
      },
    ],
  },
  {
    id: "assurance",
    label: "Assurance",
    path: "/distribution",
    icon: ClipboardCheck,
    controlOnly: true,
    workspaces: [
      {
        id: "distribution",
        label: "Distribution and acknowledgements",
        path: "/distribution",
        icon: Send,
        description: "Issue current revisions and retain read-and-understand evidence.",
        controlOnly: true,
      },
      {
        id: "reviews",
        label: "Periodic reviews",
        path: "/reviews",
        icon: ClipboardCheck,
        description: "Review currency, continued suitability, findings, and actions.",
        controlOnly: true,
      },
      {
        id: "copies",
        label: "Physical library",
        path: "/controlled-copies",
        icon: Copy,
        description: "Shelf location, QR checkout, named custody, due return, recall and disposition.",
        controlOnly: true,
      },
      {
        id: "external",
        label: "External technical data",
        path: "/external-sources",
        icon: Boxes,
        description: "OEM, authority, and supplier revision currency.",
        controlOnly: true,
      },
    ],
  },
  {
    id: "compliance",
    label: "Compliance",
    path: "/registers",
    icon: FileSearch,
    controlOnly: true,
    workspaces: [
      {
        id: "integrations",
        label: "QMS and module links",
        path: "/integrations",
        icon: Link2,
        description: "Trace controlled documents to live records in their owning modules.",
        controlOnly: true,
      },
      {
        id: "archive",
        label: "Archive and withdrawal",
        path: "/archive",
        icon: Archive,
        description: "Supersession, retention, withdrawal, and disposition evidence.",
        controlOnly: true,
      },
      {
        id: "reports",
        label: "Registers and reports",
        path: "/registers",
        icon: FileSearch,
        description: "Master register, overdue controls, LEP, and archive register.",
        controlOnly: true,
      },
      {
        id: "settings",
        label: "Control settings",
        path: "/settings",
        icon: Settings,
        description: "Review intervals, retention, acknowledgements, and workflow policy.",
        controlOnly: true,
      },
    ],
  },
];

function workspaceForPath(pathname: string): DocumentControlWorkspaceId {
  if (pathname.includes("/records")) return "records";
  if (pathname.includes("/structure")) return "structure";
  if (pathname.includes("/library")) return "library";
  if (pathname.includes("/change-proposals")) return "changes";
  if (pathname.includes("/drafts") || pathname.includes("/revisions/") || pathname.includes("/lep/")) return "revisions";
  if (pathname.includes("/authority")) return "authority";
  if (pathname.includes("/tr")) return "temporary-revisions";
  if (pathname.includes("/distribution")) return "distribution";
  if (pathname.includes("/reviews")) return "reviews";
  if (pathname.includes("/controlled-copies")) return "copies";
  if (pathname.includes("/external-sources")) return "external";
  if (pathname.includes("/integrations")) return "integrations";
  if (pathname.includes("/archive")) return "archive";
  if (pathname.includes("/registers")) return "reports";
  if (pathname.includes("/settings")) return "settings";
  return "desk";
}

export default function DocumentControlShell({
  title,
  eyebrow = "DOCUMENT CONTROL",
  subtitle,
  actions,
  canControl = true,
  children,
}: {
  title: string;
  eyebrow?: string;
  subtitle: string;
  actions?: ReactNode;
  canControl?: boolean;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { amoCode, basePath, tenant } = useDocumentControlRoute();
  const active = workspaceForPath(location.pathname);
  const visibleGroups = WORKSPACE_GROUPS
    .filter((group) => canControl || !group.controlOnly)
    .map((group) => ({
      ...group,
      workspaces: group.workspaces.filter((workspace) => canControl || !workspace.controlOnly),
    }))
    .filter((group) => group.workspaces.length > 0);

  const body = (
    <div className="dc-workspace">
      <header className="dc-workspace__header">
        <div>
          <p>{eyebrow}</p>
          <h1>{title}</h1>
          <span>{subtitle}</span>
        </div>
        {actions ? <div className="dc-workspace__header-actions">{actions}</div> : null}
      </header>

      <nav className="dc-workspace__nav dc-workspace__nav--grouped" aria-label="Document Control workspaces">
        {visibleGroups.map((group) => {
          const Icon = group.icon;
          const activeGroup = group.workspaces.some((workspace) => workspace.id === active);
          const hasMenu = group.workspaces.length > 1;
          return (
            <div className={`dc-workspace__nav-group${activeGroup ? " active" : ""}`} key={group.id}>
              <button
                type="button"
                className="dc-workspace__nav-trigger"
                aria-current={activeGroup ? "page" : undefined}
                aria-haspopup={hasMenu ? "menu" : undefined}
                onClick={() => navigate(`${basePath}${group.path}`)}
              >
                <Icon size={15} />
                <span>{group.label}</span>
                {hasMenu ? <ChevronDown className="dc-workspace__nav-chevron" size={13} aria-hidden="true" /> : null}
              </button>
              {hasMenu ? (
                <div className="dc-workspace__menu" role="menu" aria-label={`${group.label} routes`}>
                  {group.workspaces.map((workspace) => {
                    const WorkspaceIcon = workspace.icon;
                    return (
                      <button
                        type="button"
                        role="menuitem"
                        key={workspace.id}
                        className={active === workspace.id ? "active" : ""}
                        onClick={() => navigate(`${basePath}${workspace.path}`)}
                      >
                        <WorkspaceIcon size={16} />
                        <span>
                          <strong>{workspace.label}</strong>
                          <small>{workspace.description}</small>
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </nav>

      <main className="dc-workspace__content">{children}</main>
      {tenant ? <DocumentationAssistantPanel tenant={tenant} title="Search documented information" /> : null}
    </div>
  );

  if (!amoCode) return body;
  return <DepartmentLayout amoCode={amoCode} activeDepartment="document-control">{body}</DepartmentLayout>;
}

export function DocumentControlStatus({
  status,
  kind = "neutral",
}: {
  status: string;
  kind?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  return <span className={`dc-status dc-status--${kind}`}>{status.replaceAll("_", " ")}</span>;
}

export function DocumentControlEmpty({
  icon: Icon = FileSearch,
  title,
  message,
  action,
}: {
  icon?: typeof FileSearch;
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="dc-empty">
      <Icon size={24} />
      <strong>{title}</strong>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function DocumentControlError({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="dc-error" role="alert">
      <FileCog size={20} />
      <div><strong>Document Control could not complete this request.</strong><span>{message}</span></div>
      {retry ? <button type="button" onClick={retry}>Retry</button> : null}
    </div>
  );
}

export function DocumentControlLoading({ label = "Loading Document Control…" }: { label?: string }) {
  return <div className="dc-loading" role="status"><span /><strong>{label}</strong></div>;
}

export function DocumentControlSection({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="dc-section">
      <header>
        <div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>
        {actions ? <div>{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

export { useDocumentControlRoute } from "./documentControlRoute";
