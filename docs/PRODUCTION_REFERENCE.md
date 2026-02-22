# PRODUCTION REFERENCE

## 1) Target architecture (Funnel-first, WAN-ready)

```text
[Internet Client]
      |
      | HTTPS
      v
[Tailscale Funnel OR WAN:443]
      |
      v
[EDGE VM - NGINX]
  |- /            -> frontend (APP VM)
  |- /api/*       -> backend (APP VM)
  |- /api/events* -> backend SSE (APP VM)
  |- /mqtt        -> MQTT broker websocket endpoint (ASSUMPTION__REVIEW)
      |
      +----------------------+
      |                      |
      v                      v
[APP VM]                 [DB VM]
- Frontend static assets - PostgreSQL (already isolated)
- FastAPI/Uvicorn        - Not publicly exposed
- Alembic migrations
- Upload staging paths
      |
      v
[NAS (separate metal)]
- Backups
- Large persistent files
- Media/archive payloads

Optional isolated services:
[NC VM] Nextcloud (separate from DB)
[JF VM] Jellyfin (separate for CPU/transcode isolation)
```

## 2) VM roles and responsibilities

- **EDGE VM**
  - Public ingress terminator (Funnel now, direct WAN later).
  - TLS + HTTP security headers + rate/connection limiting.
  - Reverse proxies requests to APP and broker endpoints.
  - Must be the **only** publicly exposed VM.

- **APP VM**
  - Runs portal backend + frontend artifacts.
  - Executes migration preflight and controlled Alembic upgrades.
  - Writes application logs and local transient upload buffers.

- **DB VM (existing)**
  - Dedicated PostgreSQL only.
  - No Nextcloud/Jellyfin or internet-facing workloads.

- **NC VM (optional)**
  - Host Nextcloud app workloads only if Nextcloud is used.
  - Must not share DB VM due to storage + CPU contention and larger attack surface.

- **JF VM (optional)**
  - Host Jellyfin/transcode workloads only if Jellyfin is used.
  - Isolate from APP to avoid transcoding spikes impacting portal latency.

- **NAS role (separate metal)**
  - Bulk storage tier: backups, long-term files/media, export archives.
  - Snapshot + replication target (policy `UNKNOWN__FILL_ME`).

## 3) Storage placement plan

### Local NVMe (EDGE/APP/DB local disks)
- DB WAL/data on DB VM local fast disk (already dedicated).
- APP local ephemeral upload temp directory for in-flight processing.
- Container layers and short-lived logs.

### NAS mounts (separate metal)
- Nightly logical DB dumps + periodic base backup archives.
- Large durable file repositories from upload domains.
- Optional media libraries for JF and document stores for NC.

`ASSUMPTION__REVIEW`: NAS mount protocol can be NFSv4 for Linux-first homelab unless security policy requires alternatives.

## 4) Network segmentation & firewall intent

`UNKNOWN__FILL_ME`: exact VLAN IDs/subnets.

Recommended intent:
- **Public/DMZ segment**: EDGE only.
- **App segment**: APP + broker endpoints.
- **Data segment**: DB + NAS.
- **Management segment**: SSH/Proxmox admin only.

Firewall policy intent:
- Internet -> EDGE: `443/tcp` only (`80/tcp` optional redirect).
- EDGE -> APP: app ports only (`3000` frontend container, `8080` backend container).
- APP -> DB: `5432/tcp` only.
- APP/DB -> NAS: backup/mount ports only.
- Deny east-west by default; open least privilege rules explicitly.

## 5) Public ingress strategy: Funnel now -> direct WAN later

### Funnel-first (current)
1. Keep EDGE listening on private interface.
2. Funnel publishes HTTPS endpoint to EDGE service.
3. Keep DNS CNAME/alias to Funnel target if needed.

### Direct WAN migration (later)
1. Provision public DNS A/AAAA to EDGE public IP.
2. Enable WAN port-forwarding `443 -> EDGE:443`.
3. Switch certificate automation to public ACME path.
4. Keep same internal upstream routes and env vars (no app rewrite).
5. Rollback path: repoint DNS to Funnel and disable WAN forward.

## 6) Separation decision rationale (blast radius)

- DB remains isolated to prevent application compromise from directly exposing data tier.
- NC separated from DB because file-sync + previews can saturate IO/CPU and inflate exploit scope.
- JF separated because transcoding bursts (CPU/GPU heavy) can violate portal latency budgets.
- NAS separate metal ensures backup/media IO does not interfere with transactional DB workloads.

## 7) UNKNOWN__FILL_ME and ASSUMPTION__REVIEW register

### UNKNOWN__FILL_ME
- `portal_spec.md` not present; product NFR values missing.
- Tenant isolation architecture standard not formally documented.
- Exact VLAN/subnet plan.
- Upload maximum sizes and concurrency targets.
- Streaming expected sustained client count and timeout objectives.
- RPO/RTO objectives.
- NAS protocol/security requirements.
- DNS provider and final domain names.

### ASSUMPTION__REVIEW
- `/mqtt` websocket reverse proxy retained for broker connectivity based on existing doc snippet.
- NFSv4 as baseline NAS mount protocol for Linux workloads.
- Single APP VM can host both frontend and backend containers initially.
