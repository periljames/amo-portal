# QMS Audit Lifecycle Acceptance Trace — 2026-08-09

## Purpose

This document maps the original QMS implementation MD's mandatory Playwright scenarios to deterministic browser evidence in PR #488. It is a requirement-to-test trace, not a substitute for exact-head GitHub Actions results.

All listed browser files are executed by `.github/workflows/qms-audit-lifecycle-ci.yml` under the independently named `Audit lifecycle Playwright — governed acceptance` job. The workflow uses deterministic route fixtures and readiness assertions; it does not use arbitrary sleeps for application state.

## Original 18-scenario contract

| # | Original MD scenario | Deterministic browser evidence | Contract proved |
|---|---|---|---|
| 1 | Open Audit Programme | `frontend/tests/e2e/qms-audit-programme.spec.ts` | Opens `/quality/audits/program`, renders the governed programme, Audit Universe source lineage, and scheduling queue. |
| 2 | Create programme audit | `frontend/tests/e2e/qms-audit-programme.spec.ts` | Creates a governed draft programme revision and proves review transition remains reason-gated. |
| 3 | Schedule audit | `frontend/tests/e2e/qms-audit-programme.spec.ts` | Schedules a programme requirement through the authoritative Quality Planner and verifies schedule lineage is committed only after the scheduling contract succeeds. |
| 4 | Create via quick planner handoff | `frontend/tests/e2e/qms-planner-audit-handoff.spec.ts` | Uses the Planner quick audit handoff and verifies the authoritative audit/schedule request rather than a local-only calendar event. |
| 5 | Detect scheduling conflict | `frontend/tests/e2e/qms-audit-programme.spec.ts`; `frontend/tests/e2e/qms-planner-lifecycle.spec.ts` | Receives deterministic conflict evidence, blocks the unapproved write, and proves controlled override behavior rather than silent collision. |
| 6 | Change auditor | `frontend/tests/e2e/qms-audit-lifecycle-traceability.spec.ts` | Opens schedule detail, edits the team, selects a different lead auditor, persists `lead_auditor_user_id`, and confirms the retained authoritative participant selection. |
| 7 | Controlled reschedule | `frontend/tests/e2e/qms-modern-planner-live.spec.ts`; `frontend/tests/e2e/qms-planner-lifecycle.spec.ts` | Reschedules through the authoritative mutation with expected old date/version context and reason/controlled lifecycle behavior. |
| 8 | Generate notice | `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Exercises notice governance through `DRAFT → UNDER_REVIEW → APPROVED → GENERATED → DELIVERED → ACKNOWLEDGED`. |
| 9 | Open audit preparation | `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Creates and issues a governed preparation revision and verifies the issued immutable state is returned after mutation. |
| 10 | Execute checklist | `frontend/tests/e2e/qms-checklist-execution-governance.spec.ts` | Records canonical `NONCOMPLIANT`, auditor notes, structured evidence references and reason while proving legacy `NON_CONFORMING` compatibility. |
| 11 | Create finding | `frontend/tests/e2e/qms-audit-lifecycle-traceability.spec.ts` | Uses the Run Hub finding form and verifies structured classification, requirement, statement and objective-evidence payload. |
| 12 | Progress to report | `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Exercises governed report lifecycle `DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED` with revision state retained. |
| 13 | Create/associate CAR | `frontend/tests/e2e/qms-audit-lifecycle-traceability.spec.ts` | Creates the CAR from the persisted audit finding, verifies the CAR payload contains the exact `finding_id`, and confirms the register returns the linked CAR. |
| 14 | Close execution | `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Performs explicit audit execution closure through the governed closure state rather than treating answered checklist rows as closeout. |
| 15 | Retain follow-up obligation | `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Proves execution can close while CAR/effectiveness obligations remain and `ASSURANCE FOLLOW-UP COMPLETE` remains independently governed. |
| 16 | Keyboard planner use | `frontend/tests/e2e/qms-modern-planner-live.spec.ts`; `frontend/tests/e2e/qms-usability-enhancements.spec.ts` | Exercises keyboard planner navigation/movement and focus-safe controls. |
| 17 | Mobile/tablet usability | `frontend/tests/e2e/qms-usability-enhancements.spec.ts`; `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Exercises constrained viewport behavior with no document overflow and usable governed audit/closeout controls. |
| 18 | Refresh/deep-link persistence | `frontend/tests/e2e/qms-usability-enhancements.spec.ts`; `frontend/tests/e2e/qms-audit-governed-lifecycle.spec.ts` | Loads/deep-links directly into governed Quality routes, refreshes, and verifies route/tab context remains recoverable from authoritative state. |

## Checklist response compatibility proof

The original MD requires at minimum:

- `COMPLIANT`
- `NONCOMPLIANT`
- `OBSERVATION`
- `NOT_APPLICABLE`
- `NOT_VERIFIED`

The existing authoritative checklist row historically stores `NON_CONFORMING` and `PENDING`. The governance layer intentionally preserves historical compatibility:

- `NONCOMPLIANT → NON_CONFORMING`
- `NOT_VERIFIED → PENDING`

The canonical response, auditor notes, structured evidence references and append-only change events are retained separately against the same authoritative checklist item. This avoids a destructive historical rename and avoids a second checklist execution engine.

## Risk-planning acceptance linkage

Browser lifecycle evidence is complemented by `backend/amodb/apps/quality/tests/test_audit_risk_planning_factor_contract.py`, which proves deterministic source attribution for:

- time since last attributable audit;
- historical audit finding exposure;
- repeat requirement findings across distinct attributable audits;
- governed `INEFFECTIVE` corrective-action effectiveness conclusions;
- new capability additions/changes from governed Mission types;
- aircraft-type exposure only from explicit Mission scope keys;
- only explicit `safety / SAFETY_OCCURRENCE` source references for Safety occurrences;
- exact source-id targeting when Safety, effectiveness, capability or aircraft-type evidence explicitly identifies an Audit Universe source;
- factor explainability fields including source-record reference, source/observation date and rationale.

Negative-contract assertions prove that:

- generic risk records are not relabelled as Safety occurrences;
- free-text Mission titles are not parsed as aircraft-type evidence.

Mandatory surveillance remains a hard requirement outside the factor-weight total and cannot be averaged away.

## Acceptance rule

This matrix is complete only when the exact PR head carrying these files has green results for the dedicated lifecycle workflow and all other impacted Quality checks. A prior green SHA does not validate a newer head.
