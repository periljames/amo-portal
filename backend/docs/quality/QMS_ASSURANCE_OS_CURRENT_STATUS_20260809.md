# QMS Assurance Operating System — Current MD Acceptance Status

**Date:** 2026-08-09  
**Pull request:** #488  
**Branch:** `agent/qms-assurance-operating-system-refactor`  
**Release state:** DRAFT until the exact head carrying this document is green.  
**Acceptance source of truth:** the original supplied implementation MD.

## 1. Product architecture implemented

The permanent Quality operating model is:

```text
CONTROL ROOM | PLANNER | MISSIONS | PEOPLE | ASSURANCE | INTELLIGENCE
```

Audit Operations remains a specialist governed workflow inside the Quality assurance system:

```text
PROGRAMME → PLAN → SCHEDULE → PREPARE → NOTIFY → EXECUTE → FINDINGS
→ REPORT → CAR / FOLLOW-UP → EFFECTIVENESS → CLOSEOUT → TREND
```

The branch implements the six-workspace information architecture without copying authoritative Training, Workforce, Tooling, Stores/Procurement, DMS, Maintenance, Fleet, Reliability or Safety master data into QMS.

## 2. Original-MD material scope completed in code

The current branch contains first-class governed implementations for:

- source-backed Control Room;
- governed Missions, readiness gates and approval decisions;
- versioned Audit Programme and typed Audit Universe;
- programme requirement → authoritative Planner lineage;
- Year / Quarter / Month / Week / Agenda planning plus workload and coverage perspectives;
- deterministic scheduling conflict detection and controlled rescheduling;
- People & Privileges, hard eligibility checks and independence declarations;
- Assurance Cases and structured Investigation Studio;
- effectiveness plans and governed responses for ineffective/inconclusive reviews;
- deterministic Intelligence, Requirement Graph and Approval Digital Twin;
- governed audit preparation revisions with immutable issued snapshots;
- controlled notice policy/revision lifecycle through acknowledgement;
- reusable checklist templates with immutable issued revisions and exact audit binding;
- checklist item mandatory/optional state and finding-trigger policy;
- governed checklist execution with canonical response vocabulary, auditor notes and structured evidence references;
- governed report revisions and `DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED → SUPERSEDED` transitions;
- separate `AUDIT EXECUTION CLOSED` and `ASSURANCE FOLLOW-UP COMPLETE` states;
- governed deferrals with decision/apply workflow;
- custom and risk-triggered programme occurrences;
- Mission → Audit and Intelligence signal → Audit handoffs;
- governed downstream responses to ineffective effectiveness reviews, including follow-up audit, CAR reopening, additional action, escalation and risk reassessment;
- PostgreSQL tenant RLS/cross-tenant probes and append-only event history for the new Quality-owned governance domains.

## 3. Checklist execution contract

The original checklist execution row historically stores:

```text
PENDING | COMPLIANT | NON_CONFORMING | OBSERVATION | NOT_APPLICABLE
```

The governed execution layer now exposes the MD vocabulary:

```text
COMPLIANT | NONCOMPLIANT | OBSERVATION | NOT_APPLICABLE | NOT_VERIFIED
```

Compatibility is intentionally additive:

- `NONCOMPLIANT → NON_CONFORMING` in the historical row;
- `NOT_VERIFIED → PENDING` in the historical row so old closeout gates remain unresolved.

The same authoritative checklist item is retained. The governance record adds attributable auditor notes, structured evidence references and append-only execution events; it is not a second checklist engine.

## 4. Risk-based audit planning contract

`GET /audit-programmes/risk-context` now provides deterministic, source-attributed planning context. Mandatory surveillance remains a hard obligation and is never averaged away.

Implemented attributable factors include:

- mandatory regulatory surveillance;
- regulatory criticality and previous governed Audit Universe risk;
- time since last attributable audit;
- historical audit findings;
- repeat requirement findings across distinct audits;
- overdue CARs;
- governed ineffective corrective-action effectiveness conclusions;
- organizational/process change exposure;
- governed capability additions/changes from Missions;
- aircraft-type exposure only from explicit governed Mission scope keys;
- supplier approval exposure;
- Reliability events, recurrence and recommendations;
- tooling/calibration and out-of-tolerance exposure;
- training/competence exposure;
- Safety occurrences only through explicit `safety / SAFETY_OCCURRENCE` source references;
- management-review actions;
- regulator findings and external commitments;
- governed deferral pressure.

Calculated factors expose their factor/rule, source category, source-record reference, source date/observation date and rationale. The engine does **not** produce a predictive probability or automated compliance conclusion.

Safety-source rule: generic risk records are never relabelled as Safety occurrences. Specific Safety targeting requires an explicit source reference; specific universe targeting requires an explicit `audit_universe_source_id`.

Aircraft-source rule: free-text Mission titles/descriptions are never parsed as aircraft-type evidence. Aircraft-type exposure requires an explicit Mission scope field such as `aircraft_type`, `aircraft_types`, `aircraft_type_id` or `aircraft_type_ids`.

## 5. Audit lifecycle browser acceptance

Dedicated workflow:

```text
.github/workflows/qms-audit-lifecycle-ci.yml
```

The complete requirement-to-browser trace is maintained in:

```text
backend/docs/quality/QMS_AUDIT_ACCEPTANCE_TRACE_20260809.md
```

The suite now gives named deterministic ownership to all 18 original MD scenarios, including the previously weakly traced actions:

- changing the lead auditor through the authoritative schedule-participant PATCH;
- creating a structured finding from the Run Hub;
- creating and associating a CAR using the exact persisted finding ID;
- governed checklist execution using the canonical response contract.

The lifecycle suite also covers Programme creation/scheduling, quick Planner handoff, conflicts, controlled rescheduling, notices, preparation, reporting, execution closure, retained follow-up, keyboard use, constrained viewports and refresh/deep-link persistence.

## 6. Frontend integration and route ownership

The global Quality enhancement host mounts the governed specialist controls for:

- strategic Planner views;
- custom/risk-triggered programme occurrences;
- Mission/Intelligence audit handoffs;
- checklist template revision governance;
- checklist execution governance;
- preparation intelligence;
- notice governance;
- report/closeout governance;
- effectiveness-response actions.

Audit-record detection excludes collection routes so `program`, `schedule`, `register`, `checklists`, `reports` and similar collection paths are never treated as audit identifiers.

### Generic-surface cleanup result

The cleanup requirement was audited rather than interpreted as a deletion target.

Main audit dashboard, planning, schedule detail, register and Run Hub routes already have specialist owners. Two bounded collection routes remain behind the canonical compatibility dispatcher:

- `/quality/audits/checklists`;
- `/quality/audits/reports`.

They are intentionally retained because they still provide collection/register context underneath specialist checklist/report governance. Removing them would remove working functionality and violate the MD instruction not to delete a working system merely to clean up generic surfaces. Specialist audit-record workflows remain authoritative for revision/approval/issue operations.

## 7. Database and migration state

The expected single Quality migration head is:

```text
quality_260809_checklist_exec
```

New Quality-owned governance tables are registered in shared SQLAlchemy metadata and are covered by the dedicated completion contract. PostgreSQL probes exercise tenant isolation and append-only/immutability rules for the applicable domains.

## 8. CI / release rule

No historical green SHA validates a newer head.

PR #488 may be considered materially complete only when the exact current head has no required red/cancelled impacted checks and the relevant checks are green, including:

- Quality Module CI;
- QMS Assurance OS Completion CI;
- Audit lifecycle Playwright;
- QMS Planner CI when triggered;
- impacted Document Control Governance CI;
- relevant PostgreSQL/RLS probes;
- other repository checks triggered by the final head.

Until that exact-head condition is met, the PR remains draft. This document records the as-built scope; GitHub Actions remains the source of truth for the final validation state.
