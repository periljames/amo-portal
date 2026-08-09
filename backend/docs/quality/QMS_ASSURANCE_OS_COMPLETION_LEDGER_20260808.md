# QMS Assurance Operating System — Completion Ledger

Date: 2026-08-08

This ledger records implementation completion against `QMS_ASSURANCE_OPERATING_SYSTEM_REFACTOR_20260808.md`.
It does not replace the architecture contract. GitHub exact-head checks remain the release proof.

## Governing ownership rule

Quality owns assurance coordination, approval decisions, audit governance, investigations and effectiveness.
The implementation does not create shadow operational masters for Document Control, Training & Competence,
Workforce/Rostering, Tooling/Calibration, Stores/Procurement, Maintenance, Fleet, Reliability or Safety.
Quality references those authoritative records with tenant-scoped typed source links and, where a governed
human decision needs an evidentiary record, controlled source snapshots.

## Operating workspaces

The active Quality operating model is now:

`CONTROL ROOM | PLANNER | MISSIONS | PEOPLE | ASSURANCE | INTELLIGENCE`

All six workspaces have real operational implementations. The generic workspace bridge is no longer the
active destination for People, Assurance or Intelligence.

### Control Room

Implemented as a decision-first operating picture:

- assigned decisions and work;
- source-backed priority signals;
- explicit regulatory-consequence exposure;
- upcoming obligations;
- performance drift;
- data/source health;
- unassigned exposure;
- evidence freshness.

Diagnostics remain subordinate to the operating picture. Hard legal or regulatory conditions are not
converted into invented compliance percentages.

### Planner

The existing authoritative Quality Planner remains in place and is extended rather than replaced.
It retains:

- recurring and one-time audit scheduling;
- deterministic personnel/location conflict detection;
- explicit conflict override rationale;
- versioned rescheduling with human reasons;
- lifecycle suspend/resume controls;
- notifications and materialization into real audits;
- programme-to-schedule lineage.

New governed auditor assignment gates now sit in front of authoritative Planner writes and immediately
before automatic audit materialization.

When a tenant has configured Quality auditor privilege rules, assignment eligibility is a hard gate across:

- active same-tenant workforce identity;
- active Quality privilege and scope;
- privilege effective/expiry dates;
- current verified Training records from the authoritative Training module;
- configured concurrent-assignment capacity;
- assignment-specific independence declaration when required.

A schedule that later fails a governed assignment gate is suspended before audit materialization and a
critical audit event is recorded. Tenants that have not yet configured the corresponding Quality privilege
rules remain in explicit legacy-compatibility mode so rollout does not silently disable established
operations.

### Missions

Governed cross-department Missions are implemented with tenant RLS and attributable decisions.
The first operational template, `CAPABILITY_ADDITION`, uses hard readiness gates for approval/rating,
facilities, technical data, tooling, materials, personnel, training evidence, procedures, contracted
functions, manpower coverage and safety/change assessment.

Mission evidence points to owning modules; it does not copy their master records. Hard gates cannot be
averaged into a synthetic compliance score. Quality self-evaluation and Accountable Executive/authority
steps remain explicit human decisions.

### People & Privileges

Implemented as Quality's internal authorization and independence layer while Training, Workforce and
Rostering remain authoritative for their records.

Capabilities include:

- configurable Quality privilege rules;
- scoped privilege drafts and immutable grant/renew/suspend/reinstate/revoke/expire/reject decisions;
- effective/expiry dates and limitations;
- authoritative Training evidence checks;
- workload/capacity evidence;
- assignment-specific independence declarations;
- hard eligibility evaluation;
- authorization-board UI and source-gate explanations.

### Assurance

Implemented as the source-backed problem/investigation/effectiveness workspace.

Capabilities include:

- governed assurance cases and attributable lifecycle history;
- source references and regulatory basis;
- method-driven Investigation Studio;
- `FACT`, `HYPOTHESIS` and `CAUSAL_CONCLUSION` epistemic classes;
- 5 Whys, Ishikawa, causal-factor, barrier, change and human/organizational methods;
- prevention of causal-conclusion promotion without recorded facts and explicit evidence;
- corrective-action effectiveness plans with expected outcome, measure, verification method,
  observation window, reviewer and planned review date;
- immutable effectiveness conclusions with evidence;
- ineffective, partially effective or inconclusive results returning the case to action rather than
  silently allowing closure.

The existing audit finding and CAR/CAPA records remain authoritative. Assurance coordinates and tests
outcomes; it does not replace those records.

### Intelligence

Implemented as a deterministic, explainable read/governance layer rather than an opaque predictive score.

Capabilities include:

- live programme completion/deferral aggregates;
- finding recurrence and open-finding metrics;
- overdue CAR and CAR-age metrics;
- ineffective-action rate;
- auditor capacity/coverage exceptions;
- open assurance-case metrics;
- configurable deterministic threshold rules;
- immutable signal observations with formula/source snapshots;
- risk-targeted surveillance ordering that never averages away mandatory surveillance;
- requirement/approval impact graph with typed source nodes and immutable relationships;
- Approval Digital Twin states: `SUPPORTED`, `UNSUPPORTED`, `STALE`, `UNRESOLVED`, `BLOCKED`.

The Approval Digital Twin is explicitly an evidence-support/readiness view. It never declares regulatory
compliance.

## Audit Programme and Audit Universe

Implemented as governed planning primitives around the existing audit schedule/execution engine:

- versioned annual/periodic programmes;
- explicit `DRAFT → UNDER_REVIEW → APPROVED → ACTIVE → SUPERSEDED/CLOSED` lifecycle;
- approved/active records are not edited in place;
- amendments create new draft revisions with lineage;
- immutable programme events;
- tenant-owned Audit Universe with typed authoritative source pointers;
- risk classification, regulatory criticality and mandatory-surveillance flags;
- governed recurrence and target windows;
- bounded scheduling queue;
- transactional programme-item → authoritative Planner schedule linkage;
- deterministic conflict validation and programme-window enforcement.

## Audit lifecycle completion

The existing specialist audit engine remains authoritative for execution and continues to provide:

- audit reference generation;
- notices/reminders and auditee/auditor communication;
- document requests;
- executable checklist items;
- War Room/run hub;
- findings and evidence;
- post-brief/report tracking;
- CAR issuance and extension governance;
- report/checklist closeout gates;
- archive packages and audit history.

This refactor adds two missing governance layers without duplicating that engine.

### Auditor assignment eligibility and independence

The canonical schedule create/resume and programme-to-Planner routes are guarded by People & Privileges.
The original Planner/programme scheduling functions remain the delegated schedule authority.

Independence-required governed assignments cannot be activated/executed without an attributable declaration.
Automatic materialization re-checks current eligibility so an expired privilege/training record or later
conflict cannot silently become a live audit.

### Controlled audit preparation snapshots

Audit preparation now supports versioned source snapshots containing the exact:

- audit scope/criteria/assigned personnel/planned dates;
- checklist items and requirement references;
- document requests and review state;
- typed source references.

Each snapshot receives a SHA-256 fingerprint. A draft cannot be issued if any live preparation source changed
after the snapshot was created; Quality must create a new revision. Issued revisions are immutable and
preparation history is append-only.

This preserves what the auditor actually relied on without replacing the live checklist or document-request
records.

## Database assurance and tenancy

New governance tables are tenant-owned and use PostgreSQL `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL
SECURITY` policies keyed to the application tenant context.

Immutable/append-only database enforcement covers decision/evidence history including:

- Mission decisions;
- Audit Programme events;
- Quality privilege decisions;
- independence declarations;
- investigation entries;
- assurance-case events;
- signal observations;
- requirement-graph relationships;
- issued audit-preparation revisions;
- audit-preparation events.

CI contains PostgreSQL cross-tenant probes and mutation-denial checks. Exact-head GitHub Actions remain the
source of truth for whether those probes have passed on a candidate release head.

## Frontend completion

Operational surfaces now cover:

- six-workspace Quality navigation;
- assurance Control Room;
- governed Missions portfolio/detail;
- Audit Programme and Audit Universe;
- Planner programme scheduling handoff;
- People authorization board and hard eligibility review;
- Assurance case portfolio, Investigation Studio and effectiveness engineering;
- Intelligence metrics, deterministic signals, targeted surveillance and Approval Digital Twin;
- existing specialist Audit, CAR, DMS and continuous-assurance deep links.

No seeded/fabricated operating numbers are used as live product data.

## Compatibility strategy

The refactor deliberately preserves established specialist paths while ownership migrates:

- canonical `/quality` is primary;
- legacy `/qms` tenant API aliases remain contract-compatible where required;
- legacy assurance-hub deep links continue to work;
- existing Audit/CAR record-level workflows are not replaced by generic workspace screens;
- People hard gates become authoritative when tenant privilege rules are configured, allowing controlled
  migration instead of a flag-day cutover.

## Release proof required before promotion

PR #488 must remain draft until its current exact head proves all impacted gates, including:

- migration-chain contract;
- Python compilation and SQLAlchemy mapper configuration;
- Audit Programme and Assurance OS contracts;
- existing Quality workflow/dashboard regression suites;
- PostgreSQL schema hardening;
- continuous-assurance RLS/event probe;
- Mission RLS probe;
- Audit Programme/RLS/Planner-lineage probe;
- People/Assurance/Intelligence/Approval Graph RLS and immutability probe;
- completed Assurance OS + Audit Preparation RLS and immutability probe;
- frontend Quality unit tests;
- CSS ownership contract;
- TypeScript production build;
- Control Room/browser usability;
- Missions browser contract;
- Audit Programme browser contract;
- People/Assurance/Intelligence browser contract;
- bounded-register browser contract;
- Planner deterministic/lifecycle/audit-handoff browser contracts;
- Quality-owned frontend lint;
- impacted repository workflows triggered by the PR.

A green result on an earlier SHA is not sufficient proof for a later head.

## Non-goals preserved

The implementation intentionally does not:

- turn Quality into a duplicate Training, Workforce, DMS, Tooling, Stores, Procurement or Maintenance system;
- allow AI/rules to approve a Mission, close a case, declare a root cause without evidence, or declare
  regulatory compliance;
- replace the mature Audit War Room, CAR/CAPA, Planner or Document Control engines with generic CRUD;
- hide hard regulatory conditions inside an averaged readiness score.
