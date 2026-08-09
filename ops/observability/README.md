# AMO Portal observability foundation

This directory is the reproducible Phase 1 observability foundation for the Platform Operations programme. It is deliberately independent of the tenant FastAPI process.

## Components and pinned releases

- Prometheus `v3.13.2`
- Alertmanager `v0.32.1`
- Node Exporter `v1.11.1`
- cAdvisor `v0.60.5`
- OpenTelemetry Collector Contrib `0.157.0`
- Grafana `13.1.3`

Pins were selected from upstream release feeds on 2026-08-08. Review pins deliberately during upgrades; do not use `latest`.

## Roles

```bash
sudo ./ops/observability/scripts/install-ubuntu.sh --role all
sudo ./ops/observability/scripts/install-ubuntu.sh --role hub --bind-address 10.0.0.10
sudo ./ops/observability/scripts/install-ubuntu.sh --role agent --bind-address 10.0.0.21 --hub-address 10.0.0.10
```

`agent` runs Node Exporter, cAdvisor and an OTel Collector agent. `hub` runs Prometheus, Alertmanager, an OTel ingest collector and provisioned Grafana. `all` runs both roles for the current single-server deployment and registers local collectors through Docker service DNS.

The installer uses Docker's official Ubuntu apt repository if Docker Engine/Compose are absent. It rejects wildcard monitoring binds. A remote agent requires a trusted private hub address. Use a private LAN/Tailscale/VPN address and enforce host firewall policy.

## Registering nodes

On the hub:

```bash
./ops/observability/scripts/add-node.sh \
  --node-id app-02 \
  --address 10.0.0.22 \
  --environment production \
  --cluster-id amo-portal-production
```

Remove it with:

```bash
./ops/observability/scripts/remove-node.sh app-02
```

Prometheus uses file-based service discovery. Application code contains no node list.

## Isolation guarantees in this phase

Every telemetry container has an explicit CPU and memory ceiling. Agent OTLP export uses a memory limiter, batching, a bounded queue and bounded retry window. If the hub is unavailable, the queue eventually drops telemetry instead of growing without bound. No tenant request depends on these containers.

Prometheus, Alertmanager, Grafana, OTel ingest, Node Exporter and cAdvisor are published only on the configured explicit bind address. The repository defaults to loopback for validation. The installer never writes `0.0.0.0` or `::` as a host bind.

## Secrets

`.env` and `backups/` are ignored locally under this directory. The installer creates `.env` with mode `0600`. Grafana's admin password is generated once for hub/all roles when absent and is printed only on that generation run. Configure Alertmanager receiver credentials through deployment-local secret material before enabling paging.

## Backup / restore

```bash
sudo ./ops/observability/scripts/backup.sh /secure/backup/amo-observability
sudo ./ops/observability/scripts/restore.sh /secure/backup/amo-observability
```

Restore stops the observability Compose project. It refuses to overwrite a non-empty named volume; removing or moving an existing volume is an explicit operator decision. Version-controlled configuration and `.env` are not automatically overwritten: review `configuration.tgz` before restoring them.

## Verification boundary

Repository CI validates Compose, Prometheus rules/config, Alertmanager config, OTel config and shell scripts. A real Ubuntu clean-install, second-node registration, firewall reachability and resource-pressure demonstration require an Ubuntu host and remain deployment acceptance gates until executed and recorded. Do not label them verified from CI alone.
