# QMS online and offline readiness

QMS route preloading recognises both `quality` and `qms` routes. Specialist pages load separately from the canonical workspace, including the six audit stages. The production build emits their static dependency closure in `dist/portal-precache.json` under `qmsUrls`.

The service worker installs the small application shell first. After entering Quality, a visible, online browser requests background QMS asset warming after a random 10–30 second delay. Downloads use at most two concurrent requests, skip existing immutable assets, and coalesce repeated warmup requests. Data Saver and 2G connections skip proactive warming. Returning online or making the page visible schedules another attempt. Browser storage limits can still evict cached assets.

Navigation falls back to the cached shell on network errors, server failures, or after 2.5 seconds when a cached shell exists. The network request continues refreshing the shell in the background. API responses and authenticated PDFs are never added to the service worker's asset cache. Existing tenant/user-scoped encrypted IndexedDB persistence remains responsible for eligible records and drafts.

Offline availability requires a prior online visit and successful caching. Precaching page code does not download every tenant record or document. Assignment eligibility, independence, preparation readiness and approval authority are excluded from persisted/stale fallback; old persisted authority queries are filtered during restoration. Team verification and setup progression require online checks. Server-side workflow checks remain authoritative.

Audit Setup preserves unsaved edits during background refreshes, retains assigned people missing from directory pagination, validates meeting chronology, distinguishes notice revisions from template revisions, and provides one Prepare action. Existing historical records are not rewritten automatically.

Eleven unused legacy QMS page, host and stylesheet files were removed after checking references. `QmsAssurancePage.tsx` remains because an operational UI validation script reads it.

## Release verification

- Run `npm run build` and `npm run test:quality` in `frontend`.
- Run `npm run test:qms-offline` for route-loader, cache-policy, service-worker, offline HTTP and audit setup control regression tests; run the auth recovery Vitest tests as well for authentication changes.
- Run backend audit meeting/workflow/notice and authentication regression tests with the project virtual environment.
- Serve the production build over HTTPS (or localhost), allow the QMS background warmup to finish, then verify navigation and previously opened records with the network disabled. Reconnect and verify fresh permissions before sensitive actions.
- Test cross-user and cross-tenant switching, refresh after deployment, and constrained connections in a browser before rollout.

The implementation build produced six eager shell URLs and 199 QMS asset URLs, all present on disk (about 6.6 MB before transfer compression). The repository's entry-graph budget check passes; it still reports a substantial shared application entry. These build measurements are not a guarantee of regional load latency or 1,000-user server capacity. See `authentication-burst-readiness.md` for shared rate-limit configuration and staging load validation. Automated browser verification was unavailable in this execution environment.
