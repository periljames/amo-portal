# Observability Data Contract

## Purpose

This contract defines what Platform Operations telemetry is allowed to contain, how it is queried, and how consumers must interpret availability and freshness. It describes repository behaviour; it is not evidence that production deployment or load-acceptance gates have passed.

## Isolation boundary

Ordinary tenant requests must not depend on Prometheus, Alertmanager, Grafana, Node Exporter, cAdvisor, or the Platform Operations Gateway. The Superadmin browser reaches the Operations Gateway; it does not query Prometheus or Grafana directly.

Telemetry sources are bounded infrastructure/application signals:

- Node Exporter: host CPU, scheduler, memory, swap, filesystem, disk, network, TCP, boot/uptime.
- cAdvisor: container CPU, memory, block I/O, start time/restart indicators.
- AMO application telemetry: process resources, SQLAlchemy pool state, PostgreSQL semantic health, API SLO rollups, queue/worker state and provider/job failure signals.
- Platform database rollups: route/SLO, capacity context, tenant health and product analytics.

## Prometheus query contract

`backend/amodb/apps/platform/ops_query_registry.py` is the authoritative browser-facing Prometheus allow-list. The browser may select only a repository-owned query key. Arbitrary PromQL is prohibited.

Each query defines:

- canonical expression;
- unit;
- maximum lookback;
- minimum step;
- maximum returned samples;
- query timeout;
- cache TTL.

Supported historical range aliases are `15m`, `1h`, `6h`, `24h`, `7d`, and `30d`, subject to each query's stricter maximum lookback. Queries are concurrency bounded. A failed Prometheus request must return a bounded unavailable/stale representation rather than blocking ordinary tenant traffic.

## Cardinality and privacy

Infrastructure metric labels must remain bounded. Prometheus metric labels must not contain tenant IDs, user IDs, email addresses, document IDs, work-order IDs, serial numbers, raw SQL, or similar unbounded business identifiers. CI enforces the application-metric prohibition.

Tenant/product analytics belong in database rollups, not Prometheus labels. Product analytics intentionally retain tenant/module/workflow aggregates without user-level analytics drill-down.

## Freshness and stale-data semantics

Prepared snapshots include `generated_at`. Gateway responses add a `freshness` object containing:

- `stale`;
- `age_seconds` when derivable;
- `last_error` when present;
- `source`.

A prepared snapshot is stale when the snapshot store reports a source error or when its age exceeds the gateway freshness threshold. Prometheus query results use the same principle: the last successful bounded result may be returned with `stale=true`, an error string and age; if no last-good value exists, the result is unavailable and contains an empty series.

Clients must display stale/unavailable state explicitly and must not silently present it as current telemetry.

## REAL and DEMO contract

`data_mode` accepts only `REAL` or `DEMO`. Database-backed Platform Operations queries must filter tenant-scoped records by the authoritative tenant `is_demo` flag. A request for the wrong environment must not fall back to the other environment.

Infrastructure telemetry is environment-neutral unless the deployment itself is separated. Tenant health, product analytics, SLO/database rollups, user search, Tenant Fleet/360 and commercial analytics must preserve the requested data-mode boundary.

## Units and timestamps

The query registry is authoritative for metric units. API timestamp fields are UTC ISO-8601 where produced by the application. Prometheus sample timestamps remain source timestamps. Consumers must not infer a unit from a metric name when the registry supplies one.

## Failure behaviour

- Prometheus or OTel failure must not make the tenant API unavailable.
- The Operations Gateway may report degraded/stale observability while remaining healthy enough to serve cached state.
- Product-analytics persistence failure increments sink failure/drop counters and is logged; the tenant request path remains unaffected.
- A missing Operations snapshot returns a bounded `503` warming/unavailable response.

## Change control

Adding a new browser-queryable metric requires updating the query registry, preserving bounded labels, specifying unit/lookback/step/sample/timeout/cache limits, and adding or updating CI coverage. Adding product analytics requires using the approved event taxonomy and metadata allow-list in `PLATFORM_ANALYTICS_TAXONOMY.md`.

## Acceptance boundary

Repository tests can prove configuration and contract behaviour. They do not prove real Ubuntu installation, private-network/firewall policy, second-node discovery, measured OTel/Prometheus overhead, outage isolation under real load, or the 1,000-distinct-tenant production-equivalent capacity gate. Those require recorded deployment evidence before any production-capacity verification claim is made.
