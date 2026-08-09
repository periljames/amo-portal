import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = process.cwd();

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function assertIncludes(content, needle, message) {
  if (!content.includes(needle)) throw new Error(message);
}

function assertNotMatch(content, pattern, message) {
  const match = content.match(pattern);
  if (match) throw new Error(`${message}: ${match[0]}`);
}

const missions = read("src/styles/qms-missions.css");
const people = read("src/styles/qms-people.css");
const assurance = read("src/styles/qms-assurance-cases.css");
const intelligence = read("src/styles/qms-intelligence.css");
const controlRoom = read("src/styles/qms-assurance-control-room.css");
const register = read("src/styles/qms-register.css");
const registerPage = read("src/pages/qms/QmsRegisterPage.tsx");
const car = read("src/styles/qms-car-operational.css");
const planner = read("src/styles/qms-planner-readability.css");
const peoplePage = read("src/pages/qms/QmsPeoplePage.tsx");
const intelligencePage = read("src/pages/qms/QmsIntelligencePage.tsx");

for (const [name, css] of [
  ["Missions", missions],
  ["People", people],
  ["Assurance", assurance],
  ["Intelligence", intelligence],
  ["Control Room", controlRoom],
  ["QMS registers", register],
  ["CAR operational layer", car],
]) {
  assertNotMatch(
    css,
    /font-size\s*:\s*(?:8(?:\.\d+)?|9(?:\.\d+)?|10(?:\.\d+)?)px\b/i,
    `${name} reintroduced 8–10px operational typography`,
  );
}

assertIncludes(missions, "font-size: 14px;", "Missions must retain a 14px working-text baseline");
assertIncludes(missions, "position: fixed;", "New Mission must remain a secondary drawer workflow");
assertIncludes(missions, "width: min(620px, calc(100vw - 48px));", "Mission creation drawer must remain properly bounded");

assertIncludes(people, ".qms-people__workspace", "People must retain the authorization register + person detail workspace");
assertIncludes(people, ".qms-people__drawer-layer", "People governed actions must remain contextual drawers");
assertIncludes(peoplePage, "Quality authorization board", "People must remain person/authorization-first");
assertIncludes(peoplePage, "Check assignment", "People must expose task eligibility contextually");
assertIncludes(peoplePage, "Change privilege", "People must expose privilege decisions contextually");

assertIncludes(assurance, ".qms-assurance-cases__metrics + .qms-assurance-cases__panel", "Assurance New Case must remain a bounded secondary workflow");
assertIncludes(assurance, "position: fixed;", "Assurance New Case panel must remain a drawer");

assertIncludes(intelligencePage, "Surveillance priorities & assurance impact", "Intelligence must lead with surveillance priorities");
assertIncludes(intelligencePage, "source_record", "Intelligence must expose source-record provenance");
assertIncludes(intelligencePage, "source_date", "Intelligence must expose source-date provenance");
assertIncludes(intelligence, ".qms-intelligence__priority-list", "Intelligence must retain ranked priority presentation");

assertIncludes(controlRoom, ".qms-action-table__row", "Control Room must explicitly own action-queue readability");
assertIncludes(controlRoom, "font-size: 13px;", "Control Room action rows must retain readable working text");

for (const technicalField of ["owner_user_id", "assigned_to_user_id", "created_by_user_id", "updated_by_user_id"]) {
  assertIncludes(registerPage, `"${technicalField}"`, `Register technical-column denylist is missing ${technicalField}`);
}
assertIncludes(registerPage, "column.endsWith(\"_id\")", "Generic QMS registers must keep raw identifier fields out of visible working columns");
assertIncludes(registerPage, "qms-register-task-list", "My Quality Work must retain task-first rendering");
assertIncludes(register, ".qms-register-task__body > b", "My Quality Work must retain a primary human-readable assignment title");
assertIncludes(register, "font-size: 15px;", "My Quality Work primary assignment title must remain readable");

assertIncludes(car, "width: min(760px, calc(100vw - 48px));", "Create/Edit CAR must retain a substantial desktop dialog width");
assertIncludes(car, "width: min(920px, calc(100vw - 48px));", "CAR response review must retain a substantial desktop dialog width");
assertIncludes(car, "font-size: 14px;", "CAR controls must retain a 14px baseline");
assertIncludes(car, "min-height: 42px;", "CAR form controls must retain a 42px minimum height");

assertIncludes(planner, ".qms-planner-event__copy strong { font-size: .82rem;", "Planner event titles must retain the readability override");
assertIncludes(planner, ".qms-planner-modal__field :is(input, textarea) { min-height: 2.55rem;", "Planner modal controls must remain enlarged");
assertIncludes(planner, "@media (max-width: 1080px)", "Planner must protect calendar width on laptop viewports");
assertIncludes(planner, ".qms-planner-inspector { display: none; }", "Planner context rail must yield space on constrained laptop widths");

console.log("QMS operational UI contract passed: no micro-font regression and all redesigned workspace hierarchy contracts are present.");
