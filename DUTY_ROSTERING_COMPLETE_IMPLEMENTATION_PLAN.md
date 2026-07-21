# DUTY ROSTERING + WORKFORCE/HR COMPLETE IMPLEMENTATION CONTRACT

> Repository: `periljames/amo-portal`
>
> Baseline commit inspected: `9b50b3e2609a0e0a2b77c4a8117f7a099df496f5`
>
> Execution order is mandatory: **backend first, then frontend, then integration/UAT**.
>
> This document is an implementation contract for an autonomous coding agent. Do not skip sections, leave placeholders, create disconnected tables, or implement UI without working backend routes.

---

## 1. Objective

Replace the current Phase 1 read-heavy rostering surface with a complete, production-usable duty planning system integrated with:

- canonical users and personnel profiles;
- departments, bases, teams and reporting lines;
- employment conditions and contracted work patterns;
- leave, availability and public holidays;
- training, licences and maintenance authorisations;
- work orders, task cards and manpower demand;
- attendance, actual hours, overtime and payroll-ready outputs;
- roster versioning, validation, approval, publication, amendments and acknowledgements;
- notifications and calendar export.

The result must support daily planner use on desktop screens at **1920×1080 and 1366×768**, with 1920×1080 as the primary design target. The planner must be able to create, edit, validate, publish and amend rosters without using database tools, spreadsheets or hidden admin endpoints.

---

## 2. Non-negotiable architecture rules

1. `accounts.users.id` remains the canonical person key.
2. Do not duplicate names, roles, licence data, training data, bases, work orders or task cards into rostering-owned master tables.
3. Create a neutral `workforce` backend domain for HR/workforce data. Do not continue using `quality.user_availability` as the permanent leave/availability owner.
4. Existing published roster versions are immutable. Changes after publication create a new version/amendment.
5. Every write is tenant-scoped by effective AMO ID and audit-attributed to the acting user.
6. Every state transition is validated server-side; frontend guards are not sufficient.
7. No hardcoded light-only surfaces. Use existing global theme tokens from `frontend/src/styles/global.css`.
8. Respect `prefers-reduced-motion`.
9. No raw role-name checks spread through pages. Centralize backend permissions and mirror them in `frontend/src/utils/roleAccess.ts`.
10. Do not create an Alembic revision until current repository heads are inspected. New migrations must descend from the actual current head or be a deliberate merge revision.
11. Do not modify the historical migration `backend/amodb/alembic/versions/phase1_20260604_core_rostering.py`.
12. All routes listed below must exist, be typed, tested and wired into the UI.

---

# PART A — BACKEND

## 3. Existing backend files that must be revised

### Rostering core

- `backend/amodb/apps/rostering/models.py`
- `backend/amodb/apps/rostering/schemas.py`
- `backend/amodb/apps/rostering/services.py`
- `backend/amodb/apps/rostering/router.py`
- `backend/amodb/apps/rostering/__init__.py`

### Accounts/user management integration

- `backend/amodb/apps/accounts/models.py`
- `backend/amodb/apps/accounts/schemas.py`
- `backend/amodb/apps/accounts/router_admin.py`
- `backend/amodb/apps/accounts/router_modules_admin.py`
- `backend/amodb/apps/accounts/personnel_import.py`

### Cross-module integration

- `backend/amodb/apps/training/models.py`
- `backend/amodb/apps/training/compliance.py`
- `backend/amodb/apps/work/models.py`
- `backend/amodb/apps/work/services.py`
- `backend/amodb/apps/foundations/models.py`
- `backend/amodb/apps/foundations/services.py`
- `backend/amodb/apps/notifications/service.py`
- `backend/amodb/apps/audit/services.py`
- `backend/amodb/main.py`
- `backend/conftest.py`

### New backend package

Create:

```text
backend/amodb/apps/workforce/
├── __init__.py
├── models.py
├── schemas.py
├── services.py
├── router.py
├── permissions.py
├── calculations.py
└── tests/
    ├── test_employment_contracts.py
    ├── test_leave_workflow.py
    ├── test_availability_projection.py
    ├── test_attendance_timesheets.py
    └── test_workforce_tenant_isolation.py
```

Create rostering tests:

```text
backend/amodb/apps/rostering/tests/
├── test_roster_crud.py
├── test_roster_lifecycle.py
├── test_roster_permissions.py
├── test_roster_validation_rules.py
├── test_roster_training_authorisation.py
├── test_roster_leave_conflicts.py
├── test_roster_bulk_operations.py
├── test_roster_amendments.py
├── test_roster_task_allocation.py
├── test_roster_reports.py
├── test_roster_notifications.py
└── test_roster_tenant_isolation.py
```

---

## 4. Workforce/HR data model

Implement the following models in `backend/amodb/apps/workforce/models.py`. All primary keys use `String(36)` and the project UUID generator. All tenant-owned rows require `amo_id`, indexes and timestamps.

### 4.1 EmploymentContract

Table: `employment_contracts`

Required fields:

- `id`
- `amo_id -> amos.id`
- `user_id -> users.id`
- `contract_type`: `PERMANENT | FIXED_TERM | TEMPORARY | CONTRACTOR | INTERN`
- `employment_status`: `ACTIVE | SUSPENDED | TERMINATED | ONBOARDING`
- `effective_from`
- `effective_to`
- `standard_weekly_minutes`
- `standard_daily_minutes`
- `fte_percentage`
- `primary_base_station_id -> base_stations.id`
- `secondary_base_station_id -> base_stations.id`, nullable
- `supervisor_user_id -> users.id`, nullable
- `cost_centre`, nullable
- `payroll_number`, nullable
- `overtime_eligible`
- `night_shift_eligible`
- `standby_eligible`
- `created_by_user_id`
- `updated_by_user_id`
- `created_at`
- `updated_at`

Constraints:

- `effective_to IS NULL OR effective_to >= effective_from`
- minutes are non-negative
- FTE is `> 0` and `<= 100`
- prevent overlapping active contracts for the same user unless explicitly versioned by non-overlapping dates.

### 4.2 WorkPattern and WorkPatternDay

Tables:

- `work_patterns`
- `work_pattern_days`
- `employee_work_pattern_assignments`

`WorkPattern` fields:

- `code`, `name`, `description`
- `cycle_length_days`
- `is_active`
- `timezone_name`

`WorkPatternDay` fields:

- `work_pattern_id`
- `cycle_day_index` starting at `0`
- `shift_template_id`, nullable for OFF day
- `status`
- `start_time_local`, `end_time_local`
- `spans_next_day`
- `planned_minutes`

`EmployeeWorkPatternAssignment` fields:

- `user_id`
- `work_pattern_id`
- `effective_from`
- `effective_to`
- `cycle_anchor_date`

Add service to generate draft assignments from a pattern for a selected roster period. Generation must be idempotent and return a preview before commit.

### 4.3 Leave and availability

Tables:

- `leave_types`
- `employee_leave_balances`
- `leave_requests`
- `leave_request_approvals`
- `employee_availability_events`
- `public_holiday_calendars`
- `public_holidays`

Leave request states:

`DRAFT | SUBMITTED | SUPERVISOR_APPROVED | HR_APPROVED | REJECTED | CANCELLED | RECALLED`

Availability event states/types must cover:

- `AVAILABLE`
- `UNAVAILABLE`
- `ANNUAL_LEAVE`
- `SICK_LEAVE`
- `COMPASSIONATE_LEAVE`
- `MATERNITY_LEAVE`
- `PATERNITY_LEAVE`
- `STUDY_LEAVE`
- `UNPAID_LEAVE`
- `TRAINING`
- `TRAVEL`
- `SUSPENDED`
- `OTHER`

Rules:

- only `HR_APPROVED` leave blocks rostering as a blocker;
- submitted leave appears as a warning;
- cancellation/rejection removes future blocking projection;
- published assignment conflict creates a roster amendment requirement, not an in-place edit;
- leave balances update transactionally on final approval/cancellation;
- half-day and hourly leave are supported with timezone-aware datetime ranges.

### 4.4 Attendance, timesheets and overtime

Tables:

- `attendance_events`
- `timesheets`
- `timesheet_lines`
- `overtime_requests`
- `overtime_approvals`
- `roster_actual_variances`

Attendance event types:

`CLOCK_IN | CLOCK_OUT | BREAK_START | BREAK_END | MANUAL_ADJUSTMENT`

Timesheet line categories:

`ORDINARY | OVERTIME | NIGHT | WEEKEND | PUBLIC_HOLIDAY | STANDBY | CALLOUT | TRAINING | TRAVEL | LEAVE | UNPAID_ABSENCE`

Timesheet states:

`DRAFT | SUBMITTED | SUPERVISOR_APPROVED | HR_APPROVED | EXPORTED | REJECTED`

Implement planned-versus-actual calculation using:

- roster assignment planned hours;
- attendance presence hours;
- `work.work_log_entries` productive task hours;
- approved leave/training classifications.

Do not rewrite work-log ownership.

---

## 5. Permission model

Create `backend/amodb/apps/workforce/permissions.py` or a shared permission service if the repository already has a canonical permission table by execution time.

Required permission codes:

```text
roster.view_own
roster.view_department
roster.view_all
roster.create
roster.edit
roster.delete_draft_assignment
roster.validate
roster.submit
roster.approve
roster.publish
roster.amend_published
roster.override_warning
roster.override_blocker
roster.manage_rules
roster.manage_shift_templates
roster.manage_patterns
roster.allocate_work
leave.request
leave.review
leave.approve
leave.manage_balances
attendance.view_own
attendance.manage
attendance.approve
timesheet.view_own
timesheet.approve
overtime.request
overtime.approve
payroll.export
workforce.manage_contracts
workforce.view_sensitive
```

Implementation requirements:

- add `HR_OFFICER`, `HR_MANAGER`, `ROSTER_PLANNER`, `PAYROLL_OFFICER`, and `DEPARTMENT_SUPERVISOR` to `AccountRole` only if the project still relies on the enum at execution time;
- map default permissions centrally;
- allow explicit per-user grants/revocations without changing the user’s primary role;
- backend route decorators/helpers must check permission plus tenant scope;
- employees can only view own roster, leave and timesheets unless granted broader scope;
- supervisors are department-scoped;
- planners are base/department scoped where configured;
- Quality can validate and audit but must not silently edit HR records;
- system accounts cannot be rostered, approve leave or approve rosters.

Update module subscription allowlist in `backend/amodb/apps/accounts/router_modules_admin.py` to include `rostering` and `workforce` if module subscriptions remain required.

---

## 6. Rostering model restructuring

Revise `backend/amodb/apps/rostering/models.py`.

### Keep and extend

- `ShiftTemplate`
- `RosterPeriod`
- `RosterVersion`
- `RosterAssignment`
- `RosterValidationFinding`
- `RosterPublicationAcknowledgement`
- `RosterTaskAssignmentLink`

### Add

#### RosterRuleSet

- name, code, effective dates, active flag, priority.

#### RosterRule

- `rule_set_id`
- `rule_code`
- `rule_type`
- `severity`
- `configuration_json`
- optional department/base/employment-type scope
- `effective_from`, `effective_to`
- `is_active`

Supported initial rule types:

- minimum rest;
- maximum assignment duration;
- maximum rolling 7-day duty minutes;
- maximum consecutive duty days;
- maximum consecutive night shifts;
- minimum days off in rolling period;
- required role coverage;
- required certifying coverage;
- training conflict;
- licence expiry;
- authorisation expiry/scope;
- leave/availability conflict;
- employment-contract hours;
- base mismatch;
- overlapping assignments;
- work allocation exceeds duty capacity.

#### RosterRuleOverride

- version, assignment, finding, actor, reason, approval status, timestamps.
- blocker override requires `roster.override_blocker` and separate approver.

#### RosterChangeRequest

- version/assignment/user references;
- reason code;
- requested change payload;
- status;
- requester, reviewer and resolution trail.

#### ShiftSwapRequest

- source assignment;
- requesting user;
- target user/assignment, nullable;
- proposed times;
- status;
- validation snapshot;
- supervisor/planner approvals.

#### RosterNotificationReceipt

Track in-portal delivery/read state separately from publication acknowledgement.

### Extend RosterAssignment

Add:

- `department_id`
- `work_centre_code`, nullable
- `team_code`, nullable
- `source`: `MANUAL | WORK_PATTERN | IMPORT | TASK_DEMAND | SWAP | AMENDMENT`
- `source_reference_id`, nullable
- `required_role_code`, nullable
- `required_authorisation_type_id`, nullable
- `is_overtime_planned`
- `notes_visibility`: `PRIVATE_MANAGER | ASSIGNEE | TEAM`
- optimistic concurrency integer `revision_no`

`DELETE` is allowed only for draft assignments. Published assignment records remain immutable.

---

## 7. Fix existing backend bugs and weaknesses

The coding agent must explicitly correct these defects:

1. Replace the hardcoded eight-hour rest check in `rostering/services.py` with configurable rules. Seed an eight-hour default only as initial configuration.
2. Existing validation checks active personnel profiles but does not reject inactive users. Add blocker checks for inactive/deactivated accounts and inactive employment contracts.
3. Current assignment update cannot intentionally clear nullable fields because `None` is treated as “not supplied.” Use Pydantic field-set tracking and explicit patch semantics.
4. Current `RosterAssignmentUpdate` cannot change `user_id`; add controlled reassignment for drafts with full revalidation.
5. Add draft assignment deletion route.
6. Add pagination/filtering to assignment and period list routes.
7. Prevent duplicate/overlapping roster periods where business policy disallows them.
8. Prevent cross-period copy when dates do not align without an explicit date offset.
9. Add timezone conversion using `AMO.time_zone`; do not treat local shift times as UTC.
10. Current training conflict treats events as full-day because training stores dates. Extend training events with optional start/end datetimes while preserving date fallback.
11. Replace permanent dependency on `quality.UserAvailability` with workforce availability. Add a one-time migration of existing availability rows or a compatibility read adapter, then deprecate the quality source.
12. Validate detailed `UserAuthorisation` scope and expiry instead of counting only broad certifying roles.
13. Task allocation must reject allocations outside the roster assignment interval and allocations exceeding remaining assignment capacity.
14. `planning_board` must support draft-version scenario planning via optional `version_id`; published-only remains the default.
15. Add stable sorting and deterministic response order.
16. Add audit events for create/update/delete/submit/approve/publish/amend/override/swap/leave approvals.
17. Publish must send notifications and create acknowledgement obligations only for affected rostered users.
18. Correct state transition rules: draft → submitted → approved → published. Do not allow direct draft approval unless a separately named emergency permission is present.
19. An approver cannot approve their own submitted roster unless explicitly configured; default is separation of duties.
20. Add idempotency handling for publish, acknowledgement, pattern generation and bulk operations.

---

## 8. Backend API contract

All routes are under `/workforce` or `/rostering`. All dates are ISO-8601. Datetimes are timezone-aware.

### 8.1 Workforce routes

```text
GET    /workforce/contracts
POST   /workforce/contracts
GET    /workforce/contracts/{contract_id}
PATCH  /workforce/contracts/{contract_id}

GET    /workforce/work-patterns
POST   /workforce/work-patterns
GET    /workforce/work-patterns/{pattern_id}
PATCH  /workforce/work-patterns/{pattern_id}
POST   /workforce/work-patterns/{pattern_id}/preview

GET    /workforce/leave/types
POST   /workforce/leave/types
GET    /workforce/leave/balances
PATCH  /workforce/leave/balances/{balance_id}
GET    /workforce/leave/requests
POST   /workforce/leave/requests
GET    /workforce/leave/requests/{request_id}
PATCH  /workforce/leave/requests/{request_id}
POST   /workforce/leave/requests/{request_id}/submit
POST   /workforce/leave/requests/{request_id}/supervisor-approve
POST   /workforce/leave/requests/{request_id}/hr-approve
POST   /workforce/leave/requests/{request_id}/reject
POST   /workforce/leave/requests/{request_id}/cancel

GET    /workforce/availability
POST   /workforce/availability
PATCH  /workforce/availability/{event_id}
DELETE /workforce/availability/{event_id}

GET    /workforce/public-holidays
POST   /workforce/public-holidays

GET    /workforce/attendance
POST   /workforce/attendance/events
GET    /workforce/timesheets
POST   /workforce/timesheets/generate
POST   /workforce/timesheets/{timesheet_id}/submit
POST   /workforce/timesheets/{timesheet_id}/approve
GET    /workforce/payroll/export
```

### 8.2 Rostering routes

Keep existing routes for compatibility, and add/standardize:

```text
GET    /rostering/people
GET    /rostering/coverage-demand
GET    /rostering/shift-templates
POST   /rostering/shift-templates
PATCH  /rostering/shift-templates/{template_id}

GET    /rostering/rule-sets
POST   /rostering/rule-sets
PATCH  /rostering/rule-sets/{rule_set_id}
GET    /rostering/rules
POST   /rostering/rules
PATCH  /rostering/rules/{rule_id}

GET    /rostering/periods
POST   /rostering/periods
PATCH  /rostering/periods/{period_id}
GET    /rostering/periods/{period_id}/versions
POST   /rostering/periods/{period_id}/versions

GET    /rostering/versions/{version_id}
GET    /rostering/versions/{version_id}/assignments
POST   /rostering/versions/{version_id}/assignments
POST   /rostering/versions/{version_id}/assignments/bulk
POST   /rostering/versions/{version_id}/generate-from-patterns/preview
POST   /rostering/versions/{version_id}/generate-from-patterns/commit
POST   /rostering/versions/{version_id}/copy-range
POST   /rostering/versions/{version_id}/validate
POST   /rostering/versions/{version_id}/submit
POST   /rostering/versions/{version_id}/approve
POST   /rostering/versions/{version_id}/publish
POST   /rostering/versions/{version_id}/create-amendment
GET    /rostering/versions/{version_id}/diff
GET    /rostering/versions/{version_id}/acknowledgements

PATCH  /rostering/assignments/{assignment_id}
DELETE /rostering/assignments/{assignment_id}
GET    /rostering/assignments/{assignment_id}/eligibility
GET    /rostering/assignments/{assignment_id}/task-links
POST   /rostering/assignments/{assignment_id}/task-links
POST   /rostering/assignments/{assignment_id}/task-allocations
DELETE /rostering/task-links/{link_id}

GET    /rostering/change-requests
POST   /rostering/change-requests
POST   /rostering/change-requests/{request_id}/approve
POST   /rostering/change-requests/{request_id}/reject

GET    /rostering/shift-swaps
POST   /rostering/shift-swaps
POST   /rostering/shift-swaps/{swap_id}/accept
POST   /rostering/shift-swaps/{swap_id}/approve
POST   /rostering/shift-swaps/{swap_id}/reject

GET    /rostering/my-roster
POST   /rostering/versions/{version_id}/acknowledge
GET    /rostering/planning-board
GET    /rostering/reports/coverage
GET    /rostering/reports/fatigue
GET    /rostering/reports/overtime
GET    /rostering/reports/acknowledgements
GET    /rostering/reports/planned-v-actual
GET    /rostering/reports/export.xlsx
GET    /rostering/reports/export.pdf
GET    /rostering/calendar.ics
```

### Required filters

Where applicable support:

- `from`, `to`
- `period_id`, `version_id`
- `department_id`
- `base_station_id`
- `team_code`
- `user_id`
- `role`
- `status`
- `search`
- `page`, `page_size`

### Error response shape

Use a consistent shape:

```json
{
  "detail": "Human-readable explanation",
  "error_code": "ROSTER_RULE_BLOCKER",
  "field_errors": {},
  "conflicts": [],
  "retryable": false
}
```

---

## 9. Validation engine required outcomes

Create composable rule evaluators in `backend/amodb/apps/rostering/services.py` or split into `validation.py` if the service file becomes oversized.

Each finding must contain:

- stable code;
- severity;
- source;
- affected user;
- affected assignment;
- rule ID;
- concise message;
- machine-readable metadata;
- override eligibility;
- suggested corrective action.

Minimum finding codes:

```text
OUTSIDE_PERIOD
OVERLAPPING_ASSIGNMENTS
MISSING_BASE
INACTIVE_USER
MISSING_ACTIVE_CONTRACT
SYSTEM_ACCOUNT_ROSTERED
MISSING_PERSONNEL_PROFILE
REST_BELOW_MINIMUM
SHIFT_DURATION_EXCEEDED
WEEKLY_HOURS_EXCEEDED
CONSECUTIVE_DAYS_EXCEEDED
CONSECUTIVE_NIGHTS_EXCEEDED
LEAVE_CONFLICT
PENDING_LEAVE_WARNING
TRAINING_CONFLICT
LICENCE_EXPIRED
LICENCE_EXPIRES_DURING_PERIOD
AUTHORISATION_MISSING
AUTHORISATION_EXPIRED
AUTHORISATION_SCOPE_MISMATCH
BASE_SCOPE_MISMATCH
MINIMUM_COVERAGE_NOT_MET
CERTIFYING_COVERAGE_NOT_MET
SHIFT_LEAD_NOT_ASSIGNED
TASK_OUTSIDE_DUTY_WINDOW
TASK_ALLOCATION_EXCEEDS_CAPACITY
PUBLIC_HOLIDAY_RULE
OVERTIME_APPROVAL_REQUIRED
```

Validation must run:

- on single assignment create/update;
- after drag/drop and resize through the same API;
- on bulk operations;
- before submit;
- before approve;
- before publish;
- before shift-swap approval;
- before leave final approval where existing published duties are affected.

---

## 10. Notifications and audit

Use `backend/amodb/apps/notifications/service.py` for email logging/sending and the existing in-portal notification mechanism if available.

Required templates/events:

- roster published;
- roster amended;
- assignment added/changed/removed;
- acknowledgement overdue;
- leave submitted/approved/rejected/cancelled;
- shift swap requested/accepted/approved/rejected;
- overtime approval required;
- authorisation/training expiry affects future roster;
- coverage blocker created.

Notifications must include canonical frontend routes, AMO code, period/version and affected dates. Duplicate sends are prohibited through correlation/idempotency keys.

Create audit events for every sensitive transition with before/after JSON.

---

## 11. Migration procedure

1. Run:

```bash
alembic -c backend/amodb/alembic.ini heads
alembic -c backend/amodb/alembic.ini history --verbose
```

2. If multiple heads exist, do not attach a new feature revision arbitrarily. Resolve existing overlap or create a documented merge revision first.
3. Create one coherent workforce/rostering migration chain with reversible downgrade where data safety permits.
4. Include indexes for all tenant/date/user lookups.
5. Migrate `quality.user_availability` records into `employee_availability_events` preserving source IDs in metadata.
6. Seed default rule set, leave types and basic shift templates per AMO idempotently.
7. Update `backend/conftest.py` to import/create workforce and rostering tables for tests.
8. Verify PostgreSQL migration from current head and a clean database.

Mandatory commands:

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
alembic -c backend/amodb/alembic.ini current
alembic -c backend/amodb/alembic.ini check
```

Expected result: no overlap error, database heads exactly equal repository heads.

---

## 12. Backend tests and gates

Run from repository root or backend directory as appropriate:

```bash
pytest backend/amodb/apps/workforce/tests -q
pytest backend/amodb/apps/rostering/tests -q
pytest backend/amodb/apps/training/tests -q
pytest backend/amodb/apps/work/tests -q
pytest backend -q
```

Minimum required cases:

- tenant A cannot read/write tenant B workforce or roster records;
- system account cannot be rostered;
- inactive user and expired contract are blocked;
- overlapping assignment blocked;
- configurable rest rule works across midnight/timezones;
- approved leave blocks duty;
- pending leave warns but does not block unless configured;
- training conflict detected with datetime and date-only fallback;
- licence and authorisation expiry detected;
- task allocation outside shift rejected;
- draft delete succeeds; published delete fails;
- lifecycle cannot skip states;
- submitter cannot self-approve by default;
- publish is idempotent;
- acknowledgements are user/version unique;
- amendment supersedes old publication without mutating it;
- bulk operation is transactional;
- rule override requires permission and reason;
- reports use published version unless explicit scenario version supplied;
- payroll export includes only approved timesheets;
- all list routes paginate and filter deterministically.

No backend phase is complete while any test is skipped because “frontend will handle it.”

---

# PART B — FRONTEND

## 13. Existing frontend files that must be revised

- `frontend/package.json`
- `frontend/src/types/rostering.ts`
- `frontend/src/services/rostering.ts`
- `frontend/src/services/adminUsers.ts`
- `frontend/src/utils/roleAccess.ts`
- `frontend/src/app/canonicalRoutes.ts`
- `frontend/src/router.tsx`
- `frontend/src/components/Layout/DepartmentLayout.tsx`
- `frontend/src/pages/rostering/RosteringPages.tsx`
- `frontend/src/styles/rostering.css`
- `frontend/src/styles/global.css` only for reusable tokens, never module-specific layout dumping.

### Replace the monolithic page file

`frontend/src/pages/rostering/RosteringPages.tsx` must become an export barrel or be deleted after routes are updated. Split into:

```text
frontend/src/pages/rostering/
├── RosteringDashboardPage.tsx
├── RosterPlannerPage.tsx
├── ManpowerPlanningBoardPage.tsx
├── MyRosterPage.tsx
├── LeaveWorkspacePage.tsx
├── AttendanceTimesheetsPage.tsx
├── TrainingImpactPage.tsx
├── RosterReportsPage.tsx
├── RosterSettingsPage.tsx
└── index.ts
```

Create components:

```text
frontend/src/components/rostering/
├── RosterShell.tsx
├── RosterToolbar.tsx
├── RosterTimeline.tsx
├── RosterResourceRow.tsx
├── RosterAssignmentCard.tsx
├── ShiftTemplatePalette.tsx
├── AssignmentEditorDrawer.tsx
├── EmployeeInspectorDrawer.tsx
├── ValidationDrawer.tsx
├── CoverageHeatmap.tsx
├── CapacitySummaryStrip.tsx
├── RosterVersionControl.tsx
├── RosterPublishDialog.tsx
├── RosterDiffDialog.tsx
├── BulkEditDialog.tsx
├── LeaveRequestDialog.tsx
├── ShiftSwapDialog.tsx
├── ReportFilterBar.tsx
├── StatusPill.tsx
├── EmptyState.tsx
└── LoadingSkeleton.tsx
```

Create state/hooks:

```text
frontend/src/hooks/rostering/
├── useRosterPeriod.ts
├── useRosterPlanner.ts
├── useRosterDnD.ts
├── useRosterPermissions.ts
├── useRosterValidation.ts
├── useRosterFilters.ts
└── useReducedMotion.ts
```

Create tests:

```text
frontend/src/pages/rostering/__tests__/
frontend/src/components/rostering/__tests__/
frontend/tests/e2e/rostering.spec.ts
frontend/tests/e2e/rostering-dark-mode.spec.ts
frontend/tests/e2e/rostering-permissions.spec.ts
```

---

## 14. Frontend dependency decision

Install a maintained accessible drag-and-drop library. Preferred:

```bash
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/modifiers
```

Do not implement pointer dragging manually. Use keyboard sensors and collision logic. Keep `framer-motion` and `lucide-react`, which already exist.

Update `frontend/package.json` scripts so unit tests run the complete test suite, not only `verificationScan.test.ts`:

```json
"test:unit": "vitest run",
"test:rostering": "vitest run src/pages/rostering src/components/rostering",
"test:e2e:rostering": "playwright test tests/e2e/rostering*.spec.ts"
```

---

## 15. Frontend route contract

Revise canonical routes and router entries.

Required routes:

```text
/maintenance/:amoCode/rostering/dashboard
/maintenance/:amoCode/rostering/planner
/maintenance/:amoCode/rostering/planning-board
/maintenance/:amoCode/rostering/my-roster
/maintenance/:amoCode/rostering/leave
/maintenance/:amoCode/rostering/attendance
/maintenance/:amoCode/rostering/training-impact
/maintenance/:amoCode/rostering/reports
/maintenance/:amoCode/rostering/settings
```

Compatibility:

- `/rostering` redirects to dashboard;
- `/rostering/calendar` redirects to `/rostering/planner`;
- existing bookmarks remain functional.

Every route must use `RequireFeatureAccess`. Add feature keys for leave and attendance. Route denial copy must mention rostering rather than the generic maintenance denial currently returned by `getFeatureDenialMessage`.

---

## 16. Planner UI/UX specification

### 16.1 Desktop layout at 1920×1080

Use the full available content width inside the existing portal shell.

Mandatory layout:

```text
┌ Compact page title + period/version status + primary actions ┐
├ Filter/zoom/group toolbar                                     ┤
├ Left resource column 260–320px ┬ Horizontally scrollable time grid ┤
│ teams/employees              │ assignments, demand, conflicts       │
├ Sticky capacity/validation summary strip                     ┤
└ Optional right inspector drawer 360–440px                    ┘
```

Rules:

- no oversized hero block;
- title row height target: 64–88px;
- primary toolbar stays visible while vertically scrolling;
- employee column remains sticky during horizontal scrolling;
- time/date header remains sticky during vertical scrolling;
- default density must show at least 12–18 personnel rows at 1080p depending on browser chrome;
- row height options: compact 44px, comfortable 56px;
- no cards nested inside multiple cards;
- use separators, bands and grouped whitespace instead of box-in-box surfaces;
- drawers must not reduce the timeline below usable width; overlay drawer at widths under 1440px.

### 16.2 Drag and drop

Required interactions:

- drag shift template onto employee/date cell;
- drag assignment to another employee/date/time;
- resize assignment start/end;
- multi-select assignments and move/copy;
- hold modifier to copy;
- keyboard equivalent for move and resize;
- auto-scroll horizontally and vertically near viewport edges;
- ghost preview with exact target time/person;
- invalid target appears red and explains why;
- warning target appears amber and allows drop followed by validation confirmation;
- successful drop animates into position in 140–220ms;
- API failure returns card to original position and displays a concise toast;
- optimistic updates use `revision_no`; conflict response opens a refresh/compare prompt.

Do not use long hover delays. Tooltips should appear within approximately 250–400ms and never cover the active drop target.

### 16.3 Content hierarchy

Priority order:

1. unfilled coverage and blockers;
2. selected period/version and lifecycle status;
3. person, shift time, base and role;
4. qualification/leave/training warnings;
5. workload allocation;
6. secondary notes and audit metadata.

Do not overemphasize reference IDs, remarks or internal database keys. Display human labels; IDs belong in detail drawers or copy actions.

### 16.4 Color grading

Use semantic tokens in both themes:

- duty: blue/teal family;
- night: indigo family;
- standby: amber family;
- training: violet family;
- leave: muted green family;
- unavailable: neutral/red-hatched pattern;
- blocker: red;
- warning: amber;
- compliant/covered: green;
- unfilled demand: red outline with subtle fill.

Color must never be the only indicator. Add icons, labels, border styles or patterns. Meet WCAG AA text contrast.

### 16.5 Typography and icons

- use the portal font stack from global styles;
- body/control text: 13–14px on desktop;
- table headers: 11–12px, uppercase only where useful;
- page title: 24–30px, not 48px+;
- KPI figures: 22–32px based on importance;
- use `lucide-react` consistently;
- no emoji icons;
- every icon-only button requires `aria-label` and tooltip;
- icons must be 16–20px for controls, 20–24px for high-level navigation.

### 16.6 Motion

Use `framer-motion` only where it improves comprehension:

- assignment move/resize;
- drawer open/close;
- validation result insertion;
- tab/view transition;
- toast and confirmation state.

Motion duration target: 120–240ms. Avoid bounce effects in operational screens. Under `prefers-reduced-motion`, disable transforms and use immediate state changes/fades below 80ms.

### 16.7 CTA and pills

Buttons must have clear hierarchy:

- primary: create/publish/apply;
- secondary: validate/submit/filter;
- tertiary/ghost: view/copy/export;
- destructive: delete/reject/cancel.

Status pills are informational, not clickable unless rendered as a real button with focus/hover/pressed states. Minimum target size: 36px desktop and 44px touch-capable layouts.

---

## 17. Required pages and outcomes

### Dashboard

Must show:

- current published roster;
- pending draft/submitted version;
- blocker/warning totals;
- unfilled shift coverage;
- available versus required hours;
- overtime forecast;
- leave/training impact in next 30 days;
- missing acknowledgements;
- direct CTAs to open planner, validate, review or publish.

Use scan-friendly KPI strip and prioritized exception lists. Do not show the technical “module contract” panel to normal users.

### Planner

Must provide all create/edit/bulk/drag/drop/version/validation functionality. This is the primary operational page.

### Planning board

Must support:

- published or selected draft scenario;
- base/department/date filters;
- capacity heatmap;
- work-order/task demand;
- allocate rostered staff to task;
- prevent over-allocation;
- direct links to work order/task detail.

### My roster

Must show:

- calendar/list toggle;
- acknowledgement CTA;
- leave request;
- shift swap request;
- add to calendar/download ICS;
- changed-since-last-view indicator;
- training/authorisation warnings.

### Leave workspace

Must support employee request plus supervisor/HR queues based on permission.

### Attendance/timesheets

Must show planned versus actual, exceptions, overtime and approval status.

### Training impact

Replace static Phase 1 text with actual impact forecast by person/date/base and drill-through to training records.

### Reports

Implement real filters and exports. Required initial reports:

- coverage;
- fatigue/rest;
- overtime;
- acknowledgement;
- planned versus actual;
- leave/absence;
- training/authorisation impact.

### Settings

Real CRUD for:

- shift templates;
- work patterns;
- rule sets/rules;
- leave types;
- public holidays;
- planner defaults;
- notification preferences.

---

## 18. Frontend service and type requirements

Revise `frontend/src/types/rostering.ts` and create `frontend/src/types/workforce.ts`.

Requirements:

- exact parity with backend schemas;
- no `Record<string, unknown>` for stable response structures;
- typed pagination envelopes;
- typed error response;
- typed validation metadata;
- typed permissions;
- typed roster diff and amendment;
- typed report rows;
- typed leave/timesheet workflows.

Revise `frontend/src/services/rostering.ts` and create `frontend/src/services/workforce.ts`.

Add methods for every route in Sections 8.1 and 8.2. Use shared API helpers and auth headers. All mutations must return the authoritative server row/version.

Use React Query for server state, cache invalidation and optimistic mutations. Do not maintain duplicate period/assignment truth in unrelated local states.

---

## 19. Theme defects to correct

The existing `frontend/src/styles/rostering.css` hardcodes white backgrounds and dark text. Replace it completely.

Requirements:

- use `--surface`, `--surface-elevated`, `--surface-soft`, `--text-primary`, `--text-secondary`, `--text-muted`, `--border-subtle`, `--accent-*` and module semantic tokens;
- verify both `body[data-color-scheme="light"]` and dark/default;
- no `#fff`, `#111827`, `#475569` style literals for primary surfaces/text unless defining a semantic token;
- scrollbar, sticky headers, overlays and drag previews must render correctly in both themes;
- no washed-out text;
- no white islands in dark mode;
- focus rings visible in both themes;
- print stylesheet produces readable light output.

---

## 20. Frontend testing

### Unit/component

Use Vitest and the project’s React test setup. Add any missing test libraries only if needed.

Required tests:

- permission-based action visibility;
- period/version selection;
- assignment render by status;
- drag preview and invalid target state;
- optimistic update rollback;
- bulk selection;
- validation grouping and navigation to assignment;
- light/dark token use;
- reduced-motion behavior;
- keyboard drag operation;
- form validation and API error display.

### Playwright E2E

At minimum:

1. Planner creates period/version and assignment.
2. Drag assignment to another day and reload; persisted position remains.
3. Overlap produces blocker and prevents submit.
4. Fix blocker, submit, approve with separate approver, publish.
5. Employee views and acknowledges roster.
6. Approved leave conflicts with published assignment and creates amendment workflow.
7. Shift swap validates qualifications/rest and completes approval.
8. Task allocation updates capacity metrics.
9. Dark mode has no white surfaces and all controls remain readable.
10. 1920×1080 screenshot verifies sticky resource column, toolbar and timeline.
11. 1366×768 remains usable without control overlap.
12. Keyboard-only user can create/edit assignment and publish workflow.
13. Unauthorized user cannot see manager CTAs and receives 403 if calling API directly.

Commands:

```bash
cd frontend
npm ci
npm run lint
npm run test:unit
npm run build
npm run test:e2e:rostering
```

Expected: zero TypeScript errors, zero lint errors, zero failed tests.

---

# PART C — INTEGRATION AND VERIFICATION

## 21. Mandatory end-to-end verification scenario

Seed or create:

- one AMO with timezone `Africa/Nairobi`;
- two bases;
- Planning, Production, Quality and HR departments;
- planner, supervisor, quality approver, HR officer, certifying engineer and technicians;
- valid and expired authorisations;
- training event;
- approved leave;
- work order with task-card man-hour demand;
- day, night, standby, training and off shift templates;
- configurable rest and weekly-hour rules.

Execute:

1. HR creates active contracts and work patterns.
2. Planner creates monthly period and draft version.
3. Planner previews and commits pattern generation.
4. Planner drags assignments and allocates task demand.
5. System flags leave, training, expiry, rest and coverage issues.
6. Planner resolves blockers; authorized user records justified warning override.
7. Planner submits.
8. Separate supervisor/quality approver approves.
9. Approver publishes.
10. Notifications are logged for affected users.
11. Employee opens My Roster and acknowledges.
12. HR approves new leave that affects a published shift.
13. System creates/requests amendment; planner creates new version and republishes.
14. Old version is superseded, unchanged and auditable.
15. Attendance/timesheet generation compares roster, attendance and task work logs.
16. Approved timesheet exports payroll-ready rows.

Every step must be demonstrable through UI and API tests.

---

## 22. Performance requirements

At 1920×1080 with 150 personnel and a 31-day period:

- initial planner interactive target: under 3 seconds on normal development hardware after API response;
- drag feedback: under 100ms locally;
- assignment mutation response target: under 750ms excluding network extremes;
- use virtualization for resource rows and/or timeline cells;
- do not render all hidden cells or all assignment detail DOM at once;
- debounce search/filter requests;
- backend queries must avoid N+1 loading;
- assignment list requires indexed date/user/version filters;
- reports may run asynchronously only if an existing task mechanism is used and the UI provides status; do not fake completion.

Add a performance note or test fixture documenting row counts and observed timings.

---

## 23. Accessibility requirements

- WCAG 2.1 AA target;
- full keyboard navigation;
- visible focus;
- semantic buttons, dialogs, tables and headings;
- drag/drop has keyboard and screen-reader instructions;
- color is not the sole state indicator;
- dialogs trap focus and restore focus on close;
- error messages link to affected controls;
- status changes use restrained `aria-live` regions;
- minimum target sizes observed;
- run automated accessibility checks in E2E if the project permits adding `@axe-core/playwright`.

---

## 24. Required implementation evidence

Before declaring complete, provide:

1. exact migration revision IDs and `alembic heads` output;
2. list of files created/modified;
3. route inventory from FastAPI OpenAPI or route inspection;
4. backend test command output;
5. frontend lint/unit/build/E2E output;
6. screenshots at 1920×1080 for:
   - planner light mode;
   - planner dark mode;
   - blocker state;
   - planning board;
   - My Roster;
7. explanation of any intentionally deferred item with a tracked issue. Core routes and workflows in this contract may not be deferred.

---

## 25. Definition of done

The work is complete only when all statements below are true:

- planners can build a roster visually and efficiently;
- user management/workforce data directly controls eligibility and availability;
- approved leave, training, licences and authorisations affect validation;
- work-order demand and roster capacity are connected;
- lifecycle and separation of duties are enforced server-side;
- published records are immutable and amendments are versioned;
- employees can view, acknowledge, request leave and request swaps;
- attendance/timesheets produce planned-versus-actual and payroll-ready outputs;
- light and dark themes are both fully usable;
- drag/drop, resize, bulk actions, transitions and CTA states work with mouse and keyboard;
- reports and exports contain real data;
- backend and frontend tests pass;
- no placeholder page, static “Phase 1” notice, disconnected API, orphan table, unimplemented button or TODO remains in the delivered scope.

---

## 26. Coding-agent execution checklist

Execute in this exact order:

```text
[ ] Inspect current branch, migrations, model imports and tests.
[ ] Create/merge migration head correctly.
[ ] Build workforce models, schemas, services, permissions and routes.
[ ] Extend accounts/personnel import and module subscription integration.
[ ] Restructure rostering models and configurable validation.
[ ] Implement all backend routes and state transitions.
[ ] Integrate training, authorisations, bases, workload, notifications and audit.
[ ] Add backend fixtures and tests; make all pass.
[ ] Add frontend dependencies and complete typed API clients.
[ ] Split rostering pages/components/hooks.
[ ] Implement planner timeline, drag/drop, resize, bulk operations and drawers.
[ ] Implement dashboard, planning board, My Roster, leave, attendance, reports and settings.
[ ] Replace module CSS with semantic light/dark responsive design.
[ ] Update routes, canonical links, role access and navigation.
[ ] Add unit/component/E2E/accessibility tests.
[ ] Run migrations, backend tests, lint, unit tests, build and E2E.
[ ] Verify 1920×1080 and 1366×768 manually and by screenshot.
[ ] Hunt regressions across user management, training, work allocation and navigation.
[ ] Remove placeholders, dead code and obsolete Phase 1 copy.
[ ] Produce implementation evidence listed above.
```

Do not stop after creating models or a visual mockup. Completion requires a fully connected, tested workflow from personnel setup through roster publication, employee acknowledgement, actual-time reconciliation and reporting.