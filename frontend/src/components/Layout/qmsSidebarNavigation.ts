import {
  QMS_ROUTE_REGISTRY,
  qmsBasePath,
  qmsModulePath,
  qmsTrainingPath,
} from "../../pages/qms/routes/qmsRouteRegistry";

type QmsRegisteredDestination = {
  id: string;
  label: string;
  moduleId: string;
  view: string;
  keywords?: string;
  matchRelativePrefixes?: readonly string[];
};

type QmsWorkspaceTab = {
  id: string;
  label: string;
  stage: "setup" | "prepare" | "live" | "closing" | "follow-up" | "archive";
};

type QmsNavigationGroup = {
  id: string;
  label: string;
  description: string;
  moduleIds: readonly string[];
};

type QmsSidebarEnhancementOptions = {
  sidebar: HTMLElement;
  amoCode: string;
  pathname: string;
  search: string;
  onNavigate: (path: string) => void;
};

type NavigationLink = {
  id: string;
  label: string;
  path: string;
  keywords?: string;
  matchPrefixes?: readonly string[];
  activeMode?: "exact" | "prefix";
};

const QUALITY_NAV_SELECTOR = '.sidebar__qms-nav[aria-label="Quality modules"]';
const STATIC_AUDIT_SEGMENTS = new Set([
  "dashboard",
  "program",
  "programme",
  "schedule",
  "schedules",
  "register",
  "checklists",
  "templates",
  "new",
  "plan",
  "bin",
]);

export const QMS_AUDIT_DESTINATIONS: readonly QmsRegisteredDestination[] = [
  // Single sidebar entry into the workspace — section nav lives on the Assurance rail.
  {
    id: "audit-assurance-hub",
    label: "Audit Assurance",
    moduleId: "audits",
    view: "dashboard",
    keywords: "assurance overview programme register planner checklists evidence",
    matchRelativePrefixes: ["audits"],
  },
] as const;

export const QMS_CALENDAR_DESTINATIONS: readonly QmsRegisteredDestination[] = [
  { id: "calendar-week", label: "Week", moduleId: "calendar", view: "week", keywords: "calendar dates planner" },
  { id: "calendar-month", label: "Month", moduleId: "calendar", view: "month", keywords: "calendar dates planner" },
  { id: "calendar-year", label: "Year", moduleId: "calendar", view: "year", keywords: "calendar programme annual" },
  { id: "calendar-agenda", label: "Agenda", moduleId: "calendar", view: "list", keywords: "list upcoming deadlines" },
  { id: "calendar-audits", label: "Audit dates", moduleId: "calendar", view: "audits", keywords: "audit schedule inspection" },
  { id: "calendar-cars", label: "CAR deadlines", moduleId: "calendar", view: "cars", keywords: "corrective action due overdue" },
  { id: "calendar-training", label: "Training expiries", moduleId: "calendar", view: "training", keywords: "competence expiry" },
  { id: "calendar-review", label: "Management reviews", moduleId: "calendar", view: "management-review", keywords: "review meeting" },
] as const;

export const QMS_AUDIT_WORKSPACE_STAGES: readonly QmsWorkspaceTab[] = [
  { id: "audit-setup", label: "Setup", stage: "setup" },
  { id: "audit-prepare", label: "Prepare", stage: "prepare" },
  { id: "audit-live", label: "Live audit", stage: "live" },
  { id: "audit-closing", label: "Closing", stage: "closing" },
  { id: "audit-follow-up", label: "Follow-up", stage: "follow-up" },
  { id: "audit-archive", label: "Archive", stage: "archive" },
] as const;

export const QMS_NAVIGATION_GROUPS: readonly QmsNavigationGroup[] = [
  {
    id: "assurance",
    label: "Assurance & corrective action",
    description: "Findings, CARs, risk and change control",
    moduleIds: ["findings", "cars", "risk", "change-control"],
  },
  {
    id: "controls",
    label: "System controls",
    description: "Processes, documents, competence and operational controls",
    moduleIds: ["system", "documents", "suppliers", "equipment-calibration", "external-interface"],
  },
  {
    id: "review",
    label: "Review, reports & evidence",
    description: "Management review, analytics and retained evidence",
    moduleIds: ["management-review", "reports", "evidence-vault"],
  },
  {
    id: "administration",
    label: "Administration",
    description: "Quality configuration and enabled specialist tools",
    moduleIds: ["settings", "aerodoc"],
  },
] as const;

function normalise(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function pathWithoutTrailingSlash(path: string): string {
  return path.length > 1 ? path.replace(/\/+$/, "") : path;
}

function matchesPrefix(current: string, prefix: string): boolean {
  const clean = pathWithoutTrailingSlash(prefix);
  return current === clean || current.startsWith(`${clean}/`);
}

function matchesPath(pathname: string, link: NavigationLink): boolean {
  const current = pathWithoutTrailingSlash(pathname);
  const target = pathWithoutTrailingSlash(link.path.split("?")[0]);

  if (link.activeMode === "prefix") {
    return matchesPrefix(current, target) || (link.matchPrefixes || []).some((prefix) => matchesPrefix(current, prefix));
  }

  if (current === target) return true;
  return (link.matchPrefixes || []).some((prefix) => matchesPrefix(current, prefix));
}

function registeredDestinationPath(amoCode: string, destination: QmsRegisteredDestination): string {
  return qmsModulePath(amoCode, destination.moduleId, destination.view);
}

function registeredDestinationLink(amoCode: string, destination: QmsRegisteredDestination): NavigationLink {
  const basePath = qmsBasePath(amoCode);
  return {
    id: destination.id,
    label: destination.label,
    path: registeredDestinationPath(amoCode, destination),
    keywords: destination.keywords,
    matchPrefixes: (destination.matchRelativePrefixes || []).map((relative) => `${basePath}/${relative}`),
  };
}

export function getActiveAuditWorkspace(pathname: string, amoCode: string): { auditKey: string; basePath: string } | null {
  const prefix = `${qmsBasePath(amoCode)}/audits/`;
  if (!pathname.startsWith(prefix)) return null;
  const [auditKey, stage, ...tail] = pathname.slice(prefix.length).split("/").filter(Boolean);
  if (!auditKey || STATIC_AUDIT_SEGMENTS.has(auditKey)) return null;
  if (tail.length || !QMS_AUDIT_WORKSPACE_STAGES.some((item) => item.stage === stage)) return null;
  return { auditKey, basePath: `${prefix}${auditKey}` };
}

export function buildAuditWorkspaceStagePath(basePath: string, stage: QmsWorkspaceTab["stage"], search = ""): string {
  const params = new URLSearchParams(search);
  params.delete("tab");
  const remaining = params.toString();
  return `${basePath}/${stage}${remaining ? `?${remaining}` : ""}`;
}

export function isQualityNavigationPath(pathname: string, amoCode: string): boolean {
  const basePath = qmsBasePath(amoCode);
  return (
    pathname === basePath ||
    pathname.startsWith(`${basePath}/`) ||
    pathname.startsWith(`/maintenance/${encodeURIComponent(amoCode)}/training/competence`)
  );
}

function createNavigationButton(
  link: NavigationLink,
  pathname: string,
  onNavigate: (path: string) => void,
): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "qms-nav-link";
  button.dataset.qmsNavId = link.id;
  button.dataset.qmsPath = link.path;
  button.dataset.qmsActiveMode = link.activeMode || "exact";
  button.dataset.qmsSearch = normalise(`${link.label} ${link.keywords || ""}`);
  if (link.matchPrefixes?.length) button.dataset.qmsMatchPrefixes = link.matchPrefixes.join("\n");

  const label = document.createElement("span");
  label.className = "qms-nav-link__label";
  label.textContent = link.label;
  button.append(label);

  button.onclick = () => onNavigate(link.path);
  setButtonActive(button, matchesPath(pathname, link));
  return button;
}

function setButtonActive(button: HTMLButtonElement, active: boolean): void {
  button.classList.toggle("qms-nav-link--active", active);
  if (active) button.setAttribute("aria-current", "page");
  else button.removeAttribute("aria-current");
}

function linkFromButton(button: HTMLButtonElement): NavigationLink {
  return {
    id: button.dataset.qmsNavId || "qms-link",
    label: button.textContent || "Quality page",
    path: button.dataset.qmsPath || "#",
    matchPrefixes: button.dataset.qmsMatchPrefixes?.split("\n").filter(Boolean),
    activeMode: (button.dataset.qmsActiveMode as NavigationLink["activeMode"]) || "exact",
  };
}

function createSection(
  id: string,
  label: string,
  description: string,
  links: readonly NavigationLink[],
  pathname: string,
  onNavigate: (path: string) => void,
  options: { prominent?: boolean; open?: boolean } = {},
): HTMLDetailsElement {
  const details = document.createElement("details");
  details.className = `qms-nav-section${options.prominent ? " qms-nav-section--prominent" : ""}`;
  details.dataset.qmsSection = id;
  details.open = Boolean(options.open || links.some((link) => matchesPath(pathname, link)));

  const summary = document.createElement("summary");
  summary.className = "qms-nav-section__summary";
  const summaryText = document.createElement("span");
  summaryText.className = "qms-nav-section__summary-text";
  const title = document.createElement("strong");
  title.textContent = label;
  const helper = document.createElement("small");
  helper.textContent = description;
  summaryText.append(title, helper);
  summary.append(summaryText);

  const list = document.createElement("div");
  list.className = "qms-nav-section__links";
  for (const link of links) {
    list.append(createNavigationButton(link, pathname, onNavigate));
  }

  details.append(summary, list);
  return details;
}

function moduleLinksForGroup(amoCode: string, group: QmsNavigationGroup, aerodocEnabled: boolean): NavigationLink[] {
  const links: NavigationLink[] = [];
  const basePath = qmsBasePath(amoCode);
  for (const moduleId of group.moduleIds) {
    if (moduleId === "aerodoc" && !aerodocEnabled) continue;
    const module = QMS_ROUTE_REGISTRY.find((candidate) => candidate.id === moduleId);
    if (!module) continue;
    links.push({
      id: `module-${module.id}`,
      label: module.navigationLabel,
      path: qmsModulePath(amoCode, module.id),
      keywords: `${module.label} ${module.section}`,
      activeMode: "prefix",
      matchPrefixes: [`${basePath}/${module.segment}`],
    });
  }

  if (group.id === "controls") {
    links.splice(2, 0, {
      id: "module-training",
      label: "Training & competence",
      path: qmsTrainingPath(amoCode, "dashboard"),
      keywords: "training competence matrix expiry qualifications",
      activeMode: "prefix",
      matchPrefixes: [`/maintenance/${encodeURIComponent(amoCode)}/training/competence`],
    });
  }
  return links;
}

function isAeroDocEnabled(nav: HTMLElement): boolean {
  return Array.from(nav.querySelectorAll<HTMLElement>(":scope > .sidebar__qms-node"))
    .some((node) => normalise(node.textContent).includes("aerodoc"));
}

function currentAuditLinks(
  workspace: { auditKey: string; basePath: string },
  search: string,
): NavigationLink[] {
  return QMS_AUDIT_WORKSPACE_STAGES.map((item) => ({
    id: item.id,
    label: item.label,
    path: buildAuditWorkspaceStagePath(workspace.basePath, item.stage, search),
    keywords: `current audit workflow ${item.label}`,
    activeMode: "exact",
  }));
}

function createPanel(
  nav: HTMLElement,
  amoCode: string,
  pathname: string,
  search: string,
  onNavigate: (path: string) => void,
): HTMLElement {
  const panel = document.createElement("section");
  panel.className = "qms-navigation-panel";
  panel.dataset.qmsAmoCode = amoCode;
  panel.setAttribute("aria-label", "Quality navigation");

  const header = document.createElement("div");
  header.className = "qms-navigation-panel__header";
  const title = document.createElement("strong");
  title.textContent = "Quality workspace";
  const helper = document.createElement("span");
  helper.textContent = "Routes grouped by work";
  header.append(title, helper);

  const basePath = qmsBasePath(amoCode);
  const quickLinks: NavigationLink[] = [
    { id: "quick-overview", label: "Overview", path: basePath },
    {
      id: "quick-work",
      label: "My work",
      path: qmsModulePath(amoCode, "inbox", "assigned-to-me"),
      activeMode: "prefix",
      matchPrefixes: [`${basePath}/inbox`],
    },
    {
      id: "quick-calendar",
      label: "Calendar",
      path: qmsModulePath(amoCode, "calendar", "week"),
      activeMode: "prefix",
      matchPrefixes: [`${basePath}/calendar`],
    },
    {
      id: "quick-audits",
      label: "Audit Assurance",
      path: qmsModulePath(amoCode, "audits", "dashboard"),
      activeMode: "prefix",
      matchPrefixes: [`${basePath}/audits`],
    },
  ];
  const quick = document.createElement("div");
  quick.className = "qms-navigation-quick";
  quick.setAttribute("aria-label", "Primary Quality destinations");
  for (const link of quickLinks) quick.append(createNavigationButton(link, pathname, onNavigate));

  const searchLabel = document.createElement("label");
  searchLabel.className = "qms-navigation-search";
  const searchInput = document.createElement("input");
  searchInput.type = "search";
  searchInput.className = "qms-navigation-search__input";
  searchInput.placeholder = "Find a Quality page";
  searchInput.autocomplete = "off";
  searchInput.setAttribute("aria-label", "Find a Quality page");
  searchLabel.append(searchInput);

  const sections = document.createElement("div");
  sections.className = "qms-navigation-sections";

  const auditLinks = QMS_AUDIT_DESTINATIONS.map((destination) => registeredDestinationLink(amoCode, destination));
  sections.append(createSection(
    "audits",
    "Audit Assurance",
    "Programme → Planner V2 → execute → follow-up",
    auditLinks,
    pathname,
    onNavigate,
    { prominent: true },
  ));

  const activeAudit = getActiveAuditWorkspace(pathname, amoCode);
  if (activeAudit) {
    sections.append(createSection(
      "current-audit",
      `Current audit · ${safeDecode(activeAudit.auditKey)}`,
      "Move through the active audit without returning to the register",
      currentAuditLinks(activeAudit, search),
      pathname,
      onNavigate,
      { prominent: true, open: true },
    ));
  }

  sections.append(createSection(
    "calendar",
    "Quality calendar",
    "Month, agenda, audit dates, CAR deadlines, training and reviews",
    QMS_CALENDAR_DESTINATIONS.map((destination) => registeredDestinationLink(amoCode, destination)),
    pathname,
    onNavigate,
  ));

  const aerodocEnabled = isAeroDocEnabled(nav);
  for (const group of QMS_NAVIGATION_GROUPS) {
    sections.append(createSection(
      group.id,
      group.label,
      group.description,
      moduleLinksForGroup(amoCode, group, aerodocEnabled),
      pathname,
      onNavigate,
    ));
  }

  const empty = document.createElement("div");
  empty.className = "qms-navigation-empty";
  empty.textContent = "No Quality page matches that search.";
  empty.hidden = true;

  searchInput.oninput = () => applySearch(panel, searchInput.value);
  panel.append(header, quick, searchLabel, sections, empty);
  return panel;
}

function applySearch(panel: HTMLElement, query: string): void {
  const value = normalise(query);
  const sections = Array.from(panel.querySelectorAll<HTMLDetailsElement>(".qms-nav-section"));
  let totalMatches = 0;

  for (const section of sections) {
    const links = Array.from(section.querySelectorAll<HTMLButtonElement>(".qms-nav-link"));
    let matches = 0;
    for (const link of links) {
      const visible = !value || (link.dataset.qmsSearch || "").includes(value);
      link.hidden = !visible;
      if (visible) matches += 1;
    }
    section.hidden = Boolean(value && matches === 0);
    if (value && matches > 0) section.open = true;
    totalMatches += matches;
  }

  const empty = panel.querySelector<HTMLElement>(".qms-navigation-empty");
  if (empty) empty.hidden = !value || totalMatches > 0;
}

function refreshPanel(
  panel: HTMLElement,
  pathname: string,
  onNavigate: (path: string) => void,
): void {
  const currentQuery = panel.querySelector<HTMLInputElement>(".qms-navigation-search__input")?.value || "";
  for (const button of panel.querySelectorAll<HTMLButtonElement>(".qms-nav-link")) {
    const link = linkFromButton(button);
    button.onclick = () => onNavigate(link.path);
    setButtonActive(button, matchesPath(pathname, link));
  }

  if (!currentQuery) {
    for (const section of panel.querySelectorAll<HTMLDetailsElement>(".qms-nav-section")) {
      const hasActive = Boolean(section.querySelector(".qms-nav-link--active"));
      if (hasActive) section.open = true;
    }
  }
  applySearch(panel, currentQuery);
}

function suppressLegacyNavigation(nav: HTMLElement): void {
  nav.classList.remove("sidebar__qms-nav--enhanced");
  nav.classList.add("sidebar__qms-nav--structured");
  for (const node of nav.querySelectorAll<HTMLElement>(":scope > .sidebar__qms-node")) {
    node.hidden = true;
    node.setAttribute("aria-hidden", "true");
  }
  nav.querySelector(":scope > .qms-sidebar-tools")?.remove();
  nav.querySelector(":scope > .qms-sidebar-empty")?.remove();
}

export function enhanceQmsSidebarNavigation({
  sidebar,
  amoCode,
  pathname,
  search,
  onNavigate,
}: QmsSidebarEnhancementOptions): void {
  const nav = sidebar.querySelector<HTMLElement>(QUALITY_NAV_SELECTOR);
  if (!nav) return;

  suppressLegacyNavigation(nav);
  const activeAudit = getActiveAuditWorkspace(pathname, amoCode);
  const context = `${amoCode}:${activeAudit?.auditKey || "none"}`;
  let panel = nav.querySelector<HTMLElement>(":scope > .qms-navigation-panel");
  if (panel && panel.dataset.qmsContext !== context) {
    panel.remove();
    panel = null;
  }

  if (!panel) {
    panel = createPanel(nav, amoCode, pathname, search, onNavigate);
    panel.dataset.qmsContext = context;
    nav.prepend(panel);
  }

  refreshPanel(panel, pathname, onNavigate);
}
