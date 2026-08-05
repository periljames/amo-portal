import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = join(projectRoot, "src");

function fail(message) {
  console.error(`[modal-layer] ${message}`);
  process.exitCode = 1;
}

function read(relativePath) {
  const absolutePath = join(projectRoot, relativePath);
  if (!existsSync(absolutePath)) {
    fail(`Missing required file: ${relativePath}`);
    return "";
  }
  return readFileSync(absolutePath, "utf8");
}

function walk(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolutePath = join(directory, entry);
    if (statSync(absolutePath).isDirectory()) files.push(...walk(absolutePath));
    else files.push(absolutePath);
  }
  return files;
}

const guard = read("src/components/shared/ModalTopLayerGuard.tsx");
const guardCss = read("src/styles/modal-top-layer.css");
const main = read("src/main.tsx");
const routeGate = read("src/components/QMS/QualityEnhancementsRouteGate.tsx");
const standaloneManuals = read("src/standalone/manuals-main.tsx");

for (const contract of [
  "MutationObserver",
  "showPopover",
  "[aria-modal=\"true\"]",
  "selectTopLayerHost",
  "portal-modal-fallback-ancestor",
]) {
  if (!guard.includes(contract)) fail(`ModalTopLayerGuard is missing ${contract}`);
}

if (!guardCss.includes(".portal-modal-top-layer--surface")) fail("Top-layer surface styling is missing");
if (!guardCss.includes(".portal-modal-top-layer--host")) fail("Top-layer host styling is missing");
if (guardCss.includes("backdrop-filter: blur")) fail("The portal modal layer must not blur dialog content");
if (!main.includes("<QualityEnhancementsRouteGate />")) fail("The primary portal entry no longer mounts its runtime route gate");
if (!routeGate.includes("<ModalTopLayerGuard />")) fail("The primary portal entry no longer mounts ModalTopLayerGuard");
if (!standaloneManuals.includes("<ModalTopLayerGuard />")) fail("The standalone manuals entry no longer mounts ModalTopLayerGuard");

const sourceFiles = walk(sourceRoot).filter((path) => path.endsWith(".tsx") && !path.includes(".test."));
const dialogFiles = [];
const missingModalSemantics = [];

for (const absolutePath of sourceFiles) {
  const content = readFileSync(absolutePath, "utf8");
  const hasDialogRole = /role\s*=\s*["']dialog["']/.test(content);
  const hasAriaModal = /aria-modal\s*=/.test(content);
  if (hasDialogRole || hasAriaModal) dialogFiles.push(relative(projectRoot, absolutePath));
  if (hasDialogRole && !hasAriaModal) missingModalSemantics.push(relative(projectRoot, absolutePath));
}

if (!dialogFiles.length) fail("No modal surfaces were found; the source audit is not exercising the portal");
if (missingModalSemantics.length) {
  fail(`Dialog surfaces missing aria-modal and therefore bypassing the global layer:\n${missingModalSemantics.join("\n")}`);
}

if (!process.exitCode) {
  console.log(`[modal-layer] Verified ${dialogFiles.length} modal source files across both portal entry points.`);
}
