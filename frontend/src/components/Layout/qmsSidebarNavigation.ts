type QmsAuditShortcut = {
  id: string;
  label: string;
  suffix: string;
  matchSuffixes?: string[];
};

type QmsSidebarEnhancementOptions = {
  sidebar: HTMLElement;
  amoCode: string;
  pathname: string;
  onNavigate: (path: string) => void;
};

const QUALITY_NAV_SELECTOR = '.sidebar__qms-nav[aria-label="Quality modules"]';
const QUALITY_BASE_SEGMENT = "quality";

export const QMS_AUDIT_SHORTCUTS: readonly QmsAuditShortcut[] = [
  { id: "dashboard", label: "Dashboard", suffix: "audits/dashboard" },
  { id: "programme", label: "Programme", suffix: "audits/program" },
  {
    id: "schedule",
    label: "Schedule",
    suffix: "audits/schedule",
    matchSuffixes: ["audits/schedules/"],
  },
  { id: "checklists", label: "Checklists", suffix: "audits/checklists" },
  { id: "reports", label: "Reports", suffix: "audits/reports" },
] as const;

const MODULE_SEARCH_ALIASES: Record<string, string> = {
  audits: "audit inspection programme program schedule checklist report",
  "car / capa": "corrective action preventive action root cause overdue due soon closure",
  findings: "nonconformity non-conformity observation audit finding",
  "controlled documents": "document control manual procedure revision approval distribution archive obsolete",
  "risk & opportunities": "risk opportunity hazard mitigation treatment matrix",
  "training & competence": "training competence matrix expiry overdue qualification",
  suppliers: "supplier vendor approved list evaluation",
  "equipment & calibration": "tool equipment calibration expiry register",
  "management review": "management review meeting actions minutes",
  "external interface": "regulator authority external finding",
};

function qualityBasePath(amoCode: string): string {
  return `/maintenance/${amoCode}/${QUALITY_BASE_SEGMENT}`;
}

function normalise(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

function directModuleButton(node: HTMLElement): HTMLButtonElement | null {
  return node.querySelector<HTMLButtonElement>(":scope > button");
}

function moduleLabel(node: HTMLElement): string {
  const button = directModuleButton(node);
  return String(
    button?.querySelector<HTMLElement>(".sidebar__item-label")?.textContent ||
      button?.getAttribute("aria-label") ||
      button?.textContent ||
      "",
  ).trim();
}

function moduleSearchText(node: HTMLElement): string {
  const label = moduleLabel(node);
  const lowerLabel = normalise(label);
  const childText = normalise(node.textContent);
  return `${lowerLabel} ${childText} ${MODULE_SEARCH_ALIASES[lowerLabel] || ""}`.trim();
}

function matchesPath(pathname: string, path: string, matchPrefixes: string[] = []): boolean {
  return pathname === path || pathname === `${path}/` || matchPrefixes.some((prefix) => pathname.startsWith(prefix));
}

function createShortcutButton(
  shortcut: QmsAuditShortcut,
  basePath: string,
  pathname: string,
  onNavigate: (path: string) => void,
): HTMLButtonElement {
  const path = `${basePath}/${shortcut.suffix}`;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "qms-sidebar-audit-link";
  button.dataset.qmsPath = path;
  button.dataset.qmsShortcut = shortcut.id;
  button.textContent = shortcut.label;
  button.setAttribute("aria-label", `Open audit ${shortcut.label.toLowerCase()}`);
  button.onclick = () => onNavigate(path);

  const matchPrefixes = (shortcut.matchSuffixes || []).map((suffix) => `${basePath}/${suffix}`);
  const active = matchesPath(pathname, path, matchPrefixes);
  button.classList.toggle("qms-sidebar-audit-link--active", active);
  if (active) button.setAttribute("aria-current", "page");

  return button;
}

function applyModuleFilter(nav: HTMLElement, query: string): void {
  const normalisedQuery = normalise(query);
  const nodes = Array.from(nav.querySelectorAll<HTMLElement>(":scope > .sidebar__qms-node"));
  let visibleCount = 0;

  for (const node of nodes) {
    const visible = !normalisedQuery || moduleSearchText(node).includes(normalisedQuery);
    node.hidden = !visible;
    if (visible) visibleCount += 1;
  }

  const emptyState = nav.querySelector<HTMLElement>(":scope > .qms-sidebar-empty");
  if (emptyState) emptyState.hidden = visibleCount > 0;
}

function markCoreModules(nav: HTMLElement): void {
  const nodes = Array.from(nav.querySelectorAll<HTMLElement>(":scope > .sidebar__qms-node"));
  for (const node of nodes) {
    const label = normalise(moduleLabel(node));
    node.classList.toggle("sidebar__qms-node--audit", label === "audits");
    node.classList.toggle("sidebar__qms-node--core", ["audits", "findings", "car / capa"].includes(label));

    const button = directModuleButton(node);
    if (!button) continue;
    if (label === "audits") {
      button.setAttribute("aria-description", "Primary audit workspace with direct shortcuts above");
      button.title = "Audit dashboard";
    }
  }
}

function createTools(
  nav: HTMLElement,
  amoCode: string,
  pathname: string,
  onNavigate: (path: string) => void,
): HTMLElement {
  const basePath = qualityBasePath(amoCode);
  const tools = document.createElement("section");
  tools.className = "qms-sidebar-tools";
  tools.setAttribute("aria-label", "Quality navigation tools");

  const heading = document.createElement("div");
  heading.className = "qms-sidebar-tools__heading";

  const title = document.createElement("span");
  title.className = "qms-sidebar-tools__title";
  title.textContent = "Quality navigation";

  const overview = document.createElement("button");
  overview.type = "button";
  overview.className = "qms-sidebar-overview-link";
  overview.textContent = "Overview";
  overview.dataset.qmsPath = basePath;
  overview.onclick = () => onNavigate(basePath);
  const overviewActive = pathname === basePath || pathname === `${basePath}/`;
  overview.classList.toggle("qms-sidebar-overview-link--active", overviewActive);
  if (overviewActive) overview.setAttribute("aria-current", "page");

  heading.append(title, overview);

  const auditSection = document.createElement("section");
  auditSection.className = "qms-sidebar-audit";
  auditSection.setAttribute("aria-label", "Audit workspace shortcuts");

  const auditHeading = document.createElement("div");
  auditHeading.className = "qms-sidebar-audit__heading";
  auditHeading.textContent = "Audit workspace";

  const auditLinks = document.createElement("div");
  auditLinks.className = "qms-sidebar-audit__links";
  for (const shortcut of QMS_AUDIT_SHORTCUTS) {
    auditLinks.append(createShortcutButton(shortcut, basePath, pathname, onNavigate));
  }
  auditSection.append(auditHeading, auditLinks);

  const searchLabel = document.createElement("label");
  searchLabel.className = "qms-sidebar-search";
  const searchText = document.createElement("span");
  searchText.className = "qms-sidebar-search__label";
  searchText.textContent = "Find a module";
  const search = document.createElement("input");
  search.type = "search";
  search.className = "qms-sidebar-search__input";
  search.placeholder = "Search Quality modules";
  search.autocomplete = "off";
  search.setAttribute("aria-label", "Search Quality modules");
  search.oninput = () => applyModuleFilter(nav, search.value);
  searchLabel.append(searchText, search);

  const moduleLabelElement = document.createElement("div");
  moduleLabelElement.className = "qms-sidebar-tools__module-label";
  moduleLabelElement.textContent = "All Quality modules";

  tools.append(heading, auditSection, searchLabel, moduleLabelElement);
  return tools;
}

function refreshTools(
  nav: HTMLElement,
  amoCode: string,
  pathname: string,
  onNavigate: (path: string) => void,
): void {
  const basePath = qualityBasePath(amoCode);
  const overview = nav.querySelector<HTMLButtonElement>(".qms-sidebar-overview-link");
  if (overview) {
    overview.onclick = () => onNavigate(basePath);
    const active = pathname === basePath || pathname === `${basePath}/`;
    overview.classList.toggle("qms-sidebar-overview-link--active", active);
    if (active) overview.setAttribute("aria-current", "page");
    else overview.removeAttribute("aria-current");
  }

  for (const shortcut of QMS_AUDIT_SHORTCUTS) {
    const button = nav.querySelector<HTMLButtonElement>(`[data-qms-shortcut="${shortcut.id}"]`);
    if (!button) continue;
    const path = `${basePath}/${shortcut.suffix}`;
    const matchPrefixes = (shortcut.matchSuffixes || []).map((suffix) => `${basePath}/${suffix}`);
    const active = matchesPath(pathname, path, matchPrefixes);
    button.onclick = () => onNavigate(path);
    button.classList.toggle("qms-sidebar-audit-link--active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }

  const search = nav.querySelector<HTMLInputElement>(".qms-sidebar-search__input");
  if (search) {
    search.oninput = () => applyModuleFilter(nav, search.value);
    applyModuleFilter(nav, search.value);
  }
}

export function isQualityNavigationPath(pathname: string, amoCode: string): boolean {
  const basePath = qualityBasePath(amoCode);
  return (
    pathname === basePath ||
    pathname.startsWith(`${basePath}/`) ||
    pathname.startsWith(`/maintenance/${amoCode}/training/competence`)
  );
}

export function enhanceQmsSidebarNavigation({
  sidebar,
  amoCode,
  pathname,
  onNavigate,
}: QmsSidebarEnhancementOptions): void {
  const nav = sidebar.querySelector<HTMLElement>(QUALITY_NAV_SELECTOR);
  if (!nav) return;

  nav.classList.add("sidebar__qms-nav--enhanced");
  markCoreModules(nav);

  let tools = nav.querySelector<HTMLElement>(":scope > .qms-sidebar-tools");
  if (!tools) {
    tools = createTools(nav, amoCode, pathname, onNavigate);
    nav.prepend(tools);
  }

  let emptyState = nav.querySelector<HTMLElement>(":scope > .qms-sidebar-empty");
  if (!emptyState) {
    emptyState = document.createElement("div");
    emptyState.className = "qms-sidebar-empty";
    emptyState.textContent = "No Quality module matches that search.";
    emptyState.hidden = true;
    nav.append(emptyState);
  }

  refreshTools(nav, amoCode, pathname, onNavigate);
}
