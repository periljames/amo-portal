# QMS online and offline readiness

QMS route preloading recognises both `quality` and `qms` routes. Specialist pages load separately from the canonical workspace, including the six audit stages. The production build emits their static dependency closure in `dist/portal-precache.json` under `qmsUrls`.

The service worker installs the small application shell first. After entering Quality, a visible, online browser requests background QMS asset warming after a random 10–30 second delay. Downloads use at most two concurrent requests, skip existing immutable assets, and coalesce repeated warmup requests. Data Saver and 2G connections skip proactive warming. Returning online or making the page visible schedules another attempt. A separate portal warmup now downloads the immutable code and style assets for every module with the same two-request concurrency and connection safeguards. The generated `portalUrls` list keeps those downloads out of the critical shell install. The production Chrome test verified shell navigation and all 397 declared module assets with the network disabled. Browser storage limits can still evict cached assets.

Navigation falls back to the cached shell on network errors, server failures, or after 2.5 seconds when a cached shell exists. The network request continues refreshing the shell in the background. API responses and authenticated PDFs are never added to the service worker's asset cache. Existing tenant/user-scoped encrypted IndexedDB persistence remains responsible for eligible records and drafts.

Offline availability requires a prior online visit and successful caching. Precaching page code does not download every tenant record or document. Assignment eligibility, independence, preparation readiness and approval authority are excluded from persisted/stale fallback; old persisted authority queries are filtered during restoration. Team verification and setup progression require online checks. Server-side workflow checks remain authoritative.

Audit Setup preserves unsaved edits during background refreshes, retains assigned people missing from directory pagination, validates meeting chronology, distinguishes notice revisions from template revisions, and provides one Prepare action. Existing historical records are not rewritten automatically.

The service worker's offline readiness asset filter uses a valid JavaScript regular expression; a parse error here prevents the entire worker from installing. Checklist history stores capture timestamps as JSON strings. Replaying a committed internal checklist or finding command returns its receipt even after fieldwork closes, while new writes still require the current lifecycle and permissions. Pending changes remain on the device until the server confirms them.

Module HTTP failures pause that module's replay queue while other modules continue. Backoff and unresolved conflicts preserve ordering within the affected module. A confirmed shared database outage or expired session still pauses replay globally. Module-only 503 responses do not change portal connectivity. `/resilience/commands` must be proxied to the API in both Vite and Nginx so retry receipt checks receive JSON.

The portal-wide sync coordinator replaces the former QMS-only coordinator. It debounces new saves by 300 ms, follows command retry deadlines, and schedules another pass for changes created during a replay. Up to three module queues progress concurrently; commands within each module remain ordered. A renewable replay lease prevents duplicate ownership across tabs. This concurrency limit is not a measured production throughput guarantee.

All HTTP-queued writes require a committed durable device save. Their idempotency keys are attached before the first HTTP attempt and retained unchanged for transport retries. Human-reviewed revision rebases receive a new key. Unreadable encrypted drafts remain visible for recovery. Other connected devices refresh affected query families after server events; disconnected devices retain their own local queues until reconnection.

`/livez` runs without borrowing a database request worker thread. API readiness continues to require the database and migrations; background worker faults are reported separately in `jobs` and `jobs_ready`. Workspace render errors show local recovery controls inside the tenant shell so navigation remains available.

Eleven unused legacy QMS page, host and stylesheet files were removed after checking references. `QmsAssurancePage.tsx` remains because an operational UI validation script reads it.

## Release verification

The replay registry now includes 31 additional creation workflows in Training, Tasks, Fleet, Maintenance, Technical Records, Inventory, Finance, Procurement and Reliability, alongside the six existing guarded operations. Existing forms opt in automatically through the shared JSON transport. Each new server adapter commits the domain changes and replay receipt in one transaction, validates the public response before commit, and retains permission dependencies. Retrying a committed command returns the original response. All six inventory mutation routes now have replay contracts.

Fresh-every-time API reads retain an encrypted offline copy even when their in-memory freshness is zero. The transport waits for cache persistence before completing a read. The sync panel exposes saved item labels, content summaries and capture times.

Verification on 2026-10-16: 122 sync tests, 59 QMS offline tests, 48 Chrome storage/sync cases plus one production service-worker browser case, 35 backend event/fieldwork/task/fault-isolation and replay tests, and the production build pass. Backend coverage includes real database-backed personal-task, training-course and reliability-recommendation receipt/rollback checks. Chrome storage tests use fixture HTTP responses; they verify real browser storage and transport behavior, while live PostgreSQL acceptance remains a separate check.

- Run `npm run build` and `npm run test:quality` in `frontend`.
- Run `npm run test:qms-offline` for route-loader, cache-policy, service-worker, offline HTTP and audit setup control regression tests; run the auth recovery Vitest tests as well for authentication changes.
- Run `npm run build` followed by `npm run test:offline-assets` to check production service-worker coverage for module assets and shell navigation with the network disabled.
- Run `npm run test:sync` and `npm run test:offline-browser` for storage, conflict recovery, networking, live-event refresh and actual Chrome offline reload/multi-tab replay coverage. Browser tests use fixture API outcomes and do not certify live PostgreSQL acceptance.
- Run `npm run audit:offline` to regenerate the [module coverage audit](offline-capability-audit.md). The registry covers 37 operations (38 registered write routes including aliases) across 12 API modules. The audit verifies that all 31 new frontend creation contracts match their registered atomic backend handlers. Other operations are listed individually in the audit.
- Run `npx vitest run src/services/offlinePersistence.test.ts src/services/portalConnectivity.test.ts src/services/devProxyRouting.test.ts` for module isolation and receipt routing. Backend regression coverage is in `test_audit_fieldwork_sync_contract.py` and `test_module_fault_isolation.py`.
- Run backend audit meeting/workflow/notice and authentication regression tests with the project virtual environment.
- Serve the production build over HTTPS (or localhost), allow the QMS background warmup to finish, then verify navigation and previously opened records with the network disabled. Reconnect and verify fresh permissions before sensitive actions.
- Test cross-user and cross-tenant switching, refresh after deployment, and constrained connections in a browser before rollout.

Build asset counts vary by release and do not guarantee regional load latency or server capacity. See `authentication-burst-readiness.md` for shared rate-limit configuration and staging load validation. Chrome coverage includes offline reload and replay for all 37 operations, cached reads from nine module families, shared-tab lease ownership and conflicting edits across isolated device profiles. Production acceptance requires the deployed API and PostgreSQL.

## QMS and DMS follow-up, 2026-10-17

DMS JSON services (library, document detail, work queues, portfolios, reporting, retention and evidence metadata) now use the shared scoped offline transport. Controlled file bytes remain in their dedicated encrypted store. Publication bootstrap persistence completes before the reader load returns; section content is indexed individually so a saved section can reopen under a different request batch. Explicit server permission failures do not fall back to old section content.

QMS evidence, external audit evidence and controlled PDF storage select their encryption key in a single IndexedDB write transaction. Concurrent first saves cannot overwrite one another's key. The browser tests capture evidence in two tabs, reopen the database and decrypt both files; controlled PDF tests reopen the exact bytes offline and verify different user/tenant identities cannot retrieve that copy.

QMS pending checklist changes now project saved notes, sampled items and assessments back into the workspace. New edits follow their pending predecessors' expected versions and stay queued until those predecessors replay. Same-base draft compaction remains supported; it does not replace commands with different expected versions. A real server conflict still requires review. Absolute backend attempts also respect the browser's physical offline flag.

DMS document change requests and periodic review plans have atomic replay receipts on the effective guarded routes. Their forms treat a durable queued save as a device save and clear successfully captured input. Receipt replay rechecks current document access or control permissions, then returns the original committed response before duplicate-review checks. UTC dates sent by the browser are normalized before review-date comparison.

Follow-up verification: 54 Chrome storage/sync cases, 128 sync tests, 64 QMS offline tests, 86 targeted DMS/reader/workspace tests, and 21 backend replay/DMS route/workflow tests pass. The final production build and heavy-route chunk check pass. Browser HTTP outcomes are fixtures; these checks cover the actual browser clients, storage and cryptography, alongside database-backed DMS creation/replay tests. They do not certify a deployed PostgreSQL environment.
