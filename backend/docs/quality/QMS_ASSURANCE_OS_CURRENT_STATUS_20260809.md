# QMS Assurance Operating System — Current MD Acceptance Status

**Date:** 2026-08-09  
**Pull request:** #488  
**Branch:** `agent/qms-assurance-operating-system-refactor`  
**Base verified at this status snapshot:** `main@e452af62e386db65eddda6ee4ef3d14eacd5739b`  
**Head at this status snapshot:** `ca878d197a0a661e4c3a667f078572f4b5f4113e`  
**Release state:** DRAFT — do not merge or mark ready until exact-head acceptance is green.

## 1. Acceptance source of truth

The original supplied implementation MD remains the acceptance contract. This document is a current code-to-requirement map; it is not a substitute for that MD and does not infer completion from CI alone.

The earlier `QMS_ASSURANCE_OPERATING_SYSTEM_REFACTOR_20260808.md` records the architecture and earlier implementation slices. Its phase/slice status statements are historical snapshots where they conflict with this current status file.

## 2. Current product architecture

The permanent Quality operating model remains:

```text
CONTROL ROOM | PLANNER | MISSIONS | PEOPLE | ASSURANCE | INTELLIGENCE
```

Specialist Audit Operations remain a deep governed workflow rather than being flattened into generic Quality registers.

The governing audit lifecycle remains:

```text
PROGRAMME
  → PLAN
  → SCHEDULE
  → PREPARE
  → NOTIFY
  → EXECUTE
  → FINDINGS
  → REPORT
  → CAR / FOLLOW-UP
  → EFFECTIVENESS
  → CLOSEOUT
  → TREND
```

## 3. Implemented and retained on PR #488

The current branch contains first-class implementations for the following original-MD requirements:

- six-workspace Quality information architecture;
- source-backed Control Room;
- governed Missions and capability-readiness gates;
- versioned Audit Programme and typed Audit Universe;
- programme requirement → authoritative Planner lineage;
- modern Planner plus strategic Year / Quarter and workload / coverage projections;
- deterministic schedule conflicts and controlled rescheduling;
- People & Privileges, eligibility and independence declarations;
- Assurance Cases and structured Investigation Studio;
- effectiveness plans plus governed downstream responses for ineffective/inconclusive reviews;
- deterministic Intelligence and source-attributed risk-planning context;
- Regulatory / Requirement Graph and Approval Digital Twin;
- governed audit preparation revisions with immutable issued snapshots;
- governed audit notice policies, revisions and lifecycle transitions;
- reusable checklist templates, immutable issued revisions and exact-revision audit binding;
- checklist template item governance for mandatory/optional semantics and finding-trigger policy;
- governed report revisions and formal report state transitions;
- separate `AUDIT EXECUTION CLOSED` and `ASSURANCE FOLLOW-UP COMPLETE` states;
- governed audit deferrals;
- custom and risk-triggered programme occurrences;
- Mission → Audit and Intelligence signal → Audit handoffs;
- PostgreSQL tenant RLS and cross-tenant denial probes for the new Quality-owned domains;
- immutable/append-only event history where the relevant domains require it.

## 4. Frontend integration correction completed on 2026-08-09

A code review found that multiple implemented specialist frontend hosts existed but were not mounted into the live Quality route tree. The global Quality enhancement host now mounts the governed operational surfaces instead of leaving them as dormant components.

Mounted surfaces now include:

- strategic Planner views;
- custom / risk-triggered programme occurrence controls;
- Mission / Intelligence audit handoffs;
- checklist revision governance;
- audit preparation intelligence;
- audit notice governance;
- report / closeout governance;
- effectiveness-response actions.

Audit-record detection excludes collection routes such as programme, schedule, register, checklists and reports so a collection route cannot be misinterpreted as an audit identifier.

## 5. Checklist governance status

Reusable template governance now retains, in the issued revision hash/snapshot:

- section / category;
- checklist reference;
- requirement reference;
- regulatory source;
- manual source;
- prompt;
- expected evidence;
- response type;
- applicability;
- mandatory / optional state;
- governed finding-trigger policy;
- sort order.

Finding-trigger policy does not auto-finalize a finding. Human auditor judgment remains authoritative.

### Residual checklist execution gap

The authoritative legacy execution row still exposes the historical response contract:

```text
PENDING
COMPLIANT
NON_CONFORMING
OBSERVATION
NOT_APPLICABLE
```

The original MD requires the execution contract to support:

```text
COMPLIANT
NONCOMPLIANT
OBSERVATION
NOT_APPLICABLE
NOT_VERIFIED
```

and to retain explicit auditor notes plus evidence attachment/reference semantics.

This must be closed additively. Existing `NON_CONFORMING` records must remain readable; they must not be destructively renamed. `NOT_VERIFIED` must remain an unresolved condition for legacy workflow gates rather than being treated as compliant completion.

## 6. Risk-planning status

The current deterministic risk-planning service fuses governed, attributable pressures including mandatory surveillance, regulatory criticality, universe risk, deferred programme requirements, open findings, overdue CARs, training expiry, supplier approval exposure, tooling/calibration exposure, high critical risks, pending changes, overdue management review, regulator findings, external commitments and Reliability signals.

The engine explicitly orders planning attention rather than declaring compliance or generating a predictive probability.

### Residual verification required

Before calling the original MD's risk-planning section complete, verify and, where needed, add explicit attributable factors for:

- time since last audit;
- repeat audit findings/history;
- ineffective corrective actions as a direct planning factor;
- safety occurrences as a named source contract;
- new capabilities / aircraft types where not already attributable through governed change/Mission sources.

No factor should be claimed merely because a similarly named aggregate exists elsewhere.

## 7. Audit lifecycle Playwright acceptance

A dedicated workflow now exists:

```text
.github/workflows/qms-audit-lifecycle-ci.yml
```

with check/job naming centered on:

```text
Audit lifecycle Playwright
```

It executes the existing focused Programme, modern Planner, Planner lifecycle, Planner → Audit handoff and Quality usability suites together with:

```text
frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts
```

The new governed lifecycle browser contract directly exercises:

- controlled preparation revision creation and issue;
- notice draft, review, approval, generation, delivery and acknowledgement;
- report adoption, internal review, approval and issue;
- execution closure as a state independent from assurance follow-up completion;
- retention of an open CAR/effectiveness obligation after execution closure;
- mobile closeout deep-link persistence across refresh.

### Acceptance still required

Do not declare the original 18-scenario browser Definition of Done complete until the dedicated exact-head check is green and each scenario is traceable to an executed assertion. In particular, independently confirm explicit browser assertions for:

- changing the auditor;
- controlled rescheduling;
- conflict detection;
- creating/associating a CAR from the audit lifecycle;
- checklist execution using the final canonical response contract.

## 8. CI status rule

Green build/typecheck or isolated unit tests are not sufficient.

Ready-for-review requires, on one exact PR head:

- Quality Module CI green;
- Audit lifecycle Playwright green;
- QMS Planner CI green when triggered;
- impacted Document Control Governance CI green;
- relevant PostgreSQL/RLS probes green;
- no required impacted repository check red or cancelled;
- PR still based on the intended current `main` reconciliation.

As of this document commit, the latest exact-head workflows were still queued/running. No green-completion claim is made here.

## 9. Remaining execution order

1. Prove the new dedicated lifecycle browser check and repair any exact assertion/integration failures.
2. Close the checklist execution response/notes/evidence-reference contract additively and preserve legacy data.
3. Audit the deterministic risk-planning factor list against the exact original MD and add only genuinely missing authoritative source factors.
4. Make every one of the original 18 Playwright scenarios independently traceable to an executed test assertion.
5. Reconcile this status back into the long-form architecture document once code and tests are stable.
6. Remove obsolete generic QMS surfaces only after their specialist replacements are proven and deep links remain safe.
7. Keep PR #488 draft until all exact-head acceptance checks are green.
