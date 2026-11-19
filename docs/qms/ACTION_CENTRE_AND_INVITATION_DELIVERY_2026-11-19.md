# AMO Portal: connected Quality action centre and invitation delivery

PR #571 • Issues #572 and #573 • 19 November 2026

## Regulatory authority
The action centre is a read-only projection of existing governed QMS, Training, Document Control and external-provider sources. Personal to-dos are strictly separate. Watch preferences do not transfer assignment or approval powers. Users complete regulated actions only through source workflows, which retain their original validations, decisions, document histories, evidence and audit logs.

## Connected sources
- Training workflow steps: named assignee; Training Competence owns any changes
- Remedial training: named owner; Training Assessments owns completion
- Document reviews: named owner; existing controlled manual review remains authoritative
- Issued document acknowledgements: actual assigned recipient; document distribution remains authoritative
- Pending external-provider invitations: verified identity pending; Quality Manager/tenant admin review and safe resend
- Verified provider approval: a shared Quality Manager/tenant admin queue, never a blanket Quality Officer permission

The related-work API supports bounded server-side search, source, due category, and pagination. A missing source produces a partial-error warning, not false zero. The Today view gives a bounded ranked preview from governed, connected and owner-scoped personal lists. Preview counts are not the exhaustive register. Existing Inbox views and direct links are preserved.

## Email semantics and security
- A created invitation is not a sent email.
- Resend acceptance and message ID are not recipient-server delivery.
- Signed delivered webhooks establish recipient-server acceptance, not primary inbox placement.
- SANDBOX routes to the configured sandbox mailbox, not the intended recipient.
- Blocked/failed attempts remain recoverable through governed resend and scoped log history.
- Dedicated external-provider invitation/reverification/recovery templates avoid reusing the password-reset presentation contract.
- One-use codes and audit guest links are restricted to outbound email transport and the one-time authorised issuer response, never persisted in EmailLog audit context, generic provider-event views, or public account URLs.
- Provider receipt lookup is tenant/permission bound, includes bounded log/event history and hides raw webhook payload.
- An accepted provider invitation cannot be revoked by immediate repeated resend within a 60-second guard.
- Audit Prepare explicitly offers guest invitation email with copy-link fallback. Its backend default is off for compatibility; an email failure never invalidates the already-committed access grant. Only public HTTPS portal base URLs are accepted.

## Implemented files and tests
Backend: quality/work_inbox_router.py; quality/work_inbox_related_router.py; tasks/router.py; procurement/external_auth_router.py; notifications/providers.py; quality/audit_external_access_router.py.
Frontend: QmsWorkInboxPage, QmsDailyFocus, QmsConnectedWork, QmsPersonalTasks, ExternalProviderQualityPage, AuditPrepareWorkspace, associated services and scoped CSS.
Tests: Quality Inbox source and due logic; related Training/DMS/vendor owner/tenant scope and pending invitation expiry; provider mail templates, redaction, logged receipts, cooldown; audit guest mail HTTPS and transport; responsive and real-browser workflow regressions.

## Release gate
All applicable backend, frontend, full Vitest, PostgreSQL/RLS, external-provider, QMS audit/guest, Planner, operational Playwright, and security CI must pass at the exact PR head. Verify provider/sandbox configuration, signing domains, DNS authentication, signed Resend delivery events, real recipient inbox placement, one-use acceptance, and recoverable failure in a production-equivalent environment. None of those last-mile operational checks can be inferred from mocked CI alone. Do not merge or deploy while tests are failed or pending.

No new migrations, provider substitution, broad editor rewrites, or generic workflow transitions were introduced. Wider cross-department analytics and long-term performance baselines still require measured operational follow-up.

## Follow-up enhancements on the expanded PR
- **Authoritative document links:** related controlled reviews now open Document Control's Compliance/Reviews workspace and issued acknowledgements open its Distribution workspace, instead of generic QMS modules. The related-source regression asserts the navigation.
- **Local calendar interpretation:** the Today preview interprets UTC/offset personal-task due timestamps as instants on the signed-in browser's local date. Governed date-only due fields retain their calendar dates. The dedicated Quality unit test checks both forms.
- **Owner-scoped saved filters:** \`GET/POST/DELETE /work-inbox/saved-views\` uses the existing \`qms_task_assignments\` store with explicit \`QMS_SAVED_VIEW\` ownership and tenant isolation, 20-item cap, duplicate-title control, audited creation/removal and PostgreSQL per-user transaction locking. Search, source, due category, ordering and governed view are stored; no approval authority or source record mutation is persisted. The frontend exposes save/apply/remove controls with responsive layout.
- **Security and regression:** saved-view API returns only input filters (not audit metadata), rejects invalid sources, prevents cross-tenant deletion and is covered by backend lifecycle and browser apply/remove checks.
- **Limits:** a saved view is a filter preset, not permission elevation or a delegated record assignment. It is not a full server-pushed subscription or scheduled report. Operational delivery evidence and production email DNS/inbox placement still require real provider verification as separately documented above.
