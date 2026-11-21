# Public CAR invitation access

## Access model

External auditees do not need an AMO Portal employee account. Possession of a valid CAR invitation is the credential. It is scoped to the CAR resolved by the existing CorrectiveActionRequest invite-token lookup and never grants employee permissions, Quality approval rights or access to sibling CARs.

## Browser and API flow

1. Newly issued links use /qms/car-access#token=<opaque-token>. Browsers do not send URL fragments in HTTP requests or Referer headers.
2. The public page reads the token in memory and calls /quality/cars/invite/current/... with Authorization: Bearer <token>. Requests omit cookies, use cache: no-store and Referrer-Policy: no-referrer.
3. The backend resolves current from request context then performs the existing token-to-CAR lookup. Tenant context is derived from the resolved CAR.
4. Legacy /car-invite?token=... and /qms/car-access/:token links are accepted and rewritten to the canonical fragment URL. Existing direct API path-token calls remain available during transition.
5. Attachment and issued-report downloads use bearer-authenticated fetches with temporary browser object URLs, not direct unauthenticated image/iframe requests.

## Invitation lifecycle

- Newly issued invitations use secrets.token_urlsafe(32), providing 256 bits of cryptographic randomness, and a per-CAR access-control record expiring 30 days after issuance.
- Rotation replaces the bearer and starts a new 30-day validity period. Old tokens no longer match the CAR.
- Quality may set another expiry, revoke a token or rotate it using the existing controls.
- Legacy links retain existing expiry/revocation state until explicitly governed; there is no forced migration/expiration of issued invitations.

## Rate limiting, cache safety and authorization

- Public routers use shared rate limiting per IP and capability. Production should enforce AUTH_RATE_LIMIT_REQUIRE_SHARED=true and configure Redis; when required but unavailable, requests fail closed.
- Public responses set private/no-store, no-referrer, nosniff and noindex/nofollow.
- Public feedback continues through bounded polling rather than EventSource, which cannot attach bearer headers.
- A CAR token cannot be used as an employee JWT or for authenticated Quality endpoints.

## Verification before merge

Run targeted backend tests, frontend Vitest, TypeScript checks, Playwright guest flows and end-to-end CAR control-loop CI. Review expired/revoked/rotated token handling, multiple-CAR isolation and audit-report authorization.
