# PostgreSQL recovery — 18 November 2026

PostgreSQL 16/main was stopped after repeated startup failures recorded on
13 November. Its journal reported an unexpected WAL page address, an invalid
checkpoint record, and `PANIC: could not locate a valid checkpoint record`.
The VM was reachable over SSH, but database TCP connections were refused.

The failed data directory and configuration were preserved before recovery:

- `/var/backups/amo-recovery/incident-20261118/failed-cluster-and-config.tar`
- SHA-256: `245801cbe201ad5a5f62d0da1cc3d5df1b523343dbf8d7fc089ac88114aaf94a`

At the user's instruction, the completed logical backup at
`/var/backups/amo-postgres/20261111T110220Z` was restored into a new cluster.
All three files in its checksum manifest passed verification. The restore
completed with 820 public tables. PostgreSQL 16 `pg_amcheck --heapallindexed`
passed. The new cluster was initialized with data page checksums.

The existing `postgresql@16-main` service and its network/authentication settings
were retained. Its data directory now points to
`/var/lib/postgresql/16/restored_20261118`. The separate temporary cluster
registration `16/restored_20261118` has `start.conf=disabled` to prevent two
services from starting against the same data. The original failed directory
`/var/lib/postgresql/16/incident_clean` remains untouched. The previous main
configuration is also preserved under the incident backup directory.

The main service started successfully on port 5432. Both application read and
write connection settings authenticated successfully as `amodb_app`.
The API (8080), operations gateway (8090), and frontend proxy (5173) readiness
endpoints all returned HTTP 200. API readiness confirmed database, migrations,
and jobs readiness. The frontend index also returned HTTP 200.
An immediate fresh backup completed successfully at
`/var/backups/amo-postgres/20261118T045932Z`; its completion marker exists and
all three manifest checksums passed. The scheduled backup timer remains active.

Recovery point: 11 November 2026 at 11:02:20 UTC (14:02:20 Nairobi).
Changes after this backup are not included in the restored database. Integrity
checks do not establish that those later changes survived; the failed original
is retained for possible separate salvage.
