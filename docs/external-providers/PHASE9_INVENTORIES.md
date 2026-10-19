# Phase 9 — Schema/migration, API, security and frontend workspace inventories

**Static inventory only.** Routes are mapped from tracked FastAPI decorators and the registered \`amodb/main.py\` composition; actual startup and browser navigation remain unexecuted. Paths below use \`{amo_code}\` or \`{tenant_slug}\` URL placeholders and do not authorize access by themselves.

## A. Schema/migration inventory and ownership

| Revision file / ID | Dependence / new controlled data |
|---|---|
| \`external_providers_20261009_foundation.py\` — \`extprov_261009_foundation\` | Canonical tenant supplier composite uniqueness, descriptive roles, sites, contacts, capabilities, certificates, relationships, account/scope links, source links/change events, staged import batches and source rows; row security |
| \`external_providers_20261012_identity.py\` | Global identities, password factors, external organizations/memberships, tenant provider links/grants, expiring identity tokens, opaque sessions, passkey challenges, security events |
| \`external_providers_20261012_partner_portal.py\` | Member-scoped change proposals, agreement receipts, partner original evidence submissions and in-app notifications |
| \`external_providers_20261014_quality.py\` | Tenant category policies, qualification cases, check evidence, restriction decisions, surveillance links and qualification audit events |
| \`external_providers_20261015_documents.py\` | Document requirements, published form acknowledgement, chunked upload/session metadata, DMS/QMS reference controls, agreement lifecycle extension |
| \`external_providers_20261016_procurement.py\` | External quote revisions, shipment advice, partner Procurement event log |
| \`external_providers_20261016_contracted_work.py\` | Governed contracted work, transition events, additional work, property/custody, required inspections and exact evidence links |
| \`external_providers_20261017_merge_main.py\` — \`extprov_261017_main_merge\` | Alembic DAG merge with upstream Reliability line; the merge revision is not a data-copy migration |
| \`external_providers_20261018_alerts.py\` — \`extprov_261018_alerts\` | Tenant per-department alert policies, identity preferences, unique fingerprint job/outbox and retry/delivery history; FORCE RLS |
| \`external_providers_20261019_oversight.py\` — \`extprov_261019_oversight\` | Append-only tenant provider status/risk snapshots, human critical/sole-source classification plus certified evidence FK, expiry/surveillance/work lookup indexes, tenant RLS |

**Phase 9 chain:** \`extprov_261017_main_merge → extprov_261018_alerts → extprov_261019_oversight\`. Earlier Phase 2–7 IDs, upstream DAG heads, exact generated SQL and downgrade compatibility must be confirmed in Phase 10 rather than inferred from filenames.

**Existing canonical entities reused** (no second master): \`procurement_suppliers\`, \`procurement_supplier_approval_scopes\`, \`quality_external_provider_profiles\`, \`quality_external_provider_contracts\`, \`quality_external_provider_evidence\`, \`procurement_rfqs\`, \`procurement_purchase_orders\`, \`procurement_receipts\`, \`procurement_receiving_inspections\`, \`procurement_quality_holds\`, \`qms_audits\`, \`qms_audit_findings\`, \`quality_cars\`, \`qms_corrective_actions\`, \`qms_notifications\`, \`email_logs\`, \`procurement_events\`, DMS publications and revision assets.

### Database constraints requiring execution acceptance

- \`amo_id\` and \`supplier_id\` composite foreign keys must reject cross-tenant objects.
- Phase 9 classification evidence reference must be tenant/supplier-qualified, current and Quality-VERIFIED before an appointed manager changes classification.
- \`external_provider_oversight_snapshots\` append-only trigger relies on prior immutable-event trigger function; verify PostgreSQL creation and reversible downgrade.
- Existing dynamically provisioned SQLAlchemy schema, Alembic graph and runtime tenant context must not result in duplicate constraints or unqualified reads.
- \`quality_external_provider_contracts\`, certificates, surveillance and contracted-work index definitions require actual PostgreSQL query plan/upgrade checks.
- Original QMS/DMS audit/notification tables must not be independently recreated in this platform.

## B. Backend API route inventory

| Root prefix | Owner / offered operations |
|---|---|
| \`/api/maintenance/{amo_code}/quality/suppliers\` | \`GET governance\`; \`GET/POST providers\`; \`GET /providers/{id}\`; \`PATCH .../profile\`; \`POST .../transition\`; \`GET/POST .../contracts\`; \`POST .../contracts/{id}/transition\`; \`GET/POST .../evidence\`; \`POST .../evidence/{id}/decision\`; original Quality route permission contract |
| \`/api/maintenance/{amo_code}/quality/provider-oversight\` | \`GET /providers/{supplier_id}\` tenant-authorized 360; \`PUT /providers/{supplier_id}/classification\` independent manager + verified-evidence decision; \`GET /portfolio\` bounded group counts; \`GET /calendar\` bounded expiry union; \`GET /register.csv\` audited, size-limited, formula-safe controlled register |
| \`/api/maintenance/{amo_code}/quality/external-qualification\` | \`GET/PUT /policies[/{category}]\`; \`GET /queue\`; \`POST /cases\`; \`GET/PATCH /cases/{case_id}\`; \`POST /checks/{requirement_key}\`, \`/review/{domain}\`, \`/audit\`, \`/decision\`; \`GET/POST /restrictions\`; \`POST /restrictions/{id}/lift\`; \`GET /alerts\`, \`POST /alerts/escalate\`; \`POST /surveillance/{id}/review\`; \`GET /providers/{supplier_id}/overview\`, \`/export\` |
| \`/api/maintenance/{amo_code}/procurement/suppliers/{supplier_id}/identity\` | \`GET/POST /{kind}\`; \`PATCH /{kind}/{record_id}\`; \`POST /{kind}/{record_id}/governance\`; roles/sites/contacts/capabilities/certificates/consent controls bound to supplier |
| \`/api/maintenance/{amo_code}/procurement/external-provider-imports\` | \`POST /preview\`; \`GET /history\` (paged, Phase 9); \`GET /{batch_id}\` (paged source rows); \`POST /{batch_id}/confirm\`, \`/supersede\`, \`/rollback\` |
| \`/api/external-provider\` | Vendor invitation acceptance/login/session/rotation/logout; session list/revocation, password recovery/reset, MFA enrollment/challenge/verification, identity verification, scoped member invite/revoke, profile, methods |
| \`/api/maintenance/{amo_code}/quality/external-accounts\` | Quality-owned member invitations/grant decisions/revocation/re-verification/session checks/security events and partner proposal/review/evidence; **not** tenant-wide employee authority |
| \`/api/external-provider/partner/{tenant_slug}\` | Scoped \`GET session,home,organization,organization/{kind},change-requests,compliance,contracts,quality,qualification,procurement,contracted-work,notifications,activity\`; permitted change/evidence/receipt/CAR/document-request/answer submissions, original downloads and notification reads |
| \`/api/external-provider/partner/{tenant_slug}/documents\` | Exact published form requirement & acknowledgement; upload create/parts/complete, status, submissions/original and assignment scopes |
| \`/api/maintenance/{amo_code}/quality/external-accounts/documents\` | Quality/DCO requirement control, candidate evidence, exact agreement controls, options, submitted original review, register-DMS, original download/history |
| \`/api/external-provider/partner/{tenant_slug}/commerce\` | RFQs/specs/invitations, quote revision/withdrawal, sent PO/document download/acknowledgement, clarification, shipment advice/cancel, invoice status/notice and scoped transaction histories |
| \`/api/maintenance/{amo_code}/procurement/partner-collaboration\` | Staff supplier collaboration inbox, decisions, technical alternate review, document import |
| \`/api/maintenance/{amo_code}/contracted-work\` | \`GET /,options,{work_id},{work_id}/available-evidence,{work_id}/grants\`; \`POST /\` draft; \`PUT /{work_id}/schedule\`; transition, additional-work decision, custody, inspections, linked evidence and member grant writes |
| \`/api/external-provider/partner/{tenant_slug}/maintenance-work\` | Scoped list/record, exact technical data, custody acknowledgement, provider transition, communications and additional-work request |
| \`/api/maintenance/{amo_code}/provider-alerts\` | \`GET /policy\`; \`PUT /policy/{department}\` audited; \`GET /delivery-history\` bounded by **authorized event catalog in SQL**; \`POST /delivery-history/{job_id}/retry\`, \`/acknowledge\` |
| \`/api/external-provider/partner/{tenant_slug}/alert-preferences\` | \`GET/PUT /\` identity preferences; \`GET /actions/{job_id}\`, \`POST /actions/{job_id}/acknowledge\` grant-scoped |

Existing canonical Procurement/Stores, QMS Audit/CAR/DMS and Platform/Resend API endpoints remain their original owners and were not copied here. A complete autogenerated runtime OpenAPI surface **has not** been produced, as startup execution is deferred.

## C. Frontend / workspace inventory

| Internal pages | Responsibilities / integration |
|---|---|
| Quality \`QmsExternalProvidersPage.tsx\` | Search, server-paged 50 provider register with status/risk/kind filters; detail overview, approval scope, agreements, evidence, monitoring, qualification |
| Quality \`ProviderOversight.tsx\` (Phase 9) | Lazy-on-open portfolio/expiry/calendar/export; 360 per provider from source aggregates, multisite capability, procurement/receiving/repair/QMS, human critical/sole-source classification |
| Quality \`ProviderQualificationWorkspace.tsx\` | Tenant category policy optimistic revision, case questions, evidence gates, technical/Safety/Authority assessment, audit link, restrictions and surveillance |
| Quality \`ProviderAgreementControls.tsx\` | Governed contract version/signed-evidence controls and associated DMS records |
| Quality \`ExternalPartnerQualityReview.tsx\`, \`ExternalProviderDocumentsReview.tsx\`, \`ExternalProviderDmsPage.tsx\` | Partner-change and evidence review, DMS document issuance/retention references, provider-specific authorized originals |
| Quality \`ExternalProviderPortalPage.tsx\`, \`ExternalProviderQualityPage.tsx\` | External member/grant provider account access governance, suspension/reinstatement with independent control |
| Procurement \`ProviderIdentityPanel.tsx\` | Sites, identity, capability, contacts and certificate control |
| Procurement \`ProviderImportPanel.tsx\` | Spreadsheet stage/review, history, paginated source rows, approved confirmation, safe CSV, guarded rollback/supersede |
| Procurement \`ProcurementModule.tsx\`, \`ProviderProcurementInbox.tsx\`, \`ProviderAlternateTechnicalReview.tsx\` | Canonical RFQ, PO, receiving, holds; provider inbox and specialized review |
| Maintenance \`ContractedWorkModule.tsx\` | Technical work creation, grant, variation, independent acceptance, scope, history, evidence, custody, deadlines |
| \`ProviderAlertSettingsPanel.tsx\` | Quality/Procurement/Maintenance/Stores owned settings and transport history |
| External \`ExternalPartnerPage.tsx\`, \`PartnerHome.tsx\`, \`PartnerOrganization.tsx\`, \`PartnerCompliance.tsx\`, \`PartnerDocuments.tsx\`, \`PartnerCommerce.tsx\`, \`PartnerQualification.tsx\`, \`PartnerQuality.tsx\`, \`PartnerProcurementWorkspace.tsx\`, \`PartnerContractedWork.tsx\`, \`PartnerActivity.tsx\`, \`PartnerPrimitives.tsx\` | Lazy scoped partner shell; canonical records, receipts, documented proposals, evidence, job operations, read/ack/history and preferences; staff JWT routes unavailable to vendor cookies |

**UI incomplete/unverified**: no measured accessibility/responsiveness, very large tables beyond bounded pages, real receipt/download/viewer under revoked grants, every role-specific action, and lossless download of multi-megabyte originals. No tests have been run.

## D. Security-controls inventory

| Control | Source-owned implementation / acceptance boundary |
|---|---|
| Tenant RLS | New provider tables FORCE RLS on PostgreSQL using \`app.tenant_id\`; classification/snapshot deny partner context; per-user preferences and action ledger use provider+identity context. **Needs real DB check** |
| External auth | Separate global identity vs staff users, Argon2, hashed session cookie, bounded TTL, MFA/WebAuthn, CSRF, invite/reset one-use codes; active provider and membership/grant checks |
| Privilege delegation | Exact \`object_scope_json\`, staff Quality vs Procurement vs Maintenance vs Stores decisions; no implicit DMS authority, no user-supplied role elevation |
| Operational eligibility | Original supplier Quality/Procurement eligibility gate and approved site/capability/contract, independent inspection; fail closed on scope/expiry/hold regardless of notification |
| Direct-object and deep-link authorization | Tenant/supplier qualified queries, provider assigned objects; URL filters are UX only, staff/provider record API remains authoritative |
| Original uploads | Bounded upload, content/MIME and signature checks, required ClamAV fail closed, SHA provenance, storage access and independent QMS/DMS acceptance |
| Controlled downloads | Tenant+provider+work assignment and published original rules; no document object-store URL in notification |
| Event integrity | Append-only source event models and immutable provider snapshots, authoritative transaction linkage, accountable employee/user identity; email receipt distinct from read |
| Notification denial | Active recipient/grant/identity at dispatch, personal preference, default in-app with optional verified vendor email, redacted body, policy audit trail |
| Bulk exports/imports | CSV formula neutralization, source SHA/mapping identity, upper row cap with explicit error, guarded import rollback before live refs |
| Tenant configuration | QMS baseline checks immutable; notification owner role matrix; audited changes; classification backed by verified QMS original |
| Deletion and preservation | Provider archival/rollback guarded against operative references, status and audit retained; source original and retention authorizations stay with existing DMS |
| Remaining source questions | Timing of role/tenant revocation, PostgreSQL provider RLS context, SQL scans at scale, missing case/contract events, resilience and data-retention rollout **require Phase 10 execution** |

## E. Performance/resource inventory

- Server-side provider list \`limit=50\` with bounded API \`limit<=200\`; current search remains SQL-lowered LIKE and requires actual index/query-plan evaluation.
- Tenant-scoped grouped projection queries and limited per-provider site/scope/contract evidence arrays; no full-workbook frontend transfer for oversight.
- Import history \`limit<=100\`, batch rows \`limit<=200\`; source workbook upload cap existing 10MiB and lazy \`openpyxl\` read mode, existing file closure.
- Hourly scheduler reuses application jobs; bounded date window and staff role SQL filter; still may scan hundreds of recent events and cannot guarantee no backlog loss in large tenants.
- Controlled CSV synchronous export capped at 10,000 active suppliers; larger exports explicitly blocked pending asynchronous implementation.
- Database timeout/deadlock, object store latency/large streaming download, long-lived worker recovery and in-flight request cancellation remain Phase 10 stress conditions.
