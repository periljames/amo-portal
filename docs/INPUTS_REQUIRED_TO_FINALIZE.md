# INPUTS REQUIRED TO FINALIZE

Use this checklist to replace all placeholders.

| Missing item | Appears in | Why needed | Safe value example (EXAMPLE_ONLY) |
|---|---|---|---|
| Product source-of-truth file (`portal_spec.md`) | All docs with `UNKNOWN__FILL_ME` on roles/NFRs | Defines confirmed features/flows and non-functional targets | `portal_spec.md` including modules, tenants, upload/stream specs |
| Public domain(s) + DNS provider | `docs/DEPLOY_RUNBOOK.md`, `infra/nginx/nginx.conf` | Required for TLS cert issuance and production host routing | `portal.example.com` via Cloudflare |
| WAN strategy date + Funnel migration trigger | `docs/PRODUCTION_REFERENCE.md` | Required to plan change window and rollback path | Funnel until Q3; WAN after static IP ready |
| VLAN/subnet map | `docs/PRODUCTION_REFERENCE.md`, firewall intents | Needed for enforceable ACL rules and segmentation docs | `VLAN10 mgmt`, `VLAN20 edge`, `VLAN30 app`, `VLAN40 data` |
| Upload max sizes and concurrency | `docs/PERFORMANCE_PLAN.md`, `infra/nginx/nginx.conf`, `.env.example` | Needed for body limits, timeout tuning, capacity planning | `UPLOAD_MAX=512m`, `concurrency=20` |
| Stream SLO and timeout requirements | `docs/PERFORMANCE_PLAN.md`, `infra/nginx/nginx.conf` | Needed to tune long-lived SSE/socket timeouts | `proxy_read_timeout=3600s` |
| Tenant isolation model | `docs/SECURITY_BASELINE.md` | Determines threat boundaries and test requirements | Shared schema + strict amo_id filters |
| RPO/RTO and backup cadence | `docs/DEPLOY_RUNBOOK.md`, `.env.example` | Needed for backup automation and DR acceptance criteria | `RPO 15m`, `RTO 2h`, nightly full + WAL archiving |
| NAS protocol + mount path contracts | `docs/PRODUCTION_REFERENCE.md`, `.env.example` | Needed for durable file and backup path wiring | `NFSv4 /mnt/nas/amo/{uploads,backups}` |
| Secret store selection | `.env.example`, `scripts/deploy.sh` | Needed to operationalize no-secrets-in-git policy | Vault or 1Password Connect |
| CI/CD platform (if desired) | Not implemented due unknown | Required before adding automated pipelines safely | GitHub Actions with protected env secrets |
