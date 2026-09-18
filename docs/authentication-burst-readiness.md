# Authentication bursts and regional access

The supplied trace contains frequent successful refreshes followed by HTTP 429.
Previously, all users behind an IP shared ten refreshes per minute, and failed
refreshes could be retried immediately by unrelated requests. Device clock skew
could also make every newly issued JWT appear expired. These are amplification
risks; the trace alone cannot establish which triggered the first refresh.

The client now uses the server-issued token lifetime, coalesces concurrent
refreshes, serializes cross-tab rotation using Web Locks where available,
shares retry deadlines, and applies exponential backoff with positive jitter.
Throttling/transport errors preserve the session; rejected refresh credentials
still end it. A stale 401 reuses a newer token before attempting another rotation.
Healthy readiness probes are jittered and successful refreshes no longer force
an extra readiness probe while online.

## Deployment configuration

Install the updated backend requirements. For multiple API processes or replicas,
configure all replicas with the same dedicated Redis endpoint and namespace:

```dotenv
AUTH_RATE_LIMIT_REDIS_URL=rediss://USER:PASSWORD@HOST:6379/0
AUTH_RATE_LIMIT_REQUIRE_SHARED=true
AUTH_RATE_LIMIT_WINDOW_SEC=60
AUTH_RATE_LIMIT_MAX_ATTEMPTS=10
AUTH_RATE_LIMIT_IP_MAX_ATTEMPTS=3000
```

Ten attempts apply per login identity (tenant plus normalized identifier) or
verified refresh session. The broader IP limit applies independently to login,
refresh and cookie logout. A rotating credential retains its session's budget.
Existing stricter limits on other auth operations are preserved. Email and staff
code are separate identifier buckets; retain account lockout/security monitoring.
The IP ceiling is a starting configuration for shared networks, not a capacity
claim. Tune it against office/proxy populations and perimeter abuse controls.

Redis counters use an atomic increment/expiry script and return `Retry-After`.
A configured shared-store outage returns 503 rather than silently switching to
independent process limits. Without Redis, development uses bounded, expiring
in-memory counters; these are not a fleet-wide security boundary. Set
`AUTH_RATE_LIMIT_REQUIRE_SHARED=true` in production so missing configuration
cannot silently use development counters. Provision Redis memory for the expected
unique identities and use a no-eviction policy for limiter keys. Use a shared
limiter across API replicas serving the same authentication domain.

The atomic counter pattern follows the [Redis INCR documentation](https://redis.io/docs/latest/commands/incr/).

Run production API processes without `--reload`, behind TLS and a proxy configured
to trust forwarded client addresses only from your ingress. Do not trust arbitrary
forwarded headers. Use consistent signing keys, refresh pepper, and access-token
lifetimes across replicas. Keep authentication reads and refresh rotation on the
primary database; replica lag is inappropriate for token revocation decisions.

Existing `DB_EXTERNAL_POOLER` support can use a transaction pooler. Size the actual
fleet connection budget before increasing process counts: each direct API pool
defaults to 20 steady connections plus 20 overflow, and separate read engines and
workers add their own pools. Keep workforce/background jobs in their dedicated
processes and include them in that budget. Regional frontends do not require
independent writable auth databases: avoid multi-primary token rotation without
a separately designed consistency strategy. Regional latency and actual password
hashing CPU cost must be measured in staging.

## Reproduce the morning burst

Use dedicated staging users with real permissions and a private JSON file outside
version control containing at least 1,000 distinct `{amo_slug,email,password}`
records. The script logs each user in once, exercises bootstrap reads, rotates the
cookie, verifies the new access token, and logs out. It performs real writes.

```powershell
k6 run -e BASE_URL=https://staging.example.test -e USERS=1000 -e LOGIN_SPREAD_SECONDS=60 -e LOGIN_IDENTITIES_FILE=C:/private/staging-logins.json backend/tests/load/login_burst.js
```

Run again with `LOGIN_SPREAD_SECONDS=0` for simultaneous sign-ins and with 2,000
users for headroom. The [per-VU executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/per-vu-iterations/)
gives each user its own cookie jar and iteration. Run from each target region and
then concurrently from regions using disjoint identities. Also test office NAT,
multiple browser tabs, devices with skewed clocks, Redis outage, and API restart.
The existing `portal_resilience.js` tests sustained authenticated traffic; it does
not replace this password-login workload.

Initial acceptance targets in the script are under 1% failed requests, login p95
below 3 seconds/p99 below 5 seconds, and refresh p95 below 1.5 seconds. Review them
against the agreed regional service targets. Watch CPU, password verification time,
DB checkout waits/active connections, Redis latency, 429/503 rates, and worker
queue age throughout. Confirm a throttled session cannot lock out unrelated users.

Automated concurrency regressions validate request coordination and limiter
isolation, not deployed throughput. A 1,000-user production capacity claim requires
this staging test with production-sized infrastructure and regional measurements.
