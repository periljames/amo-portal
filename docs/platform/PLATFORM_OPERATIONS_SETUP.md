# Platform Operations setup

This guide describes the repository-owned Superadmin Operations control plane. It does not replace host/network approval, production change control, or the deployment acceptance gates.

## Components

The production architecture separates four responsibilities:

1. **Tenant API (`backend`)** — normal tenant business traffic. It must remain available if monitoring or the Operations gateway fails.
2. **Platform Operations Gateway (`platform-ops-gateway`)** — Superadmin-only prepared snapshots, bounded historical queries, Tenant Fleet/Tenant 360, incident/change/product/commercial reads, and controlled command creation.
3. **Platform Operations Worker (`platform-ops-worker`)** — durable lease-fenced command execution. High-risk commands require a distinct second approver.
4. **Observability stack (`ops/observability`)** — Node Exporter, cAdvisor, OpenTelemetry Collector agent/hub, Prometheus, Alertmanager and Grafana.

The browser reaches the Operations gateway through the frontend origin under `/ops/`. Prometheus is never exposed directly to the browser and arbitrary PromQL is not accepted.

## Local development

Local development preserves the same browser contract as production: the frontend uses same-origin `/ops/*` URLs, while Vite proxies those requests to the dedicated Platform Operations Gateway instead of the tenant API.

Run the tenant API and Operations Gateway as separate processes:

```bash
cd backend
python -m uvicorn amodb.main:app --host 127.0.0.1 --port 8080 --reload
```

In a second terminal:

```bash
cd backend
python -m uvicorn amodb.platform_ops_main:app --host 127.0.0.1 --port 8090 --reload
```

Then run the frontend normally:

```bash
cd frontend
npm run dev
```

The Vite defaults are:

```text
normal API proxy target     http://127.0.0.1:8080
Platform Ops proxy target   http://127.0.0.1:8090
```

Override them only when the local topology differs:

```text
VITE_API_PROXY_TARGET=http://127.0.0.1:8080
VITE_PLATFORM_OPS_PROXY_TARGET=http://127.0.0.1:8090
VITE_PLATFORM_OPS_BASE_URL=
```

Keep `VITE_PLATFORM_OPS_BASE_URL` blank for same-origin development. This avoids mixed-content and CORS problems when the frontend is reached through HTTPS or a Tailscale hostname.

Verify the dedicated gateway directly before debugging the browser:

```bash
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS http://127.0.0.1:8090/readyz
```

The Platform Operations Worker is required when testing durable control-plane commands:

```bash
cd backend
python -m amodb.platform_ops_worker_main
```

Prometheus/Node Exporter/cAdvisor are not required merely to prove `/ops/v1` routing, but host CPU, memory, disk, network and historical telemetry remain unavailable until the observability plane is running and `PLATFORM_OPS_PROMETHEUS_URL` points to it.

## Production prerequisites

- Ubuntu host(s) approved for the AMO Portal workload.
- Private management addressing/Tailscale or equivalent private network.
- PostgreSQL connection strings in deployment-local secrets.
- A strong application `SECRET_KEY`.
- Docker Engine and Compose plugin. The installer can install these on supported Ubuntu hosts.
- A Superadmin identity that is global (`is_superuser=true`) and not tenant-bound.

## Deploy the observability plane

From the repository root, copy `ops/observability/.env.example` to the deployment-local environment file only if needed, then run the installer as root from `ops/observability`.

Examples:

```bash
sudo ./scripts/install-ubuntu.sh --role hub --bind-address 127.0.0.1
sudo ./scripts/install-ubuntu.sh --role agent --bind-address 10.0.0.21 --hub-address 10.0.0.10
sudo ./scripts/install-ubuntu.sh --role all --bind-address 10.0.0.10
```

The installer rejects wildcard host bindings. Deployment-local secrets are not committed.

## Deploy application control-plane services

The production Compose model includes:

```text
backend                 127.0.0.1:8080
platform-ops-gateway    127.0.0.1:8090
platform-ops-worker     no host port
frontend                127.0.0.1:3000
```

The deployment process must run Alembic once before starting/updating replicas. Do not let every application replica race migrations.

Recommended environment variables:

```text
DATABASE_WRITE_URL=...
DATABASE_READ_URL=...
DB_EXTERNAL_POOLER=true|false
PLATFORM_OPS_PROMETHEUS_URL=http://<private-prometheus>:9090
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://<private-otel-agent>:4318
PLATFORM_OPS_DB_POOL_SIZE=3
PLATFORM_OPS_DB_MAX_OVERFLOW=2
PLATFORM_OPS_WORKER_DB_POOL_SIZE=2
PLATFORM_OPS_WORKER_DB_MAX_OVERFLOW=1
```

Use an external transaction pooler when application replica count makes per-process SQLAlchemy pools inappropriate.

## Verify

Repository CI validates configuration, migrations, broker fan-out, durable fencing, privacy/cardinality contracts, a clean PostgreSQL upgrade, frontend build, and telemetry failure isolation.

On the deployment host additionally verify:

```bash
cd ops/observability
./scripts/verify.sh
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS http://127.0.0.1:8090/readyz
```

Then open the Superadmin Operations Control Center and verify REAL/DEMO separation, node metrics, historical ranges, Tenant Fleet, users, product rollups, incidents and durable jobs.

## What repository CI cannot certify

A merge must not be presented as proof of the following until they are run on the target environment:

- clean Ubuntu install and reinstall/idempotence;
- agent-only, hub-only and all-in-one roles on real hosts;
- a second VM/node registration;
- real Tailscale/firewall/ACL rules;
- measured monitoring overhead under CPU/memory/disk pressure;
- production storage/object-store migration;
- an actual 1,000-distinct-tenant load run with representative credentials and data.
