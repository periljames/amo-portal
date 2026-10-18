# Phase 8 of 10 — Proactive Provider Alerts, Renewals and Escalation

**PR:** [#560](https://github.com/periljames/amo-portal/pull/560)  
**Branch:** codex/external-provider-platform-20261009  
**State:** Source changes committed. Phase 10 verification deliberately deferred. No Phase 9 changes.

## Architecture and sources of truth

Phase 8 reuses \`QMSNotification\`, \`external_partner_notifications\`, existing \`email_logs\`/Resend delivery events, and the \`portal_scheduler_main\` scheduled process. The \`external_provider_alert_jobs\` table is a **durable reconciliation/delivery ledger**, not a competing user-facing notification center. It has a unique tenant/fingerprint constraint, retry state, attempts, cancellation, delivery and acknowledgement timestamps. \`external_provider_alert_policies\` and \`external_provider_alert_preferences\` hold tenant departmental routing/dates/channels and individually scoped partner-member choices. Three tables are protected by PostgreSQL FORCE RLS and tenant/provider constraints. New Alembic revision: \`extprov_261018_alerts\` with parent \`extprov_261017_main_merge\`.

The scheduled scanner reads immutable Phase 4 qualification/restriction and Phase 6–7 Procurement/contracted-work transitions, supported certificate/evidence/approval/contract dates, recurring surveillance dates, canonical RFQ response deadlines, PO acknowledgement and promised-delivery dates, and manager-authored external work ETA/acknowledgement deadlines. It never treats a frontend badge as regulatory approval and never updates supplier or technical eligibility. Source status/date is rechecked when a reminder dispatches; superseded due dates, closed contracts and completed acknowledgements cancel pending obligations instead of generating stale notices. Phase 7 new dates and subsequent edits require the responsible Maintenance Manager and are recorded with attributable event provenance; contractor ETA proposals do not automatically amend authorized work dates.

Default **example** lead days: 120, 90, 60, 30, 14 and 7. They are **tenant-editable policy settings**, not statutory requirements. Default overdue escalation offsets: 0, 3 and 7 days. Scheduling uses the AMO tenant timezone, handles date-based milestones and allows quiet hours and daily email delivery windows. State-change notifications use stable authoritative event identity and do not repeat each worker scan; date-based alerts include current revision and each separate milestone in their identity. Work-item notifications deep-link to the exact authorized supplier/work action; server permission checks remain authoritative after link navigation.

Quality and Procurement each have departmental settings and dispatch history in their respective workspaces. Administrators have controlled tenant-wide delivery windows. External provider members can manage only their own notification preferences from the partner activity page; assigned contracted-work links and acknowledgements require current tenant/member/object grant checks. Provider email delivery is **not claimed** until verified external-email routing and addresses are supported. Staff email is optional; configured Resend hand-off and webhook delivery/read evidence remain separate. The ledger's \`DELIVERED\` state represents projection to the selected notification channel, **not** confirmed email inbox delivery or read. Retries/backoff and retry error visibility are available in the dispatcher and departmental UI.

## Coverage ownership

- **Implemented Phase 8 projection/reconciliation:** qualification requested/technical/Quality pending/approved/rejected, restrictions, selected metadata/site changes, certificate/evidence/scope/qualification expiry, agreement status/expiry/contract notice, surveillance audit due, RFQ invitations, RFQ response due, quotation and partner collaboration events, PO acknowledgement/delivery changes, shipment advice, contracted work assignment/technical transitions, extra work request and response, controlled contractor acknowledgement and expected completion deadlines.
- **Reused pre-existing authoritative QMS and DMS workflows, rather than duplicating:** audit notice issuance/rescheduling and auditee acknowledgement, document requests/evidence acceptance or rejection, findings, CAR response and CAPA follow-up, effectiveness review and repeat finding escalation. Confirm exact current-head hooks, deadlines and route coverage in Phase 10. This source work does not claim that every enumerated catalog event is fully wired.
- **Intentionally not assumed from unverified schema/workflows:** shipment physical receiving, formal Stores discrepancy/quality release, all return/RMA variants, authority regulatory expiry classification, and every external signature/acknowledgement status. These require matching existing canonical event sources before enabling full coverage, not synthesized frontend status.

## Security / trust boundaries

- No supplier approval, release, inspection signoff, written technical authorization, new contracted work, supplier eligibility or mandatory Quality control is granted by a notification.
- Portal and Quality roles are scoped to the tenant and owned department; vendor notifications are scoped to an active individual grant and specific assigned work.
- Generic messages omit technical/evidence contents, contract details, object store URLs and third-party addresses. Custom labels are limited plain text; never interpolate untrusted provider payloads.
- The delivery worker refreshes membership, tenant, role and current source state before dispatch. Duplicate delivery to a single recipient is prevented by the tenant/fingerprint uniqueness constraint, not an in-memory cache.
- Delivery retry/digest/quiet rules do not supersede official in-app evidence of technical/Quality decisions, and email HTTP 200/202 is never interpreted as recipient delivery or read.

## Phase 10 verification required before acceptance

No automated tests, type checking, builds, lint, migration execution, local CI or manual GitHub CI were run during Phase 8 per the user's instruction. Commits can still trigger GitHub-hosted Actions automatically; those have not been treated as verification. The following source-level items require critical verification/repair in Phase 10:

1. PostgreSQL migration upgrades/downgrades and Alembic current-head DAG; validate compound provider/supplier FKs, FORCE RLS and service role/tenant context.
2. Phase 8 authoritative schema mappings and lifecycle/status names, including \`procurement_rfqs\`, \`procurement_rfq_suppliers\`, \`quality_external_provider_contracts\`, \`quality_provider_surveillance\`, \`external_tenant_grants\`, and \`external_contracted_work\` JSON dates.
3. Outbox exactly-once/idempotency under concurrent schedulers, crash between API email accept/DB commit, transaction/savepoint rollback, unknown Resend webhook events, user role/grant revocation and tenant suspension.
4. All requested event types checked against current QMS/Procurement/Stores source transitions; complete any unmapped contract signatures, audit notices, CAR/CAPA, physical receiving/release and RMA event handoffs.
5. Lead-time edits, timezone/DST switches, date extensions, cancellation, escalations and recovery after prolonged scheduler outage; no false delivery/read flags, no alert loops, and per-tenant user/recipient preferences.
6. UI/API role matrix, Quality/Procurement ownership, partner-admin/member preferences and per-work-item deep links, including 404/403 after permission revocation and no cross-provider data inference.
7. Rate limits, signed Resend webhook reconciliation, spam/junk behavior and domain authentication before activating tenant email defaults.
8. Full functional, browser, accessibility, regression and multi-tenant acceptance suites only in Phase 10.

**Unverified means unverified.** This document records committed source coverage, not production or regulator acceptance. Do not merge #560 or start Phase 9 solely because Phase 8 source was committed.
