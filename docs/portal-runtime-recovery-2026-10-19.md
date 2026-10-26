# Portal runtime recovery — 19 October 2026

The previous loading change introduced a regression. Optional IndexedDB access was on the online request path, and login waited for data downloads, unrelated route preloads and animation. Online requests now use the existing network-first behavior. Optional query restoration has an 800 ms deadline; durable queued changes and attachment writes remain awaited. Successful GET responses no longer wait for optional encrypted cache persistence. Authentication navigates immediately after success and warms only the intended landing page.

The service worker prefers current navigation HTML, falling back to cached HTML after 350 ms when the network stalls. Immutable hashed assets retain cache-first delivery. Automatic bulk QMS warming skips constrained 2G/3G connections; explicit offline preparation remains available. This recovery does not assert full offline coverage for every workflow.

## Visible runtime controls

The previously orphaned backend, frontend 5173 and preview 4173 process trees were stopped. New server launches use labelled visible PowerShell windows. Each window owns a Windows job object: closing it terminates its descendants. Ownership records include process start ticks and workspace identity; the stop command refuses an unrelated reused PID. Startup refuses occupied ports rather than silently choosing another port.

```powershell
# Serve an explicitly built frontend, with visible backend and frontend windows:
npm --prefix frontend run build
.\scripts\Start-Portal.ps1 -FrontendMode Shared
# HMR instead, when changing frontend source:
.\scripts\Start-Portal.ps1 -Service Frontend -FrontendMode Dev
# Stop both owned consoles and every child:
.\scripts\Stop-Portal.ps1
# Or stop only one:
.\scripts\Stop-Portal.ps1 -Service Frontend
```

Shared mode copies the existing dist into a release snapshot before serving it; rebuild and restart explicitly after source changes. A build cannot remove assets from the running snapshot, and the next release retains the prior snapshot’s immutable assets for already-open tabs. IDE environment terminals run foreground commands, so Ctrl+C is available. Backend startup brings up the API first and staggers auxiliary services. The development durable worker keeps all seven job families in one process instead of spawning seven copies; production worker defaults remain isolated.

## Verification

Production build passed, including TypeScript, 49 modal checks and heavy-route entry checks. CSS contracts passed for 129 stylesheets. Recovery/frontend groups passed 55 tests and 42 tests (overlapping suites), and runtime controls/local worker tests passed seven tests. The blocked-IndexedDB test verifies online query restoration resumes after its deadline. Login warmup is tested with a preload promise that never settles.

Live headed Chrome authenticated through the frontend: login shell DOM 573 ms, successful login POST 2690 ms, navigation to Quality 2800 ms from clicking Sign In. Steady-state API probes returned livez 200 in 125 ms and readyz 200 in 47 ms. The four finding records rendered, with no captured page errors or HTTP 5xx in that check. Account identification was slow during the initial run; these local figures do not establish remote-network or all-module performance. The 12 GB workstation had about 1.5 GB free after build completion; simultaneous builds and development compilation caused severe contention earlier.

No emails were sent. Audit answers, findings, Elvin's CARs and offline queued work were not cleared.

Additional live checks: both audit rows rendered; Analysis displayed four findings and three CARs; People displayed four active authorizations. Warm findings reload reached visible rows in 2680 ms; fully disconnected reload reached the four saved findings in 1396 ms. This verifies those cached records, not all-module offline coverage. Stopping the visible frontend released port 5173; starting Shared mode again restored it in a new visible console. Live results: `.artifacts/audit-workflow-run/portal-recovery-live.json`.
