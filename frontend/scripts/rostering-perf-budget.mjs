import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const root = path.resolve("dist");
const manifestPath = path.join(root, ".vite", "manifest.json");
const reportPath = path.join(root, "rostering-perf-report.json");
const workspaceNames = [
  "CapacityBoard",
  "ComplianceImpact",
  "MyRosterWorkspace",
  "RosterDashboard",
  "RosterReports",
  "UnifiedRosterPlanner",
  "UnifiedRosterSettings",
];

function writeReport(report) {
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

if (!fs.existsSync(manifestPath)) {
  const report = {
    generatedAt: new Date().toISOString(),
    passed: false,
    failures: ["Vite manifest not found. Run npm run build first."],
  };
  writeReport(report);
  process.exit(1);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const entries = Object.entries(manifest);
const normalizedSource = (key, record) => String(record?.src || key).replaceAll("\\", "/");
const sourceMatches = (key, record, token) => {
  const source = normalizedSource(key, record).toLowerCase();
  const file = String(record?.file || "").toLowerCase();
  return source.includes(token.toLowerCase()) || file.includes(token.toLowerCase());
};

function sizeFor(file) {
  if (!file) return null;
  const absolute = path.join(root, file);
  if (!fs.existsSync(absolute)) return null;
  const buffer = fs.readFileSync(absolute);
  return {
    file,
    raw: buffer.byteLength,
    gzip: zlib.gzipSync(buffer).byteLength,
    brotli: zlib.brotliCompressSync(buffer).byteLength,
  };
}

function recordFor(entry) {
  if (!entry) return null;
  const [key, record] = entry;
  const size = sizeFor(record.file);
  if (!size) return null;
  return {
    key,
    source: record.src || key,
    isEntry: Boolean(record.isEntry),
    isDynamicEntry: Boolean(record.isDynamicEntry),
    imports: record.imports || [],
    dynamicImports: record.dynamicImports || [],
    ...size,
  };
}

const workspaceEntries = workspaceNames.map((name) => ({
  name,
  entry: entries.find(([key, record]) => sourceMatches(key, record, name)),
}));
const workspaceKeys = new Set(
  workspaceEntries.map(({ entry }) => entry?.[0]).filter(Boolean),
);
const explicitRouteEntry = entries.find(([key, record]) =>
  sourceMatches(key, record, "WorkforceRosteringPagesV2"),
);
const graphRouteEntry = entries
  .map((entry) => ({
    entry,
    workspaceEdges: (entry[1]?.dynamicImports || [])
      .filter((key) => workspaceKeys.has(key)).length,
  }))
  .sort((left, right) => right.workspaceEdges - left.workspaceEdges)[0];
const routeEntry = explicitRouteEntry
  || (graphRouteEntry?.workspaceEdges >= workspaceNames.length ? graphRouteEntry.entry : null);

const routeShell = recordFor(routeEntry);
const workspaceRecords = workspaceEntries
  .map(({ name, entry }) => ({ name, record: recordFor(entry) }))
  .filter(({ record }) => Boolean(record))
  .map(({ name, record }) => ({ name, ...record }));
const rosteringSourceRecords = entries
  .filter(([key, record]) => {
    const source = normalizedSource(key, record);
    return source.includes("src/pages/rostering/") && record?.file?.endsWith(".js");
  })
  .map(recordFor)
  .filter(Boolean);
const routeRecordsByFile = new Map();
for (const row of [routeShell, ...workspaceRecords, ...rosteringSourceRecords]) {
  if (row?.file) routeRecordsByFile.set(row.file, row);
}
const routeRecords = [...routeRecordsByFile.values()]
  .sort((left, right) => right.brotli - left.brotli);
const totals = routeRecords.reduce(
  (sum, row) => ({
    raw: sum.raw + row.raw,
    gzip: sum.gzip + row.gzip,
    brotli: sum.brotli + row.brotli,
  }),
  { raw: 0, gzip: 0, brotli: 0 },
);
const budgets = {
  requiredLazyWorkspaces: workspaceNames.length,
  routeShellBrotliBytes: 90 * 1024,
  largestWorkspaceBrotliBytes: 220 * 1024,
  allRosteringSourceBrotliBytes: 900 * 1024,
};
const failures = [];
const missingWorkspaces = workspaceEntries
  .filter(({ entry }) => !entry)
  .map(({ name }) => name);
const largestWorkspace = [...workspaceRecords]
  .sort((left, right) => right.brotli - left.brotli)[0] || null;

if (!routeShell) {
  failures.push("Could not identify the rostering route shell from the Vite manifest or lazy-workspace graph.");
}
if (missingWorkspaces.length) {
  failures.push(`Missing lazy rostering workspace chunks: ${missingWorkspaces.join(", ")}.`);
}
if (workspaceRecords.length < budgets.requiredLazyWorkspaces) {
  failures.push(`Expected ${budgets.requiredLazyWorkspaces} lazy rostering workspaces; found ${workspaceRecords.length}.`);
}
if (routeShell && routeShell.brotli > budgets.routeShellBrotliBytes) {
  failures.push(`Rostering route shell Brotli size ${routeShell.brotli} exceeds ${budgets.routeShellBrotliBytes}.`);
}
if (largestWorkspace && largestWorkspace.brotli > budgets.largestWorkspaceBrotliBytes) {
  failures.push(`Largest rostering workspace ${largestWorkspace.name} Brotli size ${largestWorkspace.brotli} exceeds ${budgets.largestWorkspaceBrotliBytes}.`);
}
if (totals.brotli > budgets.allRosteringSourceBrotliBytes) {
  failures.push(`All measured rostering source chunks Brotli size ${totals.brotli} exceeds ${budgets.allRosteringSourceBrotliBytes}.`);
}

const report = {
  generatedAt: new Date().toISOString(),
  routeSource: routeShell?.source || null,
  routeShell,
  workspaceRecords,
  routeRecords,
  totals,
  budgets,
  manifestEntryCount: entries.length,
  passed: failures.length === 0,
  failures,
  estimatedEdgeTransferSeconds: Number((totals.brotli / (30 * 1024)).toFixed(2)),
};

writeReport(report);
if (failures.length) process.exit(1);
