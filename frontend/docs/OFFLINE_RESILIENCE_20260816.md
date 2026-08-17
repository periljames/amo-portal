# Offline and recovery UX contract

The portal displays one global dependency state and one outbox state. `navigator.onLine` is only a hint; `/readyz` is authoritative.

- **Online** — server and database are ready.
- **Checking server** — one browser-tab leader is probing.
- **Server recovering** — API answered but a dependency is unavailable; honor `Retry-After`.
- **Offline** — transport is unavailable; cached screens remain viewable.
- **Session ended** — refresh was authoritatively rejected; return to sign-in without request loops.

Replayable local work is limited to roster drafts with a source reference, revision-guarded roster/task edits, and idempotent attendance events. Every saved item is tenant/user scoped, AES-GCM encrypted, ordered, leased to one tab and labelled `Waiting`, `Sending n of m`, `Confirmed`, `Conflict` or `Rejected`.

Controlled actions are live-only: deletes, approvals, rejections, payroll, roster submit/publish, regulatory sign-off, permission changes and uploads. A 503 with `request_accepted: false` is safe to retry; an ambiguous timeout after the server may have accepted a command must be resolved through its idempotency key/status endpoint rather than blindly repeated.

An offline logout clears visible cached reads immediately, blocks refresh recovery and persists a pending server revocation. The HttpOnly session is revoked automatically on recovery before another login is allowed. Refresh recovery is coordinated across tabs; one tab rotates the cookie and shares only the short-lived access response over a same-origin BroadcastChannel. Encrypted, unsynced drafts are not silently deleted; they remain inaccessible under their original user/tenant scope until that account returns or explicitly discards them.

The service worker precaches the release asset manifest so previously unvisited lazy route chunks are available after an offline refresh. It does not hold credentials or execute authoritative background writes; it asks an open authenticated client to replay. Background Sync is an enhancement only because browser support is not universal.

Before resending any timed-out draft, the outbox queries the tenant/user-scoped
durable command receipt. A succeeded command is confirmed locally without a
second write; a processing command waits; a conflict remains visible for review.
