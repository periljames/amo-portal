# QMS Live Audit Implementation Baseline

Date: 2026-08-16  
Branch: `agent/qms-live-audit-operating-workspace`  
Acceptance contract: uploaded QMS Frontend Deep Research and Fullstack Execution Specification.

## Baseline

Current `main` already owns the governed QMS business state. This implementation must orchestrate it rather than create a second audit engine.

| Capability | Authoritative current owner | Live-audit treatment |
|---|---|---|
| Audit workflow | `audit_workflow_contract.py` | Reuse seven-stage backend workflow; do not infer completion from navigation. |
| Programme / schedule | Audit Programme + Planner routers | Keep portfolio/scheduling routes; occurrence UI starts after an audit exists. |
| Preparation | `audit_preparation_router.py` and preparation models | Require an ISSUED preparation snapshot before the new Prepare stage is complete. |
| Checklist execution | existing checklist execution/governance handlers | Reuse canonical responses and evidence; later Live page will compress interaction only. |
| Findings | existing audit finding handlers | Reuse exact finding records and finding→CAR lineage. |
| Report governance | existing report revision lifecycle | Preserve `DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED`; later generate DRAFT from audit snapshot. |
| Execution close / follow-up | `audit_closure_router.py` | Preserve separate `AUDIT EXECUTION CLOSED` and `ASSURANCE FOLLOW-UP COMPLETE`. |
| CAR/CAPA | merged governed control loop (#499) | Keep milestones, deadline decisions, dependencies, escalation, effectiveness and close authority. |
| Archive | `QualityArchivePackage` + Evidence Vault | Treat archive as the final occurrence stage; later add manifest/retention orchestration. |
| Controlled documents | Document Control / DMS | Store governed references/snapshots only where the audit contract requires them. |

## First implementation slice

This branch introduces a read-only audit-session projection:

`SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE`

The projection is built from existing authoritative records:

- Setup: authoritative `war-room` stage.
- Prepare: issued preparation revision + authoritative checklist readiness.
- Live: authoritative fieldwork/findings completion.
- Closing: `QualityAuditClosureState.execution_status == CLOSED`.
- Follow-up: `QualityAuditClosureState.follow_up_status == COMPLETE`.
- Archive: at least one controlled `QualityArchivePackage`.

New API:

`GET /api/maintenance/{amo_code}/quality/audits/{audit_id}/session`

Legacy `/qms` alias receives the same route through canonical router composition.

## Frontend compatibility strategy

The existing occurrence wildcard remains in place, so no working register/detail route is removed. New deep links are additive:

- `/quality/audits/:auditRef/setup?tab=war-room`
- `/quality/audits/:auditRef/prepare?tab=checklist`
- `/quality/audits/:auditRef/live?tab=checklist`
- `/quality/audits/:auditRef/closing?tab=report`
- `/quality/audits/:auditRef/follow-up?tab=cars`
- `/quality/audits/:auditRef/archive?tab=evidence`

The query parameter keeps the existing Run Hub functional while the time-oriented IA is introduced incrementally.

## Verified remaining implementation gaps

The following are not claimed complete by this slice:

1. dedicated Live Audit fieldwork page;
2. backend-filtered auditee released-only live view;
3. first-class external auditor identity/invitation;
4. offline IndexedDB mutation outbox and idempotent replay;
5. QMS realtime event stream / presence;
6. auditee pre-audit document room;
7. automatic report composition from frozen audit state;
8. current-main e-signature integration salvaged from PR #280;
9. policy-driven approval/certificate artifact;
10. immutable archive manifest, retention, hold and disposition workflow.

These remain the next implementation slices and must not be represented as complete until database/API/browser acceptance proves them.
