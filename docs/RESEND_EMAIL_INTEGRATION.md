# Resend email integration

AMO Portal uses **Resend as its only runtime outbound email provider**. SMTP, SendGrid, SES, Mailgun, Postmark and browser-local email configuration are excluded from the portal notification path. Resend is a platform-wide credential controlled only by a platform superuser; AMO administrators cannot create tenant-specific email-provider overrides.

## Delivery policy

The platform classifies outbound email before it reaches Resend:

- `ESSENTIAL`: password recovery, account verification and security messages. Always active.
- `CRITICAL`: overdue compliance actions, audit notices and escalation. Always active.
- `ROUTINE`: normal operational notifications. Requires both tenant and user opt-in.
- `RECEIPT`: delivery and workflow receipts. Requires both tenant and user opt-in.
- `MARKETING`: product updates, surveys and promotional communication. Requires both tenant and user opt-in.

Tenant administrators choose optional classes in **Administration → Integrations & automation setup**. Users choose their own optional classes in Inbox notification settings. Essential and critical classes are intentionally not switchable.

## Configure it

1. Sign in as a platform superuser.
2. Open **Platform → Integrations, API & Support**.
3. In **Resend email delivery**, paste the real API key into the field whose placeholder is `re_xxxxxxxxx`.
4. Leave **Sending mode** set to `DISABLED` while configuration is being prepared.
5. Save the configuration and run the non-sending API authentication check.
6. Send one explicit test email. This is the only setup action that marks the current configuration delivery-ready.
7. Configure the signed webhook URL in Resend:

   `https://<portal-host>/platform/email/resend/webhook`

8. Paste the optional Resend webhook signing secret (`whsec_...`) into the same superuser panel. Saving it invalidates delivery readiness, so repeat the authentication check and explicit test.

Do not put the real API key in source code, `.env` files committed to Git, frontend variables, screenshots, tickets or chat messages. Authenticated SDK calls are pinned to `https://api.resend.com`; the API key cannot be redirected to another configurable host.

## Secret storage and key rotation

The API key must be recoverable by the backend to call Resend, so it is **encrypted**, not one-way hashed. The existing platform secret vault encrypts the credential with Fernet and stores only a short SHA-256 fingerprint for display.

Production must provide `PLATFORM_SECRETS_KEY` through the deployment secret manager. Saving a replacement API key overwrites the encrypted credential, resets the provider state to `CONFIGURED` and clears the prior check timestamp. Every email resolves and decrypts the current database credential immediately before sending, so no long-lived provider instance can continue using a previous key.

Partial rotations are merged server-side. Leaving the API-key or webhook-secret field blank preserves its existing encrypted value rather than deleting it.

Recommended rotation sequence:

1. Create a new Resend key with the required permissions and domain scope.
2. Paste it into the portal and save.
3. Run the API authentication check; the state becomes `AUTHENTICATED` when the key is valid.
4. Send one explicit test email; Resend acceptance changes the state to `HEALTHY`.
5. Confirm the new key in Resend request logs.
6. Delete the old key in Resend.

## Credential states

- `CONFIGURED`: encrypted settings exist, but the current version has not been authenticated or delivery-tested.
- `AUTHENTICATED`: the current key can authenticate to the Resend API. Automatic email remains blocked.
- `HEALTHY`: the current settings passed authentication and Resend accepted one explicit test email. Automatic email may run subject to the selected sending mode and rate controls.
- `UNHEALTHY`: authentication or the explicit test failed. Automatic email is blocked.
- `DISABLED`: the provider is administratively disabled.

A non-sending authentication probe never promotes an untested configuration to `HEALTHY`. Recurring probes preserve `HEALTHY` only when the already-tested key continues to authenticate.

## Sending modes

### `DISABLED`

Configuration, API authentication and one explicit superuser test are permitted. Automatic portal email is blocked.

### `SANDBOX`

Every automatic portal email is rerouted to `sandbox_recipient`, regardless of the intended recipient. Use this for staging and pre-production verification.

### `PRODUCTION`

Automatic email is delivered to actual recipients. The backend accepts this mode only when:

- `APP_ENV=production` or `ENV=production`;
- the sender is on a custom domain rather than `@resend.dev`; and
- the superuser types `ENABLE RESEND PRODUCTION` during the configuration change.

Any configuration save changes the provider state back to `CONFIGURED`. Automatic email remains blocked until one explicit test email changes the current configuration to `HEALTHY`.

## Burst and duplicate protection

The portal enforces platform-wide per-minute and per-day limits before calling Resend. One PostgreSQL transaction advisory lock serializes each portal send decision, preventing concurrent workers or different AMO tenants from collectively passing the same limit check. Successful notifications with the same tenant, recipient, template and correlation ID are reused rather than sent again. Every Resend request also carries an idempotency key.

The explicit test endpoint is limited to one request per credential, recipient and minute. It does not change the selected sending mode or cause any additional messages.

## Templates

`template_map_json` maps portal template keys to a published Resend template ID or alias. Example:

```json
{
  "finding-issued": "finding-issued",
  "corrective-action-reminder": "corrective-action-reminder",
  "password-reset": "password-reset"
}
```

When no mapping exists, the portal sends a safe generic HTML/text notification so existing modules continue working while hosted templates are introduced incrementally.

## Health and delivery evidence

- The non-sending check authenticates against Resend without sending an email and records `AUTHENTICATED`, not delivery health.
- The long-running `amodb.jobs.saas_worker_safe` process runs the authentication probe at startup and then hourly by default. `RESEND_HEALTH_INTERVAL_SECONDS` can set an interval from 300 to 86,400 seconds.
- A PostgreSQL advisory lock and shared database interval prevent worker replicas from duplicating each recurring probe.
- `python -m amodb.jobs.platform_integration_health` remains available for an explicit operational authentication check.
- The explicit test confirms that Resend accepts a real email request and is the only action that records `HEALTHY` after a configuration change.
- Signed Resend webhook events update the matching portal email log with delivery, delay, bounce, complaint, suppression or failure information.
- Webhook processing stores and deduplicates the signed `svix-id` in the delivery-event history.
- The portal stores the Resend message ID in the email audit context; it never stores the API key in an email log.
- Password-reset links are delivered through this same Resend path and are never returned from the public password-reset request response.
- Resend message IDs and signed delivery events are stored in indexed columns/tables instead of scanning recent JSON logs.

## Deployment checklist

- Install backend dependencies from `backend/requirements.txt`.
- Set a production `PLATFORM_SECRETS_KEY`.
- Set `APP_ENV=production` only in the production deployment.
- Verify the sending domain in Resend and configure SPF, DKIM and DMARC.
- Register the signed webhook endpoint.
- Run the long-lived `amodb.jobs.saas_worker_safe` process so recurring authentication checks and integration jobs remain active.
- Start in `DISABLED`, authenticate the API key, send one explicit test, use `SANDBOX`, and enable `PRODUCTION` only after all checks succeed.


## Tenant QMS mail identities (2026-10-18)

The public QMS configuration page is `/maintenance/{amoCode}/quality/mail-identity/overview`.
Only the tenant Quality Manager or authorised AMO Administrator can save or test
mail identities; other QMS settings viewers can inspect the safe status summary.
The API is tenant-scoped at `/api/maintenance/{amo_code}/quality/mail-identity`.
It never exposes or accepts platform API keys, webhook signing secrets, SMTP
configuration, or arbitrary tenant selectors.

### Venspera shared sending domain

1. Add `notify.venspera.com` to the **Venspera Resend team**, publish Resend's
   DNS records, and confirm **sending verification** in the Resend Domains
   dashboard. Add SPF/DKIM and an appropriate DMARC policy. DNS verification
   is an operator action; an HTTP 200 send response cannot prove it.
2. In Platform Resend settings, set:
   - `from_email` to `notifications@notify.venspera.com`
   - `tenant_default_sender_domain` to `notify.venspera.com`
   - `sending_mode` initially `SANDBOX` and an approved sandbox recipient list
3. AMO Portal derives `quality.<tenant-login-slug>@notify.venspera.com`.
   Tenants cannot choose another tenant's shared address. Display names and
   reply destinations are tenant-scoped settings.
4. A tenant's QMS sender may be suspended independently; explicit Quality
   disable blocks QMS notices instead of falling back to the platform sender.
   Account-security messages (including password recovery and verification)
   retain Venspera's separate platform sender and remain unaffected.
5. Set a public HTTPS `PORTAL_FRONTEND_BASE_URL` to avoid private
   localhost/loopback CTA and signed audit notice QR links.
6. Configure signed Resend webhooks. Events and provider retrieval are retained
   as separate evidence. `ACCEPTED` means provider acceptance;
   `DELIVERED` means recipient-server acceptance, **not Inbox placement**;
   an open event is **not proof of human reading**.

### Optional tenant-owned sender domain

A tenant wishing to send as `quality@flysafarilink.com` must first provide
evidence of authority to use that domain. Venspera then:

1. Adds/verifies that exact sending domain in **its own Resend account**;
   the tenant publishes the DNS records. Check Resend's *sending* status.
2. Adds the domain to the platform `verified_sender_domains` list.
3. Sets the platform-only `tenant_sender_domain_assignments_json` map, for example:

```json
{
  "ID-Q50VN737": ["flysafarilink.com"],
  "ID-EXAMPLE02": ["notify.anotherairline.com"]
}
```

The map keys are **tenant IDs**, not display names. A custom domain may be
assigned to only one tenant, must be present in the platform approved domain
list, and is revalidated on each send. Revoking the assignment blocks
the old custom sender immediately. A tenant's QMS page then permits an address
on only its assigned domain.

**Reply-To is independent of sender identity.** Leave it blank to resolve the
tenant's currently active Quality Manager and Quality Officer mailboxes, or
specify up to ten authorised mailbox addresses. Audit notice sends include
the assigned audit team and designated audit CC addresses in Reply-To; actual
Reply and Reply All handling is controlled by recipients' mail clients.
An outbound address does not automatically create a mailbox. For inbound
routing under `notify.venspera.com`, separately configure Resend inbound
email handling or a verified forwarding/inbox service.

### Acceptance checks

- A Safarilink default notice sends from the Safarilink shared sender.
- A second tenant cannot save or send from that Safarilink shared sender.
- A tenant cannot select another tenant's custom domain even if globally
  verified in Resend.
- Removing a domain assignment prevents further messages from a previously
  saved custom sender.
- Tenant mail suspension prevents fallback through the platform account.
- The tenant self-test only targets the signed-in manager's own email (or
  sandbox remapped mailboxes); Resend acceptance is not mislabeled as delivery.
- Semicolon-separated sandbox recipients resolve as separate addresses.
- Rapid repeated notice issue and retry are idempotent with a 60-second
  retry cooldown, preserving one controlled notice and its recipient evidence.
- Signed per-recipient delivered/failed webhooks, replay, out-of-order events,
  bounce and complaint results are reflected without false read/inbox claims.
- Verify actual inbox placement independently using raw recipient message
  headers and Resend domain/SMTP evidence; a mail server's junk decision is
  outside the provider acceptance API.
