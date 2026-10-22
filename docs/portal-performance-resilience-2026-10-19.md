# Portal latency and recovery review â€” 19 October 2026

## Readiness finding

The application has circuit breaking, bounded connection/statement timeouts, durable offline queues, idempotent replay and module-isolation tests. These do not establish database high availability or recovery from a VM/kernel failure. The supplied soft-lockup screenshot is an infrastructure incident; its root cause cannot be determined from that image alone. No VM kernel logs were available in this run. No VM restart, database termination or destructive failure injection was performed against the working database.

Live PostgreSQL settings: fsync=on, synchronous_commit=on, full_page_writes=on, wal_level=replica, archive_mode=off. The database was not in recovery mode. A physical replication/failover deployment and point-in-time recovery have not been demonstrated. Production readiness still requires an isolated restore drill, documented recovery-time/recovery-point objectives, independent failure domains and failover testing. Merely having a Kubernetes deployment template does not prove that infrastructure is deployed.

A fresh source dump dated 2026-10-19 06:01:53 UTC was copied to the Windows profile and all archive checksums verified. Previously visible local copies dated September 25. The backup utility now rejects source dumps older than twelve hours or invalid/future timestamps, and removes its own partial file after failed transfer/verification. Eight backup regression tests pass. The AMO backup-copy scheduled task was absent; attempted registration failed with Windows Access Denied. Automatic Windows copying is NOT verified. The supplied installer must be run by an account permitted to register tasks; its interactive-token setup only runs while that account is logged in. The VM source backup itself was current.

## Measured bottlenecks

Five steady-state read-only database probes: SELECT 1 median 0.9 ms, maximum 2.4 ms; connection acquisition including handshake 64.7 ms. These measurements describe healthy idle behavior, not outage or concurrent workload performance. Database guards were making two sequential network round trips for every transaction; both timeout settings now use one SELECT of transaction-local set_config calls. Read-only protection remains enabled and was verified against PostgreSQL with rollback.

This Windows workstation has about 12 GB RAM. Available RAM fell below 450 MB while running services, IDE/browser workloads and a full build. The visible backend runtime was stopped during build verification to avoid making memory pressure worse. Host contention is a credible contributor to observed latency; it does not prove the screenshot's root cause. A development workstation sharing resources with a VM is not evidence of production capacity.

The application entry was about 1,014 KB raw before this run (about 273 KB compressed), plus its framework chunk. Messaging and the Quality command palette are now separate lazy chunks. The installed React Router already uses startTransition; no obsolete compatibility flag remains.

The client has six concurrent API slots. Waiting requests previously had no queue timeout and started a fresh transport timeout only after admission, potentially multiplying delays during outages. Waiting now shares the same total request deadline with transport and alternate-route attempts; expired queued requests are removed without being sent. A fresh in-memory cache hit still returns before queue admission. Tests cover saturated queues, aborted requests, account switches, expiration and remaining transport budget.

## Loading behavior

No minimum page-display time was added. Global request activity now uses only a delayed unobtrusive progress bar; it cannot replace usable content with a workspace splash. Real first-load/code/data waits retain their local placeholders. Cached data and warmed route modules remain eligible to render immediately. Reaching 50â€“100 ms for cached in-app navigation is a useful target; a cold full reload, authentication or remote authoritative write cannot be universally guaranteed that time by a frontend change.

## Validation

Forty-four networking, cache, connectivity, service-worker, replay and realtime tests passed. Seven isolated database circuit/transaction-guard tests passed (no working database affected), plus eight backup tests. Live navigation and final build results follow after release verification. No emails or auditor/auditee workflow mutations were initiated.


## Rendering profile and native register changes

The initial build and live test did not meet the requested latency. Startup-contention login reached 8.6 seconds; repeated warmed clicks still took roughly one second after the UI click. A Chrome CPU profile identified AG Grid geometry/scroll measurement as dominant identifiable JavaScript work during these two small paginated registers (`measureSizeEl`, `getScrollPosition`, row/column measurement). This was not an assumption that the database was slow.

Findings and Audits now use a native, semantic HTML table for their bounded server-paginated results. Existing cell renderers, finding/CAR actions, audit links, delete controls, filters and pagination remain. Native columns can be resized with pointer or arrow keys. The two pages no longer import AG Grid runtime/CSS or create a grid just to display a few rows. Grid engines remain available to other workflows that use their features. Mobile finding cards remain. New table tests verify rows are present in initial HTML without a grid bootstrap and preserve workflow link/formatting output.

Background local workers now run below normal Windows CPU priority, while API and frontend retain normal priority. This was applied to the ten owned worker/wrapper processes without restarting them. Production launchers remain unchanged. It addresses CPU competition, not the machine's limited memory budget.

The isolated backend startup and frontend build were sequential to avoid repeating severe memory contention. Server windows remain visible and stoppable. Final measurements below describe this updated implementation, not the earlier grid baseline.


## Viewport registers and pagination

Findings, Audits, Evidence Vault and Recycle Bin now share the available viewport below portal navigation. Record regions flex to the bottom paginator; scrolling is contained within records. The Evidence Vault no longer has a centered maximum-width card. Desktop row actions use compact, accessible Lucide icons; mobile evidence cards retain explicit Download labels. The recycle-bin type badge no longer inherits a circular oversized presentation.

A shared paginator provides numbered pages, first/previous/next/last icons, range and total, rows per page, current-page announcement and a direct page-number input. It is used by the four registers, the shared QMS grid (including analysis/task lists), missions and module workspaces. Continuation-only APIs do not display an invented total/last page.

Recycle Bin now pages/filter/sorts deleted audits and schedules in SQL with tenant and role checks. It no longer fetches the entire audit population or only the first 500 schedules. Four isolated tests cover tenant scope, active-record exclusion, summaries, later pages, search/type filters, stable sorting and canonical URL ownership. The live check identified and corrected generic-route interception before final verification. Invalid response shapes produce a local query error rather than crashing the portal.

The first viewport run caught a mobile grid-row sizing bug which hid records below the navigation row. The mobile records shell now explicitly uses a column flex layout, allowing its content to grow below the separate navigation selector; legacy mobile block layout no longer collapses the content height. This finding demonstrates why compile success alone was not accepted as visual verification.

Verified evidence download: SIMULATED_WORKFLOW_TEST_audit_notice.pdf, 8,714 bytes, no browser download failure. No email, restore, purge, finding or CAR writes were performed.

Shared frontend service now serves a release snapshot outside the build output. Rebuilding dist cannot delete assets used by the running service. A new snapshot also retains the prior release's immutable chunks for already-open tabs. Publication remains an explicit visible frontend restart.

The candidate CSS passed twelve live geometry checks (1920x1080, 1366x768 and 390x844 across all four registers), including row-action containment and bottom-aligned pagination. Final release screenshots follow; the paginator was subsequently condensed to two rows on mobile. Investigation selection also uses the shared numbered paginator rather than Previous/More-only controls.


Visual inspection also caught an Analysis action rendered as the word Open inside a 54-pixel icon column. It now uses a named Eye button with explicit 30-pixel geometry and cell alignment, rather than borrowing the checklist-library button class. Phone recycle summaries use two columns so records retain usable height. Browser pagination fixture results are recorded separately from real-tenant checks; service-worker interception is explicitly bypassed only after the genuine disconnected reload check.


## Final verification — published release

The final production build passed TypeScript, 49 modal-source checks and entry-graph checks. CSS contracts passed for 129 stylesheets. The shared paginator/table suites passed eight tests; the recycle-bin backend suite passed four tests, including exact canonical-route ownership. Diff whitespace checks passed.

All twelve real-tenant viewport checks passed: 1920x1080, 1366x768 and 390x844 on Findings (4 records), Audits (2), Evidence (3) and Recycle Bin (1). No outer-page vertical overflow was measured; bottom pagination aligned within one pixel of the content bottom; tested native row actions stayed inside their cells. Screenshots were inspected. The mobile recycle record is visible below a two-column summary. Analysis's three Eye buttons measure 30x30 inside 43-pixel cells. The register paginator is present on its Registers tab. Findings was visually checked in dark mode, then the original theme restored.

The real evidence download succeeded again: readable filename, 8,714 bytes, no browser failure. The cached Findings page reopened while fully disconnected in 1,917 ms. This proves that cached read path, not universal offline write/attachment/sign-off coverage.

A separate browser-only pagination fixture retained the four genuine row shapes and supplied a synthetic total of 2,500. Direct page 5 requested offset 100; Last requested offset 2475; First returned to page 1. No synthetic records were inserted. The earlier fixture had supplied an inconsistent empty row set and therefore did not display the nonempty register's footer; its timeout remains in the raw log. The valid-row fixture passed with no render errors or HTTP 5xx. Structured validation: `.artifacts/audit-workflow-run/portal-viewport-validation.json`; pagination fixture: `portal-pagination-live.json`.

The final real-data run captured no online JavaScript render errors or HTTP 5xx. It did capture 17 refused MQTT websocket connection attempts to ws://127.0.0.1:8084/mqtt. No listener was present there; the operations gateway was listening on 8090. Full realtime/cross-device behavior is therefore NOT verified by this run and remains a recorded infrastructure/configuration fault.

Observed successful login-to-navigation was 2,952 ms in the final viewport run and 1,724 ms in the later steady-state fixture run. Repeated warm UI clicks in the viewport run took 670–882 ms after the first Audits visit. These are local workstation observations under the active runtime, not a production benchmark. The requested sub-100-ms navigation target has NOT been achieved. Earlier native-table measurements were faster under less contention; they do not override the current results. Cold backend startup also remains slow.

No email action, audit response, finding/CAR update, restore or purge was performed. Backend and frontend remain in named visible consoles; closing them or running `scripts/Stop-Portal.ps1` stops the owned trees. Temporary credentials were deleted and test browsers closed. Database failover, PITR, automatic Windows backup copying and an isolated restore remain unverified as described above.
