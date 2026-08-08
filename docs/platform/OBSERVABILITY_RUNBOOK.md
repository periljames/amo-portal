# Observability runbook

## Safety model

Observability is diagnostic infrastructure, not a tenant runtime dependency. During an observability incident, preserve tenant service first. Do not restart the tenant backend merely to repair Prometheus/Grafana/OTel.

## Install

Use the repository installer from the checked-out deployment revision:

```bash
sudo ./ops/observability/scripts/install-ubuntu.sh --role all
```

For split topology, install the hub on a trusted private address, then each agent with the hub private address. Register agent scrape targets on the hub with `add-node.sh`.

## Verify

```bash
sudo ./ops/observability/scripts/verify.sh all
```

For a hub, inspect Prometheus Targets and confirm registered `node-exporter` and `cadvisor` targets are `UP`. Grafana is a deep SRE interface; the product frontend will use the dedicated Platform Ops Gateway in a later phase.

## Failure behavior

- Prometheus down: tenant API continues; the later Superadmin gateway will serve last-known data marked stale.
- Alertmanager down: metrics remain queryable; paging is degraded.
- Grafana down: tenant API and metric collection continue.
- OTel hub unreachable: each agent retries for a bounded window with a bounded queue, then drops telemetry rather than accumulating indefinitely.
- Node Exporter/cAdvisor down: only the affected signal source is unavailable; foundation alerts identify the node.

## Add/remove node

```bash
./ops/observability/scripts/add-node.sh --node-id app-02 --address 10.0.0.22 --environment production --cluster-id amo-portal-production
./ops/observability/scripts/remove-node.sh app-02
```

Prometheus file discovery refreshes without application code changes.

## Backup/restore

Run `backup.sh` to capture configs/targets and named data volumes. Keep backups outside the repository and restrict permissions. `restore.sh` stops only the observability Compose project and refuses to overwrite non-empty data volumes. The configuration archive is intentionally left for operator review rather than automatically overwriting deployment-local secrets or Git-managed files.

## Moving the hub

1. Back up the existing hub.
2. Install `--role hub` on the new trusted private host.
3. Restore data into empty observability volumes and review the configuration archive.
4. Change each agent's `OTEL_EXPORTER_OTLP_ENDPOINT` in its deployment-local `.env` and restart only `otel-agent`.
5. Ensure the new hub can reach registered Node Exporter/cAdvisor private addresses.
6. Verify all targets and alerts before retiring the old hub.

No application business logic changes when the hub address changes.

## Unverified deployment gates

CI cannot prove host networking, Docker daemon policy, Tailscale/VPN ACLs, clean Ubuntu idempotency, cgroup behavior or a second physical/VM node. Record those results during deployment acceptance. Never convert an unexecuted gate into a verified checkbox.
