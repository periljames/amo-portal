import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());

function replaceOnce(text, oldValue, newValue, label) {
  const count = text.split(oldValue).length - 1;
  if (count !== 1) throw new Error(`Expected one ${label}, found ${count}`);
  return text.replace(oldValue, newValue);
}

const workspacePath = path.join(root, "src/pages/reliability/ReliabilityWorkspacePage.tsx");
let workspace = fs.readFileSync(workspacePath, "utf8");
workspace = replaceOnce(
  workspace,
  'import ReliabilityReportsView from "./ReliabilityReportsView";\n',
  'import ReliabilityReportsView from "./ReliabilityReportsView";\nimport { FracasGovernancePanel, OccurrenceProvenancePanel, ReliabilityAdvancedView, type AdvancedReliabilityViewId } from "./ReliabilityAdvancedViews";\n',
  "advanced Reliability import",
);
workspace = replaceOnce(
  workspace,
  `type ViewId =
  | "workbench" | "events" | "alerts" | "cases" | "fleet" | "systems"
  | "components" | "engines" | "program" | "changes" | "meetings"
  | "data-quality" | "reports";`,
  `type ViewId =
  | "workbench" | "events" | "alerts" | "cases" | "fleet" | "systems"
  | "components" | "engines" | "calculations" | "program" | "changes"
  | "handoffs" | "meetings" | "authority" | "ai" | "compliance"
  | "sources" | "ingestion" | "data-quality" | "reports";`,
  "Reliability ViewId",
);
workspace = replaceOnce(
  workspace,
  `const VIEWS = new Set<ViewId>([
  "workbench", "events", "alerts", "cases", "fleet", "systems", "components",
  "engines", "program", "changes", "meetings", "data-quality", "reports",
]);`,
  `const VIEWS = new Set<ViewId>([
  "workbench", "events", "alerts", "cases", "fleet", "systems", "components",
  "engines", "calculations", "program", "changes", "handoffs", "meetings",
  "authority", "ai", "compliance", "sources", "ingestion", "data-quality", "reports",
]);

const ADVANCED_VIEWS = new Set<AdvancedReliabilityViewId>([
  "compliance", "sources", "ingestion", "data-quality", "fleet", "systems",
  "components", "calculations", "program", "changes", "handoffs", "meetings",
  "authority", "ai",
]);`,
  "Reliability VIEWS set",
);
workspace = workspace.replace(/\nconst FOUNDATION:[\s\S]*?\n};\n\nfunction displayDate/, "\nfunction displayDate");
workspace = workspace.replace('function routeState(pathname: string): RouteState {', 'export function routeState(pathname: string): RouteState {');
workspace = workspace.replace('if (route.view === "workbench" || route.view === "data-quality") {', 'if (route.view === "workbench") {');
workspace = replaceOnce(
  workspace,
  `<Link className="btn btn-secondary" to={route.view === "reports" ? basePath : \`\${basePath}/reports\`}>{route.view === "reports" ? "Reliability workbench" : "Controlled reports"}</Link>`,
  `<div className="reliability-v2__actions"><Link className="btn btn-secondary" to={\`\${basePath}/compliance\`}>Compliance control</Link><Link className="btn btn-secondary" to={route.view === "reports" ? basePath : \`\${basePath}/reports\`}>{route.view === "reports" ? "Reliability workbench" : "Controlled reports"}</Link></div>`,
  "Reliability header actions",
);
const oldRender = `function renderView(props: ViewProps): React.ReactNode {
  const { route, basePath } = props;
  if (route.view === "workbench") return props.workbench ? <Workbench data={props.workbench} basePath={basePath} /> : null;
  if (route.view === "data-quality") return props.workbench ? <DataQuality items={props.workbench.data_freshness} /> : null;
  if (route.view === "events") return props.event ? <EventDetail item={props.event} basePath={basePath} /> : <EventRegister rows={props.events} basePath={basePath} />;
  if (route.view === "alerts") return props.alert ? <AlertDetail item={props.alert} basePath={basePath} /> : <AlertRegister rows={props.alerts} basePath={basePath} />;
  if (route.view === "cases") return props.fracasCase ? <CaseDetail item={props.fracasCase} actions={props.actions} basePath={basePath} /> : <CaseRegister rows={props.cases} basePath={basePath} />;
  if (route.view === "engines") return <EngineRegister rows={props.engines} />;
  if (route.view === "reports") return <ReliabilityReportsView />;
  const foundation = FOUNDATION[route.view];
  return foundation ? <FoundationView {...foundation} /> : null;
}`;
const newRender = `function renderView(props: ViewProps): React.ReactNode {
  const { route, basePath } = props;
  if (route.view === "workbench") return props.workbench ? <Workbench data={props.workbench} basePath={basePath} /> : null;
  if (route.view === "events") return props.event ? <><EventDetail item={props.event} basePath={basePath} /><OccurrenceProvenancePanel eventId={props.event.id} /></> : <EventRegister rows={props.events} basePath={basePath} />;
  if (route.view === "alerts") return props.alert ? <AlertDetail item={props.alert} basePath={basePath} /> : <AlertRegister rows={props.alerts} basePath={basePath} />;
  if (route.view === "cases") return props.fracasCase ? <><CaseDetail item={props.fracasCase} actions={props.actions} basePath={basePath} /><FracasGovernancePanel caseId={props.fracasCase.id} /></> : <CaseRegister rows={props.cases} basePath={basePath} />;
  if (route.view === "engines") return <EngineRegister rows={props.engines} />;
  if (route.view === "reports") return <ReliabilityReportsView />;
  if (ADVANCED_VIEWS.has(route.view as AdvancedReliabilityViewId)) return <ReliabilityAdvancedView view={route.view as AdvancedReliabilityViewId} basePath={basePath} />;
  return null;
}`;
workspace = replaceOnce(workspace, oldRender, newRender, "renderView");
workspace = workspace.replace(/\nfunction DataQuality\([\s\S]*?\n}\n\nfunction FoundationView\([\s\S]*?\n}\n/, "\n");
fs.writeFileSync(workspacePath, workspace.replace(/\s+$/, "") + "\n", "utf8");

const advancedPath = path.join(root, "src/pages/reliability/ReliabilityAdvancedViews.tsx");
let advanced = fs.readFileSync(advancedPath, "utf8");
advanced = advanced.replace("  transitionReliabilityAiReview,\n", "  decideReliabilityAiReview,\n");
advanced = advanced.replaceAll("transitionReliabilityAiReview(", "decideReliabilityAiReview(");
fs.writeFileSync(advancedPath, advanced.replace(/\s+$/, "") + "\n", "utf8");

const manifestPath = path.join(root, "src/app/portalRouteManifest.ts");
let manifest = fs.readFileSync(manifestPath, "utf8");
const commandOld = `          { id: "reliability-workbench", label: "Workbench", path: \`\${base}/reliability\`, exact: true },
          { id: "reliability-events", label: "Occurrences", path: \`\${base}/reliability/events\` },
          { id: "reliability-alerts", label: "Alerts", path: \`\${base}/reliability/alerts\` },
          { id: "reliability-fracas", label: "FRACAS", path: \`\${base}/reliability/cases\` },`;
const commandNew = `${commandOld}
          { id: "reliability-sources", label: "Source Control", path: \`\${base}/reliability/sources\` },
          { id: "reliability-ingestion", label: "Ingestion Batches", path: \`\${base}/reliability/ingestion\` },`;
manifest = replaceOnce(manifest, commandOld, commandNew, "Reliability command navigation");
const analysisOld = `          { id: "reliability-engines", label: "Engine Trends", path: \`\${base}/reliability/engines\` },`;
const analysisNew = `${analysisOld}
          { id: "reliability-calculations", label: "KPI Calculations", path: \`\${base}/reliability/calculations\` },`;
manifest = replaceOnce(manifest, analysisOld, analysisNew, "Reliability analysis navigation");
const governanceOld = `          { id: "reliability-program", label: "Programme", path: \`\${base}/reliability/program\` },
          { id: "reliability-changes", label: "Programme Changes", path: \`\${base}/reliability/changes\` },
          { id: "reliability-meetings", label: "Review Meetings", path: \`\${base}/reliability/meetings\` },
          { id: "reliability-reports", label: "Controlled Reports", path: \`\${base}/reliability/reports\` },
          { id: "reliability-data-quality", label: "Data Quality", path: \`\${base}/reliability/data-quality\` },`;
const governanceNew = `          { id: "reliability-compliance", label: "Compliance Control", path: \`\${base}/reliability/compliance\` },
          { id: "reliability-program", label: "Programme", path: \`\${base}/reliability/program\` },
          { id: "reliability-changes", label: "Programme Changes", path: \`\${base}/reliability/changes\` },
          { id: "reliability-handoffs", label: "Module Handoffs", path: \`\${base}/reliability/handoffs\` },
          { id: "reliability-meetings", label: "Review Meetings", path: \`\${base}/reliability/meetings\` },
          { id: "reliability-authority", label: "Authority Packages", path: \`\${base}/reliability/authority\` },
          { id: "reliability-ai", label: "AI Reviews", path: \`\${base}/reliability/ai\` },
          { id: "reliability-reports", label: "Controlled Reports", path: \`\${base}/reliability/reports\` },
          { id: "reliability-data-quality", label: "Data Quality", path: \`\${base}/reliability/data-quality\` },`;
manifest = replaceOnce(manifest, governanceOld, governanceNew, "Reliability governance navigation");
fs.writeFileSync(manifestPath, manifest.replace(/\s+$/, "") + "\n", "utf8");

const testPath = path.join(root, "src/app/portalRouteManifest.test.ts");
let test = fs.readFileSync(testPath, "utf8");
const testAnchor = `    expect(paths.get("reliability-data-quality")).toBe("/maintenance/tenant-a/reliability/data-quality");`;
const testAddition = `${testAnchor}
    expect(paths.get("reliability-sources")).toBe("/maintenance/tenant-a/reliability/sources");
    expect(paths.get("reliability-ingestion")).toBe("/maintenance/tenant-a/reliability/ingestion");
    expect(paths.get("reliability-calculations")).toBe("/maintenance/tenant-a/reliability/calculations");
    expect(paths.get("reliability-compliance")).toBe("/maintenance/tenant-a/reliability/compliance");
    expect(paths.get("reliability-handoffs")).toBe("/maintenance/tenant-a/reliability/handoffs");
    expect(paths.get("reliability-authority")).toBe("/maintenance/tenant-a/reliability/authority");
    expect(paths.get("reliability-ai")).toBe("/maintenance/tenant-a/reliability/ai");`;
if (!test.includes('paths.get("reliability-sources")')) test = replaceOnce(test, testAnchor, testAddition, "Reliability navigation test anchor");
fs.writeFileSync(testPath, test.replace(/\s+$/, "") + "\n", "utf8");

console.log("Complete Reliability workspace, routes and navigation wired.");
