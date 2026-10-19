# Phase 9 — Consolidated architecture, domain ownership and operational boundaries

**Single branch / one draft PR:** \`codex/external-provider-platform-20261009\` / #560. Multi-tenant FastAPI + React/Vite + SQLAlchemy/Alembic, with PostgreSQL FORCE RLS when deployed.

## Strict owner separation

| Source domain | Primary owner | May decide / must not be inferred from |
|---|---|---|
| Supplier identity and commercial use | Procurement \`ProcurementSupplier\`, \`supplier_governance_service\`, \`supplier_quality_control\` | Commercial procurement status does not independently qualify a maintenance supplier |
| Provider organization, locations and metadata | Existing \`external_provider_*\` tables bound to supplier and tenant | A capability row is metadata, **not** an approved supplier scope |
| Credential/session, scoped external access | \`external_auth_core\` + \`external_identities\`, \`external_tenant_grants\`, \`external_sessions\` | Vendor account login grants no staff role, maintenance certification or DMS ownership |
| Regulator certificates and scope review | Quality and designated Maintenance/Safety reviewers | Uploaded certificates do not become verified or Authority-approved automatically |
| Supplier evaluation, qualification, restriction, risk classification | QMS \`quality_provider_qualification_cases\`, original supplier evaluation, \`quality_provider_restrictions\` and \`procurement_supplier_approval_scopes\` | Quality Manager's decision required; review and metrics must never self-approve |
| Contracts/acknowledgement | QMS \`quality_external_provider_contracts\`, DMS originals | Vendor receipt is **not** signature/Authority acceptance |
| DMS originals, published revisions, retention & evidence | Existing DMS/Manuals; Quality separately verifies originals | Upload success and virus scan are not QMS VERIFIED status |
| Audits, notices, findings, CAR/CAPA, effectiveness | Original QMS audit and corrective action modules | Provider module links to exact IDs; does not clone audit, CAR or effectiveness |
| RFQ, quotation, PO, shipment, receipt, hold, return | Canonical Procurement/Stores; partner collaboration proposals separate | No provider request makes a PO issued or stock released until internal authority records it |
| Contracted maintenance authorization | Maintenance Manager; independent Quality and Stores; Phase 7 \`external_contracted_work\` coordinates | PO is not technical order, retained uploaded form is not release or Safarilink CRS |
| Notifications, delivery & scheduling | Existing QMS center, partner center, Resend email logs and portal job scheduler | Phase 8 durable alert ledger is only an outbox; API 200/202 is **not** delivered/read |
| Provider 360, management review and trend views | Read-only Phase 9 \`provider_oversight_router\` from owner tables | On-time/cost/risk indicators cannot change eligibility or prove compliance |
| Critical/sole-source labels | Appointed Quality Manager with current verified Quality evidence | Qualitative decision stored with revision/audit; never determined by order-concentration formula |

## Tenant configuration and guards

- Provider categories, questionnaire and required checks: \`quality_provider_qualification_policies\`, exact adopted tenant manual references, Quality Manager review and optimistic revision. Baseline gates cannot be removed. No Safarilink annual audit is universal.
- Forms, acknowledgements and evidence requirements: \`external_provider_document_requirements\`, published DMS revision, QMS verification. Retention and legal hold still belong to DMS and appointed DCO authority.
- Delegation: \`external_tenant_grants\` capabilities and exact object_scope_json, review/revoke/expiry. External identities never inherit QMS or internal module roles.
- Alert routes/leads/escalation/templates/channels/digest/quiet hours: \`external_provider_alert_policies\`; changes now have attributed tenant audit record. Vendor preferences are identity-scoped in PostgreSQL.
- Human classification: \`external_provider_special_classifications\`, evidence FK, manager-only revision check and audit event. No score-based approval/reinstate/suspension.
- Supplier eligibility: \`supplier_quality_control\`, scope/contract/hold restrictions and authoritative work transitions run regardless of notification availability.
- Missing universal controls: user-specified retention is not permission to shorten mandated retention; no common source-proven retention engine or per-tenant application of all regulatory policies is claimed.

## Data architecture and performance

- Canonical read projection queries are **tenant + supplier-scoped**; provider register 50-row server pagination and SQL-filtered alert history; provider detail returns bounded categories and aggregated counts instead of full tenant workbooks.
- Phase 9 adds indexed \`(amo_id, status, expires_on)\` contracts, \`(amo_id, verification_state,valid_until)\` certificate lookup, surveillance due, work status, and indexed status-snapshot history. These are **unexecuted migration definitions**, not measured query plans.
- Phase 8 hourly scanner reuses the same scheduler, bounded current time windows; dedicated background export and large-source streaming/batch ingestion remain unfinished.
- New original uploads use existing shared storage, checksums, MIME/extension gates and fail-closed ClamAV, QMS/DMS review. Shared-object-store failover and scanner capacity must be verified in Phase 10.
- Changes to approved work date, scope, source evidence and profile state must invalidate only related future alerts; current status is re-checked at dispatch. Email transport needs provider-signed webhook to establish actual delivered/opened states.

## Security invariants

External identities have opaque, revocable cookies and CSRF proof; grant+membership+provider status+tenant+object authorization rechecked server-side. PostgreSQL \`app.tenant_id\`, \`app.external_provider_id\`, and \`app.external_identity_id\` guard new provider rows. Suppress sensitive descriptions, tokens, vendor contacts, source object URLs and internal identifiers in email. Direct links can only *navigate* to a source record that must separately authorize access. Deny new technical work when supplier/provider not eligible; allow only narrowly approved self-service and outstanding CAPA for suspended participants. Immutable source audit trails remain retained rather than mutated to depict past approval.

## Migration, API, and UI inventories

See \`PHASE9_INVENTORIES.md\`. The requirement status is in \`PHASE9_REQUIREMENT_MATRIX.md\`, risks in \`PHASE9_RISK_REGISTER.md\`, and execution-only acceptance in \`PHASE10_VERIFICATION_LEDGER.md\`.
