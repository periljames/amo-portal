# Platform Operations architecture

## Status

Phase 1 foundation. This document defines the target boundary and records what is implemented versus deliberately deferred.

## Non-negotiable boundary

The tenant API is not the observability database and the Superadmin browser must not query Prometheus or Grafana directly. Ordinary tenant requests must continue when Prometheus, Alertmanager, Grafana, Node Exporter, cAdvisor, OTel or the future Platform Ops Gateway is unavailable.

Target request path:

```text
Superadmin UI
    |
    +-- /platform-ops-api/* and /platform-ops-live/*
            |
            v
      Platform Ops Gateway (separate process/resources)
            |
            v
      bounded query registry + snapshot cache
            |
            v
      Prometheus / Alertmanager
```

Telemetry path:

```text
Application node N
  Node Exporter ----\
  cAdvisor ----------> Prometheus hub
  app -> OTel agent -> OTel hub -> Prometheus
```

The number of application nodes is infrastructure configuration, not application business logic. Prometheus file discovery under `ops/observability/runtime/targets` is the Phase 1 node registry.

## Current repository audit — 2026-08-08

The production compose currently has one backend container, one rostering automation container and one frontend container. The backend is host-bound on loopback and uses a single Uvicorn process by default. Uploads and application logs use host-local bind mounts under `/opt/amo-portal/shared`, which is a horizontal-scaling blocker until shared object/log storage is introduced.

The deployment script already runs Alembic once before starting services, which is the correct migration ownership direction for replicas.

The current Platform console is inside the tenant API. Its SSE loop periodically opens tenant-database read sessions per connected browser and rebuilds bootstrap snapshots. Multiple Platform pages also poll independently. This remains in place in Phase 1 to avoid a risky cut-over; Phase 3 introduces the isolated Platform Ops Gateway and prepared SSE snapshot cache, then the frontend migrates in Phase 4.

The current database engine has bounded local pools but no external-pooler switch on `main`; the useful external-pooler design from PR #487 is to be reconciled later rather than merged wholesale.

## Phase 1 implemented

- repository-owned observability Compose topology;
- agent/hub/all roles;
- Node Exporter and cAdvisor host/container signals;
- bounded OTel agent export path;
- central Prometheus, Alertmanager and provisioned Grafana;
- explicit private/loopback host binding;
- per-container CPU/memory limits;
- file-based node registration;
- configuration CI;
- backup/restore and Ubuntu install scripts.

## Deferred boundaries

Phase 2 instruments application/DB/worker/provider metrics with controlled cardinality. Phase 3 creates a separate Platform Ops Gateway and auth/query/cache/SSE contracts. Phase 4 moves Superadmin operational presentation to the gateway. Later phases add incidents/SLOs, capacity, product analytics, Tenant Fleet/360, bulk jobs, user scale, commercial analytics, changes, REAL/DEMO enforcement and horizontal/database scale hardening.

No Phase 1 artifact claims 1,000-tenant capacity. That claim is reserved for the production-equivalent load gate with 1,000 distinct tenant fixtures and monitoring-off/on comparison.
