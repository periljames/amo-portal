# Rostering Fullstack Reference and Execution Plan

Primary implementation issue: #347  
Scenario matrix: `docs/rostering-scenario-matrix.md`

## 1. Purpose

This document is the authoritative product, architecture, implementation and validation reference for the Rostering overhaul. It consolidates the agreed decisions, additional audit findings, cross-module requirements and delivery sequence so implementation agents do not guess, duplicate ownership or reduce the module to passive cards and lists.

The target is a usable operational system for tenant administrators, roster planners, supervisors, Quality, HR/Workforce and employees. The planner must support real roster creation and controlled change. Compliance must support corrective action. Operations and reports must expose live project/work-order progress rather than static summary cards.

## 2. Concurrency boundaries

Concurrent agents are active. Changes must be stacked and isolated.

- PR #349 owns the first Operating Structure and guided-setup implementation slice.
- PR #352 is documentation and acceptance criteria only.
- Follow-on implementation branches must stack on the latest approved predecessor.
- Do not modify unrelated Quality, Publications/Document Control, global shell, shared navigation or SaaS files unless a direct Rostering contract requires it.
- Every PR description must state the owned files and the files intentionally avoided.
- Before editing a shared file, inspect open PRs and confirm that no concurrent branch owns the same area.

## 3. Canonical ownership

### 3.1 Personnel

Personnel identity remains `accounts.users.id`. Rostering must never create a second employee/person table.

Inactive, suspended, terminated and system accounts are not roster-eligible. Historical records remain readable.

### 3.2 Bases and stations

Base/station master data is tenant-wide shared foundation data, not Rostering-owned data.

Canonical records:

- `foundations.base_stations`
- `foundations.base_station_aliases`
- `foundations.user_base_assignments`

Administrative home:

`System Admin -> Organisation Setup -> Bases & Stations`

Rostering, Workforce, Planning, Production, Maintenance, Training, Quality, Stores and reporting consume the same base IDs.

A Rostering setup page may deep-link to or embed the canonical admin component. It must not create a duplicate base table or infer the available base list from personnel records.

### 3.3 Source-owned commitments

- Approved leave and unavailability remain Workforce-owned.
- Training events and training validity remain Training-owned.
- Quality audit assignments remain Quality-owned.
- Work orders and tasks remain Maintenance/Production-owned.
- Rostering projects these records into the planner and never duplicates or rewrites them.

## 4. Base and personnel mobility model

### 4.1 Distinct concepts

The portal must keep the following concepts separate:

1. **Home base** — durable personnel placement.
2. **Temporary deployment** — where the person is assigned for a defined period.
3. **Base eligibility** — bases where the person is allowed to work.
4. **Actual duty base** — base stored on a specific roster assignment.
5. **Authorisation scope** — aircraft, task, licence and certification limitations for that base/work.

A deployment does not automatically grant technical authorisation.

### 4.2 Assignment kinds

- `HOME_BASE`
- `TEMPORARY`
- `RELIEF`
- `TRAINING`
- `OTHER`

Temporary, relief and training placements must normally have an end date. Open-ended records require an explicitly authorised exception with a reason and warning.

### 4.3 Effective-date behaviour

- Home base is not overwritten by a temporary movement.
- Temporary/relief/training overlays take precedence during their effective windows.
- Date boundaries are inclusive and consistent across API, planner, reports and exports.
- Overnight shifts resolve the suggested base using the assignment's local start time.
- The assignment persists its actual `base_station_id`; later deployment edits do not silently rewrite the assignment.
- A deployment change affecting draft or published assignments creates an impact list and requires revalidation.

### 4.4 Cross-base travel

Maintain configurable travel/positioning time between bases. Cross-base consecutive assignments must validate:

- travel/positioning time;
- reporting time;
- minimum rest after travel where applicable;
- warning versus hard-stop classification from the controlled rule source.

## 5. Base administration requirements

### 5.1 Base fields

- canonical code;
- name;
- type;
- ICAO/IATA where applicable;
- IANA time zone;
- aliases;
- description;
- active state;
- effective-dated temporary closure windows;
- optional capability metadata such as line maintenance, workshop or training site.

### 5.2 Validation

- Tenant isolation for all reads and writes.
- Code and alias uniqueness after case/spacing normalisation.
- Valid IANA timezone only.
- Inactive bases cannot receive new deployments or assignments.
- Deactivation requires dependency impact analysis.
- Renaming preserves historical readability and records the old code as an alias.

### 5.3 Controlled deactivation

Before deactivation, show dependencies:

- current/future deployments;
- draft and published roster assignments;
- open work orders/tasks;
- training events;
- Quality audits;
- inventory/store locations;
- aircraft allocations.

Block deactivation until dependencies are reassigned, or use an effective-dated closure workflow.

### 5.4 Controlled merge

Support merging duplicate physical base records:

1. Select surviving base.
2. Preview all affected records.
3. Repoint foreign keys transactionally.
4. Preserve retired codes as aliases.
5. Record append-only audit evidence.
6. Reject merge where incompatible tenant or protected historical constraints exist.

## 6. Permission, privacy and audit model

Do not use hardcoded account-role checks as the final authority.

Required capability families:

- `organisation.bases.view`
- `organisation.bases.manage`
- `workforce.deployments.view`
- `workforce.deployments.manage`
- `roster.view_own`
- `roster.view_department`
- `roster.view_all`
- `roster.create`
- `roster.edit`
- `roster.delete_draft_assignment`
- `roster.validate`
- `roster.submit`
- `roster.approve`
- `roster.publish`
- `roster.amend_published`
- `roster.override_warning`
- `roster.override_blocker`
- `roster.manage_rules`
- `roster.manage_shift_templates`
- `roster.manage_patterns`
- `roster.allocate_work`

Capabilities may be scoped to department and/or base. Explicit deny wins over role-derived grant.

Ordinary employees may not enumerate tenant-wide deployment history. Quality assurance visibility must be distinct from the right to move personnel.

Every critical mutation records:

- tenant;
- actor;
- action;
- reason;
- before/after state;
- timestamp;
- correlation ID;
- state revision;
- source IP/device metadata where already supported by the platform.

Use optimistic concurrency for base, deployment, roster assignment and lifecycle mutations. A stale revision returns a conflict with reload/compare guidance instead of silently overwriting.

## 7. Contextual help and prerequisites

### 7.1 One-time help

Explanations useful only during onboarding must not occupy permanent page space.

The reusable contextual-help system must:

- auto-open only on first successful access per tenant, user, topic and version;
- persist acknowledgement server-side;
- use local storage only as an offline fallback;
- reopen from a small unobtrusive help icon;
- reappear once when the content version increases;
- distinguish closing from acknowledging;
- trap and restore focus;
- make the background inert;
- support keyboard and screen readers.

Escape, backdrop click and the close icon close the dialog without marking it acknowledged. Only `Got it` or an explicit acknowledgement action persists acknowledgement.

### 7.2 Prerequisite dialogs

Every operational page evaluates prerequisites before presenting an unusable workspace.

Examples:

- no active bases;
- no active shifts;
- no planning period;
- no draft version;
- no eligible personnel;
- missing employment contract;
- no approval authority;
- no active rule set;
- no work estimates for capacity/Gantt;
- missing permission;
- degraded integration source.

Each dialog must show:

- what is missing;
- why it matters;
- exact corrective action;
- primary action to the correct page/subsection;
- optional secondary valid action;
- return URL back to the interrupted workflow;
- `Continue read-only` only when a meaningful read-only workflow exists.

Query-string actions such as `?tab=shifts` and `?tab=periods` must actually open those sections.

## 8. Planner requirements

### 8.1 Progressive loading

Render independently:

1. page shell and period/version controls;
2. visible grid structure;
3. personnel pages;
4. assignments;
5. source-owned commitments;
6. findings;
7. capability diagnostics.

A failed/hanging commitments, findings or contracts request must not hold the whole planner in an indefinite spinner.

Every pane needs:

- request timeout/abort;
- stale/cached timestamp;
- retry;
- degraded state;
- correlation/diagnostic ID;
- no automatic blanking of already loaded data.

### 8.2 Core editing

Visible and permission-aware actions:

- create period;
- create draft version;
- create assignment;
- edit assignment;
- move/reassign;
- delete draft assignment;
- bulk assign;
- apply work pattern;
- copy/paste week;
- duplicate previous period;
- validate;
- submit;
- approve;
- publish;
- controlled amendment of published roster.

Do not silently hide all controls. A disabled control explains the missing permission or lifecycle restriction and links to the corrective administration page where appropriate.

### 8.3 Base behaviour

Assignment editor uses canonical active bases.

Default base comes from the effective deployment on the assignment's local start date. If the planner chooses another base:

- validate base eligibility and authorisation;
- validate travel/rest;
- offer to create a dated temporary/relief deployment when authorised;
- otherwise cancel or keep the current base.

### 8.4 Bulk/offline/concurrency

- Non-atomic bulk mode creates valid rows and reports indexed conflicts.
- Atomic mode rolls back everything on conflict.
- Source-owned commitments are never copied or duplicated.
- Offline mutations are idempotent and visible in an outbox.
- Replay after publication becomes a conflict, never a silent published-roster edit.
- Two planners editing the same assignment receive optimistic-concurrency conflict handling.

### 8.5 Scale

Support at least 2,000 personnel and a four-week horizon through:

- server-side search/filter;
- pagination;
- grid virtualisation;
- lazy secondary details;
- bounded cache and DOM size;
- no `load all people` dependency.

## 9. Rostering setup requirements

Replace excessive pill navigation with six operational sections:

1. Operating structure
2. Shift library
3. Work patterns
4. Compliance policy
5. Approval workflow
6. Integrations and preferences

### 9.1 Shift library

Support:

- create;
- edit;
- clone;
- activate/deactivate;
- controlled delete when unused;
- reorder;
- day/night/standby/training/off/leave/travel/other;
- local start/end and overnight handling;
- duty-time classification;
- colour/icon presentation without hardcoded business meaning.

### 9.2 Work patterns

Use a visual cycle builder. Support exceptions, effective dates, preview, clone and safe application to a draft.

### 9.3 Approval workflow

Configure scoped planners, department heads, base managers, approvers and publishers with separation-of-duties checks.

## 10. Compliance action queue

Compliance must be actionable, not a passive report.

Each finding includes:

- employee;
- assignment/date;
- base/department;
- exact rule;
- source document/clause;
- effective date;
- severity/classification;
- overridability;
- owner;
- corrective actions;
- current workflow state.

Actions:

- open assignment;
- replace employee;
- move/remove duty;
- open Training/Licence/Authorisation record;
- request override;
- attach reason/evidence;
- approve/reject override;
- revalidate.

Rule classes:

- statutory hard stop;
- approved MoPM hard stop;
- operational warning;
- advisory.

No numerical value may be presented as a KCAR 2025 statutory limit without a controlled regulation citation. Draft planning remains possible where safe; unresolved non-overridable hard stops block publication.

Override requester and approver must be different where separation of duties applies.

## 11. Operations and reports

Replace shallow report cards with an `Operations` workspace combining capacity, projects/work orders and live progress.

Collapsed rows show:

- aircraft/project/work order;
- planned and actual dates;
- progress;
- planned/consumed/remaining man-hours;
- staffing;
- certifying coverage;
- blockers;
- delay;
- forecast completion;
- freshness timestamp.

Expand a row to lazy-load its Gantt:

- phases/tasks;
- planned and actual bars;
- dependencies;
- milestones;
- critical path;
- assigned personnel;
- roster coverage;
- training/licence conflicts;
- remaining effort;
- delay and aircraft ground-time impact.

Supervisor actions:

- reallocate personnel;
- open roster assignment;
- open Production/Maintenance task;
- authorised plan adjustment;
- record delay reason;
- escalate blocker;
- add progress note.

Exports are secondary and include data-as-of time, filters and source freshness.

## 12. Cross-module behaviour

Required reactions:

- Leave approved after publication creates an immediate conflict and amendment path.
- Training at another base shows time/location and may prompt a deployment.
- Quality audit overlap links to the source audit.
- Contract expiry blocks only duty after expiry.
- Suspension/deactivation removes future eligibility and blocks publication.
- Work-order base/date changes recalculate capacity and forecast.
- Attendance at another base creates a review mismatch without rewriting roster history.
- Imported legacy base aliases resolve to canonical IDs or quarantine.
- Source outages show cached data and freshness without blocking Planner core.
- Corrected/deleted source records reconcile idempotently.

## 13. Immediate audit findings in PR #349

The first implementation slice must resolve or explicitly hand off:

1. Setup links include `?tab=shifts` and `?tab=periods`, but Setup must consume those query parameters.
2. Contextual help is local-storage only; Escape/backdrop/close currently acknowledge unintentionally.
3. Prerequisite dialog always offers read-only continuation, including hard prerequisites.
4. Operating Structure loads bases, up to 250 people and all deployments in one `Promise.all`.
5. Base tab unnecessarily depends on people/deployments.
6. Large tenants are truncated.
7. Deployment permissions use hardcoded roles rather than scoped capabilities.
8. Tenant-wide deployment listing lacks explicit privacy permission.
9. Deployment validation must reject inactive/suspended/terminated users.
10. `End today` fails for future deployments and is ambiguous for inclusive dates.
11. Open-ended temporary/relief/training deployments are uncontrolled.
12. Base deactivation lacks dependency analysis, reason, audit and concurrency.
13. Effective-base resolution is not yet applied to roster assignment defaults.
14. Mutations reload all datasets rather than updating/invalidation by query.
15. Contextual dialogs need focus trap, focus restoration and background inertness.

## 14. Test strategy

### 14.1 Backend unit

- date validation and inclusive boundaries;
- deployment precedence;
- active-user eligibility;
- scoped permission and explicit deny;
- state revisions;
- source-owned commitment guards;
- rule classification;
- override separation of duties;
- idempotency.

### 14.2 PostgreSQL integration

- tenant isolation;
- alias/code uniqueness;
- concurrent deployment/base edits;
- migration from existing data;
- controlled deactivation/merge transactions;
- audit evidence;
- published-roster impact.

### 14.3 Frontend component

- server/local guidance acknowledgement;
- close versus acknowledge;
- prerequisite hard/soft modes;
- exact query-subsection navigation;
- independent error/loading states;
- permission explanations;
- large-list pagination/virtualisation;
- accessibility.

### 14.4 Authenticated Playwright

Seed and test:

- AMO Admin;
- Planner;
- Supervisor;
- Quality;
- Employee.

Use real clicks and mutations against the rendered portal. Source-string tests alone do not satisfy acceptance.

### 14.5 Network/offline

- synthetic 2G cold and warm loads;
- one hanging source;
- one failing source;
- offline after initial load;
- duplicate replay;
- replay after publication;
- stale tenant cache isolation.

## 15. Delivery sequence

1. PR #349: Operating Structure, canonical base APIs/UI, contextual help and prerequisites.
2. Hardening PR: server acknowledgement, scoped permissions/privacy, deployment lifecycle, audit, concurrency, independent queries and exact setup routing.
3. Planner PR: progressive loading, diagnostics, base defaults and full draft editing/bulk/copy/pattern flows.
4. Setup PR: shift lifecycle, visual patterns, approval workflow and sourced compliance policy.
5. Compliance PR: remediation and override workflow.
6. Operations PR: live work hierarchy, capacity and lazy Gantt.
7. E2E PR: role, browser, network, offline, accessibility and final UX cleanup.

Each implementation test should reference scenario IDs from `docs/rostering-scenario-matrix.md`.

## 16. Definition of done

The overhaul is not complete until:

- Admin and Planner can create and modify real roster data through the UI.
- Missing setup leads to direct corrective actions rather than empty pages.
- Optional integrations cannot cause indefinite Planner loading.
- Personnel mobility, bases and roster assignments are canonical, effective-dated and auditable.
- Source-owned leave/training/Quality records remain source-owned.
- Compliance findings can be corrected through linked workflows.
- Supervisors can see live work progress and lazy Gantt detail.
- Role, tenant, concurrency, slow-network and offline tests pass on the exact merge head.
