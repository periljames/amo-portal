# AMO local VM reliability work — 25 September 2026

## Evidence and changes

The application used `megatron` / `100.95.25.50` over Tailscale. Guest logs on
25 September around 04:49 UTC showed UDP failures, relay connection deadlines,
and repeated network rebinding. PostgreSQL logged client timeouts and open
transactions losing their clients. Keeping either machine awake cannot fix
that network path. The supplied Uvicorn log ends with an orderly shutdown;
it does not establish what requested that shutdown.

The VM runs on this Windows PC at `E:\AMOs DB_Server.vmx`. Its private VMware
VMnet8 interface now has persistent address `192.168.72.10/24`, outside the
configured DHCP range `.128–.254`. Windows is `192.168.72.1`. The guest's
existing DHCP address is retained. Netplan matches the private NIC by MAC.
The development database URLs now use this private IP and require TLS.
PostgreSQL permits only `amodb_app` to `amodb` from `192.168.72.1/32` on this
path, using SCRAM and TLS. Other access rules were preserved.

Initial 32 MiB synthetic database downloads measured 35.5 Mbps over Tailscale
and 332–361 Mbps over private VMnet8 with E1000. These are application payload
measurements, not an iperf benchmark or an uptime/jitter guarantee. A separate
128 MiB single-stream Python TCP test measured 202/210 Mbps with E1000; results
depend on protocol, host load and CPU work. VMnet8's displayed Windows adapter
speed is not a measured throughput cap.

The private adapter was subsequently changed to VMXNET3 and verified after a
clean VM shutdown/startup. The latest private database samples were 228–397 Mbps.
A four-stream Python socket run during application startup measured only
67.5 Mbps, demonstrating host-load sensitivity. Full 1 Gbps saturation and
near-zero jitter have NOT been established. Do not treat any one sample as an SLA.

Application changes:

- Offload the blocking database recovery probe from the async HTTP event loop.
- Pause Document Control reminders during a database outage, discard failed
  sessions safely, and resume without waiting the normal one-hour interval.
- Avoid automatically loading unbounded security-event history with user lists.
- Mark cached admin snapshots stale; emit freshness events; return HTTP 503
  from readiness when snapshots are stale or the refresh task is stopped.
- Keep the snapshot refresh loop alive if closing a broken DB session fails.
- Add `--no-reload` to the existing development process supervisor.

Database durability: `fsync`, `full_page_writes`, and `synchronous_commit` were
already enabled and remain enabled. Page checksums were enabled during a clean
maintenance stop/start. The PostgreSQL systemd unit now restarts on failure,
with a five-second delay and a five-starts-per-five-minutes limit. Explicit
maintenance stops should use `systemctl stop postgresql@16-main`.

## Backups and recovery

Installed in the VM:

- `/usr/local/sbin/amo-backup-postgres`
- `/usr/local/sbin/amo-export-postgres-backup`
- `/usr/local/sbin/amo-verify-postgres-backup`
- `amo-postgres-backup.service` and `.timer` (every six hours, UTC)
- Backup repository `/var/backups/amo-postgres`, accessible only to postgres

Each backup contains a consistent custom-format `pg_dump`, global roles,
archive table of contents and SHA-256 manifest. Completed backups are published
by renaming a staging directory. Failed/incomplete directories are not exported.
An isolated restore of `20260925T052046Z` succeeded with 722 tables and 71 users;
the disposable database was subsequently removed. This verifies that archive,
not every future backup or every application's business-level recovery behavior.

Run a further restore drill on the VM:

```sh
sudo -u postgres /usr/local/sbin/amo-verify-postgres-backup
systemctl list-timers amo-postgres-backup.timer
journalctl -u amo-postgres-backup.service --since today
```

Windows host copies are under
`%LOCALAPPDATA%\AMO-Portal\backups\postgres` on the C: NVMe disk, physically
separate from the VM's E: SATA disk. An additional initial copy is on
`E:\AMO-Backups\postgres`. Backup folders and the recovery key folder have
restricted Windows ACLs. Roles and tenant data are sensitive; preserve these
permissions when moving backups.

```powershell
.venv\Scripts\python.exe scripts\backup_private_vm.py
```

The host copy uses a new SSH key restricted to source `192.168.72.1` and a
forced export command, with forwarding disabled. It cannot execute arbitrary
remote commands. No supplied SSH password is stored in repository scripts.

Windows rejected scheduled-task registration with **Access is denied**. The
task is NOT installed. From an elevated PowerShell for the same Windows user:

```powershell
.\scripts\install-backup-copy-task.ps1
```

This task uses an interactive token and runs while that user is logged in.
For logged-out/unattended operation, provision a dedicated service account
and a non-interactive scheduled task, with access to the backup key and folder.
Task schedule uses Windows local time; the guest backup timer uses UTC.

Current recovery limits:

- Scheduled logical backups have up to six hours of data loss exposure, longer
  if a backup fails. The host copy schedule still requires installation.
- WAL archiving is OFF. There is no point-in-time recovery or synchronous replica.
- Backups cover PostgreSQL, not tenant file/object storage, VM disks or all
  application configuration. Include those in the NAS backup design.
- C: and E: copies share this PC's power, controller and theft/ransomware risks.
- Guest retention keeps 28 completed backups marked by the current script
  (seven days at four per day); Windows keeps 56 verified copies (14 days at
  four per day). Initial unmarked guest backup and incomplete directories are
  preserved for inspection. Monitor free space, backup failures and backup age.
  The guest refuses to start a new backup with less than 1 GiB available.
- Guest root filesystem was 84% full (4.7 GiB free); its volume group has 31 GiB
  unallocated. Plan filesystem expansion and a bounded backup retention policy.

When the NAS is ready, configure an independent, protected backup repository
(for example pgBackRest base backups plus continuous WAL archiving), include
tenant file storage, define retention/RPO/RTO, and rehearse full restores.
An independent synchronous standby is needed if loss of this PC must not lose
acknowledged writes; replication does not replace backups.

## Runtime and remaining uptime work

The existing supervisor restarts exited processes and isolates API/worker
connection pools. Start it from the repository root, after stopping old copies:

```powershell
.venv\Scripts\python.exe scripts\dev_runtime.py --no-reload --no-frontend
```

It runs API 8080, ops gateway 8090 and configured workers. This remains a
development runtime: it does not install a Windows boot service, provide VM
autostart, serve a production frontend, rotate redirected logs or provide HA.
For continuous operation, supervise it under a dedicated service account,
configure Windows and VMware startup/recovery, rotate logs, and run external
alerts against readiness, backup age, disk space and DB connection usage.
Do not start duplicate API/worker fleets: PostgreSQL has 100 max connections.

The no-reload supervisor was started during this work (initial PID 25872).
Both API `/readyz` on 8080 and ops `/readyz` on 8090 returned HTTP 200; ops
snapshots were fresh with zero broker refresh failures. Runtime output is in
`%LOCALAPPDATA%\AMO-Portal\runtime\20260925-013330.stdout.log` and its stderr
companion. The frontend was not started by this supervisor.

Validation: 18 targeted pytest tests passed, including account directory,
security-history loading, worker recovery, broker freshness and HTTP readiness.
Python compilation, PowerShell parsing and `git diff --check` passed. The
updated backup/retention script completed another successful backup at
`20260925T053821Z`; a checksum-verified Windows copy was made at 05:38 UTC.
The external internet speedtest provider returned HTTP 403 during scheduler
startup; that telemetry is unavailable and must not be shown as a successful
internet capacity measurement. The private database tests are independent of it.

Freshness flags in API/SSE responses must also be displayed by monitoring
clients. Retained historical snapshots are not live measurements. This change
does not bypass existing tenant authorization or grant new tenant privileges.

Rollback locations:

- Original dotenv file: `%LOCALAPPDATA%\AMO-Portal\recovery\env.development.before-private-*`
- Guest HBA: `/etc/postgresql/16/main/pg_hba.conf.before-amo-local-*`
- VMX: `E:\AMOs DB_Server.vmx.before-amo-vmxnet3-20260925`
- Private netplan overlay: `/etc/netplan/60-amo-private.yaml`
- PostgreSQL recovery override: `/etc/systemd/system/postgresql@16-main.service.d/amo-recovery.conf`

Never copy a live PostgreSQL data directory as a database backup. Do not disable
fsync/synchronous commits/full-page writes to obtain a better throughput number.

References: [Tailscale performance troubleshooting](https://tailscale.com/docs/reference/troubleshooting/poor-performance-tailnet),
[VMware virtual network adapter types](https://knowledge.broadcom.com/external/article/321259/),
[PostgreSQL durability settings](https://www.postgresql.org/docs/16/runtime-config-wal.html).
