# Phase 3 — External Partner Portal and provider self-service
Same branch: `codex/external-provider-platform-20261009`. One draft PR #560 against `main`, unmerged. No Phase 4 work.

## Source architecture and trust boundaries
- Route `/partner/:tenant/*` is a lazy-loaded external-only React shell. It is **not** behind the staff OAuth/JWT/RequireAuth maintenance framework, and never navigates to internal QMS, Procurement or Document Control routes.
- Vendor account login issues the Phase 2 HttpOnly vendor cookie and now navigates to `/partner/:tenant/home`. Existing `/vendor/account` remains the security/MFA/member-management surface; no second authentication store is created.
- All partner APIs live under `/api/external-provider/partner/{tenant_slug}`. They call Phase 2 `active_session`, check the requested tenant against the session tenant, capability, canonical supplier life cycle, current grant, vendor membership and named object scopes. Every SQL projection includes tenant and canonical supplier/provider predicates; audit and CAR reads require explicitly assigned audit IDs. The latest Quality `RELEASED` finding event is required before findings or related CAR details/responses are visible.
- New small relational workflow tables belong to the existing database: `external_partner_change_requests`, `external_partner_contract_receipts`, `external_partner_evidence_submissions`, `external_partner_notifications`. PostgreSQL FORCE RLS applies tenant policies, plus a transaction-local `app.external_provider_id` provider-membership isolation condition. Internal Quality reviews use separate staff auth, Quality roles, tenant context and explicit provider-context clearing.
- Supplier identity and approved scope remain **only** in canonical `procurement_suppliers`, `external_provider_*` identity metadata, `procurement_supplier_approval_scopes`, `quality_external_provider_profiles`, `quality_external_provider_contracts`, `quality_external_provider_evidence`, and QMS audit/CAR records. Phase 3 workflow tables store submissions, approvals and receipt history only; they do not clone these authorities.

## Connected backend endpoints
- `GET .../session`, `GET .../home`: vendor context, canonical approval and provider state, real pending RFQ/PO/audit-request/released CAR counts, expiring certificates, assigned expiring agreements, unread notifications and change-proposal counts.
- `GET .../organization`, `GET .../organization/{sites|contacts|capabilities}`, `GET .../change-requests`, `POST .../change-requests`: bounded identity lists and **proposed**, not applied, changes. Supported proposal kinds are IDENTITY, CONTACT, SITE, CAPABILITY, BANKING (commercial grant plus recent verified MFA; never bank account numbers) and RENEWAL. Server validates owning supplier for certificate/contract renewals. Quality reviews proposals in a separate internal route.
- `GET .../compliance`, `POST .../evidence`, `GET .../evidence/{id}/download`: authoritative approved scopes, certificates, evidence and queued provider submissions; max 20 MB, file type/signature gate, SHA-256, existing local/S3 `amodb.storage`, tenant/provider review identity, pending approval, same-origin CSRF, server-checked object assignments. Upload progress/cancellation are exposed via XMLHttpRequest in the React UI.
- `GET .../contracts`, `POST .../contracts/{id}/receipt`: assigned canonical contract version summaries and version-locked, non-signature acknowledgement / clarification with attributable audit events. A response is **not** a legal signature, automatic contract approval or a DMS controlled-document release.
- `GET .../quality`, `POST .../quality/cars/{id}/submit`: released notices, assigned document requests, released findings/CARs and accepted uploaded evidence. The CAR response endpoint reuses the authoritative QMS CAR submission handler; it requires an assigned, currently released audit and Quality-accepted evidence when the CAR requires evidence. Suspended providers may retain the delegated `capa.respond` capability for existing released CARs, not start new work.
- `GET .../procurement`, `GET .../contracted-work`: real supplier-bound RFQ and sent PO projections and approved scope metadata; no synthetic quotations, PO acknowledgements, release certificates or technical work transactions.
- `GET .../notifications`, `POST .../notifications/{id}/read`, `GET .../activity`: stored per-identity notifications/read state and attributable external security events, never raw internal staff IDs.
- Internal authorized staff: `GET .../quality/external-accounts/partner-change-requests`, `POST .../{id}/review`, `GET .../partner-evidence`, `GET .../partner-evidence/{id}/download`, `POST .../partner-evidence/{id}/review`. Quality Manager controls decisions; Quality Officer can inspect. Decision history is immutable in `external_security_events`. `ACCEPTED` proposal means **accepted for controlled implementation**, not changed Supplier/QMS authority. `ACCEPTED` upload means the submitted file was reviewed, **not** verified as an approved controlled document.

## Frontend workspaces
- **Home / Action Center:** live supplier standing, review deadlines, upcoming certificates/contracts, actionable task counts, notification counts and deep links.
- **My Organization:** canonical identity, sites, contacts, operational capabilities, roles, governed change forms, reviewed proposal history; search, page bounds and version labels.
- **Compliance:** approved scope, certificates, evidence registers, uploaded evidence state, progress-aware/cancellable uploads.
- **Contracts:** assigned agreement summaries, revisions, expiry, version-specific receipts and clarification; DMS release limitations accurately shown.
- **Quality:** actual assigned notice/request/finding/CAR panels; authorized, reviewed-evidence-backed canonical CAR response; bounded retrieval, per-operation recovery.
- **Procurement:** real issued RFQ/PO projection, with transaction controls explicitly reserved for Phase 6.
- **Contracted work:** approved supplier scope and explicit assignment count, without fabricated maintenance execution (Phase 7).
- **Users / Account Security:** existing Phase 2 account/MFA/session/member-management route, accessible from shell.
- **Notifications & Activity:** server notifications, read/unread action, per-member attributable history and partner-only deep links.
- Internal Quality account governance now includes partner-submitted change and evidence decision queues.
- Shared typed API, request cancellation/abort, pager, messages, forms, status chips, scoped navigation, mobile layout and lazy workspaces prevent a monolithic component.

## Explicit verification and deferred work
1. **No tests, builds, lint, migrations or CI were manually executed in Phase 3, as required.** All code is source inspected only, and runtime availability remains unverified. Automatic GitHub Actions may run on commits; do not treat them as an executed validation instruction or claim success.
2. The exact source supplier/workbook reconciliation remains absent and must be done under Phase 10 with the uploaded Safarilink workbooks.
3. Vendor user-facing **controlled contract/DMS revision binary download** still needs explicit Document Control release and an existing reader streaming adapter: metadata is displayed, but no unauthorized file link is invented. Contract receipt cannot substitute for that release.
4. Quality documentary requests are visible and the user can submit tagged objective evidence, but automatic association with an existing guest-document-request lifecycle and Quality acceptance is **not** claimed. Phase 4/5 must wire the controlled request-specific upload bridge without bypassing guest auditor approvals.
5. The existing notification delivery primitive is used for Phase 2 account codes; Phase 3 writes attributable partner notification records and read state. Phase 8 will integrate complete QMS/Procurement/DMS outbound event dispatch, repeat/dedup rules, per-recipient templates and delivery confirmation.
6. RFQ quotations, PO acknowledgements, deliveries and accepted invoices are read-only in Phase 3: Phase 6 implements the real transactions. Maintenance contracted-work execution is deliberately reserved for Phase 7.
7. Phase 10 must test cross-tenant/provider grant isolation, RLS with and without `app.external_provider_id`, tampered browser scopes/tenant, member/account revocation during async requests, immutable event history, contractual revision conflict, Qual approvals, CAR release withdraw/reissue and actual Quality review, safe object storage, CSRF, MFA, rate limits, uploaded file signature/malware scanning pipeline, browser accessibility and navigation.
8. A malware/CDR quarantine service is not implemented in Phase 3; submissions are held for Quality review and should not be automatically distributed as trusted controlled data. Production distribution requires the established security scanning/release path before expanded DMS sharing.
9. No Phase 4 implementation is authorized until its separate prompt. Continue on the same single PR and branch.

## Phase 4 handoff
Build verified **partner onboarding and approval/evidence governance** on these contracts. Integrate Quality-approved certificate evidence, controlled source-chain, expiry monitoring, organization change requests, QMS response/request-specific document review, DMS controlled revision release and independently audited reviewer decisions. Continue the one consolidated draft PR and defer acceptance tests to Phase 10.


## Integration follow-through — 14 October 2026
The Phase 1–3 contract review repaired the approval scope enum mismatch, exposed canonical supplier lookup for Quality invitations, added explicit write-only capabilities for organization proposals and agreement receipts, hardened cross-member evidence metadata boundaries, and connected real assigned deadlines in Home.

Controlled agreement binaries are now accessible through the guarded partner contract document route, but **only** when member grants include both contract and manual IDs and DMS marks the matching revision as current PUBLISHED. The frontend uses a bounded authenticated download, never the internal DMS interface or a raw storage URL.

Audit document requests now have a distinct, assignment-bound upload within the partner Quality page. It invokes the existing governed QMS submission model/storage and enters the same QMS review queue; generic provider evidence upload remains a separate record used for supplier approval and CAR supporting evidence.

No Phase 10 migration/test/build/lint/browser run occurred during this source integration review. Do not equate committed source with a fully verified production workflow. Explicit document-release approvals, scanning, legacy DMS storage path compatibility, user-managed grant migrations and actual email/MFA behavior remain acceptance gates.


## Final source contract audit
Checked code presence and route inclusion for all eight lazy workspaces, vendor security UI, staff Quality review UI, four external FastAPI route mounts and Alembic Phase 1 → Phase 2 → Phase 3 revision parent links. This is *not* proof of database or TypeScript compilation success.

Phase 3 record ownership is enforced by the explicit tenant/supplier/member object queries and the partner-specific PostgreSQL RLS policy; the policy now fails closed if an external provider context is absent, while authorized internal Quality inspection sets a distinct marker.

Browser sign-out and account switching now invalidate the old active session. DMS current published revision download requires both the contract and document grants. The QMS document-request upload uses the existing QMS submission and storage system, not a second review queue.

Accepted provider organization change proposals remain pending controlled domain-owner application; no master data is rewritten simply because an external representative submitted a form or a Quality reviewer accepted it for processing. The user-requested no-test policy means this implementation **cannot yet be certified end to end**.
