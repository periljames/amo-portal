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

const missions = read("src/styles/qms/missions.css");
const people = read("src/styles/qms/people.css");
const intelligence = read("src/styles/qms-intelligence.css");
const controlRoom = read("src/styles/qms-assurance-control-room.css");
const register = read("src/styles/qms/register.css");
const registerPage = read("src/pages/qms/QmsRegisterPage.tsx");
const car = read("src/styles/qms-car-operational.css");
const planner = read("src/styles/qms-planner-readability.css");
const peoplePage = read("src/pages/qms/QmsPeoplePage.tsx");
const peopleService = read("src/services/qmsPeople.ts");
const intelligencePage = read("src/pages/qms/QmsIntelligencePage.tsx");
const routeGuards = read("src/app/routeGuards.ts");
const workspaceRegistry = read("src/pages/qms/routes/qmsWorkspaceRegistry.ts");
const overviewPage = read("src/pages/qms/QmsOverviewPage.tsx");
const routeRegistry = read("src/pages/qms/routes/qmsRouteRegistry.ts");
const backendAssurancePermissions = read("../backend/amodb/apps/quality/assurance_permissions.py");
const backendTenantSecurity = read("../backend/amodb/apps/quality/tenant_security.py");
const semanticRegressions = read("tests/e2e/qms-operational-semantic-regressions.spec.ts");
const assuranceBrowser = read("tests/e2e/qms-assurance-operating-system.spec.ts");
const codexRegressions = read("tests/e2e/qms-codex-review-regressions.spec.ts");

for (const [name, css] of [
  ["Missions", missions],
  ["People", people],
  ["Intelligence", intelligence],
  ["Control Room", controlRoom],
  ["QMS registers", register],
  ["CAR operational layer", car],
]) {
  assertNotMatch(css, /font-size\s*:\s*(?:8(?:\.\d+)?|9(?:\.\d+)?|10(?:\.\d+)?)px\b/i, `${name} reintroduced 8–10px operational typography`);
}

assertIncludes(missions, "font-size: 14px;", "Missions must retain a 14px working-text baseline");
assertIncludes(missions, "position: relative;", "Mission creation must stay within the workspace flow");
assertIncludes(missions, "width: 100%;", "Mission creation must fit its workspace");

assertIncludes(people, ".qms-authz-grid--split", "People authorization control must retain a two-pane operational workspace");
assertIncludes(people, ".qms-authz-modal", "Governed authorization actions must remain contextual and explicit");
assertIncludes(people, "--qms-authz-accent: var(--accent-primary);", "People must consume the portal/QMS accent token instead of a local colour system");
assertIncludes(people, "--qms-authz-surface: var(--surface-elevated);", "People must consume the portal elevated-surface token");
assertIncludes(people, "background: var(--portal-overlay);", "People modal scrims must use the portal overlay token");
assertIncludes(people, ".qms-authz-list--viewport", "People and case registers must have bounded vertical growth");
assertIncludes(people, "@media (max-width: 1080px)", "People must collapse the two-pane workspace before constrained laptop widths overflow");
assertNotMatch(people, /--accent-color|--border-color/, "People must not reintroduce page-local accent/border token aliases");
assertNotMatch(peoplePage, /className="qms-authz-modal"\s+role="dialog"/, "People must not apply dialog semantics to the full-screen modal scrim");
assertIncludes(peoplePage, 'className="qms-authz-modal__panel" role="dialog"', "People dialog semantics must live on the actual modal panel");
assertIncludes(peoplePage, 'aria-current={effectiveTab === value ? "page" : undefined}', "People tab navigation must expose the active view accessibly");
assertIncludes(peoplePage, "Authorization governance", "People must remain authorization-control focused");
assertIncludes(peoplePage, "Authorization Cases", "People must expose the governed pre-decision case workflow");
assertIncludes(peoplePage, "Controlled Exemption / Conditional Authorization", "People must expose only the controlled exception workflow");
assertIncludes(peoplePage, "Final authorization decision", "People must expose attributable final authorization decisions");
assertIncludes(peoplePage, "Batch nominate", "People must retain batch nomination without bypassing case governance");
assertIncludes(peoplePage, "permissions?.can_prepare", "People must split preparation authority from decision authority");
assertIncludes(peoplePage, "permissions?.can_approve", "People must gate final decisions on approval authority");
assertIncludes(peoplePage, "permissions?.can_manage_policy", "People advanced policy configuration must be restricted");
assertIncludes(peopleService, '"/people/authorization-control/cases"', "People service must use governed authorization cases");
assertIncludes(peopleService, "/lifecycle", "People service must use governed authorization lifecycle decisions");
assertIncludes(peopleService, "/reviews", "People service must retain governed periodic reviews");
assertNotMatch(peopleService, /\/people\/privileges|qm-bypass|auditor-eligibility/, "People service must not retain superseded direct privilege, bypass or assignment-preflight APIs");
assertNotMatch(peoplePage, /Check audit assignment|Change privilege|QM training bypass|personnel ID/i, "People must not retain superseded assignment, direct-rank or identifier UI");

for (const permission of [
  "qms.management_review.view",
  "qms.supplier.view",
  "qms.equipment.view",
  "qms.risk.view",
  "qms.change.view",
  "qms.training.view",
]) {
  assertIncludes(backendAssurancePermissions, `"${permission}"`, `Backend assurance role contract no longer grants ${permission}`);
  assertIncludes(routeGuards, `"${permission}"`, `Frontend inspector/auditor read permissions must mirror backend grant ${permission}`);
}
assertIncludes(backendTenantSecurity, '"qms.reports.view"', "Backend reporting permission contract must retain qms.reports.view");
assertIncludes(backendTenantSecurity, '"qms.management_review.view"', "Backend management-review permission contract must retain qms.management_review.view");
assertIncludes(workspaceRegistry, 'permission: "qms.reports.view"', "Intelligence workspace must use the backend qms.reports.view permission key");
assertIncludes(routeRegistry, 'permission: "qms.reports.view"', "Reports route must use the backend qms.reports.view permission key");
assertIncludes(routeRegistry, 'permission: "qms.management_review.view"', "Management Review route must use the backend qms.management_review.view permission key");
assertIncludes(routeGuards, '"qms.reports.view"', "VIEW_ONLY frontend permissions must use the backend qms.reports.view key");
assertNotMatch(workspaceRegistry, /qms\.report\.view/, "Intelligence workspace must not regress to the obsolete singular reports permission");
assertNotMatch(routeRegistry, /qms\.report\.view|qms\.review\.view/, "QMS reporting routes must not use obsolete frontend-only permission aliases");
assertNotMatch(routeGuards, /qms\.report\.view|qms\.review\.view/, "Frontend role guards must not use obsolete reporting permission aliases");

assertIncludes(workspaceRegistry, 'if (workspace === "assurance") return qmsModulePath(amoCode, "audits", "dashboard");', "Assurance navigation must enter the consolidated Audits hub");
assertIncludes(overviewPage, 'if (workspace === "assurance")', "Legacy Assurance workspace links must be handled explicitly");
assertIncludes(overviewPage, 'return <Navigate to={`${qualityRoot}/audits/register`} replace />;', "Legacy Assurance workspace links must redirect to the consolidated audits register");
assertIncludes(assuranceBrowser, "Assurance keeps case triage primary in the consolidated finding lifecycle", "Browser coverage must exercise the live consolidated Assurance surface");
assertIncludes(assuranceBrowser, "/maintenance/tenant-a/quality/audits/register", "Assurance browser coverage must use the live consolidated audits route");
assertNotMatch(semanticRegressions, /workspace=assurance/, "Semantic regressions must not exercise the retired Assurance workspace");

assertIncludes(intelligencePage, "Surveillance priorities & assurance impact", "Intelligence must lead with surveillance priorities");
assertIncludes(intelligencePage, "source_record", "Intelligence must expose source-record provenance");
assertIncludes(intelligencePage, "source_date", "Intelligence must expose source-date provenance");
assertIncludes(intelligencePage, "right.planning_order - left.planning_order", "Intelligence must preserve descending backend surveillance priority order");
assertNotMatch(intelligencePage, /left\.planning_order\s*-\s*right\.planning_order/, "Intelligence must never reverse backend surveillance priority order");
assertIncludes(intelligencePage, "Review affected authoritative sources", "Intelligence must expose source-warning detail through progressive disclosure");
assertIncludes(intelligencePage, "humanise(warning.source)", "Intelligence source warnings must identify the affected authoritative source");
assertIncludes(intelligencePage, "warning.message", "Intelligence source warnings must expose the backend-provided failure message");
assertIncludes(intelligencePage, "clearQmsApiResponseCache();", "Intelligence manual refresh must bypass cached planning/source data");
assertIncludes(intelligence, ".qms-intelligence__priority-list", "Intelligence must retain ranked priority presentation");

assertIncludes(controlRoom, ".qms-action-table__row", "Control Room must explicitly own action-queue readability");
assertIncludes(controlRoom, "font-size: 13px;", "Control Room action rows must retain readable working text");
assertIncludes(controlRoom, ".qms-overview-section--priority { overflow-x: auto; overflow-y: hidden; }", "Control Room priority action queue must remain horizontally reachable");
assertNotMatch(controlRoom, /\.qms-action-table\s*\{[^}]*overflow-x:\s*auto;/, "Horizontal scrolling must live on the constrained Control Room section, not the fixed-width action table");

for (const technicalField of ["owner_user_id", "assigned_to_user_id", "created_by_user_id", "updated_by_user_id"]) {
  assertIncludes(registerPage, `"${technicalField}"`, `Register technical-column denylist is missing ${technicalField}`);
}
assertIncludes(registerPage, "column.endsWith(\"_id\")", "Generic QMS registers must keep raw identifier fields out of visible working columns");
assertIncludes(registerPage, "QmsPersonalTasks", "My Quality Work must expose saved personal tasks");
assertIncludes(registerPage, "QmsWorkspaceGrid", "Assigned work must use the shared AG Grid");
assertNotMatch(registerPage, /function taskDue\(row: QmsRow\): unknown \{[^}]*created_at[^}]*\}/, "Inbox notification creation timestamps must not be treated as deadlines");
assertIncludes(registerPage, '"due_date", "due_at", "target_date", "planned_date", "scheduled_for", "review_date"', "My Quality Work must derive urgency only from actual due/planning fields");
assertIncludes(registerPage, "function taskReceived(row: QmsRow): unknown", "Inbox task view must preserve notification receipt time separately from urgency");
assertIncludes(registerPage, '["received_at", "created_at"]', "Inbox receipt context must accept the production created_at contract without feeding it into due calculations");
assertIncludes(registerPage, 'colId: "received"', "Inbox must retain a separate received column");
assertIncludes(registerPage, "DATE_ONLY_PATTERN", "My Quality Work must recognize date-only deadlines");
assertIncludes(registerPage, "now.setHours(0, 0, 0, 0)", "Date-only due dates must be compared by calendar day, not midnight clock time");
assertIncludes(registerPage, "sourceError.label", "Registers must identify each failed authoritative source");
assertIncludes(registerPage, "sourceError.message", "Registers must expose each source failure message");
assertIncludes(registerPage, "cacheTtlMs: fresh ? 0 : undefined", "Register Refresh must bypass the normal GET cache");
assertIncludes(registerPage, "load(true)", "Register Refresh/Retry must request a fresh authoritative read");

assertIncludes(car, "width: min(760px, calc(100vw - 48px));", "Create/Edit CAR must retain a substantial desktop dialog width");
assertIncludes(car, "width: min(920px, calc(100vw - 48px));", "CAR response review must retain a substantial desktop dialog width");
assertIncludes(car, "font-size: 14px;", "CAR controls must retain a 14px baseline");
assertIncludes(car, "min-height: 42px;", "CAR form controls must retain a 42px minimum height");

assertIncludes(planner, ".qms-planner-event__copy strong { font-size: .82rem;", "Planner event titles must retain the readability override");
assertIncludes(planner, ".qms-planner-modal__field :is(input, textarea) { min-height: 2.55rem;", "Planner modal controls must remain enlarged");
assertIncludes(planner, "@media (max-width: 1080px)", "Planner must protect calendar width on laptop viewports");
assertIncludes(planner, ".qms-modern-planner-v2.has-left-rail.has-context .qms-planner-inspector:not(.is-event) { display: none; }", "Planner idle context rail must yield space on constrained laptop widths without hiding selected-event detail");
assertNotMatch(planner, /\.qms-modern-planner-v2\.has-left-rail\.has-context\s+\.qms-planner-inspector\s*\{\s*display:\s*none;\s*\}/, "Planner must not hide selected-event inspector detail at constrained widths");

for (const testContract of [
  "Intelligence keeps authoritative source-warning provenance",
  "My Quality Work treats a date-only deadline due today as due today",
]) {
  assertIncludes(semanticRegressions, testContract, `Semantic browser regression is missing: ${testContract}`);
}

for (const reviewRegression of [
  "Inbox preserves notification receipt time without treating created_at as a deadline",
]) {
  assertIncludes(codexRegressions, reviewRegression, `Codex review regression coverage is missing: ${reviewRegression}`);
}

console.log("QMS operational UI contract passed: readability, governed People authorization cases, split preparation/approval authority, backend-aligned permissions, authoritative refresh, source provenance, Assurance lifecycle/effectiveness gates and responsive reachability are preserved.");
