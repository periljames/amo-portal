import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = path.resolve(process.cwd());
const src = path.join(root, "src");
const styles = path.join(src, "styles");
const failures = [];

function read(file) {
  return fs.readFileSync(file, "utf8");
}

function fail(message) {
  failures.push(message);
}

const mainPath = path.join(src, "main.tsx");
const main = read(mainPath);
const styleImports = [...main.matchAll(/import\s+["'](\.\/styles\/[^"']+\.css)["'];?/g)].map((match) => match[1]);
if (styleImports.length !== 1 || styleImports[0] !== "./styles/index.css") {
  fail(`main.tsx must import only ./styles/index.css; found ${JSON.stringify(styleImports)}`);
}

const indexPath = path.join(styles, "index.css");
const index = read(indexPath);
const requiredOrder = [
  "./global.css",
  "./tokens.css",
  "./base.css",
  "./theme-contract.css",
  "./theme-module-repairs.css",
  "./foundations/forms-and-overlays.css",
  "./foundations/layout-safety.css",
  "./foundations/appearance.css",
];
let previous = -1;
for (const required of requiredOrder) {
  const offset = index.indexOf(`@import "${required}"`);
  if (offset < 0) fail(`styles/index.css is missing ${required}`);
  if (offset >= 0 && offset <= previous) fail(`styles/index.css loads ${required} out of contract order`);
  if (offset >= 0) previous = offset;
}

function cssFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return cssFiles(target);
    return entry.name.endsWith(".css") ? [target] : [];
  });
}

const files = cssFiles(styles);
for (const file of files) {
  const content = read(file);
  const relative = path.relative(root, file).replaceAll(path.sep, "/");
  const selfReferences = [...content.matchAll(/(--[\w-]+)\s*:\s*var\(\s*\1(?:\s*[,)]|\s*\))/g)];
  for (const match of selfReferences) fail(`${relative} contains recursive custom property ${match[1]}`);
}

const graph = new Map();
for (const file of files) {
  const imports = [...read(file).matchAll(/@import\s+["']([^"']+)["']/g)]
    .map((match) => match[1])
    .filter((value) => value.startsWith("."))
    .map((value) => {
      const target = path.resolve(path.dirname(file), value);
      return path.extname(target) ? target : `${target}.css`;
    })
    .filter((target) => fs.existsSync(target));
  graph.set(file, imports);
}

const visiting = new Set();
const visited = new Set();
function visit(file, trail = []) {
  if (visiting.has(file)) {
    const cycle = [...trail, file].map((item) => path.relative(root, item)).join(" -> ");
    fail(`CSS import cycle detected: ${cycle}`);
    return;
  }
  if (visited.has(file)) return;
  visiting.add(file);
  for (const dependency of graph.get(file) || []) visit(dependency, [...trail, file]);
  visiting.delete(file);
  visited.add(file);
}
for (const file of graph.keys()) visit(file);

const contract = read(path.join(styles, "foundations", "forms-and-overlays.css"));
for (const requiredSelector of ['[role="dialog"]', "textarea", "select option", ":-webkit-autofill"]) {
  if (!contract.includes(requiredSelector)) fail(`forms-and-overlays.css is missing ${requiredSelector}`);
}

if (failures.length) {
  console.error("CSS contract failed:\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log(`CSS contract passed for ${files.length} stylesheets.`);
