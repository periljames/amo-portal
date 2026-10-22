# Portal and PostgreSQL recovery — 22 October 2026

## Established causes

The VM and Tailscale were online, but PostgreSQL 16/main was stopped after exhausting its startup retries. Its log reported an invalid WAL checkpoint and `PANIC: could not locate a valid checkpoint record`. Both `192.168.72.10:5432` and the VM's Tailscale address refused TCP connections. SSH to the private VM address worked immediately. This was a database startup failure, not evidence of a PostgreSQL authentication or browser cache failure.

The Windows frontend and API were also stopped. Tailscale Funnel still targeted `127.0.0.1:5173`, so it returned 502 until the frontend was restarted.

Public DNS-over-HTTPS resolved three Funnel ingress addresses. All three returned HTTP 200 for `/readyz` after recovery, taking approximately 3.6–3.8 seconds. The browser's previous 1.5-second readiness deadline was shorter than these healthy public requests and could incorrectly block uploads as offline.

## Data preservation and recovery

The original failed data directory `/var/lib/postgresql/16/main` was retained. Its data, configuration and PostgreSQL log were archived at:

- VM: `/var/backups/amo-recovery/incident-20261022/failed-cluster-and-config.tar`
- Windows: `%LOCALAPPDATA%/AMO-Portal/recovery/incident-20261022/failed-cluster-and-config.tar`

Both archives have SHA-256 `596416fa40c871ff91d4b9415e019f83e0732f832495b3fbe77dd95cf7fd9ce8` and size 462,264,320 bytes. They contain sensitive database material and remain outside Git.

The latest pre-incident complete backup, October 20 at 06:15 UTC, passed checksum verification and a separate restore. The user selected salvage before reverting to this older backup.

WAL reset was applied **only to a separate copied cluster**, which was started on loopback port 55433 with default transactions read-only and autovacuum disabled. Its full custom-format database export succeeded. That export was restored into a newly initialized cluster with page checksums. PostgreSQL `pg_amcheck --heapallindexed` passed on the rebuilt database. Sequential row counts matched for all 755 original public tables. An index in the damaged copy undercounted a worker-heartbeat table; rebuilding indexes through logical restore corrected that discrepancy. The salvage retained records newer than the old backup.

After explicit user approval, the rebuilt cluster was activated on port 5432. The service remains `postgresql@16-main`; its configuration remains `/etc/postgresql/16/main/postgresql.conf`, and its active data directory is `/var/lib/postgresql/16/incident_clean`. The duplicate `incident_clean` cluster registration was archived so it cannot accidentally be started against the active directory. The separate old-backup verification cluster is stopped and configured for manual startup.

TLS connections using the application's existing database credentials were verified. Existing HBA rules were retained. `fsync`, `synchronous_commit`, `full_page_writes`, and data checksums are enabled. Eleven pending repository migrations were applied successfully, ending at `extprov_261019_oversight`.

A fresh logical backup completed after migration and was copied and verified on Windows at `%LOCALAPPDATA%/AMO-Portal/backups/postgres/20261022T061003284975Z.tar`. The six-hour VM backup timer remains active.

The forensic copies brought the VM root filesystem to 93% usage. Its ext4 filesystem and logical volume were grown online by 8 GiB from the volume group's existing free space. Root usage fell to 74%, with approximately 9.6 GiB available. No recovery evidence was deleted.

**Recovery limitation:** a successful dump, clean restore, constraint creation and integrity checks do not prove that every transaction immediately preceding WAL corruption survived. The precise cause of the WAL damage was not established. The guest journal also showed an unclean prior shutdown. The preserved original remains available for further investigation. PostgreSQL's [WAL recovery guidance](https://www.postgresql.org/docs/16/app-pgresetwal.html) explains why a reset copy must be exported and rebuilt rather than used as the live database.

## Network and runtime changes

- Shared mode serves a built release through `scripts/portal_gateway.py`, using streaming request/response bodies, bounded upstream connections, independent inactivity timeouts, range support, static compression and immutable asset caching. Missing JS/PDF assets return 404 rather than the SPA HTML. Signed public navigation tokens containing dots still open the SPA.
- API auth headers, public host, response headers and individual cookies are forwarded. The upstream client does not store or reuse user cookies. Disconnect cleanup releases upstream sockets even when a tab cancels its stream. Backend connection failures return a marked 503 rather than HTML.
- Readiness probes now allow eight seconds. Browser-online probe transport failures are advisory `DEGRADED` observations; actual dependency readiness failures and browser-confirmed offline state retain their existing handling. An ambiguous background timeout cannot by itself block an upload.
- Multipart/blob uploads use size-aware deadlines. Common typed, QMS/CAR, evidence-pack and CRS downloads use bounded whole-request GET retries, inactivity detection, byte-count checks where applicable, caller cancellation, and account/tenant scope checks. Different attempts are never concatenated. A portal HTML fallback cannot silently become a downloaded file.
- Ambiguous writes are not replayed against a second backend address. A proxy-confirmed failure before reaching the backend can still use the existing alternate route. File uploads are not silently queued or declared complete on transport failure.
- The evidence-pack worker pauses and backs off during database outages, retains queued jobs, and resumes after recovery.
- Shared releases use bounded-retry parallel copying. Frontend and backend owners restart exited server processes. Owners prevent automatic idle sleep while running; explicit user sleep/shutdown remains possible. The default launch is hidden Shared mode; `-Visible` requests windows.
- A current-user `AMO Portal managed runtime.lnk` startup shortcut starts the supervised portal at Windows sign-in. It is not an unattended Windows boot service or VM autostart configuration.
- Ignored local environment settings now use a 20-second interactive pool wait, the actual database maximum of 100 connections, dedicated worker process counts, and the current required migration head. Previous local settings were backed up under `%LOCALAPPDATA%/AMO-Portal/recovery`.

Start and stop the managed runtime with:

```powershell
.\scripts\Start-Portal.ps1
.\scripts\Stop-Portal.ps1
# HMR for local frontend development:
.\scripts\Start-Portal.ps1 -Service Frontend -FrontendMode Dev -Visible
```

Logs and ownership records are under `.artifacts/portal-runtime`. Do not run duplicate unmanaged API/worker fleets. A shared frontend restart publishes the current built `frontend/dist` into a release snapshot.

## Verification

- Production build, modal checks and heavy-route checks passed; the final release includes the revised readiness policy.
- Frontend transfer/network/offline groups: 58 tests passed. Connectivity/eligibility groups: 28 passed, including eight overlapping contract tests.
- Gateway, runtime and worker recovery tests: 13 passed.
- Live gateway over real TCP: three 8 MiB uploads and three 8 MiB downloads matched SHA-256 exactly.
- The managed gateway was deliberately interrupted and restarted automatically; readiness returned 200 afterward. Public-host HTTPS redirects were verified to retain the public hostname.
- Live public Funnel ingress: an 8 MiB download matched SHA-256 in approximately 21.5 seconds; a 1 MiB byte-range request returned 206 and matched the expected bytes in approximately 4.0 seconds. The synthetic public probe file was removed afterward.
- API, database/migration readiness, and operations gateway readiness returned 200. Private database TCP probes succeeded 10/10. Tailscale netcheck reported working UDP and no captive portal.
- Evidence: `.artifacts/live-streaming-transfer-result.json`, `.artifacts/live-public-transfer-result.json`, test/build logs and runtime logs.

Synthetic transport checks do not establish that every business upload workflow or every remote device has been exercised. No synthetic audit evidence was added to tenant records. Public Funnel traffic still has Tailscale's [non-configurable bandwidth limits](https://tailscale.com/docs/features/tailscale-funnel). The workstation and VM must remain running; these changes do not provide hardware redundancy, point-in-time recovery or an uptime guarantee.
