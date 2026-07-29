# Rostering Automation and Workforce/HR Overhaul

Date: 2026-07-28  
Implementation branch: `agent/rostering-automation-workforce-hr-overhaul`  
Parent contract: issue #347  
Synchronized main baseline: `f20fef6a29817fc5a777557860ce356ef82c881c`

## Purpose

Replace the duplicated, form-heavy Rostering Setup page with a guided operational setup workspace and expose the existing canonical Workforce backend as a coherent HR workspace. This change does not create a second employee, contract, leave, attendance, timesheet or pattern-assignment data model.

## Domain ownership

### Rostering owns

- roster periods and immutable versions;
- shift templates;
- roster assignments;
- draft generation from effective work patterns;
- roster validation findings;
- controlled rule sets and approval authorities;
- submission, approval, publication and amendment lifecycle;
- automation policy and immutable automation-run evidence.

### Workforce and HR own

- employment contracts and employment status;
- supervisors, FTE, standard hours and payroll identifiers;
- employee work-pattern assignments and effective dates;
- leave types, balances, requests and approvals;
- availability and attendance events;
- timesheets and overtime requests;
- payroll readiness and export permissions.

### Shared Foundations owns

- canonical bases and stations;
- effective-dated home, temporary, relief and training deployments.

## User experience

Primary Rostering navigation is now:

1. Command
2. Planner
3. Operations
4. Compliance
5. My duty
6. Workforce
7. Setup

Capacity and Reports are combined in Operations. Workforce is presented as a top-level workspace using an existing conflict-safe Rostering route deep link while the active Document Control router work remains untouched.

## Guided Setup

The previous stack of `RosterPeriodQuickActions`, `RosterRuleQuickEditor` and `UnifiedRosterSettings` is replaced by one workspace containing:

- readiness summary and direct actions;
- one planning-period register;
- automatic future-period policy;
- automatic draft rotation policy;
- preview and explicit confirmation before generation;
- shift library create/edit/clone/deactivate lifecycle;
- visual mixed-shift work-pattern builder;
- controlled compliance-rule classification;
- approval-authority summary;
- immutable automation-run history.

Contracts, leave policy, leave approval, timesheet approval, payroll export and personal planner preferences are no longer presented as Rostering setup concepts.

## Automation safety contract

Automation:

- is tenant scoped;
- is idempotent by `(amo_id, idempotency_key)`;
- uses optimistic concurrency for policy changes;
- creates periods and draft versions only;
- can generate draft assignments from effective Workforce pattern assignments;
- retains skipped and conflicting items;
- validates the generated draft when configured;
- records failed execution evidence;
- never submits, approves or publishes a roster.

The final merge-safety pass also guarantees that:

- policy revisions are locked before their expected revision is checked;
- reused draft versions are locked and revalidated as `DRAFT` before mutation;
- manual generation does not advance or suppress the scheduled cadence;
- concurrent identical manual requests return the matching winning run instead of a false database-conflict response;
- failed, mismatched and still-running idempotent replays remain explicit conflicts;
- leave rejection is shown only to users with the effective review permission.

## Persistence

Migration `rostering_20260728_automation_policy` adds:

- `roster_generation_policies`;
- `roster_generation_runs`.

The policy is one row per AMO. Run records are append-only execution evidence and retain generation counts, conflicts, validation outcomes, error messages and structured summaries.

## API

- `GET /rostering/setup/readiness`
- `GET /rostering/automation-policy`
- `PATCH /rostering/automation-policy`
- `POST /rostering/automation/preview`
- `POST /rostering/automation/run`
- `GET /rostering/automation/runs`
- `GET /workforce/hr/dashboard`

## HR workspace

The HR dashboard projects canonical source records into:

- active, onboarding and suspended employee metrics;
- expiring-contract actions;
- missing-base and missing-pattern actions;
- leave approvals;
- attendance and timesheet controls;
- overtime and payroll readiness;
- employee-level operational readiness.

All mutations continue to use the existing Workforce APIs and permission model. The dashboard requires `workforce.view_sensitive`; individual actions remain protected by their existing contract, leave, time and payroll permissions.

## Validation requirements before merge

- Alembic graph verification;
- clean PostgreSQL migration;
- legacy overlapping-head repair;
- backend compilation and mapper configuration;
- Rostering and Workforce regressions;
- frontend TypeScript/Vite build;
- frontend source-contract tests;
- integrated lint;
- authenticated browser use by AMO Admin, Planner, Supervisor, HR Manager and ordinary Employee;
- synthetic constrained-network validation for Planner, Workforce and Setup.
