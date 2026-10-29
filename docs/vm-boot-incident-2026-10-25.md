# VM boot incident — October 25, 2026

Public readiness and staff login returned HTTP 503. The API remained running but could not reach PostgreSQL on the VM. Tailscale reported the guest offline. Read-only inspection identified the running VMware Player guest and visually confirmed Ubuntu kernel `6.8.0-147-generic` stopped with `Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)`. No database inspection is possible at that boot state. Database corruption has not been established by this incident.

The VM configuration is `E:\AMOs DB_Server.vmx`; its single virtual disk is `E:\AMOs DB_Server.vmdk` (29,617,946,624 bytes). An earlier VMware log also reported that the disk needed repair; that warning is retained for investigation and was not treated as authorization to repair the sole image. The source Windows volume reported Healthy/Online, which does not establish guest filesystem integrity.

Preservation is outside Git under `%LOCALAPPDATA%\AMO-Portal\recovery\incident-20261025\vm-preserved`. Configuration, metadata and VMware logs were copied, followed by the full virtual disk while the guest remained at its kernel panic. A read-sharing-aware SHA-256 check matched the preserved image to the source image captured before restart:

`7F0D71A0D3932D66BC223D0C6D531FB9D1396FE21760F9A0A33FF38B9055CACF`

The verification manifest is `%LOCALAPPDATA%\AMO-Portal\recovery\incident-20261025\preservation.json`. This is a matching byte copy, not proof of guest filesystem/database consistency. The preserved image has not been booted or repaired.

The newest database archive found on this Windows account was `%LOCALAPPDATA%\AMO-Portal\backups\postgres\20261022T061003284975Z.tar`. Its `amodb.dump`, `globals.sql` and `contents.txt` all matched the archive's stored SHA-256 checksums. The dump timestamp is October 22, 2026, 06:08:40 UTC (2:08:40 a.m. EDT). Restoring it could omit subsequent changes. It has not been restored over the current database.

The user explicitly approved power-cycling the failed VM and trying an older installed kernel after preservation. The full copy completed and its source hash was collected before restarting the original VM; destination hashing then completed with a match. `vmrun` restarted only the known VM. GRUB 2.12 appeared with Ubuntu and Advanced options for Ubuntu. Automated input did not visibly change the selection; the default kernel booted again and returned to the same panic. The user was asked to select an older kernel manually in VMware. No filesystem repair, WAL reset, database replacement or package upgrades were executed.

After a successful older-kernel boot, inspect the running kernel, `/boot` capacity, initramfs files, package state, PostgreSQL and Tailscale before proposing a permanent boot repair. Preserve current data and obtain a fresh logical backup before any database recovery. The app-selector work remains separate from this boot incident.

References: [Ubuntu GRUB submenus](https://help.ubuntu.com/community/Grub2/Submenus), [Broadcom Workstation file-integrity guidance](https://knowledge.broadcom.com/external/article/341508/verifying-vmware-workstation-virtual-mac.html). Neither reference is authorization to delete VM files or run repair on the preserved disk.


Update, October 26: the user selected the older kernel and confirmed VMware was back on. Read-only SSH inspection confirmed `6.8.0-146-generic`, active PostgreSQL 16/main and Tailscale. The `amodb` database was writable-primary (`pg_is_in_recovery() = false`), with 72 user rows; public `/readyz` and authenticated staff login returned success. This is a service recovery check, not a full database integrity certification. `/` had 11 GB free and `/boot` 1.6 GB free. Both 146 and 147 initramfs files existed (74 MB each).

`dpkg --audit` reported a malformed `/var/lib/dpkg/status` at line 0. Permanent package/initramfs repair remains outstanding. Keep the working older-kernel boot available; obtain a fresh logical backup before attempting OS/disk repair. The preserved original image and October 22 backup remain untouched. No newer backup has yet been verified in this phase.


Before the Settings deployment on October 26, the restricted-key export completed successfully and verified all archive checksums plus source freshness (12-hour limit): `%LOCALAPPDATA%\AMO-Portal\backups\postgres\20261026T051036406187Z.tar`. This supplies a fresh logical recovery copy after the older-kernel boot.


Later read-only inspection (October 26, 05:44 UTC) found the currently running guest on `6.8.0-147-generic`, booted at 04:08 UTC. The earlier older-kernel observation describes the recovery attempt, not the present boot. PostgreSQL/private networking and Tailscale are reachable. `/var/lib/dpkg/status` and `/var/backups/dpkg.status.0` contain binary/NUL data; `status-old` is readable ASCII beginning with a normal package stanza. These files were inspected only. Package-state recovery still needs a controlled repair; no package database, bootloader or initramfs was changed during the Settings work.
