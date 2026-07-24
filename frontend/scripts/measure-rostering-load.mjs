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
const profile = {
  name: "synthetic-edge-2g",
  latencyMs: 700,
  downloadBytesPerSecond: 30 * 1024,
  uploadBytesPerSecond: 15 * 1024,
};

function writeReport(report) {
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

function failureReport(failures, extra = {}) {
  return {
    generatedAt: new Date().toISOString(),
    baseUrl,
    profile,
    passed: false,
    failures,
    ...extra,
  };
}

if (!fs.existsSync(manifestPath)) {
  writeReport(failureReport(["Vite manifest not found. Run npm run build first."]));
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
  writeReport(failureReport(failures, { manifestEntryCount: entries.length }));
  process.exit(1);
}

function collectDependencyFiles(seedKeys) {
  const visited = new Set();
  const files = new Set();
  const visit = (key) => {
    if (!key || visited.has(key)) return;
    visited.add(key);
    const record = manifest[key];
    if (!record) return;
    if (record.file) files.add(record.file);
    for (const cssFile of record.css || []) files.add(cssFile);
    for (const assetFile of record.assets || []) files.add(assetFile);
    for (const importKey of record.imports || []) visit(importKey);
  };
  for (const key of seedKeys) visit(key);
  return [...files].sort();
}

const workspaceMap = new Map(workspaceEntries.map(({ name, entry }) => [name, entry]));
const routeKey = routeEntry[0];
const scenarios = {
  planner: collectDependencyFiles([routeKey, workspaceMap.get("UnifiedRosterPlanner")[0]]),
  setup: collectDependencyFiles([routeKey, workspaceMap.get("UnifiedRosterSettings")[0]]),
  myRoster: collectDependencyFiles([routeKey, workspaceMap.get("MyRosterWorkspace")[0]]),
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

async function measureScenario(browser, name, files) {
  const context = await browser.newContext({ serviceWorkers: "block" });
  const urls = files.map((file) => new URL(`/${file}`, baseUrl).href);

  async function measurePhase(phase) {
    const page = await context.newPage();
    await page.goto(`${baseUrl}/perf-shell.html`, { waitUntil: "domcontentloaded" });
    const client = await applyNetworkProfile(context, page);
    const result = await page.evaluate(async ({ assetUrls, scenario, label }) => {
      performance.clearResourceTimings();
      const startedAt = performance.now();
      const responses = await Promise.all(assetUrls.map(async (url) => {
        const response = await fetch(url, { cache: "default", credentials: "same-origin" });
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
        await response.arrayBuffer();
        return { url, status: response.status };
      }));
      const totalMs = Number((performance.now() - startedAt).toFixed(2));
      const resources = performance.getEntriesByType("resource")
        .filter((entry) => assetUrls.includes(entry.name))
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
      return { scenario, phase: label, totalMs, responses, resources };
    }, { assetUrls: urls, scenario: name, label: phase });
    await client.detach();
    await page.close();
    return result;
  }

  try {
    const cold = await measurePhase("cold-cache");
    const warm = await measurePhase("warm-http-cache");
    return {
      name,
      files,
      assetCount: files.length,
      cold,
      warm,
      warmSpeedup: cold.totalMs && warm.totalMs
        ? Number((cold.totalMs / warm.totalMs).toFixed(2))
        : null,
    };
  } finally {
    await context.close();
  }
}

const budgets = {
  coldRouteAssetsMs: 70_000,
  warmRouteAssetsMs: 5_000,
  maximumRouteAssetRequests: 80,
};
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const measurements = [];
  for (const [name, files] of Object.entries(scenarios)) {
    measurements.push(await measureScenario(browser, name, files));
  }

  const failures = [];
  for (const measurement of measurements) {
    if (measurement.cold.totalMs > budgets.coldRouteAssetsMs) {
      failures.push(`${measurement.name} cold assets ${measurement.cold.totalMs}ms exceed ${budgets.coldRouteAssetsMs}ms.`);
    }
    if (measurement.warm.totalMs > budgets.warmRouteAssetsMs) {
      failures.push(`${measurement.name} warm assets ${measurement.warm.totalMs}ms exceed ${budgets.warmRouteAssetsMs}ms.`);
    }
    if (measurement.assetCount > budgets.maximumRouteAssetRequests) {
      failures.push(`${measurement.name} requires ${measurement.assetCount} route assets; maximum is ${budgets.maximumRouteAssetRequests}.`);
    }
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
    measurements,
    budgets,
    passed: failures.length === 0,
    failures,
  };
  writeReport(report);
  if (failures.length) process.exitCode = 1;
} catch (error) {
  writeReport(failureReport([
    error instanceof Error ? `${error.name}: ${error.message}` : String(error),
  ], {
    routeSource: routeEntry[1].src || routeEntry[0],
    scenarios,
  }));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
