# QMS Live Audit Acceptance Trace

This matrix tracks the supplied Live Audit operating specification against PR #502 after the code-completion pass.

**Status rule:** `IMPLEMENTED / NOT YET PROVEN` means source, integration and executable acceptance exist on the branch, but the exact current head has not yet passed the required workflow. A row becomes `COMPLETE` only after exact-head executable evidence is green. The PR remains draft until every required row is proven.

| # | Requirement | Pre-validation status | Executable/source evidence |
|---|---|---|---|
| 1 | Programme occurrence becomes an audit | EXISTING / NOT YET RE-PROVEN | Audit Programme + canonical occurrence router |
| 2 | Schedule audit | EXISTING / NOT YET RE-PROVEN | Governed planner/schedule lifecycle |
| 3 | Assign internal lead/audit team | IMPLEMENTED / NOT YET PROVEN | Setup assignment + People & Privileges qualification/independence/workload gates |
| 4 | External auditor invitation | IMPLEMENTED / NOT YET PROVEN | Purpose-bound participant/grant model; EMAIL_LINK or PASSKEY |
| 5 | Independence/eligibility blocks assignment | IMPLEMENTED / NOT YET PROVEN | Active privilege, scope, training, workload and audit-specific independence gates |
| 6 | Notice issue / acknowledgement | IMPLEMENTED / NOT YET PROVEN | `qms-live-audit-setup-prepare-real.spec.ts` drives CREATE→SUBMIT→APPROVE→GENERATE→DELIVER→ACKNOWLEDGE |
| 7 | Explicit opening/closing meetings | IMPLEMENTED / NOT YET PROVEN | Real Setup browser creates both meetings; PostgreSQL workflow asserts both records |
| 8 | Auditee document requests | IMPLEMENTED / NOT YET PROVEN | Real Pre-Audit browser creates criterion-linked governed request |
| 9 | Upload or controlled-DMS response | IMPLEMENTED / NOT YET PROVEN | Real auditee browser uploads file; PostgreSQL verifies stored file SHA; DMS path remains backend-contract covered |
| 10 | Auditor accept / return / waive | IMPLEMENTED / NOT YET PROVEN | Real internal browser accepts auditee submission with attributable review note |
| 11 | Exact checklist revision bound | EXISTING / NOT YET RE-PROVEN | Frozen binding revision/SHA |
| 12 | Source/expected evidence shown in Live | IMPLEMENTED / NOT YET PROVEN | Immutable binding snapshot projected per checklist item without N+1 calls |
| 13 | Live checklist response persists | IMPLEMENTED / NOT YET PROVEN | Real browser fieldwork + PostgreSQL version/actor assertions |
| 14 | Realtime collaboration | IMPLEMENTED / NOT YET PROVEN | Two separately authenticated browsers; B must update from audit-scoped SSE without refresh/focus/reload |
| 15 | Internal offline queue/replay | IMPLEMENTED / NOT YET PROVEN | Encrypted portal outbox + idempotency/base-version contracts |
| 16 | External auditor offline queue/replay | IMPLEMENTED / NOT YET PROVEN | Real browser offline queue, reconnect and PostgreSQL receipt assertions |
| 17 | Stale conflict visible | IMPLEMENTED / NOT YET PROVEN | Real stale browser gets 409; newer version survives |
| 18 | Governed evidence artifacts | IMPLEMENTED / NOT YET PROVEN | Immutable evidence model/SHA contracts and browser preparation upload proof |
| 19 | Auditee sees released data only | IMPLEMENTED / NOT YET PROVEN | Server-filtered released projection + public browser assertions |
| 20 | Finding receipt separate from acceptance | IMPLEMENTED / NOT YET PROVEN | Real auditee finding receipt persisted independently |
| 21 | Official NC creates canonical CAR | EXISTING / NOT YET RE-PROVEN | Atomic finding/CAR workflow |
| 22 | Closing finding/CAR sharing | IMPLEMENTED / NOT YET PROVEN | Released finding boundary; CAR projection limited to released finding |
| 23 | Closing narrative persisted | IMPLEMENTED / NOT YET PROVEN | Management summary, conclusion and positive practices included in closing fixture/report composition |
| 24 | Fieldwork freeze before report | IMPLEMENTED / NOT YET PROVEN | Actual-end/NOT_VERIFIED generation gates |
| 25 | Report generated without manual upload | IMPLEMENTED / NOT YET PROVEN | Real closing browser generates/downloads deterministic report artifact |
| 26 | Report includes closing narrative/meetings | IMPLEMENTED / NOT YET PROVEN | `QMS_AUDIT_REPORT_SNAPSHOT_V2` |
| 27 | Generated artifact adopted into governed report | IMPLEMENTED / NOT YET PROVEN | Real browser generated artifact → governed DRAFT |
| 28 | Auditee closing response before review/approval | IMPLEMENTED / NOT YET PROVEN | Separate auditee browser records response against exact DRAFT revision/SHA |
| 29 | Quality review / approval | IMPLEMENTED / NOT YET PROVEN | Real internal browser SUBMIT→APPROVE |
| 30 | WebAuthn/passkey electronic signing | IMPLEMENTED / NOT YET PROVEN | Chromium virtual CTAP2 authenticator performs real browser WebAuthn create/get ceremony against exact APPROVED SHA |
| 31 | Issue refuses stale/missing signature | IMPLEMENTED / NOT YET PROVEN | ISSUE is disabled before passkey evidence; backend signing contracts cover stale/missing evidence |
| 32 | Issued report immutable | IMPLEMENTED / NOT YET PROVEN | Governed revision/SHA lineage; PostgreSQL recomputes artifact hash |
| 33 | Public verification | IMPLEMENTED / NOT YET PROVEN | Separate unauthenticated browser verifies purpose-bound token and locally compares governed SHA |
| 34 | Policy-controlled certificate/approval output | IMPLEMENTED / NOT YET PROVEN | NONE / REPORT_ONLY / APPROVAL_LETTER / CERTIFICATE / ATTESTATION; real ceremony uses REPORT_ONLY |
| 35 | Auditee issued-report receipt | IMPLEMENTED / NOT YET PROVEN | Real auditee browser downloads and records exact issued revision/SHA receipt |
| 36 | Execution closes while CAR remains open | IMPLEMENTED / NOT YET PROVEN | Real ceremony closes execution and PostgreSQL requires follow-up OPEN + linked CAR OPEN |
| 37 | RCA / CAP submission | IMPLEMENTED / NOT YET PROVEN | `qms-car-control-loop-real.spec.ts` responsible-manager public submission |
| 38 | Quality reject / return / accept | IMPLEMENTED / NOT YET PROVEN | Real Quality browser rejects initial RCA/CAPA, public actor reworks, final review accepts |
| 39 | Reminders / escalation | EXISTING / NOT YET RE-PROVEN | Existing CAR reminder/escalation service |
| 40 | Extension with risk / decision | IMPLEMENTED / NOT YET PROVEN | Real CAR browser requests extension with impact statement; Quality approves decision |
| 41 | Effectiveness and final closure | IMPLEMENTED / NOT YET PROVEN | Five staged milestones, blocking dependency, effectiveness review and governed close; PostgreSQL event assertions |
| 42 | Dedicated Follow-up workspace | IMPLEMENTED / NOT YET PROVEN | Audit-filtered CAR queue + control-loop detail/readiness |
| 43 | Archive governance | IMPLEMENTED / NOT YET PROVEN | Real browser manifest/package generation, download, legal-hold place/release; PostgreSQL recomputes package SHA |
| 44 | Cross-tenant public/direct-object isolation | IMPLEMENTED / NOT YET PROVEN | Forced RLS metadata plus non-owner/non-superuser runtime tenant read/write isolation probe; external-token contract tests cover tamper/expiry/CSRF/downgrade |
| 45 | Mobile closeout deep link | IMPLEMENTED / NOT YET PROVEN | URL-derived canonical Closing state plus responsive acceptance |
| 46 | Unimplemented MFA not presented | IMPLEMENTED / NOT YET PROVEN | UI omits generic MFA; backend rejects unsupported assurance fail-closed |
| 47 | Competing legacy occurrence surface removed | IMPLEMENTED / NOT YET PROVEN | Canonical stage shell; legacy Run Hub does not mount |
| 48 | Narrow realtime/query invalidation | IMPLEMENTED / NOT YET PROVEN | Active occurrence only; other audit events ignored |
| 49 | Responsive public workspace | IMPLEMENTED / NOT YET PROVEN | Playwright explicitly covers 360, 390, 430, 768, 1024, 1280 and 1440 px with long content and overflow/touch assertions |
| 50 | Keyboard/focus/error accessibility | IMPLEMENTED / NOT YET PROVEN | Playwright verifies keyboard action, visible focus, semantic main/H1/control names, status announcement, reduced motion, expired/revoked fail-closed states |
| 51 | Network/API semantics | IMPLEMENTED / NOT YET RE-PROVEN | `apiClient.ts`: HTTP failures terminal, alternate route only on genuine transport/proxy failure, AbortSignal retained, dev-only direct route, production single primary route |

## Real-stack acceptance workflows added for the final validation phase

- `.github/workflows/qms-live-audit-real-browser-ci.yml`
  - clean PostgreSQL → `alembic upgrade heads` → FastAPI → production Vite preview → Chromium
  - fieldwork persistence, two-party SSE, offline/reconnect/exactly-once/conflict
  - exact-SHA acknowledgement, WebAuthn signing, ISSUE, public verification, execution close, archive and legal hold
  - post-browser PostgreSQL integrity assertions
- `.github/workflows/qms-live-audit-setup-prepare-real-browser-ci.yml`
  - independent clean database and real Setup/Prepare browser journey
  - PostgreSQL proof for occurrence definition, meetings, governed notice, auditee upload/hash, internal acceptance and EMAIL_LINK grant
- `.github/workflows/qms-car-control-loop-real-browser-ci.yml`
  - independent clean database and real responsible-manager/Quality CAR lifecycle
  - rejection/rework, deadline governance, dependency, implementation/evidence/effectiveness milestones and closure persisted to PostgreSQL
- `.github/workflows/qms-live-audit-ci.yml`
  - final-head schema/RLS/immutable-history probe now proves runtime tenant isolation with a non-owner/non-superuser role, not metadata alone
  - public/responsive/browser accessibility suite

## Security boundary retained

- Auditee: `EMAIL_LINK`.
- External auditor: `EMAIL_LINK` or `PASSKEY`.
- Generic unsupported MFA: fail closed.
- Existing identity assurance cannot silently downgrade/upgrade between PASSKEY and EMAIL_LINK.
- Ordinary access-token exchange rejects a PASSKEY-required external auditor before acceptance/session mutation.
- Tenant context is established before external identity lookup; grants are audit/tenant/scope/expiry/revocation bound.

## Release rule

This document records **source-completion evidence only** until the validation phase runs. Do not relabel a row `COMPLETE`, mark PR #502 ready, or merge it until the same final head has passing executable acceptance for every required layer and no unresolved required CI failures.
