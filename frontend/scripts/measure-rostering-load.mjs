import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const distDir = path.resolve("dist");
const manifestPath = path.join(distDir, ".vite", "manifest.json");
const reportPath = path.join(distDir, "rostering-network-waterfall.json");
const baseUrl = process.env.PERF_BASE_URL || "http://127.0.0.1:4173";

// These are the current first-level Rostering workspaces. Capacity and legacy
// report components are second-level chunks inside RosterOperationsWorkspace.
const workspaceNames = [
  "RosterDashboard",
  "UnifiedRosterPlanner",
  "RosterOperationsWorkspace",
  "ComplianceImpact",
  "MyRosterWorkspace",
  "WorkforceHrWorkspace",
  "RosteringSetupWorkspace",
];
const profile = {
  name: "synthetic-edge-2g",
  latencyMs: 700,
  downloadBytesPerSecond: 30 * 1024,
  uploadBytesPerSecond: 15 * 1024,
};
const phaseMethodology = {
  cold: "Empty Chromium HTTP cache over the synthetic edge-2G profile.",
  prime: "Unthrottled Chromium fetch with bounded retries populates the browser HTTP cache.",
  warm: "Force-cache replay from the populated Chromium HTTP cache; every route asset must be verified as a cache hit.",
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
    phaseMethodology,
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
  sourceMatches(key, record, "WorkforceRosteringPagesV2")
  || sourceMatches(key, record, "RosteringPages"),
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
  setup: collectDependencyFiles([routeKey, workspaceMap.get("RosteringSetupWorkspace")[0]]),
  workforce: collectDependencyFiles([routeKey, workspaceMap.get("WorkforceHrWorkspace")[0]]),
};

async function createNetworkClient(context, page, phase) {
  const client = await context.newCDPSession(page);
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: false });

  if (phase === "cold-cache") {
    await client.send("Network.clearBrowserCache");
    await client.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: profile.latencyMs,
      downloadThroughput: profile.downloadBytesPerSecond,
      uploadThroughput: profile.uploadBytesPerSecond,
      connectionType: "cellular2g",
    });
  } else {
    await client.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
      connectionType: "none",
    });
  }

  return client;
}

async function fetchAssets(page, assetUrls, options) {
  return page.evaluate(async ({ urls, cacheMode, retries, retryDelayMs, label }) => {
    const sleep = (duration) => new Promise((resolve) => window.setTimeout(resolve, duration));
    const fetchWithRetry = async (url) => {
      let lastError;
      for (let attempt = 1; attempt <= retries; attempt += 1) {
        try {
          const response = await fetch(url, {
            cache: cacheMode,
            credentials: "same-origin",
          });
          if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}: ${url}`);
          }
          await response.arrayBuffer();
          return { url, status: response.status, attempts: attempt };
        } catch (error) {
          lastError = error;
          if (attempt < retries) await sleep(retryDelayMs * attempt);
        }
      }
      throw lastError instanceof Error ? lastError : new Error(`Failed to fetch ${url}`);
    };

    performance.clearResourceTimings();
    const startedAt = performance.now();
    const responses = await Promise.all(urls.map(fetchWithRetry));
    const totalMs = Number((performance.now() - startedAt).toFixed(2));
    const resources = performance.getEntriesByType("resource")
      .filter((entry) => urls.includes(entry.name))
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
    return { phase: label, totalMs, responses, resources };
  }, {
    urls: assetUrls,
    cacheMode: options.cacheMode,
    retries: options.retries,
    retryDelayMs: options.retryDelayMs,
    label: options.label,
  });
}

function observeCacheHits(client, expectedUrls) {
  const expected = new Set(expectedUrls);
  const requestUrls = new Map();
  const cacheHits = new Set();

  client.on("Network.requestWillBeSent", ({ requestId, request }) => {
    if (expected.has(request.url)) requestUrls.set(requestId, request.url);
  });
  client.on("Network.requestServedFromCache", ({ requestId }) => {
    const url = requestUrls.get(requestId);
    if (url) cacheHits.add(url);
  });
  client.on("Network.responseReceived", ({ requestId, response }) => {
    const url = requestUrls.get(requestId) || response.url;
    if (expected.has(url) && (response.fromDiskCache || response.fromPrefetchCache)) {
      cacheHits.add(url);
    }
  });

  return cacheHits;
}

async function openMeasurementPage(context) {
  const page = await context.newPage();
  await page.goto(`${baseUrl}/perf-shell.html`, { waitUntil: "domcontentloaded" });
  return page;
}

async function measureScenario(browser, name, files) {
  const context = await browser.newContext({ serviceWorkers: "block" });
  const urls = files.map((file) => new URL(`/${file}`, baseUrl).href);

  try {
    const coldPage = await openMeasurementPage(context);
    const coldClient = await createNetworkClient(context, coldPage, "cold-cache");
    const coldResult = await fetchAssets(coldPage, urls, {
      cacheMode: "reload",
      retries: 2,
      retryDelayMs: 500,
      label: "cold-cache",
    });
    await coldClient.detach();
    await coldPage.close();

    // Explicitly prime the Chromium cache online. Workflow curl checks verify
    // server availability, but only browser requests can populate this cache.
    const primePage = await openMeasurementPage(context);
    const primeClient = await createNetworkClient(context, primePage, "cache-prime");
    const primeResult = await fetchAssets(primePage, urls, {
      cacheMode: "reload",
      retries: 3,
      retryDelayMs: 400,
      label: "cache-prime",
    });
    await primeClient.detach();
    await primePage.close();

    const warmPage = await openMeasurementPage(context);
    const warmClient = await createNetworkClient(context, warmPage, "warm-http-cache");
    const cacheHits = observeCacheHits(warmClient, urls);
    const warmResult = await fetchAssets(warmPage, urls, {
      cacheMode: "force-cache",
      retries: 1,
      retryDelayMs: 0,
      label: "warm-http-cache",
    });
    await warmPage.waitForTimeout(50);

    const timingCacheHits = new Set(
      warmResult.resources
        .filter((resource) => resource.transferSize === 0 && resource.decodedBodySize > 0)
        .map((resource) => resource.name),
    );
    const verifiedCacheHits = new Set([...cacheHits, ...timingCacheHits]);
    const missingCacheHits = urls.filter((url) => !verifiedCacheHits.has(url));

    await warmClient.detach();
    await warmPage.close();

    const cold = { scenario: name, ...coldResult };
    const prime = { scenario: name, ...primeResult };
    const warm = {
      scenario: name,
      ...warmResult,
      verifiedCacheHitCount: verifiedCacheHits.size,
      missingCacheHits,
    };

    return {
      name,
      files,
      assetCount: files.length,
      cold,
      prime,
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
    if (measurement.warm.missingCacheHits.length) {
      failures.push(`${measurement.name} warm cache missed ${measurement.warm.missingCacheHits.length} route asset(s): ${measurement.warm.missingCacheHits.join(", ")}.`);
    }
    if (measurement.assetCount > budgets.maximumRouteAssetRequests) {
      failures.push(`${measurement.name} requires ${measurement.assetCount} route assets; maximum is ${budgets.maximumRouteAssetRequests}.`);
    }
  }

  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    profile,
    phaseMethodology,
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
