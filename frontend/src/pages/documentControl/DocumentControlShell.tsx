import type { ReactNode } from "react";
import {
  Archive,
  BookOpen,
  Boxes,
  ClipboardCheck,
  ClipboardList,
  Copy,
  FileClock,
  FileCog,
  FileDiff,
  FileSearch,
  Gauge,
  GitPullRequestArrow,
  Landmark,
  Link2,
  Settings,
  Send,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import "./documentControlWorkspace.css";

export type DocumentControlWorkspaceId =
  | "desk"
  | "library"
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

const WORKSPACES: Array<{
  id: DocumentControlWorkspaceId;
  label: string;
  path: string;
  icon: typeof Gauge;
  controlOnly?: boolean;
}> = [
  { id: "desk", label: "Control desk", path: "", icon: Gauge, controlOnly: true },
  { id: "library", label: "Library", path: "/library", icon: BookOpen },
  { id: "changes", label: "Changes", path: "/change-proposals", icon: ClipboardList, controlOnly: true },
  { id: "revisions", label: "Revisions", path: "/drafts", icon: GitPullRequestArrow, controlOnly: true },
  { id: "authority", label: "Authority", path: "/authority", icon: Landmark, controlOnly: true },
  { id: "temporary-revisions", label: "Temporary revisions", path: "/tr", icon: FileClock, controlOnly: true },
  { id: "distribution", label: "Distribution", path: "/distribution", icon: Send, controlOnly: true },
  { id: "reviews", label: "Reviews", path: "/reviews", icon: ClipboardCheck, controlOnly: true },
  { id: "copies", label: "Controlled copies", path: "/controlled-copies", icon: Copy, controlOnly: true },
  { id: "external", label: "External data", path: "/external-sources", icon: Boxes, controlOnly: true },
  { id: "integrations", label: "Integrations", path: "/integrations", icon: Link2, controlOnly: true },
  { id: "archive", label: "Archive", path: "/archive", icon: Archive, controlOnly: true },
  { id: "reports", label: "Reports", path: "/registers", icon: FileSearch, controlOnly: true },
  { id: "settings", label: "Settings", path: "/settings", icon: Settings, controlOnly: true },
];

export function useDocumentControlRoute() {
  const params = useParams<{
    amoCode?: string;
    department?: string;
    docId?: string;
    draftId?: string;
    proposalId?: string;
    trId?: string;
    eventId?: string;
  }>();
  const amoCode = params.amoCode || "";
  return {
    ...params,
    amoCode,
    tenant: amoCode.toLowerCase(),
    basePath: `/maintenance/${amoCode}/document-control`,
    readerBasePath: `/maintenance/${amoCode}/publications`,
  };
}

function workspaceForPath(pathname: string): DocumentControlWorkspaceId {
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
  const { amoCode, basePath } = useDocumentControlRoute();
  const active = workspaceForPath(location.pathname);
  const visibleWorkspaces = WORKSPACES.filter((workspace) => canControl || !workspace.controlOnly);

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

      <nav className="dc-workspace__nav" aria-label="Document Control workspaces">
        {visibleWorkspaces.map((workspace) => {
          const Icon = workspace.icon;
          return (
            <button
              type="button"
              key={workspace.id}
              className={active === workspace.id ? "active" : ""}
              aria-current={active === workspace.id ? "page" : undefined}
              onClick={() => navigate(`${basePath}${workspace.path}`)}
            >
              <Icon size={15} />
              <span>{workspace.label}</span>
            </button>
          );
        })}
      </nav>

      <main className="dc-workspace__content">{children}</main>
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

export const DocumentControlIcons = {
  BookOpen,
  FileDiff,
};
