import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const root = path.resolve("dist");
const manifestPath = path.join(root, ".vite", "manifest.json");
if (!fs.existsSync(manifestPath)) {
  console.error("Vite manifest not found. Run npm run build first.");
  process.exit(1);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const entries = Object.entries(manifest);
const isRosteringSource = (key, record) => {
  const source = String(record?.src || key).replaceAll("\\", "/");
  return source.includes("src/pages/rostering/");
};
const routeEntry = entries.find(([key, record]) => {
  const source = String(record?.src || key).replaceAll("\\", "/");
  return source.endsWith("src/pages/rostering/WorkforceRosteringPagesV2.tsx");
});

if (!routeEntry) {
  console.error("Rostering route manifest entry was not generated.");
  process.exit(1);
}

function sizeFor(file) {
  const absolute = path.join(root, file);
  const buffer = fs.readFileSync(absolute);
  return {
    file,
    raw: buffer.byteLength,
    gzip: zlib.gzipSync(buffer).byteLength,
    brotli: zlib.brotliCompressSync(buffer).byteLength,
  };
}

const routeRecords = entries
  .filter(([key, record]) => isRosteringSource(key, record) && record?.file?.endsWith(".js"))
  .map(([key, record]) => ({
    source: record.src || key,
    isEntry: Boolean(record.isEntry),
    isDynamicEntry: Boolean(record.isDynamicEntry),
    imports: record.imports || [],
    dynamicImports: record.dynamicImports || [],
    ...sizeFor(record.file),
  }))
  .sort((left, right) => right.brotli - left.brotli);

const [, routeRecord] = routeEntry;
const routeShell = sizeFor(routeRecord.file);
const totals = routeRecords.reduce(
  (sum, row) => ({
    raw: sum.raw + row.raw,
    gzip: sum.gzip + row.gzip,
    brotli: sum.brotli + row.brotli,
  }),
  { raw: 0, gzip: 0, brotli: 0 },
);
const directLazyWorkspaces = routeRecord.dynamicImports || [];
const budgets = {
  minimumLazyWorkspaces: 7,
  routeShellBrotliBytes: 90 * 1024,
  largestWorkspaceBrotliBytes: 220 * 1024,
  allRosteringSourceBrotliBytes: 900 * 1024,
};
const largestWorkspace = routeRecords[0] || routeShell;
const failures = [];

if (directLazyWorkspaces.length < budgets.minimumLazyWorkspaces) {
  failures.push(`Expected at least ${budgets.minimumLazyWorkspaces} lazy rostering workspaces; found ${directLazyWorkspaces.length}.`);
}
if (routeShell.brotli > budgets.routeShellBrotliBytes) {
  failures.push(`Rostering route shell Brotli size ${routeShell.brotli} exceeds ${budgets.routeShellBrotliBytes}.`);
}
if (largestWorkspace.brotli > budgets.largestWorkspaceBrotliBytes) {
  failures.push(`Largest rostering source chunk ${largestWorkspace.file} Brotli size ${largestWorkspace.brotli} exceeds ${budgets.largestWorkspaceBrotliBytes}.`);
}
if (totals.brotli > budgets.allRosteringSourceBrotliBytes) {
  failures.push(`All rostering source chunks Brotli size ${totals.brotli} exceeds ${budgets.allRosteringSourceBrotliBytes}.`);
}

const report = {
  generatedAt: new Date().toISOString(),
  routeSource: routeRecord.src || routeEntry[0],
  routeShell,
  directLazyWorkspaces,
  routeRecords,
  totals,
  budgets,
  passed: failures.length === 0,
  failures,
  estimatedEdgeTransferSeconds: Number((totals.brotli / (30 * 1024)).toFixed(2)),
};

fs.writeFileSync(path.join(root, "rostering-perf-report.json"), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
if (failures.length) process.exit(1);
