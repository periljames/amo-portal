import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const manifestPath = resolve("dist/.vite/manifest.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

function requireEntry(key) {
  const entry = manifest[key];
  if (!entry) throw new Error(`[heavy-route-chunks] Missing manifest entry: ${key}`);
  return entry;
}

function dependencyClosure(key, visited = new Set()) {
  if (visited.has(key)) return visited;
  visited.add(key);
  const entry = requireEntry(key);
  for (const dependency of entry.imports || []) dependencyClosure(dependency, visited);
  return visited;
}

function containsEngine(keys, engine) {
  return [...keys].some((key) => {
    const entry = manifest[key];
    return key.includes(engine) || String(entry?.name || "").includes(engine) || String(entry?.file || "").includes(engine);
  });
}

const applicationDependencies = dependencyClosure("index.html");
if (containsEngine(applicationDependencies, "pdf-vendor")) {
  throw new Error("[heavy-route-chunks] PDF engine leaked into the application entry graph.");
}
if (containsEngine(applicationDependencies, "grid-vendor")) {
  throw new Error("[heavy-route-chunks] Grid engine leaked into the application entry graph.");
}

const documentControl = requireEntry("src/pages/DocControlPages.tsx");
if (!(documentControl.dynamicImports || []).includes("src/pages/documentControl/DocumentLibraryRegisterGrid.tsx")) {
  throw new Error("[heavy-route-chunks] Document Library register is not an on-demand chunk.");
}

const registerDependencies = dependencyClosure("src/pages/documentControl/DocumentLibraryRegisterGrid.tsx");
if (!containsEngine(registerDependencies, "grid-vendor")) {
  throw new Error("[heavy-route-chunks] Register chunk no longer owns the grid engine.");
}

const readerDependencies = dependencyClosure("src/pages/manuals/ManualReaderPage.tsx");
if (!containsEngine(readerDependencies, "pdf-vendor")) {
  throw new Error("[heavy-route-chunks] Reader chunk no longer owns the PDF engine.");
}

const entryFile = requireEntry("index.html").file;
const entryBytes = statSync(resolve("dist", entryFile)).size;
const precache = JSON.parse(readFileSync(resolve("dist/portal-precache.json"), "utf8"));
const precacheUrls = Array.isArray(precache.urls) ? precache.urls : [];
if (precacheUrls.some((url) => /(?:pdf|grid)-vendor/i.test(String(url)))) {
  throw new Error("[heavy-route-chunks] A heavy route engine leaked into the install-time service-worker precache.");
}
console.log(`[heavy-route-chunks] Entry graph excludes PDF/grid engines (${Math.round(entryBytes / 1024)} KiB application entry); ${precacheUrls.length} shell URLs install eagerly.`);
