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
const peopleService = read("src/services/qmsPeople.ts");
const assurancePage = read("src/pages/qms/QmsAssurancePage.tsx");
const intelligencePage = read("src/pages/qms/QmsIntelligencePage.tsx");
const routeGuards = read("src/app/routeGuards.ts");
const workspaceRegistry = read("src/pages/qms/routes/qmsWorkspaceRegistry.ts");
const routeRegistry = read("src/pages/qms/routes/qmsRouteRegistry.ts");
const backendAssurancePermissions = read("../backend/amodb/apps/quality/assurance_permissions.py");
const backendTenantSecurity = read("../backend/amodb/apps/quality/tenant_security.py");
const semanticRegressions = read("tests/e2e/qms-operational-semantic-regressions.spec.ts");
const codexRegressions = read("tests/e2e/qms-codex-review-regressions.spec.ts");

for (const [name, css] of [
  ["Missions", missions],
  ["People", people],
  ["Assurance", assurance],
  ["Intelligence", intelligence],
  ["Control Room", controlRoom],
  ["QMS registers", register],
  ["CAR operational layer", car],
]) {
  assertNotMatch(css, /font-size\s*:\s*(?:8(?:\.\d+)?|9(?:\.\d+)?|10(?:\.\d+)?)px\b/i, `${name} reintroduced 8–10px operational typography`);
}

assertIncludes(missions, "font-size: 14px;", "Missions must retain a 14px working-text baseline");
assertIncludes(missions, "position: fixed;", "New Mission must remain a secondary drawer workflow");
assertIncludes(missions, "width: min(620px, calc(100vw - 48px));", "Mission creation drawer must remain properly bounded");

assertIncludes(people, ".qms-people__workspace", "People must retain the authorization register + person detail workspace");
assertIncludes(people, ".qms-people__drawer-layer", "People governed actions must remain contextual drawers");
assertIncludes(peoplePage, "Quality authorization board", "People must remain person/authorization-first");
assertIncludes(peoplePage, "Check audit assignment", "People must expose the governed audit-assignment preflight contextually");
assertIncludes(peoplePage, "Change privilege", "People must expose privilege decisions contextually");
assertIncludes(peoplePage, "snapshotRevision", "People eligibility must retain an explicit refresh revision signal");
assertIncludes(peoplePage, "setSnapshotRevision((value) => value + 1);", "People reload must invalidate the selected authorization snapshot");
assertIncludes(peoplePage, "[amoCode, selected, snapshotRevision]", "People authorization-readiness effect must rerun when the selected authorization or refresh revision changes");
assertIncludes(peoplePage, "snapshot.active_privilege?.id === privilege.id", "People authorization readiness must be tied to the selected privilege record");
assertIncludes(peoplePage, "selected_privilege_active: selectedPrivilegeMatches", "People must expose whether the selected authorization is the backend active privilege");
assertIncludes(peoplePage, "preflightQmsAuditorAssignment", "People assignment checks must call the governed Planner assignment preflight");
assertIncludes(peoplePage, "assignment_scope_key: submitted.assignment_scope_key", "People must send the immutable submitted assignment scope to the authoritative guard");
assertIncludes(peoplePage, "assignment_role: submitted.assignment_role", "People must send the immutable submitted auditor role to the authoritative guard");
assertIncludes(peoplePage, "assignment_date: submitted.assignment_date", "People must send the immutable submitted assignment date to the authoritative guard");
assertIncludes(peoplePage, "enforce_independence: true", "People assignment preflight must enforce independence");
assertIncludes(peoplePage, "assignmentAssessment?.active_privilege?.id === selected.id", "People must verify that the authoritative assignment guard used the selected privilege record");
assertIncludes(peoplePage, "assignmentResultInput", "People must retain the exact submitted assignment parameters with the returned preflight result");
assertIncludes(peoplePage, "invalidateAssignmentResult", "People must explicitly invalidate stale preflight results when inputs change");
assertIncludes(peoplePage, "assignmentRequestRevision", "People must ignore stale asynchronous preflight responses after result invalidation or drawer closure");
assertIncludes(peoplePage, "disabled={checkingAssignment}", "People assignment inputs must be locked while the authoritative preflight is in flight");
assertIncludes(peoplePage, "humanise(assignmentResultInput.assignment_scope_key)", "People must render the checked scope from the submitted snapshot, not mutable form state");
assertIncludes(peoplePage, "humanise(assignmentResultInput.assignment_role)", "People must render the checked role from the submitted snapshot, not mutable form state");
assertIncludes(peoplePage, "assignmentResultInput.assignment_date", "People must render the checked date from the submitted snapshot, not mutable form state");
assertIncludes(peoplePage, 'hasQmsRolePermission("qms.audit.manage")', "People must expose assignment/independence actions only to users permitted to manage audits");
assertIncludes(peoplePage, 'hasQmsRolePermission("qms.training.manage")', "People must expose privilege mutation controls only to users permitted to manage training/authorization governance");
assertNotMatch(peoplePage, /eligibilityUserId|eligibilityRule/, "People assignment checks must not regress to free-form user/privilege lookup");
assertIncludes(peoplePage, "if (!signal) clearQmsApiResponseCache();", "People manual refresh must bypass cached readiness/source data");
assertIncludes(peopleService, 'qmsPath(amoCode, "/integrations/calendar/auditor-eligibility")', "People service must retain the governed auditor-assignment endpoint");
assertIncludes(peopleService, "assignment_scope_key: string", "People preflight contract must require an assignment scope");

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

assertIncludes(assurance, ".qms-assurance-cases__metrics + .qms-assurance-cases__panel", "Assurance New Case must remain a bounded secondary workflow");
assertIncludes(assurance, "position: fixed;", "Assurance New Case panel must remain a drawer");
assertIncludes(assurancePage, "selectedIdRef", "Assurance must track selected case identity independently from a stale detail object");
assertIncludes(assurancePage, "getQmsAssuranceCase(amoCode, selectedId, signal)", "Assurance portfolio refresh must re-read selected case detail");
assertIncludes(assurancePage, "if (!signal) clearQmsApiResponseCache();", "Assurance manual refresh must bypass cached case data");
assertIncludes(assurancePage, 'OPEN: ["INVESTIGATING", "CANCELLED"]', "Assurance UI must retain the backend OPEN transition contract");
assertIncludes(assurancePage, 'EFFECTIVENESS_REVIEW: ["CLOSED", "ACTION_PENDING", "CANCELLED"]', "Assurance UI must retain the backend effectiveness-review transition contract");
assertIncludes(assurancePage, "concludeQmsEffectivenessPlan", "Assurance must expose the backend effectiveness-conclusion operation");
assertIncludes(assurancePage, "Record immutable effectiveness conclusion", "Assurance must let operators conclude effectiveness with governed evidence");
assertIncludes(assurancePage, "conclusionEvidence.trim()", "Assurance effectiveness conclusions must require an authoritative evidence reference");
assertIncludes(assurancePage, "plan.planned_review_date <= today", "Assurance must not expose conclusion before the planned review date");
assertIncludes(assurancePage, 'reviewDate < today', "Assurance must reject effectiveness plans with a past review date");
assertIncludes(assurancePage, 'entryType === "CAUSAL_CONCLUSION"', "Assurance must distinguish causal conclusions from ordinary investigation statements");
assertIncludes(assurancePage, "hasRecordedFact && Boolean(evidenceSource.trim())", "Assurance causal conclusions must require a prior fact and explicit evidence");
assertIncludes(assurancePage, "status !== \"CLOSED\" || !closureBlocked", "Assurance must hide CLOSED while effectiveness closure gates fail");
assertIncludes(assurancePage, 'const isTerminal = selected ? ["CLOSED", "CANCELLED"].includes(selected.status)', "Assurance must suppress new investigation/effectiveness work on terminal cases");

assertIncludes(intelligencePage, "Surveillance priorities & assurance impact", "Intelligence must lead with surveillance priorities");
assertIncludes(intelligencePage, "source_record", "Intelligence must expose source-record provenance");
assertIncludes(intelligencePage, "source_date", "Intelligence must expose source-date provenance");
assertIncludes(intelligencePage, "right.planning_order - left.planning_order", "Intelligence must preserve descending backend surveillance priority order");
assertNotMatch(intelligencePage, /left\.planning_order\s*-\s*right\.planning_order/, "Intelligence must never reverse backend surveillance priority order");
assertIncludes(intelligencePage, "Review affected authoritative sources", "Intelligence must expose source-warning detail through progressive disclosure");
assertIncludes(intelligencePage, "humanise(warning.source)", "Intelligence source warnings must identify the affected authoritative source");
assertIncludes(intelligencePage, "warning.message", "Intelligence source warnings must expose the backend-provided failure message");
assertIncludes(intelligencePage, "if (!signal) clearQmsApiResponseCache();", "Intelligence manual refresh must bypass cached planning/source data");
assertIncludes(intelligence, ".qms-intelligence__priority-list", "Intelligence must retain ranked priority presentation");

assertIncludes(controlRoom, ".qms-action-table__row", "Control Room must explicitly own action-queue readability");
assertIncludes(controlRoom, "font-size: 13px;", "Control Room action rows must retain readable working text");
assertIncludes(controlRoom, ".qms-overview-section--priority { overflow-x: auto; overflow-y: hidden; }", "Control Room priority action queue must remain horizontally reachable");
assertNotMatch(controlRoom, /\.qms-action-table\s*\{[^}]*overflow-x:\s*auto;/, "Horizontal scrolling must live on the constrained Control Room section, not the fixed-width action table");

for (const technicalField of ["owner_user_id", "assigned_to_user_id", "created_by_user_id", "updated_by_user_id"]) {
  assertIncludes(registerPage, `"${technicalField}"`, `Register technical-column denylist is missing ${technicalField}`);
}
assertIncludes(registerPage, "column.endsWith(\"_id\")", "Generic QMS registers must keep raw identifier fields out of visible working columns");
assertIncludes(registerPage, "qms-register-task-list", "My Quality Work must retain task-first rendering");
assertNotMatch(registerPage, /function taskDue\(row: QmsRow\): unknown \{[^}]*created_at[^}]*\}/, "Inbox notification creation timestamps must not be treated as deadlines");
assertIncludes(registerPage, '"due_date", "target_date", "planned_date", "scheduled_for", "review_date"', "My Quality Work must derive urgency only from actual due/planning fields");
assertIncludes(registerPage, "function taskReceived(row: QmsRow): unknown", "Inbox task view must preserve notification receipt time separately from urgency");
assertIncludes(registerPage, '["received_at", "created_at"]', "Inbox receipt context must accept the production created_at contract without feeding it into due calculations");
assertIncludes(registerPage, "`Received ${formatValue(receivedValue)}`", "Inbox notifications without deadlines must render their receipt timestamp");
assertIncludes(registerPage, "DATE_ONLY_PATTERN", "My Quality Work must recognize date-only deadlines");
assertIncludes(registerPage, "localCalendarDay(parsed) - localCalendarDay(now)", "Date-only due dates must be compared by calendar day, not midnight clock time");
assertIncludes(registerPage, "sourceError.label", "Registers must identify each failed authoritative source");
assertIncludes(registerPage, "sourceError.message", "Registers must expose each source failure message");
assertIncludes(registerPage, "cacheTtlMs: fresh ? 0 : undefined", "Register Refresh must bypass the normal GET cache");
assertIncludes(registerPage, "load(true)", "Register Refresh/Retry must request a fresh authoritative read");
assertIncludes(register, ".qms-register-task__body > b", "My Quality Work must retain a primary human-readable assignment title");
assertIncludes(register, "font-size: 15px;", "My Quality Work primary assignment title must remain readable");

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
  "People uses the governed Planner preflight",
  "Intelligence keeps authoritative source-warning provenance",
  "My Quality Work treats a date-only deadline due today as due today",
  "Assurance refresh re-reads the selected case detail",
  "Assurance exposes only backend-allowed transitions",
  "Assurance requires an evidence-backed effectiveness conclusion before closure becomes available",
]) {
  assertIncludes(semanticRegressions, testContract, `Semantic browser regression is missing: ${testContract}`);
}

for (const reviewRegression of [
  "People invalidates a governed assignment result when any checked input changes and locks inputs in flight",
  "Inbox preserves notification receipt time without treating created_at as a deadline",
  "People read access does not expose mutation controls to a Quality Auditor",
]) {
  assertIncludes(codexRegressions, reviewRegression, `Codex review regression coverage is missing: ${reviewRegression}`);
}

console.log("QMS operational UI contract passed: readability, backend priority truth, due-vs-received time semantics, immutable assignment preflight snapshots, backend-aligned read permissions, permission boundaries, authoritative refresh, source provenance, Assurance lifecycle/effectiveness gates and responsive reachability are preserved.");
