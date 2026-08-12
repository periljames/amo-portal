/* eslint react-refresh/only-export-components: ["error", { "allowExportNames": ["useDocumentControlRoute"] }] */
import { useMemo, type ReactNode } from "react";
import {
  BookOpen,
  ClipboardList,
  FileCog,
  FileSearch,
  Gauge,
  Send,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import DocumentationAssistantPanel from "../manuals/DocumentationAssistantPanel";
import DocumentLifecycleHeaderActions from "./DocumentLifecycleHeaderActions";
import DocumentWorkflowGuide from "./DocumentWorkflowGuide";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentControlWorkspace.css";
import "./documentControlExperience.css";
import "./documentControlLibraryExperience.css";
import "./dmsLibraryDiscovery.css";

/**
 * Legacy workspace identifiers remain exported until the route migration is
 * complete. New permanent navigation is intentionally expressed through the
 * smaller PrimaryWorkspaceId set below.
 */
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

type PrimaryWorkspaceId =
  | "home"
  | "library"
  | "changes"
  | "distribution"
  | "compliance"
  | "reports"
  | "administration";

type PrimaryWorkspaceRoute = {
  id: PrimaryWorkspaceId;
  label: string;
  path: string;
  icon: typeof Gauge;
  controlOnly?: boolean;
};

/**
 * Daily-use DMS information architecture. Detailed backend entities remain
 * addressable through deep links but are no longer permanent navigation peers.
 */
const PRIMARY_WORKSPACES: PrimaryWorkspaceRoute[] = [
  { id: "home", label: "Home", path: "", icon: Gauge },
  { id: "library", label: "Library", path: "/library", icon: BookOpen },
  { id: "changes", label: "Changes", path: "/changes", icon: ClipboardList, controlOnly: true },
  { id: "distribution", label: "Distribution", path: "/distribution", icon: Send, controlOnly: true },
  { id: "compliance", label: "Compliance", path: "/compliance", icon: ShieldCheck, controlOnly: true },
  { id: "reports", label: "Reports", path: "/reports", icon: FileSearch, controlOnly: true },
  { id: "administration", label: "Administration", path: "/administration", icon: Settings, controlOnly: true },
];

/**
 * During migration, legacy routes illuminate the primary workspace that owns
 * their job-to-be-done. This preserves deep links without preserving the old
 * navigation model.
 */
function primaryWorkspaceForPath(pathname: string): PrimaryWorkspaceId {
  if (
    pathname.includes("/drafts") ||
    pathname.includes("/change-proposals") ||
    pathname.includes("/revisions/") ||
    pathname.includes("/lep/") ||
    pathname.includes("/authority") ||
    pathname.includes("/tr") ||
    pathname.includes("/changes")
  ) return "changes";

  if (pathname.includes("/distribution") || pathname.includes("/controlled-copies")) return "distribution";

  if (
    pathname.includes("/reviews") ||
    pathname.includes("/external-sources") ||
    pathname.includes("/integrations") ||
    pathname.includes("/compliance")
  ) return "compliance";

  if (pathname.includes("/registers") || pathname.includes("/reports")) return "reports";
  if (pathname.includes("/settings") || pathname.includes("/administration")) return "administration";

  if (
    pathname.includes("/library") ||
    pathname.includes("/structure") ||
    pathname.includes("/records") ||
    pathname.includes("/archive")
  ) return "library";

  return "home";
}

function libraryDocumentId(pathname: string): string | undefined {
  const match = pathname.match(/\/document-control\/library\/([^/?#]+)/);
  if (!match?.[1]) return undefined;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
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
  const { amoCode, tenant, basePath } = useDocumentControlRoute();
  const active = primaryWorkspaceForPath(location.pathname);
  const visibleWorkspaces = PRIMARY_WORKSPACES.filter((workspace) => canControl || !workspace.controlOnly);
  const assistantDocumentId = active === "library" ? libraryDocumentId(location.pathname) : undefined;
  const showContextualAssistant = Boolean(tenant && location.pathname.includes("/document-control/library"));
  const lifecycleActions = canControl && tenant
    ? <DocumentLifecycleHeaderActions tenant={tenant} basePath={basePath} manualId={assistantDocumentId} />
    : null;
  const workflowRefreshKey = useMemo(() => ({ actions }), [actions]);
  const workflowGuide = tenant && assistantDocumentId
    ? <DocumentWorkflowGuide tenant={tenant} basePath={basePath} manualId={assistantDocumentId} refreshKey={workflowRefreshKey} />
    : null;

  const body = (
    <div className="dc-workspace">
      <header className="dc-workspace__header">
        <div>
          <p>{eyebrow}</p>
          <h1>{title}</h1>
          <span>{subtitle}</span>
        </div>
        {actions || lifecycleActions ? <div className="dc-workspace__header-actions">{lifecycleActions}{actions}</div> : null}
      </header>

      {workflowGuide}

      <nav className="dc-workspace__nav dc-workspace__nav--primary" aria-label="Document Control">
        {visibleWorkspaces.map((workspace) => {
          const Icon = workspace.icon;
          const isActive = active === workspace.id;
          return (
            <button
              type="button"
              key={workspace.id}
              className={isActive ? "active" : ""}
              aria-current={isActive ? "page" : undefined}
              onClick={() => navigate(`${basePath}${workspace.path}`)}
            >
              <Icon size={15} aria-hidden="true" />
              <span>{workspace.label}</span>
            </button>
          );
        })}
      </nav>

      <main className="dc-workspace__content">{children}</main>
      {showContextualAssistant ? <DocumentationAssistantPanel
        tenant={tenant}
        manualId={assistantDocumentId}
        title={assistantDocumentId ? "Document evidence search" : "Controlled information search"}
      /> : null}
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
