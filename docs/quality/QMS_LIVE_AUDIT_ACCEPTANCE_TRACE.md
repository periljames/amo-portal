# QMS Live Audit Acceptance Trace

**Status legend:**

- `IMPLEMENTED` — material code exists on this branch; exact-head CI still determines release readiness.
- `PARTIAL` — material slice exists but requirement is not end-to-end complete.
- `PENDING` — not implemented on this branch.

| # | Requirement | Status | Primary frontend owner | Primary backend owner | Database / governance | Automated proof |
|---|---|---|---|---|---|---|
| 1 | Programme occurrence becomes an audit | Existing main | Existing Planner/Audit Programme | Existing #488 programme/planner | Existing | Existing lifecycle suite |
| 2 | Audit scheduled | Existing main | Existing Planner | Existing scheduling router | Existing | Existing lifecycle suite |
| 3 | Internal lead auditor assigned | Existing main | Existing schedule/setup | Existing planner/audit API | Existing | Existing lifecycle suite |
| 4 | External auditor invitation | PARTIAL | `AuditPrepareWorkspace.tsx` | `audit_external_access_router.py` | external identity/participant/grant | token/scope contract; browser pending |
| 5 | Conflict/independence blocks invalid assignment | Existing main | Existing planner/people | Existing #488 controls | Existing | Existing lifecycle suite |
| 6 | Notice issued/acknowledged | Existing main | Existing notice governance | Existing notice router | Existing | Existing lifecycle suite |
| 7 | Auditee receives document requests | IMPLEMENTED | `PublicAuditAccessPage.tsx` | external read model | existing requests + grant | browser pending |
| 8 | Auditee submits documents | IMPLEMENTED | `GuestDocumentSubmit.tsx` | `audit_guest_documents_router.py` | document submissions | storage unit + PG probe; browser pending |
| 9 | Auditor accepts/returns submission | IMPLEMENTED | `AuditPrepareWorkspace.tsx` | existing request update API | existing request events | browser pending |
| 10 | Exact checklist revision bound | Existing main | existing checklist template governance | existing #488 | existing | existing lifecycle suite |
| 11 | Opening meeting recorded | Existing main | existing Run Hub/governance | existing preparation/audit | existing | existing lifecycle suite |
| 12 | Auditor starts live fieldwork | PARTIAL | `LiveAuditWorkspace.tsx` | existing audit engine | existing | browser pending |
| 13 | Checklist response persists | IMPLEMENTED | `LiveAuditWorkspace.tsx` | governed checklist execution API | existing | existing + new frontend build |
| 14 | Second internal browser sees realtime update | PENDING | reuse global realtime provider | QMS publisher integration pending | event/outbox pending | pending |
| 15 | Auditee sees only released data | IMPLEMENTED | `PublicAuditAccessPage.tsx` | released-data projection | release events/grants | token tests; browser pending |
| 16 | Draft finding invisible to auditee | IMPLEMENTED | release panel/public page | released-data projection | release events | browser pending |
| 17 | Released finding becomes visible | IMPLEMENTED | `LiveFindingReleasePanel.tsx` | finding release endpoint | append-only release events | browser pending |
| 18 | Evidence links correctly | PARTIAL | live/release controls | existing checklist evidence + release refs | existing/new release history | pending browser |
| 19 | Browser offline | PENDING | existing platform offline infra to reuse | idempotent QMS commands pending | mutation ledger pending | pending |
| 20 | Checklist mutations queue | PENDING | existing offline mutation manager | QMS mutation contract pending | pending | pending |
| 21 | Reconnect | PENDING | existing offline/realtime | pending | pending | pending |
| 22 | Replay exactly once | PENDING | existing offline manager | idempotency pending | pending | pending |
| 23 | Stale conflict visible | PENDING | conflict UX pending | version conflict API pending | pending | pending |
| 24 | Fieldwork completion freezes closing source state | PARTIAL | `AuditClosingWorkspace.tsx` | report composition | report artifact | helper tests; browser pending |
| 25 | Report generated without manual upload | IMPLEMENTED | `AuditClosingWorkspace.tsx` | `audit_report_composition.py` | report artifacts | composition tests + PG probe |
| 26 | Report reflects checklist/findings | IMPLEMENTED | Closing metrics/download | canonical report snapshot | snapshot hash/artifact hash | composition tests |
| 27 | Auditee closing acknowledgement | PARTIAL | finding acknowledgement implemented | guest acknowledgement endpoint | access events + finding ack | closing acknowledgement pending |
| 28 | Quality Manager approves report | Existing report engine / not yet linked to generated artifact | existing report closeout UI | existing report governance | existing | generated-artifact adoption pending |
| 29 | Electronic signing | PENDING | pending | selective #280 port pending | pending | pending |
| 30 | Issued report immutable | Existing main | existing report governance | existing report governance | existing | existing tests |
| 31 | Certificate/approval only when policy enabled | PENDING | pending | pending policy engine | pending | pending |
| 32 | CAR shared | Existing main/#499 | existing CAR workspace | existing CAR invite/control | existing | existing CAR CI |
| 33 | Auditee submits RCA/CAP | Existing main/#499 | CAR invite/control | existing CAR services | existing | existing CAR CI |
| 34 | Quality return/reject/accept | Existing main/#499 | existing CAR control | existing CAR services | existing | existing CAR CI |
| 35 | Reminder/escalation fires | Existing main/#499 | existing CAR UI | reminder/escalation service | existing | existing CAR CI |
| 36 | Extension requires risk assessment | Existing main/#499, UX expansion pending | existing control loop | existing deadline change control | existing | existing CAR CI |
| 37 | QM/Accountable Executive policy escalation | Existing main/#499, policy visibility pending | existing control loop | escalation service | existing | existing CAR CI |
| 38 | Execution closes while CAR remains open | Existing main/#488 | existing closeout | existing closeout | existing | existing lifecycle CI |
| 39 | Effectiveness later | Existing main/#488/#499 | existing effectiveness UI | existing effectiveness services | existing | existing CI |
| 40 | Follow-up completes only after gates | Existing main/#488 | existing closeout | closure state service | existing | existing lifecycle CI |
| 41 | Archive manifest includes governed refs/hashes | PENDING | Archive workspace pending | archive package pending | retention/manifest pending | pending |
| 42 | Cross-tenant guest/direct-object access fails | PARTIAL | n/a | grant/RLS design | new RLS tables | PG RLS probe; full IDOR test pending |
| 43 | Deep-link refresh retains authoritative state | PARTIAL | stage route compatibility | session projection | n/a | route unit; browser pending |
| 44 | Keyboard navigation | PARTIAL | semantic controls added | n/a | n/a | dedicated browser accessibility pending |
| 45 | Tablet/mobile viewport | PARTIAL | responsive Prepare/Live/Public/Closing CSS | n/a | n/a | dedicated browser viewport pending |

## Additional implementation mapping

### Session projection

- Frontend: `AuditLifecycleRail.tsx`, `auditSessionRoutes.ts`
- Backend: `audit_session_router.py`
- Test: `test_audit_session_projection.py`

### External access

- Frontend: `AuditPrepareWorkspace.tsx`, `PublicAuditAccessPage.tsx`
- Backend: `audit_external_access_router.py`
- DB: `quality_260816_external_access.py`
- Tests: `test_audit_external_access_contract.py`, PostgreSQL probe

### Guest documents

- Frontend: `GuestDocumentSubmit.tsx`, `AuditDocumentSubmissionReviewPanel.tsx`
- Backend: `audit_guest_documents_router.py`, `audit_guest_document_storage.py`
- DB: `quality_260816_guest_documents.py`
- Tests: `test_audit_guest_document_storage_contract.py`, PostgreSQL probe

### Generated closing report

- Frontend: `AuditClosingWorkspace.tsx`
- Backend: `audit_report_composition.py`, `audit_report_composition_router.py`
- DB: `quality_260816_report_composition.py`
- Tests: `test_audit_report_composition_contract.py`, PostgreSQL probe

## Release rule

No `IMPLEMENTED` line in this document means production-ready by itself. Exact-head CI, migration topology, tenant isolation, browser acceptance and mandatory review status remain authoritative for merge readiness.
