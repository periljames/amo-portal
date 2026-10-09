/* eslint react-refresh/only-export-components: ["error", { "allowExportNames": ["useDocumentControlRoute"] }] */
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  Archive,
  BarChart3,
  BookOpen,
  Boxes,
  ClipboardList,
  Clock3,
  FileCog,
  FileSearch,
  Heart,
  Home,
  LibraryBig,
  Menu,
  Search,
  Send,
  Settings,
  Share2,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import DocumentationAssistantPanel from "../manuals/DocumentationAssistantPanel";
import DocumentControlJobLauncher from "./DocumentControlJobLauncher";
import DocumentLifecycleHeaderActions from "./DocumentLifecycleHeaderActions";
import DocumentWorkflowGuide from "./DocumentWorkflowGuide";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentControlWorkspace.css";
import "./documentControlExperience.css";
import "./documentControlLibraryExperience.css";
import "./dmsLibraryDiscovery.css";

type NavigationItem = {
  id: string;
  label: string;
  path: string;
  icon: typeof Home;
  controlOnly?: boolean;
};

const READER_NAVIGATION: NavigationItem[] = [
  { id: "home", label: "Home", path: "", icon: Home },
  { id: "my-documents", label: "My documents", path: "/library?view=my-documents", icon: UserRound },
  { id: "shared-with-me", label: "Shared with me", path: "/library?view=shared-with-me", icon: Share2 },
  { id: "favorites", label: "Favorites", path: "/library?view=favorites", icon: Heart },
  { id: "recent", label: "Recent", path: "/library?view=recently-opened", icon: Clock3 },
  { id: "libraries", label: "Libraries", path: "/library", icon: LibraryBig },
  { id: "external", label: "External Technical Data", path: "/library?view=external-technical-data", icon: Boxes },
  { id: "physical", label: "Physical Library", path: "/physical-library", icon: BookOpen },
  { id: "records", label: "Records", path: "/reports/records", icon: Archive },
  { id: "archive", label: "Archive", path: "/library?view=archived", icon: Archive },
];

const GOVERNANCE_NAVIGATION: NavigationItem[] = [
  { id: "control-center", label: "Control Center", path: "", icon: ShieldCheck, controlOnly: true },
  { id: "changes", label: "Changes", path: "/changes", icon: ClipboardList, controlOnly: true },
  { id: "distribution", label: "Distribution", path: "/distribution", icon: Send, controlOnly: true },
  { id: "compliance", label: "Compliance", path: "/compliance", icon: ShieldCheck, controlOnly: true },
  { id: "reports", label: "Reports", path: "/reports", icon: BarChart3, controlOnly: true },
  { id: "administration", label: "Administration", path: "/administration", icon: Settings, controlOnly: true },
];

function libraryDocumentId(pathname: string): string | undefined {
  const match = pathname.match(/\/document-control\/library\/([^/?#]+)/);
  if (!match?.[1]) return undefined;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function activeNavigation(pathname: string, search: string): string {
  const params = new URLSearchParams(search);
  if (pathname.includes("/changes")) return "changes";
  if (pathname.includes("/distribution")) return "distribution";
  if (pathname.includes("/compliance")) return "compliance";
  if (pathname.includes("/administration")) return "administration";
  if (pathname.includes("/reports/records")) return "records";
  if (pathname.includes("/reports")) return "reports";
  if (pathname.includes("/physical-library")) return "physical";
  if (pathname.includes("/library")) {
    if (params.get("view") === "my-documents") return "my-documents";
    if (params.get("view") === "shared-with-me") return "shared-with-me";
    if (params.get("view") === "favorites") return "favorites";
    if (params.get("view") === "recently-opened") return "recent";
    if (params.get("view") === "external-technical-data") return "external";
    if (params.get("view") === "archived") return "archive";
    if (params.get("library_services")) return "physical";
    return "libraries";
  }
  return "home";
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
  const routeKey = `${location.pathname}${location.search}`;
  const [navigationRoute, setNavigationRoute] = useState<string | null>(null);
  const navigationOpen = navigationRoute === routeKey;
  const [searchDraft, setSearchDraft] = useState<{ routeKey: string; value: string } | null>(null);
  const searchText = searchDraft?.routeKey === routeKey
    ? searchDraft.value
    : new URLSearchParams(location.search).get("q") || "";
  const active = activeNavigation(location.pathname, location.search);
  const assistantDocumentId = libraryDocumentId(location.pathname);
  const assistantParams = new URLSearchParams(location.search);
  const assistantQuery = assistantParams.get("assistant_query") || "";
  const assistantRequested = assistantParams.get("assistant") === "1";
  const showContextualAssistant = Boolean(tenant && (location.pathname.includes("/document-control/library") || location.pathname.includes("/document-control/search")));
  const lifecycleActions = canControl && tenant
    ? <DocumentLifecycleHeaderActions tenant={tenant} basePath={basePath} manualId={assistantDocumentId} />
    : null;
  const startWork = canControl ? <DocumentControlJobLauncher basePath={basePath} /> : null;
  const workflowRefreshKey = useMemo(() => ({ actions }), [actions]);
  const workflowGuide = tenant && assistantDocumentId
    ? <DocumentWorkflowGuide tenant={tenant} basePath={basePath} manualId={assistantDocumentId} refreshKey={workflowRefreshKey} />
    : null;

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchText.trim();
    const next = new URLSearchParams();
    if (query) next.set("q", query);
    navigate(`${basePath}/search${next.size ? `?${next.toString()}` : ""}`);
  };

  const navigateItem = (item: NavigationItem) => {
    navigate(`${basePath}${item.path}`);
    setNavigationRoute(null);
  };

  const renderNavigation = (items: NavigationItem[]) => items
    .filter((item) => canControl || !item.controlOnly)
    .map((item) => {
      const Icon = item.icon;
      const selected = active === item.id;
      return (
        <button
          type="button"
          key={item.id}
          className={selected ? "active" : ""}
          aria-current={selected ? "page" : undefined}
          onClick={() => navigateItem(item)}
        >
          <Icon size={16} aria-hidden="true" />
          <span>{item.label}</span>
        </button>
      );
    });

  const body = (
    <div className="dc-workspace">
      <a className="dc-skip-link" href="#dc-main-content">Skip to document content</a>
      <header className="dc-workspace__appbar">
        <button
          type="button"
          className="dc-workspace__nav-toggle"
          aria-label={navigationOpen ? "Close Document Control navigation" : "Open Document Control navigation"}
          aria-expanded={navigationOpen}
          onClick={() => setNavigationRoute(navigationOpen ? null : routeKey)}
        >
          {navigationOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
        <div className="dc-workspace__identity">
          <strong>Document Control</strong>
          <span>Company knowledge library</span>
        </div>
        <form className="dc-workspace__global-search" role="search" onSubmit={submitSearch}>
          <Search size={16} aria-hidden="true" />
          <input
            value={searchText}
            onChange={(event) => setSearchDraft({ routeKey, value: event.target.value })}
            aria-label="Search controlled company information"
            placeholder="Search documents, records, codes, owners or indexed text"
          />
        </form>
        <div className="dc-workspace__app-actions">{startWork}{lifecycleActions}{actions}</div>
      </header>

      <div className="dc-workspace__frame">
        <aside className={`dc-workspace__sidebar${navigationOpen ? " is-open" : ""}`} aria-label="Document Control navigation">
          <nav>
            <div className="dc-workspace__nav-group">{renderNavigation(READER_NAVIGATION)}</div>
            {canControl ? <>
              <div className="dc-workspace__nav-separator" />
              <p className="dc-workspace__nav-label">Governance</p>
              <div className="dc-workspace__nav-group">{renderNavigation(GOVERNANCE_NAVIGATION)}</div>
            </> : null}
          </nav>
        </aside>
        {navigationOpen ? <button type="button" className="dc-workspace__nav-backdrop" aria-label="Close navigation" onClick={() => setNavigationRoute(null)} /> : null}

        <div className="dc-workspace__main">
          <header className="dc-workspace__context-header">
            <div>
              <p>{eyebrow}</p>
              <h1>{title}</h1>
              <span>{subtitle}</span>
            </div>
          </header>

          {workflowGuide}

          <main id="dc-main-content" className="dc-workspace__content" tabIndex={-1}>{children}</main>
        </div>
      </div>

      {showContextualAssistant ? <DocumentationAssistantPanel
        tenant={tenant}
        manualId={assistantDocumentId}
        defaultOpen={assistantRequested}
        initialQuery={assistantQuery}
        initialMode="ASSIST"
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
