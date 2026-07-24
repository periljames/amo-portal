import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const distDir = path.resolve("dist");
const manifestPath = path.join(distDir, ".vite", "manifest.json");
const reportPath = path.join(distDir, "rostering-network-waterfall.json");
const baseUrl = process.env.PERF_BASE_URL || "http://127.0.0.1:4173";
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
  writeReport({
    generatedAt: new Date().toISOString(),
    passed: false,
    failures: ["Vite manifest not found. Run npm run build first."],
  });
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
const workspaceEntries = workspaceNames.map((name) => ({
  name,
  entry: entries.find(([key, record]) => sourceMatches(key, record, name)),
}));
const workspaceKeys = new Set(workspaceEntries.map(({ entry }) => entry?.[0]).filter(Boolean));
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
const missingWorkspaces = workspaceEntries
  .filter(({ entry }) => !entry)
  .map(({ name }) => name);

if (!routeEntry || missingWorkspaces.length) {
  const failures = [];
  if (!routeEntry) failures.push("Rostering route shell could not be identified from the Vite manifest.");
  if (missingWorkspaces.length) failures.push(`Missing workspace chunks: ${missingWorkspaces.join(", ")}.`);
  writeReport({
    generatedAt: new Date().toISOString(),
    manifestEntryCount: entries.length,
    passed: false,
    failures,
  });
  process.exit(1);
}

const moduleFiles = [
  routeEntry[1].file,
  ...workspaceEntries.map(({ entry }) => entry?.[1]?.file).filter(Boolean),
];
const moduleUrls = [...new Set(moduleFiles)]
  .map((file) => new URL(`/${file}`, baseUrl).href);
const profile = {
  name: "synthetic-edge-2g",
  latencyMs: 700,
  downloadBytesPerSecond: 30 * 1024,
  uploadBytesPerSecond: 15 * 1024,
};

async function applyNetworkProfile(context, page) {
  const client = await context.newCDPSession(page);
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: false });
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: profile.latencyMs,
    downloadThroughput: profile.downloadBytesPerSecond,
    uploadThroughput: profile.uploadBytesPerSecond,
    connectionType: "cellular2g",
  });
  return client;
}

async function measure(context, label) {
  const page = await context.newPage();
  await page.goto(`${baseUrl}/perf-shell.html`, { waitUntil: "domcontentloaded" });
  const client = await applyNetworkProfile(context, page);
  const result = await page.evaluate(async ({ urls, phase }) => {
    performance.clearResourceTimings();
    const moduleTimings = [];
    const phaseStart = performance.now();
    for (const url of urls) {
      const startedAt = performance.now();
      await import(url);
      moduleTimings.push({
        url,
        durationMs: Number((performance.now() - startedAt).toFixed(2)),
      });
    }
    const totalMs = Number((performance.now() - phaseStart).toFixed(2));
    const resources = performance.getEntriesByType("resource")
      .filter((entry) => entry.name.includes("/assets/"))
      .map((entry) => ({
        name: entry.name,
        initiatorType: entry.initiatorType,
        startTimeMs: Number(entry.startTime.toFixed(2)),
        durationMs: Number(entry.duration.toFixed(2)),
        transferSize: entry.transferSize,
        encodedBodySize: entry.encodedBodySize,
        decodedBodySize: entry.decodedBodySize,
      }))
      .sort((left, right) => left.startTimeMs - right.startTimeMs);
    return { phase, totalMs, moduleTimings, resources };
  }, { urls: moduleUrls, phase: label });
  await client.detach();
  await page.close();
  return result;
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ serviceWorkers: "block" });
let cold;
let warm;
try {
  cold = await measure(context, "cold-cache");
  warm = await measure(context, "warm-http-cache");
} finally {
  await context.close();
  await browser.close();
}

const budgets = {
  coldRouteActivationMs: 70_000,
  warmRouteActivationMs: 5_000,
  maximumColdAssetRequests: 80,
};
const failures = [];
if (cold.totalMs > budgets.coldRouteActivationMs) {
  failures.push(`Cold route module activation ${cold.totalMs}ms exceeds ${budgets.coldRouteActivationMs}ms.`);
}
if (warm.totalMs > budgets.warmRouteActivationMs) {
  failures.push(`Warm route module activation ${warm.totalMs}ms exceeds ${budgets.warmRouteActivationMs}ms.`);
}
if (cold.resources.length > budgets.maximumColdAssetRequests) {
  failures.push(`Cold route activation made ${cold.resources.length} asset requests; maximum is ${budgets.maximumColdAssetRequests}.`);
}

const report = {
  generatedAt: new Date().toISOString(),
  baseUrl,
  profile,
  routeSource: routeEntry[1].src || routeEntry[0],
  workspaces: workspaceEntries.map(({ name, entry }) => ({
    name,
    source: entry[1].src || entry[0],
    file: entry[1].file,
  })),
  moduleUrls,
  cold,
  warm,
  warmSpeedup: cold.totalMs && warm.totalMs
    ? Number((cold.totalMs / warm.totalMs).toFixed(2))
    : null,
  budgets,
  passed: failures.length === 0,
  failures,
};

writeReport(report);
if (failures.length) process.exit(1);
