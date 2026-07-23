# AMO Portal SaaS Control Plane Hardening

**Date:** 2026-07-22  
**Stacked branch:** `agent/saas-control-plane-hardening`  
**Base branch:** `agent/quality-module-stability`

## 1. Objective

This release establishes the full-stack SaaS control-plane foundation required to operate AMO Portal as a multi-tenant product rather than a collection of portal screens.

The implementation covers:

- Quality-to-Training and shared-service integration health;
- horizontally claimable background work;
- encrypted integration credentials;
- global and tenant-specific provider configuration;
- module-level pricing and subscription control;
- recurring card checkout and webhook-controlled access state;
- M-PESA Daraja provider configuration;
- invoice generation and fiscalization state;
- KRA eTIMS OSCU/VSCU adapter controls;
- platform support tickets and conversations;
- AI-assisted support replies;
- superuser frontend controls;
- tenant and invoice pagination;
- API/worker deployment profiles;
- runtime capacity diagnostics and repeatable load validation.

This document defines what is implemented, what remains environment-specific, and the release evidence required before claiming production capacity.

## 2. Product architecture

The control plane remains inside the existing AMO Portal monorepo. It uses the same tenant, user, billing, entitlement and Alembic history as the operational modules.

The deployment is separated by runtime responsibility:

| Runtime | Responsibility |
|---|---|
| API replicas | Authentication, authorization, validation, bounded reads/writes, enqueueing work and returning job identifiers |
| SaaS workers | Payment-provider calls, webhook processing, provider health checks, AI support drafting and eTIMS fiscalization |
| Platform command workers | Existing diagnostics, tenant maintenance and approved operational commands |
| PostgreSQL | Tenant data, billing ledger, job queue, idempotency, provider configuration, audit records and worker leases |
| Persistent object storage | Controlled files, reports, invoices and retained evidence |

HTTP requests do not wait for external AI, payment, email, tax or platform-diagnostic calls. They commit a durable queue record and return.

## 3. Multi-tenant boundary

Tenant ownership continues to use `amo_id`. New control-plane records use `tenant_id` where the entity is a platform-level object that may be global or tenant scoped.

### Tenant isolation rules

- Provider configuration may be global or tenant specific.
- A tenant-specific provider overrides the platform default for that tenant.
- Provider secrets are encrypted at rest and never returned to the frontend.
- Tenant users may create and read only support tickets belonging to their AMO.
- Platform superusers may inspect and administer all tenants.
- Module subscriptions, billing accounts, invoices and jobs retain the tenant identifier.
- Queue workers receive the tenant identifier from the persisted job; they do not infer it from browser state.
- Billing and subscription changes are audited with actor, tenant, entity and reason.

## 4. Quality and Training integration

The canonical Quality calendar already provides the integration boundary:

`/api/maintenance/{amo_code}/quality/calendar`

The calendar combines:

- Quality audit schedules and planned audits;
- CAR due and target-closure dates;
- Training-record expiry dates;
- Training-session start and end dates.

Training data is loaded only when the tenant is entitled to Training and the required Training tables are available. A disabled or unavailable Training module returns an explicit source condition while Quality audit and CAR sources remain usable.

The runtime integration-health endpoint is:

`GET /platform/saas/integration-health`

It checks:

- direct and canonical Quality routes;
- Training routes;
- task, notification and billing routes;
- required Quality, Training, billing and support tables;
- important indexes;
- module-subscription states;
- worker heartbeats;
- queue depth and oldest pending job;
- SQLAlchemy pool state and PostgreSQL connection usage;
- the Quality-to-Training calendar contract.

The endpoint reports `HEALTHY`, `DEGRADED` or `BLOCKED`. It intentionally does not claim that a 1,000-tenant load target has passed.

## 5. Durable queue

The queue is implemented in `saas_jobs` and `saas_job_events`.

### Queue guarantees

- Jobs have a queue, type, tenant, idempotency key, correlation identifier, priority and maximum attempts.
- The unique key `(job_type, tenant_scope, idempotency_key)` prevents duplicate logical jobs.
- PostgreSQL workers claim jobs using `FOR UPDATE SKIP LOCKED`.
- Multiple workers can claim different rows concurrently without a global queue lock.
- Leases expire if a worker dies.
- Expired jobs return to retry or move to dead-letter state after their attempt limit.
- Retry delay uses bounded exponential backoff.
- Every state transition creates an event record.
- Queue depth, status counts and oldest pending age are exposed to the superuser console.

### Queues

| Queue | Work |
|---|---|
| `billing` | Stripe checkout creation and verified payment webhooks |
| `integrations` | Provider health checks |
| `fiscalization` | Certified eTIMS adapter submission |
| `ai` | AI-assisted support replies |
| `platform` | Existing platform command jobs |
| `default` | General bounded background work |

Workers can be scaled independently from API replicas.

## 6. Usage metering and request latency

API usage is accumulated in memory per API worker. A daemon owned by the API process flushes the batch; no ordinary request is selected to perform the database flush.

PostgreSQL usage increments use:

`INSERT ... ON CONFLICT (amo_id, meter_key) DO UPDATE`

The update adds the incoming amount to the stored amount atomically. This removes the lost-increment race in the previous read-modify-write implementation.

The database pool remains bounded through:

- `DB_POOL_SIZE`;
- `DB_MAX_OVERFLOW`;
- `DB_POOL_TIMEOUT`;
- pre-ping and connection recycling;
- controlled `503` handling when a pool checkout times out.

Capacity values must be chosen from load-test evidence and database connection limits. Multiplying API replicas without recalculating total possible PostgreSQL connections is prohibited.

## 7. Provider credential management

Provider records are stored in `saas_provider_credentials`.

### Security controls

- Secrets are encrypted with Fernet before persistence.
- Production requires `PLATFORM_SECRETS_KEY` from the deployment secret manager.
- The API returns only `has_secret` and a non-reversible fingerprint.
- Changing non-secret settings without supplying a new secret preserves the stored secret.
- Diagnostic output redacts common secret, password, token and key fields.
- Provider calls are made only from backend workers.
- Browser environment variables must not contain Stripe, OpenAI, SMTP, eTIMS or M-PESA secrets.

### Registered providers

- Stripe;
- M-PESA Daraja;
- KRA eTIMS OSCU;
- KRA eTIMS VSCU;
- SMTP;
- SendGrid;
- OpenAI;
- Azure OpenAI;
- Zendesk;
- Jira Service Management;
- Freshdesk.

A registered provider is not automatically operational. It becomes operational only after its configuration, credentials, network access and health test succeed.

## 8. Pricing, subscriptions and tenant modules

Module prices are stored in `saas_module_prices`.

A price contains:

- module code;
- plan code;
- billing term;
- amount in minor currency units;
- currency;
- trial days;
- tax rate in basis points;
- optional external payment-provider price reference;
- active/inactive state.

The frontend never supplies the authoritative invoice amount. Manual invoices resolve the stored price, quantity and tax on the server.

Each tenant module has one state:

- `ENABLED`;
- `TRIAL`;
- `SUSPENDED`;
- `DISABLED`.

The platform tenant screen supports audited batch updates of module states and plan codes. Payment webhooks can also update the same subscription state.

## 9. Recurring card billing

Stripe Checkout creation is asynchronous:

1. The superuser selects a tenant and a module price containing a Stripe price reference.
2. The API enqueues `STRIPE_CREATE_CHECKOUT_SESSION`.
3. A billing worker creates the Checkout session with tenant and module metadata.
4. Checkout remains pending; no module is enabled merely because the Checkout URL was created.
5. Stripe sends signed webhook events.
6. The webhook endpoint verifies the Stripe signature before storing the event.
7. A billing worker processes the stored event idempotently.
8. Active/trial subscriptions enable or trial the module.
9. Past-due or unpaid states suspend the module.
10. Cancellation disables the module.
11. Paid invoice events mark linked portal invoices paid when portal metadata is present.

The customer-facing card form and payment-method portal are hosted by the configured payment provider. Card data must not pass through AMO Portal application servers.

## 10. M-PESA

M-PESA is configured through the `mpesa_daraja` provider.

The provider registry supports:

- consumer key;
- encrypted consumer secret;
- shortcode;
- encrypted passkey;
- sandbox or production environment;
- callback URL;
- backend health checks against Daraja OAuth.

M-PESA collection is separate from recurring card subscriptions. A production collection workflow must define the exact Daraja product, callback reconciliation, idempotency, reversal handling, invoice matching and customer notification before activation.

## 11. Invoices and ledger

Manual invoice creation is idempotent and records:

- a ledger charge;
- a billing invoice;
- module, plan, term, quantity, unit price, tax rate and tax amount in the invoice description payload;
- issue date and due date;
- actor and reason in the platform audit log.

The platform billing screen provides:

- module price creation;
- tenant invoice creation;
- queued recurring Checkout creation;
- invoice pagination;
- manual paid-state correction with reason;
- eTIMS fiscalization queueing;
- billing queue visibility.

A manual paid-state change is an administrative correction and must not replace provider reconciliation in a production automatic-payment flow.

## 12. KRA eTIMS and iTax boundary

The portal models fiscalization separately from the billing invoice.

`saas_invoice_fiscalizations` records:

- provider;
- state;
- submitted request;
- redacted response;
- fiscal document number;
- control-unit serial;
- receipt signature;
- failure detail and timestamps.

The API blocks fiscalization until an OSCU or VSCU provider is explicitly marked as tested/certified. The worker then submits the invoice to the configured adapter endpoint.

This release does not claim that AMO Portal itself is KRA-certified. A production deployment must use:

- a KRA-tested and certified in-house OSCU/VSCU implementation; or
- a verified third-party integrator;
- production credentials and certificates;
- documented invoice, credit-note, cancellation and offline-recovery behaviour;
- finance and tax acceptance testing.

eTIMS invoice fiscalization does not automatically perform every iTax filing obligation. Tax returns, withholding, payroll and other iTax processes require their own legal, accounting and integration analysis.

## 13. Email

SMTP settings and secrets are managed through the provider registry.

The backend supports:

- TLS or SSL;
- authenticated SMTP;
- configured sender name and address;
- bounded connection timeouts;
- queued email work;
- provider health checks.

SendGrid is registered as a separate API provider. Provider-specific send adapters can be enabled without exposing API keys to the frontend.

## 14. AI and chatbot support

The support assistant uses a backend OpenAI provider configuration.

The AI worker:

- reads only the selected public support-ticket conversation;
- uses a constrained support instruction;
- does not claim that actions were performed;
- is instructed to escalate aviation safety, billing disputes, security incidents, tax/fiscalization issues and access changes to a human;
- writes an `AI_ASSISTANT` message to the ticket;
- records provider usage returned by the API;
- never returns the provider API key to the frontend.

AI output is support drafting, not autonomous administrative authority. It cannot activate subscriptions, change prices, modify tenant access or perform tax submissions.

## 15. Support desk

The internal support desk extends `platform_support_tickets` with:

- requester;
- tenant;
- category;
- priority;
- SLA due time;
- assignee;
- resolution;
- public messages;
- internal notes;
- AI-assisted replies.

Tenant users can access only their own tenant tickets. Platform superusers may operate the global queue. Provider records for Zendesk, Jira and Freshdesk allow later synchronization without replacing the internal source of truth.

## 16. Superuser frontend

### Tenants

- paginated tenant register;
- real/demo/all scopes;
- tenant provisioning;
- activation, suspension, lock and unlock;
- read-only support sessions;
- module subscription batch control;
- advanced tenant and asset detail.

### Billing

- price catalog;
- module, plan, term, tax and trial controls;
- Stripe price references;
- manual invoice generation;
- queued recurring Checkout;
- invoice pagination;
- fiscalization action;
- billing queue diagnostics.

### Integrations and support

- platform and tenant-specific provider configuration;
- encrypted-secret presence/fingerprint;
- queued provider health checks;
- durable job register;
- API keys;
- outbound webhooks;
- support ticket creation and conversations;
- queued AI support replies.

## 17. Deployment

Compose profile:

`deploy/saas/docker-compose.yml`

Required production variables include:

- `DATABASE_URL`;
- `PLATFORM_SECRETS_KEY`;
- `SECRET_KEY`;
- allowed frontend origins;
- persistent storage configuration;
- provider credentials supplied through the superuser console or a controlled bootstrap process.

Run:

```bash
docker compose -f deploy/saas/docker-compose.yml up --build
```

The profile starts:

- one migration job;
- API service with configurable Uvicorn workers;
- SaaS worker;
- platform command worker.

Scale workers and API containers independently:

```bash
docker compose -f deploy/saas/docker-compose.yml up --scale api=4 --scale saas-worker=4 --scale platform-command-worker=2
```

A production environment should place API containers behind a reverse proxy or load balancer with TLS termination, health checks, request limits and trusted forwarded-header configuration.

## 18. Capacity validation for 1,000 tenants

The committed k6 profile is:

`loadtests/k6_saas_control_plane.js`

It supports:

- 1,000 tenant virtual users;
- sustained platform-control traffic;
- Quality calendar traffic;
- Training integration reads;
- p95 and p99 thresholds;
- failure-rate and check thresholds;
- JSON summary output.

Example:

```bash
k6 run \
  -e BASE_URL=https://staging.example.com \
  -e PLATFORM_TOKEN="$PLATFORM_TOKEN" \
  -e TENANT_CONTEXTS_JSON="$(cat tenant-contexts.json)" \
  -e TENANT_VUS=1000 \
  -e DURATION=15m \
  loadtests/k6_saas_control_plane.js
```

Required acceptance evidence:

- API p95 and p99 latency;
- request failure rate;
- PostgreSQL CPU, I/O, locks and connections;
- database pool checkout and timeout rate;
- queue depth and oldest pending age;
- worker throughput and retries;
- webhook processing delay;
- object-storage latency;
- memory/CPU per API and worker replica;
- no cross-tenant record leakage;
- no lost usage-meter increments;
- no duplicate invoice, payment or fiscalization effects.

No statement that 1,000 tenants are supported should be made until this test passes against production-like data, infrastructure and provider sandboxes.

## 19. CI release gate

Workflow:

`.github/workflows/saas-control-plane-ci.yml`

The branch is releasable only when:

1. static SaaS contract gate passes;
2. Alembic graph contains `saas_20260722_control_plane` at the expected head;
3. migration upgrades a PostgreSQL database from the repository graph;
4. SQLAlchemy mappers configure;
5. required API routes are registered;
6. backend queue, encryption and webhook tests pass;
7. empty-queue worker smoke tests pass;
8. frontend service tests pass;
9. TypeScript production build passes;
10. changed platform files pass ESLint;
11. compose configuration validates;
12. the production-like load test and environment acceptance are completed outside CI.

## 20. Environment-specific work still required

The code foundation cannot supply or certify third-party services by itself. Before production launch, the operator must complete:

- Stripe account, products/prices, webhook endpoint and customer portal configuration;
- M-PESA Daraja application approval, production credentials, callback hosting and reconciliation tests;
- KRA eTIMS certified integration or verified integrator onboarding;
- OpenAI or Azure OpenAI account, model and usage limits;
- SMTP/SendGrid sender verification and DNS records;
- optional Zendesk/Jira/Freshdesk credentials and sync mapping;
- persistent object storage and backup/restore tests;
- TLS, WAF/rate limiting, DNS and load balancer configuration;
- database sizing, replicas/backups and connection-budget review;
- data-protection, payment, tax, aviation-record and retention review;
- disaster recovery and incident-response exercises.

## 21. Authoritative external references

- Stripe subscription webhooks: `https://docs.stripe.com/billing/subscriptions/webhooks`
- KRA eTIMS system-to-system integration: `https://www.kra.go.ke/business/etims-electronic-tax-invoice-management-system/learn-about-etims/etims-system-to-system-integration`
- Safaricom Daraja: `https://developer.safaricom.co.ke/`
- OpenAI API quickstart: `https://platform.openai.com/docs/quickstart`

These references define provider behaviour and onboarding expectations. Repository tests validate the portal contracts; they do not replace provider approval or legal/tax acceptance.
