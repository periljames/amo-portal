import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const distDir = path.resolve("dist");
const manifestPath = path.join(distDir, ".vite", "manifest.json");
const baseUrl = process.env.PERF_BASE_URL || "http://127.0.0.1:4173";

if (!fs.existsSync(manifestPath)) {
  console.error("Vite manifest not found. Run npm run build first.");
  process.exit(1);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const routeEntry = Object.entries(manifest).find(([key, record]) => {
  const source = String(record?.src || key).replaceAll("\\", "/");
  return source.endsWith("src/pages/rostering/WorkforceRosteringPagesV2.tsx");
});
if (!routeEntry) {
  console.error("Rostering route entry not found in Vite manifest.");
  process.exit(1);
}

const [, routeRecord] = routeEntry;
const moduleFiles = [
  routeRecord.file,
  ...(routeRecord.dynamicImports || [])
    .map((key) => manifest[key]?.file)
    .filter(Boolean),
];
const moduleUrls = [...new Set(moduleFiles)].map((file) => new URL(`/${file}`, baseUrl).href);

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

fs.writeFileSync(
  path.join(distDir, "rostering-network-waterfall.json"),
  JSON.stringify(report, null, 2),
);
console.log(JSON.stringify(report, null, 2));
if (failures.length) process.exit(1);
