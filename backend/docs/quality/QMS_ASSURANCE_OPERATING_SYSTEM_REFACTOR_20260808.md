# QMS Assurance Operating System — As-Built Architecture

**Architecture date:** 2026-08-09  
**Pull request:** #488  
**Branch:** `agent/qms-assurance-operating-system-refactor`  
**Status:** implementation materially complete; exact-head validation controls release state.

## 1. Product model

Quality is an aviation **Assurance Operating System**, not a collection of disconnected registers.

Permanent top-level workspaces:

```text
CONTROL ROOM | PLANNER | MISSIONS | PEOPLE | ASSURANCE | INTELLIGENCE
```

Quality answers:

1. What requires assurance action?
2. Why?
3. By when?
4. Which approval, capability, control or commitment is exposed?
5. Which authoritative records support the conclusion?
6. Which human decision or next action is required?
7. Did the corrective action work?

## 2. Source ownership boundary

Quality does not duplicate operational master data merely because it audits that data.

| Domain | Authoritative owner | Quality use |
|---|---|---|
| Audit programme, audits, findings, CAR, effectiveness | Quality | governed assurance lifecycle |
| Training / competence | Training | eligibility and audit evidence by reference |
| Roster / leave / workforce | Workforce / Rostering | availability and conflict evidence |
| Tooling / calibration | Tooling / Workshops | calibration and equipment exposure |
| Suppliers / procurement | Procurement / Stores | supplier surveillance evidence |
| Manuals / procedures | DMS / Document Control | controlled source references |
| Work orders / defects / workpacks | Maintenance | sampling and assurance evidence |
| Aircraft / technical records | Fleet / Technical Records | aircraft/capability surveillance context |
| Reliability | Reliability | technical recurrence/trend context |
| Safety occurrences | Safety / SMS | explicitly linked safety-assurance context only |

Audit Universe records use typed source pointers (`source_owner_module`, `source_type`, `source_id`, `source_route`) instead of copied master records.

## 3. Governing Audit Operations lifecycle

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

These are governed transitions and evidence gates, not decorative tabs.

## 4. Audit Programme and Audit Universe

The programme domain supports controlled revisions and state transitions including draft, review, approval, activation, supersession and closure. Approved history is not silently rewritten.

Audit Universe provides a governed catalogue of auditable entities with authoritative-source identity, surveillance interval, risk classification, regulatory criticality and mandatory-surveillance state.

Programme items link to exact universe items and preserve schedule/Planner lineage. Custom and risk-triggered occurrences create discrete governed schedule records without rewriting completed historical audits.

## 5. Risk-based audit planning

The risk-planning endpoint is deterministic and explainable. Mandatory surveillance is a hard obligation.

### First-class planning factors

The engine consumes attributable evidence for:

- regulatory surveillance frequency;
- time since last attributable audit;
- historical findings;
- repeat requirement findings across distinct audits;
- overdue CAR exposure;
- ineffective corrective actions from governed effectiveness conclusions;
- organizational/process changes;
- new capability additions/changes from governed Missions;
- new aircraft types only when explicitly present in governed Mission scope;
- supplier performance/approval exposure;
- Reliability events, recurrence and recommendations;
- tooling/calibration and out-of-tolerance exposure;
- training/competence exposure;
- Safety occurrences only through explicit Safety-owned occurrence references;
- management-review actions;
- previous Audit Universe risk;
- regulator findings and external commitments;
- deferral pressure.

Each calculated factor exposes:

- factor code/rule;
- value;
- source category;
- source-record reference;
- source date or observation date where available;
- rationale;
- deterministic planning weight where a special weight is used.

The output is an ordering aid. It is not an AI probability, compliance score or automatic audit conclusion.

### Safety boundary

A Safety occurrence is accepted only when the source reference explicitly identifies:

```text
source_owner_module = safety
source_type = SAFETY_OCCURRENCE
```

A generic Quality/risk record is never renamed as a Safety occurrence. Exact Audit Universe targeting additionally requires an explicit `audit_universe_source_id`.

### Aircraft-type boundary

Aircraft type is not inferred from Mission title or description. It is recognized only through explicit governed Mission scope keys:

```text
aircraft_type
aircraft_types
aircraft_type_id
aircraft_type_ids
```

This prevents free-text inference from becoming an authoritative planning signal.

## 6. Planner

Planner supports the required planning horizons and perspectives:

- Year;
- Quarter;
- Month;
- Week;
- Agenda/List;
- auditor workload;
- department coverage;
- facility/station coverage;
- supplier surveillance;
- regulatory commitments;
- overdue/deferred exposure.

Operational interactions include quick-create, detailed scheduling, search/filtering, controlled drag/keyboard rescheduling, conflict handling and authoritative Planner → Audit handoff.

Approved schedule changes retain reason, actor, timestamp and before/after lineage rather than silently overwriting the plan.

## 7. Scheduling conflicts, competence and independence

Conflict evaluation is deterministic and differentiates blockers from warnings. Supported evidence includes scheduling overlap, assignment conflicts, missing scheduling essentials, programme constraints, notice timing, availability/competence where source data is available, and independence declarations.

People & Privileges owns governed Quality privilege/eligibility decisions. Training remains the authoritative competence-record source. Independence declarations are attributable decisions rather than inferred labels.

## 8. Audit notices

Audit notices are governed objects with tenant policy and revision history.

Lifecycle:

```text
DRAFT → UNDER_REVIEW → APPROVED → GENERATED → DELIVERED → ACKNOWLEDGED
```

Policies control notice period, review requirement, acknowledgement requirement and permitted emergency/unannounced exceptions. Revisions and transitions retain actors, reasons and immutable event history.

## 9. Audit preparation

Preparation revisions snapshot the operational preparation state, including scope/criteria, dates/personnel, checklist rows, document requests and source references. A source fingerprint detects the exact issued preparation state.

Issued preparation revisions are immutable. The frontend exposes preparation intelligence and revision issue/history inside the live audit workflow.

## 10. Checklist template and execution governance

### Reusable templates

Issued checklist template revisions retain:

- template identity and revision;
- section/category;
- checklist/requirement references;
- regulatory/manual sources;
- prompt/question;
- expected evidence;
- response type;
- applicability;
- mandatory/optional semantics;
- finding-trigger policy;
- ordering.

An audit binding retains the exact issued revision executed.

### Execution

Canonical response vocabulary:

```text
COMPLIANT
NONCOMPLIANT
OBSERVATION
NOT_APPLICABLE
NOT_VERIFIED
```

Historical compatibility remains:

```text
NONCOMPLIANT → NON_CONFORMING
NOT_VERIFIED → PENDING
```

The original checklist row remains authoritative for existing workflow gates. A one-to-one governance record stores the canonical response, auditor notes, structured evidence references and append-only execution events. This avoids destructive historical migration and avoids creating a parallel execution engine.

## 11. Findings and CAR handoff

Findings are structured records carrying classification, requirement/reference, statement, objective evidence, audit identity and governed relationship to CARs.

CAR issuance from the audit uses the persisted finding ID. CAR lifecycle remains its own governed process; audit execution closure does not erase unresolved CAR/effectiveness obligations.

## 12. Audit reports

Governed report revisions support:

```text
DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED → SUPERSEDED
```

Revision identity, file hash/snapshot, review/approval/issue actors and event history protect issued reports from destructive overwrite.

## 13. Closeout and follow-up

The architecture explicitly separates:

```text
AUDIT EXECUTION CLOSED
```

from:

```text
ASSURANCE FOLLOW-UP COMPLETE
```

The two states can occur on different dates. Open CAR/effectiveness obligations remain visible after execution closure.

Effectiveness plans support expected outcome, measure, method, reviewer, observation period, review date, indicators and conclusion:

```text
EFFECTIVE | PARTIALLY_EFFECTIVE | INEFFECTIVE | INCONCLUSIVE
```

Governed downstream responses support additional action, follow-up audit, CAR reopening, management escalation and risk reassessment.

## 14. Deferrals and recurrence

Deferrals are governed requests/decisions rather than an alias for dragging an event. They retain original/revised dates, reason/risk rationale, actor and decision/apply history.

Programme recurrence supports standard cadence plus controlled custom and risk-triggered occurrences. Historical completed audits remain discrete records and are not rewritten when future recurrence changes.

## 15. Missions and Intelligence audit handoffs

Missions can generate authoritative Audit scheduling handoffs for readiness/facility/competence/post-implementation surveillance without creating a second audit system.

Intelligence signals can generate the same kind of handoff while preserving signal source lineage.

Schedule/source-link records preserve the originating governed source rather than flattening the action into an untraceable calendar item.

## 16. Frontend ownership

The global Quality enhancement host mounts specialist governed controls for:

- strategic Planner views;
- custom/risk-triggered occurrences;
- Mission/Intelligence audit handoffs;
- checklist template revisions;
- checklist execution governance;
- preparation intelligence;
- notice governance;
- report/closeout governance;
- effectiveness-response actions.

Collection-route names are excluded from audit-record detection, preventing paths such as `program`, `schedule`, `register`, `checklists` or `reports` from being treated as audit IDs.

### Compatibility collection routes

The cleanup audit intentionally retains two bounded collection routes under the canonical dispatcher:

```text
/quality/audits/checklists
/quality/audits/reports
```

They still provide collection/register context beneath specialist governance. Removing them would delete working functionality. Specialist record-level workflows own revision/approval/issue behavior.

This is intentional compatibility ownership, not an unfinished duplicate audit engine.

## 17. Database and isolation

Expected single Quality Alembic head:

```text
quality_260809_checklist_exec
```

New Quality-owned governance domains use tenant-scoped keys and PostgreSQL row-level security where required. Dedicated probes exercise:

- cross-tenant denial;
- RLS/force-RLS state;
- append-only or immutable event histories;
- custom/risk-triggered occurrence lineage;
- checklist execution governance;
- completed Assurance OS governance domains.

## 18. Browser acceptance

The mandatory 18-scenario requirement is mapped one-to-one in:

```text
backend/docs/quality/QMS_AUDIT_ACCEPTANCE_TRACE_20260809.md
```

Dedicated workflow:

```text
.github/workflows/qms-audit-lifecycle-ci.yml
```

The suite includes explicit assertions for programme, schedule, quick handoff, conflicts, auditor reassignment, rescheduling, notices, preparation, checklist execution, finding creation, report lifecycle, CAR linkage, execution closure, retained follow-up, keyboard use, constrained viewports and refresh/deep-link persistence.

## 19. Release policy

Architecture completion and CI completion are separate claims.

The code may be described as materially implementing the original MD only after the exact current PR head proves the relevant contracts. A historical green commit does not validate a newer commit.

PR #488 remains draft until the exact final head has no required red/cancelled impacted checks and the relevant Quality, lifecycle, Planner, PostgreSQL/RLS and impacted cross-module workflows are green.
