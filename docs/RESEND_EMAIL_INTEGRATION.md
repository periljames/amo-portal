# Resend email integration

AMO Portal uses **Resend as its only runtime outbound email provider**. SMTP, SendGrid, SES, Mailgun, Postmark and browser-local email configuration are excluded from the portal notification path. Resend is a platform-wide credential controlled only by a platform superuser; AMO administrators cannot create tenant-specific email-provider overrides.

## Configure it

1. Sign in as a platform superuser.
2. Open **Platform → Integrations, API & Support**.
3. In **Resend email delivery**, paste the real API key into the field whose placeholder is `re_xxxxxxxxx`.
4. Leave **Sending mode** set to `DISABLED` while configuration is being prepared.
5. Save the configuration, run the non-sending health check, then send one explicit test email.
6. Configure the signed webhook URL in Resend:

   `https://<portal-host>/platform/email/resend/webhook`

7. Paste the optional Resend webhook signing secret (`whsec_...`) into the same superuser panel and repeat the health/test sequence.

Do not put the real API key in source code, `.env` files committed to Git, frontend variables, screenshots, tickets or chat messages. Authenticated SDK calls are pinned to `https://api.resend.com`; the API key cannot be redirected to another configurable host.

## Secret storage and key rotation

The API key must be recoverable by the backend to call Resend, so it is **encrypted**, not one-way hashed. The existing platform secret vault encrypts the credential with Fernet and stores only a short SHA-256 fingerprint for display.

Production must provide `PLATFORM_SECRETS_KEY` through the deployment secret manager. Saving a replacement API key overwrites the encrypted credential, resets the provider health state and clears the prior health timestamp. Every email resolves and decrypts the current database credential immediately before sending, so no long-lived provider instance can continue using a previous key.

Partial rotations are merged server-side. Leaving the API-key or webhook-secret field blank preserves its existing encrypted value rather than deleting it.

Recommended rotation sequence:

1. Create a new Resend key with the required permissions/domain scope.
2. Paste it into the portal and save.
3. Run the health check and explicit test email.
4. Confirm the new key in Resend request logs.
5. Delete the old key in Resend.

## Sending modes

### `DISABLED`

Configuration, health checks and one explicit superuser test are permitted. Automatic portal email is blocked.

### `SANDBOX`

Every automatic portal email is rerouted to `sandbox_recipient`, regardless of the intended recipient. Use this for staging and pre-production verification.

### `PRODUCTION`

Automatic email is delivered to actual recipients. The backend accepts this mode only when:

- `APP_ENV=production` or `ENV=production`;
- the sender is on a custom domain rather than `@resend.dev`; and
- the superuser types `ENABLE RESEND PRODUCTION` during the configuration change.

Any configuration save changes the provider state back to `CONFIGURED`. Automatic email remains blocked until the current configuration reaches `HEALTHY` through the non-sending check or an explicit test email.

## Burst and duplicate protection

The portal enforces configurable per-minute and per-day limits before calling Resend. PostgreSQL transaction advisory locks serialize each tenant's send decision, preventing concurrent workers from all passing the same limit check. Successful notifications with the same tenant, recipient, template and correlation ID are reused rather than sent again. Every Resend request also carries an idempotency key.

The explicit test endpoint is limited to one request per credential, recipient and minute. It does not enable normal portal delivery.

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

- The non-sending health check authenticates against Resend without sending an email.
- `python -m amodb.jobs.platform_integration_health` checks all configured Resend credentials and updates their health state. Schedule this command through the production job scheduler.
- The explicit test confirms that Resend accepts a real email request.
- Signed Resend webhook events update the matching portal email log with delivery, delay, bounce, complaint, suppression or failure information.
- Webhook processing stores and deduplicates the signed `svix-id` in the delivery-event history.
- The portal stores the Resend message ID in the email audit context; it never stores the API key in an email log.

## Deployment checklist

- Install backend dependencies from `backend/requirements.txt`.
- Set a production `PLATFORM_SECRETS_KEY`.
- Set `APP_ENV=production` only in the production deployment.
- Verify the sending domain in Resend and configure SPF, DKIM and DMARC.
- Register the signed webhook endpoint.
- Schedule the non-sending health job.
- Start in `DISABLED`, then `SANDBOX`, and enable `PRODUCTION` only after the explicit test succeeds.
