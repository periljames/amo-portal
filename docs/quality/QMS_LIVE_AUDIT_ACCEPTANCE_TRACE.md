# QMS Live Audit Acceptance Trace

This matrix tracks the uploaded Live Audit execution specification against the current PR #502 branch. The branch extends the governed QMS Assurance OS and CAR control loop; it does not create a parallel audit, finding, CAR/CAPA or closeout state machine.

**Status legend**

- `EXISTING` — authoritative capability already exists in the merged QMS baseline and is reused.
- `IMPLEMENTED` — the required material code exists on this branch. Release readiness still depends on exact-head CI and the proof notes below.
- `PARTIAL` — a governed slice exists, but an acceptance or scope gap remains.
- `PENDING` — not implemented.

| # | Requirement | Status | Implemented / authoritative path | Proof / remaining qualification |
|---|---|---|---|---|
| 1 | Programme occurrence becomes an audit | EXISTING | Existing Audit Programme / Planner | Existing lifecycle contract |
| 2 | Audit scheduled | EXISTING | Existing scheduling workflow | Existing lifecycle contract |
| 3 | Internal lead auditor assigned | EXISTING | Existing audit setup / People controls | Existing lifecycle contract |
| 4 | External auditor invitation | IMPLEMENTED | `AuditPrepareWorkspace.tsx`, external participant/grant model | Token/scope/CSRF contracts and external browser acceptance; EMAIL_LINK is supported, MFA/PASSKEY labels fail closed until a real ceremony exists |
| 5 | Conflict/independence blocks invalid assignment | EXISTING | Existing auditor eligibility / planning governance | Existing Assurance OS contract |
| 6 | Notice issued / acknowledged | EXISTING | Existing notice governance | Existing lifecycle contract |
| 7 | Auditee receives document requests | IMPLEMENTED | `PublicAuditAccessPage.tsx`, scoped external read model | Chromium public-access acceptance |
| 8 | Auditee submits documents | IMPLEMENTED | `GuestDocumentSubmit.tsx`, `audit_guest_documents_router.py` | Storage contract, PostgreSQL probe and Chromium upload acceptance |
| 9 | Auditor accepts / returns submission | IMPLEMENTED | `AuditDocumentSubmissionReviewPanel.tsx`, governed request update workflow | Exact-head frontend/backend contract coverage |
| 10 | Exact checklist revision bound | EXISTING | Existing checklist-template/revision governance | Existing lifecycle contract |
| 11 | Opening meeting recorded | EXISTING | Existing Run Hub / preparation governance | Existing lifecycle contract |
| 12 | Auditor starts live fieldwork | IMPLEMENTED | `LiveAuditWorkspace.tsx`, six-stage audit-session projection | Production build and lifecycle contracts |
| 13 | Checklist response persists | IMPLEMENTED | Governed checklist execution API | Idempotent fieldwork contract + browser acceptance |
| 14 | Second internal browser sees realtime update | PARTIAL | QMS audit events publish after commit; audit occurrence subscribes through `qmsAuditRealtime.ts` | Reconnect/tenant replay contract passes; a dedicated two-browser E2E remains desirable |
| 15 | Auditee sees only released data | IMPLEMENTED | Server-filtered external read model | Token/scope contract + Chromium released-only acceptance |
| 16 | Draft finding invisible to auditee | IMPLEMENTED | Explicit release boundary; external page receives no private/draft state | Chromium acceptance |
| 17 | Released finding becomes visible | IMPLEMENTED | `LiveFindingReleasePanel.tsx`, append-only release events | Browser and backend contracts |
| 18 | Evidence links correctly | PARTIAL | Checklist evidence references and released evidence references are governed separately | Data contract exists; dedicated end-to-end evidence-link/opening proof remains desirable |
| 19 | Browser offline | IMPLEMENTED | Internal Live Audit reuses encrypted portal offline persistence | Internal employee Live scope only; external guest-cookie offline replay remains deliberately excluded |
| 20 | Checklist mutations queue | IMPLEMENTED | Encrypted mutation outbox + QMS idempotency metadata | Internal Live scope only |
| 21 | Reconnect | IMPLEMENTED | Online replay + QMS realtime reconnect | Realtime reconnect/tenant replay contract passes |
| 22 | Replay exactly once | IMPLEMENTED | Client mutation ID, device sequence and server idempotent receipts | `test_audit_fieldwork_sync_contract.py` |
| 23 | Stale conflict visible | IMPLEMENTED | Base-version conflict rejection and conflict-aware replay path | No silent last-write-wins; internal Live scope |
| 24 | Fieldwork completion freezes closing source state | IMPLEMENTED | Deterministic report snapshot / governed closing composition | Closing/report composition contracts preserve source hashes |
| 25 | Report generated without manual upload | IMPLEMENTED | `AuditClosingWorkspace.tsx`, `audit_report_composition.py` | Deterministic composition contract + PostgreSQL probe |
| 26 | Report reflects checklist / findings | IMPLEMENTED | Canonical report snapshot from governed audit state | Snapshot/artifact hash contracts |
| 27 | Auditee closing acknowledgement | IMPLEMENTED | Issued-report status/download/acknowledgement in secure auditee workspace | Exact issued revision + SHA-256 bound to append-only participant access event; Chromium acceptance |
| 28 | Quality Manager approves report | IMPLEMENTED | Governed issued-report closing assurance workflow | Closing-assurance contracts; authorization remains capability-gated |
| 29 | Electronic signing | IMPLEMENTED | `PASSWORD_REAUTH` signature evidence over exact issued report hash with HMAC digest | Rate-limit policy + signature evidence contract. **This is not WebAuthn/passkey signing.** |
| 30 | Issued report immutable | EXISTING / STRENGTHENED | Existing report revision governance + checksum verification before signing/download | Existing report tests plus closing/report contracts |
| 31 | Certificate / approval only when policy enabled | IMPLEMENTED | Versioned output policy: `NONE`, `REPORT_ONLY`, `APPROVAL_LETTER`, `CERTIFICATE`, `ATTESTATION` | Closing-assurance policy/artifact contracts |
| 32 | CAR shared | EXISTING | Governed CAR invite/control loop from #499 | CAR CI |
| 33 | Auditee submits RCA / CAP | EXISTING | CAR external response workflow | CAR CI |
| 34 | Quality return / reject / accept | EXISTING | CAR control loop | CAR CI |
| 35 | Reminder / escalation fires | EXISTING | CAR reminder/escalation service | CAR CI |
| 36 | Extension requires risk assessment | EXISTING | Controlled CAR deadline change workflow | CAR governance tests |
| 37 | QM / Accountable Executive policy escalation | EXISTING | CAR escalation workflow | CAR governance tests |
| 38 | Execution closes while CAR remains open | EXISTING | Audit execution closeout separated from CAR lifecycle | Existing lifecycle contract |
| 39 | Effectiveness later | EXISTING | CAR/effectiveness workflow | Existing CAR / Assurance OS tests |
| 40 | Follow-up completes only after gates | EXISTING | Governed closeout gates | Existing lifecycle contract |
| 41 | Archive manifest includes governed refs / hashes | IMPLEMENTED | Versioned archive manifest + items + package checksum + retention policy + legal hold + disposition events | Closing/archive governance contracts and PostgreSQL all-head probe |
| 42 | Cross-tenant guest / direct-object access fails | PARTIAL | Tenant RLS/FORCE RLS, scoped grant/session and server-side audit binding | PostgreSQL RLS probe passes; dedicated adversarial IDOR browser/API suite remains desirable |
| 43 | Deep-link refresh retains authoritative state | IMPLEMENTED | Session projection + SPA navigation bypass for signed `/qms/audit-access/*` and `/qms/car-access/*` paths | Route unit tests + production-preview Chromium acceptance |
| 44 | Keyboard navigation | IMPLEMENTED | Semantic controls and dedicated public accessibility spec | Chromium accessibility acceptance |
| 45 | Tablet / mobile viewport | IMPLEMENTED | Responsive Prepare/Live/Public/Closing surfaces | Dedicated Chromium mobile/tablet acceptance |

## Implementation map

### Audit occurrence and fieldwork

- Frontend: `AuditLifecycleRail.tsx`, `LiveAuditWorkspace.tsx`, `auditSessionRoutes.ts`
- Backend: `audit_session_router.py`, checklist execution/fieldwork sync contracts
- Realtime: `qmsAuditRealtime.ts`, committed Quality audit events
- Offline: encrypted employee mutation outbox with idempotent QMS receipts

### External audit access

- Frontend: `AuditPrepareWorkspace.tsx`, `PublicAuditAccessPage.tsx`, `ExternalAuditorFieldworkWorkspace.tsx`
- Backend: external participant/grant/session/fieldwork routers
- Governance: tenant RLS/FORCE RLS, scoped permissions, CSRF-bound external writes
- External finding drafts: immutable draft lifecycle plus internal Quality review/promotion into the canonical official finding workflow

### Guest documents and released data

- Frontend: `GuestDocumentSubmit.tsx`, `AuditDocumentSubmissionReviewPanel.tsx`
- Backend: guest document storage/review and explicit finding release projection
- Rule: private auditor notes and draft findings are not sent to the auditee read model

### Closing assurance

- Deterministic report composition from canonical audit state
- Governed report approval/issuance retained as the authoritative report lifecycle
- Electronic signature evidence uses configured **password re-authentication**, exact report SHA-256, nonce, signer identity, reason, timestamp and HMAC digest
- Versioned output policy controls whether an approval letter, certificate or attestation may be generated
- Auditee may download and acknowledge only the latest formally `ISSUED` report; acknowledgement is idempotent and bound to its exact revision/hash

### Archive governance

- Versioned retention policy
- Immutable manifest inventory with authoritative IDs/revisions/content hashes
- Controlled package checksum
- Legal-hold events
- Governed disposition approval/rejection/execution history

## Explicit non-claims / remaining hardening

1. External-auditor guest sessions do **not** reuse the employee bearer-token offline outbox. A guest-specific encrypted replay design would need fresh CSRF/session validation without persisting guest secrets.
2. `PASSWORD_REAUTH` signing is implemented; WebAuthn/passkey signing is **not** implemented and must not be represented as such.
3. Cross-tenant RLS is proven, but a dedicated adversarial direct-object/IDOR suite would strengthen acceptance row 42.
4. Realtime backend/frontend contracts are green; a dedicated simultaneous two-internal-browser E2E would strengthen row 14.
5. Dedicated evidence-link opening/download E2E would strengthen row 18.

## Release rule

No `IMPLEMENTED` row alone means merge-ready. The final PR head must pass migrations, tenant isolation, security, production build, browser acceptance and repository-required checks, and must have no unresolved blocking review threads.
