# Adding an Operations metric, dashboard or panel

The Platform Operations browser must never receive arbitrary PromQL. Add observability capability in this order.

## Add a metric

1. Instrument the application with OpenTelemetry or expose the metric from an approved exporter.
2. Keep metric labels low-cardinality. Do not use tenant IDs, user IDs, email addresses, document IDs, serial numbers, work-order IDs, raw SQL, URLs with IDs, tokens or secrets as metric attributes.
3. Add a fixed semantic query to `backend/amodb/apps/platform/ops_query_registry.py`.
4. Set its unit, maximum lookback, minimum step, maximum samples, timeout and cache TTL.
5. Expose it through a semantic `/ops/v1/...` endpoint. Do not add a browser endpoint accepting raw PromQL.
6. Add a unit/contract test for cardinality, bounds and stale-data behavior.

## Historical data

The query registry owns allowed ranges and downsampling. Current ranges are 15m, 1h, 6h, 24h, 7d and 30d. A query may support less than the global maximum. Keep the sample limit bounded; the browser must not trigger unbounded long-range queries.

## Add a Grafana panel

Repository-provisioned dashboards live under `ops/observability/grafana/dashboards/`. Add panels only for operational investigation or alert validation. The Superadmin application remains the daily operating surface; Grafana is not a replacement for tenant/support/commercial controls.

When editing dashboard JSON:

- use the provisioned Prometheus datasource;
- avoid dashboard variables that reveal sensitive tenant identifiers;
- choose bounded default ranges;
- show units explicitly;
- make stale/no-data distinguishable from zero;
- link to the relevant runbook when the panel represents a failure condition.

## Add an alert

Rules live in `ops/observability/prometheus/rules/`. Alerts should include an actionable condition and a stable severity. Validate with `promtool` through Platform Operations CI.

An alert is not automatically an incident. Create/correlate an incident when operational impact requires acknowledgement, mitigation, resolution and a durable timeline.

## Acceptance checklist

Before merging a new metric/panel:

- configuration validates;
- metric label cardinality is bounded;
- no sensitive identifiers appear in labels;
- query timeout/cache/sample bounds exist;
- stale behavior is explicit;
- the UI does not expose PromQL;
- relevant unit/CI contracts pass.
