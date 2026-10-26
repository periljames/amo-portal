import { readFileSync, writeFileSync, mkdtempSync, unlinkSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { Script } from "node:vm";
import ts from "typescript";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const temporary = mkdtempSync(join(tmpdir(), "portal-offline-audit-"));
const inventory = join(temporary, "routes.json");
try {
  const python = join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  const result = spawnSync(python, [join(root, "backend/scripts/export_offline_route_inventory.py"), inventory], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr || "API route inspection failed");
  const source = readFileSync(join(root, "frontend/src/services/offlineCapabilities.ts"), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  const manifest = {};
  const manifestSource = readFileSync(join(root, "frontend/src/services/offlineCreateRoutes.ts"), "utf8");
  new Script(ts.transpileModule(manifestSource, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)
    .runInNewContext({ exports: manifest });
  new Script(compiled).runInNewContext({ exports, require(name) {
    if (name === "./offlineCreateRoutes") return manifest;
    throw new Error(`Unexpected audit dependency: ${name}`);
  } });
  const routes = JSON.parse(readFileSync(inventory, "utf8")).map((route) => ({
    ...route, capability: exports.classifyOfflineMutation(route.path.replace(/\{[^}]+\}/g, "test-id"), route.method).capability,
  }));
  for (const create of manifest.OFFLINE_CREATE_ROUTES) {
    const effective = routes.find((route) => route.method === "POST" && route.path.replace(/\/+$/, "") === create.path);
    if (effective?.offline_create_path !== create.path) {
      throw new Error(`Offline create has no matching atomic server handler: ${create.path}`);
    }
  }
  for (const route of routes.filter((route) => route.offline_create_path)) {
    if (route.path.replace(/\/+$/, "") !== route.offline_create_path) {
      throw new Error(`Offline receipt path differs from registered route: ${route.path}`);
    }
  }
  const totals = new Map();
  for (const route of routes) {
    const row = totals.get(route.module) || { module: route.module, replay: 0, live: 0, unsupported: 0 };
    row[route.capability === "draft-safe" ? "replay" : route.capability === "live-only" ? "live" : "unsupported"]++;
    totals.set(route.module, row);
  }
  const modules = [...totals.values()].sort((a, b) => a.module.localeCompare(b.module));
  writeFileSync(join(root, "docs/offline-capability-audit.json"), JSON.stringify({
    scope: "Static route/registry coverage. This is not proof of live server acceptance or full offline workflows.",
    modules, routes,
  }, null, 2) + "\n");
  const report = [
    "# Offline capability audit", "",
    "Generated from registered API write routes and the frontend replay registry. Run `npm run audit:offline` in `frontend` to regenerate.", "",
    `${manifest.OFFLINE_CREATE_ROUTES.length} creation workflows automatically save offline through the shared JSON transport, in addition to the six existing guarded operations. New create handlers commit domain rows and replay receipts atomically. The audit verifies that every frontend creation contract has a matching registered server handler. The table identifies remaining operations without a replay contract; full offline functionality across all modules is not implemented.`, "",
    "Cached reads require a prior successful download. Fresh-every-time reads retain an encrypted offline copy. Live authority checks are excluded from stale fallback. QMS encrypted evidence and document downloads use separate explicit workflows.", "",
    "| API module | Replay-enabled write routes | Explicitly online | No replay contract |",
    "| --- | ---: | ---: | ---: |",
    ...modules.map((row) => `| ${row.module} | ${row.replay} | ${row.live} | ${row.unsupported} |`), "",
    "Cross-device updates require connection to the server. Local encrypted queues stay on the device where they were created. Conflicting revisions require review; they are not silently overwritten.", "",
    "Browser automation tests actual Chrome offline storage, reload, unchanged replay keys, shared-tab leases and conflicting edits from isolated device profiles using fixture HTTP responses. It does not replace live PostgreSQL, permissions, evidence upload and production device acceptance testing.", "",
    "This static audit does not test deployment connectivity or production end-to-end acceptance.", "",
  ];
  writeFileSync(join(root, "docs/offline-capability-audit.md"), report.join("\n"));
  console.log(`Audited ${routes.length} write routes in ${modules.length} API modules; ${routes.filter((route) => route.capability === "draft-safe").length} match replay contracts.`);
} finally {
  try { unlinkSync(inventory); rmdirSync(temporary); } catch { /* No recursive cleanup outside the generated directory. */ }
}
